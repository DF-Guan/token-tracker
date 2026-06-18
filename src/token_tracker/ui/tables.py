"""表格渲染（daily/weekly/monthly/sessions/模型分布）与 dashboard 编排。

格式化/主题/小部件/面板已拆到 format.py / theme.py / widgets.py / panels.py；
本模块聚焦各类表格与把它们组装成 dashboard。
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from rich import box
from rich.console import Group
from rich.padding import Padding
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from ..adapters.types import DailyStats, MonthlyStats, P90Limits, RateLimits, SessionBlock, SessionStats, WeeklyStats
from ..i18n import t
from .console import forced_color_console, get_console
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


def render_weekly(stats: list[WeeklyStats], agents: list[str] | None = None,
                  daily: list[DailyStats] | None = None) -> None:
    if not stats:
        get_console().print(f"[{_S.warn}]{t('no_data')}[/{_S.warn}]")
        return

    weeks = _merge_weeks(stats)
    cur = weeks[-1]
    prev = weeks[-2] if len(weeks) >= 2 else None

    with forced_color_console():
        active_days = len({d.date for d in daily if d.date >= cur.week}) if daily else 0
        _render_week_summary(cur, prev, agents or ["Claude Code"], active_days)
        if daily:
            by_date: dict[str, int] = {}
            for d in daily:
                by_date[d.date] = by_date.get(d.date, 0) + d.total_tokens
            _render_daily_barchart(by_date)
        _render_weekly_trend(weeks)
        _render_distribution("Project Trend", "Project", cur.projects, _project_short, _S.pink)
        _render_distribution("Model Trend", "Model", cur.models, _model_short, _S.blue)
        get_console().print(Text("  tt · by stormzhang", style=_S.dim))


def _render_daily_barchart(by_date: dict[str, int], days_back: int = 30, height: int = 6) -> None:
    """最近 days_back 天的每日 token 垂直柱状图（▁-█ sub-cell 精度，列间留白）；
    峰值柱子上方标其日期，底部两端标起止日期。"""
    today = datetime.now(UTC).date()
    dates = [today - timedelta(days=i) for i in range(days_back - 1, -1, -1)]
    vals = [by_date.get(d.isoformat(), 0) for d in dates]
    max_v = max(vals) or 1
    blocks = " ▁▂▃▄▅▆▇█"
    heights = [v / max_v * height for v in vals]
    width = len(dates) * 2 - 1  # 每天 1 字符 + 1 间隔

    title = Text()
    title.append("[Daily Trend]", style=f"bold {_S.peach}")
    title.append(" (last 30d)", style=f"dim {_S.peach}")
    lines: list[Text] = [title, Text()]
    peak_idx = vals.index(max(vals))
    peak_label = dates[peak_idx].strftime("%m/%d")
    top = [" "] * width
    pos = max(0, min(width - len(peak_label), peak_idx * 2 - len(peak_label) // 2))
    for j, ch in enumerate(peak_label):
        top[pos + j] = ch
    lines.append(Text("".join(top), style=_S.peach))
    top3 = set(sorted(range(len(vals)), key=lambda i: vals[i], reverse=True)[:3])
    for row in range(height, 0, -1):
        line = Text()
        for i, h in enumerate(heights):
            diff = h - (row - 1)
            ch = "█" if diff >= 1 else " " if diff <= 0 else blocks[round(diff * 8)]
            line.append(ch, style=_S.peach if i in top3 else f"dim {_S.peach}")
            if i < len(heights) - 1:
                line.append(" ")
        lines.append(line)
    start, end = dates[0].strftime("%m/%d"), dates[-1].strftime("%m/%d")
    gap = max(1, width - len(start) - len(end))
    lines.append(Text(start + " " * gap + end, style=_S.dim))
    get_console().print(Padding(Group(*lines), (0, 0, 0, 2), expand=False))
    get_console().print()


def _merge_weeks(stats: list[WeeklyStats]) -> list[WeeklyStats]:
    """跨 agent 合并同一周（多 agent 时每周多条），按周升序返回。"""
    merged: dict[str, WeeklyStats] = {}
    for s in stats:
        m = merged.get(s.week)
        if m is None:
            m = merged[s.week] = WeeklyStats(week=s.week, week_start=s.week_start, week_end=s.week_end)
        m.input_tokens += s.input_tokens
        m.output_tokens += s.output_tokens
        m.cache_creation_tokens += s.cache_creation_tokens
        m.cache_read_tokens += s.cache_read_tokens
        m.total_tokens += s.total_tokens
        m.cost_usd += s.cost_usd
        m.session_count += s.session_count
        m.message_count += s.message_count
        for k, v in s.models.items():
            m.models[k] = m.models.get(k, 0) + v
        for k, v in s.projects.items():
            m.projects[k] = m.projects.get(k, 0) + v
    return [merged[k] for k in sorted(merged)]


def _darken(color: str, factor: float = 0.6) -> str:
    """把 #RRGGBB 按 factor 压暗（保持色相），用于突出排第一的项。"""
    h = color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"


def _bar_text(ratio: float, fill_style: str, width: int = 20) -> Text:
    """半高进度条（▄ 仅占行下半，相邻行天然空半行）：填充用 fill_style、
    空槽用同色 dim 版（同色深浅对比，仿 daily 方格）。"""
    filled = round(max(0.0, min(1.0, ratio)) * width)
    t = Text()
    t.append("▄" * filled, style=fill_style)
    t.append("▄" * (width - filled), style=f"dim {fill_style}")
    return t


