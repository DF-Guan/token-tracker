import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .types import AgentInfo, RateLimits, UsageEntry, normalize_pct
from .util import iter_jsonl_dicts, project_from_cwd

CODEX_DIR = os.path.expanduser("~/.codex")
SESSIONS_DIR = os.path.join(CODEX_DIR, "sessions")
STATE_DB = os.path.join(CODEX_DIR, "state_5.sqlite")
_RATE_LIMIT_SCAN_FILES = 5  # 只扫最近改动的 N 个 session 文件找限额信息


def detect() -> AgentInfo | None:
    # 以 ~/.codex 目录判断是否安装（与 hooks._has_codex 一致；不要求已产生 sessions/）
    if Path(CODEX_DIR).is_dir():
        return AgentInfo(id="codex", name="Codex")
    return None


def load_entries(hours_back: int = 0) -> list[UsageEntry]:
    entries: list[UsageEntry] = []
    seen: set[str] = set()
    cutoff = None
    if hours_back > 0:
        cutoff = datetime.now(UTC) - timedelta(hours=hours_back)

    models = _load_thread_models()

    sessions_path = Path(SESSIONS_DIR)
    if not sessions_path.is_dir():
        return entries

    for jsonl_path in sessions_path.rglob("*.jsonl"):
        _parse_jsonl(jsonl_path, models, entries, seen, cutoff)

    entries.sort(key=lambda e: e.timestamp)
    return entries


def _load_thread_models() -> dict[str, str]:
    if not os.path.exists(STATE_DB):
        return {}
    try:
        conn = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
        rows = conn.execute("SELECT id, model FROM threads WHERE model IS NOT NULL").fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}
    except (sqlite3.Error, OSError):
        return {}


def load_rate_limits() -> RateLimits | None:
    sessions_path = Path(SESSIONS_DIR)
    if not sessions_path.is_dir():
        return None

    # session 文件在轮转，rglob 与 stat 之间文件可能消失：mtime 取不到时退化为 0，避免整体崩溃
    jsonl_files = sorted(sessions_path.rglob("*.jsonl"), key=_safe_mtime, reverse=True)
    models = _load_thread_models()

    for path in jsonl_files[:_RATE_LIMIT_SCAN_FILES]:
        rl = _extract_rate_limits(path, models)
        if rl:
            return rl
    return None


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _extract_rate_limits(path: Path, models: dict[str, str]) -> RateLimits | None:
    session_id = ""
    last_payload = None
    for data in iter_jsonl_dicts(path):
        if data.get("type") == "session_meta":
            session_id = data.get("payload", {}).get("id", "")
        if data.get("type") != "event_msg":
            continue
        payload = data.get("payload", {})
        if payload.get("type") != "token_count":
            continue
        rl = payload.get("rate_limits")
        if rl:
            last_payload = (rl, payload.get("info") or {}, session_id)

    if not last_payload:
        return None

    rl, info, sid = last_payload

    now_ts = datetime.now(UTC).timestamp()
    five_pct = five_reset = None
    seven_pct = seven_reset = None

    # 按 window_minutes 字段分配 5h / 7d 桶，
    # 而不是固定 primary→5h、secondary→7d（free plan 实测 primary 为 7 天窗口）
    for bucket in (rl.get("primary"), rl.get("secondary")):
        if not bucket:
            continue
        resets = bucket.get("resets_at")
        window = bucket.get("window_minutes") or 0
        pct = normalize_pct(bucket.get("used_percent"), resets, now_ts)
        if window < 1440:
            five_pct, five_reset = pct, resets
        else:
            seven_pct, seven_reset = pct, resets

    if five_pct is None and seven_pct is None:
        return None

    return RateLimits(
        five_hour_pct=five_pct,
        five_hour_resets_at=five_reset,
        seven_day_pct=seven_pct,
        seven_day_resets_at=seven_reset,
        model=models.get(sid, ""),
        plan_type=rl.get("plan_type") or "",
        context_window=info.get("model_context_window"),
    )


def _parse_jsonl(
    path: Path,
    models: dict[str, str],
    entries: list[UsageEntry],
    seen: set[str],
    cutoff: datetime | None,
) -> None:
    session_id = ""
    session_ts = ""
    project = "unknown"
    model = "unknown"
    last_usage = None
    msg_count = 0

    for data in iter_jsonl_dicts(path):
        row_type = data.get("type")

        if row_type == "session_meta":
            payload = data.get("payload", {})
            session_id = payload.get("id", "")
            session_ts = payload.get("timestamp", "")
            cwd = payload.get("cwd", "")
            if cwd:
                project = project_from_cwd(cwd)
            model = models.get(session_id, "unknown")
            continue

        if row_type != "event_msg":
            continue

        payload = data.get("payload", {})
        if payload.get("type") == "token_count":
            info = payload.get("info")
            if info and info.get("total_token_usage"):
                last_usage = info["total_token_usage"]
                msg_count += 1

    if not last_usage or not session_id:
        return

    cached = last_usage.get("cached_input_tokens", 0)
    input_tokens = last_usage.get("input_tokens", 0) - cached
    output_tokens = last_usage.get("output_tokens", 0) + last_usage.get("reasoning_output_tokens", 0)

    if input_tokens == 0 and output_tokens == 0:
        return

    try:
        ts = datetime.fromisoformat(session_ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return

    if cutoff and ts < cutoff:
        return

    if session_id in seen:
        return
    seen.add(session_id)

    entries.append(UsageEntry(
        timestamp=ts,
        session_id=session_id,
        message_id=session_id,
        request_id="",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=0,
        cache_read_tokens=cached,
        cost_usd=None,
        project=project,
        agent_id="codex",
        message_count=msg_count,
    ))
