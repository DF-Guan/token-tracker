"""终端主题与样式选择：配色走 Catppuccin。

暗终端用 Mocha、亮终端用 Latte，两套 flavor 的颜色槽位一一对应。默认按终端深浅
自动选，`TT_THEME=mocha/latte` 可手动覆盖（自动检测失灵时用，兼容旧 light/dark 别名）。
"""

import os


def _is_light_theme() -> bool:
    """是否浅色（Latte）flavor。TT_THEME 手动覆盖，否则按 COLORFGBG 自动判深浅。"""
    theme = os.environ.get("TT_THEME", "").lower()
    if theme in ("latte", "light"):
        return True
    if theme in ("mocha", "dark"):
        return False
    colorfgbg = os.environ.get("COLORFGBG", "")
    if colorfgbg:
        parts = colorfgbg.split(";")
        try:
            return int(parts[-1]) > 8
        except (ValueError, IndexError):
            pass
    return False


# Catppuccin 官方调色板（truecolor）。暗终端 Mocha、亮终端 Latte，槽位一一对应。
_MOCHA = {
    "overlay0": "#6c7086", "green": "#a6e3a1", "yellow": "#f9e2af", "peach": "#fab387",
    "red": "#f38ba8", "blue": "#89b4fa", "sapphire": "#74c7ec", "mauve": "#cba6f7", "pink": "#f5c2e7",
}
_LATTE = {
    "overlay0": "#9ca0b0", "green": "#40a02b", "yellow": "#df8e1d", "peach": "#fe640b",
    "red": "#d20f39", "blue": "#1e66f5", "sapphire": "#209fb5", "mauve": "#8839ef", "pink": "#ea76cb",
}


class _S:
    """语义化样式，按终端深浅映射到 Catppuccin Mocha / Latte 槽位。"""
    light = _is_light_theme()
    _p = _LATTE if light else _MOCHA
    dim = _p["overlay0"]
    blue = _p["blue"]
    token = _p["sapphire"]
    token_bold = f"bold {_p['sapphire']}"
    cost = _p["yellow"]
    cost_bold = f"bold {_p['yellow']}"
    peach = _p["peach"]
    mauve = _p["mauve"]
    pink = _p["pink"]
    red = _p["red"]
    accent = f"bold {_p['green']}"
    bar_low = _p["green"]
    bar_mid = _p["yellow"]
    bar_high = _p["red"]
    good = _p["green"]
    warn = _p["yellow"]
    bad = _p["red"]


def _token_heat_style(ratio: float) -> str:
    if ratio > 0.8:
        return f"bold {_S.bad}"
    if ratio > 0.5:
        return f"bold {_S.warn}"
    return "bold"


def _pct_style(pct: float) -> str:
    return _S.bar_high if pct > 80 else _S.bar_mid if pct > 50 else _S.bar_low


# --- Catppuccin 贡献图热力配色（daily 热力图用）---
# 0 档=无数据（surface0），1-4 档由 green 叠在 base 上逐档加深。暗用 Mocha、亮用 Latte。
_HEAT_MOCHA = ["#313244", "#475951", "#628168", "#7da87f", "#a6e3a1"]
_HEAT_LATTE = ["#ccd0da", "#bbd9b8", "#98c990", "#75b868", "#40a02b"]
HEAT_GREENS = _HEAT_LATTE if _S.light else _HEAT_MOCHA


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
