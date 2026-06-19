# ROADMAP — token-tracker

本地 AI Agent Token 消耗追踪：Claude Code / Codex 的状态栏显示 + CLI Dashboard。
本文件是项目真实进度源，记录当前阶段、已完成、待办、阻塞与最近验证。`README.md` 写介绍与用法，`CLAUDE.md` 写开发约定，三者分工不混。

## 当前阶段

`0.4.0` 已开发完成并全部提交，**等待发布**（打 `v0.4.0` tag + 发 PyPI）。
项目整体进入「功能完整、维护迭代」阶段。

## 已完成（均已发布并验证）

**核心能力**
- 状态栏：Claude Code 三行布局（会话时长 / Cache 命中率 / Token 增量 / 重置倒计时 / Git 分支）+ Codex 官方 `status_line`；主题系统（mocha / dracula / default）；宽度自适应 + 终端尺寸实时检测
- CLI Dashboard：交互式（备用屏 + 按键 + vim 键位 + ESC 退出），启动自动检测 setup 状态并支持脚本版本更新
- 报表：`daily` / `weekly` / `monthly` / `sessions`，多 Agent 来源分组、排序功能
- 数据源：Claude / Codex 适配器，`registry` 探测可用 agent，`rate_limits` 采集
- 成本定价：litellm 在线表（7 天缓存）+ `_fallback_pricing` 离线底座，模型识别，5 小时块 + p90
- i18n：zh / en 跟随系统语言，支持 `TT_LANG` 覆盖

**工程**
- `ruff` / `pytest` / `mypy` 配置；CI；PyPI 发布（`pip install` + curl 一键安装脚本）
- 测试基线：6 个测试文件、45 个用例

**近期版本迭代**
- `0.3.7`：修复 Opus 4.8 成本估算为 0
- `0.3.8`：识别 Claude Fable 5 定价 + 未知模型显形（不再静默归零）
- `0.4.0`：包目录迁移标准 src layout（导入名 `src` → `token_tracker`）+ CI 适配新包名 + README 双语同步

## 进行中（已实现并验证，待发布）

- **`tt daily` 重构为 GitHub 风格 token 贡献热力图**（2026-06-16）：全角 ■ 深浅绿方格（5 档）+ 月份表头 + 紧凑总览 + 图例，替换原逐日表格。
  - 新增 `ui/heatmap.py`（渲染 + 自带紧凑总览）；`ui/theme.py` 加 5 档 GitHub 绿 + 分位分档；`ui/console.py` 加 `forced_color_console()` 强制 24-bit truecolor。
  - 自适应：按终端宽度决定显示周数（最多一年），`soft_wrap` 防折行；总览自渲染（不复用 dashboard 宽 header），半屏不折。
  - 会话内彩色：在 Claude Code 里用户敲 `!tt daily` 才渲染真彩色（slash command 注入、模型工具输出都会 strip 颜色，唯用户 `!` bash 模式渲染 ANSI —— 已实测确认）。
  - **原「会话内 skill 替代 + 删除终端 daily」设想撤销**：终端命令是彩色热力图的唯一载体，删了功能即失。
  - 新增 `tests/test_heatmap.py` 6 用例。
  - **daily 跟随当前会话 agent**（环境变量识别）：CC 会话只显示 CC、Codex 会话只显示 Codex；独立终端暂保持合并（待后续处理）。
  - 修复 `■` 实为 1 列宽导致的月份/方块错位（`_CELL_W=2`）；拿不到终端宽度（Claude Code `!` 非 tty）时默认显示整年。
  - 总览改紧凑卡片（`Panel` expand=False，贴合内容不撑满）+ 数据前置标签；daily 不再打 Detected 行。
- **全 CLI 配色切到 Catppuccin Mocha / Latte 双 flavor**（2026-06-18）：`ui/theme.py` 重构——`_MOCHA`/`_LATTE` 官方调色板（truecolor）映射到 `_S` 语义槽位，暗终端 Mocha、亮终端 Latte 按 `COLORFGBG` 自动选，`TT_THEME=mocha/latte` 手动覆盖（兼容旧 light/dark）；热力梯度出 `_HEAT_MOCHA`/`_HEAT_LATTE` 双版。dashboard / daily / weekly / monthly / sessions 全部统一（`panels.py`/`tables.py` 硬编码 blue → `_S.blue`），和 statusline 同源。
- **daily 概览卡片**（2026-06-18）：紧凑卡片 = 品牌行（Token Tracker 红 + agent 暗红）+ 红分割线 + `Last 12 months` 周期标题（带日期范围）+ 过去一年三行分析：橙 Tokens/Cost/Sessions/Avg-Cost/Active-Days、蓝 Peak/Current·Longest Streak、粉 Busiest/Top Model/Active Hour，与 weekly 顶部样式统一。数据筛过去一年；Active Hour = 过去一月按**北京时区（UTC+8，固定不随系统）**聚合 token、取活跃小时区间（支持跨午夜）；Current/Longest Streak = 当前连续（末尾段延续到今/昨才有效，否则归 0）·历史最长连续活跃天数（去重日期算）。配色走 Catppuccin 语义槽位、具体色值见 `theme.py`。
  - 几轮迭代后**删除** Top Project（连带 `proj_tokens`）与 Longest Session（连带 `sessions` 参数链、`_fmt_duration`/`SessionStats` import）；`Max Streak` 改为 `Current/Longest Streak`。
  - Active Days 只统计**本地日志覆盖到的活跃天**（CC `~/.claude/projects`、Codex session 文件保留有限，更早的天无数据可读），非 bug。
