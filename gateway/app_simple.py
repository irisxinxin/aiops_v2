import os, sys, json, asyncio, time, re, subprocess
from typing import Any, Dict, Optional
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from gateway.mapping import build_incident_key_from_alert, sop_id_from_incident_key

APP_NAME = os.getenv("APP_NAME", "q-gateway-simple")
SESSION_ROOT = Path(os.getenv("SESSION_ROOT", "./q-sessions"))
SOP_DIR = Path(os.getenv("SOP_DIR", "./sop"))
TASK_DOC_PATH = Path(os.getenv("TASK_DOC_PATH", "./task_instructions.md"))
TASK_DOC_BUDGET = int(os.getenv("TASK_DOC_BUDGET", "131072"))
ALERT_JSON_PRETTY = os.getenv("ALERT_JSON_PRETTY", "1") not in ("0","false","False")

Q_TIMEOUT = int(os.getenv("Q_TIMEOUT", "90"))
MIN_OUTPUT_CHARS = int(os.getenv("MIN_OUTPUT_CHARS", "50"))

app = FastAPI(title=APP_NAME)

def _read_task_doc() -> str:
    if not TASK_DOC_PATH.exists():
        return ""
    data = TASK_DOC_PATH.read_bytes()
    if TASK_DOC_BUDGET and len(data) > TASK_DOC_BUDGET:
        data = data[:TASK_DOC_BUDGET] + b"\n..."
    return data.decode("utf-8", "ignore").strip()

def _load_sop_text(sop_id: str) -> str:
    for ext in ("md","txt","json"):
        p = SOP_DIR / f"{sop_id}.{ext}"
        if p.exists():
            try:
                return p.read_text(encoding="utf-8", errors="ignore").strip()
            except Exception:
                pass
    return ""

def _build_prompt(body: Dict[str, Any], sop_id: str, user_text: str) -> str:
    parts = []
    task = _read_task_doc()
    if task:
        parts.append("## TASK INSTRUCTIONS\n" + task)
    sop_text = _load_sop_text(sop_id)
    if sop_text:
        parts.append(f"## SOP ({sop_id})\n" + sop_text)
    if ALERT_JSON_PRETTY and isinstance(body.get("alert"), dict):
        parts.append("## ALERT JSON\n" + json.dumps(body["alert"], ensure_ascii=False, indent=2))
    parts.append("## USER\n" + user_text)
    return "\n\n".join(parts).strip()

def _resolve_sop_id(body: Dict[str, Any]) -> str:
    if "sop_id" in body and body["sop_id"]:
        return str(body["sop_id"]).strip()
    if "incident_key" in body and body["incident_key"]:
        return sop_id_from_incident_key(str(body["incident_key"]))
    if "alert" in body and isinstance(body["alert"], dict):
        ik = build_incident_key_from_alert(body["alert"])
        return sop_id_from_incident_key(ik)
    return "default"

def _run_q_direct(sop_id: str, prompt: str) -> Dict[str, Any]:
    """直接使用subprocess运行Q CLI"""
    workdir = SESSION_ROOT / sop_id
    workdir.mkdir(parents=True, exist_ok=True)
    
    try:
        proc = subprocess.run(
            ["q", "chat", "--no-interactive", "--trust-all-tools", "--resume", "--", prompt],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=Q_TIMEOUT
        )
        
        output = (proc.stdout or "").strip()
        error = (proc.stderr or "").strip()
        
        return {
            "ok": proc.returncode == 0,
            "output": output,
            "error": error,
            "code": proc.returncode
        }
        
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "output": "",
            "error": f"timeout after {Q_TIMEOUT}s",
            "code": -1
        }
    except Exception as e:
        return {
            "ok": False,
            "output": "",
            "error": str(e),
            "code": -1
        }

@app.get("/healthz")
def healthz():
    return {"ok": True, "service": APP_NAME}

@app.post("/ask_json")
async def ask_json(request: Request):
    """简化版本的分析接口"""
    try:
        body = await request.json()
    except Exception as e:
        print(f"JSON解析错误: {e}")
        raise HTTPException(400, f"expect JSON body: {e}")
    
    user_text = (body.get("text") or "").strip()
    if not user_text:
        raise HTTPException(400, "text required")

    sop_id = _resolve_sop_id(body)
    print(f"开始处理请求: sop_id={sop_id}, text={user_text[:50]}...")
    
    try:
        # 构建提示
        prompt = _build_prompt(body, sop_id, user_text)
        print(f"提示构建完成，长度: {len(prompt)}")
        
        # 执行分析
        t0 = time.time()
        result = _run_q_direct(sop_id, prompt)
        took_ms = int((time.time() - t0) * 1000)
        
        print(f"Q CLI执行完成: ok={result['ok']}, took={took_ms}ms")
        
        # 构建响应
        out = {
            "ok": result["ok"],
            "sop_id": sop_id,
            "took_ms": took_ms,
            "output": result["output"],
            "error": result["error"],
            "loaded": False,  # 简化版本不支持加载
            "saved": False,   # 简化版本不支持保存
            "events": []      # 简化版本不支持事件
        }
        
        code = 200 if out["ok"] else 504
        return JSONResponse(out, status_code=code)
        
    except Exception as e:
        print(f"处理异常: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Internal error: {e}")
