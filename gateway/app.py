import os, sys, json, asyncio, time, re, subprocess, shutil, signal
from asyncio import Lock
from typing import List, Tuple
from typing import Any, Dict, Optional
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

# terminal-api-for-qcli client
sys.path.append("/opt/terminal-api-for-qcli")
from api import TerminalAPIClient
from api.data_structures import TerminalType
from api.terminal_api_client import TerminalBusinessState

from gateway.mapping import build_incident_key_from_alert, sop_id_from_incident_key

APP_NAME = os.getenv("APP_NAME", "q-gateway-json")
HOST = os.getenv("QTTY_HOST", "127.0.0.1")
PORT = int(os.getenv("QTTY_PORT", "7682"))
# 统一使用仓库下的 q-sessions 目录
SESSION_ROOT = Path(os.getenv("SESSION_ROOT", str(Path(__file__).resolve().parents[1] / "q-sessions")))
SOP_DIR = Path(os.getenv("SOP_DIR", "./sop"))
TASK_DOC_PATH = Path(os.getenv("TASK_DOC_PATH", "./task_instructions.md"))
TASK_DOC_BUDGET = int(os.getenv("TASK_DOC_BUDGET", "131072"))
ALERT_JSON_PRETTY = os.getenv("ALERT_JSON_PRETTY", "1") not in ("0","false","False")

# 总体超时：默认 300s（避免 MCP 首次加载被 30s 误杀）
Q_OVERALL_TIMEOUT = int(os.getenv("Q_OVERALL_TIMEOUT", "300"))
PURGE_ON_TIMEOUT = os.getenv("PURGE_ON_TIMEOUT", "0") not in ("0", "false", "False")
PRE_SLASH_CMD = os.getenv("PRE_SLASH_CMD", "")  # 空为默认：不额外发送，保证“一条调用只发一次”
STREAM_OVERALL_TIMEOUT = int(os.getenv("STREAM_OVERALL_TIMEOUT", "300"))
STREAM_SILENCE_TIMEOUT = int(os.getenv("STREAM_SILENCE_TIMEOUT", "180"))

MIN_OUTPUT_CHARS = int(os.getenv("MIN_OUTPUT_CHARS", "50"))
BAD_PATTERNS = os.getenv("BAD_PATTERNS", "as an ai language model|cannot assist with").split("|")

# 工具软等与离线兜底策略
TOOL_RETRY_WAIT = int(os.getenv("TOOL_RETRY_WAIT", "5"))  # 秒
TOOL_RETRY_COUNT = int(os.getenv("TOOL_RETRY_COUNT", "2"))
OFFLINE_FALLBACK = os.getenv("OFFLINE_FALLBACK", "1") not in ("0", "false", "False")

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
        # 跳过映射记录文件，避免将其当作 SOP 正文命中
        if p.name == "incident_sop_map.jsonl":
            continue
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
                    if isinstance(obj, dict) and str(obj.get("sop_id","")) .strip() == sop_id:
                        # 1) direct text fields
                        for key in ("sop","content","text","body"):
                            v = obj.get(key)
                            if isinstance(v, str) and v.strip():
                                return v.strip()
                        # 2) assemble from structured fields
                        parts2 = []
                        title = obj.get("title") or obj.get("name")
                        if isinstance(title, str) and title.strip():
                            parts2.append(f"# {title.strip()}")
                        if obj.get("priority"):
                            parts2.append(f"Priority: {obj.get('priority')}")
                        if obj.get("keys"):
                            try:
                                parts2.append("Keys: " + ", ".join(map(str, obj.get("keys") or [])))
                            except Exception:
                                pass
                        def _section(h, arr):
                            if isinstance(arr, list) and arr:
                                lines = "\n".join([f"- {str(x)}" for x in arr])
                                parts2.append(f"## {h}\n{lines}")
                        _section("Commands", obj.get("command"))
                        _section("Metrics", obj.get("metric"))
                        _section("Logs", obj.get("log"))
                        _section("Fix Actions", obj.get("fix_action"))
                        if parts2:
                            return "\n\n".join(parts2).strip()
                        # 3) fallback: raw json
                        try:
                            return json.dumps(obj, ensure_ascii=False, indent=2)
                        except Exception:
                            return str(obj)
        except Exception:
            continue
    return ""

