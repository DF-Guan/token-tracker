"""表格渲染（daily/weekly/monthly/sessions/模型分布）与 dashboard 编排。

格式化/主题/小部件/面板已拆到 format.py / theme.py / widgets.py / panels.py；
本模块聚焦各类表格与把它们组装成 dashboard。
"""

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..adapters.types import DailyStats, MonthlyStats, P90Limits, RateLimits, SessionBlock, SessionStats, WeeklyStats
from ..i18n import t
from .console import get_console
from .format import (
    AGENT_LABEL,
    AGENT_SHORT,
    _fmt_cost,
    _fmt_duration,
    _fmt_tokens,
    _group_by_agent,
    _is_multi_agent,
    _model_short,
    _project_short,
    _width_mode,
)
from .panels import (
    _render_active_block,
    _render_agent_summaries,
    _render_daily_panel,
    _render_header,
    _render_idle_panel,
    _render_month_overview,
    render_tab_bar,
)
from .theme import _S, _token_heat_style

# render_tab_bar / AGENT_LABEL 在子模块定义，这里 re-export 以保持 ui.tables 的公开入口集中
__all__ = [
    "AGENT_LABEL",
    "render_daily",
    "render_dashboard",
    "render_monthly",
    "render_sessions",
    "render_tab_bar",
    "render_weekly",
]


def render_dashboard(
    daily_stats: list[DailyStats],
    weekly_stats: list[WeeklyStats],
    monthly_stats: list[MonthlyStats],
    sessions: list[SessionStats],
    blocks: list[SessionBlock],
    rate_limits: RateLimits | None = None,
    p90: P90Limits | None = None,
    agents: list[str] | None = None,
    session_limit: int = 10,
    top_margin: bool = True,
    session_title: str | None = None,
) -> None:
    if not daily_stats:
        get_console().print(f"[{_S.warn}]{t('no_data')}[/{_S.warn}]")
        return

    total_tokens = sum(s.total_tokens for s in daily_stats)
    total_cost = sum(s.cost_usd for s in daily_stats)
    total_msgs = sum(s.message_count for s in daily_stats)
    total_sessions = sum(s.session_count for s in daily_stats)

    _render_header(
        agents or ["Claude Code"],
        total_tokens,
        total_cost,
        total_sessions,
        total_msgs,
        len(daily_stats),
        top_margin=top_margin,
    )

    # --- 本月概览 ---
    if monthly_stats:
        last_month = monthly_stats[-2] if len(monthly_stats) >= 2 else None
        _render_month_overview(monthly_stats[-1], last_month)

    # --- 数据面板 ---
    cur_week = weekly_stats[-1] if weekly_stats else None
    last_week = weekly_stats[-2] if len(weekly_stats) >= 2 else None

    has_limits = rate_limits and (rate_limits.five_hour_pct is not None or rate_limits.seven_day_pct is not None)
    if p90 and not has_limits:
        today = daily_stats[-1] if daily_stats else None
        yesterday = daily_stats[-2] if len(daily_stats) >= 2 else None
        if today:
            _render_daily_panel(today, yesterday, p90, cur_week, last_week)
    else:
        active_blocks = [b for b in blocks if not b.is_gap and b.is_active]
        finished_blocks = [b for b in blocks if not b.is_gap and not b.is_active]
        last_block = finished_blocks[-1] if finished_blocks else None
        if active_blocks:
            for b in active_blocks:
                _render_active_block(b, rate_limits, cur_week, last_block, last_week)
        elif rate_limits:
            _render_idle_panel(rate_limits, cur_week, last_week)

    # --- 最近会话 ---
    if sessions and session_limit > 0:
        _render_recent_sessions(sessions[:session_limit], title=session_title)

    get_console().print()


def _render_recent_sessions(stats: list[SessionStats], title: str | None = None) -> None:
    multi_agent = _is_multi_agent(stats)
    mode = _width_mode()
    table = Table(
        title=title or t("recent_sessions"),
        box=box.SIMPLE_HEAVY,
        header_style="bold",
        padding=(0, 1),
        expand=True,
    )
    table.add_column(t("col_time"), style=_S.token, no_wrap=True)
    if multi_agent:
        table.add_column(t("col_source"), no_wrap=True)
    table.add_column(t("col_project"), no_wrap=True, max_width=14)
    if mode != "compact":
        table.add_column(t("col_model"), style=_S.cost, no_wrap=True)
    table.add_column("Input", justify="right")
    table.add_column("Output", justify="right")
    table.add_column(t("col_total_tokens"), justify="right", style=_S.token_bold)
    table.add_column(t("col_cost"), justify="right", style=_S.good)
    table.add_column(t("col_messages"), justify="right", style=_S.dim)

    for s in stats:
        row: list = [s.start_time.strftime("%m-%d %H:%M")]
        if multi_agent:
            row.append(AGENT_SHORT.get(s.agent_id, s.agent_id))
        row.append(_project_short(s.project))
        if mode != "compact":
            row.append(_model_short(s.model))
        row += [
            _fmt_tokens(s.input_tokens),
            _fmt_tokens(s.output_tokens),
            Text(_fmt_tokens(s.total_tokens), style=_S.token_bold),
            _fmt_cost(s.cost_usd),
            str(s.message_count),
        ]
        table.add_row(*row)

    get_console().print(table)


