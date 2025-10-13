#!/usr/bin/env python3
import os
import json
import hashlib
import asyncio
import re
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

import sys
sys.path.append('/app')

from api.terminal_api_client import TerminalAPIClient, TerminalBusinessState
from api.data_structures import TerminalType
from api.connection_pool import get_client, release_client, get_pool_status

from gateway.mapping import build_incident_key_from_alert, sop_id_from_incident_key


SOP_DIR = Path(os.getenv("SOP_DIR", "./sop")).resolve()
TASK_DOC_PATH = Path(os.getenv("TASK_DOC_PATH", "./task_instructions.md")).resolve()
TASK_DOC_BUDGET = int(os.getenv("TASK_DOC_BUDGET", "131072"))

QTTY_HOST = os.getenv("QTTY_HOST", "127.0.0.1")
QTTY_PORT = int(os.getenv("QTTY_PORT", "7682"))
QTTY_PING = int(os.getenv("QTTY_PING", "55"))

ALERT_JSON_PRETTY = os.getenv("ALERT_JSON_PRETTY", "1") in ("1", "true", "TRUE", "True")

app = FastAPI()


def _read_task_doc() -> str:
    try:
        data = TASK_DOC_PATH.read_bytes()
        if len(data) > TASK_DOC_BUDGET:
            data = data[:TASK_DOC_BUDGET]
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _load_sop_by_id(sop_id: str) -> str:
    # 1) 文件直接命中 .md/.txt/.json
    for ext in (".md", ".txt", ".json"):
        p = SOP_DIR / f"{sop_id}{ext}"
        if p.exists():
            try:
                if p.suffix == ".json":
                    return json.dumps(json.loads(p.read_text("utf-8", errors="replace")), ensure_ascii=False, indent=2)
                return p.read_text("utf-8", errors="replace")
            except Exception:
                continue

    # 2) 扫描 jsonl
    try:
        for jsonl in SOP_DIR.glob("*.jsonl"):
            with jsonl.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    cand = obj.get("sop_id") or obj.get("id") or obj.get("incident_key")
                    if cand and str(cand) == sop_id:
                        # 优先字段
                        for k in ("sop", "content", "text", "body"):
                            if k in obj and obj[k]:
                                v = obj[k]
                                return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=2)
                        # 兜底输出整对象
                        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return ""


def parse_q_response(content_buffer: str) -> Dict[str, Any]:
    """解析Q的输出，提取关键分析结果"""
    try:
        # 尝试提取JSON部分
        json_match = re.search(r'> \{.*?\}(?=\s*$)', content_buffer, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)[2:].strip()  # 去掉 "> "
            analysis = json.loads(json_str)
            return {
                "type": "analysis_complete",
                "analysis": analysis,
                "summary": format_analysis_summary(analysis)
            }
    except:
        pass
    
    # 如果无法解析JSON，提取关键信息
    summary = extract_key_insights(content_buffer)
    return {
        "type": "analysis_partial", 
        "summary": summary,
        "raw_content": content_buffer[-1000:]  # 保留最后1000字符
    }

def format_analysis_summary(analysis: Dict[str, Any]) -> str:
    """格式化分析结果为可读摘要"""
    parts = ["=== 告警分析结果 ==="]
    
    # 工具调用
    if "tool_calls" in analysis:
        parts.append("1. 工具调用:")
        for i, call in enumerate(analysis["tool_calls"], 1):
            tool = call.get("tool", "未知")
            result = call.get("result", "")
            parts.append(f"   {i}) {tool}: {result[:100]}...")
    
    # 根因分析
    if "root_cause" in analysis:
        parts.append(f"2. 根因分析: {analysis['root_cause']}")
    
    # 证据
    if "evidence" in analysis:
        parts.append(f"3. 支持证据: {analysis['evidence']}")
    
    # 建议措施
    if "suggested_actions" in analysis:
        parts.append("4. 建议措施:")
        for action in analysis["suggested_actions"]:
            parts.append(f"   - {action}")
    
    return "\n".join(parts)

def extract_key_insights(content: str) -> str:
    """从原始内容中提取关键洞察"""
    lines = content.split('\n')
    insights = []
    
    for line in lines:
        line = line.strip()
        # 查找包含关键词的行
        if any(keyword in line.lower() for keyword in 
               ['cpu', '告警', 'alert', '根因', 'root cause', '建议', 'suggest']):
            if len(line) > 10 and len(line) < 200:  # 过滤太短或太长的行
                insights.append(line)
    
    if insights:
        return "关键发现:\n" + "\n".join(f"- {insight}" for insight in insights[-5:])
    return "正在分析中..."


