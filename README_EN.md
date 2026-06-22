# Token Tracker

Track token usage across local AI agents. Supports **Claude Code** and **Codex**.

Custom StatusLine integration + CLI Dashboard — see token usage, cost, and rate limits at a glance.

![Python](https://img.shields.io/badge/python-3.11+-blue) ![CI](https://github.com/stormzhang/token-tracker/actions/workflows/ci.yml/badge.svg) ![License](https://img.shields.io/badge/license-MIT-green)

[中文](README.md)

## StatusLine

`tt setup` auto-configures status lines for Claude Code and Codex, auto-upgraded when the script updates.

**Claude Code**: Built on the official custom StatusLine API — all data comes directly from local Claude, accurate with zero guesswork

![Claude Code StatusLine](assets/screenshot-statusline-cc.png)

The status line has four rows, left to right:

| Row | Field | Description |
|-----|-------|-------------|
| 1 | `[project](branch +12 -3)` | Project name (bold) + Git branch (`*` = uncommitted), with added/removed lines vs HEAD in parentheses |
| 1 | `Total: 1.2M` | Cumulative tokens consumed this session (input+output+cache, parsed from transcript) |
| 1 | `Cost: $35.51` | Session cost (from Claude Code itself, official billing, accurate) |
| 1 | `Code: +208 -8` | Lines of code written / removed by Claude this session (`+` green `-` red, same as git diff) |
| 2 | `Limit: 5h: ██░ 31% (1h19m)` | 5-hour sliding window quota (subscription only; reset countdown in parens) |
| 2 | `7d: ██░ 11% (5d8h)` | 7-day sliding window quota |
| 2 | `1.0M Ctx: ██░ 20%` | Total context window size and usage percentage |
| 3 | `Tokens: in 392k, out 937, cache 388k` | **Current context window** token breakdown (note: not session cumulative; changes on compact) |
| 3 | `Out TPS: 60 tokens/s` | Current-turn output token generation speed (includes thinking; idle frames keep last value) |
| 4 | `Model: Opus 4.8/xhigh/nofast` | Model / reasoning level / fast mode status |
| 4 | `Duration: 1h33m` | Current session elapsed time |
| 4 | `Remote: github` | Code repository host (top-level domain stripped) |

> When terminal width is limited, the display auto-degrades: first hides reset countdowns, then simplifies progress bars to plain percentages. **API mode** has no subscription quota, so row 2 shows only Ctx.

**Codex**: Custom StatusLine rendering is not yet supported by Codex, so `tt setup` installs a **faux statusline** via a Codex `Stop` hook — **two** colored status lines appended after each turn completes, mirroring the Claude Code status line (it no longer touches Codex's official `status_line`; the faux statusline carries more than the official fields):

![Codex StatusLine](assets/screenshot-statusline-codex.png)

**Faux statusline layout (two lines)**:

- **L1** `[project](branch +A -D) | Total: <session tokens> | Model: <model reasoning>` — Total in orange, Model in red
- **L2** `Limit: 5h <bar> % (reset <ttl>) | 7d <bar> % (reset <ttl>) | <window> Ctx <bar> %`

Implemented via a `Stop` hook returning `systemMessage` — renders 24-bit truecolor, **does not enter the model context** (verified), and **follows the current theme** (same source as the CLI reports / CC status line; `tt theme` switches all three together). `tt unsetup` removes it.

## Daily Overview & Daily / Weekly / Monthly Reports

`tt` (no args) / `tt daily`: the default entrypoint — GitHub-style token contribution heatmap + a top **single card** containing three stacked sections (**Last 12 months / This Month / This Week**, coarse → fine).
- Last 12 months: orange Tokens / Cost / Sessions / Avg/Cost / Active Days + blue Daily Peak / Current·Longest Streak
- This Month / This Week: orange Tokens / Cost / Avg/Cost / Active Days, with **delta vs prev month / week** (↑/↓)

`tt status`: a **last-5-hours** real-time panel — top: multi-agent **merged** overview (Token / Cost / Sessions / Messages / Top Model); middle: **5h / 7d subscription quota** bars (Claude Code / Codex separately; when neither has a subscription quota, shows per-agent token/cost/sessions/messages instead); bottom: **recent sessions** (CC + Codex merged, with an Agent column, sorted by Cost desc, top-3 cost highlighted). All times use the **system timezone**; colors follow the current theme.

![Token Tracker Daily](assets/screenshot-daily.png)

![Token Tracker Status](assets/screenshot.png)

![Token Tracker Weekly](assets/screenshot-weekly.png)

![Token Tracker Monthly](assets/screenshot-monthly.png)

## Features

- **Multi-agent tracking** — Claude Code + Codex in one place, interactive tab switching
- **Status line integration** — Claude Code statusLine + Codex faux statusline, auto-configured on first run, auto-upgraded on script updates
- **Rate limit monitoring** — real-time 5h / 7d quota usage with reset countdown
- **Cost analysis** — per-session, daily, weekly, monthly cost breakdown with per-agent grouping
- **Pricing resolution** — litellm live pricing with built-in official-price fallback; new models in a known family are priced automatically (incl. Claude Fable 5 / Opus 4.8), and unknown models trigger an explicit warning instead of silently counting as $0
- **Session insights** — project, model, duration, message count per session
- **Unified multi-theme** — 6 themes (Catppuccin Mocha/Latte/Frappe/Macchiato + Nord + Dracula) shared across CLI reports, the CC status line, and the Codex faux statusline; switch/preview with `tt theme`, auto-pick Catppuccin by terminal light/dark, first-run wizard guides selection (override with `TT_THEME`); falls back to 256-color approximation when the terminal lacks truecolor
- **Zero config** — auto-detects installed agents, reads local data directly
- **Privacy first** — all data stays local, no collection or upload of any user information, lightweight and worry-free

## Install

One-liner (the script auto-picks uv / pipx / a private venv — sidesteps PEP 668, never pollutes system Python):

```bash
curl -sSL https://raw.githubusercontent.com/stormzhang/token-tracker/main/install.sh | bash
```

Or install manually (for a CLI tool, uv / pipx is recommended — isolated env):

```bash
uv tool install token-tracker && tt setup      # if you have uv
pipx install token-tracker && tt setup         # or pipx
pip install --user token-tracker && tt setup   # otherwise
```

> **Upgrade**: re-run any install command above (the curl script is idempotent and pulls the latest).
> **Uninstall**: run `tt unsetup` first to restore the status bar, then `uv tool uninstall token-tracker` / `pipx uninstall token-tracker` (for the private-venv install, remove `~/.local/share/token-tracker` and `~/.local/bin/tt`).

## Usage

```bash
tt setup          # interactive setup wizard (terminal: language / theme / components); auto full-install on non-tty
tt                # last-12-months heatmap + top tri-section overview (Last 12 months / This Month / This Week, = tt daily)
tt daily          # same (tt with no args enters daily)
tt status         # last-5h real-time panel (merged overview + 5h/7d quota + recent sessions)
tt weekly         # weekly report: this-week card + daily-trend bars + weekly / project / model trends
tt monthly        # monthly summary (per-agent grouping)
tt sessions       # last 20 session details
tt theme          # view / switch color theme (show / list / set / preview)
tt unsetup        # uninstall and restore previous config
```

> 💡 `tt daily` is a GitHub-style token contribution heatmap (shaded green cells). In a Claude Code session, type `!tt daily` to see it in full color — commands you run yourself with `!` have their 24-bit true-color output rendered.

### First-run wizard

The first time you run `tt` (or right after the curl one-liner installer finishes), an **interactive wizard** kicks in — arrow keys to move, Enter to confirm:

1. **Pick a language** — 中文 / English (saved to `~/.config/token-tracker/config.json`, applied to all commands)
2. **Pick a color theme** — 6 themes with an inline color swatch on each option
3. **Enable Codex faux statusline** — Yes/No, Yes by default (only when Codex is detected)

A key-value config summary follows, with restart / next-step hints. CI / non-tty environments (Docker, scripts) auto-install with defaults: **language follows the system setting** (reads the OS language, not misled by the CLI's `LANG`), theme mocha, all components on. To change anything later, just run `tt setup` again (in a terminal, every `tt setup` enters the wizard).

### Color Themes

6 built-in themes, **shared** across CLI reports, the CC status line, and the Codex faux statusline (switching changes all three):

| Theme | Notes |
|-------|-------|
| `mocha` / `latte` / `frappe` / `macchiato` | Full Catppuccin (mocha/latte auto-picked by dark/light terminal) |
| `nord` | Nord |
| `dracula` | Dracula |

```bash
tt theme               # show current theme and its source
tt theme list          # list all themes with color swatches
tt theme preview nord  # preview a theme (CLI sample + status line sample)
tt theme set nord      # switch theme (persist + re-bake status line)
tt monthly --theme nord  # render any report in a theme temporarily (no persist, status line untouched)
```

- **First run** (in a terminal, not inside an AI session) opens an interactive wizard to pick a theme; CI / scripts / in-session runs skip it silently and use the default.
- Choice persists to `~/.config/token-tracker/config.json` (theme + language + component intent all in this one file); priority: `--theme` flag > `TT_THEME` env var > config file > auto (both `--theme` and `TT_THEME` are temporary and never written to config).
- Truecolor terminals get exact colors; terminals without truecolor (e.g. macOS Terminal.app) fall back to a **256-color approximation** of the current theme; 8-color terminals are no longer targeted.

### Report Sorting

All report commands support `--sort` and `--asc/--desc` flags:

```bash
tt weekly --sort cost --desc    # sort by cost, descending
tt sessions --sort tokens --asc # sort by tokens, ascending
```

Available sort fields: `tokens` / `cost` / `messages` / `time` / `input` / `output`

### Dashboard Shortcuts

| Key | Action |
|-----|--------|
| `←` `→` | Switch agent |
| `↑` `↓` | Scroll content |
| `s` | Cycle sort field (time → tokens → cost → messages) |
| `r` | Reverse sort direction |
| `+` / `-` | Adjust session count (±10, min 10) |
| `q` | Quit |

## Data Sources

| Agent | Path | Format |
|-------|------|--------|
| Claude Code | `~/.claude/projects/*/` | JSONL (per-message usage) |
| Codex | `~/.codex/sessions/` | JSONL + SQLite |

Cross-platform paths: on Windows `~` resolves to `%USERPROFILE%` (e.g. `C:\Users\xxx\.claude`). Honors `CLAUDE_CONFIG_DIR` / `CODEX_HOME` (the official custom-directory env vars) when set.

Token Tracker is **read-only** — it never modifies any agent data.

## Requirements

- Python 3.11+
- [Rich](https://github.com/Textualize/rich) (auto-installed)

## Development

```bash
git clone https://github.com/stormzhang/token-tracker && cd token-tracker
uv run --extra dev pytest                # run tests
uv run --extra dev ruff check src tests  # lint
```

The package uses the standard src layout (`src/token_tracker/`): distribution name `token-tracker`, import name `token_tracker` (since 0.4.0).

## TODO

More reports and multi-dimensional analysis coming soon.

## License

Copyright (c) 2026 stormzhang. MIT License.
