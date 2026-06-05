import sys
from datetime import UTC

from .adapters import claude, codex
from .adapters.rate_limits import load_rate_limits as load_claude_rate_limits
from .adapters.registry import detect_agents
from .analyzer.aggregator import aggregate_daily, aggregate_monthly, aggregate_sessions, aggregate_weekly
from .analyzer.blocks import analyze_blocks, calculate_p90
from .hooks import is_setup, needs_update, setup, unsetup, update_hook
from .i18n import t
from .ui.tables import (
    AGENT_LABEL,
    console,
    render_daily,
    render_dashboard,
    render_monthly,
    render_sessions,
    render_tab_bar,
    render_weekly,
)

AGENT_ALIASES = {"claude": "claude-code", "codex": "codex"}
AGENT_LOADERS = {"claude-code": claude, "codex": codex}
RATE_LIMIT_LOADERS = {"claude-code": load_claude_rate_limits, "codex": codex.load_rate_limits}

# 排序字段 → stats 属性名（单一权威表，dashboard sort cycle 也复用）。
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
        console.print(f"[yellow]{t('unknown_sort_field', key=sort_key, valid=valid)}[/yellow]")
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


def _show_agent_dashboard(agent_id: str):
    agent_name = AGENT_LABEL.get(agent_id, agent_id)
    data = _build_agent_data(agent_id, agent_name)
    if not data:
        console.print(f"[yellow]{t('no_token_data')}[/yellow]")
        return
    render_dashboard(**data)


def _build_agent_data(agent_id: str, agent_name: str) -> dict | None:
    entries = _load_entries(agent_id)
    if not entries:
        return None
    daily = aggregate_daily(entries)
    weekly = aggregate_weekly(entries)
    monthly = aggregate_monthly(entries)
    sessions = aggregate_sessions(entries)
    from datetime import datetime, timedelta
    cutoff = datetime.now(UTC) - timedelta(hours=48)
    recent = [e for e in entries if e.timestamp >= cutoff]
    blocks = analyze_blocks(recent)
    rate_limits = RATE_LIMIT_LOADERS.get(agent_id, lambda: None)()
    p90 = None
    has_limits = rate_limits and (rate_limits.five_hour_pct is not None or rate_limits.seven_day_pct is not None)
    if not has_limits:
        p90 = calculate_p90(daily)
    return dict(
        daily_stats=daily, weekly_stats=weekly, monthly_stats=monthly,
        sessions=sessions, blocks=blocks, rate_limits=rate_limits,
        p90=p90, agents=[agent_name],
    )


def _initial_agent_index(agents) -> int:
    import os

    preferred = None
    if os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_SANDBOX"):
        preferred = "codex"
    elif os.environ.get("CLAUDE_CONFIG_DIR") or os.environ.get("CLAUDECODE"):
        preferred = "claude-code"

    if preferred:
        for i, agent in enumerate(agents):
            if agent.id == preferred:
                return i
    return 0


def _fit_screen(text: str, height: int, scroll_offset: int) -> tuple[str, int]:
    lines = text.splitlines()
    if not lines:
        return "", 0
    max_body = max(1, height - 1)
    max_scroll = max(0, len(lines) - max_body)
    scroll_offset = max(0, min(scroll_offset, max_scroll))
    visible = lines[:1] + lines[1 + scroll_offset:1 + scroll_offset + max_body - 1]
    return "\n".join(visible), max_scroll


def _dashboard_sort_cycle():
    return [
        ("time", "start_time", t("sort_time")),  # dashboard 始终排 sessions，time→start_time
        ("tokens", SORT_ATTRS["tokens"], t("sort_token")),
        ("cost", SORT_ATTRS["cost"], t("sort_cost")),
        ("messages", SORT_ATTRS["messages"], t("sort_messages")),
    ]


