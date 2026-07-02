"""终端主题与样式：CLI 报表配色的运行时入口。

主题数据源在 `themes.py`、解析/持久化在 `config.py`。本模块提供：
- `_S`：语义化样式代理，属性按**当前激活主题**动态解析（支持预览/切换，60+ 处 `_S.token` 调用零改）；
- `get_active_theme*` / `set_active_theme` / `preview_theme`：激活主题的读取、切换与临时预览；
- `heat_greens()`：当前主题的贡献图 5 档热力配色；
- `_pct_style` / `_heat_thresholds` / `_heat_level`：派生样式与分档工具。
"""

from contextlib import contextmanager

from .. import config
from . import themes

_ACTIVE_NAME: str | None = None  # 当前激活主题名；None=未解析，首次访问时按 config.resolve_theme() 解析
_SLOTS_CACHE: dict[str, dict] = {}  # 主题名 → 17 语义槽（按需派生、缓存）


def get_active_theme_name() -> str:
    """当前激活主题名（懒解析一次后缓存到 _ACTIVE_NAME）。"""
    global _ACTIVE_NAME
    if _ACTIVE_NAME is None:
        _ACTIVE_NAME = config.resolve_theme()
    return _ACTIVE_NAME


def get_active_theme() -> dict:
    """当前激活主题 spec（含 base / is_light / heat）。"""
    return themes.get_theme(get_active_theme_name())


def set_active_theme(name: str) -> None:
    """切换激活主题（仅改进程内状态，持久化由 config.save_theme 负责）。"""
    global _ACTIVE_NAME
    _ACTIVE_NAME = name


@contextmanager
def preview_theme(name: str):
    """临时切到某主题渲染，退出后还原（仿 console.forced_color_console 的上下文模式）。"""
    global _ACTIVE_NAME
    prev = _ACTIVE_NAME
    _ACTIVE_NAME = name
    try:
        yield
    finally:
        _ACTIVE_NAME = prev


def _active_slots() -> dict:
    name = get_active_theme_name()
    if name not in _SLOTS_CACHE:
        _SLOTS_CACHE[name] = themes.derive_slots(themes.get_theme(name)["base"])
    return _SLOTS_CACHE[name]


def heat_greens() -> list[str]:
    """当前主题的贡献图 5 档热力配色（0=无数据/最浅 → 4=最深）。"""
    return themes.heat_colors(get_active_theme_name())


class _SProxy:
    """语义化样式代理：属性（dim/token/cost/accent/bar_*/good/warn/bad…）按当前激活主题动态解析。"""

    def __getattr__(self, name: str) -> str:
        try:
            return _active_slots()[name]
        except KeyError:
            raise AttributeError(name) from None


_S = _SProxy()


def _pct_style(pct: float) -> str:
    return _S.bar_high if pct > 80 else _S.bar_mid if pct > 50 else _S.bar_low


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
