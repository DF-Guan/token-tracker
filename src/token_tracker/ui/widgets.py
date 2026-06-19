"""构建到 Rich Text 上的小部件：进度条、趋势箭头、限额条、周区块。"""

from datetime import UTC, datetime

from rich.text import Text

from ..adapters.types import WeeklyStats
from ..i18n import t
from .format import _fmt_cost, _fmt_tokens, system_tz
from .theme import _S


def _append_bar(lines: Text, label: str, pct: float,
                bar_width: int, suffix: str = "") -> None:
    filled = int(pct / 100 * bar_width)
    bar = "█" * filled + "░" * (bar_width - filled)
    bar_style = _S.bar_high if pct > 80 else _S.bar_mid if pct > 50 else _S.bar_low
    lines.append(label, style=_S.dim)
    lines.append(bar, style=bar_style)
    lines.append(f"  {pct:.0f}%", style=bar_style)
    if suffix:
        lines.append(suffix, style=_S.dim)
    lines.append("\n")


def _append_trend(lines: Text, current: float, previous: float) -> None:
    arrow = "↑" if current >= previous else "↓"
    style = _S.bad if current >= previous else _S.good
    lines.append(f"{arrow}", style=style)


def _render_rate_bar(lines: Text, label: str, pct: float,
                     resets_at: int | None, bar_width: int,
                     date_fmt: str = "%H:%M") -> None:
    reset_suffix = ""
    if resets_at:
        reset_dt = datetime.fromtimestamp(resets_at, tz=system_tz())
        reset_suffix = f"  {t('reset_at', time=reset_dt.strftime(date_fmt))}"
    _append_bar(lines, f"  {label}    ", pct, bar_width, reset_suffix)


def _render_week_section(lines: Text, week: WeeklyStats,
                         last_week: WeeklyStats | None = None) -> None:
    now = datetime.now(UTC)
    elapsed_days = now.weekday() + 1
    daily_avg_cost = week.cost_usd / elapsed_days if elapsed_days > 0 else 0
    lines.append(f"  Token     {_fmt_tokens(week.total_tokens)}", style=_S.token)
    if last_week:
        _append_trend(lines, week.total_tokens, last_week.total_tokens)
    lines.append(f"  Output: {_fmt_tokens(week.output_tokens)}", style=_S.dim)
    lines.append(f"  {t('rate_per_day', rate=_fmt_tokens(week.total_tokens // elapsed_days))}\n", style=_S.dim)
    lines.append(f"  {t('cost_label')}  {_fmt_cost(week.cost_usd)}", style=_S.cost)
    lines.append(f"  {t('daily_avg', cost=_fmt_cost(daily_avg_cost))}", style=_S.dim)
    lines.append("\n")
    lines.append(f"  {t('msg_session', msgs=week.message_count, sessions=week.session_count)}", style=_S.dim)