def resolve_sop_id(payload: Dict[str, Any]) -> Optional[str]:
    # 优先 sop_id
    if isinstance(payload.get("sop_id"), str) and payload["sop_id"].strip():
        return payload["sop_id"].strip()

    # 其次 incident_key → sop_id
    if isinstance(payload.get("incident_key"), str) and payload["incident_key"].strip():
        return sop_id_from_incident_key(payload["incident_key"].strip())

    # 最后 alert → incident_key → sop_id
    alert = payload.get("alert")
    if isinstance(alert, dict):
        ikey = build_incident_key_from_alert(alert)
        if ikey:
            # 将生成的incident_key存回payload供后续使用
            payload["incident_key"] = ikey
            return sop_id_from_incident_key(ikey)
    return None


def build_prompt(text: str, sop_id: Optional[str], alert: Optional[Dict[str, Any]]) -> str:
    # 斜杠命令直接透传
    if text.strip().startswith("/"):
        return text

    parts = []
    # TASK
    task_doc = _read_task_doc()
    if task_doc:
        parts.append("## TASK INSTRUCTIONS\n" + task_doc.strip())

    # SOP
    if sop_id:
        sop_body = _load_sop_by_id(sop_id)
        if sop_body:
            parts.append(f"## SOP ({sop_id})\n" + sop_body.strip())

    # ALERT JSON
    if alert:
        try:
            j = json.dumps(alert, ensure_ascii=False, indent=(2 if ALERT_JSON_PRETTY else None))
        except Exception:
            j = str(alert)
        parts.append("## ALERT JSON\n" + j)

    # USER
    parts.append("## USER\n" + text)

    return "\n\n".join(parts) + "\n"


async def stream_sse(generator):
    async def event_iter():
        try:
            async for item in generator:
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(event_iter(), media_type="text/event-stream")


@app.post("/ask")
async def ask(req: Request):
    payload = await req.json()

    text = str(payload.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")

    sop_id = resolve_sop_id(payload)
    alert = payload.get("alert") if isinstance(payload.get("alert"), dict) else None

    prompt = build_prompt(text, sop_id, alert)

    # 使用连接池获取客户端
    connection_id = f"sop_{sop_id or 'default'}"
    ttyd_query = (f"arg={sop_id}" if sop_id else None)
    
    client = await get_client(
        connection_id=connection_id,
        host=QTTY_HOST, 
        port=QTTY_PORT, 
        terminal_type=TerminalType.QCLI, 
        ttyd_query=ttyd_query
    )
    
    if not client:
        raise HTTPException(status_code=503, detail="无法获取终端连接，请稍后重试")

    async def gen():
        try:
            if client.terminal_state != TerminalBusinessState.IDLE:
                yield {"type": "error", "message": "终端未就绪"}
                return

            json_started = False
            content_buffer = ""
            last_analysis_time = 0
            
            async for chunk in client.execute_command_stream(prompt):
                if chunk.get("type") == "content":
                    content = chunk.get("content", "")
                    content_buffer += content
                    
                    # 检测JSON开始
                    if not json_started and ('"tool"' in content_buffer or '> {' in content_buffer):
                        json_started = True
                        yield {"type": "status", "message": "开始分析..."}
                
                # 流式输出原始内容
                if json_started:
                    yield chunk
                
                # 定期解析并输出分析摘要
                current_time = asyncio.get_event_loop().time()
                if current_time - last_analysis_time > 2.0:  # 每2秒解析一次
                    parsed = parse_q_response(content_buffer)
                    if parsed["type"] != "analysis_partial" or "cpu" in content_buffer.lower():
                        yield parsed
                        last_analysis_time = current_time
            
            # 最终解析
            final_result = parse_q_response(content_buffer)
            yield final_result
                    
        except Exception as e:
            yield {"type": "error", "message": f"执行错误: {str(e)}"}
        finally:
            pass

    return await stream_sse(gen())


@app.get("/healthz")
async def healthz():
    pool_status = get_pool_status()
    return JSONResponse({
        "ok": True,
        "sop_dir": str(SOP_DIR),
        "task_doc": str(TASK_DOC_PATH),
        "qtty": {"host": QTTY_HOST, "port": QTTY_PORT},
        "connection_pool": pool_status
    })


