# OfferLab · AI 模拟面试与复盘系统

OfferLab 是我们为《大模型与智能体工程实践》课程开发的项目，面向求职准备场景，提供基于简历和目标岗位的文字模拟面试。

我们希望把“练习回答”和“根据反馈改进”连接起来：系统围绕候选人的经历提问，根据回答继续追问，并在结束后生成带有原文依据的复盘报告，帮助使用者发现表达中的不足，明确下一次练习的重点。

项目采用 **React + FastAPI + SQLite** 架构，前后端在本机运行，通过 SSH 隧道调用学校部署的 **OpenClaw**。首版以文字面试为主，支持演示模式和真实模型模式。

当前已验证基础模型调用、真实面试计划生成，以及专用 `interviewer` Agent 的安装、HTTP 路由和 Skill / 评价标准读取。完整报告曾出现模型等待超时，正在继续验证真实流程的稳定性。应用已将模型生成改为后台任务，页面可离开、刷新并恢复状态。具体证据与验收边界见 [验证记录](docs/verification.md)。

## 功能概览

| 功能 | 说明 |
| --- | --- |
| 面试准备 | 上传简历或粘贴文本，填写目标岗位和可选的岗位描述（JD） |
| 简历解析 | 支持 UTF-8 TXT 和文本型 PDF，解析后可检查并修改文本 |
| 面试计划 | 根据材料生成计划，确认后开始面试 |
| 对话面试 | 每次展示一道题，支持 1–5 道主问题，每题最多追问两次 |
| 面试恢复 | 保存已提交回答，浏览器保留答题草稿，通过历史记录继续练习 |
| 后台生成 | 保存后立即确认，展示排队、生成与校验状态；刷新或离开页面后仍可查看结果 |
| 异常恢复 | 模型调用失败后保留回答，支持重试并防止重复提交 |
| 复盘报告 | 从表达结构、项目深度、岗位匹配和反思能力四个维度提供反馈 |
| 回答证据 | 检查报告引文是否确实来自对应回答，拒绝保存不匹配的引文 |
| 导出与再练习 | 导出 Markdown 报告，或携带某一维度的练习目标创建新面试 |

完整流程：

```text
准备简历与岗位 → 生成并确认计划 → 逐题回答与追问 → 生成复盘 → 导出或重新练习
```

当前首版不包含语音、视频、岗位网页自动抓取和外部资料检索。报告会注明未进行外部查证，面试评价仅用于训练反馈，不代表真实招聘录用概率。

## 技术架构

| 层级 | 技术 | 职责 |
| --- | --- | --- |
| 前端 | React、TypeScript、Vite、Tailwind CSS | 材料输入、面试交互、报告与历史记录展示 |
| 后端 | Python、FastAPI、Pydantic | 接口校验、面试状态控制、简历解析、模型调用与报告校验 |
| 数据存储 | SQLite、本地文件 | 保存面试材料、问答、报告和接入检查结果 |
| 智能体服务 | 学校 OpenClaw | 根据材料生成计划、判断追问并输出复盘 |
| 连接方式 | SSH 本地端口转发 | 将本机后端接入学校 Gateway |

```text
本机浏览器
    │
    ▼
React 前端 · 127.0.0.1:5173
    │ /api 请求，由 Vite 代理
    ▼
FastAPI 后端 · 127.0.0.1:8000
    ├── SQLite · data/offerlab.sqlite3
    │
    └── OpenClaw 模式
            │
            ▼
        本机隧道入口 · 127.0.0.1:18790
            │ SSH
            ▼
        学校 Gateway · 127.0.0.1:18789
            │
            ▼
        OpenClaw Agent 与已配置模型
```

**前端和后端都运行在开发电脑上；OpenClaw 和模型接入配置位于学校服务器。** 演示模式不调用学校服务。

## 开发环境

- Bash 终端；现有脚本按 Linux/macOS 的目录和虚拟环境结构编写。
- Python 3.11+，具备 `venv` 和 `pip` 支持。
- Node.js 22.12+ 和 npm。
- 首次安装依赖时需要能够访问 Python 和 npm 包源。
- 使用真实模型时，需要可用的学校 SSH 连接和 OpenClaw Gateway Token。