- **`!tt` 非 tty 宽度探测修复**（2026-06-18，已提交 73916af）：`ui/console.py` 加 `_forced_width()`，从 `_P9K_TTY`/`SSH_TTY` ioctl 取真实终端宽度（忽略 Claude Code 子进程置的占位 `COLUMNS=0`），daily 周数判定交回 Rich console。
- **`tt weekly` 重构为五区块周报**（2026-06-18）：① This Week 卡片（品牌行 Token Tracker + agent、红分割线；第二行 Tokens/Cost/Avg-Cost 橙、第三行 Sessions/Msgs/Active Days 蓝，均带环比上周；Avg/Cost=本周成本÷已过天数）② Daily Trend 每日 token 垂直柱状图（近 30 天，前三天亮、峰值标日期、底部起止）③ Weekly Trend 逐周进度条 ④ Project Trend ⑤ Model Trend（均本周口径）。四块各用主色（橙/绿/粉/蓝），标题/名称列/进度条/分割线统一该主色，进度条用同色深浅，突出项（Weekly Trend 本周 / Project·Model Trend 第一名）用亮主色、其余压暗；Weekly/Project/Model Trend 各限 8 行。
  - 数据层：`WeeklyStats`（连带 Daily/Monthly）加 `projects` 字段 + `_aggregate` 按 project 累加（同 models 机制）；新增 `test_aggregator.py::test_aggregate_fills_projects_by_token`。
  - weekly 也跟随当前会话（原仅 daily）：CC 会话只看 CC、独立终端合并；去掉 weekly 的 Detected 行。
  - daily / weekly 品牌行统一为 `Token Tracker: a + b`（冒号 + 连接、去圆点、跟随会话）。
  - 渲染走 `forced_color_console`，`!tt weekly` 非 tty 也彩色；配色沿用 Catppuccin 语义槽位。
