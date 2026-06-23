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
# 判定改用 `/dev/tty` 可读可写（真终端必然有、CI/Docker 没有），不依赖 `[ -t 1 ]`——
# 后者在某些 shell / iTerm / 集成终端 + curl|bash 下会被误判为 false，导致 setup 收不到
# tty stdin 走静默 _auto_setup、wizard 弹不起。
say ""
if [ -r /dev/tty ] && [ -w /dev/tty ]; then
    "$TT_BIN" setup < /dev/tty
else
    say "Configuring status bar..."
    "$TT_BIN" setup
fi

say ""
say "Done! Run 'tt' to start."
