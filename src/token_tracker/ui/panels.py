"""面板与概览：tab 栏、总览 header、月概览、P90/限额数据面板。"""

from datetime import UTC, datetime

from rich.panel import Panel
from rich.text import Text

from ..adapters.types import DailyStats, MonthlyStats, P90Limits, RateLimits, SessionBlock, WeeklyStats
from ..i18n import t
from .console import get_console
from .format import AGENT_LABEL, AGENT_SHORT, _display_width, _fmt_cost, _fmt_tokens, _width_mode
from .theme import _S, _pct_style
from .widgets import _append_bar, _append_trend, _render_rate_bar, _render_week_section


def render_tab_bar(agent_names: list[str], current: int) -> None:
    line = Text()
    line.append("  ")
    compact = get_console().width < 72
    for i, name in enumerate(agent_names):
        if i > 0:
            line.append(" │ ", style=_S.dim)
        label = AGENT_SHORT.get("claude-code" if name == "Claude Code" else name.lower(), name)
        if compact and name == "Claude Code":
            label = "CC"
        elif compact:
            label = name[:8]
        if i == current:
            line.append(f" {label} ", style="bold reverse")
        else:
            line.append(f" {label} ", style=_S.dim)
    help_text = t("tab_help_compact") if compact else t("tab_help")
    line.append(help_text, style=_S.dim)
    get_console().print(line)