from typing import Optional

def _build_prompt(body: Dict[str, Any], sop_id: str, allow_tools: bool = True, boundary_id: Optional[str] = None) -> str:
    parts = []

    task = _read_task_doc()
    if task:
        parts.append("## TASK INSTRUCTIONS\n" + task)

    sop_text = _load_sop_text(sop_id)
    if sop_text:
        parts.append(f"## SOP ({sop_id})\n" + sop_text)

    if not allow_tools:
        parts.append("""## TOOL POLICY
- Do NOT call any tools or MCP servers in this turn.
- Use ONLY SOP and ALERT JSON to produce output.
- If data is missing, fill fields with null/empty; do not ask questions.""")

        parts.append("""## OUTPUT SPEC
Return ONLY one JSON object (no extra prose) with:
incident_key, sop_id, severity, classification, impact, hypothesis,
runbook_steps[], commands[], next_action""")

    if boundary_id:
        parts.append(f"## BOUNDARY\nBOUNDARY_ID: {boundary_id}")

    if ALERT_JSON_PRETTY and isinstance(body.get("alert"), dict):
        parts.append("## ALERT JSON\n" + json.dumps(body["alert"], ensure_ascii=False, indent=2))

    return "\n\n".join(parts).strip()

def _log_prompt(sop_id: str, prompt: str) -> None:
    try:
        proj_dir = Path(__file__).resolve().parents[1]
        log_dir = proj_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"prompts_{sop_id}.log"
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"\n===== {ts} sop_id={sop_id} =====\n")
            f.write(prompt)
            f.write("\n")
    except Exception:
        pass

# 工具未就绪判定（扩展语义覆盖）
_TOOL_FAIL_PAT = re.compile(
    r"(mcp (server|tool)s?.{0,40}(not available|were ?n’t available|weren't available)|"
    r"still loading|not (yet )?ready|initiali[sz]ation failed|"
    r"failed to (call|invoke) tool|no tool called due to init|"
    r"waiting for (mcp|server) init)",
    re.IGNORECASE
)

def _looks_like_tool_unavailable(text: str) -> bool:
    return bool(_TOOL_FAIL_PAT.search(text or ""))

# 进程/会话目录辅助
def _pids_q_using_dir(dir_path: Path) -> list[int]:
    """找出 cwd==dir_path 的 q 进程 PID 列表"""
    pids: list[int] = []
    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            comm_p = Path(f"/proc/{pid}/comm")
            cwd_p = Path(f"/proc/{pid}/cwd")
            try:
                if comm_p.read_text().strip() != "q":
                    continue
                cw = os.path.realpath(str(cwd_p))
                if cw == str(dir_path.resolve()):
                    pids.append(int(pid))
            except Exception:
                continue
    except Exception:
        pass
    return pids

def _purge_session_dir(sop_dir: Path) -> tuple[bool, str]:
    """
    安全删除会话目录：仅允许删除 SESSION_ROOT 下的子目录；
    先 SIGTERM 优雅退出占用的 q 进程，最多等 5s；仍存活则 SIGKILL；最后 rm -rf。
    """
    try:
        sop_dir = sop_dir.resolve()
        root = SESSION_ROOT.resolve()
        # 必须在 SESSION_ROOT 下，且不是根本身
        sop_dir.relative_to(root)
        if sop_dir == root:
            return False, "refuse to delete SESSION_ROOT itself"
        if not sop_dir.exists():
            return True, "dir not found (already gone)"

        pids = _pids_q_using_dir(sop_dir)
        if pids:
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass
            deadline = time.time() + 5.0
            while time.time() < deadline:
                alive = [pid for pid in pids if os.path.exists(f"/proc/{pid}")]
                if not alive:
                    break
                time.sleep(0.2)
            for pid in pids:
                if os.path.exists(f"/proc/{pid}"):
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except Exception:
                        pass

        shutil.rmtree(sop_dir)
        return True, "deleted"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _append_incident_sop_mapping(incident_key: Optional[str], sop_id: str) -> None:
    """将 incident_key 与 sop_id 的映射追加记录到 sop/incident_sop_map.jsonl（仅记录用途）。"""
    try:
        if not incident_key:
            return
        proj_dir = Path(__file__).resolve().parents[1]
        map_file = proj_dir / "sop" / "incident_sop_map.jsonl"
        map_file.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": int(time.time()),
            "incident_key": incident_key,
            "sop_id": sop_id,
        }
        with map_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


