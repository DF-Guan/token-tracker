import os
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from rich.text import Text

from . import config
from .adapters import claude, codex
from .adapters.rate_limits import load_rate_limits as load_claude_rate_limits
from .adapters.registry import detect_agents
from .adapters.types import StatusSummary
from .analyzer.aggregator import (
    add_token_fields,
    aggregate_daily,
    aggregate_monthly,
    aggregate_sessions,
    aggregate_weekly,
)
from .analyzer.cost import calculate_cost
from .hooks import is_setup, needs_update, setup, unsetup, update_hook
from .i18n import t
from .ui import theme, themes
from .ui.console import forced_color_console, get_console
from .ui.format import system_tz
from .ui.heatmap import render_daily_heatmap
from .ui.status import render_status
from .ui.tables import (
    render_monthly,
    render_sessions,
    render_weekly,
)

AGENT_LOADERS = {"claude-code": claude, "codex": codex}
RATE_LIMIT_LOADERS = {"claude-code": load_claude_rate_limits, "codex": codex.load_rate_limits}

# status 面板的时间窗口：过去 5 小时
_STATUS_HOURS = 5

# 排序字段 → stats 属性名（单一权威表）。
# "time" 的属性因命令而异（daily=date / weekly=week / sessions=start_time），不在此表，走 default_attr。
SORT_ATTRS = {
    "tokens": "total_tokens",
    "cost": "cost_usd",
    "messages": "message_count",
    "sessions": "session_count",
    "input": "input_tokens",
    "output": "output_tokens",
}
VALID_SORT_KEYS = (*SORT_ATTRS.keys(), "time")


# 数据报表命令分发表：命令 → (聚合函数, 渲染函数, time 排序的属性, 无 --sort 时的默认属性, 默认降序)
# time_attr 与 no_sort_attr 仅 daily 不同（默认按 token 排，--sort time 才按日期）
_REPORT_COMMANDS = {
    "daily": (aggregate_daily, render_daily_heatmap, "date", "total_tokens", True),
    "weekly": (aggregate_weekly, render_weekly, "week", "week", True),
    "monthly": (aggregate_monthly, render_monthly, "month", "month", False),
    "sessions": (aggregate_sessions, render_sessions, "start_time", "start_time", True),
}


def _parse_limit(args: list[str], default: int) -> int:
    for a in args:
        try:
            return int(a)
        except ValueError:
            pass
    return default


def _parse_sort_args(args: list[str]) -> tuple[list[str], str | None, bool]:
    """Extract --sort KEY and --asc from args, return (remaining, sort_key, descending)."""
    remaining = []
    sort_key = None
    descending = True
    i = 0
    while i < len(args):
        if args[i] == "--sort" and i + 1 < len(args):
            sort_key = args[i + 1].lower()
            i += 2
        elif args[i] == "--asc":
            descending = False
            i += 1
        elif args[i] == "--desc":
            descending = True
            i += 1
        else:
            remaining.append(args[i])
            i += 1
    return remaining, sort_key, descending


def _apply_sort(stats, sort_key: str | None, descending: bool, default_attr: str, default_reverse: bool):
    if sort_key is None:
        stats.sort(key=lambda s: getattr(s, default_attr), reverse=default_reverse)
        return
    if sort_key not in VALID_SORT_KEYS:
        valid = ", ".join(VALID_SORT_KEYS)
        get_console().print(f"[yellow]{t('unknown_sort_field', key=sort_key, valid=valid)}[/yellow]")
        stats.sort(key=lambda s: getattr(s, default_attr), reverse=default_reverse)
        return
    # "time" 不在 SORT_ATTRS → 退回 default_attr（各命令的时间字段）
    attr = SORT_ATTRS.get(sort_key, default_attr)
    stats.sort(key=lambda s: getattr(s, attr), reverse=descending)


def _load_entries(agent_id: str, hours_back: int = 0):
    loader = AGENT_LOADERS.get(agent_id)
    return loader.load_entries(hours_back=hours_back) if loader else []


def _aggregate_per_agent(agents, agg_fn):
    stats = []
    for a in agents:
        entries = _load_entries(a.id)
        for s in agg_fn(entries):
            s.agent_id = a.id
            stats.append(s)
    return stats


