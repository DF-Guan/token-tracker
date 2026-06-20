"""主题持久化与解析：~/.config/token-tracker/theme.json（XDG 中立，不绑 Claude Code）。

解析优先级：`TT_THEME` 环境变量（兼容旧 light/dark 别名）> 配置文件 > `COLORFGBG` 自动
> mocha 默认。`auto` 仅在 Catppuccin mocha↔latte 间按终端深浅切，其它主题选了即锁定。
"""

import json
import os

from .ui import themes

CONFIG_DIR = os.path.expanduser("~/.config/token-tracker")
CONFIG_PATH = os.path.join(CONFIG_DIR, "theme.json")
LANG_CONFIG_PATH = os.path.join(CONFIG_DIR, "lang.json")

# 旧 TT_THEME 值兼容映射。
_ALIASES = {"light": "latte", "dark": "mocha"}


def load_theme_config() -> dict:
    """读配置文件，缺失/损坏都返回空 dict（不抛）。"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_theme(name: str) -> None:
    """把主题名写入配置文件（保留其它字段）。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    data = load_theme_config()
    data["theme"] = name
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _normalize(name: str) -> str:
    name = name.strip().lower()
    return _ALIASES.get(name, name)


def _auto_theme() -> str:
    """按 COLORFGBG 判终端深浅：浅色 → latte，否则 → mocha。"""
    colorfgbg = os.environ.get("COLORFGBG", "")
    if colorfgbg:
        parts = colorfgbg.split(";")
        try:
            if int(parts[-1]) > 8:
                return "latte"
        except (ValueError, IndexError):
            pass
    return "mocha"


def load_lang_config() -> dict:
    """读语言配置，缺失/损坏都返回空 dict。"""
    try:
        with open(LANG_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_lang(lang: str) -> None:
    """把语言写入配置文件（wizard 选完调）。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(LANG_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"lang": lang}, f, indent=2, ensure_ascii=False)


def resolve_lang() -> str | None:
    """读用户保存的语言偏好，仅返回受支持值（zh/en）；未配置 / 非法返回 None。"""
    val = load_lang_config().get("lang")
    return val if val in ("zh", "en") else None


def resolve_theme() -> str:
    """按优先级链解析出当前生效的主题名（保证是 themes.THEMES 里的合法键）。"""
    env = _normalize(os.environ.get("TT_THEME", ""))
    if env == "auto":
        return _auto_theme()
    if env in themes.THEMES:
        return env

    cfg = _normalize(load_theme_config().get("theme", ""))
    if cfg == "auto":
        return _auto_theme()
    if cfg in themes.THEMES:
        return cfg

    return _auto_theme()