QTTY_MAX_CONN = int(os.getenv("QTTY_MAX_CONN", "20"))
_GLOBAL_CONN = 0
_GLOBAL_LOCK: Lock = Lock()
INIT_WAIT = float(os.getenv("INIT_WAIT", "5"))  # 非阻塞初始化等待秒数


class _PooledClient:
    def __init__(self, client: TerminalAPIClient):
        self.client = client
        self.lock: Lock = Lock()
        self.last_used: float = 0.0

class _QPool:
    def __init__(self, sop_id: str, size: int = 1):
        self.sop_id = sop_id
        self.size = 1  # 简化为单连接
        self._clients: List[_PooledClient] = []

    async def _ensure_client(self) -> bool:
        """如无客户端则懒创建一个；达到全局上限时尝试淘汰一条空闲连接。"""
        global _GLOBAL_CONN
        if self._clients:
            return True
        # 全局额度
        acquired = False
        async with _GLOBAL_LOCK:
            if _GLOBAL_CONN < QTTY_MAX_CONN:
                _GLOBAL_CONN += 1
                acquired = True
        if not acquired:
            # 尝试淘汰任意空闲
            evicted = await _evict_one_idle()
            if not evicted:
                return False
            async with _GLOBAL_LOCK:
                if _GLOBAL_CONN < QTTY_MAX_CONN:
                    _GLOBAL_CONN += 1
                    acquired = True
        if not acquired:
            return False
        # 创建并短等初始化
        try:
            print(f"[pool] create sop={self.sop_id} host={HOST} port={PORT}")
            cli = TerminalAPIClient(
                host=HOST, port=PORT, terminal_type=TerminalType.QCLI,
                url_query={"arg": self.sop_id}
            )
            ok = False
            try:
                ok = await asyncio.wait_for(cli.initialize(), timeout=INIT_WAIT)
            except asyncio.TimeoutError:
                ok = False
            except Exception:
                ok = False
            if not ok:
                try:
                    await cli._connection_manager.connect()
                    cli._setup_normal_message_handling()
                    cli._set_state(TerminalBusinessState.IDLE)
                    ok = True
                except Exception as e2:
                    print(f"[pool] fallback setup failed sop={self.sop_id} err={e2}")
                    ok = False
            if ok:
                self._clients.append(_PooledClient(cli))
                print(f"[pool] ready sop={self.sop_id} size=1")
                return True
        except Exception as e:
            print(f"[pool] create error sop={self.sop_id} err={e}")
        # 失败则回收全局额度
        async with _GLOBAL_LOCK:
            if _GLOBAL_CONN > 0:
                _GLOBAL_CONN -= 1
        return False

    async def acquire(self) -> Tuple[_PooledClient, int]:
        have = await self._ensure_client()
        if not have:
            raise HTTPException(503, "no available connection (global cap)")
        pc = self._clients[0]
        waited = 0
        while pc.lock.locked():
            await asyncio.sleep(0.01)
            waited += 1
            if waited > 30000:
                raise HTTPException(503, "acquire timeout")
        await pc.lock.acquire()
        pc.last_used = time.time()
        print(f"[pool] acquire sop={self.sop_id} idx=0")
        return pc, 0

    async def release(self, pc: _PooledClient):
        if pc.lock.locked():
            pc.lock.release()
            print(f"[pool] release sop={self.sop_id}")
            # 连接保持常驻


