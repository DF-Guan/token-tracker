"""纯格式化与分组工具：宽度模式、token/成本/时长格式、agent/模型短名、卡片文本片段（品牌行 / 指标）。"""

from collections import defaultdict

from rich.text import Text

from .console import get_console
from .theme import _S

AGENT_SHORT = {"claude-code": "CC", "codex": "Codex"}
AGENT_LABEL = {"claude-code": "Claude Code", "codex": "Codex"}

MODEL_SHORT = {
    "claude-fable-5": "Fable 5",
    "claude-opus-4-6": "Opus 4.6",
    "claude-opus-4-7": "Opus 4.7",
    "claude-opus-4-8": "Opus 4.8",
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


def brand_line(agents: list[str]) -> Text:
    """品牌行：Token Tracker（红）+ agents（暗红，` + ` 连接）。daily / weekly 卡片共用。"""
    line = Text()
    line.append("Token Tracker", style=f"bold {_S.red}")
    line.append(": ", style=f"bold {_S.red}")
    for i, a in enumerate(agents):
        if i:
            line.append(" + ", style=f"dim {_S.red}")
        line.append(a, style=f"dim {_S.red}")
    return line


def append_metric(body: Text, label: str, value: str, color: str,
                  cur: float | None = None, prev: float | None = None) -> None:
    """往 body 追加「label: value」（label 常规、value 加粗）；传 cur/prev 且 prev>0 时再追加环比（dim）。"""
    body.append(f"{label}: ", style=color)
    body.append(value, style=f"bold {color}")
    if cur is not None and prev and prev > 0:
        pct = (cur - prev) / prev * 100
        body.append(f" ({'↑' if pct >= 0 else '↓'}{abs(pct):.0f}%)", style=f"dim {color}")
