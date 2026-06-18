# Token Tracker

Track token usage across local AI agents. Supports **Claude Code** and **Codex**.

Custom StatusLine integration + CLI Dashboard — see token usage, cost, and rate limits at a glance.

![Python](https://img.shields.io/badge/python-3.11+-blue) ![CI](https://github.com/stormzhang/token-tracker/actions/workflows/ci.yml/badge.svg) ![License](https://img.shields.io/badge/license-MIT-green)

[中文](README.md)

## StatusLine

`tt setup` auto-configures status lines for Claude Code and Codex, auto-upgraded when the script updates.

**Claude Code**: Built on the official custom StatusLine API — all data comes directly from local Claude, accurate with zero guesswork

![Claude Code StatusLine](assets/screenshot-statusline-cc.png)

The status line has three rows, left to right:

| Row | Field | Description |
|-----|-------|-------------|
| 1 | `project(branch)` | Current project directory + Git branch, `*` indicates uncommitted changes |
| 1 | `5h: ██░ 31% (1h19m)` | 5-hour sliding window quota usage, countdown to reset in parentheses |
| 1 | `7d: ██░ 11% (5d8h)` | 7-day sliding window quota usage |
| 1 | `1.0M Context: ██░ 20%` | Total context window size and usage percentage |
| 2 | `Tokens: in 155k, out 128k` | Cumulative input/output tokens for the current session |
| 2 | `(Turn: in 1, out 15)` | Token usage for the current conversation turn |
| 2 | `Cached: 204k` | Prompt cache hit tokens for the current turn |
| 2 | `Cost: $35.51` | Estimated session cost (based on official pricing) |
| 3 | `Model: Opus 4.6/high/nofast` | Model / thinking level / fast mode status |
| 3 | `Duration: 1h33m` | Current session elapsed time |

> When terminal width is limited, the display auto-degrades: first hides reset countdowns, then simplifies progress bars to plain percentages.

**Codex**: Custom StatusLine rendering is not yet supported by Codex, so the official default style is reused. `tt setup` only writes the field configuration.

![Codex StatusLine](assets/screenshot-statusline-codex.png)

| Field | Meaning |
|------|------|
| `project` | Current project directory name |
| `five-hour-limit` | 5-hour rolling-window quota usage |
| `weekly-limit` | 7-day rolling-window quota usage |
| `context-remaining` | Remaining percentage of the context window |
| `model-with-reasoning` | Model name + reasoning level (e.g. `gpt-5-codex/high`) |

## Dashboard & Daily / Weekly / Monthly Reports

![Token Tracker Dashboard](assets/screenshot.png)

![Token Tracker Daily](assets/screenshot-daily.png)

![Token Tracker Weekly](assets/screenshot-weekly.png)

![Token Tracker Monthly](assets/screenshot-monthly.png)

## Features

- **Multi-agent tracking** — Claude Code + Codex in one place, interactive tab switching
- **Status line integration** — Claude Code statusLine + Codex status_line, auto-configured on first run, auto-upgraded on script updates
- **Rate limit monitoring** — real-time 5h / 7d quota usage with reset countdown
- **Cost analysis** — per-session, daily, weekly, monthly cost breakdown with per-agent grouping
- **Pricing resolution** — litellm live pricing with built-in official-price fallback; new models in a known family are priced automatically (incl. Claude Fable 5 / Opus 4.8), and unknown models trigger an explicit warning instead of silently counting as $0
- **Session insights** — project, model, duration, message count per session
- **Catppuccin theme** — unified Catppuccin colors across the CLI; Mocha on dark terminals, Latte on light, auto-selected (override with `TT_THEME`)
- **Zero config** — auto-detects installed agents, reads local data directly
- **Privacy first** — all data stays local, no collection or upload of any user information, lightweight and worry-free

## Install

```bash
curl -sSL https://raw.githubusercontent.com/stormzhang/token-tracker/main/install.sh | bash
```

Or via pip:

```bash
pip install --force-reinstall token-tracker && tt setup
```

## Usage

```bash
tt setup          # initialize and configure Claude Code + Codex status_line
tt                # interactive dashboard (arrow keys to switch agents)
tt claude         # Claude Code only
tt codex          # Codex only
tt daily          # last-12-months token contribution heatmap (GitHub-style) + yearly analysis card
tt weekly         # weekly report: this-week card + daily-trend bars + weekly / project / model trends
tt monthly        # monthly summary (per-agent grouping)
tt sessions       # last 20 session details
tt unsetup        # uninstall and restore previous config
```

> 💡 `tt daily` is a GitHub-style token contribution heatmap (shaded green cells). In a Claude Code session, type `!tt daily` to see it in full color — commands you run yourself with `!` have their 24-bit true-color output rendered.

### In-session color commands (auto-registered by `tt setup`)

`tt setup` also registers a set of in-session color commands so you can render full-color daily / weekly reports right inside an AI session — **without going through the model or spending context tokens**:

- **Claude Code**: type `/tt-daily`, `/tt-weekly`
- **Codex**: type `ttdaily`, `ttweekly` (Codex has no slash-command interception, so plain-text triggers are used)

How it works: a Claude Code `UserPromptExpansion` / Codex `UserPromptSubmit` hook intercepts the command, runs the matching `tt` subcommand, and echoes the colored output back directly — never sent to the model. `tt unsetup` removes them.

> ⚠️ **Terminal CLI only**: the desktop app / web versions are GUIs and don't render terminal ANSI, so these commands show up garbled / as plain text there. On desktop, use plain `tt daily` instead.

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
