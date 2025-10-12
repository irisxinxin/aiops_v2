# qproxy_pool.py
# -*- coding: utf-8 -*-
"""
Q Proxy (Python) with a warmed WebSocket connection pool to Amazon Q CLI via ttyd.

- Uses TerminalAPIClient from aleck31/terminal-api-for-qcli (the Git repo you referenced)
- Pre-warms a pool of long-lived WS connections (reduces MCP-loading latency)
- HTTP POST /call will borrow a hot connection and interact with Q
- Before each interaction:
    * If conversations/<sop_id>.qconv exists -> send `/load <file>`
- After each interaction:
    * If the output looks valid -> send `/compact` then `/save <file>`
- Prompt building:
    * Always include task_instructions.md
    * Insert the matched SOP (by sop_id derived from alert) from sdn5_sop_full.jsonl (or SOP_DIR/ files)
    * Include the full input alert JSON
- A local test helper will read ./sdn5_cpu.json and POST it to /call

Run:
    pip install fastapi uvicorn "git+https://github.com/aleck31/terminal-api-for-qcli@master"
    # Ensure ttyd+Q is up, e.g.: ttyd --ping-interval 25 -p 7682 q
    python qproxy_pool.py
"""

import os
import re
import json
import hashlib
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# --- External library from your Git repo ---
# pip install "git+https://github.com/aleck31/terminal-api-for-qcli@master"
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


# =========================
# Helpers: cleaning & validity checks
# =========================
CSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
OSC = re.compile(r'\x1b\][^\a]*\x07')
CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')  # keep \t \n \r
TUI_PREFIX = re.compile(r'(?m)^(>|!>|\s*\x1b\[0m)+\s*')
SPINNER = re.compile(r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]\s*Thinking\.\.\.')

REQUIRED_TOP_LEVEL_KEYS = {"tool_calls", "root_cause", "evidence", "confidence", "suggested_actions", "analysis_summary"}

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

def try_extract_json_payload(s: str) -> Optional[Dict[str, Any]]:
    """Try to extract a JSON object from a string that may contain extra text/code fences."""
    s = clean_text(s)
    # strip code fences
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.I | re.M)
    # find first {...} block
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = s[start:end+1]
        try:
            return json.loads(candidate)
        except Exception:
            pass
    # last resort: whole string
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
    # convert * -> regex
    import re as _re
    re_str = "^" + _re.escape(patt).replace("\\*", ".*") + "$"
    return _re.compile(re_str).match(val) is not None

def _key_matches(keys: List[str], a: Dict[str, Any]) -> bool:
    """keys like: svc:omada cat:cpu sev:critical region:aps1 (supports * wildcard)"""
    if not keys:
        return False
    matches = 0
    for k in keys:
        k = (k or "").strip().lower()
        if ":" not in k:
            continue
        field, patt = k.split(":", 1)
        # map fields out of alert
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
            # unsupported field -> skip entire rule
            return False
        if _wildcard_match(patt, v):
            matches += 1
        else:
            return False
    return matches > 0

def _join_section(title: str, items: Optional[List[str]], limit: int) -> str:
    items = items or []
    out: List[str] = []
    for i, v in enumerate(items):
        if isinstance(v, str) and v.strip():
            out.append(f"- {title}: {v.strip()}")
        if limit and (i + 1) >= limit:
            break
    return "\n".join(out)

def build_sop_context_with_id(alert: Dict[str, Any], sop_dir: Path) -> Tuple[str, str]:
    """
    Implements the Go logic:
      - Compute incident_key (normalized composite)
      - sop_id = 'sop_' + sha1(incident_key)[:12]
      - Load SOP jsonl; first prefer exact sop_id; fallback to incident_key; then keys-matching
      - Return pretty SOP text + final sop_id
    """
    if not str(sop_dir).strip():
        return "", ""

    incident_key = build_incident_key(alert)
    sop_id = "sop_" + hashlib.sha1(incident_key.encode("utf-8")).hexdigest()[:12]

    # 1) Try from loose files in SOP_DIR (sop_id.md/txt/json)
    for ext in (".md", ".txt", ".json"):
        fp = sop_dir / f"{sop_id}{ext}"
        if fp.exists():
            try:
                return fp.read_text(encoding="utf-8"), sop_id
            except Exception:
                pass

    # 2) Scan jsonl for matches
    lines = _load_jsonl_candidates()
    best: Optional[SopLine] = None
    # a) exact sop_id
    for ln in lines:
        if (ln.sop_id or "").strip() == sop_id:
            best = ln
            break
    # b) same incident_key
    if best is None:
        for ln in lines:
            if (ln.incident_key or "").strip() == incident_key:
                best = ln
                break
    # c) key-matching with priority ranking
    if best is None:
        candidates: List[SopLine] = []
        for ln in lines:
            if ln.keys and _key_matches(ln.keys, alert):
                candidates.append(ln)
        if candidates:
            candidates.sort(key=lambda x: _priority_weight(x.priority), reverse=True)
            best = candidates[0]

    if best is None:
        return "", sop_id

    parts: List[str] = [f"### [SOP] Preloaded knowledge (high priority)\nMatched SOP ID: {sop_id}\n"]
    parts.append(_join_section("Command", best.command, 5))
    parts.append(_join_section("Metric", best.metric, 5))
    parts.append(_join_section("Log", best.log, 3))
    parts.append(_join_section("Parameter", best.parameter, 3))
    parts.append(_join_section("FixAction", best.fix_action, 3))

    return "\n".join([p for p in parts if p]).strip(), sop_id


