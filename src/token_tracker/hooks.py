import json
import os
import re
import stat
import sys
import tomllib

from . import config
from .i18n import t
from .ui import themes
from .ui.console import get_console

CLAUDE_SETTINGS = os.path.expanduser("~/.claude/settings.json")
HOOK_SCRIPT_PATH = os.path.expanduser("~/.claude/tt-statusline.py")
CODEX_CONFIG = os.path.expanduser("~/.codex/config.toml")
CODEX_BACKUP = os.path.expanduser("~/.codex/tt-backup.json")
HOOK_VERSION = "1.18"
REPORT_HOOK_VERSION = "1.0"
CC_REPORT_HOOK_PATH = os.path.expanduser("~/.claude/tt-report-hook.py")
CC_COMMANDS_DIR = os.path.expanduser("~/.claude/commands")
CODEX_REPORT_HOOK_PATH = os.path.expanduser("~/.codex/tt-report-hook.py")
# 会话内彩色报表命令：CC 斜杠命令名 → 命令说明（生成 commands/*.md 用；matcher 用其 key）
_CC_REPORT_CMDS = {
    "tt-daily": "tt daily 真彩色热力图（会话内直接渲染，不发模型）",
    "tt-weekly": "tt weekly 真彩色周报（会话内直接渲染，不发模型）",
}
_BACKUP_KEY = "tokenTracker"
_PREV_SL_KEY = "previousStatusLine"
_SL_REGEX = re.compile(r'status_line\s*=\s*\[.*?\]', re.DOTALL)

CODEX_STATUS_LINE = [
    "project",
    "five-hour-limit",
    "weekly-limit",
    "context-remaining",
    "model-with-reasoning",
]

