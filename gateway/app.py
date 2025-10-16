import os, sys, json, asyncio, time, re, subprocess, shutil, signal
from asyncio import Lock
from typing import List, Tuple
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
# 统一使用仓库下的 q-sessions 目录
SESSION_ROOT = Path(os.getenv("SESSION_ROOT", str(Path(__file__).resolve().parents[1] / "q-sessions")))
SOP_DIR = Path(os.getenv("SOP_DIR", "./sop"))
TASK_DOC_PATH = Path(os.getenv("TASK_DOC_PATH", "./task_instructions.md"))
TASK_DOC_BUDGET = int(os.getenv("TASK_DOC_BUDGET", "131072"))
ALERT_JSON_PRETTY = os.getenv("ALERT_JSON_PRETTY", "1") not in ("0","false","False")

Q_OVERALL_TIMEOUT = int(os.getenv("Q_OVERALL_TIMEOUT", "30"))
SLASH_TIMEOUT = int(os.getenv("SLASH_TIMEOUT", "10"))

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

QTTY_MAX_CONN = int(os.getenv("QTTY_MAX_CONN", "20"))
_GLOBAL_CONN = 0
_GLOBAL_LOCK: Lock = Lock()


class _PooledClient:
    def __init__(self, client: TerminalAPIClient):
        self.client = client
        self.lock: Lock = Lock()
        self.last_used: float = 0.0

