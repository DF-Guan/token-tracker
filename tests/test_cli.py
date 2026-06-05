from src import cli
from src.adapters.types import DailyStats


def test_key_map_covers_dashboard_actions():
    # 回归：Windows reader 此前漏了 sort/reverse/more/less，现在两平台统一走 KEY_MAP
    actions = set(cli.KEY_MAP.values())
    assert {"left", "right", "up", "down", "sort", "reverse", "more", "less", "quit"} <= actions


def test_apply_sort_by_tokens_uses_authoritative_attr():
    stats = [
        DailyStats(date="2026-01-01", total_tokens=10),
        DailyStats(date="2026-01-02", total_tokens=30),
    ]
    cli._apply_sort(stats, "tokens", descending=True, default_attr="date", default_reverse=True)
    assert [s.total_tokens for s in stats] == [30, 10]


def test_apply_sort_time_falls_back_to_default_attr():
    stats = [
        DailyStats(date="2026-01-01", total_tokens=99),
        DailyStats(date="2026-01-03", total_tokens=1),
    ]
    # "time" 不在 SORT_ATTRS，应按 default_attr=date 排
    cli._apply_sort(stats, "time", descending=True, default_attr="date", default_reverse=True)
    assert [s.date for s in stats] == ["2026-01-03", "2026-01-01"]


def test_apply_sort_unknown_key_falls_back():
    stats = [
        DailyStats(date="2026-01-02", total_tokens=5),
        DailyStats(date="2026-01-01", total_tokens=99),
    ]
    cli._apply_sort(stats, "bogus", descending=True, default_attr="date", default_reverse=True)
    assert [s.date for s in stats] == ["2026-01-02", "2026-01-01"]


def _key(st, key, *, num_agents=2, num_sorts=4, max_scroll=5, page=10):
    return cli._apply_key(st, key, num_agents=num_agents, num_sorts=num_sorts, max_scroll=max_scroll, page=page)


def test_apply_key_quit_returns_false():
    assert _key(cli._DashState(), "quit") is False


def test_apply_key_left_right_wrap_and_reset_scroll():
    st = cli._DashState(current=0, scroll_offset=3)
    assert _key(st, "left") is True
    assert st.current == 1 and st.scroll_offset == 0  # 0-1 wraps to last of 2 agents
    _key(st, "right")
    assert st.current == 0


def test_apply_key_scroll_bounds():
    st = cli._DashState(scroll_offset=0)
    _key(st, "up")
    assert st.scroll_offset == 0  # 不越下界
    for _ in range(10):
        _key(st, "down")
    assert st.scroll_offset == 5  # 封顶 max_scroll
    _key(st, "page_up")
    assert st.scroll_offset == 0  # page=10 > 5，回到 0


def test_apply_key_sort_cycle_and_reverse():
    st = cli._DashState(sort_idx=3, scroll_offset=2)
    _key(st, "sort")
    assert st.sort_idx == 0 and st.scroll_offset == 0  # (3+1)%4，且重置滚动
    assert st.sort_desc is True
    _key(st, "reverse")
    assert st.sort_desc is False


def test_apply_key_session_limit_bounds():
    st = cli._DashState(session_limit=10)
    _key(st, "less")
    assert st.session_limit == 10  # 不低于 10
    _key(st, "more")
    assert st.session_limit == 20


def test_render_dashboard_frame_produces_screen():
    # 走交互式渲染路径：capture_console + render_tab_bar + render_dashboard + _fit_screen
    from src.adapters.types import DailyStats as DS
    data = {
        "daily_stats": [DS(date="2026-06-01", total_tokens=1000, cost_usd=1.0, message_count=3, session_count=1)],
        "weekly_stats": [], "monthly_stats": [], "sessions": [], "blocks": [],
        "rate_limits": None, "p90": None, "agents": ["Claude Code"],
    }
    st = cli._DashState()
    sort_cycle = cli._dashboard_sort_cycle()
    screen, max_scroll = cli._render_dashboard_frame(["Claude Code"], 0, data, st, sort_cycle, 100, 24)
    assert "Token Tracker" in screen
    assert max_scroll >= 0
