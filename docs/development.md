# 开发与检查

环境：Bash、Python 3.11+（含 venv/pip）、Node.js 22.12+ 和 npm。首次依赖安装需要访问包源。所有命令在项目根目录运行。

## 独立启动与热更新

先安装依赖：

```bash
python3 scripts/manage.py setup
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

## 测试与构建

安装依赖后，运行完整检查：

```bash
python3 scripts/manage.py check
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

真实 OpenClaw 连接检查独立于本地测试，使用 `python3 scripts/manage.py gateway-check` 执行。历史测试结果与人工验收步骤见 [验证记录](verification.md)，不能用演示测试代替真实模型验收。

## 修改入口

| 修改内容 | 位置 |
| --- | --- |
| 页面与交互 | `frontend/src/pages/`、`components/`、`styles.css` |
| 轮询、版本防回退与草稿 | `frontend/src/hooks.ts`、`session.ts`、`drafts.ts` |
| API 与输入校验 | `backend/app/main.py` |
| 面试流程、次数限制、导出 | `backend/app/engine.py` |
| 后台任务、持久化与恢复 | `backend/app/jobs.py`、`store.py` |
| 模型请求、输出与证据校验 | `backend/app/provider.py`、`validation.py` |
| 默认 Agent 的系统提示与演示题库 | `openclaw/skills/interviewer/`、`openclaw/knowledge/general.json` |
| 学校专用 Agent 的规则和参考资料 | `openclaw/interviewer/`（修改前阅读其中 AGENTS.md） |
| 本机脚本与命令调度 | `scripts/`，命令表见 [运维说明](operations.md) |

两套面试规则分别用于默认 Agent 提示注入和学校专用 Agent 文件读取，仍有运行用途，不能当成冗余文件删除。后端数据结构调整时同步更新 `frontend/src/types.ts` 与相关校验；接口与状态机见 [架构约定](architecture.md)。

前端依赖锁保留在 `frontend/package-lock.json`，安装脚本优先使用 `npm ci`。本轮整理未更新依赖版本。

## 文档维护

- README 只维护项目概览、快速启动与文档导航。
- `docs/operations.md` 维护本机配置、命令、运行数据和排查流程。
- `openclaw/DEPLOYMENT.md` 维护学校端安装、模型切换与备份；该文件随安装包分发，学校端步骤应可独立阅读。
- `docs/architecture.md` 维护实现、状态和接口契约。
- `docs/verification.md` 按日期记录实际验证及尚未覆盖的部分。
- 早期交接记录只用于追溯，不能作为当前操作指令或继续开发清单。