def render_daily(stats: list[DailyStats], agents: list[str] | None = None) -> None:
    if not stats:
        get_console().print(f"[{_S.warn}]{t('no_data')}[/{_S.warn}]")
        return

    multi_agent = _is_multi_agent(stats)
    dates = {s.date for s in stats}
    total_tokens = sum(s.total_tokens for s in stats)
    total_cost = sum(s.cost_usd for s in stats)
    total_msgs = sum(s.message_count for s in stats)
    total_sessions = sum(s.session_count for s in stats)

    _render_header(agents or ["Claude Code"], total_tokens, total_cost, total_sessions, total_msgs, len(dates))
    _render_agent_summaries(stats, multi_agent)

    mode = _width_mode()
    table = Table(box=box.SIMPLE_HEAVY, header_style="bold", padding=(0, 1), expand=True)
    table.add_column(t("col_date"), style=_S.token, no_wrap=True)
    if multi_agent:
        table.add_column(t("col_source"), no_wrap=True)
    if mode != "compact":
        table.add_column("Input", justify="right")
        table.add_column("Output", justify="right")
    if mode == "wide":
        table.add_column("Cache", justify="right")
    table.add_column(t("col_total_tokens"), justify="right", style="bold")
    table.add_column(t("col_cost"), justify="right", style=_S.good)
    table.add_column(t("col_sessions"), justify="right", style=_S.dim)
    table.add_column(t("col_messages"), justify="right", style=_S.dim)

    max_tokens = max(s.total_tokens for s in stats) if stats else 1

    for s in stats:
        cache_total = s.cache_creation_tokens + s.cache_read_tokens
        row: list = [s.date]
        if multi_agent:
            row.append(AGENT_SHORT.get(s.agent_id, s.agent_id))
        if mode != "compact":
            row += [_fmt_tokens(s.input_tokens), _fmt_tokens(s.output_tokens)]
        if mode == "wide":
            row.append(_fmt_tokens(cache_total))
        row += [
            Text(_fmt_tokens(s.total_tokens), style=_token_heat_style(s.total_tokens / max_tokens)),
            _fmt_cost(s.cost_usd),
            str(s.session_count),
            str(s.message_count),
        ]
        table.add_row(*row)

    get_console().print(table)
    get_console().print()


def _render_weekly_table(stats: list[WeeklyStats], title: str | None = None) -> None:
    mode = _width_mode()
    table = Table(
        title=title, title_style="bold", box=box.SIMPLE_HEAVY,
        header_style="bold", padding=(0, 1), expand=True,
    )
    table.add_column(t("col_week"), style=_S.token, no_wrap=True)
    if mode != "compact":
        table.add_column("Input", justify="right")
        table.add_column("Output", justify="right")
    if mode == "wide":
        table.add_column("Cache", justify="right")
    table.add_column(t("col_total_tokens"), justify="right", style="bold")
    table.add_column(t("col_cost"), justify="right", style=_S.good)
    table.add_column(t("col_sessions"), justify="right", style=_S.dim)
    table.add_column(t("col_messages"), justify="right", style=_S.dim)

    max_tokens = max(s.total_tokens for s in stats) if stats else 1

    for s in stats:
        cache_total = s.cache_creation_tokens + s.cache_read_tokens
        week_label = f"{s.week_start} ~ {s.week_end}"
        row: list = [week_label]
        if mode != "compact":
            row += [_fmt_tokens(s.input_tokens), _fmt_tokens(s.output_tokens)]
        if mode == "wide":
            row.append(_fmt_tokens(cache_total))
        row += [
            Text(_fmt_tokens(s.total_tokens), style=_token_heat_style(s.total_tokens / max_tokens)),
            _fmt_cost(s.cost_usd),
            str(s.session_count),
            str(s.message_count),
        ]
        table.add_row(*row)

    table.add_section()
    total_row: list = [f"[bold]{t('total_row')}[/bold]"]
    if mode != "compact":
        total_row += [
            _fmt_tokens(sum(s.input_tokens for s in stats)),
            _fmt_tokens(sum(s.output_tokens for s in stats)),
        ]
    if mode == "wide":
        total_row.append(_fmt_tokens(sum(s.cache_creation_tokens + s.cache_read_tokens for s in stats)))
    total_row += [
        f"[{_S.token_bold}]{_fmt_tokens(sum(s.total_tokens for s in stats))}[/{_S.token_bold}]",
        f"[{_S.cost_bold}]{_fmt_cost(sum(s.cost_usd for s in stats))}[/{_S.cost_bold}]",
        str(sum(s.session_count for s in stats)),
        str(sum(s.message_count for s in stats)),
    ]
    table.add_row(*total_row)

    get_console().print(table)


