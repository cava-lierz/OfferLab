# 本机运行与排查

本文是日常操作的入口；学校端安装与模型配置见 [部署说明](../openclaw/DEPLOYMENT.md)，代码结构见 [架构约定](architecture.md)。以下命令在项目根目录运行。

## 命令速查

统一入口为 `python3 scripts/manage.py <命令>`，用 `--help` 或 `<命令> --help` 查看说明。入口只负责调度现有脚本，切换到项目根目录并保留退出码和 Ctrl+C 行为；也可从任意目录使用脚本的绝对路径。

| 命令 | 执行位置与作用 | 底层脚本 / 产物 |
| --- | --- | --- |
| `setup` | 本机：安装依赖，缺少时创建 `.env` | `scripts/setup.sh` |
| `dev` | 本机：同时启动前后端，缺依赖时自动安装 | `scripts/dev.sh` |
| `check` | 本机：后端测试、前端测试及构建，不调用模型 | `scripts/check.sh`；`frontend/dist/` |
| `tunnel` | 本机：保持 SSH 隧道前台运行 | SSH 别名 `openclaw`；本机 18790 → 学校 18789 |
| `gateway-config` | 本机：隐藏输入 Token，切到真实模式 | `scripts/configure_gateway.py`；私有 `.env` |
| `gateway-check` | 本机：健康检查及一次真实模型调用 | `scripts/check_gateway.py`；`data/gateway-check.json` |
| `runs` | 本机：通过 SSH 只读获取学校运行摘要 | `scripts/inspect_openclaw_runs.py --ssh`；`data/openclaw-runs.json` |
| `package` | 本机：生成部署包，不上传 | `scripts/package_interviewer.py`；`data/offerlab-interviewer.tar.gz` |

学校端专用脚本：`openclaw/install_interviewer.py` 安装或更新 Agent，`scripts/configure_deepseek.py` 配置个人模型或更新密钥。二者保持可单独上传、仅依赖 Python 标准库，具体参数见部署说明。`inspect_openclaw_runs.py` 不加 `--ssh` 时读取执行机器的 `~/.openclaw`，不要把本机空结果当作学校状态。

现有脚本路径继续可用。维护时在底层脚本修改业务逻辑，在 `manage.py` 维护命令入口，在本文维护本机操作；学校操作仅维护部署说明。

## 启动与停止

```bash
python3 scripts/manage.py dev
```

访问 http://127.0.0.1:5173，接口文档为 http://127.0.0.1:8000/docs。保持终端运行，Ctrl+C 同时停止前后端。排队任务在下次启动后继续；运行中的生成标记中断，回到原记录重试。修改后端配置或代码后重启。

## 运行模式与配置

