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

## 待办 / 计划

- **发布 `0.4.0`**：打 `v0.4.0` tag 并 push → 发 PyPI（属红线操作，待主人确认）
- 桌面版（Tauri）规划：图表可视化、数据钻取、实时监控、多 Agent 多模型监控（仅规划，未启动）
- `mypy src` 有 5 个历史遗留报错（`aggregator.py` / `cli.py`）：准则是**别新增**，不顺手改无关旧报错

## 阻塞

- 无技术阻塞。`0.4.0` 发布需主人确认（红线）。

## 最近验证

- **2026-06-16**：daily 热力图实现完成。`uv run --extra dev pytest` 51 用例全绿（原 45 + 热力图 6）；`ruff check src tests` 全过；`tt daily` 终端实跑 truecolor 热力图正常。
  `0.4.0` 仍未打 tag / 未发布；热力图作为 `0.4.0` 之后的改动，本次提交到本地 main。
