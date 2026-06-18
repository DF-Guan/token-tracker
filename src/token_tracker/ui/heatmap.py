"""GitHub 贡献图风格的 daily token 热力图渲染。

替代原 daily 逐日表格：紧凑总览 + 月份表头 + 7 行（星期）× N 列（周）的深浅绿方格 + 图例。
彩色靠 forced_color_console() 强制 24-bit 输出，因此终端直跑与会话内 `!tt daily` 都能看到颜色。
每格 = 方块 ■ + 间隔空格（_CELL_W 显示宽），分离成方格；按终端宽度自适应周数、soft_wrap 避免折行。
总览自己渲染（不复用 dashboard 的宽 header），紧凑单行、半屏不折。
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from rich.console import Group
from rich.padding import Padding
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from ..adapters.types import DailyStats
from ..i18n import t
from .console import forced_color_console, get_console
from .format import _fmt_cost, _fmt_tokens, _model_short, brand_line, emit_metrics
from .theme import _S, HEAT_GREENS, _heat_level, _heat_thresholds

_WEEKS = 53
_CELL_W = 2  # 每格显示宽：方块(1) + 间隔(1)；■ 在多数终端按 1 列渲染
_DAY_LABELS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def render_daily_heatmap(stats: list[DailyStats], agents: list[str] | None = None,
                         hourly: dict[int, int] | None = None) -> None:
    if not stats:
        get_console().print(f"[{_S.warn}]{t('no_data')}[/{_S.warn}]")
        return

    # 按天合并 token
    tokens_by_date: dict[str, int] = {}
    for s in stats:
        tokens_by_date[s.date] = tokens_by_date.get(s.date, 0) + s.total_tokens

    with forced_color_console():
        _render_summary(stats, agents, hourly)
        _render_grid(tokens_by_date)
        _render_legend()


def _render_summary(stats: list[DailyStats], agents: list[str] | None,
                    hourly: dict[int, int] | None) -> None:
    today = datetime.now(UTC).date()
    year_ago = (today - timedelta(days=365)).isoformat()
    rows = [s for s in stats if s.date >= year_ago]  # 过去一年（与热力图范围一致）

    # 品牌行（Token Tracker + agent 暗红）+ 红分割线 + 过去一年汇总（同 weekly 顶部样式）
    brand = brand_line(agents or ["Claude Code"])

    avail = max(40, get_console().width - 6)  # 卡片可用内容宽 = 终端 - 缩进2 - 边框2 - padding2
    body = Text()
    body.append("Last 12 months", style=f"bold {_S.good}")
    body.append(f"  {year_ago} ~ {today.isoformat()}", style=f"dim {_S.good}")
    body.append("\n")
    days = len({s.date for s in rows})
    total_cost = sum(s.cost_usd for s in rows)
    # 第一行（橙）：Tokens / Cost / Sessions / Avg/Cost / Active Days（Avg/Cost = 总成本 ÷ 活跃天数）
    emit_metrics(body, [
        ("Tokens", _fmt_tokens(sum(s.total_tokens for s in rows))),
        ("Cost", _fmt_cost(total_cost)),
        ("Sessions", str(sum(s.session_count for s in rows))),
        ("Avg/Cost", _fmt_cost(total_cost / days if days else 0)),
        ("Active Days", str(days)),
    ], _S.peach, avail)
    body.append("\n")
    # 第二行（蓝）：单日峰值 token / 当前·最长连续活跃天数
    peak = max(rows, key=lambda s: s.total_tokens)
    dts = sorted(date.fromisoformat(d) for d in {s.date for s in rows})
    cur_streak = longest_streak = 1 if dts else 0
    for i in range(1, len(dts)):
        cur_streak = cur_streak + 1 if (dts[i] - dts[i - 1]).days == 1 else 1
        longest_streak = max(longest_streak, cur_streak)
    if dts and (today - dts[-1]).days > 1:  # 最近活跃日距今 > 1 天，当前连续已断
        cur_streak = 0
    emit_metrics(body, [
        ("Peak", f"{peak.date[5:]} ({_fmt_tokens(peak.total_tokens)})"),
        ("Current/Longest Streak", f"{cur_streak}/{longest_streak}d"),
    ], _S.blue, avail)
    body.append("\n")
    # 第三行（粉）：最忙星期几 / Top Model / 最活跃时段（按会话开始时间近似）
    wd_tokens: dict[int, int] = defaultdict(int)
    model_tokens: dict[str, int] = defaultdict(int)
    for s in rows:
        wd_tokens[date.fromisoformat(s.date).weekday()] += s.total_tokens
        for m, tk in s.models.items():
            model_tokens[m] += tk
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    busiest = weekdays[max(wd_tokens.items(), key=lambda x: x[1])[0]] if wd_tokens else "-"
    top_model = _model_short(max(model_tokens.items(), key=lambda x: x[1])[0]) if model_tokens else "-"
    rng = _active_hour_range(hourly or {})
    active = f"{rng[0]:02d}:00-{rng[1]:02d}:00" if rng else "-"
    emit_metrics(body, [
        ("Busiest", busiest), ("Top Model", top_model), ("Active Hour", active),
    ], _S.pink, avail)

    get_console().print(Padding(Panel(Group(brand, Rule(style=f"bold {_S.red}"), body),
                                      expand=False, border_style=_S.blue, padding=(0, 1)),
                                (0, 0, 0, 2), expand=False))
    get_console().print()


def _active_hour_range(hourly: dict[int, int]) -> tuple[int, int] | None:
    """从 24 小时 token 分布求活跃时段：以峰值 20% 为阈值取活跃小时，再用最长
    「非活跃」连续段（环形遍历两圈）的补集作为活跃区间，支持跨午夜（如 15:00-03:00）。"""
    if not hourly:
        return None
    threshold = max(hourly.values()) * 0.2
    active = [hourly.get(h, 0) >= threshold for h in range(24)]
    if all(active):
        return (0, 23)
    best_len = best_end = cur = 0
    for h in range(48):
        if not active[h % 24]:
            cur += 1
            if cur > best_len:
                best_len, best_end = cur, h % 24
        else:
            cur = 0
    gap_start = (best_end - min(best_len, 24) + 1) % 24
    return ((best_end + 1) % 24, (gap_start - 1) % 24)


def _display_weeks() -> int:
    """要显示的周数，右对齐只保留最近若干周。宽度交给 Rich console 判定（它依次读 tty
    尺寸、`COLUMNS`，都拿不到才回落 80）；装不下整年时砍掉最左（最老）的周、不折行。
    `!` 非 tty 或窄屏想多显示几周，可 `export COLUMNS=<列数>` 精确控制。"""
    width = get_console().width
    return max(8, min(_WEEKS, (width - 6) // _CELL_W))  # -6 = 缩进 2 + 星期标签列 4


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
    get_console().print(Text("      " + "".join(header).rstrip(), style=_S.dim), soft_wrap=True)

    # 7 行：星期标签 + 方块 + 间隔
    for r in range(7):
        line = Text("  ")
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
    get_console().print()
    line = Text()
    line.append(f"      {t('heat_less')} ", style=_S.dim)
    for color in HEAT_GREENS:
        line.append("■", style=color)
        line.append(" ")
    line.append(t("heat_more"), style=_S.dim)
    footer = "tt · by stormzhang"
    # 宽够把署名接图例右边（空 4 格）；窄了另起一行（缩进 2），避免终端硬折导致折行 + 掉色
    if line.cell_len + 4 + len(footer) <= get_console().width:
        line.append("    " + footer, style=_S.dim)
        get_console().print(line, soft_wrap=True)
    else:
        get_console().print(line, soft_wrap=True)
        get_console().print()                       # 空一行
        get_console().print(Text("      " + footer, style=_S.dim))  # 缩进 6 对齐 Less
