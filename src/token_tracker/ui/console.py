"""全局 Rich console 持有者。

所有渲染都通过 get_console() 取当前 console，而不是各模块各自 import 一个全局名，
这样交互式 dashboard 截屏时用 capture_console() 临时换成定宽缓冲 console，
对拆分到多个 ui 子模块的渲染函数同时生效（避免猴补丁只改一个模块全局的老问题）。
"""

import contextlib
from collections.abc import Iterator
from io import StringIO

from rich.console import Console

_console = Console()


def get_console() -> Console:
    return _console


@contextlib.contextmanager
def capture_console(width: int) -> Iterator[StringIO]:
    """临时把全局 console 换成定宽、写入缓冲区的 console，yield 该缓冲区。"""
    global _console
    prev = _console
    buf = StringIO()
    _console = Console(file=buf, width=width, force_terminal=True)
    try:
        yield buf
    finally:
        _console = prev
