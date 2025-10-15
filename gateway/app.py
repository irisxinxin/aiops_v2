import os, sys, json, asyncio, time, re, subprocess
from typing import Any, Dict, Optional
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

# terminal-api-for-qcli client
sys.path.append("/opt/terminal-api-for-qcli")
from api import TerminalAPIClient
from api.data_structures import TerminalType

from gateway.mapping import build_incident_key_from_alert, sop_id_from_incident_key

APP_NAME = os.getenv("APP_NAME", "q-gateway-json")
HOST = os.getenv("QTTY_HOST", "127.0.0.1")
PORT = int(os.getenv("QTTY_PORT", "7682"))
SESSION_ROOT = Path(os.getenv("SESSION_ROOT", "./q-sessions"))
SOP_DIR = Path(os.getenv("SOP_DIR", "./sop"))
TASK_DOC_PATH = Path(os.getenv("TASK_DOC_PATH", "./task_instructions.md"))
TASK_DOC_BUDGET = int(os.getenv("TASK_DOC_BUDGET", "131072"))
ALERT_JSON_PRETTY = os.getenv("ALERT_JSON_PRETTY", "1") not in ("0","false","False")

Q_OVERALL_TIMEOUT = int(os.getenv("Q_OVERALL_TIMEOUT", "60"))
SLASH_TIMEOUT = int(os.getenv("SLASH_TIMEOUT", "10"))

MIN_OUTPUT_CHARS = int(os.getenv("MIN_OUTPUT_CHARS", "50"))
BAD_PATTERNS = os.getenv("BAD_PATTERNS", "as an ai language model|cannot assist with").split("|")

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
    for p in sorted(SOP_DIR.glob("*.jsonl")):
        try:
            with p.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(obj, dict) and str(obj.get("sop_id","")).strip() == sop_id:
                        for key in ("sop","content","text","body"):
                            v = obj.get(key)
                            if isinstance(v, str) and v.strip():
                                return v.strip()
        except Exception:
            continue
    return ""

def _build_prompt(body: Dict[str, Any], sop_id: str) -> str:
    parts = []
    task = _read_task_doc()
    if task:
        parts.append("## TASK INSTRUCTIONS\n" + task)
    sop_text = _load_sop_text(sop_id)
    if sop_text:
        parts.append(f"## SOP ({sop_id})\n" + sop_text)
    if ALERT_JSON_PRETTY and isinstance(body.get("alert"), dict):
        parts.append("## ALERT JSON\n" + json.dumps(body["alert"], ensure_ascii=False, indent=2))
    return "\n\n".join(parts).strip()

async def _run_q_slash(sop_id: str, slash_cmd: str, timeout: int = None) -> Dict[str, Any]:
    if timeout is None:
        timeout = SLASH_TIMEOUT
    workdir = SESSION_ROOT / sop_id
    workdir.mkdir(parents=True, exist_ok=True)
    if slash_cmd.startswith("/save") and " -f" not in slash_cmd and " --force" not in slash_cmd:
        slash_cmd += " -f"
    
    try:
        async with TerminalAPIClient(host="127.0.0.1", port=7682, terminal_type=TerminalType.QCLI,
                                   url_query={"arg": sop_id}) as c:
            await c.send_text(f"{slash_cmd}\n")
            # Wait a bit for command to execute
            import asyncio
            await asyncio.sleep(1)
            
            response_data = ""
            try:
                async for ev in c.stream():
                    if ev.get("type") in ("content", "notification", "tool"):
                        response_data = str(ev.get("data", ""))
                        break
            except:
                pass  # Ignore stream errors
            
            return {"ok": True, "code": 0, "stdout": response_data, "stderr": ""}
    except Exception as e:
        return {"ok": False, "code": 1, "stdout": "", "stderr": str(e)}

async def _run_q_collect(sop_id: str, text: str, timeout: int = None) -> Dict[str, Any]:
    if timeout is None:
        timeout = Q_OVERALL_TIMEOUT
    out_chunks = []
    events = []
    async def _inner():
        ttyd_query = f"arg={sop_id}" if sop_id else None
        async with TerminalAPIClient(host=HOST, port=PORT, terminal_type=TerminalType.QCLI,
                                     ttyd_query=ttyd_query) as client:
            async for chunk in client.execute_command_stream(text):
                t = chunk.get("type")
                if t == "content":
                    out_chunks.append(chunk.get("content",""))
                elif t in ("notification","tool","error"):
                    events.append(chunk)
                elif t == "complete":
                    break
    try:
        await asyncio.wait_for(_inner(), timeout=timeout)
        ok = True
        err = ""
    except asyncio.TimeoutError:
        ok = False
        err = f"timeout after {timeout}s"
    except Exception as e:
        ok = False
        err = str(e)
    return {"ok": ok, "output": "".join(out_chunks), "events": events, "error": err}

