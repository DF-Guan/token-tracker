"""首次运行交互配置向导：选配色主题，再落地状态栏 + 会话内彩色命令。

仅在「首次运行 + tty + 非会话内」时进入（判定在 cli.py），其它场景（CI / 脚本 /
`!tt` / report hook 子进程 / AI 会话内）一律降级到静默 `setup(auto=True)`。
零新依赖，用 Rich 的 Prompt；agent 由 setup 自动检测、语言跟随系统。
"""

from rich.prompt import Prompt

from . import config
from .hooks import setup
from .i18n import t
from .ui import themes
from .ui.console import get_console


def run_wizard() -> None:
    console = get_console()
    console.print()
    console.print(f"[bold]{t('wizard_welcome')}[/bold]")
    console.print(f"[dim]{t('wizard_intro')}[/dim]")
    console.print()

    # 主题选择（列表 + 选后预览）。延迟 import 破 cli↔wizard 循环。
    from .cli import _render_theme_sample, _theme_list

    console.print(t("wizard_pick_theme"))
    _theme_list()
    choice = Prompt.ask(
        t("wizard_theme_prompt"),
        choices=list(themes.THEME_NAMES),
        default=config.resolve_theme(),
        show_choices=False,
    )
    config.save_theme(choice)
    console.print()
    _render_theme_sample(choice)
    console.print()

    # 落地配置（statusline 按所选主题烘焙 + 会话内彩色命令）。
    setup()
    console.print(f"[green]✓[/green] {t('wizard_done')}")
