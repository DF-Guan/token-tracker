# Token Tracker (tt)

本地 AI Agent Token 消耗追踪/分析工具，支持 **Claude Code** 和 **Codex** 。

自定义 StatusLine 状态栏 + CLI Dashboard，实时查看 token 用量、等效成本、限额状态。

![Python](https://img.shields.io/badge/python-3.11+-blue) ![CI](https://github.com/stormzhang/token-tracker/actions/workflows/ci.yml/badge.svg) ![License](https://img.shields.io/badge/license-MIT-green)

[English](README_EN.md)

## StatusLine 状态栏

自动为 Claude Code 和 Codex 配置状态栏，`tt setup` 一键配置，脚本更新时自动升级。

**Claude Code**：基于官方自定义 StatusLine 接口，数据完全来自本地 Claude，准确无任何推测

![Claude Code StatusLine](assets/screenshot-statusline-cc.png)

状态栏共四行，从左到右：

| 行 | 字段 | 说明 |
|----|------|------|
| 1 | `[项目](分支 +12 -3)` | 项目名（加粗）+ Git 分支（未提交修改标 `*`），括号内附工作区相对 HEAD 的增删行数 |
| 1 | `Total: 1.2M` | 本次会话累计消耗 token（输入+输出+cache，解析 transcript 得出） |
| 1 | `Cost: $35.51` | 本次会话等效成本（Claude Code 自带，按官方计费，准确） |
| 1 | `Code: +208 -8` | 本会话 Claude 写 / 删的代码行数（`+` 绿 `-` 红，与 git 变动同配色） |
| 2 | `Limit: 5h: ██░ 31% (1h19m)` | 5 小时滑动窗口配额（仅订阅模式；括号内重置倒计时） |
| 2 | `7d: ██░ 11% (5d8h)` | 7 天滑动窗口配额 |
| 2 | `1.0M Ctx: ██░ 20%` | 上下文窗口总大小及已用占比 |
| 3 | `Tokens: in 392k, out 937, cache 388k` | **当前上下文窗口**的 token 构成（注意：非会话累计，会随 compact 变化） |
| 3 | `Out TPS: 60 tokens/s` | 本轮 output token 生成速度（含 thinking；空闲帧保留上次值） |
| 4 | `Model: Opus 4.8/xhigh/nofast` | 模型名 / reasoning 级别 / 是否 fast 模式 |
| 4 | `Duration: 1h33m` | 当前会话已持续时间 |
| 4 | `Remote: github` | 代码仓库 host（去顶级域） |

> 终端宽度不足时会自动降级：先隐藏重置倒计时，再将进度条简化为百分比数字。**API 模式**无订阅配额，第 2 行只显示 Ctx。

**Codex**：官方暂不支持自定义 StatusLine 渲染，沿用官方默认样式（顶部官方 status_line，`tt setup` 写入字段配置）。`tt setup` 同时启用**伪 statusline**——每次回答完成后在回答尾部追加一行彩色 status，弥补 Codex 无自定义状态栏的缺口：

![Codex StatusLine](assets/screenshot-statusline-codex.png)

**官方 status_line 字段**：

| 字段 | 说明 |
|------|------|
| `project` | 当前项目目录名 |
| `five-hour-limit` | 5 小时滑动窗口配额用量 |
| `weekly-limit` | 7 天滑动窗口配额用量 |
| `context-remaining` | 上下文窗口剩余占比 |
| `model-with-reasoning` | 模型名 + 推理强度（如 `gpt-5-codex/high`） |

**伪 statusline 一行布局** `[项目](分支 +A -D) | 5h: <%> (reset <倒计时>) | 7d: <%> (reset <倒计时>) | Ctx: <%>`

通过 Codex `Stop` hook 注入 `systemMessage` 实现，渲染 24-bit 真彩色、**不进模型上下文**（实测）。`tt unsetup` 一并移除。

## Status 实时面板和 日/周/月 数据报表分析

`tt`（无参）/ `tt status`：聚焦**过去 5 小时**的实时面板——顶部多 Agent **合并**概览（Token / Cost / Sessions / Messages / Top Model），中间 **5h / 7d 订阅额度**进度条（Claude Code / Codex 分开；都没订阅额度时换成 per-agent 的 token/cost/sessions/messages 统计），底部**近期会话**列表（CC + Codex 合并、带 Agent 列、按 Cost 倒序、Cost 前三名高亮）。所有时间按**系统时区**显示，配色跟随当前主题。

![Token Tracker Status](assets/screenshot.png)

![Token Tracker Daily](assets/screenshot-daily.png)

![Token Tracker Weekly](assets/screenshot-weekly.png)

![Token Tracker Monthly](assets/screenshot-monthly.png)

## 功能

- **多 Agent 追踪** — Claude Code + Codex 统一面板，左右键切换
- **状态栏集成** — Claude Code statusLine + Codex status_line，首次运行自动配置，脚本更新自动升级
- **限额监控** — 实时 5h / 7d 配额百分比 + 重置倒计时
- **成本分析** — 按会话、日、周、月维度的等效成本统计，多 Agent 按来源分组展示
- **定价识别** — litellm 在线定价 + 内置官方价双层兜底；同系列新模型自动套用本档定价（含 Claude Fable 5 / Opus 4.8），全新系列缺价时明确提示，不静默按 $0 统计
- **会话洞察** — 项目、模型、时长、消息数一览
- **多主题统一配色** — 6 套主题（Catppuccin Mocha/Latte/Frappe/Macchiato + Nord + Dracula），CLI 报表与状态栏**同源**；`tt theme` 一键切换 / 预览，暗 / 亮终端自动选 Catppuccin，首次运行交互向导引导选择，`TT_THEME` 可覆盖；终端不支持 truecolor 时自动降级到 256 色近似
- **零配置** — 自动检测已安装的 Agent，直接读取本地数据
- **隐私安全** — 数据纯本地存储，不采集、不上传任何用户信息，极轻量无后顾之忧

## 安装

```bash
curl -sSL https://raw.githubusercontent.com/stormzhang/token-tracker/main/install.sh | bash
```

或者通过 pip：

```bash
pip install --force-reinstall token-tracker && tt setup
```

## 使用

```bash
tt setup          # 交互配置向导（终端：上下键选语言 / 主题 / 各组件）；非 tty 环境自动全装
tt                # 过去 5h 实时面板（合并概览 + 5h/7d 额度 + 近期会话，= tt status）
tt status         # 同上（tt 无参即进 status）
tt daily          # 过去一年 token 贡献热力图（GitHub 风格）+ 年度分析卡片
tt weekly         # 周报：本周分析卡片 + 每日趋势柱状图 + 周 / 项目 / 模型趋势
tt monthly        # 按月汇总（多 Agent 分组展示）
tt sessions       # 最近 20 条会话明细数据
tt theme          # 查看 / 切换配色主题（show / list / set / preview）
tt unsetup        # 卸载并恢复安装前的配置
```

> 💡 `tt daily` 是 GitHub 风格的 token 贡献热力图（深浅绿方格）。在 Claude Code 会话里输入 `!tt daily` 即可看到彩色热力图 —— 用户主动用 `!` 执行的命令，Claude Code 会渲染其 24-bit 真彩色输出。

### 首次运行向导

第一次跑 `tt`（或通过 curl 一键安装脚本装完自动启动）会进入**交互式配置向导**，全程上下键选 + 回车确认：

1. **选语言** — 中文 / English（落 `~/.config/token-tracker/lang.json`，之后所有命令跟随）
2. **选配色主题** — 6 套主题上下键选择，每个选项右侧内联色板预览
3. **启用 Codex 伪 statusline** — Yes/No（仅检测到 Codex 时）

选完给一行综合总结。CI / 非 tty 环境（Docker / 脚本）自动按默认全装：**语言跟随系统设置**（读系统语言、不被 CLI 的 `LANG` 误导）、主题 mocha、组件全开。装好后想改任何一项，再跑一次 `tt setup` 即可（终端里每次 `tt setup` 都进向导）。

### 配色主题

内置 6 套主题，CLI 报表与状态栏**统一同源**（切主题两边一起变）：

| 主题 | 说明 |
|------|------|
| `mocha` / `latte` / `frappe` / `macchiato` | Catppuccin 全家（暗 / 亮终端自动选 mocha / latte） |
| `nord` | Nord |
| `dracula` | Dracula |

```bash
tt theme               # 显示当前主题及来源
tt theme list          # 列出全部主题 + 色块预览
tt theme preview nord  # 预览某主题（CLI 样例 + 状态栏样例行）
tt theme set nord      # 切换主题（持久化 + 重烘焙状态栏）
tt monthly --theme nord  # 任意报表临时换主题渲染（不持久化、不动状态栏，适合对比）
```

- **首次运行**（终端内、非 AI 会话）会进入交互向导引导选主题；CI / 脚本 / 会话内自动跳过、静默用默认。
- 切换持久化到 `~/.config/token-tracker/theme.json` ；优先级 `--theme` 参数 > `TT_THEME` 环境变量 > 配置文件 > 自动（`--theme` 和 `TT_THEME` 都只临时生效、不写配置）。
- 终端支持 truecolor 用精确配色；不支持的（如 macOS 自带 Terminal.app）自动降级到当前主题的 **256 色近似**，8 色老终端不再适配。

### 报告排序

所有报告命令支持 `--sort` 和 `--asc/--desc` 参数：

```bash
tt weekly --sort cost --desc    # 按成本降序
tt sessions --sort tokens --asc # 按 token 升序
```

可选排序字段：`tokens` / `cost` / `messages` / `time` / `input` / `output`

### Dashboard 快捷键

| 按键 | 功能 |
|------|------|
| `←` `→` | 切换 Agent |
| `↑` `↓` | 滚动内容 |
| `s` | 切换排序字段（时间 → Token → 等效成本 → 消息数） |
| `r` | 反转排序方向 |
| `+` / `-` | 调整会话显示条数（±10，最少 10 条） |
| `q` | 退出 |

## 数据来源

| Agent | 路径 | 格式 |
|-------|------|------|
| Claude Code | `~/.claude/projects/*/` | JSONL（逐消息用量） |
| Codex | `~/.codex/sessions/` | JSONL + SQLite |

路径跨平台：Windows 下 `~` 解析到 `%USERPROFILE%`（如 `C:\Users\xxx\.claude`）。设了 `CLAUDE_CONFIG_DIR` / `CODEX_HOME` 环境变量（官方支持的自定义目录）时自动跟随。

Token Tracker 对 Agent 数据**只读**，不做任何修改。

## 环境要求

- Python 3.11+
- [Rich](https://github.com/Textualize/rich)（自动安装）

## 开发

```bash
git clone https://github.com/stormzhang/token-tracker && cd token-tracker
uv run --extra dev pytest                # 运行测试
uv run --extra dev ruff check src tests  # Lint
```

包采用标准 src layout（`src/token_tracker/`）：发行名 `token-tracker`，导入名 `token_tracker`（0.4.0 起）。

## TODO

未来持续增加更多数据报表，多维度分析。

## License

Copyright (c) 2026 stormzhang. MIT License.
