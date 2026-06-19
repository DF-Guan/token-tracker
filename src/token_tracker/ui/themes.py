"""统一主题源：CLI 报表（`_S` 17 语义槽）与 statusline（12 个着色 key）共用一套配色。

每个主题只定义 **9 个基色**（沿用 Catppuccin 的槽位命名）+ 是否浅色 + 5 档热力渐变；
- 17 个 CLI 语义槽由 `derive_slots()` 统一派生（`token=sapphire`、`cost=yellow`…）；
- statusline 的 12 个 key 由 `_STATUSLINE_SLOTS` 映射到这 9 槽的子集。

颜色取值：Catppuccin（mocha/latte/frappe/macchiato）用官方 hex；Nord / Dracula 按色相
就近映射到这 9 槽。truecolor 终端用精确 hex，不支持 truecolor 的降级到 **256 色近似**
（`theme_to_statusline_ansi(depth='256')`），不再适配 8 色终端。
官方来源：catppuccin/palette、nordtheme.com、dracula-theme（均逐字段核对）。
"""

# 9 个基色槽位（所有主题必须齐全）。CLI 17 槽与 statusline 10 key 都从这 9 槽派生。
BASE_SLOTS = ("overlay0", "green", "yellow", "peach", "red", "blue", "sapphire", "mauve", "pink")

# 热力渐变插值比例：贴合现有 mocha 手调曲线（中间档偏向底色端，低档够暗才看得出空）。
_HEAT_RATIOS = (0.0, 0.2, 0.42, 0.65, 1.0)

# 每主题：is_light + 9 基色 base + cell（贡献图 level0 底色，通常 surface0）。
# mocha/latte 额外带显式 heat（手调现值，保持 daily 热力图像素级不回归）；
# 其余主题的 heat 由 cell→green 按 _HEAT_RATIOS 运行时插值。
THEMES: dict[str, dict] = {
    "mocha": {
        "is_light": False,
        "base": {
            "overlay0": "#6c7086", "green": "#a6e3a1", "yellow": "#f9e2af", "peach": "#fab387",
            "red": "#f38ba8", "blue": "#89b4fa", "sapphire": "#74c7ec", "mauve": "#cba6f7", "pink": "#f5c2e7",
        },
        "cell": "#313244",
        "heat": ["#313244", "#475951", "#628168", "#7da87f", "#a6e3a1"],
    },
    "latte": {
        "is_light": True,
        "base": {
            "overlay0": "#9ca0b0", "green": "#40a02b", "yellow": "#df8e1d", "peach": "#fe640b",
            "red": "#d20f39", "blue": "#1e66f5", "sapphire": "#209fb5", "mauve": "#8839ef", "pink": "#ea76cb",
        },
        "cell": "#ccd0da",
        "heat": ["#ccd0da", "#bbd9b8", "#98c990", "#75b868", "#40a02b"],
    },
    "frappe": {
        "is_light": False,
        "base": {
            "overlay0": "#737994", "green": "#a6d189", "yellow": "#e5c890", "peach": "#ef9f76",
            "red": "#e78284", "blue": "#8caaee", "sapphire": "#85c1dc", "mauve": "#ca9ee6", "pink": "#f4b8e4",
        },
        "cell": "#414559",
    },
    "macchiato": {
        "is_light": False,
        "base": {
            "overlay0": "#6e738d", "green": "#a6da95", "yellow": "#eed49f", "peach": "#f5a97f",
            "red": "#ed8796", "blue": "#8aadf4", "sapphire": "#7dc4e4", "mauve": "#c6a0f6", "pink": "#f5bde6",
        },
        "cell": "#363a4f",
    },
    # Nord：Frost(蓝青)+ Aurora(红橙黄绿紫) 就近映射；Nord 无第二个粉，pink 复用 nord15。
    "nord": {
        "is_light": False,
        "base": {
            "overlay0": "#4c566a", "green": "#a3be8c", "yellow": "#ebcb8b", "peach": "#d08770",
            "red": "#bf616a", "blue": "#5e81ac", "sapphire": "#88c0d0", "mauve": "#b48ead", "pink": "#b48ead",
        },
        "cell": "#3b4252",
    },
    # Dracula：蓝色稀缺，blue 与 mauve 都落 purple；sapphire 用 cyan，pink 用官方 pink。
    "dracula": {
        "is_light": False,
        "base": {
            "overlay0": "#6272a4", "green": "#50fa7b", "yellow": "#f1fa8c", "peach": "#ffb86c",
            "red": "#ff5555", "blue": "#bd93f9", "sapphire": "#8be9fd", "mauve": "#bd93f9", "pink": "#ff79c6",
        },
        "cell": "#44475a",
    },
}