所有命令如无特别说明，均在项目根目录执行。

## 本地启动

### 同时启动前后端

```bash
bash scripts/dev.sh
```

脚本会检查依赖；依赖缺失时自动调用安装脚本，再同时启动前后端。首次安装会创建 Python 虚拟环境 `.venv`，并在不存在 `.env` 时从 `.env.example` 创建配置，默认使用演示模式。

启动后访问：

| 地址 | 用途 |
| --- | --- |
| http://127.0.0.1:5173 | 前端应用入口 |
| http://127.0.0.1:8000/docs | FastAPI 接口文档与调试页面 |
| http://127.0.0.1:8000/api/health | 后端健康状态与运行模式 |

保持启动终端打开，在浏览器中使用应用。在该终端按 `Ctrl+C` 会同时停止前后端，已经保存的面试记录不会删除。排队任务在下次启动后继续；运行中的模型调用会标记为中断，可回到原记录重新生成。开发时 `--reload` 同样会中断正在生成的任务。下次启动执行相同命令即可。

### 分别启动，便于开发调试

先安装依赖：

```bash
bash scripts/setup.sh
```

终端一，在项目根目录启动后端，开启代码修改后自动重载：

```bash
.venv/bin/python -m uvicorn backend.app.main:app \
  --host 127.0.0.1 --port 8000 --reload
```

终端二，进入前端目录启动 Vite：

```bash
cd frontend
npm run dev
```

Vite 提供前端热更新，并将 `/api` 请求转发到 `127.0.0.1:8000`。一键启动脚本未开启后端自动重载；修改后端代码后需要重启，或使用上述独立启动方式。

两种启动方式选择一种即可，避免重复占用端口。

## 运行模式与配置

后端读取项目根目录的 `.env`。配置示例见 [.env.example](.env.example)，修改后需要重启后端。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `OFFERLAB_MODE` | `demo` | `demo` 为演示模式，`openclaw` 为真实模型模式 |
| `OPENCLAW_BASE_URL` | `http://127.0.0.1:18790` | 后端访问 Gateway 的基础地址 |
| `OPENCLAW_TOKEN` | 空 | Gateway 认证 Token，仅保存在后端私有配置中 |
| `OPENCLAW_MODEL` | `openclaw` | Gateway 兼容接口的入口标识；实际模型由学校 Agent 配置决定 |
| `OPENCLAW_AGENT_ID` | 空 | 留空使用默认 Agent；云端安装后设为 `interviewer` |
| `OPENCLAW_TIMEOUT` | `120` | 计划与追问请求总时限，限制在 5–150 秒 |
| `OPENCLAW_REPORT_TIMEOUT` | `300` | 复盘请求总时限，限制在 30–600 秒；排队时间另计 |
| `OFFERLAB_DATA_DIR` | `data` | 数据目录；相对路径以项目根目录为基准 |

### 演示模式

演示模式使用本地固定题库和规则，适合界面开发、流程调试和演示备份，不需要 Token 或 SSH 隧道。

前端点击「使用示例体验」可以填入虚构简历与 JD。演示复盘展示报告结构和回答引文，不进行能力评分，也不代表实时模型评价。

### OpenClaw 模式

真实模式通过学校 Gateway 生成问题和反馈。每场面试固定使用创建时的模式；切换配置后需要新建面试，已有演示记录不会变成真实模型记录。真实调用失败会显示错误，不会自动替换为演示回复。

接入步骤如下。

**1. 建立 SSH 隧道**

本地 SSH 配置需要已有可用的 `openclaw` 主机别名。在单独终端运行：

```bash
ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -L 127.0.0.1:18790:127.0.0.1:18789 \
  openclaw
```

保持该终端运行。如果隧道已经在线，无需重复启动。

**2. 配置 Gateway Token**

```bash
python3 scripts/configure_gateway.py
```

脚本以隐藏输入方式读取 Token，写入权限为 `600` 的 `.env`，同时将模式设为 `openclaw`。这里使用的是 **Gateway Token**；模型 API Key 继续由学校 OpenClaw 管理。