async def _evict_one_idle() -> bool:
    """在所有 sop 池中淘汰一个空闲连接（LRU），释放全局额度。"""
    global _GLOBAL_CONN
    # 选择最久未使用且未加锁的连接
    candidate: Tuple[str, int, _PooledClient] | None = None
    oldest = float('inf')
    for sop, pool in list(_SOP_POOLS.items()):
        for idx, pc in enumerate(pool._clients):
            if pc.lock.locked():
                continue
            lu = pc.last_used or 0.0
            if lu < oldest:
                oldest = lu
                candidate = (sop, idx, pc)
    if not candidate:
        return False
    sop, idx, pc = candidate
    try:
        # 关闭并移除
        try:
            await pc.client.shutdown()
        except Exception:
            pass
        pool = _SOP_POOLS.get(sop)
        if pool:
            try:
                pool._clients.pop(idx)
            except Exception:
                pass
            # 如果该 sop 已无连接，删除池条目
            if not pool._clients:
                _SOP_POOLS.pop(sop, None)
        # 回收全局额度
        async with _GLOBAL_LOCK:
            if _GLOBAL_CONN > 0:
                _GLOBAL_CONN -= 1
        return True
    except Exception:
        return False

_SOP_POOLS: Dict[str, _QPool] = {}

def _get_pool(sop_id: str) -> _QPool:
    if sop_id not in _SOP_POOLS:
        _SOP_POOLS[sop_id] = _QPool(sop_id, size=3)
    return _SOP_POOLS[sop_id]

async def _run_q_collect(sop_id: str, text: str, timeout: int = None) -> Dict[str, Any]:
    if timeout is None:
        timeout = Q_OVERALL_TIMEOUT
    out_chunks: List[str] = []
    events: List[Dict[str, Any]] = []
    stream_error_detected = False
    stream_error_message = ""

    print(f"[collect] start sop={sop_id} timeout={timeout}")

    pool = _get_pool(sop_id)
    pc: _PooledClient
    should_reset_client = False
    try:
        pc, _ = await pool.acquire()

        async def _inner():
            nonlocal stream_error_detected, stream_error_message
            # 直接发送原始文本，换行由底层 QCLI 适配（\r）
            prompt = (text or "")
            if not prompt.strip():
                raise HTTPException(400, f"empty prompt for sop_id={sop_id}")
            # 打印长度与 sha1 以确认是否重复构造
            import hashlib as _hl
            _sha1 = _hl.sha1(prompt.encode('utf-8', 'ignore')).hexdigest()
            print(f"[ask_json] send sop={sop_id} bytes={len(prompt.encode('utf-8'))} sha1={_sha1}")
            # 使用 execute_command_stream 以稳定的统一数据流
            async for chunk in pc.client.execute_command_stream(prompt, silence_timeout=float(timeout)):
                t = str(chunk.get("type", "")).lower()
                if t == "content":
                    out_chunks.append(chunk.get("content", ""))
                elif t in ("thinking", "tool_use", "pending", "error", "notification", "tool"):
                    # 兼容老事件名(notification/tool)，并捕获统一数据流事件
                    events.append(chunk)
                    if not stream_error_detected and t == "error":
                        stream_error_detected = True
                        # 尝试提取统一数据结构中的错误信息
                        meta = chunk.get("metadata", {}) if isinstance(chunk, dict) else {}
                        stream_error_message = (
                            meta.get("error_message") or meta.get("message") or chunk.get("content", "") or "stream error"
                        )
                elif t == "complete":
                    print(f"[collect] complete sop={sop_id} chunks={len(out_chunks)} events={len(events)}")
                    break

        await asyncio.wait_for(_inner(), timeout=timeout)
        ok = True
        err = ""
    except asyncio.TimeoutError:
        ok = False
        err = f"timeout after {timeout}s"
        print(f"[collect] timeout sop={sop_id} err={err}")
        should_reset_client = True
    except Exception as e:
        ok = False
        err = str(e)
        print(f"[collect] error sop={sop_id} err={e}")
        should_reset_client = True
    finally:
        # 释放连接
        try:
            await pool.release(pc)  # 内部已有 release 打印，这里不重复
        except Exception:
            pass
        # 若需要，主动关闭并移除损坏连接，避免下次复用坏状态
        if should_reset_client:
            try:
                await pc.client.shutdown()
            except Exception:
                pass
            try:
                if pool._clients and pool._clients[0] is pc:
                    pool._clients.pop(0)
            except Exception:
                pass
            try:
                async with _GLOBAL_LOCK:
                    if _GLOBAL_CONN > 0:
                        _GLOBAL_CONN -= 1
            except Exception:
                pass

    # 若流中检测到 error 事件，则将最终结果标记为失败，并填充错误信息
    if stream_error_detected:
        ok = False
        if not err:
            err = stream_error_message

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

