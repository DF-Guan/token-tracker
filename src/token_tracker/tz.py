"""系统时区探测：analyzer（日期分桶）与 ui（绝对时间显示）共用，放包顶层避免反向依赖 ui。"""

import os
from zoneinfo import ZoneInfo


def system_tz():
    """系统真实时区（读 /etc/localtime 软链接，绕过 CLI 的 TZ 环境变量；macOS / Linux 通用）。

    凡显示给用户的绝对时间、以及 daily/weekly/monthly 的日期分桶都该用它
    （主人 CLI 设了 TZ，但要按系统设置的时区显示）。
    Linux `/usr/share/zoneinfo/X`、macOS `/var/db/timezone/zoneinfo/X` 都能 split 出时区名；
    失败（如 Windows 无 /etc/localtime、或非软链接）回退 None → 调用方按进程时区显示
    （astimezone(None) / datetime.now(None) 均落到进程本地时区，语义一致）。
    """
    try:
        link = os.readlink("/etc/localtime")
        if "zoneinfo/" in link:
            return ZoneInfo(link.split("zoneinfo/", 1)[1])
    except Exception:  # 无文件 / 非软链接 / 无效时区名（ZoneInfoNotFoundError）等一律回退
        pass
    return None