Token 不应提交到仓库，也不能放在前端 `VITE_*` 环境变量中。

**3. 检查真实模型连接**

```bash
python3 scripts/check_gateway.py
```

脚本检查健康接口并发起一次完整模型请求，将脱敏结果写入 `data/gateway-check.json`。`completion_present: true` 表示本次完整调用成功；健康接口成功本身不代表模型调用成功。检查结果不包含 Token 或模型响应正文。

**4. 重启项目并新建面试**

```bash
bash scripts/dev.sh
```

确认前端标记为「OpenClaw 模式」，再走完计划、回答、追问和报告流程，验证真实模型输出符合应用约定。

当前适配沿用学校已验证的 OpenClaw `2026.5.22` 接口：`model: "openclaw"`、`stream: false` 和 `/v1/chat/completions`。默认 Agent 路径继续将本地 `openclaw/skills/` 中的规则作为系统提示发送。

### 专用面试官 Agent

我们将面试官组织为独立的 `interviewer` Agent：它根据当前任务和候选人回答决定如何提问、是否追问以及怎样评价，并通过工具读取所需参考资料。后端继续负责持久化、题数限制、重复提交保护和引文校验。

| 组成 | 项目中的职责 |
| --- | --- |
| Agent 配置 | 在学校 `openclaw.json` 中注册 `interviewer`，指定独立工作区、模型、Skill 和工具权限；保留 `main` 默认路由 |
| 工作区规则 | `AGENTS.md` 定义执行规则，`SOUL.md` 定义角色与反馈原则；身份、调用方说明及后台任务约定分别放在其他工作区文件中 |
| `offerlab-interviewer` Skill | 定义 `plan`、`decision`、`report` 三个阶段的步骤、资料读取时机和 JSON 输出契约 |
| `read` 工具 | 读取工作区内的 Skill、题库和评价标准；配置仅允许该工具，并限制文件访问范围 |
| 题库与评价标准 | `questions.json` 提供主题与追问框架，`rubric.json` 提供四维评价及证据要求 |

各阶段的预期行为为：

```text
plan     → 读取 Skill 与题库 → 结合简历和 JD 选择、改写问题
decision → 分析当前回答缺口 → 必要时读取追问框架 → 决定追问或换题
report   → 读取评价标准 → 引用回答原文 → 输出四维复盘
```

首版实际开放的工具只有 `read`。题库与评价标准是工具读取的资料，不是另外注册的搜索函数。当前没有加入浏览器、外部检索或命令执行工具。专用 Agent 的作用是明确职责与工具范围，延迟变化需要实际测量。

工作区源码位于 [`openclaw/interviewer/`](openclaw/interviewer/)，云端目标位置为 `~/.openclaw/workspace-interviewer/`。本地准备的配置继续使用学校现有默认模型 `sjtu/deepseek-reasoner`，没有更换模型。

部署时，在本机运行：

```bash
python3 scripts/package_interviewer.py
```

生成的 `data/offerlab-interviewer.tar.gz` 仅包含明确列出的工作区源码、安装脚本和部署说明。上传到学校后，安装器基于服务器的最新配置执行校验、备份与增量合并。上传命令、学校端安装和加载检查见 [面试官 Agent 部署说明](openclaw/DEPLOYMENT.md)。

云端安装并验证后，在本机 `.env` 设置：

```dotenv
OPENCLAW_AGENT_ID=interviewer
```

重启后端即可切换。适配器通过 `x-openclaw-agent-id` 指定 Agent，并允许它读取专用 Skill 与资料；留空时继续使用原默认 Agent 路径。健康接口返回的 `agent_id` 表示本机配置的调用目标，真实路由、Skill 加载和 `read` 调用仍需通过学校运行记录验证。

## 长时间生成时的交互

创建面试会先保存材料并排队生成计划；提交回答会先保存回答，再排队生成下一题。接口及时返回，不再让浏览器等待完整模型调用。自然答完后仍由用户点击生成复盘；提前结束会直接排队生成报告。