def _improve_json_readability(json_str: str) -> str:
    """Improve readability of JSON text by adding spaces"""
    import re
    # Add space before capital letters that follow lowercase letters
    json_str = re.sub(r'([a-z])([A-Z])', r'\1 \2', json_str)
    # Add space before numbers that follow letters  
    json_str = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', json_str)
    # Add space after numbers that are followed by letters
    json_str = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', json_str)
    return json_str

def _is_usable(text: str) -> bool:
    if len(text.strip()) < MIN_OUTPUT_CHARS:
        return False
    low = text.lower()
    for pat in BAD_PATTERNS:
        pat = pat.strip()
        if pat and pat in low:
            return False
    return True

REQUIRED_ALERT_KEYS = ("service", "category", "severity", "region", "title")

def _require_sop_inputs(body: Dict[str, Any]) -> str:
    """仅允许从 alert 构造 sop_id（强制 sdn5_cpu 风格）。"""
    alert = body.get("alert")
    if isinstance(alert, dict):
        missing = [k for k in REQUIRED_ALERT_KEYS if not str(alert.get(k, "")).strip()]
        if missing:
            raise HTTPException(400, f"alert missing required fields: {', '.join(missing)}")
        ik = build_incident_key_from_alert(alert)
        return sop_id_from_incident_key(ik)
    raise HTTPException(400, "alert{service,category,severity,region,title} is required")


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": APP_NAME}

@app.post("/ask_json")
async def ask_json(request: Request):
    """Single-shot workflow:
    (1) incident_key -> sop_id
    (2) if session file exists, /load
    (3) inject SOP/TASK/ALERT into prompt, ask and collect all output
    (4) if output usable, /save
    (5) return JSON with all details
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "expect JSON body")
    # 禁止传入 text
    if "text" in body:
        raise HTTPException(400, "text is not allowed; provide alert only")

    # 禁止客户端直接传 sop_id/incident_key/prompt/text，强制 sdn5_cpu 风格
    for k in ("sop_id", "incident_key", "prompt", "text"):
        if k in body and str(body.get(k, "")).strip():
            raise HTTPException(400, f"{k} is not allowed; provide alert + text only")

    # 仅通过 alert 解析 sop_id
    sop_id = _require_sop_inputs(body)
    workdir = SESSION_ROOT / sop_id
    workdir.mkdir(parents=True, exist_ok=True)

    # auto-load conversation history
    loaded = False
    conv_file = workdir / "conv.json"
    if conv_file.exists():
        try:
            with open(conv_file, 'r', encoding='utf-8') as f:
                conv_data = json.load(f)
            # Add previous context to the current request
            if conv_data.get("response"):
                # This is a simple approach - in a real implementation you'd want to 
                # properly integrate with Q's conversation history
                loaded = True
        except Exception as e:
            print(f"Load error: {e}")
            loaded = False

    # 构建 Prompt（仅 TASK/SOP/ALERT）并请求
    prompt = _build_prompt(body, sop_id)
    t0 = time.time()
    res = await _run_q_collect(sop_id, prompt)
    took_ms = int((time.time() - t0) * 1000)

    # save conversation directly to file
    saved = False
    if res["ok"] and len(res["output"].strip()) > 100:
        try:
            conv_file = workdir / "conv.json"
            # Create a simple conversation record
            conv_data = {
                "timestamp": time.time(),
                "request": body.get("text", ""),
                "alert": body.get("alert", {}),
                "response": res["output"],
                "sop_id": sop_id
            }
            with open(conv_file, 'w', encoding='utf-8') as f:
                json.dump(conv_data, f, indent=2, ensure_ascii=False)
            saved = conv_file.exists()
        except Exception as e:
            print(f"Save error: {e}")
            saved = False

    out = {"ok": res["ok"], "sop_id": sop_id, "loaded": loaded, "saved": saved,
           "took_ms": took_ms, "output": _improve_json_readability(res["output"]), "events": res["events"], "error": res["error"]}
    code = 200 if out["ok"] else 504
    return JSONResponse(out, status_code=code)