后端读取项目根目录的 `.env`。配置示例见 [.env.example](../.env.example)，修改后需要重启后端。

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
python3 scripts/manage.py tunnel
```

保持该终端运行。如果隧道已经在线，无需重复启动。

**2. 配置 Gateway Token**

```bash
python3 scripts/manage.py gateway-config
```

脚本以隐藏输入方式读取 Token，写入权限为 `600` 的 `.env`，同时将模式设为 `openclaw`。这里使用的是 **Gateway Token**；模型 API Key 继续由学校 OpenClaw 管理。

Token 不应提交到仓库，也不能放在前端 `VITE_*` 环境变量中。

**3. 检查真实模型连接**

```bash
python3 scripts/manage.py gateway-check
```

脚本检查健康接口并发起一次完整模型请求，将脱敏结果写入 `data/gateway-check.json`。`completion_present: true` 表示本次完整调用成功；健康接口成功本身不代表模型调用成功。检查结果不包含 Token 或模型响应正文。

**4. 重启项目并新建面试**

```bash
python3 scripts/manage.py dev
```

确认前端标记为「OpenClaw 模式」，再走完计划、回答、追问和报告流程，验证真实模型输出符合应用约定。

当前适配沿用学校已验证的 OpenClaw `2026.5.22` 接口：`model: "openclaw"`、`stream: false` 和 `/v1/chat/completions`。默认 Agent 路径继续将本地 `openclaw/skills/` 中的规则作为系统提示发送。

### 当前个人 DeepSeek 配置

2026-11-26，开发者确认已切换个人 DeepSeek，响应明显加快。实际模型 ID 以学校配置和新的脱敏运行摘要为准，配置脚本的默认值不能作为已部署模型的证据。

本机仍使用 `OPENCLAW_MODEL=openclaw`；专用 Agent 路由设置 `OPENCLAW_AGENT_ID=interviewer`。个人 API Key 存在学校配置中，Gateway Token 存在本机 `.env`。已有接入不需要重复执行首次配置；更换密钥、更新 Agent 源码等操作见部署说明。

## 生成等待与恢复

创建面试会先保存材料并生成计划，准备页只展示问题数量，开始后逐题作答。提交回答后仍由模型判断题内追问；本题结束后点击“下一题”，立即打开下一道预设大题，同时在后台分析上一组完整问答。最后一题结束后由用户点击生成复盘；提前结束会直接生成报告。

- 页面只展示加载图标，不展示秒数、排队说明或模型处理阶段。生成中的任务约每 1.5 秒查询一次，后台标签页降低查询频率。
- 可以切换到历史记录、新建练习或刷新页面。生成由本机后端继续执行，因此后端及 SSH 隧道需要保持运行。
- 等待期间可检查材料或回看已保存回答。失败后在原记录重新生成，不会重复提交回答。
- 状态查询断网会单独提示并自动重连；不会把暂时无法查询误判成模型失败。旧查询结果不会覆盖较新的回答或报告。
- 后端每进程有 2 个前台任务 Worker，另有 1 个分题复盘 Worker；分题复盘不锁住当前面试，答题可以继续。排队记录持久化；运行中断后保留材料与回答，允许显式重试，避免重启时自动重复调用模型。

总报告复用已完成的分题分析，尚未完成或失败的部分直接依据原始回答处理。该方式可把部分复盘耗时与答题重叠，但每个已切换大题会增加一次模型调用；真实速度需结合模型服务的并发能力验收。

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

为当前 Python 安装对应的虚拟环境支持。Ubuntu 通常使用 `python3-venv`，安装后重新执行 `python3 scripts/manage.py setup`。

**前端可以打开，但接口请求失败**

检查后端启动终端是否报错，访问 `http://127.0.0.1:8000/api/health`。默认前端代理目标是端口 `8000`；修改后端端口时，需要同步调整 `frontend/vite.config.ts`。

**启动提示端口被占用**

检查是否已经运行一键启动脚本或独立开发服务。停止原有进程后再启动，避免同时运行两套前后端。

**切换模式后仍然显示演示记录**

修改 `.env` 后重启后端，再创建新面试。历史记录保留各自创建时的模式。

**OpenClaw 连接失败或请求超时**

确认隧道终端仍在运行、Token 已配置，并执行接入检查脚本。模型失败后，已提交回答仍会保留，可以在面试页面重试。

检查脚本会分别显示健康检查和最小模型调用阶段，并记录耗时。若最小调用成功但面试计划超时，需继续排查完整计划请求，不能直接认定为 Token 或隧道故障。前端等待时只显示加载图标；后端终端输出 `OpenClaw start/end`、任务类型和耗时，不记录 Token、简历或模型响应正文。

**PDF 无法提取文本**

首版仅支持未加密的文本型 PDF，最多 20 页、5 MB。扫描件需要先进行 OCR，或直接粘贴简历文本。

最小模型调用成功但面试仍失败时，执行 `python3 scripts/manage.py runs` 查看实际 Agent、模型、工具调用与中止记录。该命令不发起新模型请求。完整验收步骤见 [验证记录](verification.md)。