- 页面展示实际的排队、等待模型、校验结果状态与耗时，不显示模拟进度百分比。生成中的任务约每 1.5 秒查询一次，后台标签页降低查询频率。
- 可以切换到历史记录、新建练习或刷新页面。生成由本机后端继续执行，因此后端及 SSH 隧道需要保持运行。
- 等待期间可检查材料或回看已保存回答。失败后在原记录重新生成，不会重复提交回答。
- 状态查询断网会单独提示并自动重连；不会把暂时无法查询误判成模型失败。旧查询结果不会覆盖较新的回答或报告。
- 后端每进程最多同时执行 2 个生成任务，其余排队。排队记录持久化；运行中断后保留材料与回答，允许显式重试，避免重启时自动重复调用模型。

这些改动改善保存反馈、等待与恢复体验。模型仍由学校 OpenClaw 执行，后台任务本身不缩短模型推理耗时。

## 项目结构

```text
.
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 接口与配置加载
│   │   ├── engine.py            # 面试流程、状态推进与报告导出
│   │   ├── store.py             # SQLite 快照、并发租约与中断恢复
│   │   ├── jobs.py              # 后台任务队列、有限并发与 Worker 心跳
│   │   ├── provider.py          # 演示模式和 OpenClaw 适配
│   │   ├── resume.py            # TXT / PDF 简历解析
│   │   └── validation.py        # 模型输出与报告引文校验
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx             # 应用外壳、导航与历史概要
│   │   ├── pages/              # 准备、面试、历史页面
│   │   ├── components/         # 生成状态、回答编辑、问答记录与报告
│   │   ├── hooks.ts            # 自动轮询、路由与短请求状态
│   │   ├── session.ts          # 状态文案与快照版本比较
│   │   ├── drafts.ts           # 按面试和问题隔离的浏览器草稿
│   │   ├── api.ts              # 后端请求封装
│   │   ├── types.ts            # 接口数据类型
│   │   ├── generation.css      # 后台生成状态样式
│   │   └── styles.css          # 页面样式与响应式布局
│   ├── tests/                 # 长任务状态、版本防回退与草稿测试
│   ├── package.json
│   └── vite.config.ts          # 前端服务与 API 代理配置
├── openclaw/
│   ├── interviewer/            # 专用 Agent 工作区源码（角色、Skill、参考资料）
│   ├── install_interviewer.py  # 副本准备及云端增量安装
│   ├── knowledge/general.json  # 通用题库与评价标准
│   └── skills/interviewer/     # 面试官 Skill 源码
├── scripts/                    # 安装、启动、检查与配置脚本
├── tests/                      # 核心逻辑与 API 集成测试
├── docs/                       # 架构说明、验证和历史记录
├── data/                       # 本地运行数据，不提交
├── .cache/                     # 依赖下载缓存，不提交
├── .env.example                # 可提交的配置模板
└── README.md
```

开发时，页面与交互主要修改 `frontend/src/`；面试状态和次数限制修改 `engine.py`；模型调用修改 `provider.py`。默认 Agent 路径的规则和题库位于 `openclaw/skills/`、`openclaw/knowledge/`；专用 Agent 的规则和参考资料在 `openclaw/interviewer/` 中维护。后端修改数据结构时，需要同步更新前端 `types.ts` 和相关校验。

## 测试与构建

安装依赖后，运行完整检查：

```bash
bash scripts/check.sh
```

检查内容包括后端流程、后台任务与 ASGI 接口测试，前端等待状态、快照版本和草稿测试，以及 TypeScript 类型检查与 Vite 生产构建。接口测试使用进程内传输，不需要学校服务；真实浏览器与 Gateway 验收另行进行。

也可以分别执行：

```bash
# 后端测试，在项目根目录运行
.venv/bin/python -m unittest discover -s tests -v

# 前端测试、类型检查与构建
cd frontend
npm test
npm run build
```

未安装后端依赖时，可通过 `python3 -m unittest discover -s tests -v` 运行不依赖第三方库的核心测试，API/PDF 集成测试会明确跳过。测试覆盖追问上限、重复提交、会话隔离、失败恢复、并发控制和报告引文校验，也覆盖 Agent 路由、安装失败回滚、重复安装、原配置保留和打包文件范围。

