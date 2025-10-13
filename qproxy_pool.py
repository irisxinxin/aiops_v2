# qproxy_longpool_final.py
# -*- coding: utf-8 -*-
"""
Q Proxy (Python) — Long‑lived WebSocket pool using aleck31/terminal-api-for-qcli

Highlights
- Uses TerminalAPIClient from the Git repo to establish and keep N long-lived WS connections.
- HTTP POST /call borrows one connection, interacts with Q, and then returns it to the pool.
- Before ask: if conversations/<sop_id>.qconv exists, run `/load <file>`.
- After ask: if output looks valid JSON (with required keys), run `/compact` then `/save <file>`.
- Prompt always includes task_instructions.md and a SOP (resolved by sop_id derived from alert).
- For SOP: first check files in SOP_DIR/<sop_id>.{md,txt,json>, else scan a jsonl (e.g. sdn5_sop_full.jsonl).
- A convenience /test endpoint (and RUN_TEST_ON_START=1) uses /mnt/data/sdn5_cpu.json to exercise /call.

Pre-req:
    pip install fastapi uvicorn "git+https://github.com/aleck31/terminal-api-for-qcli@master"
Ensure QCLI via ttyd is running, e.g.:
    ttyd --ping-interval 25 -p 7682 q

Run:
    python qproxy_longpool_final.py
"""

import os
import logging
import re
import json
import hashlib
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# --- External library from the Git repo ---
import sys
sys.path.insert(0, './terminal-api-for-qcli')
from api import TerminalAPIClient
from api.data_structures import TerminalType


# =========================
# Config (env-overridable)
# =========================
Q_HOST = os.getenv("Q_HOST", "127.0.0.1")
Q_PORT = int(os.getenv("Q_PORT", "7682"))
Q_USER = os.getenv("Q_USER", "demo")
Q_PASS = os.getenv("Q_PASS", "password123")

POOL_SIZE = int(os.getenv("POOL_SIZE", "2"))
READY_NEED = int(os.getenv("READY_NEED", "1"))

CONV_DIR = Path(os.getenv("CONV_DIR", "./conversations")).resolve()
SOP_DIR = Path(os.getenv("SOP_DIR", "./sop")).resolve()

SOP_JSONL_DIR = Path(os.getenv("SOP_JSONL_DIR", "./sop")).resolve()
SOP_JSONL_FILE = os.getenv("SOP_JSONL_FILE", "sdn5_sop_full.jsonl")

TASK_INSTR_PATH = Path(os.getenv("TASK_INSTR_PATH", "./task_instructions.md")).resolve()
TASK_DOC_BUDGET = int(os.getenv("QPROXY_TASK_DOC_BUDGET", "2048"))
ALERT_JSON_PRETTY = os.getenv("QPROXY_ALERT_JSON_PRETTY", "0") == "1"

REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "300"))  # seconds
HTTP_HOST = os.getenv("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("HTTP_PORT", "8080"))
WARMUP_DELAY_MS = int(os.getenv("WARMUP_DELAY_MS", "500"))  # sequential warmup delay between connections
WARMUP_PAUSE_SEC = int(os.getenv("WARMUP_PAUSE_SEC", "30"))  # pause before first /help to wait MCP loading
Q_LAZY = os.getenv("Q_LAZY", "0") in ("1", "true", "TRUE", "True")
ACQUIRE_TIMEOUT = float(os.getenv("ACQUIRE_TIMEOUT", "60"))  # seconds to wait for a ready client
Q_WAKE = os.getenv("Q_WAKE", "newline").lower()  # newline | crlf | ctrlc | ctrlc+newline | none

# Logging config
LOG_LEVEL = os.getenv("QPROXY_LOG_LEVEL", "INFO").upper()
LOG_PAYLOAD = os.getenv("QPROXY_LOG_PAYLOAD", "0") == "1"
LOG_PAYLOAD_LIMIT = int(os.getenv("QPROXY_LOG_PAYLOAD_LIMIT", "2048"))
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("qproxy")


# =========================
# Helpers: cleaning & validity checks
# =========================
CSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
OSC = re.compile(r'\x1b\][^\a]*\x07')
CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')  # keep \t \n \r
TUI_PREFIX = re.compile(r'(?m)^(>|!>|\s*\x1b\[0m)+\s*')
SPINNER = re.compile(r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]\s*Thinking\.\.\.')

REQUIRED_TOP_LEVEL_KEYS = {
    "tool_calls", "root_cause", "evidence", "confidence", "suggested_actions", "analysis_summary"
}

def clean_text(s: str) -> str:
    s = CSI.sub("", s)
    s = OSC.sub("", s)
    s = CTRL.sub("", s)
    s = SPINNER.sub("", s)
    s = TUI_PREFIX.sub("", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    while "\n\n\n" in s:
        s = s.replace("\n\n\n", "\n\n")
    return s.strip()

def strip_code_fences(s: str) -> str:
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.I | re.M)

def try_extract_json_payload(s: str) -> Optional[Dict[str, Any]]:
    """Extract a JSON object from text that may contain ANSI, fences or headers."""
    s = strip_code_fences(clean_text(s))
    # Try the largest {...} block
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = s[start:end+1]
        try:
            return json.loads(candidate)
        except Exception:
            pass
    try:
        return json.loads(s)
    except Exception:
        return None

def is_valid_json_result(s: str) -> bool:
    obj = try_extract_json_payload(s)
    if not isinstance(obj, dict):
        return False
    missing = REQUIRED_TOP_LEVEL_KEYS - set(obj.keys())
    return len(missing) == 0


# =========================
# SOP parsing & matching
# =========================
class SopLine(BaseModel):
    sop_id: Optional[str] = None
    incident_key: Optional[str] = None
    keys: Optional[List[str]] = None
    priority: Optional[str] = None  # HIGH/MIDDLE/LOW
    # Accept both capitalized and lower-case field names
    Command: Optional[List[str]] = None
    Metric: Optional[List[str]] = None
    Log: Optional[List[str]] = None
    Parameter: Optional[List[str]] = None
    FixAction: Optional[List[str]] = None
    command: Optional[List[str]] = None
    metric: Optional[List[str]] = None
    log: Optional[List[str]] = None
    parameter: Optional[List[str]] = None
    fix_action: Optional[List[str]] = None

def _load_jsonl_candidates() -> List[SopLine]:
    paths: List[Path] = []
    fixed = SOP_JSONL_DIR / SOP_JSONL_FILE
    if fixed.exists():
        paths = [fixed]
    else:
        paths = list(SOP_JSONL_DIR.glob("*.jsonl"))
    out: List[SopLine] = []
    for p in paths:
        try:
            with p.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        obj = json.loads(line)
                        out.append(SopLine(**obj))
                    except Exception:
                        continue
        except Exception:
            continue
    return out

def _priority_weight(s: Optional[str]) -> int:
    s = (s or "").strip().upper()
    if s == "HIGH":
        return 3
    if s in ("MID", "MIDDLE", "MEDIUM"):
        return 2
    if s == "LOW":
        return 1
    return 0

def _wildcard_match(patt: str, val: str) -> bool:
    patt = patt.strip().lower()
    val = val.strip().lower()
    if patt == "*":
        return True
    if "*" not in patt:
        return patt == val
    import re as _re
    re_str = "^" + _re.escape(patt).replace("\\*", ".*") + "$"
    return _re.compile(re_str).match(val) is not None

def _key_matches(keys: List[str], a: Dict[str, Any]) -> bool:
    if not keys:
        return False
    matches = 0
    for k in keys:
        k = (k or "").strip().lower()
        if ":" not in k:
            continue
        field, patt = k.split(":", 1)
        v = ""
        if field in ("svc", "service"):
            v = str(_dig(a, "service") or "")
        elif field in ("cat", "category"):
            v = str(_dig(a, "category") or "")
        elif field in ("sev", "severity"):
            v = str(_dig(a, "severity") or "")
        elif field == "region":
            v = str(_dig(a, "region") or "")
        else:
            return False
        if _wildcard_match(patt, v):
            matches += 1
        else:
            return False
    return matches > 0

def _pick_items(line: SopLine, name_cap: str, name_low: str, limit: int) -> str:
    items = getattr(line, name_cap) or getattr(line, name_low) or []
    out: List[str] = []
    for i, v in enumerate(items):
        if isinstance(v, str) and v.strip():
            out.append(f"- {name_cap}: {v.strip()}")
        if limit and (i + 1) >= limit:
            break
    return "\n".join(out)

def build_sop_context_from_files(sop_id: str) -> str:
    """Prefer SOP_DIR files if present: <sop_id>.md/txt/json."""
    if not sop_id:
        return ""
    for ext in (".md", ".txt", ".json"):
        p = SOP_DIR / f"{sop_id}{ext}"
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except Exception:
                continue
    return ""

def build_sop_context_from_jsonl(alert: Dict[str, Any], sop_id: str, incident_key: str) -> str:
    lines = _load_jsonl_candidates()
    best: Optional[SopLine] = None
    for ln in lines:
        if (ln.sop_id or "").strip() == sop_id:
            best = ln
            break
    if best is None:
        for ln in lines:
            if (ln.incident_key or "").strip() == incident_key:
                best = ln
                break
    if best is None:
        candidates: List[SopLine] = []
        for ln in lines:
            if ln.keys and _key_matches(ln.keys, alert):
                candidates.append(ln)
        if candidates:
            candidates.sort(key=lambda x: _priority_weight(x.priority), reverse=True)
            best = candidates[0]
    if best is None:
        return ""
    parts = [f"### [SOP] Preloaded knowledge (high priority)\nMatched SOP ID: {sop_id}\n"]
    parts.append(_pick_items(best, "Command", "command", 5))
    parts.append(_pick_items(best, "Metric", "metric", 5))
    parts.append(_pick_items(best, "Log", "log", 3))
    parts.append(_pick_items(best, "Parameter", "parameter", 3))
    parts.append(_pick_items(best, "FixAction", "fix_action", 3))
    return "\n".join([p for p in parts if p]).strip()


# =========================
# Incident key & sop_id (ported from Go)
# =========================
def _dig(d: Dict[str, Any], path: str) -> Any:
    cur: Any = d
    for key in path.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur

def _normalize(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")

def _first_non_empty(*vals: Optional[str]) -> str:
    for v in vals:
        if v and str(v).strip():
            return str(v).strip()
    return ""

def build_incident_key(alert: Dict[str, Any]) -> str:
    """service_category_severity_region[_alertname][_groupid]"""
    service = _first_non_empty(
        str(alert.get("service", "")),
        str(_dig(alert, "inputs.service") or ""),
        str(_dig(alert, "data.service") or ""),
    )
    category = _first_non_empty(
        str(alert.get("category", "")),
        str(_dig(alert, "inputs.category") or ""),
        str(_dig(alert, "data.category") or ""),
    )
    severity = _first_non_empty(
        str(alert.get("severity", "")),
        str(_dig(alert, "inputs.severity") or ""),
        str(_dig(alert, "data.severity") or ""),
    )
    region = _first_non_empty(
        str(alert.get("region", "")),
        str(_dig(alert, "inputs.region") or ""),
        str(_dig(alert, "data.region") or ""),
    )
    group_id = _first_non_empty(
        str(alert.get("group_id", "")),
        str(_dig(alert, "metadata.group_id") or ""),
        str(_dig(alert, "groupId") or ""),
    )
    alert_name = _first_non_empty(
        str(_dig(alert, "metadata.alert_name") or ""),
        str(_dig(alert, "metadata.alertname") or ""),
        str(alert.get("alert_name", "")),
        str(alert.get("alertname", "")),
    )

    service = _normalize(service)
    category = _normalize(category)
    severity = _normalize(severity)
    region = _normalize(region)
    alert_name = _normalize(alert_name)
    group_id = _normalize(group_id)

    parts = [service, category, severity, region]
    if alert_name:
        parts.append(alert_name)
    if group_id:
        parts.append(group_id)

    return "_".join([p for p in parts if p])


# =========================
# Q client wrapper (uses repo's TerminalAPIClient, kept open)
# =========================
class QClient:
    def __init__(self, idx: int):
        self.idx = idx
        self._ctx = TerminalAPIClient(
            host=Q_HOST, port=Q_PORT, terminal_type=TerminalType.QCLI,
            username=Q_USER, password=Q_PASS
        )
        self.client: Optional[TerminalAPIClient] = None
        self.lock = asyncio.Lock()
        self.ready = False

    async def connect(self):
        self.client = await self._ctx.__aenter__()
        # Warmup: wait for MCP/plugins to load, then run /help to ensure ready
        try:
            if WARMUP_PAUSE_SEC > 0:
                log.info("client.connect: pause %ds before /help warmup", WARMUP_PAUSE_SEC)
                await asyncio.sleep(WARMUP_PAUSE_SEC)
            # Wake up TUI/spinner if needed
            try:
                if Q_WAKE in ("ctrlc", "ctrlc+newline"):
                    log.info("client.connect: send wake CTRL-C")
                    await asyncio.wait_for(self.exec_collect("\x03"), timeout=5)
                if Q_WAKE in ("newline", "ctrlc+newline"):
                    log.info("client.connect: send wake newline\\n")
                    await asyncio.wait_for(self.exec_collect("\n"), timeout=5)
                if Q_WAKE == "crlf":
                    log.info("client.connect: send wake CRLF\\r\\n")
                    await asyncio.wait_for(self.exec_collect("\r\n"), timeout=5)
            except Exception:
                log.debug("client.connect: wake sequence ignored (no effect)")
            help_out = await asyncio.wait_for(self.exec_collect("/help"), timeout=30)
            log.info("client.connect: ran /help for warmup")
            if LOG_PAYLOAD and help_out:
                preview = help_out[:LOG_PAYLOAD_LIMIT]
                log.debug("client.connect: /help preview (len=%d)\n%s", len(help_out), preview)
            self.ready = True
        except Exception:
            self.ready = False

    async def close(self):
        try:
            await self._ctx.__aexit__(None, None, None)
        finally:
            self.client = None
            self.ready = False

    async def exec_collect(self, cmd: str) -> str:
        assert self.client is not None
        out: List[str] = []
        async for chunk in self.client.execute_command_stream(cmd):
            if isinstance(chunk, dict):
                t = chunk.get("type")
                if t == "content":
                    out.append(chunk.get("content", ""))
                elif t == "complete":
                    break
            else:
                out.append(str(chunk))
        return "".join(out)

    async def load_if_exists(self, sop_id: str):
        if not sop_id:
            return
        CONV_DIR.mkdir(parents=True, exist_ok=True)
        p = CONV_DIR / f"{sop_id}.qconv"
        if p.exists():
            await self.exec_collect(f"/load {str(p.resolve())}")

    async def compact_and_save(self, sop_id: str):
        if not sop_id:
            return
        CONV_DIR.mkdir(parents=True, exist_ok=True)
        p = CONV_DIR / f"{sop_id}.qconv"
        await self.exec_collect("/compact")
        await self.exec_collect(f"/save {str(p.resolve())}")

    async def healthy(self) -> bool:
        """Lightweight health check: try a noop command that should be safe."""
        try:
            _ = await self.exec_collect("/help")
            return True
        except Exception:
            return False


# =========================
# Connection pool (N long-lived clients)
# =========================
class QPool:
    def __init__(self, size: int):
        self.size = size
        self.clients: List[QClient] = [QClient(i) for i in range(size)]
        self.available: "asyncio.Queue[int]" = asyncio.Queue()
        self._ready = asyncio.Event()

    async def start(self):
        # Sequential warmup to avoid CPU spikes from concurrent Q/MCP loading
        if Q_LAZY:
            log.info("pool.start: LAZY mode enabled, skip pre-connect; will connect on first acquire")
            if READY_NEED == 0 and not self._ready.is_set():
                self._ready.set()
            return
        for i, cli in enumerate(self.clients):
            try:
                log.info("pool.start: connecting client idx=%d host=%s port=%d", i, Q_HOST, Q_PORT)
                await cli.connect()
                if cli.ready:
                    await self.available.put(i)
                    log.info("pool.start: client idx=%d ready and enqueued", i)
                else:
                    log.warning("pool.start: client idx=%d not ready after warmup, skipping enqueue", i)
            except Exception as e:
                # Keep going; remaining connections may still succeed
                log.error("pool.start: client idx=%d connect failed: %s", i, e)
            # Mark ready as soon as threshold met
            ready_now = sum(1 for c in self.clients if c.ready)
            if ready_now >= READY_NEED:
                if not self._ready.is_set():
                    log.info("pool.start: ready threshold met (ready=%d / size=%d)", ready_now, self.size)
                self._ready.set()
            # Small delay between spawns to smooth CPU usage
            if WARMUP_DELAY_MS > 0 and i + 1 < self.size:
                await asyncio.sleep(WARMUP_DELAY_MS / 1000.0)

    async def stop(self):
        await asyncio.gather(*[c.close() for c in self.clients], return_exceptions=True)

    def stats(self) -> Tuple[int, int, int]:
        return sum(1 for c in self.clients if c.ready), self.size, self.available.qsize()

    @asynccontextmanager
    async def acquire(self):
        # In lazy mode or when queue is empty, try to establish one on-demand
        if self.available.qsize() == 0:
            for idx, cli in enumerate(self.clients):
                if not cli.ready:
                    log.info("pool.acquire: on-demand connect idx=%d", idx)
                    try:
                        await cli.connect()
                        if cli.ready:
                            await self.available.put(idx)
                            log.info("pool.acquire: on-demand ready idx=%d", idx)
                            break
                    except Exception:
                        log.exception("pool.acquire: on-demand connect failed idx=%d", idx)
        # Wait with timeout so /call 不会无限挂起
        log.debug("pool.acquire: waiting for available client (timeout=%ss) ...", int(ACQUIRE_TIMEOUT))
        try:
            idx = await asyncio.wait_for(self.available.get(), timeout=ACQUIRE_TIMEOUT)
        except asyncio.TimeoutError as e:
            log.warning("pool.acquire: timeout waiting for ready client")
            raise
        cli = self.clients[idx]
        try:
            log.debug("pool.acquire: got idx=%d, acquiring lock ...", idx)
            await cli.lock.acquire()
            try:
                log.debug("pool.acquire: lock acquired idx=%d", idx)
                yield cli
            finally:
                cli.lock.release()
                log.debug("pool.acquire: lock released idx=%d", idx)
        except Exception:
            # If something bad happened before yielding, mark unhealthy & try to reconnect
            cli.ready = False
            try:
                await cli.close()
            except Exception:
                log.exception("pool.acquire: close failed idx=%d", idx)
            try:
                await cli.connect()
            except Exception:
                log.exception("pool.acquire: reconnect failed idx=%d", idx)
        finally:
            # Return index to the pool regardless; caller will retry on error response
            await self.available.put(idx)
            log.debug("pool.acquire: idx=%d returned to queue", idx)

    async def wait_ready(self, timeout: float = 30.0):
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass


# =========================
# Prompt builder
# =========================
def _read_task_doc(budget: int = TASK_DOC_BUDGET) -> str:
    if not TASK_INSTR_PATH.exists():
        return ""
    b = TASK_INSTR_PATH.read_bytes()
    if budget and len(b) > budget:
        b = b[:budget] + b"\n..."
    return b.decode("utf-8", "ignore").strip()

TASK_DOC = ""

def build_prompt_and_ids(alert: Dict[str, Any], extra_user_prompt: Optional[str]) -> Tuple[str, str]:
    incident_key = build_incident_key(alert)
    sop_id = "sop_" + hashlib.sha1(incident_key.encode("utf-8")).hexdigest()[:12]

    # SOP priority: SOP_DIR file > JSONL match
    sop_text = build_sop_context_from_files(sop_id)
    if not sop_text:
        sop_text = build_sop_context_from_jsonl(alert, sop_id, incident_key)

    parts: List[str] = []
    # You can add a brief system priming line here if needed
    if TASK_DOC:
        parts.append("## TASK INSTRUCTIONS (verbatim)\n" + TASK_DOC)

    if ALERT_JSON_PRETTY:
        alert_json = json.dumps(alert, ensure_ascii=False, indent=2)
    else:
        alert_json = json.dumps(alert, ensure_ascii=False, separators=(",", ":"))
    parts.append("## ALERT JSON (complete)\n" + alert_json)

    if sop_text:
        parts.append(sop_text)

    if extra_user_prompt:
        parts.append("## USER QUERY\n" + extra_user_prompt)

    return "\n\n".join([p for p in parts if p.strip()]), sop_id


# =========================
# FastAPI app
# =========================
app = FastAPI(title="Q Proxy (Python) — Long‑lived WS Pool")
pool = QPool(POOL_SIZE)

class CallReq(BaseModel):
    alert: Dict[str, Any]        # required
    prompt: Optional[str] = None # optional extra prompt

class CallResp(BaseModel):
    ok: bool
    answer: Optional[str] = None
    sop_id: Optional[str] = None
    error: Optional[str] = None

@app.on_event("startup")
async def _startup():
    global TASK_DOC
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    SOP_DIR.mkdir(parents=True, exist_ok=True)
    TASK_DOC = _read_task_doc(TASK_DOC_BUDGET)
    asyncio.create_task(pool.start())
    try:
        log.info("startup: waiting pool ready (timeout=30s) ...")
        await pool.wait_ready(30.0)  # 增加超时时间到30秒
        ready, size, avail = pool.stats()
        log.info("startup: pool ready=%d size=%d avail=%d", ready, size, avail)
    except asyncio.TimeoutError:
        log.warning("startup: pool initialization timeout, continue anyway")
    except Exception as e:
        log.exception("startup: pool initialization error, continue anyway")

@app.get("/healthz")
async def healthz():
    ready, size, avail = pool.stats()
    return {"ready": ready, "size": size, "available": avail}

@app.get("/readyz")
async def readyz():
    ready, _, _ = pool.stats()
    return "ok" if ready >= READY_NEED else "warming"

@app.post("/call", response_model=CallResp)
async def call(req: CallReq):
    # Build prompt (task instructions + alert JSON + SOP; always included)
    try:
        prompt, sop_id = build_prompt_and_ids(req.alert, req.prompt)
        log.info("call: built prompt (sop_id=%s, alert_keys=%s, prompt_len=%d)",
                 sop_id, list(req.alert.keys())[:6], len(prompt))
        if LOG_PAYLOAD:
            prev = prompt[:LOG_PAYLOAD_LIMIT]
            log.info("PROMPT (truncated=%d):\n%s", LOG_PAYLOAD_LIMIT, prev)
    except Exception as e:
        log.exception("call: build prompt failed")
        raise HTTPException(status_code=400, detail=f"build prompt failed: {e}")

    try:
        async with pool.acquire() as cli:
            if sop_id:
                log.debug("call: loading conversation if exists (sop_id=%s)", sop_id)
                await cli.load_if_exists(sop_id)

            log.info("call: executing prompt (timeout=%ss)", int(REQUEST_TIMEOUT))
            out = await asyncio.wait_for(cli.exec_collect(prompt), timeout=REQUEST_TIMEOUT)
            cleaned = clean_text(out)
            log.info("call: got response (len_raw=%d, len_cleaned=%d)", len(out), len(cleaned))
            if LOG_PAYLOAD and cleaned:
                rs = cleaned[:LOG_PAYLOAD_LIMIT]
                log.info("RESPONSE (truncated=%d):\n%s", LOG_PAYLOAD_LIMIT, rs)
            if is_valid_json_result(cleaned) and sop_id:
                log.info("call: valid JSON result detected; compact+save (sop_id=%s)", sop_id)
                await cli.compact_and_save(sop_id)

            return CallResp(ok=True, answer=cleaned, sop_id=sop_id)

    except asyncio.TimeoutError:
        log.warning("call: request timeout after %ss", int(REQUEST_TIMEOUT))
        raise HTTPException(status_code=504, detail="request timeout")
    except Exception as e:
        log.exception("call: exception during execution")
        return CallResp(ok=False, error=str(e), sop_id=sop_id)


# =========================
# Optional: local test using /mnt/data/sdn5_cpu.json
# =========================
@app.get("/test")
async def test_once():
    sample = Path("/mnt/data/sdn5_cpu.json")
    if not sample.exists():
        raise HTTPException(404, detail="sample not found: /mnt/data/sdn5_cpu.json")
    try:
        alert = json.loads(sample.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(400, detail=f"invalid sample json: {e}")
    resp = await call(CallReq(alert=alert))
    return resp


def main():
    import uvicorn
    uvicorn.run("qproxy_pool:app", host=HTTP_HOST, port=HTTP_PORT, log_level="info")

if __name__ == "__main__":
    if os.getenv("RUN_TEST_ON_START", "0") == "1":
        async def _run():
            await _startup()
            # Call /test logic inline
            try:
                sample = Path("/mnt/data/sdn5_cpu.json")
                alert = json.loads(sample.read_text(encoding="utf-8"))
                r = await call(CallReq(alert=alert))
                print("[TEST] ok:", r.ok)
                print("[TEST] sop_id:", r.sop_id)
                if r.answer:
                    print("[TEST] answer preview:", r.answer[:600], "...")
            except Exception as e:
                print("[TEST] failed:", e)
        asyncio.run(_run())
    else:
        main()
