# 本机运行与排查

本文是日常操作的入口；学校端安装与模型配置见 [部署说明](../openclaw/DEPLOYMENT.md)，代码结构见 [架构约定](architecture.md)。以下命令在项目根目录运行。

## 命令速查

统一入口为 `python3 scripts/manage.py <命令>`，用 `--help` 或 `<命令> --help` 查看说明。入口只负责调度现有脚本，切换到项目根目录并保留退出码和 Ctrl+C 行为；也可从任意目录使用脚本的绝对路径。

| 命令 | 执行位置与作用 | 底层脚本 / 产物 |
| --- | --- | --- |
| `setup` | 本机：安装依赖，缺少时创建 `.env` | `scripts/setup.sh` |
| `dev [--reload]` | 同时启动前后端，缺依赖时自动安装；开发时加 `--reload` | `scripts/dev.sh` |
| `check` | 本机：后端测试、前端测试及构建，不调用模型 | `scripts/check.sh`；`frontend/dist/` |
| `tunnel` | 本机：保持 SSH 隧道前台运行 | SSH 别名 `openclaw`；本机 18790 → 学校 18789 |
| `gateway-config` | 本机：隐藏输入 Token，切到真实模式 | `scripts/configure_gateway.py`；私有 `.env` |
| `gateway-check` | 本机：健康检查及一次真实模型调用 | `scripts/check_gateway.py`；`data/gateway-check.json` |
| `runs` | 本机：通过 SSH 只读获取学校运行摘要 | `scripts/inspect_openclaw_runs.py --ssh`；`data/openclaw-runs.json` |
| `package` | 本机：生成部署包，不上传 | `scripts/package_interviewer.py`；`data/offerlab-interviewer.tar.gz` |

学校端专用脚本：`openclaw/install_interviewer.py` 安装或更新 Agent，`scripts/configure_deepseek.py` 配置个人模型或更新密钥。二者保持可单独上传、仅依赖 Python 标准库，具体参数见部署说明。`inspect_openclaw_runs.py` 不加 `--ssh` 时读取执行机器的 `~/.openclaw`，不要把本机空结果当作学校状态。

## 日常启动

演示模式执行 `python3 scripts/manage.py dev`。已经接通学校 Gateway 的环境先在一个终端运行 `python3 scripts/manage.py tunnel`，再在项目终端运行 `python3 scripts/manage.py dev`。打开 `http://127.0.0.1:5173`，接口文档在 `http://127.0.0.1:8000/docs`。在应用终端按 Ctrl+C 同时停止前后端。

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

## 面试记录与运行数据

- 在“历史记录 → 最近的面试”找到目标场次。点击“删除”后可以取消，点击“确认删除”会移除本机的材料、问答、报告和分题复盘，并清理当前浏览器里该场的草稿。学校 Gateway 的会话由学校单独管理。
- 生成期间可离开页面或刷新。排队任务由后端继续处理。服务中断后，已保存的面试可在原记录重试。已删除场次的后台结果会被丢弃。
- 默认数据库为 `data/offerlab.sqlite3`；简历原文件仅用于解析。答题草稿保存在当前浏览器，提交成功后清除。未提交的准备材料只在当前页面内存中。
- 私有配置在 `.env`，模型和搜索提供商的密钥在学校端。依赖目录为 `.venv/`、`frontend/node_modules/`；下载缓存在 `.cache/`。安装脚本优先使用 `frontend/package-lock.json` 和 `npm ci`。

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