def _render_header(agents: list[str], total_tokens: int, total_cost: float,
                   total_sessions: int, total_messages: int, days: int,
                   top_margin: bool = True) -> None:
    agent_text = " ".join(f"[{_S.good}]●[/{_S.good}] {a}" for a in agents)
    if top_margin:
        get_console().print()
    get_console().print(Panel(
        f"[bold]Token Tracker[/bold]  {agent_text}",
        border_style="blue",
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


def _render_month_overview(month: MonthlyStats, last_month: MonthlyStats | None = None) -> None:
    now = datetime.now(UTC)
    elapsed_days = now.day
    daily_avg_cost = month.cost_usd / elapsed_days if elapsed_days > 0 else 0

    lines = Text()
    lines.append(t("month_overview"), style="bold")

    lines.append("  Token: ", style=_S.dim)
    lines.append(f"{_fmt_tokens(month.total_tokens)}", style=_S.token_bold)
    if last_month:
        _append_trend(lines, month.total_tokens, last_month.total_tokens)

    lines.append(f"  {t('cost_colon')}", style=_S.dim)
    lines.append(f"{_fmt_cost(month.cost_usd)}", style=_S.cost_bold)

    lines.append(f"  {t('sessions_colon')}", style=_S.dim)
    lines.append(f"{month.session_count}", style="bold")
    lines.append(f"  {t('messages_colon')}", style=_S.dim)
    lines.append(f"{month.message_count}", style="bold")
    lines.append(f"  {t('daily_avg_colon')}", style=_S.dim)
    lines.append(f"{_fmt_cost(daily_avg_cost)}", style=_S.cost)

    get_console().print(lines)


def _render_daily_panel(
    today: DailyStats,
    yesterday: DailyStats | None,
    p90: P90Limits,
    week: WeeklyStats | None = None,
    last_week: WeeklyStats | None = None,
) -> None:
    bar_width = 20 if _width_mode() == "compact" else 30
    lines = Text()
    lines.append(f"{t('daily_panel_title')}\n\n", style="bold")

    p90_items = [
        ("Token Usage", today.total_tokens, p90.token_limit, _fmt_tokens),
        ("Cost Usage", today.cost_usd, p90.cost_limit, _fmt_cost),
        ("Msg Usage", today.message_count, p90.message_limit, lambda x: t("msg_unit", n=x)),
    ]
    max_pct = 0.0
    for label, current, limit, unit_fmt in p90_items:
        pct = min(current / limit * 100, 100) if limit > 0 else 0
        max_pct = max(max_pct, pct)
        display_label = f"  {label}" + " " * (14 - _display_width(label))
        suffix = f"  {unit_fmt(current)} / {unit_fmt(limit)}"
        _append_bar(lines, display_label, pct, bar_width, suffix)
        lines.append("\n")

    lines.append(f"  Token     {_fmt_tokens(today.total_tokens)}", style=_S.token)
    if yesterday:
        _append_trend(lines, today.total_tokens, yesterday.total_tokens)
    lines.append(f"  Output: {_fmt_tokens(today.output_tokens)}", style=_S.dim)
    lines.append(f"  Cache: {_fmt_tokens(today.cache_creation_tokens + today.cache_read_tokens)}\n", style=_S.dim)
    lines.append(f"  {t('cost_label')}  {_fmt_cost(today.cost_usd)}", style=_S.cost)
    if yesterday:
        _append_trend(lines, today.cost_usd, yesterday.cost_usd)
    lines.append(f"  {t('session_msg', sessions=today.session_count, msgs=today.message_count)}", style=_S.dim)
    if today.message_count > 0:
        tokens_per_msg = today.total_tokens // today.message_count
        lines.append(f"  {t('rate_per_msg', rate=_fmt_tokens(tokens_per_msg))}", style=_S.dim)

    if week:
        now = datetime.now(UTC)
        elapsed_days = now.weekday() + 1
        daily_avg_cost = week.cost_usd / elapsed_days if elapsed_days > 0 else 0

        lines.append(f"\n\n  {t('week_token', tokens=_fmt_tokens(week.total_tokens))}", style=_S.token)
        if last_week:
            _append_trend(lines, week.total_tokens, last_week.total_tokens)
        lines.append(f"  Output: {_fmt_tokens(week.output_tokens)}", style=_S.dim)
        lines.append(f"  {t('rate_per_day', rate=_fmt_tokens(week.total_tokens // elapsed_days))}\n", style=_S.dim)
        lines.append(f"  {t('week_cost')}  {_fmt_cost(week.cost_usd)}", style=_S.cost)
        if last_week:
            _append_trend(lines, week.cost_usd, last_week.cost_usd)
        lines.append(f"  {t('daily_avg', cost=_fmt_cost(daily_avg_cost))}", style=_S.dim)
        lines.append(f"  {t('session_msg', sessions=week.session_count, msgs=week.message_count)}", style=_S.dim)

    lines.append("\n")

    get_console().print(Panel(lines, border_style=_pct_style(max_pct), padding=(0, 1)))


def _render_active_block(
    b: SessionBlock,
    rate_limits: RateLimits | None = None,
    week: WeeklyStats | None = None,
    last_block: SessionBlock | None = None,
    last_week: WeeklyStats | None = None,
) -> None:
    now = datetime.now(UTC)
    elapsed = (now - b.start_time).total_seconds()
    remaining = (b.end_time - now).total_seconds()

    elapsed_min = int(elapsed / 60)
    remaining_min = int(remaining / 60)
    remaining_h = remaining_min // 60
    remaining_m = remaining_min % 60

    bar_width = 20 if _width_mode() == "compact" else 30

    lines = Text()
    lines.append(f"{t('active_panel_title')}\n\n", style="bold")

    if rate_limits and rate_limits.five_hour_pct is not None:
        _render_rate_bar(lines, t("limit_5h"), rate_limits.five_hour_pct,
                         rate_limits.five_hour_resets_at, bar_width)

    lines.append(f"  {t('time_label')}      ", style=_S.dim)
    lines.append(f"{t('time_elapsed', elapsed=elapsed_min, h=remaining_h, m=remaining_m)}\n", style=_S.dim)

    lines.append(f"  Token     {_fmt_tokens(b.total_tokens)}", style=_S.token)
    if last_block:
        _append_trend(lines, b.total_tokens, last_block.total_tokens)
    lines.append(f"  Output: {_fmt_tokens(b.output_tokens)}", style=_S.dim)
    lines.append(f"  {t('rate_per_min', rate=_fmt_tokens(int(b.burn_rate)))}\n", style=_S.dim)
    lines.append(f"  {t('cost_label')}  {_fmt_cost(b.cost_usd)}", style=_S.cost)
    if rate_limits and rate_limits.model:
        lines.append(f"  {t('model_label', model=rate_limits.model)}", style=_S.dim)
    lines.append("\n")
    lines.append(f"  {t('msg_count', n=len(b.entries))}", style=_S.dim)

    if rate_limits and rate_limits.seven_day_pct is not None:
        lines.append("\n\n")
        _render_rate_bar(lines, t("limit_7d"), rate_limits.seven_day_pct,
                         rate_limits.seven_day_resets_at, bar_width, "%m-%d %H:%M")
        if week:
            _render_week_section(lines, week, last_week)

    lines.append("\n")

    pct = rate_limits.five_hour_pct if rate_limits and rate_limits.five_hour_pct is not None else 0
    get_console().print(Panel(lines, border_style=_pct_style(pct), padding=(0, 1)))


def _render_idle_panel(
    rate_limits: RateLimits,
    week: WeeklyStats | None = None,
    last_week: WeeklyStats | None = None,
) -> None:
    bar_width = 20 if _width_mode() == "compact" else 30
    lines = Text()
    lines.append(f"{t('idle_panel_title')}\n\n", style="bold")

    if rate_limits.five_hour_pct is not None:
        _render_rate_bar(lines, t("limit_5h"), rate_limits.five_hour_pct,
                         rate_limits.five_hour_resets_at, bar_width)

    if rate_limits.seven_day_pct is not None:
        if rate_limits.five_hour_pct is not None:
            lines.append("\n")
        _render_rate_bar(lines, t("limit_7d"), rate_limits.seven_day_pct,
                         rate_limits.seven_day_resets_at, bar_width, "%m-%d %H:%M")
        if week:
            _render_week_section(lines, week, last_week)

    if rate_limits.model:
        lines.append(f"\n  {t('model_label', model=rate_limits.model)}", style=_S.dim)

    lines.append("\n")

    max_pct = max(rate_limits.five_hour_pct or 0, rate_limits.seven_day_pct or 0)
    get_console().print(Panel(lines, border_style=_pct_style(max_pct), padding=(0, 1)))