def _resolve_sop_id(body: Dict[str, Any]) -> str:
    if "sop_id" in body and str(body["sop_id"]).strip():
        return str(body["sop_id"]).strip()
    if "incident_key" in body and str(body["incident_key"]).strip():
        return sop_id_from_incident_key(str(body["incident_key"]).strip())
    # fallback to alert path
    return _require_sop_inputs(body)


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": APP_NAME}

@app.post("/ask_json")
async def ask_json(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "expect JSON body")

    # 不允许传 text（只接受 alert / sop_id / incident_key）
    if "text" in body and str(body["text"]).strip():
        raise HTTPException(400, "text is not allowed; provide alert/sop_id/incident_key only")

    sop_id = _resolve_sop_id(body)
    (SESSION_ROOT / sop_id).mkdir(parents=True, exist_ok=True)

    # 记录 incident_key 与 sop_id 的映射（若存在 incident_key）
    ik = str(body.get("incident_key", "")).strip() or None
    if not ik and isinstance(body.get("alert"), dict):
        try:
            ik = build_incident_key_from_alert(body["alert"]) or None
        except Exception:
            ik = None
    _append_incident_sop_mapping(ik, sop_id)

    attempts = []
    sop_used = sop_id

    # 仅发送一次：允许工具
    prompt = _build_prompt(body, sop_id, allow_tools=True)
    _log_prompt(sop_id, prompt)
    t0 = time.time()
    res = await _run_q_collect(sop_id, prompt, timeout=Q_OVERALL_TIMEOUT)
    attempts.append({"allow_tools": True, "took_ms": int((time.time()-t0)*1000), "ok": res.get("ok", False)})

    # 超时清理：若本次请求以超时失败，尝试安全删除本次使用的会话目录
    purged_on_timeout = False
    purge_reason = ""
    if PURGE_ON_TIMEOUT and (not res.get("ok")) and ("timeout" in (res.get("error", "").lower())):
        ok_del, why = _purge_session_dir(SESSION_ROOT / sop_used)
        purged_on_timeout, purge_reason = ok_del, why

    out = {
        "ok": res["ok"],
        "sop_id": sop_id,
        "sop_used": sop_used,
        "output": res.get("output", ""),
        "events": res.get("events", []),
        "error": res.get("error", ""),
        "retried_with_tools": False,
        "fell_back_offline": False,
        "attempts": attempts,
        "retry_wait_seconds": 0,
        "purged_on_timeout": purged_on_timeout,
        "purge_reason": purge_reason,
    }
    return JSONResponse(out, status_code=200 if out["ok"] else 504)


# 流式接口：边收边回，避免链路读超时
@app.post("/call_stream")
async def call_stream(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "expect JSON body")

    sop_id = _resolve_sop_id(body)
    (SESSION_ROOT / sop_id).mkdir(parents=True, exist_ok=True)

    prompt = _build_prompt(body, sop_id, allow_tools=True)
    _log_prompt(sop_id, prompt)

    async def _gen():
        pool = _get_pool(sop_id)
        pc: _PooledClient
        try:
            pc, _ = await pool.acquire()

            # 发送并消费结构化流；收到 complete 退出
            first_chunk_time = None

            async def _inner_stream():
                nonlocal first_chunk_time
                async for ch in pc.client.execute_command_stream(prompt, silence_timeout=float(STREAM_OVERALL_TIMEOUT)):
                    t = str(ch.get("type", "")).lower()
                    now = time.time()
                    if first_chunk_time is None:
                        first_chunk_time = now
                    # 输出仅透传 content；其它类型不返回正文
                    if t == "content":
                        yield ch.get("content", "")
                    elif t == "complete":
                        return
            # 将内部 async 生成器桥接为同步 yield
            async for piece in _inner_stream():
                yield piece
        finally:
            try:
                await pool.release(pc)
            except Exception:
                pass

    return StreamingResponse(_gen(), media_type="text/plain; charset=utf-8")