def _append_metric(body: Text, label: str, value: str, color: str,
                   cur_val: float, prev_val: float | None) -> None:
    body.append(f"{label}: ", style=color)
    body.append(value, style=f"bold {color}")
    if prev_val and prev_val > 0:
        pct = (cur_val - prev_val) / prev_val * 100
        body.append(f" ({'↑' if pct >= 0 else '↓'}{abs(pct):.0f}%)", style=f"dim {color}")


def _render_week_summary(cur: WeeklyStats, prev: WeeklyStats | None, agents: list[str],
                         active_days: int) -> None:
    """本周分析卡片：品牌行 + 分割线 + 本周区间；第二行 Tokens/Cost/Avg·Cost（橙）、
    第三行 Sessions/Msgs/Active Days（蓝），带环比上周。Avg/Cost = 本周成本 ÷ 已过天数（日均）。"""
    brand = Text()
    brand.append("Token Tracker", style=f"bold {_S.red}")
    brand.append(": ", style=f"bold {_S.red}")
    for i, a in enumerate(agents):
        if i:
            brand.append(" + ", style=f"dim {_S.red}")
        brand.append(a, style=f"dim {_S.red}")

    body = Text()
    body.append("This Week", style=f"bold {_S.good}")
    body.append(f"  {cur.week_start} ~ {cur.week_end}", style=f"dim {_S.good}")
    body.append("\n")
    this_monday = datetime.fromisoformat(cur.week).date()
    days = max(1, min(7, (datetime.now(UTC).date() - this_monday).days + 1))
    cur_avg = cur.cost_usd / days
    prev_avg = prev.cost_usd / 7 if prev else None
    # 第二行（橙）：Tokens / Cost / Avg/Cost（日均花费）
    _append_metric(body, "Tokens", _fmt_tokens(cur.total_tokens), _S.peach,
                   cur.total_tokens, prev.total_tokens if prev else None)
    body.append("   ")
    _append_metric(body, "Cost", _fmt_cost(cur.cost_usd), _S.peach,
                   cur.cost_usd, prev.cost_usd if prev else None)
    body.append("   ")
    _append_metric(body, "Avg/Cost", _fmt_cost(cur_avg), _S.peach, cur_avg, prev_avg)
    body.append("\n")
    # 第三行（粉）：Sessions / Msgs
    _append_metric(body, "Sessions", str(cur.session_count), _S.blue,
                   cur.session_count, prev.session_count if prev else None)
    body.append("   ")
    _append_metric(body, "Msgs", str(cur.message_count), _S.blue,
                   cur.message_count, prev.message_count if prev else None)
    body.append("   ")
    _append_metric(body, "Active Days", f"{active_days}/7", _S.blue, active_days, None)
    get_console().print(Panel(Group(brand, Rule(style=f"bold {_S.red}"), body),
                              expand=False, border_style=_S.blue, padding=(0, 1)))
    get_console().print()


def _render_weekly_trend(weeks: list[WeeklyStats], limit: int = 8) -> None:
    """逐周 token 进度条（最近若干周，最新在上、本周高亮绿）。"""
    recent = weeks[-limit:]
    max_tok = max((w.total_tokens for w in recent), default=0) or 1
    cur_week = weeks[-1].week
    table = Table(title=Text("[Weekly Trend]", style=f"bold {_S.good}"), title_justify="left", box=box.SIMPLE,
                  header_style="bold", padding=(0, 1), expand=False, border_style=_S.good)
    table.add_column("Week", style=_S.good, no_wrap=True)
    table.add_column("Token", justify="right")
    table.add_column("", min_width=20)
    for w in reversed(recent):
        is_cur = w.week == cur_week
        table.add_row(
            Text(f"{w.week_start} ~ {w.week_end}", style="bold" if is_cur else ""),
            _fmt_tokens(w.total_tokens),
            _bar_text(w.total_tokens / max_tok, _S.good if is_cur else _darken(_S.good)),
        )
    get_console().print(Padding(table, (0, 0, 0, 2), expand=False))


def _render_distribution(title: str, name_col: str, data: dict[str, int],
                         short_fn: Callable[[str], str], accent: str) -> None:
    """通用分布表（Project / Model）：标题、名称列、进度条统一用模块主色 accent，
    按 token 降序取前 8；Token/Ratio 数值保持中性。"""
    if not data:
        return
    total = sum(data.values())
    items = sorted(data.items(), key=lambda x: x[1], reverse=True)
    table = Table(title=Text(f"[{title}]", style=f"bold {accent}"), title_justify="left", box=box.SIMPLE,
                  header_style="bold", padding=(0, 1), expand=False, border_style=accent)
    table.add_column(name_col, style=accent, no_wrap=True)
    table.add_column("Token", justify="right")
    table.add_column("", min_width=20)
    table.add_column("", justify="right", style=f"dim {accent}")
    for idx, (name, tokens) in enumerate(items[:8]):
        pct = tokens / total * 100 if total else 0
        fill = accent if idx == 0 else _darken(accent)
        table.add_row(short_fn(name), _fmt_tokens(tokens),
                      _bar_text(pct / 100, fill), f"{pct:.1f}%")
    get_console().print(Padding(table, (0, 0, 0, 2), expand=False))


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
