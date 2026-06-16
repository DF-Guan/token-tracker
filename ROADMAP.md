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

## 待办 / 计划

- **发布 `0.4.0`**：打 `v0.4.0` tag 并 push → 发 PyPI（属红线操作，待主人确认）
- 桌面版（Tauri）规划：图表可视化、数据钻取、实时监控、多 Agent 多模型监控（仅规划，未启动）
- `mypy src` 有 5 个历史遗留报错（`aggregator.py` / `cli.py`）：准则是**别新增**，不顺手改无关旧报错

## 阻塞

- 无技术阻塞。`0.4.0` 发布需主人确认（红线）。

## 最近验证

- **2026-06-16**：`uv run --extra dev pytest` 45 用例全绿；`ruff check src tests` 全过。
  HEAD = `b2fd07c`（0.4.0 docs），最新 tag `v0.3.8` —— 即 `0.4.0` 尚未打 tag、未发布。