# =========================
# Incident key & sop_id (ported from Go)
# =========================
def _dig(d: Dict[str, Any], path: str) -> Any:
    """Simple dot-path dig (e.g. 'inputs.prompt' or 'metadata.alert_name')"""
    cur: Any = d
    for key in path.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur

def _normalize(s: str) -> str:
    s = (s or "").strip().lower()
    # replace spaces & non-alnum with underscore; collapse repeats
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s)
    s = s.strip("_")
    return s

def _first_non_empty(*vals: Optional[str]) -> str:
    for v in vals:
        if v and str(v).strip():
            return str(v).strip()
    return ""

def build_incident_key(alert: Dict[str, Any]) -> str:
    """Format: service_category_severity_region[_alertname][_groupid] with normalization."""
    # Extract candidate fields with fallbacks across common nests
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
# Q client wrapper
# =========================
class QClient:
    def __init__(self, idx: int):
        self.idx = idx
        self._cm = TerminalAPIClient(
            host=Q_HOST, port=Q_PORT, terminal_type=TerminalType.QCLI,
            username=Q_USER, password=Q_PASS
        )
        self.client = None
        self.lock = asyncio.Lock()
        self.ready = False

    async def connect(self):
        self.client = await self._cm.__aenter__()
        self.ready = True

    async def close(self):
        try:
            await self._cm.__aexit__(None, None, None)
        finally:
            self.client = None
            self.ready = False

    async def _exec_collect(self, cmd: str) -> str:
        assert self.client is not None
        chunks: List[str] = []
        async for piece in self.client.execute_command_stream(cmd):
            if isinstance(piece, dict):
                t = piece.get("type")
                if t == "content":
                    chunks.append(piece.get("content", ""))
                elif t == "complete":
                    break
            else:
                chunks.append(str(piece))
        return "".join(chunks)

    async def warmup(self):
        try:
            await self._exec_collect("/help")
        except Exception:
            pass

    async def load_conversation_if_exists(self, sop_id: str):
        if not sop_id:
            return
        CONV_DIR.mkdir(parents=True, exist_ok=True)
        conv_path = CONV_DIR / f"{sop_id}.qconv"
        if conv_path.exists():
            await self._exec_collect(f"/load {str(conv_path.resolve())}")

    async def compact_and_save(self, sop_id: str):
        if not sop_id:
            return
        CONV_DIR.mkdir(parents=True, exist_ok=True)
        conv_path = CONV_DIR / f"{sop_id}.qconv"
        await self._exec_collect("/compact")
        await self._exec_collect(f"/save {str(conv_path.resolve())}")

    async def ask_q(self, prompt: str) -> str:
        return await self._exec_collect(prompt)


# =========================
# Connection pool
# =========================
class QPool:
    def __init__(self, size: int):
        self.size = size
        self.clients: List[QClient] = [QClient(i) for i in range(size)]
        self._ready = asyncio.Event()

    async def start(self):
        async def _start_one(cli: QClient):
            await cli.connect()
            await cli.warmup()

        tasks = [asyncio.create_task(_start_one(c)) for c in self.clients]
        await asyncio.gather(*tasks, return_exceptions=True)
        ready = sum(1 for c in self.clients if c.ready)
        if ready >= READY_NEED:
            self._ready.set()

    async def stop(self):
        await asyncio.gather(*[c.close() for c in self.clients], return_exceptions=True)

    def stats(self) -> Tuple[int, int]:
        return sum(1 for c in self.clients if c.ready), self.size

    @asynccontextmanager
    async def acquire(self):
        # Simple round-robin scan for a free client (with lock to ensure per-conn serial use)
        while True:
            for cli in self.clients:
                if not cli.ready:
                    continue
                if not cli.lock.locked():
                    await cli.lock.acquire()
                    try:
                        yield cli
                    finally:
                        cli.lock.release()
                    return
            await asyncio.sleep(0.01)

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
        b = b[:budget] + "\n...".encode("utf-8")
    return b.decode("utf-8", "ignore").strip()

