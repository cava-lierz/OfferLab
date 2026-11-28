# 开发环境与代码组织

我把面试流程的控制放在后端。以追问为例，模型根据刚提交的回答决定是否需要补充信息，后端检查本题已经追问了几次，前端负责显示当前问题。修改提示词能调整面试官关注的内容，每道主问题的次数限制则由同一套后端规则执行。

## 源码职责

| 模块 | 主要文件 | 职责 |
| --- | --- | --- |
| 页面与答题 | `frontend/src/App.tsx`、`pages/InterviewPage.tsx`、`components/AnswerComposer.tsx` | 导航与历史概要、当前问题、答题输入与提交。样式在 `styles.css` 和 `generation.css`。 |
| 草稿与页面状态 | `frontend/src/drafts.ts`、`hooks.ts`、`session.ts` | 保存未提交文字，轮询后台进度，按版本合并响应，避免旧查询覆盖新回答。 |
| 接口与流程控制 | `backend/app/main.py`、`engine.py` | 校验请求字段，检查题目 ID 和追问次数，推进面试状态并生成 Markdown 导出。 |
| 后台执行与存储 | `backend/app/jobs.py`、`store.py` | 领取任务、写入 SQLite、处理并发和重启恢复。 |
| 模型输入与输出 | `backend/app/provider.py`、`validation.py` | 构造各阶段的模型请求，校验题目、决策、备课来源、评分和引文。前端对应的数据类型在 `frontend/src/types.ts`。 |

演示题库保存在 `openclaw/knowledge/general.json`。默认 Agent 使用本机后端随请求发送的规则，源码在 `openclaw/skills/interviewer/SKILL.md`。学校专用 Agent 从自己的工作区读取 `AGENTS.md`、Skill 和参考资料，对应源码在 `openclaw/interviewer/`。专用面试官的规则更新需要重新打包部署，学校工作区才会加载新版本。[学校 Agent 部署](../openclaw/DEPLOYMENT.md) · [架构与接口约定](architecture.md)

## 开发环境

开发环境使用 Bash、Python 3.11+（含 venv 和 pip）、Node.js 22.12+ 及 npm。首次安装需要访问包源。开发服务从项目根目录启动。

```bash
python3 scripts/manage.py dev --reload
```

Vite 在 `127.0.0.1:5173` 提供页面热更新，FastAPI 在 `127.0.0.1:8000` 提供 API，`--reload` 使后端能加载修改后的 Python 代码。启动终端收到 Ctrl+C 后同时关闭两个服务。首次缺少配置时使用演示模式，其余情况沿用已有配置。[开发页面](http://127.0.0.1:5173) · [本机接口文档](http://127.0.0.1:8000/docs) · [运行配置](operations.md)

## 本地测试与构建

依赖安装入口是 `python3 scripts/manage.py setup`，前端优先按 `frontend/package-lock.json` 执行 `npm ci`。完整检查使用项目根目录的统一命令。

```bash
python3 scripts/manage.py check
```

Python 测试覆盖追问上限、重复提交、队列恢复、引文校验和 API 返回，也覆盖安装器更新、回滚和打包文件范围。前端测试覆盖题目逐一展示、加载状态、草稿和旧响应处理。随后执行 TypeScript 检查与 Vite 构建，产物在 `frontend/dist/`。运行构建产物需要配套的 FastAPI 服务和同源 `/api` 代理。

后端测试也有独立入口。

```bash
.venv/bin/python -m unittest discover -s tests -v
```

系统 Python 也可以执行同一条 unittest 命令。第三方依赖缺失时，部分 API 或 PDF 集成测试会跳过，测试摘要会列出跳过情况。前端独立检查在 `frontend/` 下执行。

```bash
cd frontend
npm test
npm run build
```

接口测试在进程内驱动 ASGI 应用，前端自动测试使用 Node 和 React 服务端渲染。浏览器操作使用实际页面另行验收，学校工具使用真实场次的运行轨迹验证。`python3 scripts/manage.py gateway-check` 会单独发起一次最小模型请求。[验证记录](verification.md)

## 文档维护

项目概览与启动入口在 [README](../README.md)。本机命令及配置归入[运行手册](operations.md)，面试状态和接口字段归入[架构约定](architecture.md)。[部署说明](../openclaw/DEPLOYMENT.md) 随学校安装包分发。[验证记录](verification.md) 按日期保留实际运行的环境和结果，[早期交接](handoff-2026-11-25.md) 保留选题当天的设计背景。