def render_weekly(stats: list[WeeklyStats], agents: list[str] | None = None) -> None:
    if not stats:
        get_console().print(f"[{_S.warn}]{t('no_data')}[/{_S.warn}]")
        return

    multi_agent = _is_multi_agent(stats)
    weeks = {s.week for s in stats}
    total_tokens = sum(s.total_tokens for s in stats)
    total_cost = sum(s.cost_usd for s in stats)
    total_msgs = sum(s.message_count for s in stats)
    total_sessions = sum(s.session_count for s in stats)

    _render_header(agents or ["Claude Code"], total_tokens, total_cost, total_sessions, total_msgs, len(weeks) * 7)

    if multi_agent:
        for agent_id, group in sorted(_group_by_agent(stats).items()):
            _render_weekly_table(group, title=AGENT_LABEL.get(agent_id, agent_id))
    else:
        _render_weekly_table(stats)

    get_console().print()


def _render_monthly_table(stats: list[MonthlyStats], title: str | None = None) -> None:
    mode = _width_mode()
    table = Table(
        title=title, title_style="bold", box=box.SIMPLE_HEAVY,
        header_style="bold", padding=(0, 1), expand=True,
    )
    table.add_column(t("col_month"), style=_S.token, no_wrap=True)
    if mode != "compact":
        table.add_column("Input", justify="right")
        table.add_column("Output", justify="right")
    if mode == "wide":
        table.add_column(t("col_cache_create"), justify="right")
        table.add_column(t("col_cache_read"), justify="right")
    table.add_column(t("col_total_tokens"), justify="right", style="bold")
    table.add_column(t("col_cost"), justify="right", style=_S.good)
    table.add_column(t("col_sessions"), justify="right", style=_S.dim)
    table.add_column(t("col_messages"), justify="right", style=_S.dim)

    for s in stats:
        row: list = [s.month]
        if mode != "compact":
            row += [_fmt_tokens(s.input_tokens), _fmt_tokens(s.output_tokens)]
        if mode == "wide":
            row += [_fmt_tokens(s.cache_creation_tokens), _fmt_tokens(s.cache_read_tokens)]
        row += [
            _fmt_tokens(s.total_tokens),
            _fmt_cost(s.cost_usd),
            str(s.session_count),
            str(s.message_count),
        ]
        table.add_row(*row)

    table.add_section()
    total_row: list = [f"[bold]{t('total_row')}[/bold]"]
    if mode != "compact":
        total_row += [
            _fmt_tokens(sum(s.input_tokens for s in stats)),
            _fmt_tokens(sum(s.output_tokens for s in stats)),
        ]
    if mode == "wide":
        total_row += [
            _fmt_tokens(sum(s.cache_creation_tokens for s in stats)),
            _fmt_tokens(sum(s.cache_read_tokens for s in stats)),
        ]
    total_row += [
        f"[{_S.token_bold}]{_fmt_tokens(sum(s.total_tokens for s in stats))}[/{_S.token_bold}]",
        f"[{_S.cost_bold}]{_fmt_cost(sum(s.cost_usd for s in stats))}[/{_S.cost_bold}]",
        str(sum(s.session_count for s in stats)),
        str(sum(s.message_count for s in stats)),
    ]
    table.add_row(*total_row)

    get_console().print(table)


