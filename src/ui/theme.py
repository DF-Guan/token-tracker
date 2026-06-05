"""终端主题与样式选择：根据明/暗背景给出语义化 Rich 样式。"""

import os


def _is_light_theme() -> bool:
    theme = os.environ.get("TT_THEME", "").lower()
    if theme == "light":
        return True
    if theme == "dark":
        return False
    colorfgbg = os.environ.get("COLORFGBG", "")
    if colorfgbg:
        parts = colorfgbg.split(";")
        try:
            return int(parts[-1]) > 8
        except (ValueError, IndexError):
            pass
    return False


class _S:
    """语义化样式，根据终端主题自动切换"""
    light = _is_light_theme()
    dim = "grey50" if light else "dim"
    token = "dark_cyan" if light else "dim cyan"
    token_bold = "bold dark_cyan" if light else "bold cyan"
    cost = "rgb(180,130,0)" if light else "dim yellow"
    cost_bold = "bold rgb(180,130,0)" if light else "bold yellow"
    accent = "bold dark_green" if light else "bold green"
    bar_low = "dark_green" if light else "green"
    bar_mid = "rgb(200,150,0)" if light else "yellow"
    bar_high = "red"
    good = "dark_green" if light else "green"
    warn = "rgb(200,150,0)" if light else "yellow"
    bad = "red"


def _token_heat_style(ratio: float) -> str:
    if ratio > 0.8:
        return f"bold {_S.bad}"
    if ratio > 0.5:
        return f"bold {_S.warn}"
    return "bold"


def _pct_style(pct: float) -> str:
    return _S.bar_high if pct > 80 else _S.bar_mid if pct > 50 else _S.bar_low