# HOOK_VERSION 是唯一版本来源；__HOOK_VERSION__ 占位符在 _render_hook_script() 里注入。
# 不要用 f-string：HOOK_SCRIPT 是含 \033 与正则的 r-string，f-string 会破坏花括号。
HOOK_SCRIPT = r'''#!/usr/bin/env python3
"""Claude Code statusLine — 状态栏显示 + 数据持久化到 tt-status.json"""
__version__ = "__HOOK_VERSION__"
import json, os, re, subprocess, sys, tempfile
from datetime import datetime, timezone

STATUS_FILE = os.path.expanduser("~/.claude/tt-status.json")
ANSI_RE = re.compile(r'\033\[[0-9;]*m')
# 配色在 tt setup / update_hook 烘焙时由 themes.theme_to_statusline_ansi(当前主题) 注入：
# THEME_COLORS 为当前主题 truecolor，THEME_COLORS_256 为同主题的 256 色近似（兜底不支持
# truecolor 的终端，如 macOS Terminal.app）。只认 COLORTERM=truecolor/24bit 走真彩，否则降 256。
THEME_COLORS = __STATUSLINE_TRUECOLOR__
THEME_COLORS_256 = __STATUSLINE_COLOR256__
def _supports_truecolor():
    return os.environ.get("COLORTERM", "") in ("truecolor", "24bit")

C = THEME_COLORS if _supports_truecolor() else THEME_COLORS_256

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def vlen(s):
    return len(ANSI_RE.sub("", s))


def get_width():
    try:
        return max(1, os.get_terminal_size(2).columns - 4)
    except Exception:
        pass
    if os.name != "nt":
        try:
            import fcntl, struct, termios
            with open('/dev/tty', 'r') as tty:
                res = fcntl.ioctl(tty, termios.TIOCGWINSZ, b'\x00' * 8)
                return max(1, struct.unpack('hh', res[:4])[1] - 4)
        except Exception:
            pass
    return 116


def color_by_pct(pct):
    return C["bar_ok"] if pct < 50 else C["bar_warn"] if pct < 80 else C["bar_danger"]


def fmt_tokens(n):
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.0f}k"
    return str(n)


def progress_bar(value, bar_width=8):
    filled_char, empty_char = "█", "░"
    if value is None:
        return empty_char * bar_width + " n/a"
    pct = max(0.0, min(100.0, float(value)))
    filled = round(pct / 100 * bar_width)
    empty = bar_width - filled
    color = color_by_pct(pct)
    # 未填充网格也染当前档位色（░ 字形天然更淡 → 同色暗格）；pct=0 时不动、保持灰
    empty_str = f"{color}{empty_char * empty}{C['reset']}" if pct > 0 and empty else empty_char * empty
    return f"{color}{filled_char * filled}{C['reset']}{empty_str} {C['label']}{pct:.0f}%{C['reset']}"


def fmt_duration(seconds):
    if seconds >= 86400:
        d, rem = int(seconds // 86400), int(seconds % 86400)
        return f"{d}d{rem // 3600}h"
    if seconds >= 3600:
        h, m = int(seconds // 3600), int((seconds % 3600) // 60)
        return f"{h}h{m}m"
    if seconds >= 60:
        return f"{int(seconds // 60)}min"
    return f"{int(seconds)}s"


def git_branch(cwd):
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=cwd,
            stderr=subprocess.DEVNULL, text=True, timeout=2,
        ).strip()
    except Exception:
        return ""
    if not branch:
        return ""
    try:
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=cwd,
            stderr=subprocess.DEVNULL, text=True, timeout=2,
        ).strip()
        if dirty:
            branch += "*"
    except Exception:
        pass
    return branch


def git_diff_stat(cwd):
    """相对 HEAD 的未提交增删行数（暂存+未暂存，不含未跟踪文件）。失败/无 commit 返回 (0, 0)。"""
    try:
        out = subprocess.check_output(
            ["git", "diff", "HEAD", "--numstat"], cwd=cwd,
            stderr=subprocess.DEVNULL, text=True, timeout=2,
        )
    except Exception:
        return 0, 0
    added = deleted = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        a, d = parts[0], parts[1]
        if a.isdigit():
            added += int(a)
        if d.isdigit():
            deleted += int(d)
    return added, deleted


def save_data(data, now):
    data["_received_at"] = now.isoformat()
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STATUS_FILE), suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, STATUS_FILE)
    except OSError:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _read_prev(session_id):
    """读旧 tt-status.json：本会话 (api_duration_ms, last_tps) + 全量 _tps_state（供合并写回）。

    tt-status.json 是多会话共享单文件、会被其它会话覆盖；TPS 差分按 session_id 存进
    _tps_state dict、各会话互不干扰。返回 state 让本帧把自己的状态并回去、不丢别的会话。
    """
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            old = json.load(f)
    except Exception:
        return None, None, {}
    state = old.get("_tps_state")
    if not isinstance(state, dict):
        state = {}
    if session_id and session_id in state:
        s = state.get(session_id) or {}
        return s.get("api"), s.get("tps"), state
    if session_id and old.get("session_id") == session_id:  # 兼容升级前的旧单会话帧
        return (old.get("cost") or {}).get("total_api_duration_ms"), old.get("_last_tps"), state
    return None, None, state


def _compute_tps(data, prev_api_ms, prev_tps):
    """本轮 TPS = 本轮 output / Δapi_duration；数据缺失/中间帧/算出会显示为 0 时都沿用上次值、不刷新。"""
    cur_api_ms = (data.get("cost") or {}).get("total_api_duration_ms")
    out = ((data.get("context_window") or {}).get("current_usage") or {}).get("output_tokens", 0)
    if prev_api_ms is not None and cur_api_ms is not None:
        delta_ms = cur_api_ms - prev_api_ms
        if delta_ms >= 500 and out >= 20:
            tps = out / (delta_ms / 1000)
            if round(tps) > 0:  # 算出会显示成 0 的（output 小 / Δ 很大），不刷新、保持上次值
                return tps
    return prev_tps


def _read_transcript_totals(path):
    """解析会话 transcript 的累计 (input, output, cache) token，按 message_id:requestId 去重。

    数据来自 CC 源文件（stdin 的 transcript_path），约 1.8MB / 800 行长会话解析约 6ms；失败返回 (0,0,0)。
    """
    inp = out = cache = 0
    seen = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    x = json.loads(line)
                except Exception:
                    continue
                if x.get("type") != "assistant":
                    continue
                k = f"{x.get('message', {}).get('id')}:{x.get('requestId')}"
                if k in seen:
                    continue
                seen.add(k)
                u = x.get("message", {}).get("usage", {})
                inp += u.get("input_tokens", 0)
                out += u.get("output_tokens", 0)
                cache += u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
    except Exception:
        return 0, 0, 0
    return inp, out, cache


def render(data, now, tps=None):
    W = get_width()
    ctx = data.get("context_window") or {}
    cost = data.get("cost") or {}
    bar_w = 8 if W >= 100 else 6 if W >= 60 else 4

    # --- Line 1: Project | Total | Cost | Code（项目名原色，消耗/产出指标统一青色）---
    line1 = []

    project = (data.get("workspace") or {}).get("project_dir", "")
    if project:
        name = os.path.basename(project)
        branch = git_branch(project)
        if branch:
            inner = f"{C['branch']}{branch}{C['reset']}"
            added, deleted = git_diff_stat(project)
            if added:
                inner += f" {C['added']}+{added}{C['reset']}"
            if deleted:
                inner += f" {C['deleted']}-{deleted}{C['reset']}"
            line1.append(f"\033[1m{C['project']}[{name}]{C['reset']}({inner})")
        else:
            line1.append(f"\033[1m{C['project']}[{name}]{C['reset']}")

    # Total：会话累计（解析 transcript，CC 源数据，长会话约 6ms）；Total = in+out+cache
    tpath = data.get("transcript_path")
    if tpath:
        tin, tout, tcache = _read_transcript_totals(tpath)
        if tin or tout or tcache:
            line1.append(f"{C['total']}Total: {fmt_tokens(tin + tout + tcache)}{C['reset']}")

    # Cost（CC 自带累计，准确）
    usd = cost.get("total_cost_usd")
    if usd is not None:
        line1.append(f"{C['total']}Cost: ${usd:.2f}{C['reset']}")

    # Code：本会话 Claude 写/删的代码行数（标签青色，+/- 与 L1 git 变动同样的绿/红）
    lines_added = cost.get("total_lines_added", 0)
    lines_removed = cost.get("total_lines_removed", 0)
    if lines_added or lines_removed:
        line1.append(
            f"{C['total']}Code:{C['reset']} "
            f"{C['added']}+{lines_added}{C['reset']} {C['deleted']}-{lines_removed}{C['reset']}"
        )

    # 窄终端：宽度不够从尾部逐段去（保留项目名）
    while len(line1) > 1 and vlen(" | ".join(line1)) > W:
        line1.pop()

    # --- Line 2: Limit: 5h | 7d | Ctx ---
    rl = data.get("rate_limits") or {}
    rl_parts = []
    for key, label in [("five_hour", "5h"), ("seven_day", "7d")]:
        entry = rl.get(key) or {}
        pct = entry.get("used_percentage")
        if pct is not None:
            reset_str = ""
            resets_at = entry.get("resets_at")
            if resets_at:
                remain = int(resets_at) - int(now.timestamp())
                if remain > 0:
                    reset_str = f" \033[2m{C['label']}({fmt_duration(remain)}){C['reset']}"
            rl_parts.append((
                f"{C['label']}{label}:{C['reset']}{progress_bar(pct, bar_w)}{reset_str}",
                f"{C['label']}{label}:{C['reset']}{progress_bar(pct, bar_w)}",
                f"{C['label']}{label}:{pct:.0f}%{C['reset']}",
            ))
    ctx_parts = []
    if ctx.get("used_percentage") is not None:
        size = ctx.get("context_window_size", 0)
        ctx_parts = [
            f"{C['label']}{fmt_tokens(size)} Ctx:{C['reset']}{progress_bar(ctx['used_percentage'], bar_w)}",
            f"{C['label']}{fmt_tokens(size)} Ctx:{ctx['used_percentage']:.0f}%{C['reset']}",
        ]
    line2 = []
    if rl_parts or ctx_parts:
        for idx in (0, 1, 2):
            rl_seg = [p[idx] for p in rl_parts]
            ctx_seg = (ctx_parts[:1] if idx < 2 else ctx_parts[1:2]) if ctx_parts else []
            segs = rl_seg + ctx_seg
            if rl_seg:
                segs[0] = f"{C['label']}Limit:{C['reset']} {segs[0]}"
            if idx == 2 or vlen(" | ".join(segs)) <= W:
                line2 = segs
                break

    # --- Line 3: Tokens（上下文窗口 in/out/cache 构成，非会话累计）| TPS ---
    line3 = []
    total_in = ctx.get("total_input_tokens", 0)
    total_out = ctx.get("total_output_tokens", 0)
    cache_read = (ctx.get("current_usage") or {}).get("cache_read_input_tokens", 0)
    if total_in or total_out:
        tok = f"{C['tokens']}Tokens: in {fmt_tokens(total_in)}, out {fmt_tokens(total_out)}"
        if cache_read:
            tok += f", cache {fmt_tokens(cache_read)}"
        line3.append(tok + C['reset'])
    # 本轮 TPS（main 里算好传入，带单位）；颜色与 L3 Tokens 一致（tokens 桃色）
    tps_str = f"{tps:.0f} tokens/s" if tps else "-"
    line3.append(f"{C['tokens']}Out TPS: {tps_str}{C['reset']}")
    while len(line3) > 1 and vlen(" | ".join(line3)) > W:
        line3.pop()

    # --- Line 4: Model | Duration | Remote ---
    line4 = []

    model_name = (data.get("model") or {}).get("display_name", "")
    if model_name:
        model_name = re.sub(r'\s*\(.*?\)', '', model_name)
        effort = (data.get("effort") or {}).get("level", "")
        if effort:
            model_name += f"/{effort}"
        model_name += f"/{'fast' if data.get('fast_mode') else 'nofast'}"
        line4.append(f"{C['model']}Model: {model_name}{C['reset']}")

    duration_ms = cost.get("total_duration_ms")
    if duration_ms and duration_ms > 0:
        line4.append(f"{C['duration']}Duration: {fmt_duration(duration_ms / 1000)}{C['reset']}")

    repo_host = ((data.get("workspace") or {}).get("repo") or {}).get("host", "")
    if repo_host:
        line4.append(f"{C['model']}Remote: {repo_host.rsplit('.', 1)[0]}{C['reset']}")

    while len(line4) > 1 and vlen(" | ".join(line4)) > W:
        line4.pop()

    output = [" | ".join(line) for line in (line1, line2, line3, line4) if line]
    if output:
        print("\n".join(output))
        sys.stdout.flush()


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return
        data = json.loads(raw)
    except Exception:
        return

    now = datetime.now(timezone.utc)
    session_id = data.get("session_id") or ""
    prev_api_ms, prev_tps, state = _read_prev(session_id)  # 覆盖前读旧帧（按会话）
    tps = _compute_tps(data, prev_api_ms, prev_tps)
    if session_id:  # 本会话 TPS 状态并回 _tps_state（多会话共享文件互不清零；LRU 限 20 防膨胀）
        state.pop(session_id, None)
        state[session_id] = {"api": (data.get("cost") or {}).get("total_api_duration_ms"), "tps": tps}
        for k in list(state)[:-20]:
            del state[k]
        data["_tps_state"] = state
    save_data(data, now)
    render(data, now, tps)


if __name__ == "__main__":
    main()
'''


