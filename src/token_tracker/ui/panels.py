"""面板与概览：tab 栏、总览 header、月概览、P90/限额数据面板。"""

from rich.panel import Panel
from rich.text import Text

from ..i18n import t
from .console import get_console
from .format import AGENT_LABEL, _fmt_cost, _fmt_tokens
from .theme import _S


def _render_header(agents: list[str], total_tokens: int, total_cost: float,
                   total_sessions: int, total_messages: int, days: int,
                   top_margin: bool = True) -> None:
    agent_text = " ".join(f"[{_S.good}]●[/{_S.good}] {a}" for a in agents)
    if top_margin:
        get_console().print()
    get_console().print(Panel(
        f"[bold]Token Tracker[/bold]  {agent_text}",
        border_style=_S.blue,
        padding=(0, 1),
    ))

    lines = Text()
    lines.append(t("history_overview"), style="bold")
    lines.append("  Token: ", style=_S.dim)
    lines.append(f"{_fmt_tokens(total_tokens)}", style=_S.token_bold)
    lines.append(f"  {t('cost_colon')}", style=_S.dim)
    lines.append(f"{_fmt_cost(total_cost)}", style=_S.cost_bold)
    lines.append(f"  {t('sessions_colon')}", style=_S.dim)
    lines.append(f"{total_sessions}", style="bold")
    lines.append(f"  {t('messages_colon')}", style=_S.dim)
    lines.append(f"{total_messages}", style="bold")
    lines.append(f"  {t('days_colon')}", style=_S.dim)
    lines.append(f"{days}", style=_S.accent)
    get_console().print(lines)


def _render_agent_summaries(stats_list, multi_agent: bool) -> None:
    if not multi_agent:
        return
    by_agent: dict[str, dict] = {}
    for s in stats_list:
        if not s.agent_id:
            continue
        a = by_agent.setdefault(s.agent_id, {"tokens": 0, "cost": 0.0, "sessions": 0, "messages": 0})
        a["tokens"] += s.total_tokens
        a["cost"] += s.cost_usd
        a["sessions"] += s.session_count
        a["messages"] += s.message_count
    if len(by_agent) < 2:
        return
    for agent_id, d in sorted(by_agent.items()):
        lines = Text()
        label = AGENT_LABEL.get(agent_id, agent_id)
        lines.append(f"{label}", style="bold")
        lines.append("  Token: ", style=_S.dim)
        lines.append(f"{_fmt_tokens(d['tokens'])}", style=_S.token_bold)
        lines.append(f"  {t('cost_colon')}", style=_S.dim)
        lines.append(f"{_fmt_cost(d['cost'])}", style=_S.cost_bold)
        lines.append(f"  {t('sessions_colon')}", style=_S.dim)
        lines.append(f"{d['sessions']}", style="bold")
        lines.append(f"  {t('messages_colon')}", style=_S.dim)
        lines.append(f"{d['messages']}", style="bold")
        get_console().print(lines)