def _build_status_data(agents) -> dict | None:
    """过去 5h status 数据：合并汇总 + per-agent 汇总 + 分 agent 额度 + 合并 session（按 cost 倒序）。

    session 列表过滤掉 5min 以下的短会话；Sessions 计数也只算够时长的会话。
    """
    summary = StatusSummary()
    per_agent: dict = {}
    sessions = []
    rate_limits: dict = {}
    for a in agents:
        entries = _load_entries(a.id, hours_back=_STATUS_HOURS)
        a_sum = StatusSummary()
        for e in entries:
            cost = calculate_cost(e)
            add_token_fields(summary, e, cost)
            add_token_fields(a_sum, e, cost)
            summary.message_count += e.message_count
            a_sum.message_count += e.message_count
            summary.models[e.model] = summary.models.get(e.model, 0) + e.total_tokens
        a_sessions = [s for s in aggregate_sessions(entries) if s.duration_minutes >= 5]
        for s in a_sessions:
            s.agent_id = a.id
        a_sum.session_count = len(a_sessions)
        per_agent[a.id] = a_sum
        sessions.extend(a_sessions)
        rl = RATE_LIMIT_LOADERS.get(a.id, lambda: None)()
        if rl and (rl.five_hour_pct is not None or rl.seven_day_pct is not None):
            rate_limits[a.id] = rl
    if not sessions and summary.total_tokens == 0:
        return None
    summary.session_count = len(sessions)
    sessions.sort(key=lambda s: s.cost_usd, reverse=True)
    return dict(summary=summary, per_agent=per_agent, rate_limits=rate_limits,
                sessions=sessions, agents=[a.name for a in agents])


def _current_session_agent() -> str | None:
    """识别当前所在的 agent 会话（靠环境变量）：Codex / Claude Code；独立终端返回 None。"""
    if os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_SANDBOX"):
        return "codex"
    if os.environ.get("CLAUDE_CONFIG_DIR") or os.environ.get("CLAUDECODE"):
        return "claude-code"
    return None


def _get_version() -> str:
    from importlib.metadata import version
    return version("token-tracker")


# --- 首次运行交互向导判定 ---

def _is_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _should_run_wizard() -> bool:
    """首次运行是否进交互向导：必须双 tty 且不在 AI 会话内（否则降级静默 setup）。"""
    return _is_tty() and not _current_session_agent()


# --- theme 命令 ---

def _theme_source() -> str:
    if os.environ.get("TT_THEME", "").strip():
        return t("theme_src_env")
    if config.load_theme_config().get("theme"):
        return t("theme_src_config")
    return t("theme_src_auto")


def _theme_show() -> None:
    get_console().print(t("theme_current", name=config.resolve_theme(), src=_theme_source()))


def _theme_list() -> None:
    current = config.resolve_theme()
    slots = ("green", "yellow", "peach", "red", "blue", "sapphire", "mauve", "pink")
    with forced_color_console():
        console = get_console()
        for name in themes.THEME_NAMES:
            base = themes.get_theme(name)["base"]
            marker = "●" if name == current else " "
            line = Text(f"  {marker} {name:<11}", style="bold" if name == current else "")
            for slot in slots:
                line.append("■ ", style=base[slot])
            console.print(line)


def _render_theme_sample(name: str) -> None:
    """渲染某主题配色示例（CLI 语义色 + 进度条 + 热力阶 + statusline 行），preview 与向导复用。"""
    with forced_color_console(), theme.preview_theme(name):
        console = get_console()
        text = Text("  ")
        text.append("Tokens 1.2M  ", style=theme._S.token)
        text.append("Cost $3.45  ", style=theme._S.cost)
        text.append("good  ", style=theme._S.good)
        text.append("warn  ", style=theme._S.warn)
        text.append("bad", style=theme._S.bad)
        console.print(text)
        bar = Text("  ")
        bar.append("██████", style=theme._S.bar_low)
        bar.append("█████", style=theme._S.bar_mid)
        bar.append("███", style=theme._S.bar_high)
        bar.append("  80%", style=theme._S.dim)
        console.print(bar)
        heat = Text("  ")
        for c in theme.heat_greens():
            heat.append("■ ", style=c)
        console.print(heat)
    sl = themes.theme_to_statusline_ansi(name)
    print(
        f"  {sl['project']}[project]{sl['reset']}({sl['branch']}main{sl['reset']})  "
        f"{sl['bar_ok']}██░{sl['reset']}  {sl['tokens']}Tokens 1.2M{sl['reset']}  "
        f"{sl['model']}Opus 4.8{sl['reset']}"
    )


def _theme_set(name: str) -> None:
    console = get_console()
    if name not in themes.THEMES:
        console.print(f"[red]{t('theme_unknown', name=name)}[/red]")
        console.print(f"[dim]{t('theme_options', names=', '.join(themes.THEME_NAMES))}[/dim]")
        sys.exit(1)
    config.save_theme(name)
    theme.set_active_theme(name)
    console.print(t("theme_set_ok", name=name))
    if is_setup():
        update_hook()
        console.print(f"[dim]{t('theme_set_statusline')}[/dim]")
    if config.resolve_theme() != name:
        console.print(f"[yellow]{t('theme_env_override')}[/yellow]")