# 会话内彩色报表 hook 脚本（落盘 ~/.claude/tt-report-hook.py）；占位在 _render_cc_report_hook() 注入。
# 不用 f-string：含 \033 与 \0 的字面，f-string 会破坏。
CC_REPORT_HOOK_SCRIPT = r'''#!/usr/bin/env python3
"""token-tracker 会话内彩色报表 hook（Claude Code / UserPromptExpansion）。
输入 /tt-daily、/tt-weekly 时拦截 → 跑 tt 子命令 → block + reason 渲染真彩色、不发模型、不污染上下文。
由 `tt setup` 生成，勿手改。"""
__version__ = "__REPORT_HOOK_VERSION__"
import json
import os
import subprocess
import sys

_CMD = {"tt-daily": "daily", "tt-weekly": "weekly"}
_MARGIN = 14  # CC reason 显示区比真实终端窄，收窄 COLUMNS 防热力图 grid 折行


def _cols():
    if os.name == "nt":
        return None
    try:
        import fcntl
        import struct
        import termios
    except ImportError:
        return None
    for var in ("_P9K_TTY", "_P9K_SSH_TTY", "SSH_TTY"):
        path = os.environ.get(var)
        if not path:
            continue
        try:
            fd = os.open(path, os.O_RDONLY)
            try:
                cols = struct.unpack("HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8))[1]
            finally:
                os.close(fd)
            if cols > 0:
                return cols
        except OSError:
            continue
    return None


try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
sub = _CMD.get((data.get("command_name") or "").strip())
if not sub:
    sys.exit(0)
env = dict(os.environ)
cols = _cols()
if cols:
    env["COLUMNS"] = str(max(40, cols - _MARGIN))
try:
    out = subprocess.run(
        ["__TT_PYTHON__", "-m", "token_tracker.cli", sub],
        capture_output=True, text=True, env=env, timeout=60,
    ).stdout or ("tt " + sub + " no output")
except Exception as e:
    out = "tt " + sub + " failed: " + str(e)
print(json.dumps({"decision": "block", "reason": out}))
sys.exit(0)
'''


