"""GitHub 贡献图风格的 daily token 热力图渲染。

替代原 daily 逐日表格：紧凑总览 + 月份表头 + 7 行（星期）× N 列（周）的深浅绿方格 + 图例。
彩色靠 forced_color_console() 强制 24-bit 输出，因此终端直跑与会话内 `!tt daily` 都能看到颜色。
每格 = 方块 ■ + 间隔空格（_CELL_W 显示宽），分离成方格；按终端宽度自适应周数、soft_wrap 避免折行。
总览自己渲染（不复用 dashboard 的宽 header），紧凑单行、半屏不折。
"""

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
    today = datetime.now(UTC).date()
    this_sunday = (today - timedelta(days=(today.weekday() + 1) % 7)).isoformat()
    week = [s for s in stats if s.date >= this_sunday]

    body = Text()
    # 标题行
    body.append("Token Tracker", style=f"bold {_S.red}")
    body.append(": ", style=_S.dim)
    for i, a in enumerate(agents or ["Claude Code"]):
        if i:
            body.append(" + ", style=_S.dim)
        body.append(a, style="bold")
    body.append("\n")
    # 总计行 + 本周行（本周日起至今）
    _append_stat_row(body, "Overview", stats)
    body.append("\n")
    _append_stat_row(body, "This Week", week)

    # 紧凑框（expand=False 贴合内容、不撑满）框住整个总览
    get_console().print(Panel(body, expand=False, border_style=_S.blue, padding=(0, 1)))
    get_console().print()


def _append_stat_row(body: Text, label: str, rows: list[DailyStats]) -> None:
    """向 body 追加一行：行首标签 + Tokens/Cost/Sessions/Days，每项标签与值同色
    （Tokens 粉 / Cost 黄 / Sessions 紫 / Days 橙），值加粗、标签常规，项间用灰 | 分隔（同 statusline）；行首标签绿。"""
    sep = " | "
    body.append(f"{label}:".ljust(11), style=f"bold {_S.good}")
    body.append("Tokens: ", style=_S.pink)
    body.append(_fmt_tokens(sum(s.total_tokens for s in rows)), style=f"bold {_S.pink}")
    body.append(sep, style=_S.dim)
    body.append("Cost: ", style=_S.cost)
    body.append(_fmt_cost(sum(s.cost_usd for s in rows)), style=_S.cost_bold)
    body.append(sep, style=_S.dim)
    body.append("Sessions: ", style=_S.mauve)
    body.append(str(sum(s.session_count for s in rows)), style=f"bold {_S.mauve}")
    body.append(sep, style=_S.dim)
    body.append("Days: ", style=_S.peach)
    body.append(str(len({s.date for s in rows})), style=f"bold {_S.peach}")


def _display_weeks() -> int:
    """要显示的周数，右对齐只保留最近若干周。宽度交给 Rich console 判定（它依次读 tty
    尺寸、`COLUMNS`，都拿不到才回落 80）；装不下整年时砍掉最左（最老）的周、不折行。
    `!` 非 tty 或窄屏想多显示几周，可 `export COLUMNS=<列数>` 精确控制。"""
    width = get_console().width
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