def _theme_preview(name: str) -> None:
    console = get_console()
    if name not in themes.THEMES:
        console.print(f"[red]{t('theme_unknown', name=name)}[/red]")
        console.print(f"[dim]{t('theme_options', names=', '.join(themes.THEME_NAMES))}[/dim]")
        sys.exit(1)
    console.print(f"[bold]{name}[/bold]")
    _render_theme_sample(name)


def cmd_theme(args: list[str]) -> None:
    sub = args[0] if args else "show"
    if sub == "show":
        _theme_show()
    elif sub == "list":
        _theme_list()
    elif sub == "set" and len(args) >= 2:
        _theme_set(args[1])
    elif sub == "preview" and len(args) >= 2:
        _theme_preview(args[1])
    elif sub in themes.THEMES:
        _theme_set(sub)
    else:
        get_console().print(f"[dim]{t('theme_usage')}[/dim]")


def main():
    args = sys.argv[1:]
    command = args[0] if args else "status"

    # 版本查询不该触发任何文件读写，放在 auto-update 之前短路返回
    if command in ("--version", "-v", "-V"):
        print(f"token-tracker {_get_version()}")
        print("by stormzhang · https://github.com/stormzhang/token-tracker")
        return

    if command == "theme":
        cmd_theme(args[1:])
        return

    # 已配置过的情况下，任意命令都顺带同步状态栏脚本（setup/unsetup 自行处理）
    # 避免升级 pip 包后忘了 tt setup，导致 ~/.claude/tt-statusline.py 停在旧版本
    if command not in ("setup", "unsetup") and is_setup() and needs_update():
        update_hook()

    if command == "setup":
        setup()
        return
    if command == "unsetup":
        unsetup()
        return

    agents = detect_agents()
    if not agents:
        get_console().print(f"[red]{t('no_agent')}[/red]")
        sys.exit(1)

    agent_ids = {a.id for a in agents}

    if command not in ("status", "dashboard", "daily", "weekly"):
        get_console().print(f"[dim]{t('detected', agents=', '.join(a.name + ' ✓' for a in agents))}[/dim]")

    if not is_setup():
        if _should_run_wizard():
            from .wizard import run_wizard
            run_wizard()
        else:
            setup(auto=True)

    if command in ("status", "dashboard"):
        data = _build_status_data(agents)
        if not data:
            get_console().print(f"[yellow]{t('no_token_data')}[/yellow]")
            return
        render_status(**data)
        return

    rest_args, sort_key, sort_desc = _parse_sort_args(args[1:])

    if command not in _REPORT_COMMANDS:
        get_console().print(f"[red]{t('unknown_cmd', cmd=command)}[/red]")
        get_console().print(f"[dim]{t('available_cmds')}[/dim]")
        sys.exit(1)

    # daily / weekly 跟随当前会话：CC 会话只看 CC、Codex 会话只看 Codex；
    # 独立终端（识别不到会话）保持合并所有 agent。
    report_agents = agents
    if command in ("daily", "weekly"):
        session_agent = _current_session_agent()
        if session_agent and session_agent in agent_ids:
            report_agents = [a for a in agents if a.id == session_agent]
    agent_names = [a.name for a in report_agents]

    agg_fn, render_fn, time_attr, no_sort_attr, default_reverse = _REPORT_COMMANDS[command]
    stats = _aggregate_per_agent(report_agents, agg_fn)
    default_attr = time_attr if sort_key == "time" else no_sort_attr
    _apply_sort(stats, sort_key, sort_desc, default_attr, default_reverse)

    if command == "sessions":
        render_fn(stats, _parse_limit(rest_args, default=20))
    elif command == "weekly":
        render_weekly(stats, agents=agent_names, daily=_aggregate_per_agent(report_agents, aggregate_daily))
    elif command == "daily":
        d_entries = [e for a in report_agents for e in _load_entries(a.id)]
        # 最活跃时段：过去一个月按小时聚合 token（24 小时分布），渲染层据此求活跃区间
        month_ago = (datetime.now(UTC) - timedelta(days=30)).date()
        tz = system_tz()  # Active Hour 按系统时区（绕过 CLI 的 TZ）
        hourly: dict[int, int] = defaultdict(int)
        for e in d_entries:
            if e.timestamp.date() >= month_ago:
                hourly[e.timestamp.astimezone(tz).hour] += e.total_tokens
        render_daily_heatmap(stats, agents=agent_names, hourly=dict(hourly))
    else:
        render_fn(stats, agents=agent_names)


if __name__ == "__main__":
    main()