# 会话内彩色报表 hook（Codex / UserPromptSubmit）；占位在 _render_codex_report_hook() 注入
CODEX_REPORT_HOOK_SCRIPT = r'''#!/usr/bin/env python3
"""token-tracker 会话内彩色报表 hook（Codex / UserPromptSubmit）。
输入 ttdaily、ttweekly 时拦截 → 跑 tt 子命令 → block + reason 渲染真彩色、不发模型。
Codex 无 UserPromptExpansion，用纯文本触发词；reason 开头加 \n 让 Codex 包裹行与内容分开。
由 `tt setup` 生成，勿手改。"""
__version__ = "__REPORT_HOOK_VERSION__"
import json
import os
import subprocess
import sys

_CMD = {"ttdaily": "daily", "ttweekly": "weekly"}
_MARGIN = 14  # Codex reason 显示区比真实终端窄，收窄 COLUMNS 防热力图 grid 折行


def _cols():
    if os.name == "nt":
        return None
    try:
        import fcntl
        import struct
        import termios
    except ImportError:
        return None
    for var in ("_P9K_TTY", "_P9K_SSH_TTY", "SSH_TTY"):
        path = os.environ.get(var)
        if not path:
            continue
        try:
            fd = os.open(path, os.O_RDONLY)
            try:
                cols = struct.unpack("HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8))[1]
            finally:
                os.close(fd)
            if cols > 0:
                return cols
        except OSError:
            continue
    return None


try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
sub = _CMD.get((data.get("prompt") or "").strip())
if not sub:
    sys.exit(0)
env = dict(os.environ)
cols = _cols()
if cols:
    env["COLUMNS"] = str(max(40, cols - _MARGIN))
try:
    out = subprocess.run(
        ["__TT_PYTHON__", "-m", "token_tracker.cli", sub],
        capture_output=True, text=True, env=env, timeout=60,
    ).stdout or ("tt " + sub + " no output")
except Exception as e:
    out = "tt " + sub + " failed: " + str(e)
print(json.dumps({"decision": "block", "reason": "\n" + out}))
sys.exit(0)
'''


