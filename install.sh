#!/usr/bin/env bash
set -e

PKG="token-tracker"

say() { printf '%s\n' "$*"; }
err() { printf 'Error: %s\n' "$*" >&2; }

# 安装方式优先级：uv > pipx > 自建私有 venv > pip --user。
# 前两者隔离 + 自带 PATH 处理；都没有时自建 venv（绕开 PEP 668 externally-managed、
# 不需要 sudo、不往系统装任何新工具）；venv 也建不了才最后退到 pip --user。
TT_BIN=""

if command -v uv >/dev/null 2>&1; then
    say "Installing $PKG with uv..."
    uv tool install --force "$PKG"
    TT_BIN="$(command -v tt || echo "$HOME/.local/bin/tt")"

elif command -v pipx >/dev/null 2>&1; then
    say "Installing $PKG with pipx..."
    pipx install --force "$PKG"
    TT_BIN="$(command -v tt || echo "$HOME/.local/bin/tt")"

elif command -v python3 >/dev/null 2>&1 && python3 -m venv -h >/dev/null 2>&1; then
    say "Installing $PKG into a private venv (~/.local/share/token-tracker)..."
    VENV_DIR="$HOME/.local/share/token-tracker/venv"
    BIN_DIR="$HOME/.local/bin"
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade "$PKG"
    mkdir -p "$BIN_DIR"
    ln -sf "$VENV_DIR/bin/tt" "$BIN_DIR/tt"
    TT_BIN="$BIN_DIR/tt"

else
    # 最后保险：pip --user（可能撞 PEP 668，再加 --break-system-packages 重试）。
    # 一般是 Debian/Ubuntu 缺 python3-venv 包才会走到这里。
    PIP="$(command -v pip3 || command -v pip || true)"
    if [ -z "$PIP" ]; then
        err "Need one of: uv / pipx / python3(+venv) / pip. Please install Python 3.11+ first."
        exit 1
    fi
    say "uv / pipx / venv unavailable, falling back to pip --user..."
    "$PIP" install --user --upgrade "$PKG" \
        || "$PIP" install --user --break-system-packages --upgrade "$PKG"
    TT_BIN="$(command -v tt || echo "$HOME/.local/bin/tt")"
fi

# PATH 检测：tt 所在目录不在 PATH 就给出明确的一行修复命令（macOS 默认不含 ~/.local/bin）。
TT_DIR="$(dirname "$TT_BIN")"
case ":$PATH:" in
    *":$TT_DIR:"*) ;;
    *)
        say ""
        say "Note: $TT_DIR is not on your PATH. Add this to ~/.zshrc (or ~/.bashrc), then restart your shell:"
        say "    export PATH=\"$TT_DIR:\$PATH\""
        ;;
esac

# 跑配置向导：用 tt 绝对路径调，避免 PATH 尚未更新时 command not found。
# 不把 stdin 重定向到 /dev/tty——curl|bash 下 bash 没 controlling terminal，
# 这种「pipe stdin → /dev/tty 重定向」会触发 prompt_toolkit issue #1943（kqueue
# 注册 fd 失败 OSError [Errno 22]）。改用：让 tt setup 看到 non-tty stdin →
# 自动走 _auto_setup 默认全装（语言跟随系统 / mocha / 组件全开），不崩。
# 想自定义的用户末尾会看到明确提示，去独立终端跑 `tt setup` 即可。
say ""
say "Configuring status bar..."
"$TT_BIN" setup

say ""
say "Done! Run 'tt' to start."