TASK_DOC = ""

def build_prompt_and_ids(payload: Dict[str, Any]) -> Tuple[str, str, str]:
    """Return (prompt, incident_key, sop_id)."""
    # Prefer request.alert; otherwise assume payload itself is the alert
    alert = payload.get("alert") if isinstance(payload, dict) else None
    if alert is None:
        alert = payload

    if not isinstance(alert, dict):
        raise HTTPException(status_code=400, detail="alert must be a JSON object or set payload.alert")

    incident_key = build_incident_key(alert)
    sop_text, sop_id = build_sop_context_with_id(alert, SOP_DIR)

    parts: List[str] = []
    parts.append("You are an AIOps assistant.")

    if TASK_DOC:
        parts.append("## TASK INSTRUCTIONS (verbatim)\n" + TASK_DOC)

    if ALERT_JSON_PRETTY:
        alert_json = json.dumps(alert, ensure_ascii=False, indent=2)
    else:
        alert_json = json.dumps(alert, ensure_ascii=False, separators=(",", ":"))
    parts.append("## ALERT JSON (complete)\n" + alert_json)

    if sop_text:
        parts.append(sop_text)

    final_prompt = "\n\n".join([p for p in parts if p.strip()])
    return final_prompt, incident_key, sop_id


# =========================
# FastAPI app
# =========================
app = FastAPI(title="Q Proxy (Python) with Warmed WS Pool")
pool = QPool(POOL_SIZE)

class CallReq(BaseModel):
    sop_id: Optional[str] = None  # optional override
    alert: Optional[Dict[str, Any]] = None
    prompt: Optional[str] = None  # if you want to pass a custom user text

class CallResp(BaseModel):
    ok: bool
    answer: Optional[str] = None
    sop_id: Optional[str] = None
    incident_key: Optional[str] = None
    error: Optional[str] = None

@app.on_event("startup")
async def _startup():
    global TASK_DOC
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    SOP_DIR.mkdir(parents=True, exist_ok=True)
    TASK_DOC = _read_task_doc(TASK_DOC_BUDGET)
    # warm the pool
    asyncio.create_task(pool.start())
    await pool.wait_ready(10.0)

@app.get("/healthz")
async def healthz():
    ready, size = pool.stats()
    return {"ready": ready, "size": size}

@app.get("/readyz")
async def readyz():
    ready, _ = pool.stats()
    return "ok" if ready >= READY_NEED else "warming"

@app.post("/call", response_model=CallResp)
async def call(req: CallReq):
    # Build prompt (always include task doc + sop if resolvable)
    try:
        # If req.prompt given, treat it as an extra user query appended after alert/sop
        payload: Dict[str, Any] = {"alert": req.alert or {}}
        prompt, incident_key, sop_id_auto = build_prompt_and_ids(payload)
        sop_id = (req.sop_id or sop_id_auto or "").strip()

        if req.prompt:
            prompt = f"{prompt}\n\n## USER QUERY\n{req.prompt}"

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"build prompt failed: {e}")

    try:
        async with pool.acquire() as cli:
            # 1) load previous conversation if exists
            if sop_id:
                await cli.load_conversation_if_exists(sop_id)

            # 2) ask Q
            out = await asyncio.wait_for(cli.ask_q(prompt), timeout=REQUEST_TIMEOUT)
            cleaned = clean_text(out)

            # 3) if valid -> compact + save
            if is_valid_json_result(cleaned) and sop_id:
                await cli.compact_and_save(sop_id)

            return CallResp(ok=True, answer=cleaned, sop_id=sop_id, incident_key=incident_key)

    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="request timeout")
    except Exception as e:
        return CallResp(ok=False, error=str(e), sop_id=sop_id, incident_key=incident_key)

def main():
    import uvicorn
    uvicorn.run("qproxy_pool:app", host=HTTP_HOST, port=HTTP_PORT, log_level="info")

if __name__ == "__main__":
    main()