# --- helpers ---

def _render_hook_script() -> str:
    """把 HOOK_VERSION + 当前主题 truecolor / 256 两套配色注入占位符，得到要落盘的状态栏脚本。"""
    name = config.resolve_theme()
    return (
        HOOK_SCRIPT
        .replace("__HOOK_VERSION__", HOOK_VERSION)
        .replace("__STATUSLINE_TRUECOLOR__", repr(themes.theme_to_statusline_ansi(name)))
        .replace("__STATUSLINE_COLOR256__", repr(themes.theme_to_statusline_ansi(name, "256")))
    )


def _render_cc_report_hook() -> str:
    """注入版本号 + 当前解释器路径，得到要落盘的 CC 报表 hook 脚本。"""
    python = sys.executable or "python3"
    return (CC_REPORT_HOOK_SCRIPT
            .replace("__REPORT_HOOK_VERSION__", REPORT_HOOK_VERSION)
            .replace("__TT_PYTHON__", python))


def _installed_report_version() -> str | None:
    """读已落盘的 CC 报表 hook 脚本版本（与 statusline 版本独立）。"""
    try:
        with open(CC_REPORT_HOOK_PATH, encoding="utf-8") as f:
            for line in f:
                if line.startswith("__version__"):
                    return line.split("=", 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return None


def _is_tt_report_entry(entry: dict) -> bool:
    """判断一个 UserPromptExpansion 数组项是不是 tt 装的（按 hook command 特征码）。"""
    hooks = entry.get("hooks") or []
    return any("tt-report-hook" in (h.get("command") or "") for h in hooks if isinstance(h, dict))


def _write_cc_report_script() -> None:
    """渲染并落盘 CC 报表 hook 脚本（+ 执行权限）。setup 与版本同步都用。"""
    with open(CC_REPORT_HOOK_PATH, "w", encoding="utf-8") as f:
        f.write(_render_cc_report_hook())
    if os.name != "nt":
        os.chmod(CC_REPORT_HOOK_PATH,
                 os.stat(CC_REPORT_HOOK_PATH).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _install_cc_report(settings: dict, python: str) -> None:
    """落盘脚本 + commands/*.md，并把 UserPromptExpansion matcher 合并进 settings（幂等、不动用户其它项）。"""
    _write_cc_report_script()
    os.makedirs(CC_COMMANDS_DIR, exist_ok=True)
    for name, desc in _CC_REPORT_CMDS.items():
        with open(os.path.join(CC_COMMANDS_DIR, name + ".md"), "w", encoding="utf-8") as f:
            f.write(f"---\ndescription: {desc}\n---\n\n"
                    "此命令由 token-tracker 的 UserPromptExpansion hook 拦截并直接渲染，正常不发给模型。\n")
    expansion = settings.setdefault("hooks", {}).setdefault("UserPromptExpansion", [])
    expansion[:] = [e for e in expansion if not (isinstance(e, dict) and _is_tt_report_entry(e))]
    cmd = f"{python} {CC_REPORT_HOOK_PATH}"
    for name in _CC_REPORT_CMDS:
        expansion.append({"matcher": name, "hooks": [{"type": "command", "command": cmd}]})


def _uninstall_cc_report(settings: dict) -> None:
    """删 report 脚本 + commands/*.md，从 settings 移除 tt 的 UserPromptExpansion 项（不动用户其它）。"""
    if os.path.exists(CC_REPORT_HOOK_PATH):
        os.remove(CC_REPORT_HOOK_PATH)
    for name in _CC_REPORT_CMDS:
        p = os.path.join(CC_COMMANDS_DIR, name + ".md")
        if os.path.exists(p):
            os.remove(p)
    hooks_cfg = settings.get("hooks")
    if isinstance(hooks_cfg, dict):
        expansion = hooks_cfg.get("UserPromptExpansion")
        if isinstance(expansion, list):
            expansion[:] = [e for e in expansion if not (isinstance(e, dict) and _is_tt_report_entry(e))]
            if not expansion:
                hooks_cfg.pop("UserPromptExpansion", None)
        if not hooks_cfg:
            settings.pop("hooks", None)


def _render_codex_report_hook() -> str:
    """注入版本号 + 当前解释器路径，得到要落盘的 Codex 报表 hook 脚本。"""
    python = sys.executable or "python3"
    return (CODEX_REPORT_HOOK_SCRIPT
            .replace("__REPORT_HOOK_VERSION__", REPORT_HOOK_VERSION)
            .replace("__TT_PYTHON__", python))


def _write_codex_report_script() -> None:
    with open(CODEX_REPORT_HOOK_PATH, "w", encoding="utf-8") as f:
        f.write(_render_codex_report_hook())
    if os.name != "nt":
        os.chmod(CODEX_REPORT_HOOK_PATH,
                 os.stat(CODEX_REPORT_HOOK_PATH).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _installed_codex_report_version() -> str | None:
    try:
        with open(CODEX_REPORT_HOOK_PATH, encoding="utf-8") as f:
            for line in f:
                if line.startswith("__version__"):
                    return line.split("=", 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return None


# 卸载时定位 tt 追加的整段 [[hooks.UserPromptSubmit]]（按 command 含特征码 tt-report-hook）
_CODEX_HOOK_REGEX = re.compile(
    r'\n*\[\[hooks\.UserPromptSubmit\]\]\s*'
    r'\[\[hooks\.UserPromptSubmit\.hooks\]\]\s*'
    r'type = "command"\s*'
    r'command = "[^"]*tt-report-hook[^"]*"\s*'
    r'timeout = 60\s*'
)


def _install_codex_report(content: str, python: str) -> str:
    """落盘 Codex report 脚本 + 在 config.toml 末尾追加 hook 段（幂等：已含特征码则不重复）。返回新 content。"""
    _write_codex_report_script()
    if "tt-report-hook" in content:
        return content
    cmd = f"{python} {CODEX_REPORT_HOOK_PATH}"
    return content.rstrip() + (
        "\n\n[[hooks.UserPromptSubmit]]\n\n"
        "[[hooks.UserPromptSubmit.hooks]]\n"
        'type = "command"\n'
        f'command = "{cmd}"\n'
        "timeout = 60\n"
    )


def _uninstall_codex_report(content: str) -> str:
    """删 Codex report 脚本 + 从 content 移除 tt 追加的 hook 段（不动用户其它）。返回新 content。"""
    if os.path.exists(CODEX_REPORT_HOOK_PATH):
        os.remove(CODEX_REPORT_HOOK_PATH)
    return _CODEX_HOOK_REGEX.sub("\n", content)


def _status_line_toml(items: list[str]) -> str:
    body = ",\n".join(f'  "{item}"' for item in items)
    return f"status_line = [\n{body},\n]"


def _read_codex_config() -> tuple[str, dict] | None:
    try:
        with open(CODEX_CONFIG, encoding="utf-8") as f:
            content = f.read()
        return content, tomllib.loads(content)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def is_setup() -> bool:
    has_cc = os.path.isdir(os.path.dirname(CLAUDE_SETTINGS))
    has_codex = os.path.exists(CODEX_CONFIG)
    if not has_cc and not has_codex:
        return False
    if has_cc:
        try:
            with open(CLAUDE_SETTINGS, encoding="utf-8") as f:
                settings = json.load(f)
            sl = settings.get("statusLine")
            if not isinstance(sl, dict) or "tt-statusline" not in (sl.get("command") or ""):
                return False
        except (OSError, json.JSONDecodeError):
            return False
    if has_codex:
        result = _read_codex_config()
        if not result:
            return False
        _, parsed = result
        if parsed.get("tui", {}).get("status_line") != CODEX_STATUS_LINE:
            return False
    return True


def _installed_hook_version() -> str | None:
    try:
        with open(HOOK_SCRIPT_PATH, encoding="utf-8") as f:
            for line in f:
                if line.startswith("__version__"):
                    return line.split("=", 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return None


def needs_update() -> bool:
    # report hook 只在已安装时纳入版本判断（未装不主动装）
    if os.path.isdir(os.path.dirname(HOOK_SCRIPT_PATH)):
        if _installed_hook_version() != HOOK_VERSION:
            return True
        rv = _installed_report_version()
        if rv is not None and rv != REPORT_HOOK_VERSION:
            return True
    cv = _installed_codex_report_version()
    return cv is not None and cv != REPORT_HOOK_VERSION


def update_hook() -> None:
    if os.path.isdir(os.path.dirname(HOOK_SCRIPT_PATH)):
        with open(HOOK_SCRIPT_PATH, "w", encoding="utf-8") as f:
            f.write(_render_hook_script())
        if os.name != "nt":
            os.chmod(HOOK_SCRIPT_PATH,
                     os.stat(HOOK_SCRIPT_PATH).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        if _installed_report_version() is not None:  # 仅当已装才同步（不主动装）
            _write_cc_report_script()
    if _installed_codex_report_version() is not None:
        _write_codex_report_script()


# --- setup ---

def setup(auto: bool = False) -> None:
    has_cc = os.path.isdir(os.path.dirname(CLAUDE_SETTINGS))
    has_codex = os.path.exists(CODEX_CONFIG)

    if not has_cc and not has_codex:
        get_console().print(f"[red]{t('no_agent_install')}[/red]")
        return

    if auto:
        get_console().print(f"[dim]{t('first_setup')}[/dim]")

    if has_cc:
        _setup_claude()
    else:
        if not auto:
            get_console().print(f"[dim]{t('cc_not_found')}[/dim]")

    if has_codex:
        _setup_codex()
    else:
        if not auto:
            get_console().print(f"[dim]{t('codex_not_found')}[/dim]")


def _setup_claude() -> None:
    update_hook()

    settings: dict = {}
    if os.path.exists(CLAUDE_SETTINGS):
        with open(CLAUDE_SETTINGS, encoding="utf-8") as f:
            settings = json.load(f)

    existing = settings.get("statusLine")
    if existing and "tt-statusline" not in (existing.get("command") or ""):
        get_console().print(f"[yellow]{t('sl_backup_replace')}[/yellow]")
        settings.setdefault(_BACKUP_KEY, {})[_PREV_SL_KEY] = existing

    python = sys.executable or "python3"
    settings["statusLine"] = {"type": "command", "command": f"{python} {HOOK_SCRIPT_PATH}"}
    _install_cc_report(settings, python)

    with open(CLAUDE_SETTINGS, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    get_console().print(f"[green]✓[/green] {t('cc_configured')}")
    get_console().print(f"[dim]{t('cc_report_hint')}[/dim]")
    get_console().print(f"[dim]{t('restart_cc')}[/dim]")


def _setup_codex() -> None:
    result = _read_codex_config()
    if not result:
        return
    content, parsed = result

    python = sys.executable or "python3"

    # status_line（已是目标则跳过这部分，但仍继续装 report hook）
    old = parsed.get("tui", {}).get("status_line")
    if old != CODEX_STATUS_LINE:
        if old is not None:
            with open(CODEX_BACKUP, "w", encoding="utf-8") as f:
                json.dump({"status_line": old}, f)
            content = _SL_REGEX.sub(_status_line_toml(CODEX_STATUS_LINE), content)
        elif "[tui]" in content:
            content = content.replace("[tui]", f"[tui]\n{_status_line_toml(CODEX_STATUS_LINE)}")
        else:
            content += f"\n[tui]\n{_status_line_toml(CODEX_STATUS_LINE)}\n"

    # report hook（末尾追加，幂等）
    content = _install_codex_report(content, python)

    with open(CODEX_CONFIG, "w", encoding="utf-8") as f:
        f.write(content)

    get_console().print(f"[green]✓[/green] {t('codex_configured')}")
    if old is not None and old != CODEX_STATUS_LINE:
        get_console().print(f"[dim]{t('codex_backup', path=CODEX_BACKUP)}[/dim]")
    get_console().print(f"[dim]{t('codex_report_hint')}[/dim]")
    get_console().print(f"[dim]{t('restart_codex')}[/dim]")


# --- unsetup ---

def unsetup() -> None:
    has_cc = os.path.isdir(os.path.dirname(CLAUDE_SETTINGS))
    has_codex = os.path.exists(CODEX_CONFIG)

    if has_cc:
        _unsetup_claude()
    if has_codex:
        _unsetup_codex()
    if not has_cc and not has_codex:
        get_console().print(f"[dim]{t('no_agent_detected')}[/dim]")


def _unsetup_claude() -> None:
    if os.path.exists(HOOK_SCRIPT_PATH):
        os.remove(HOOK_SCRIPT_PATH)
        get_console().print(f"[green]✓[/green] {t('deleted_file', path=HOOK_SCRIPT_PATH)}")

    if not os.path.exists(CLAUDE_SETTINGS):
        return

    with open(CLAUDE_SETTINGS, encoding="utf-8") as f:
        settings = json.load(f)

    # 先独立清理 report hook（脚本 + commands + hooks 数组里的 tt 项），不受 statusLine 检查影响
    _uninstall_cc_report(settings)

    sl = settings.get("statusLine")
    if isinstance(sl, dict) and "tt-statusline" in (sl.get("command") or ""):
        previous = settings.get(_BACKUP_KEY, {}).get(_PREV_SL_KEY)
        if isinstance(previous, dict):
            settings["statusLine"] = previous
            get_console().print(f"[green]✓[/green] {t('cc_restored')}")
        else:
            settings.pop("statusLine", None)
            get_console().print(f"[green]✓[/green] {t('cc_removed')}")
        backup = settings.get(_BACKUP_KEY)
        if isinstance(backup, dict):
            backup.pop(_PREV_SL_KEY, None)
            if not backup:
                del settings[_BACKUP_KEY]
        status_file = os.path.expanduser("~/.claude/tt-status.json")
        if os.path.exists(status_file):
            os.remove(status_file)
            get_console().print(f"[green]✓[/green] {t('deleted_cache', path=status_file)}")

    with open(CLAUDE_SETTINGS, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def _unsetup_codex() -> None:
    result = _read_codex_config()
    if not result:
        return
    content, parsed = result

    content = _uninstall_codex_report(content)  # 先独立清 report（脚本 + hook 段），不受 status_line 检查阻断

    if parsed.get("tui", {}).get("status_line") is not None:
        if os.path.exists(CODEX_BACKUP):
            with open(CODEX_BACKUP, encoding="utf-8") as f:
                old_items = json.load(f).get("status_line", [])
            content = _SL_REGEX.sub(_status_line_toml(old_items), content)
            os.remove(CODEX_BACKUP)
            get_console().print(f"[green]✓[/green] {t('codex_restored')}")
        else:
            content = re.sub(r'status_line\s*=\s*\[.*?\]\n?', '', content, flags=re.DOTALL)
            get_console().print(f"[green]✓[/green] {t('codex_removed')}")

    with open(CODEX_CONFIG, "w", encoding="utf-8") as f:
        f.write(content)
