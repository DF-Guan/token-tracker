"""GitHub 贡献图风格的 daily token 热力图渲染。

替代原 daily 逐日表格：紧凑总览 + 月份表头 + 7 行（星期）× N 列（周）的深浅绿方格 + 图例。
彩色靠 forced_color_console() 强制 24-bit 输出，因此终端直跑与会话内 `!tt daily` 都能看到颜色。
每格 = 方块 ■ + 间隔空格（_CELL_W 显示宽），分离成方格；按终端宽度自适应周数、soft_wrap 避免折行。
总览自己渲染（不复用 dashboard 的宽 header），紧凑单行、半屏不折。
"""

import os
from datetime import UTC, datetime, timedelta

from rich.panel import Panel
from rich.text import Text

from ..adapters.types import DailyStats
from ..i18n import t
from .console import forced_color_console, get_console
from .format import _fmt_cost, _fmt_tokens
from .theme import _S, HEAT_GREENS, _heat_level, _heat_thresholds

_WEEKS = 53
_CELL_W = 2  # 每格显示宽：方块(1) + 间隔(1)；■ 在多数终端按 1 列渲染
_DAY_LABELS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def render_daily_heatmap(stats: list[DailyStats], agents: list[str] | None = None) -> None:
    if not stats:
        get_console().print(f"[{_S.warn}]{t('no_data')}[/{_S.warn}]")
        return

    # 按天合并 token
    tokens_by_date: dict[str, int] = {}
    for s in stats:
        tokens_by_date[s.date] = tokens_by_date.get(s.date, 0) + s.total_tokens

    with forced_color_console():
        _render_summary(stats, agents)
        _render_grid(tokens_by_date)
        _render_legend()


def _render_summary(stats: list[DailyStats], agents: list[str] | None) -> None:
    total_tokens = sum(s.total_tokens for s in stats)
    total_cost = sum(s.cost_usd for s in stats)
    total_msgs = sum(s.message_count for s in stats)
    total_sessions = sum(s.session_count for s in stats)
    days = len({s.date for s in stats})

    body = Text()
    # 标题行
    body.append("Token Tracker", style="bold")
    for a in agents or ["Claude Code"]:
        body.append("  ● ", style=_S.good)
        body.append(a, style="bold")
    body.append("\n")
    # 数据行：每项带前置标签、· 分隔，明确各数值含义
    body.append("Tokens ", style=_S.dim)
    body.append(_fmt_tokens(total_tokens), style=_S.token_bold)
    body.append(" · Cost ", style=_S.dim)
    body.append(_fmt_cost(total_cost), style=_S.cost_bold)
    body.append(f" · Sessions {total_sessions} · Msgs {total_msgs} · Days {days}", style=_S.dim)

    # 紧凑框（expand=False 贴合内容、不撑满）框住整个总览
    get_console().print(Panel(body, expand=False, border_style="blue", padding=(0, 1)))
    get_console().print()


def _display_weeks() -> int:
    """要显示的周数。优先按真实终端宽度自适应；拿不到宽度时（Claude Code `!` 等非 tty
    且无 COLUMNS）默认显示整年——全屏够宽即可，窄屏可 `export COLUMNS` 精确自适应。"""
    cols = os.environ.get("COLUMNS")
    width = int(cols) if cols and cols.isdigit() else None
    if width is None:
        for fd in (2, 1, 0):
            try:
                width = os.get_terminal_size(fd).columns
                break
            except OSError:
                continue
    if width is None:
        return _WEEKS
    return max(8, min(_WEEKS, (width - 4) // _CELL_W))


def _render_grid(tokens_by_date: dict[str, int]) -> None:
    today = datetime.now(UTC).date()
    days_since_sunday = (today.weekday() + 1) % 7  # Mon=0→1 … Sun=6→0
    this_sunday = today - timedelta(days=days_since_sunday)

    weeks = _display_weeks()
    start_sunday = this_sunday - timedelta(weeks=weeks - 1)

    thresholds = _heat_thresholds(list(tokens_by_date.values()))

    # 月份表头：每列 _CELL_W 显示宽，在月份变化处标月名缩写。
    # prev_month 预设为首列月 → 跳过左端不完整的部分月；last_end 保证月名间留间隔。
    header = [" "] * (weeks * _CELL_W)
    prev_month = start_sunday.month
    last_end = -1
    for c in range(weeks):
        col_day = start_sunday + timedelta(weeks=c)
        if col_day.month != prev_month:
            prev_month = col_day.month
            if c > last_end:
                for i, ch in enumerate(_MONTHS[col_day.month]):
                    if c * _CELL_W + i < len(header):
                        header[c * _CELL_W + i] = ch
                last_end = c + 1
    get_console().print(Text("    " + "".join(header).rstrip(), style=_S.dim), soft_wrap=True)

    # 7 行：星期标签 + 方块 + 间隔
    for r in range(7):
        line = Text()
        line.append(f"{_DAY_LABELS[r]}  ", style=_S.dim)
        for c in range(weeks):
            d = start_sunday + timedelta(weeks=c, days=r)
            if d > today:
                line.append(" " * _CELL_W)  # 未来日期占位（保持列对齐）
                continue
            level = _heat_level(tokens_by_date.get(d.isoformat(), 0), thresholds)
            line.append("■", style=HEAT_GREENS[level])
            line.append(" ")  # 格子间隔
        get_console().print(line, soft_wrap=True)


def _render_legend() -> None:
    line = Text()
    line.append(f"\n    {t('heat_less')} ", style=_S.dim)
    for color in HEAT_GREENS:
        line.append("■", style=color)
        line.append(" ")
    line.append(t("heat_more"), style=_S.dim)
    get_console().print(line, soft_wrap=True)