def render_monthly(stats: list[MonthlyStats], agents: list[str] | None = None) -> None:
    if not stats:
        get_console().print(f"[{_S.warn}]{t('no_data')}[/{_S.warn}]")
        return

    multi_agent = _is_multi_agent(stats)
    months = {s.month for s in stats}
    total_tokens = sum(s.total_tokens for s in stats)
    total_cost = sum(s.cost_usd for s in stats)
    total_msgs = sum(s.message_count for s in stats)
    total_sessions = sum(s.session_count for s in stats)
    days = len(months) * 30

    _render_header(agents or ["Claude Code"], total_tokens, total_cost, total_sessions, total_msgs, days)

    if multi_agent:
        for agent_id, group in sorted(_group_by_agent(stats).items()):
            _render_monthly_table(group, title=AGENT_LABEL.get(agent_id, agent_id))
    else:
        _render_monthly_table(stats)

    if len(stats) > 1:
        get_console().print()
        _render_model_breakdown(stats)

    get_console().print()


def _render_model_breakdown(stats: list[MonthlyStats]) -> None:
    all_models: dict[str, int] = {}
    for s in stats:
        for model, tokens in s.models.items():
            all_models[model] = all_models.get(model, 0) + tokens

    if not all_models:
        return

    total = sum(all_models.values())
    sorted_models = sorted(all_models.items(), key=lambda x: x[1], reverse=True)

    table = Table(
        title=t("model_breakdown"),
        box=box.SIMPLE,
        header_style="bold",
        padding=(0, 1),
        expand=True,
    )
    table.add_column(t("col_model"), style=_S.cost, no_wrap=True)
    table.add_column("Token", justify="right")
    table.add_column(t("col_ratio"), justify="right")
    table.add_column("", min_width=20)

    for model, tokens in sorted_models[:8]:
        pct = tokens / total * 100 if total > 0 else 0
        bar_width = int(pct / 100 * 20)
        bar_text = "█" * bar_width + "░" * (20 - bar_width)

        if pct > 50:
            bar_style = _S.token_bold
        elif pct > 20:
            bar_style = _S.blue
        else:
            bar_style = _S.dim

        table.add_row(
            _model_short(model),
            _fmt_tokens(tokens),
            f"{pct:.1f}%",
            Text(bar_text, style=bar_style),
        )

    get_console().print(table)


def render_sessions(stats: list[SessionStats], limit: int = 20) -> None:
    if not stats:
        get_console().print(f"[{_S.warn}]{t('no_data')}[/{_S.warn}]")
        return

    multi_agent = _is_multi_agent(stats)
    shown = stats[:limit]
    total_tokens = sum(s.total_tokens for s in shown)
    total_cost = sum(s.cost_usd for s in shown)

    get_console().print()
    get_console().print(Panel(
        f"[bold]Token Tracker[/bold]  {t('session_summary', shown=len(shown), total=len(stats))}  "
        f"Token: [{_S.token_bold}]{_fmt_tokens(total_tokens)}[/{_S.token_bold}]  "
        f"{t('cost_colon')}[{_S.cost_bold}]{_fmt_cost(total_cost)}[/{_S.cost_bold}]",
        border_style=_S.blue,
        padding=(0, 1),
    ))

    mode = _width_mode()
    table = Table(box=box.SIMPLE_HEAVY, header_style="bold", padding=(0, 1))
    table.add_column(t("col_time"), style=_S.token, no_wrap=True)
    if multi_agent:
        table.add_column(t("col_source"), no_wrap=True)
    table.add_column(t("col_project"), no_wrap=True, max_width=14)
    if mode != "compact":
        table.add_column(t("col_model"), style=_S.cost, no_wrap=True)
        table.add_column(t("col_duration"), justify="right")
    if mode == "wide":
        table.add_column("Input", justify="right")
        table.add_column("Output", justify="right")
    table.add_column(t("col_total_tokens"), justify="right", style="bold")
    table.add_column(t("col_cost"), justify="right", style=_S.good)
    table.add_column(t("col_messages"), justify="right", style=_S.dim)

    max_tokens = max(s.total_tokens for s in shown) if shown else 1

    for s in shown:
        row: list = [s.start_time.strftime("%m-%d %H:%M")]
        if multi_agent:
            row.append(AGENT_SHORT.get(s.agent_id, s.agent_id))
        row.append(_project_short(s.project))
        if mode != "compact":
            row += [_model_short(s.model), _fmt_duration(s.duration_minutes)]
        if mode == "wide":
            row += [_fmt_tokens(s.input_tokens), _fmt_tokens(s.output_tokens)]
        row += [
            Text(_fmt_tokens(s.total_tokens), style=_token_heat_style(s.total_tokens / max_tokens)),
            _fmt_cost(s.cost_usd),
            str(s.message_count),
        ]
        table.add_row(*row)

    get_console().print(table)
    get_console().print()
