#!/usr/bin/env bash
set -e

if ! command -v pip &>/dev/null && ! command -v pip3 &>/dev/null; then
    echo "Error: pip not found. Please install Python 3.11+ first."
    exit 1
fi

PIP=$(command -v pip3 || command -v pip)
$PIP install -U token-tracker

echo ""
# 有 tty 时跑 tt setup 进交互向导（curl|bash 管道下 stdin 是 curl 输出，必须接 /dev/tty）；
# 无 tty（CI/Docker）降级到非交互全装。
if [ -t 1 ] && [ -e /dev/tty ]; then
    tt setup < /dev/tty
else
    echo "Configuring status bar..."
    tt setup
fi

echo ""
echo "Done! Run 'tt' to start."