前端构建产物位于 `frontend/dist/`。这些静态文件仍需配合 FastAPI 后端和 `/api` 代理使用，不能单独提供完整面试服务。

真实 OpenClaw 连接检查独立于本地测试，使用 `python3 scripts/check_gateway.py` 执行。历史测试结果与人工验收步骤见 [验证记录](docs/verification.md)，不能用演示测试代替真实模型验收。

## 数据与依赖管理

- **运行数据**：默认保存在 `data/offerlab.sqlite3`，包含简历解析文本、JD、问答和报告；简历原文件不保存。
- **回答保存**：提交后先写入数据库，再请求模型。答题草稿按面试和问题保存在当前浏览器的 localStorage，服务端确认保存后清除；浏览器禁止存储时会明确提示。准备页尚未提交的材料仍只保留在当前应用内存中。
- **材料传输**：OpenClaw 模式会将面试材料与回答发送到学校 Gateway，供模型生成问题和反馈。
- **私有配置**：`.env`、数据目录和日志已配置 Git 忽略规则；用于本地检查的完整云端副本 `openclaw/.openclaw/` 也被忽略，不进入部署安装包。
- **项目依赖**：Python 包安装到 `.venv/`，前端包安装到 `frontend/node_modules/`。
- **下载缓存**：安装脚本使用 `.cache/pip/` 和 `.cache/npm/`；在 `frontend/` 中手动执行 npm 也使用项目缓存。此前已有的全局缓存不会迁移或清理。
- **依赖锁定**：保留 `frontend/package-lock.json`。存在锁文件时，安装脚本使用 `npm ci`。

当前应用面向本机单用户开发和课程演示，前后端仅监听 `127.0.0.1`，尚未实现多用户认证与公网部署方案。

## 常见问题

**首次安装提示缺少 `venv` 或 `ensurepip`**

为当前 Python 安装对应的虚拟环境支持。Ubuntu 通常使用 `python3-venv`，安装后重新执行 `bash scripts/setup.sh`。

**前端可以打开，但接口请求失败**

检查后端启动终端是否报错，访问 `http://127.0.0.1:8000/api/health`。默认前端代理目标是端口 `8000`；修改后端端口时，需要同步调整 `frontend/vite.config.ts`。

**启动提示端口被占用**

检查是否已经运行一键启动脚本或独立开发服务。停止原有进程后再启动，避免同时运行两套前后端。

**切换模式后仍然显示演示记录**

修改 `.env` 后重启后端，再创建新面试。历史记录保留各自创建时的模式。

**OpenClaw 连接失败或请求超时**

确认隧道终端仍在运行、Token 已配置，并执行接入检查脚本。模型失败后，已提交回答仍会保留，可以在面试页面重试。

检查脚本会分别显示健康检查和最小模型调用阶段，并记录耗时。若最小调用成功但面试计划超时，需继续排查完整计划请求，不能直接认定为 Token 或隧道故障。前端显示持久化任务状态与耗时，不把超时时限当成预计完成时间；后端终端输出 `OpenClaw start/end`、任务类型和耗时，不记录 Token、简历或模型响应正文。

**PDF 无法提取文本**

首版仅支持未加密的文本型 PDF，最多 20 页、5 MB。扫描件需要先进行 OCR，或直接粘贴简历文本。

## 后续计划

- 完善真实 OpenClaw 面试流程的端到端验证与输出稳定性。
- 在已验证的专用 Agent 路由基础上，对比模型和输出长度对复盘耗时的影响。
- 接入岗位网页获取、技术资料检索与可验证的来源引用。
- 根据真实测试完善演示案例、课程报告和答辩材料。

## 相关文档

- [面试官 Agent 部署、验证与切换](openclaw/DEPLOYMENT.md)
- [架构与接口约定](docs/architecture.md)
- [测试与验收记录](docs/verification.md)
- [学校环境与早期交接记录](docs/handoff-2026-11-25.md)（历史快照，不代表当前开发进度）
- [课程要求原图](requirement.png)