def _show_interactive_dashboard(agents):
    import shutil
    from io import StringIO

    from rich.console import Console as RichConsole

    import src.ui.tables as _tables

    agent_names = [a.name for a in agents]
    current = _initial_agent_index(agents)
    scroll_offset = 0
    sort_idx = 0
    sort_desc = True
    session_limit = 30
    orig = _tables.console

    sys.stdout.write("\033[?1049h\033[?7l\033[2J\033[3J\033[H\033[?25l")
    cache = {}
    sort_cycle = _dashboard_sort_cycle()

    try:
        while True:
            agent = agents[current]
            if agent.id not in cache:
                sys.stdout.write(f"\033[2J\033[3J\033[H\033[2m{t('loading')}\033[0m")
                sys.stdout.flush()
                cache[agent.id] = _build_agent_data(agent.id, agent.name)

            size = shutil.get_terminal_size((80, 24))
            width = size.columns
            height = size.lines

            data = cache[agent.id]
            if data:
                _, sort_attr, sort_label = sort_cycle[sort_idx]
                sorted_sessions = sorted(
                    data["sessions"],
                    key=lambda s: getattr(s, sort_attr),
                    reverse=sort_desc,
                )
                arrow = "↓" if sort_desc else "↑"
                session_title = t("session_title", limit=session_limit, label=sort_label, arrow=arrow)
            else:
                sorted_sessions = []
                session_title = None

            buf = StringIO()
            _tables.console = RichConsole(
                file=buf, width=width, force_terminal=True,
            )
            render_tab_bar(agent_names, current)
            if data:
                render_data = {**data, "sessions": sorted_sessions}
                render_dashboard(**render_data, session_limit=session_limit, top_margin=False, session_title=session_title)
            else:
                _tables.console.print(f"[yellow]{t('no_data')}[/yellow]")
            _tables.console = orig

            screen, max_scroll = _fit_screen(buf.getvalue(), height, scroll_offset)
            sys.stdout.write("\033[2J\033[3J\033[H" + screen)
            sys.stdout.flush()

            key = _read_key()
            if key == "left":
                current = (current - 1) % len(agents)
                scroll_offset = 0
            elif key == "right":
                current = (current + 1) % len(agents)
                scroll_offset = 0
            elif key == "up":
                scroll_offset = max(0, scroll_offset - 1)
            elif key == "down":
                scroll_offset = min(max_scroll, scroll_offset + 1)
            elif key == "page_up":
                scroll_offset = max(0, scroll_offset - max(1, height - 3))
            elif key == "page_down":
                scroll_offset = min(max_scroll, scroll_offset + max(1, height - 3))
            elif key == "sort":
                sort_idx = (sort_idx + 1) % len(sort_cycle)
                scroll_offset = 0
            elif key == "reverse":
                sort_desc = not sort_desc
            elif key == "more":
                session_limit += 10
            elif key == "less":
                session_limit = max(10, session_limit - 10)
            elif key == "quit":
                break
    finally:
        sys.stdout.write("\033[?7h\033[?25h\033[?1049l")
        sys.stdout.flush()
        _tables.console = orig


# 普通字母按键 → 动作，两个平台的 reader 共用（此前 Windows 漏了 sort/reverse/more/less）
KEY_MAP = {
    b"h": "left", b"l": "right", b"k": "up", b"j": "down",
    b"b": "page_up", b"f": "page_down",
    b"s": "sort", b"r": "reverse",
    b"+": "more", b"=": "more", b"-": "less", b"_": "less",
    b"q": "quit", b"Q": "quit", b"\x03": "quit",
}

# 终端方向键的 ESC 序列尾字节 → 动作
_UNIX_ARROW = {b"D": "left", b"C": "right", b"A": "up", b"B": "down"}
_WIN_ARROW = {b"K": "left", b"M": "right", b"H": "up", b"P": "down", b"I": "page_up", b"Q": "page_down"}


def _read_key_unix():
    import os as _os
    import select
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = _os.read(fd, 1)
        if ch == b"\x1b":
            if not select.select([fd], [], [], 0.05)[0]:
                return "quit"
            ch2 = _os.read(fd, 1)
            if ch2 == b"[":
                ch3 = _os.read(fd, 1)
                if ch3 in _UNIX_ARROW:
                    return _UNIX_ARROW[ch3]
                if ch3 in (b"5", b"6"):
                    if select.select([fd], [], [], 0.05)[0]:
                        _os.read(fd, 1)
                    return "page_up" if ch3 == b"5" else "page_down"
            return "other"
        return KEY_MAP.get(ch, "other")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_key_win():
    import msvcrt
    ch = msvcrt.getch()
    if ch in (b"\xe0", b"\x00"):
        return _WIN_ARROW.get(msvcrt.getch(), "other")
    if ch == b"\x1b":
        return "quit"
    return KEY_MAP.get(ch, "other")


