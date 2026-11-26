# OfferLab · AI 模拟面试与复盘系统

《大模型与智能体工程实践》课程项目。根据简历和目标岗位进行文字模拟面试，围绕回答追问，生成带原文证据的四维复盘，并支持历史恢复和 Markdown 导出。

```text
准备材料 → 开始面试 → 逐题回答与追问 → 复盘报告 → 导出或重新练习
```

前后端在本机运行：React + TypeScript + Vite → FastAPI + SQLite → SSH 隧道 → 学校 OpenClaw 的 `interviewer` Agent → 模型。演示模式使用本地题库，不需要学校服务。

## 当前状态

- 已实现简历文本 / TXT / 文本型 PDF 解析、1–5 道主问题、每题最多两次追问、报告引文校验与导出。
- 模型生成使用持久化后台任务，等待时只显示加载图标；支持刷新恢复、浏览器答题草稿和失败重试。
- 主问题预先准备但不提前展示；题内追问结束后点击“下一题”，上一组问答在后台复盘，总报告复用已完成的分析。
- 学校专用 Agent 已安装，已有真实计划生成、Agent 路由与 Skill / 评价标准读取证据。
- **2026-11-26：开发者确认已切换个人 DeepSeek，响应明显加快。** 当前模型 ID 与完整面试耗时需以新的运行记录为准；旧模型的超时记录保留在历史验证中。
- 完整真实报告与桌面 / 手机浏览器验收仍需完成；尚未接入语音、视频、岗位网页抓取和外部检索。

## 快速启动

需要 Bash、Python 3.11+（含 venv/pip）、Node.js 22.12+ 和 npm。在项目根目录执行：

```bash
python3 scripts/manage.py dev
```

首次运行自动安装缺失依赖，并在 `.env` 不存在时按 [.env.example](.env.example) 创建演示配置；已有配置保留。打开 http://127.0.0.1:5173，Ctrl+C 同时停止前后端。

已配置真实模型时，在另一个终端运行 `python3 scripts/manage.py tunnel` 保持 SSH 隧道（已有隧道无需重复启动）。真实模式接入、Token 和环境变量见 [本机运行与排查](docs/operations.md)。

## 常用命令

```bash
python3 scripts/manage.py --help       # 所有命令及用途
python3 scripts/manage.py setup        # 安装 / 同步依赖
python3 scripts/manage.py check        # 本地测试、类型检查和生产构建
python3 scripts/manage.py gateway-check # 一次真实模型连接检查
python3 scripts/manage.py runs         # 只读查看学校脱敏运行摘要
python3 scripts/manage.py package      # 生成 Agent 安装包
```

原有独立脚本继续可用。统一入口仅使用 Python 标准库；学校安装与个人模型配置仍由可单独上传的脚本完成。

## 目录与文档

| 路径 / 文档 | 内容 |
| --- | --- |
| `frontend/` | 页面、答题交互、任务状态和草稿 |
| `backend/app/` | API、面试流程、后台任务、SQLite 与模型校验 |
| `openclaw/interviewer/` | 学校专用 Agent 工作区源码 |
| `openclaw/skills/`、`openclaw/knowledge/` | 默认 Agent 提示规则与本地题库，仍在使用 |
| `scripts/`、`tests/` | 本机管理脚本与后端 / 运维测试 |
| [本机运行与排查](docs/operations.md) | 命令速查、配置、数据、SSH 与常见问题 |
| [开发与检查](docs/development.md) | 独立启动、测试、代码与文档维护入口 |
| [学校 Agent 部署与模型配置](openclaw/DEPLOYMENT.md) | 安装、更新、个人 DeepSeek、备份与加载验证 |
| [架构与接口约定](docs/architecture.md) | 数据流、状态机、模型契约与 API |
| [验证记录](docs/verification.md) | 按日期区分本地测试、真实调用与待验收项 |
| [早期交接快照](docs/handoff-2026-11-25.md) | 选题与初期接入背景，非当前操作指南 |
| [课程要求](requirement.png) | 原始要求图片 |

本项目面向本机单用户开发与课程演示。运行数据在 `data/`，私有配置在 `.env`，均不提交；个人模型密钥由学校 OpenClaw 管理。演示数据和真实模型结果明确区分，报告用于练习反馈。
