"""adapter 间共享的小工具：JSONL 逐行解析、cwd → 项目名。"""

import json
import os
from collections.abc import Iterator
from pathlib import Path


def iter_jsonl_dicts(path: Path | str) -> Iterator[dict]:
    """逐行读取 JSONL，只 yield dict 行。

    统一处理 strip/空行/JSONDecodeError/非 dict 行/文件打不开，
    让调用方只关心业务字段，不必各自复制这套骨架。
    """
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):
                    yield data
    except OSError:
        return


def project_from_cwd(cwd: str) -> str:
    """从工作目录路径取项目名（去掉 home 前缀后的最后一段）。"""
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        rel = cwd[len(home):].strip(os.sep)
    else:
        rel = cwd.strip(os.sep)
    parts = rel.split(os.sep)
    return parts[-1] if parts and parts[-1] else rel or "unknown"