class _QPool:
    def __init__(self, sop_id: str, size: int = 1):
        self.sop_id = sop_id
        self.size = size
        self._clients: List[_PooledClient] = []
        self._init_lock: Lock = Lock()

    async def _ensure_min_clients(self):
        global _GLOBAL_CONN
        async with self._init_lock:
            while len(self._clients) < self.size:
                # 全局连接上限控制
                acquired_global = False
                for _ in range(300):  # 最长约3s等待全局额度
                    async with _GLOBAL_LOCK:
                        if _GLOBAL_CONN < QTTY_MAX_CONN:
                            _GLOBAL_CONN += 1
                            acquired_global = True
                            break
                    await asyncio.sleep(0.01)

                if not acquired_global:
                    # 全局连接已达上限，尝试淘汰一个空闲连接
                    evicted = await _evict_one_idle()
                    if not evicted:
                        # 无可淘汰连接，放弃创建
                        break
                    # 淘汰成功后继续重试一次获取额度
                    async with _GLOBAL_LOCK:
                        if _GLOBAL_CONN < QTTY_MAX_CONN:
                            _GLOBAL_CONN += 1
                            acquired_global = True
                        else:
                            # 极端情况下仍不可用
                            break

                try:
                    cli = TerminalAPIClient(
                        host=HOST, port=PORT, terminal_type=TerminalType.QCLI,
                        url_query={"arg": self.sop_id}
                    )
                    ok = await cli.initialize()
                    if ok:
                        self._clients.append(_PooledClient(cli))
                    else:
                        # 初始化失败，回收全局名额
                        async with _GLOBAL_LOCK:
                            _GLOBAL_CONN -= 1
                        break
                except Exception:
                    # 异常也需回收名额
                    async with _GLOBAL_LOCK:
                        _GLOBAL_CONN -= 1
                    break

    async def acquire(self) -> Tuple[_PooledClient, int]:
        await self._ensure_min_clients()
        # 简单轮询：寻找空闲连接
        # 若都繁忙，等待任一连接释放
        waited = 0
        while True:
            for idx, pc in enumerate(self._clients):
                if not pc.lock.locked():
                    await pc.lock.acquire()
                    pc.last_used = time.time()
                    return pc, idx
            await asyncio.sleep(0.01)
            waited += 1
            if waited > 30000 and not self._clients:
                # 等待超时且无可用连接
                raise HTTPException(503, "no available connection for sop_id")

    async def release(self, pc: _PooledClient):
        if pc.lock.locked():
            pc.lock.release()
            # 连接保持，不回收；若未来需要关闭，可在此实现空闲回收并减少 _GLOBAL_CONN


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

    pool = _get_pool(sop_id)
    pc: _PooledClient
    try:
        pc, _ = await pool.acquire()

        async def _inner():
            # 确保有换行并发送
            prompt = (text or "").rstrip("\n") + "\n"
            if not prompt.strip():
                raise HTTPException(400, f"empty prompt for sop_id={sop_id}")
            print(f"[ask_json] send sop={sop_id} bytes={len(prompt.encode('utf-8'))}")
            
            await pc.client.send_text(prompt)
            async for ev in pc.client.stream():
                t = ev.get("type")
                if t == "content":
                    out_chunks.append(ev.get("data") or ev.get("content") or ev.get("text") or "")
                elif t in ("notification", "tool", "error"):
                    events.append(ev)
                elif t == "complete":
                    break

        await asyncio.wait_for(_inner(), timeout=timeout)
        ok = True
        err = ""
    except asyncio.TimeoutError:
        ok = False
        err = f"timeout after {timeout}s"
    except Exception as e:
        ok = False
        err = str(e)
    finally:
        # 释放连接
        try:
            await pool.release(pc)
        except Exception:
            pass

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

    # 1) 首次：允许工具
    prompt = _build_prompt(body, sop_id, allow_tools=True)
    _log_prompt(sop_id, prompt)
    t0 = time.time()
    res = await _run_q_collect(sop_id, prompt, timeout=Q_OVERALL_TIMEOUT)
    attempts.append({"allow_tools": True, "took_ms": int((time.time()-t0)*1000), "ok": res["ok"]})

    # 2) 若工具未就绪：等待 TOOL_RETRY_WAIT 秒，再“允许工具”重试 N 次
    retried_with_tools = False
    if _looks_like_tool_unavailable(res.get("output", "")) and TOOL_RETRY_COUNT > 0:
        retried_with_tools = True
        for _ in range(TOOL_RETRY_COUNT):
            await asyncio.sleep(TOOL_RETRY_WAIT)
            prompt2 = _build_prompt(body, sop_id, allow_tools=True)
            _log_prompt(sop_id, prompt2)
            t1 = time.time()
            res2 = await _run_q_collect(sop_id, prompt2, timeout=Q_OVERALL_TIMEOUT)
            attempts.append({"allow_tools": True, "took_ms": int((time.time()-t1)*1000), "ok": res2["ok"]})
            if res2["ok"] and not _looks_like_tool_unavailable(res2.get("output", "")):
                res = res2
                break

    # 3) 仍失败/仍提示工具未就绪 → 禁用工具离线分析（一次）
    fell_back_offline = False
    if OFFLINE_FALLBACK and (not res["ok"] or _looks_like_tool_unavailable(res.get("output", ""))):
        fell_back_offline = True

        # 生成 alert_id，作为边界标记
        def _alert_id(alert: dict) -> str:
            try:
                blob = json.dumps(alert, ensure_ascii=False, sort_keys=True)
            except Exception:
                blob = str(alert)
            import hashlib
            return hashlib.sha1(blob.encode("utf-8", "ignore")).hexdigest()[:12]

        aid = _alert_id(body.get("alert", {})) if isinstance(body.get("alert"), dict) else None

        # 离线兜底：禁工具 + 边界提示，且使用“冷目录”避免历史影响
        prompt_off = _build_prompt(body, sop_id, allow_tools=False, boundary_id=aid)
        _log_prompt(sop_id, prompt_off)
        sop_id_off = f"{sop_id}__offline"
        (SESSION_ROOT / sop_id_off).mkdir(parents=True, exist_ok=True)
        sop_used = sop_id_off

        t2 = time.time()
        res = await _run_q_collect(sop_id_off, prompt_off, timeout=Q_OVERALL_TIMEOUT)
        attempts.append({
            "allow_tools": False,
            "cold_dir": True,
            "took_ms": int((time.time()-t2)*1000),
            "ok": res["ok"]
        })

    # 超时清理：若本次请求以超时失败，尝试安全删除本次使用的会话目录
    purged_on_timeout = False
    purge_reason = ""
    if (not res.get("ok")) and ("timeout" in (res.get("error", "").lower())):
        ok_del, why = _purge_session_dir(SESSION_ROOT / sop_used)
        purged_on_timeout, purge_reason = ok_del, why

    out = {
        "ok": res["ok"],
        "sop_id": sop_id,
        "sop_used": sop_used,
        "output": res.get("output", ""),
        "events": res.get("events", []),
        "error": res.get("error", ""),
        "retried_with_tools": retried_with_tools,
        "fell_back_offline": fell_back_offline,
        "attempts": attempts,
        "retry_wait_seconds": TOOL_RETRY_WAIT,
        "purged_on_timeout": purged_on_timeout,
        "purge_reason": purge_reason,
    }
    return JSONResponse(out, status_code=200 if out["ok"] else 504)


