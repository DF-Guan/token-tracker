"""纯格式化与分组工具：宽度模式、token/成本/时长格式、agent/模型短名。"""

from collections import defaultdict

from .console import get_console

AGENT_SHORT = {"claude-code": "CC", "codex": "Codex"}
AGENT_LABEL = {"claude-code": "Claude Code", "codex": "Codex"}

MODEL_SHORT = {
    "claude-opus-4-6": "Opus 4.6",
    "claude-opus-4-7": "Opus 4.7",
    "claude-sonnet-4-6": "Sonnet 4.6",
    "claude-sonnet": "Sonnet",
    "claude-haiku-4-5-20251001": "Haiku 4.5",
    "claude-haiku": "Haiku",
}


def _width_mode() -> str:
    w = get_console().width
    if w < 100:
        return "compact"
    if w < 120:
        return "medium"
    return "wide"


def _is_multi_agent(stats) -> bool:
    return len({s.agent_id for s in stats if s.agent_id}) > 1


def _group_by_agent(stats) -> dict[str, list]:
    by_agent: dict[str, list] = defaultdict(list)
    for s in stats:
        by_agent[s.agent_id].append(s)
    return by_agent


def _model_short(model: str) -> str:
    if model in MODEL_SHORT:
        return MODEL_SHORT[model]
    if "/" in model:
        return model.split("/")[-1][:16]
    return model[:16]


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_cost(usd: float) -> str:
    if usd >= 100:
        return f"${usd:.0f}"
    if usd >= 1:
        return f"${usd:.2f}"
    if usd > 0:
        return f"${usd:.3f}"
    return "$0"


def _fmt_duration(minutes: float) -> str:
    if minutes >= 60:
        h = int(minutes // 60)
        m = int(minutes % 60)
        return f"{h}h{m:02d}m"
    return f"{int(minutes)}min"


def _display_width(s: str) -> int:
    w = 0
    for ch in s:
        w += 2 if ord(ch) > 0x7F else 1
    return w


def _project_short(project: str) -> str:
    return project if project else "unknown"
