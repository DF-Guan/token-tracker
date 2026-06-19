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
- **统一多主题系统**（进行中，分 7 阶段，方案见 `~/.claude/plans/modular-chasing-pine.md`）：把现在割裂的两套配色（CLI `ui/theme.py` Catppuccin Mocha/Latte vs statusline `hooks.py` 内嵌 256-color + 写死 mocha）统一成一套主题源，主题集扩到 Catppuccin 全家（Mocha/Latte/Frappe/Macchiato）+ Nord + Dracula + default，支持预览、`tt theme` 切换、首次运行交互向导。
  - **阶段 1 ✅ 地基（不接线）**（2026-06-18）：新增 `ui/themes.py`（7 主题 × 9 基色 + 5 档热力 + `is_light`；mocha/latte 迁现值、frappe/macchiato 官方 hex、Nord/Dracula 按色相就近映射 9 槽、default 用 3-bit 兼容色名；`derive_slots` 9→17 语义槽、`_STATUSLINE_SLOTS` 10 key 子集、`theme_to_statusline_ansi` hex→truecolor/default→3-bit）+ `config.py`（`~/.config/token-tracker/theme.json` 读写 + `resolve_theme` 优先级链 `TT_THEME`>配置>`COLORFGBG`>mocha、兼容旧 light/dark）+ `tests/test_theme.py` 12 用例。官方 hex 逐字段核对（catppuccin/palette、nordtheme、dracula README）。
  - **阶段 2 ✅ `_S` 运行时化（接线 CLI）**（2026-06-18）：`ui/theme.py` 删旧 `_MOCHA`/`_LATTE`/`_is_light_theme`/`_HEAT_*`，`_S` 改成 `_SProxy` 运行时代理（`__getattr__` 取当前激活主题的 17 槽，60+ 处 `_S.token` 调用零改、KeyError→AttributeError）；加 `get_active_theme(_name)`/`set_active_theme`/`preview_theme`（上下文管理器）/`heat_greens()`（取代模块级 `HEAT_GREENS`）；`heatmap.py` 引用随之改。CLI 报表配色现在走 `config.resolve_theme()`，`TT_THEME=dracula/nord/...` 即时生效。新增 5 用例（代理跟随/未知属性/preview 还原/heat 跟随）。
  - **阶段 3 ✅ statusline 同源烘焙**（2026-06-18）：`hooks.py` 把 statusline 脚本里写死的 `THEME="mocha"`/256-color `THEMES` 换成占位符 `__STATUSLINE_THEME_COLORS__`（当前主题 truecolor）+ `__STATUSLINE_DEFAULT_COLORS__`（3-bit 兜底）；`_render_hook_script` 注入 `themes.theme_to_statusline_ansi(config.resolve_theme())`；脚本内 `C = THEME_COLORS if _supports_color() else DEFAULT_COLORS`。`HOOK_VERSION` 1.8→1.9（老用户 pip 升级后自动重烘焙）。statusline 配色就此与 CLI 同源（mocha 旧 256 色 → 统一 truecolor，预期变化）。
  - 阶段 4-7 待做：`tt theme set/show/list` → 预览 → 交互向导 → 测试/i18n/文档收尾。

## 待办 / 计划

- **发布 `0.4.0`**：打 `v0.4.0` tag 并 push → 发 PyPI（属红线操作，待主人确认）
- 桌面版（Tauri）规划：图表可视化、数据钻取、实时监控、多 Agent 多模型监控（仅规划，未启动）
- **会话内彩色报表 hook — 桌面多形态适配**（终端部分已落地，见「进行中」）：桌面 app / web GUI 不吃 ANSI（实测乱码），需按形态输出 HTML/markdown（`tt` 加 `--format`、hook 检测形态）。详见本地 `docs/cc-hook-tt-真彩色.md`。
- **Codex 伪 statusline**（待主人 Codex 额度重置后实测）：`Stop` hook + `systemMessage` 做「回答后追加彩色 status」，验证 systemMessage 能否渲染真彩色 + 是否污染上下文。已搭 `.codex/hooks/test-statusline.py`，详见 `docs/codex-hooks-statusline-research.md`。
- `mypy src` 有 5 个历史遗留报错（`aggregator.py` / `cli.py`）：准则是**别新增**，不顺手改无关旧报错

## 阻塞

- 无技术阻塞。`0.4.0` 发布需主人确认（红线）。

## 最近验证

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