_read_key = _read_key_win if sys.platform == "win32" else _read_key_unix


def _get_version() -> str:
    from importlib.metadata import version
    return version("token-tracker")


def main():
    args = sys.argv[1:]
    command = args[0] if args else "dashboard"

    # 已配置过的情况下，任意命令都顺带同步状态栏脚本（setup/unsetup 自行处理）
    # 避免升级 pip 包后忘了 tt setup，导致 ~/.claude/tt-statusline.py 停在旧版本
    if command not in ("setup", "unsetup") and is_setup() and needs_update():
        update_hook()

    if command in ("--version", "-v", "-V"):
        print(f"tt {_get_version()}")
        return
    if command == "setup":
        setup()
        return
    if command == "unsetup":
        unsetup()
        return

    agents = detect_agents()
    if not agents:
        console.print(f"[red]{t('no_agent')}[/red]")
        sys.exit(1)

    agent_ids = {a.id for a in agents}

    if command != "dashboard":
        console.print(f"[dim]{t('detected', agents=', '.join(a.name + ' ✓' for a in agents))}[/dim]")

    if not is_setup():
        setup(auto=True)

    # tt claude / tt codex
    if command in AGENT_ALIASES:
        agent_id = AGENT_ALIASES[command]
        if agent_id not in agent_ids:
            console.print(f"[red]{t('agent_not_found', name=command)}[/red]")
            sys.exit(1)
        _show_agent_dashboard(agent_id)
        return

    if command == "dashboard":
        agent_filter = args[1] if len(args) > 1 and args[1] in AGENT_ALIASES else None
        if agent_filter:
            agent_id = AGENT_ALIASES[agent_filter]
            if agent_id not in agent_ids:
                console.print(f"[red]{t('agent_not_found', name=agent_filter)}[/red]")
                sys.exit(1)
            _show_agent_dashboard(agent_id)
        elif len(agents) > 1 and sys.stdin.isatty():
            _show_interactive_dashboard(agents)
        else:
            _show_agent_dashboard(agents[0].id)
        return

    # 其他命令使用合并数据
    agent_names = [a.name for a in agents]
    rest_args, sort_key, sort_desc = _parse_sort_args(args[1:])

    if command == "daily":
        stats = _aggregate_per_agent(agents, aggregate_daily)
        default_attr = "date" if sort_key == "time" else "total_tokens"
        _apply_sort(stats, sort_key, sort_desc, default_attr, default_reverse=True)
        render_daily(stats, agents=agent_names)
    elif command == "weekly":
        stats = _aggregate_per_agent(agents, aggregate_weekly)
        default_attr = "week"
        _apply_sort(stats, sort_key, sort_desc, default_attr, default_reverse=True)
        render_weekly(stats, agents=agent_names)
    elif command == "monthly":
        stats = _aggregate_per_agent(agents, aggregate_monthly)
        default_attr = "month"
        _apply_sort(stats, sort_key, sort_desc, default_attr, default_reverse=False)
        render_monthly(stats, agents=agent_names)
    elif command == "sessions":
        limit = 20
        for a in rest_args:
            try:
                limit = int(a)
                break
            except ValueError:
                pass
        stats = _aggregate_per_agent(agents, aggregate_sessions)
        default_attr = "start_time"
        _apply_sort(stats, sort_key, sort_desc, default_attr, default_reverse=True)
        render_sessions(stats, limit)
    else:
        console.print(f"[red]{t('unknown_cmd', cmd=command)}[/red]")
        console.print(f"[dim]{t('available_cmds')}[/dim]")
        sys.exit(1)


if __name__ == "__main__":
    main()
