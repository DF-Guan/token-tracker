"""tt status 面板：过去 5h 合并概览 + 额度/per-agent 统计 + 合并 session 列表。

配色跟随当前主题（`_S` 运行时代理）；头图仿 daily 品牌面板，额度条仿 weekly trend 样式。
"""

from datetime import datetime, timedelta

from rich import box
from rich.console import Group
from rich.padding import Padding
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from ..i18n import t
from .console import forced_color_console, get_console
from .format import (
    AGENT_LABEL,
    AGENT_SHORT,
    _fmt_cost,
    _fmt_duration,
    _fmt_tokens,
    _model_short,
    _project_short,
    _width_mode,
    brand_line,
    emit_metrics,
    system_tz,
)
from .tables import _bar_text
from .theme import _S, _pct_style


def render_status(summary, per_agent, rate_limits, sessions, agents) -> None:
    """三段：合并头图概览；有订阅额度→额度条，否则→per-agent 统计；合并 session 列表。"""
    with forced_color_console():
        _render_summary(summary, agents)
        if rate_limits:
            _render_limits(rate_limits)
        else:
            _render_agent_stats(per_agent)
        if sessions:
            _render_sessions(sessions)
        get_console().print()


def _render_summary(summary, agents: list[str]) -> None:
    """头图品牌面板：仿 daily `_render_summary`，数据是过去 5h 多 agent 合并汇总。"""
    now = datetime.now(system_tz())  # 系统真实时区（绕过 CLI 的 TZ）
    start = now - timedelta(hours=5)
    brand = brand_line(agents)
    avail = max(40, get_console().width - 6)
    body = Text()
    body.append("Last 5 hours", style=f"bold {_S.good}")
    body.append(f"  {start.strftime('%H:%M')} ~ {now.strftime('%H:%M')}", style=f"dim {_S.good}")
    body.append("\n")
    metrics = [
        ("Tokens", _fmt_tokens(summary.total_tokens)),
        ("Cost", _fmt_cost(summary.cost_usd)),
        ("Sessions", str(summary.session_count)),
        ("Messages", str(summary.message_count)),
    ]
    if summary.models:
        metrics.append(("Top Model", _model_short(max(summary.models, key=lambda m: summary.models[m]))))
    emit_metrics(body, metrics, _S.peach, avail)
    get_console().print(Padding(Panel(Group(brand, Rule(style=f"bold {_S.red}"), body),
                                      expand=False, border_style=_S.blue, padding=(0, 1)),
                                (0, 0, 0, 2), expand=False))
    get_console().print()


def _render_limits(rate_limits: dict) -> None:
    """订阅额度（weekly trend 样式横条）：每 agent 的 5h/7d，进度条按用量百分比着色。"""
    table = Table(title=Text("[Rate Limits]", style=f"bold {_S.good}"), title_justify="left",
                  box=box.SIMPLE, header_style="bold", padding=(0, 1), expand=False, border_style=_S.good)
    table.add_column("Window", style=_S.good, no_wrap=True)
    table.add_column("Used", justify="right")
    table.add_column("", min_width=20)
    table.add_column("Resets", justify="right", style=_S.dim)
    for agent_id, rl in rate_limits.items():
        short = AGENT_SHORT.get(agent_id, agent_id)
        for label, pct, resets in (("5h", rl.five_hour_pct, rl.five_hour_resets_at),
                                   ("7d", rl.seven_day_pct, rl.seven_day_resets_at)):
            if pct is None:
                continue
            reset_str = datetime.fromtimestamp(resets, tz=system_tz()).strftime("%H:%M") if resets else ""
            table.add_row(f"{short} {label}", f"{pct:.0f}%", _bar_text(pct / 100, _pct_style(pct)), reset_str)
    get_console().print(Padding(table, (0, 0, 0, 2), expand=False))
    get_console().print()


def _render_agent_stats(per_agent: dict) -> None:
    """都没订阅额度时（API 模式等）：每个 agent 过去 5h 的 token/cost/sessions/messages。"""
    rows = [(aid, s) for aid, s in per_agent.items() if s.total_tokens or s.message_count]
    if not rows:
        return
    table = Table(title=Text("[Last 5h by Agent]", style=f"bold {_S.peach}"), title_justify="left",
                  box=box.SIMPLE, header_style="bold", padding=(0, 1), expand=False, border_style=_S.peach)
    table.add_column("Agent", style=_S.peach, no_wrap=True)
    table.add_column("Tokens", justify="right", style=_S.token_bold)
    table.add_column("Cost", justify="right", style=_S.good)
    table.add_column("Sessions", justify="right", style=_S.dim)
    table.add_column("Messages", justify="right", style=_S.dim)
    for agent_id, s in rows:
        table.add_row(AGENT_LABEL.get(agent_id, agent_id), _fmt_tokens(s.total_tokens),
                      _fmt_cost(s.cost_usd), str(s.session_count), str(s.message_count))
    get_console().print(Padding(table, (0, 0, 0, 2), expand=False))
    get_console().print()


def _render_sessions(sessions) -> None:
    """合并 session 列表：强制 Agent 列、加 Duration / Total tokens；按 cost 倒序、前三名 cost 高亮。"""
    mode = _width_mode()
    table = Table(title=t("recent_sessions"), box=box.SIMPLE_HEAVY, header_style="bold",
                  padding=(0, 1), expand=False)
    table.add_column(t("col_time"), style=_S.token, no_wrap=True)
    table.add_column(t("col_agent"), no_wrap=True)
    table.add_column(t("col_project"), no_wrap=True, max_width=14)
    if mode != "compact":
        table.add_column(t("col_model"), style=_S.cost, no_wrap=True)
    table.add_column(t("col_duration"), justify="right")
    table.add_column(t("col_total_tokens"), justify="right", style=_S.token_bold)
    table.add_column(t("col_cost"), justify="right", style=_S.good)
    table.add_column(t("col_messages"), justify="right", style=_S.dim)
    # cost 前三名用不同色突出（top1 红 / top2 橙 / top3 黄）
    top_styles = (f"bold {_S.bad}", f"bold {_S.peach}", f"bold {_S.warn}")
    for idx, s in enumerate(sessions):
        row: list = [s.start_time.astimezone(system_tz()).strftime("%m-%d %H:%M"),
                     AGENT_SHORT.get(s.agent_id, s.agent_id), _project_short(s.project)]
        if mode != "compact":
            row.append(_model_short(s.model))
        cost_cell = Text(_fmt_cost(s.cost_usd), style=top_styles[idx]) if idx < 3 else _fmt_cost(s.cost_usd)
        row += [
            _fmt_duration(s.duration_minutes),
            Text(_fmt_tokens(s.total_tokens), style=_S.token_bold),
            cost_cell,
            str(s.message_count),
        ]
        table.add_row(*row)
    get_console().print(Padding(table, (0, 0, 0, 2), expand=False))