# 展示顺序（tt theme list / 向导）。
THEME_NAMES = tuple(THEMES)

# statusline 12 个着色 key → 9 基色槽（reset 固定为 \033[0m，单列）。
# 这套角色映射沿用旧 mocha 状态栏观感（分支红/玫红、标签粉、Tokens 桃、Model/Duration 蓝），
# 与 CLI 报表的 _S 语义槽**不完全同源**（CLI token=sapphire 青）——按主人审美选择保留状态栏旧手感。
# total=red 红：第 1 行消耗/产出指标（Total/Cost/Code 标签）用它。
_STATUSLINE_SLOTS = {
    "project": "green",
    "branch": "red",
    "added": "green",
    "deleted": "red",
    "label": "pink",
    "bar_ok": "green",
    "bar_warn": "yellow",
    "bar_danger": "red",
    "tokens": "peach",
    "total": "red",
    "duration": "blue",
    "model": "blue",
}

def get_theme(name: str) -> dict:
    """取主题 spec，未知名兜底 mocha。"""
    return THEMES.get(name, THEMES["mocha"])


def _blend(a: str, b: str, t: float) -> str:
    """两个 #hex 之间按比例 t 线性插值，返回 #hex。"""
    return "#" + "".join(
        f"{round(int(a[i:i + 2], 16) + (int(b[i:i + 2], 16) - int(a[i:i + 2], 16)) * t):02x}"
        for i in (1, 3, 5)
    )


def heat_colors(name: str) -> list[str]:
    """该主题的 5 档热力配色（0=无数据/最浅 → 4=最深）。显式 heat 优先，否则 cell→green 插值。"""
    spec = get_theme(name)
    if "heat" in spec:
        return spec["heat"]
    return [_blend(spec["cell"], spec["base"]["green"], t) for t in _HEAT_RATIOS]


def derive_slots(base: dict) -> dict:
    """9 基色 → 17 个 CLI 语义槽（与原 theme.py `_S` 一一对应）。"""
    return {
        "dim": base["overlay0"],
        "blue": base["blue"],
        "token": base["sapphire"],
        "token_bold": f"bold {base['sapphire']}",
        "cost": base["yellow"],
        "cost_bold": f"bold {base['yellow']}",
        "peach": base["peach"],
        "mauve": base["mauve"],
        "pink": base["pink"],
        "red": base["red"],
        "accent": f"bold {base['green']}",
        "bar_low": base["green"],
        "bar_mid": base["yellow"],
        "bar_high": base["red"],
        "good": base["green"],
        "warn": base["yellow"],
        "bad": base["red"],
    }


def _color_to_ansi(value: str) -> str:
    """#hex → statusline truecolor 前景序列（38;2;R;G;B）。"""
    r, g, b = (int(value[i:i + 2], 16) for i in (1, 3, 5))
    return f"\033[38;2;{r};{g};{b}m"


def _hex_to_256(value: str) -> int:
    """#hex → 最接近的 xterm-256 调色板索引（16-255），供不支持 truecolor 的终端降级。"""
    r, g, b = (int(value[i:i + 2], 16) for i in (1, 3, 5))
    if r == g == b:  # 灰阶走 232-255 渐变档
        if r < 8:
            return 16
        if r > 248:
            return 231
        return 232 + (r - 8) * 24 // 247
    levels = (0, 95, 135, 175, 215, 255)  # 6×6×6 颜色立方各档实际亮度

    def nearest(v: int) -> int:
        return min(range(6), key=lambda i: abs(levels[i] - v))

    return 16 + 36 * nearest(r) + 6 * nearest(g) + nearest(b)


def _color_to_ansi256(value: str) -> str:
    """#hex → statusline 256 色前景序列（38;5;N，最近调色板色）。"""
    return f"\033[38;5;{_hex_to_256(value)}m"


def theme_to_statusline_ansi(name: str, depth: str = "truecolor") -> dict:
    """主题 → statusline ANSI dict（9 着色 key + reset）。depth='truecolor'(38;2) 或 '256'(38;5 近似)。"""
    base = get_theme(name)["base"]
    conv = _color_to_ansi if depth == "truecolor" else _color_to_ansi256
    out = {key: conv(base[slot]) for key, slot in _STATUSLINE_SLOTS.items()}
    out["reset"] = "\033[0m"
    return out
