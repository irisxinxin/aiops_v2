#!/usr/bin/env python3
import os
import json
import hashlib
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from api.terminal_api_client import TerminalAPIClient, TerminalBusinessState
from api.data_structures import TerminalType

from .mapping import build_incident_key_from_alert, sop_id_from_incident_key


SOP_DIR = Path(os.getenv("SOP_DIR", "/app/aiops/sop")).resolve()
TASK_DOC_PATH = Path(os.getenv("TASK_DOC_PATH", "/app/aiops/task_instructions.md")).resolve()
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

    # 构造客户端（每次请求新建，稳定但 QPS 较低）
    client = TerminalAPIClient(host=QTTY_HOST, port=QTTY_PORT, terminal_type=TerminalType.QCLI)

    async def gen():
        try:
            ok = await client.initialize()
            if not ok or client.terminal_state != TerminalBusinessState.IDLE:
                yield {"type": "error", "message": "QTTY 未就绪"}
                return

            # 进入指定会话目录（按 sop_id 隔离）并启动/继续会话
            if sop_id:
                # 在 q_entry.sh 中通过 --resume 实现，这里直接发送聊天命令
                pass

            async for chunk in client.execute_command_stream(prompt):
                yield chunk
        finally:
            try:
                await client.shutdown()
            except Exception:
                pass

    return await stream_sse(gen())


@app.get("/healthz")
async def healthz():
    return JSONResponse({
        "ok": True,
        "sop_dir": str(SOP_DIR),
        "task_doc": str(TASK_DOC_PATH),
        "qtty": {"host": QTTY_HOST, "port": QTTY_PORT}
    })


