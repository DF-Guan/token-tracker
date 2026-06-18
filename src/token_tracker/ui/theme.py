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


# --- GitHub 贡献图热力配色（daily 热力图用）---
# 0 档=无数据，1-4 档由浅到深。暗/亮两套，按背景选。0 档用稍亮灰，保证空格子在终端可辨。
_HEAT_GREENS_DARK = [
    "rgb(48,54,61)", "rgb(14,68,41)", "rgb(0,109,50)", "rgb(38,166,65)", "rgb(57,211,83)",
]
_HEAT_GREENS_LIGHT = [
    "rgb(235,237,240)", "rgb(155,233,168)", "rgb(64,196,99)", "rgb(48,161,78)", "rgb(33,110,57)",
]
HEAT_GREENS = _HEAT_GREENS_LIGHT if _S.light else _HEAT_GREENS_DARK


def _heat_thresholds(values: list[int]) -> list[float]:
    """对非零 token 值取 25/50/75 分位，作为 1-4 档的上界阈值（GitHub 风格分位分档）。"""
    nonzero = sorted(v for v in values if v > 0)
    if not nonzero:
        return [1, 1, 1]
    n = len(nonzero)
    return [nonzero[min(n - 1, int(n * q))] for q in (0.25, 0.5, 0.75)]


def _heat_level(tokens: float, thresholds: list[float]) -> int:
    """按阈值把当天 token 量映射到 0-4 档（0=无数据/最浅）：超过 N 个阈值 → 第 N+1 档。"""
    if tokens <= 0:
        return 0
    return 1 + sum(tokens > th for th in thresholds)