- **statusline 标签微调**（2026-06-18）：`Context` 标签缩写为 `Ctx`（缩短状态栏宽度，`HOOK_VERSION` → 1.8，老用户升级 pip 后自动同步 `~/.claude/tt-statusline.py`）；进度条维持原样（█ 三段色填充 + ░ 空槽，期间试过 ▄/满格双色/灰底/蓝紫灰/浅蓝紫均回退）。
- **daily / weekly 署名 footer + 缩进对齐 + `tt -v`**（2026-06-18）：四个 Trend 区块（Daily/Weekly/Project/Model Trend）+ daily 热力图整面板统一左缩进 2 格（对齐卡片内容；daily grid 宽度判定预留 2，`_display_weeks` 用 `width-6`，防折行）；weekly 底部、daily 图例 `More` 右侧（空 4 格）加 dim 署名 `tt · by stormzhang`（左对齐缩进 2）；`tt -v` 输出全名 `token-tracker <版本>` + `by stormzhang · GitHub 链接`。
- **UI 去重重构**（2026-06-18）：提取 `brand_line` / `append_metric` 到 `format.py`，daily（heatmap.py）与 weekly（tables.py）品牌行 + 指标渲染共用、消除重复；渲染输出逐字不变。
- **daily/weekly 稀疏 + 窄终端自适应**（2026-06-18）：① Weekly Trend 取消本周高亮、逐周统一亮绿（本周恒在最上无需另标）；② daily 概览三行指标按终端可用宽贪心折行（`emit_metrics`，窄终端不溢出卡片）；③ Daily Trend 稀疏自适应——去前导空白天（保底 7 天）+ 中间 > 5 天连续空压成 3 列「·」gap + 标题显实际跨度；④ daily 图例署名窄终端自动另起一行、对齐 Less 列、空行隔开（避免终端硬折导致折行掉色），宽终端仍接图例右侧。
- **会话内彩色报表 hook 产品化（终端 CLI）**（2026-06-18）：`tt setup` 自动注册会话内彩色命令——CC `/tt-daily`·`/tt-weekly`（`UserPromptExpansion`）、Codex `ttdaily`·`ttweekly`（`UserPromptSubmit`），`block`+`reason` 直接渲染真彩色报表、不经模型、不污染上下文。`hooks.py` 加 `CC_REPORT_HOOK_SCRIPT`/`CODEX_REPORT_HOOK_SCRIPT` 内嵌模板（`sys.executable -m token_tracker.cli` 调用、独立 `REPORT_HOOK_VERSION`、宽度探测 -14、Windows 跳 ioctl）+ 扩展 `_setup_*`/`_unsetup_*`（特征码 `tt-report-hook` 幂等合并、不覆盖用户 hook、CC 写 commands/*.md + 合并 UserPromptExpansion 数组、Codex 末尾追加 `[[hooks.UserPromptSubmit]]` 零依赖）+ 4 个测试 + README 双语（含「仅终端」限制）。
- **统一多主题系统**（已完成 7 阶段，方案见 `~/.claude/plans/modular-chasing-pine.md`）：把现在割裂的两套配色（CLI `ui/theme.py` Catppuccin Mocha/Latte vs statusline `hooks.py` 内嵌 256-color + 写死 mocha）统一成一套主题源，主题集扩到 Catppuccin 全家（Mocha/Latte/Frappe/Macchiato）+ Nord + Dracula + default，支持预览、`tt theme` 切换、首次运行交互向导。
  - **阶段 1 ✅ 地基（不接线）**（2026-06-18）：新增 `ui/themes.py`（7 主题 × 9 基色 + 5 档热力 + `is_light`；mocha/latte 迁现值、frappe/macchiato 官方 hex、Nord/Dracula 按色相就近映射 9 槽、default 用 3-bit 兼容色名；`derive_slots` 9→17 语义槽、`_STATUSLINE_SLOTS` 10 key 子集、`theme_to_statusline_ansi` hex→truecolor/default→3-bit）+ `config.py`（`~/.config/token-tracker/theme.json` 读写 + `resolve_theme` 优先级链 `TT_THEME`>配置>`COLORFGBG`>mocha、兼容旧 light/dark）+ `tests/test_theme.py` 12 用例。官方 hex 逐字段核对（catppuccin/palette、nordtheme、dracula README）。
  - **阶段 2 ✅ `_S` 运行时化（接线 CLI）**（2026-06-18）：`ui/theme.py` 删旧 `_MOCHA`/`_LATTE`/`_is_light_theme`/`_HEAT_*`，`_S` 改成 `_SProxy` 运行时代理（`__getattr__` 取当前激活主题的 17 槽，60+ 处 `_S.token` 调用零改、KeyError→AttributeError）；加 `get_active_theme(_name)`/`set_active_theme`/`preview_theme`（上下文管理器）/`heat_greens()`（取代模块级 `HEAT_GREENS`）；`heatmap.py` 引用随之改。CLI 报表配色现在走 `config.resolve_theme()`，`TT_THEME=dracula/nord/...` 即时生效。新增 5 用例（代理跟随/未知属性/preview 还原/heat 跟随）。
  - **阶段 3 ✅ statusline 同源烘焙**（2026-06-18）：`hooks.py` 把 statusline 脚本里写死的 `THEME="mocha"`/256-color `THEMES` 换成占位符 `__STATUSLINE_THEME_COLORS__`（当前主题 truecolor）+ `__STATUSLINE_DEFAULT_COLORS__`（3-bit 兜底）；`_render_hook_script` 注入 `themes.theme_to_statusline_ansi(config.resolve_theme())`；脚本内 `C = THEME_COLORS if _supports_color() else DEFAULT_COLORS`。`HOOK_VERSION` 1.8→1.9（老用户 pip 升级后自动重烘焙）。statusline 改 truecolor 烘焙（后按主人审美把 mocha 状态栏配色调回旧观感，`_STATUSLINE_SLOTS` 与 CLI `_S` 不完全同源，见最近验证 2026-06-19）。
  - **阶段 4-5 ✅ `tt theme` 命令 + 预览**（2026-06-18）：`cli.py` 加 `theme` 子命令（自管、不触发 auto-update/agent 检测）——`show`（当前主题 + 来源 env/config/auto）、`list`（7 主题 × 8 色块 + ● 当前标记）、`set <name>`（`config.save_theme` + `set_active_theme` + 已配则 `update_hook` 重烘焙 statusline + env 覆盖警告）、`preview <name>`（`preview_theme` 渲染 CLI 语义色/三段进度条/热力阶 + statusline 示例行）、`tt theme <name>` 简写 = set。i18n 加 10 条文案、`available_cmds` 加 theme。+5 测试。
  - **阶段 6 ✅ 交互向导**（2026-06-18）：新增 `wizard.py`（`run_wizard`：欢迎 → 列主题 → Prompt 选 → 渲染所选主题预览 → `save_theme` + `setup()` 落地）；`cli.py` 首次运行钩子改为 `_should_run_wizard()`（双 tty 且非会话内才进，否则降级静默 `setup(auto=True)`）；延迟 import 破 cli↔wizard 循环。向导聚焦主题选择，agent 自动检测、彩色命令随 setup 默认装、语言跟随系统（对原 plan 四问的合理收敛，避免改 setup 签名链）。+2 测试（判定三态 + happy path）。
  - **阶段 7 ✅ 文档收尾**（2026-06-18）：README 双语加「配色主题」节（主题表 + `tt theme` 用法 + 向导 / `TT_THEME` 说明）+ 功能列表改「多主题统一配色」+ 使用表加 `tt theme`；CLAUDE.md 加「主题系统约定」节 + 项目结构表（themes/config/wizard）+ 命令行；ROADMAP 同步。

## 待办 / 计划

- **发布 `0.4.0`**：打 `v0.4.0` tag 并 push → 发 PyPI（属红线操作，待主人确认）
- 桌面版（Tauri）规划：图表可视化、数据钻取、实时监控、多 Agent 多模型监控（仅规划，未启动）
- **会话内彩色报表 hook — 桌面多形态适配**（终端部分已落地，见「进行中」）：桌面 app / web GUI 不吃 ANSI（实测乱码），需按形态输出 HTML/markdown（`tt` 加 `--format`、hook 检测形态）。详见本地 `docs/cc-hook-tt-真彩色.md`。
- **Codex 伪 statusline**（✅ 已实测可用、待产品化）：`Stop` hook + `systemMessage` 实测**渲染真彩色 + 不污染上下文**（2026-06-19）；可用版 `.codex/hooks/tt-statusline.py`（一行 `[项目](git) | 5h/7d（+reset）| Ctx`，本地 gitignore），剩进 `tt setup` 自动注册。详见 `docs/codex-hooks-statusline-research.md`。
- `mypy src` 有 5 个历史遗留报错（`aggregator.py` / `cli.py`）：准则是**别新增**，不顺手改无关旧报错

## 阻塞

- 无技术阻塞。`0.4.0` 发布需主人确认（红线）。

## 最近验证

- **2026-06-19**：**`tt sessions` Model 列修正取值口径 + 支持多模型展示**。修 bug：`aggregate_sessions` 原按各 model 的 `total_tokens` 累加取 primary，而 `total_tokens` 实测 99% 是 cache_read——后台小模型（如 Haiku）读了海量上下文会被误判为会话主力（实测 9 个多模型会话里 2 个被误标 Haiku，真实生成是 Opus）。改为按 **`output_tokens`（真实生成量）选 primary**，output 持平用 total 兜底。`SessionStats` 新增 `models: dict[str,int]`（按 output 降序），Model 列**最多展示前两个**（`Opus 4.8, Haiku 4.5`），单模型照常一个。`test_aggregator.py` helper 加 `out`/`cache_read` 参数、重写 primary 测试验证「不被 cache_read 带偏」+ 加 3 模型有序断言。`pytest` 全量 87 用例全绿、`ruff` 过；`tt sessions` 实测多模型会话正确展示主力在前。
- **2026-06-19**：**`tt sessions` 重构为 status 同款两段视图 + 列样式打磨**。复用 `ui/status.py` 头图概览 + session 列表（新增 `render_sessions_view`、`_render_summary` 参数化 title/subtitle），**去掉额度段**；顶部汇总以**展示出的 session 为口径**（`cli._summary_from_sessions`）。默认 **cost 倒序** + **过滤 <5min** 后取前 20（不足全显，`--sort`/裸数字可覆盖）；标题加计数 `Recent Sessions (N)`、末尾加参数 Tips（仅 sessions、不入 status）。列序 Time·Project·Tokens·Cost·Msgs·Duration·Model·Agent；配色 Time 蓝 / Project 绿 / Tokens 橙 / Cost 黄，Tokens·Cost 各自前三（第一红、二三粉）；`AGENT_SHORT` 全局 `CC`→`Claude`。清理旧 `tables.render_sessions` 死代码 + 孤儿 import + i18n 孤儿 key（`session_summary`）。`tt status` 底部 session 列共用同步。`pytest` 全绿、`ruff` 过、`mypy` 3→2（删调用消掉一个历史报错）。
- **2026-06-19**：**Codex 伪 statusline 实测通过 + 可用版落地**（`Stop` hook + `systemMessage`）。机制实测两点均过：① 渲染 **24-bit 真彩色**（包裹 `Stop hook (completed)` + `warning:`）② **不进模型上下文**（Codex 答不出 status 数字、要查本机文件还原）。可用版 `.codex/hooks/tt-statusline.py`（Miniforge python、零依赖、`.codex/` 本地 gitignore 不进仓库）：一行 `[项目](分支+改动) | 5h/7d（+reset）| Ctx`，借 CC statusline 样式 + mocha 配色；数据 = `load_rate_limits()`（5h/7d 账号级准）+ 最近 session `last_token_usage`（Ctx）+ git。删掉 Total（最近文件近似不准）/ Cost（估算非 Codex 自带）。Ctx 已按 Stop payload 的 `transcript_path` **精确定位当前会话**（实测 payload 带 session_id/transcript_path/cwd/model，取到的 Ctx 与目标会话一致、不再串别的会话、免 rglob 全扫）；剩产品化（进 `tt setup` 自动注册）未做。详见 `docs/codex-hooks-statusline-research.md`。
- **2026-06-19**：**statusline TPS 多会话修复 + `tt status` Rate Limits 头行 + 进度条网格着色**（本会话三件，均已提交、live `update_hook()` 已重烘焙）。① **`Out TPS` 恒显 `-` 修复**：`tt-status.json` 是全会话共享单文件、会被其它会话覆盖 → `_read_prev` 按 `session_id` 对不上 → 差分取不到 → TPS 恒 `-`；改为按 `session_id` 存进 `_tps_state` dict、写入时合并保留其它会话状态、LRU 限 20，`HOOK_VERSION` 1.17→**1.18**，加 `test_statusline_tps_isolated_per_session` 回归（commit `e71496d`）。② **Rate Limits 段重构**：扁平表 → 「每 agent 一段」，头行展示该 agent 过去 5h `Tokens`/`Cost`/`Model`（去 CC `display_name` 的 `(1M context)` 后缀），下接 5h/7d 进度条；时间前缀改 `reset at`、删 `Resets` 列头；多 agent 块间空一行（commit `43886fc`）。③ **进度条未填充网格着色**：`progress_bar` 未填充 `░` 段 `pct>0` 用 `color_by_pct` 染当前档位色（░ 字形天然更淡 → 同色暗格），`pct=0` 保持灰、`value=None`（API 模式 n/a）不变，加 `test_statusline_progress_bar_empty_grid_tinted`（commit `1317cd1`）。`pytest` 全绿（+2 hooks 测试、status 断言同步）、`ruff` 全过、`mypy` 仍 3 历史无新增。
- **2026-06-19**：**清理旧交互式 dashboard 死代码**（`tt status` 已替代，旧代码无活路径调用）。删 `cli.py`（`_show_interactive_dashboard`/`_show_agent_dashboard`/`_build_agent_data`/`_DashState`/`_apply_key`/`_render_dashboard_frame`/`_read_key*`/`KEY_MAP` + `_ALT_*`/`_RECENT_BLOCK_HOURS` 常量）+ `tables.py`（`render_dashboard`/`_render_recent_sessions`）+ `panels.py`（`render_tab_bar`/`_render_daily_panel`/`_render_active_block`/`_render_idle_panel`/`_render_month_overview`）+ `widgets.py`（全部 widget，文件删除）+ `test_cli.py`（对应 dashboard 测试）。**净删 ~720 行**。保留 daily/weekly/monthly/sessions/status 共用的 `_render_header`/`_render_agent_summaries` 及 `_load_entries`/`_build_status_data`/`_current_session_agent`。逐个 grep 确认 0 残留；`pytest` 全绿、`ruff` 全过、`mypy` **5→3**（死代码里 `msvcrt.getch` 两个历史报错随之删除、无新增）、`tt status/daily/weekly/monthly/sessions` 实跑全正常。commit `6c8acb2` + `9706cfe`（删空 widgets.py）。
- **2026-06-19**：新增 **`tt status`** 命令（替代 dashboard，`tt` 无参默认进），过去 5h 实时面板三段——头图多 agent **合并**概览（Token/Cost/Sessions/Messages/Top Model，仿 daily 品牌面板）、中间 **5h/7d 额度**（CC/Codex **分开**，weekly trend 样式横条；都无订阅额度则换成 per-agent token/cost/sessions/messages 统计）、底部**近期会话**（CC+Codex **合并**、强制 **Agent 列**、按 **Cost 倒序**、cost 前三名红/橙/黄高亮、加 Duration、过滤 <5min 短会话）。新增 `cli._build_status_data` + `ui/status.py` + `types.StatusSummary`，复用 `brand_line`/`emit_metrics`/`_bar_text`/`aggregate_sessions`。**全项目时间统一系统时区**：新增 `format.system_tz()` 读 `/etc/localtime` 绕过 CLI 的 `TZ` 环境变量（主人 CLI 设 `TZ=America/Los_Angeles` 但系统是北京）；status 头图/reset/session、`tt sessions` Time 列、daily Active Hour（原硬编码 +8）、dashboard reset 全改用它；macOS/Linux 软链接解析通用、Windows 回退进程时区、`except Exception` 兜底无效时区。**TPS 限制**：`_compute_tps` 算出会显示成 0 的（output 小/Δ大）也不刷新、沿用上次值；`HOOK_VERSION` 1.16→**1.17**。`pytest` 全绿（+test_status 6 + TPS round-0 用例）、`ruff` 全过、`mypy` 5 历史无新增；多场景实跑核对（有/无额度、TZ=LA 仍北京、Agent 列、cost 前三色、<5min 过滤）。README 双语「Status 面板」节 + 使用表改 `tt status`。
- **2026-06-19**：statusline **四行布局整体重排 + 配色定稿**（按主人多轮调整）。L1 `[项目](分支 +N -N，项目名 bold)` + `Total`（会话累计 in+out+cache，新增 `_read_transcript_totals` 解析当前会话 transcript，实测 1.8MB/793 行约 6ms）+ `Cost`（CC 自带 `total_cost_usd`）+ `Code: +A -B`（标签红、+/- 绿红同 git 变动）——消耗/产出指标标签统一 **红色**（`_STATUSLINE_SLOTS` 加 `total` 槽 = red）；L2 `Limit: 5h | 7d | Ctx`；L3 `Tokens: in/out/cache`（context window 快照、**非会话累计**）+ `Out TPS`（桃色）；L4 `Model | Duration | Remote`（host 去顶级域）。删原 context 快照 `Tokens`/`Cached` 旧行、消耗指标提到 L1。**API 模式**（无 `rate_limits`）实测优雅降级：L2 只剩 Ctx、不崩溃（三边界：无字段/None/空 dict 均无报错）。`HOOK_VERSION` 1.15→**1.16**（本地连续迭代合并一次升，不每次微调都 bump——见教训）。`pytest` 全绿、`ruff` 全过、`mypy` 5 历史无新增；多次重烘焙喂真实 JSON 核对四行布局/配色/降级。README 双语状态栏表按新四行重写。
- **2026-06-19**：statusline 新增**第 4 行** `TPS | Code | Repo`，数据全来自 CC 实时 stdin、不碰 transcript、不新建持久化文件（多轮探索结论：真实 api_duration 只在 statusline stdin，历史 transcript 没有，主人否决自建持久化——重 + 隐私）。① **本轮 TPS** = `current_usage.output_tokens` ÷ Δ`total_api_duration_ms`（差分，prev 从现有 `tt-status.json` 同会话读），带单位 `tokens/s`；中间/空闲帧沿用上次值（存 `tt-status.json` 的 `_last_tps` 字段，**常驻不回落 -**）；阈值 output≥20、Δ≥500ms 过滤「刚提交未生成」帧。② **Code** = `cost.total_lines_added/removed`（本会话 Claude 写/删行数，与第 1 行 git diff 语义不同）。③ **Repo** = `workspace.repo.host`。`hooks.py` 加 `_read_prev`/`_compute_tps` + render Line 4 + main 算 TPS 存 `_last_tps`；`HOOK_VERSION` 1.13→1.15。核实结论：`output_tokens` 含 thinking token（纯思考轮 text=0 但 output 上万为铁证）、`api_duration` 含 thinking 时间 → TPS 分子分母同口径自洽。`pytest` 全绿（+2 Line 4：完成帧带单位 + 空闲帧常驻 / 无历史值显 -）、`ruff` 全过、`mypy` 5 历史无新增；实跑落盘脚本喂两帧：完成帧 `TPS: 181 tokens/s`、空闲帧沿用 181，已 `update_hook()` 重烘焙（1.15）。README 双语状态栏表补第 4 行 + 第 1 行 git diff 列。
- **2026-06-19**：statusline 加 git 增删行数——第一行分支括号内显示相对 HEAD 的未提交改动 `[proj](main* +13 -8)`（+绿 / -红，0 改动隐藏）。`hooks.py` 加 `git_diff_stat`（`git diff HEAD --numstat` 求和、跳二进制、无 commit 兜底 0）+ render 拼接；`themes.py` `_STATUSLINE_SLOTS` 加 `added`/`deleted` 两槽（复用各主题 green/red 基色、6 主题自动跟随）；`HOOK_VERSION` 1.12→1.13。`pytest` 81 全绿（+1 端到端：临时 git repo 跑落盘脚本核对 +2 -1 / 干净 repo 无 +/-）、`ruff` 全过、`mypy` 5 历史无新增；实跑落盘脚本喂真实 JSON：本项目显示 +35 -4 与 `git diff HEAD` 一致、已 `update_hook()` 重烘焙本地脚本（1.13）。
- **2026-06-19**：移除 `tt claude` / `tt codex` 两个独立子命令（交互式 dashboard 方向键已能切 agent，独立命令冗余）。`cli.py` 删 `AGENT_ALIASES` + `tt claude/codex` 处理块 + dashboard 的 `agent_filter` 分支；`i18n.py` 删 `agent_not_found` 文案、`available_cmds` 去 claude/codex（zh+en）；README 双语用法表删两行；CLAUDE.md 命令行同步。`tt claude` 现回退到「未知命令」并列可用命令、不崩溃。`pytest` 80 全绿、`ruff check src tests` 全过；实跑 `tt claude`（未知命令）、`tt`（默认 dashboard）正常。
- **2026-06-19**：statusline 颜色分层重构——默认 truecolor、不支持则降当前主题 **256 色近似**、不再适配 8 色；删 `default` 主题（THEMES 6 个真彩主题）；判断改只认 `COLORTERM=truecolor/24bit`，顺手修 macOS Terminal.app 被误发 truecolor 的坑（它无 COLORTERM、`xterm-256color` → 走 256）。`themes.py` 加 `_hex_to_256` 近似算法（mocha green #a6e3a1 → 索引 151，与旧手调值一致）+ `theme_to_statusline_ansi(depth)`；`HOOK_VERSION` 1.11→1.12。`pytest` 80 全绿、`ruff` 全过、`mypy` 5 历史无新增；实跑落盘脚本：truecolor 终端发 38;2、`xterm-256color` 无 COLORTERM 发 38;5 且 0 残留 truecolor。依据：termstandard/colors 终端清单（WebFetch 核对）。
- **2026-06-19**：按主人反馈把 statusline mocha 配色调回旧观感——`_STATUSLINE_SLOTS` 改（分支 `red` 玫红对齐旧 211、标签 `pink`、Tokens `peach`、Model/Duration `blue`），`HOOK_VERSION` 1.9→1.11 触发自动重烘焙；状态栏 token 色与 CLI 报表（sapphire 青）不再同源（主人审美选择）。注：旧 branch `38;5;211`（#ff87af）实为玫红 ≈ mocha red `#f38ba8`、非 pink，首次误映射 pink 已修正。`pytest` 79 全绿、`ruff` 全过；已 `update_hook()` 重烘焙本地脚本核对：红色 + 桃色就位、版本 1.11。
- **2026-06-18**：统一多主题系统 阶段 7（文档收尾）+ 全工程收口（7 阶段完成）。README.md / README_EN.md（功能列表 + 使用表 + 「配色主题」节）、CLAUDE.md（「主题系统约定」节 + 结构表 + 命令行）同步。最终 `uv run --extra dev pytest` **79 全绿**（test_theme.py 22）、`ruff check src tests` 全过、`mypy src` 5 历史无新增。
- **2026-06-18**：统一多主题系统 阶段 6（交互向导）。新增 `wizard.py` + cli 首次运行 `_should_run_wizard()` 判定。`pytest` 全绿（+2）、`ruff` 全过、`mypy src` 5 历史无新增；实跑：`import wizard` 无循环、`tt daily` 回归正常、判定三态单测覆盖（非 tty/会话内降级）。
- **2026-06-18**：统一多主题系统 阶段 4-5（`tt theme` 命令 + 预览）。`cli.py` 加 `theme show/list/set/preview` + 简写。`pytest` 全绿（+5）、`ruff` 全过、`mypy src` 5 历史无新增；实跑：`list` 列 7 主题 + ● 当前、`show` 显示来源、`preview dracula` 注入 5 段 dracula truecolor、`set nord` 隔离 HOME 写入 `{"theme":"nord"}` 不污染主人配置。
- **2026-06-18**：统一多主题系统 阶段 3（statusline 同源烘焙）。`hooks.py` 占位符注入主题色 + `HOOK_VERSION` 1.8→1.9。`pytest` 全绿（+1 烘焙测试）、`ruff` 全过、`mypy src` 5 历史无新增；实跑落盘脚本喂真实 JSON：mocha/dracula 各注入 truecolor 正常运行、老终端（TERM=dumb 无 COLORTERM）走 default 3-bit 兜底（0 段 truecolor）。
- **2026-06-18**：统一多主题系统 阶段 2（`_S` 运行时化、接线 CLI）。`theme.py` 改 `_SProxy` 代理 + `preview_theme`/`set_active_theme`/`heat_greens`，`heatmap.py` 随改。`pytest` 全绿（test_theme.py 16 用例）、`ruff` 全过、`mypy src` 5 历史无新增；实跑核对：mocha 默认渲染正常、`TT_THEME=dracula/latte/nord` 切换即时生效（daily 热力图色随主题变）、daily/weekly/monthly/sessions 四报表无 Traceback、`_S` 全部 16 处属性用法 ⊆ 17 槽（无漏槽）。
- **2026-06-18**：统一多主题系统 阶段 1（地基）。新增 `ui/themes.py` + `config.py` + `tests/test_theme.py`，不接线。`uv run --extra dev pytest` 全绿（test_theme.py 12 用例 + 历史无回归）、`ruff check src tests` 全过、`mypy src` 5 历史无新增。frappe/macchiato/nord/dracula 官方 hex 经 WebFetch 逐字段核对。
- **2026-06-18**：会话内彩色报表 hook 终端产品化（CC `/tt-daily`·`/tt-weekly` + Codex `ttdaily`·`ttweekly`，`tt setup` 自动配 + `unsetup` 恢复）。临时 HOME 实跑 setup/unsetup 往返：合并不覆盖用户 hook、幂等不翻倍、卸载恢复原配置、解释器烘焙 venv python；report 脚本端 daily/weekly 渲染真彩色、非命令放行。`pytest` 56 全绿（+4）、`ruff check src tests` 全过、`mypy src` 5 历史无新增。提交 `74f6b62`/`776728d`/`9d5001b`/`d4cc4de`。
- **2026-06-18**：daily/weekly 稀疏 + 窄终端自适应（Weekly Trend 统一亮绿、概览 `emit_metrics` 折行、Daily Trend 去前导空 + 中间 gap、图例署名窄终端换行对齐）+ UI 去重（`brand_line`/`append_metric` 提取）。`pytest` 52 全绿、`ruff` 全过、`mypy` 5 历史无新增；窄终端（COLUMNS=40/44）+ 宽终端（120/200）实跑核对，去重前后渲染逐字一致。提交 `42386cd`/`62fc087`/`9330c7c`/`fea9d8e`/`e654537`/`b87feb4`。
- **2026-06-18（探索，本地实验）**：会话内彩色 hook 黑科技双端跑通——CC `/tt-daily`·`/tt-weekly`（UserPromptExpansion）、Codex `ttdaily`·`ttweekly`（UserPromptSubmit），`block`+`reason` 渲染真彩色、不污染上下文（核验 `hooks.md`/`context-window.md`）；桌面版 GUI hook 支持但 ANSI 显乱码（实测），列为后续 HTML/md 适配。实验在 `.claude/`·`.codex/`（gitignore），记录存 `docs/`。
- **2026-06-18**：daily/weekly/statusline UI 收尾——Trend 进度条突出第一名、daily/weekly 署名 footer + 统一缩进 2、`Context`→`Ctx`、daily 概览删 Top Project/Longest Session、Active Hour 固定北京时区、`Max Streak`→`Current/Longest Streak`、`tt -v` 全名+作者。`uv run --extra dev pytest` 52 全绿、`ruff check src` 全过、`mypy src` 5 历史无新增；`tt daily`/`tt weekly`/`tt -v` 实跑核对，宽终端（COLUMNS=200）验证 footer/缩进对齐。提交：`0f4b2bd`/`769d514`/`a650b89`/`8cb3fdd`。
- **2026-06-18**：`tt weekly` 五区块周报 + projects 数据层 + 跟随会话 + 品牌行统一。`uv run --extra dev pytest` 52 用例全绿（+1 projects 聚合）；`ruff check src tests` 全过；`mypy src` 5 个历史基线无新增；`tt weekly` / `tt daily` 实跑校验本周/合并两种模式正常。
- **2026-06-18（调研）**：确认 **CC 与 Codex 的本地 JSONL 日志都不含成本字段**——CC 日志无 `costUSD`（扫多个文件零匹配，新版只写 token usage）、Codex `token_count` 仅有纯 token。故 CLI 报表成本一律由 `cost.py` 定价表**估算**（`calculate_cost` 里 `cost_usd` 优先分支因 `cost_usd` 恒为 None 而从不触发）；状态栏能显示 CC 自带成本是因为走 CC 实时 stdin 推送的 `total_cost_usd`（数据源不同），历史 JSONL 无法回填成本。
- **2026-06-18**：daily 概览改版 + 全 CLI 切 Catppuccin 配色。`uv run --extra dev pytest` 51 用例全绿；`ruff check src tests` 全过；`mypy src` 仍 5 个历史遗留报错、无新增；`tt daily` / `tt` 终端实跑 Mocha 配色正常，色码核对一致。
- **2026-06-16**：daily 热力图实现完成。`uv run --extra dev pytest` 51 用例全绿（原 45 + 热力图 6）；`ruff check src tests` 全过；`tt daily` 终端实跑 truecolor 热力图正常。
  `0.4.0` 仍未打 tag / 未发布；热力图作为 `0.4.0` 之后的改动，本次提交到本地 main。
