# 本机运行与运维说明

我把前后端和面试数据库放在本机，保留两种运行配置。课程演示使用本地题库即可完成问答和复盘。真实模型模式在同一套页面上运行，通过学校 Gateway 生成问题与反馈。

## 本机启动

项目依赖 Bash、Python 3.11+（含 venv 和 pip）、Node.js 22.12+ 及 npm。前后端通过项目根目录的同一条命令启动。

```bash
python3 scripts/manage.py dev
```

脚本在依赖缺失时安装依赖，在缺少 `.env` 时按模板创建演示配置。首次安装需要访问包源。前端运行在 5173 端口，FastAPI 运行在 8000 端口。页面内置「使用示例体验」入口，可填入虚构简历与 JD。启动终端收到 Ctrl+C 后同时停止两个服务。[面试页面](http://127.0.0.1:5173) · [API 文档](http://127.0.0.1:8000/docs)

## 学校模型接入

学校 Gateway 只监听容器的回环地址。本机使用已有的 SSH 别名 `openclaw` 做端口转发。隧道与应用分别占用一个终端，已有的同一条隧道可以复用。

| 环节 | 执行位置与命令 | 结果 |
| --- | --- | --- |
| 建立隧道 | 本机终端一，`python3 scripts/manage.py tunnel` | 将本机 `127.0.0.1:18790` 转发到学校 `127.0.0.1:18789`，终端在使用期间保持运行。 |
| 配置认证 | 本机终端二，`python3 scripts/manage.py gateway-config` | 隐藏输入 Gateway Token，脚本写入权限为 `600` 的 `.env` 并将模式设为 `openclaw`。模型提供商的 API Key 由学校保管。 |
| 指定 Agent | 本机 `.env`，`OPENCLAW_AGENT_ID=interviewer` | 目标为学校已安装的专用面试官，留空时使用默认 Agent。[学校 Agent 部署](../openclaw/DEPLOYMENT.md) |
| 验证连接 | 本机终端二，`python3 scripts/manage.py gateway-check` | 先探测健康接口，再发起一次模型调用。`data/gateway-check.json` 中的 `completion_present: true` 表示收到了模型回复。 |
| 加载配置 | 本机应用终端，停止已有进程后运行 `python3 scripts/manage.py dev` | 页面显示「OpenClaw 模式」，新面试采用学校模型。切回演示时，`OFFERLAB_MODE=demo` 同样在重启后对新场次生效。 |

Gateway Token 只在后端使用。Vite 的 `VITE_*` 变量会进入浏览器，因此前端配置只承载公开信息。

## 环境变量

后端启动时加载根目录的 `.env`。项目随附的模板列出了下面的默认值。[配置模板](../.env.example)

| 配置项 | 默认值 | 用途 |
| --- | --- | --- |
| `OFFERLAB_MODE` | `demo` | 决定新面试采用本地规则或学校模型 |
| `OPENCLAW_BASE_URL` | `http://127.0.0.1:18790` | 后端到隧道的入口 |
| `OPENCLAW_TOKEN` | 空 | Gateway 用它认证本机后端 |
| `OPENCLAW_MODEL` | `openclaw` | 学校兼容接口接受的模型入口名，具体提供商在学校配置 |
| `OPENCLAW_AGENT_ID` | 空 | 安装专用面试官后填 `interviewer` |
| `OPENCLAW_TIMEOUT` | `120` 秒 | 计划和追问的请求总时限，范围 5–150 秒 |
| `OPENCLAW_REPORT_TIMEOUT` | `300` 秒 | 复盘请求总时限，范围 30–600 秒，排队另计 |
| `OFFERLAB_DATA_DIR` | `data` | 面试数据库目录，相对路径从项目根目录算起 |

## 练习记录与草稿

准备页尚未提交的材料保存在页面内存中。简历文件只用于提取文本，候选人可在创建面试前核对解析结果。创建后，简历文本、问答和报告写入本机 SQLite，默认路径为 `data/offerlab.sqlite3`。答题草稿保存在当前浏览器，刷新后能恢复，后端确认收到回答后才清除。

生成任务也存入数据库，关闭页面后仍可从历史记录恢复进度。模型报错时，原场次保留已提交的回答并提供重试入口。历史页确认删除单场练习后，系统清除本机的面试、关联分题复盘及当前浏览器的对应草稿，迟到的生成结果也会被丢弃。学校 Gateway 的会话由学校单独管理。

## 常见故障与诊断依据

| 现象 | 诊断与处理 |
| --- | --- |
| 安装报缺少 `venv` 或 `ensurepip` | 安装当前 Python 对应的虚拟环境支持（Ubuntu 通常为 `python3-venv`），再运行 `python3 scripts/manage.py setup`。 |
| 启动时报端口占用 | 通常是已有开发服务占用了端口。可复用原进程，或停止后重新启动。 |
| 页面能打开，提交失败 | 访问 [本机健康接口](http://127.0.0.1:8000/api/health)，查看后端终端。若改过 API 端口，同时核对 `frontend/vite.config.ts` 的代理目标。 |
| 健康接口可用，真实调用失败 | 确认隧道在线，再跑 `gateway-check`。健康探测和模型调用分别计时，认证失败时核对 Gateway Token。 |
| 最小调用成功，计划或报告生成超时 | 后端终端的 `OpenClaw start/end` 会记录任务、结果和耗时。运行 `python3 scripts/manage.py runs`，核对学校端实际的 Agent、模型、工具调用和中止位置，再回原场重试。[验证记录](verification.md) |
| 简历提取失败 | TXT 使用 UTF-8。PDF 需为未加密、最多 20 页的文本型文件，上传上限 5 MB。扫描件可先做 OCR，或直接粘贴 20–20000 字简历文本。 |

## 命令速查

所有命令共用 `python3 scripts/manage.py <命令>`。加 `--help` 可查看帮助。从项目外也可使用脚本的绝对路径，入口会自行切回项目根目录。

| 命令 | 作用与产物 |
| --- | --- |
| `setup` | 安装依赖到 `.venv/` 和 `frontend/node_modules/`，下载缓存位于 `.cache/`。前端优先使用锁文件和 `npm ci`。 |
| `dev [--reload]` | 同时启动前后端，修改后端代码时可用 `--reload` 自动重载。 |
| `check` | 运行后端、前端测试与生产构建，静态文件在 `frontend/dist/`。 |
| `tunnel` | 在前台保持 SSH 转发，Ctrl+C 关闭该隧道。 |
| `gateway-config` | 在本机交互终端录入 Token，更新私有 `.env`。 |
| `gateway-check` | 发起一次真实模型请求，将脱敏结果写入 `data/gateway-check.json`。 |
| `runs` | 经 SSH 读取已有运行记录，将脱敏摘要写入 `data/openclaw-runs.json`。底层 `scripts/inspect_openclaw_runs.py` 单独执行时需加 `--ssh` 才读取学校记录。 |
| `package` | 在本机生成 `data/offerlab-interviewer.tar.gz`，供单独上传部署。 |
