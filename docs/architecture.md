# 实现与接口约定

## 数据流

```text
浏览器 :5173 ⇄ Vite /api 代理 ⇄ FastAPI :8000
                                  │ 保存 / 查询
                                  ▼
                       SQLite 快照与持久化任务队列
                                  │ 领取任务
                                  ▼
                       后台 Worker（每进程最多 2 个）
                                  │
                                  ▼
                       本机 SSH 隧道 :18790
                                  │
                                  ▼
                 学校 Gateway :18789 → interviewer Agent
```

开发模式和 `vite preview` 都代理 `/api`。构建产物不是独立后端，部署时需另行提供同源 API 代理；本版未发布到云端。

后端只读取根目录 `.env`，不返回凭据。HTTP 客户端设置 `trust_env=False`，避免本机代理干扰隧道。沿用学校已验证的 `model: openclaw`、Bearer 认证、`stream: false`。

每次生成使用 `offerlab-{interview_id}-{request_uuid}` 作为 `user`，提供完整且有长度上限的资料和问答快照，不依赖 Gateway 历史记忆。这会增加重复上下文的 token 消耗，但避免叠加远端与本地历史。学校版本的会话行为仍需端到端验证。

参考：[OpenClaw HTTP 接口](https://docs.openclaw.ai/gateway/openai-http-api)、[FastAPI 文档](https://fastapi.tiangolo.com/tutorial/)、[Vite 文档](https://vite.dev/guide/)。在线文档可能对应新版本，学校版本以交接记录的实测结果为准。

## 状态与持久化

```text
preparing --生成计划--> ready --确认--> active
active --先保存回答--> awaiting_next --生成追问/下一题--> active
awaiting_next --题数已达上限--> reporting --生成复盘--> completed
active / awaiting_next --提前结束--> reporting
```

创建接口保存材料并排队生成计划，返回 201 和持久化 ID。回答接口在同一次 SQLite 写入中保存回答与排队任务，返回 202，无需等待模型。`Engine.submit` 处理短操作，`Engine.process_job` 由后台线程执行一次模型调用；同步 `act` 仅作为核心测试适配器。`retry` 只推进当前待处理步骤，已经排队或运行时返回同一个任务，不重复调用。模型失败后保留阶段及错误，绝不以演示内容替换真实调用。自然结束先进入 `reporting`，用户点击生成复盘。

首版用单表 JSON 快照保存小规模面试数据，避免多表间的部分更新；问答、报告、证据作为嵌套结构持久化。列表最多返回最近 100 场概要，不包含简历和回答。

SQLite 原子条件更新实现每场面试独占租约，Worker 领取任务时延长至 `max(180, timeout + 30)` 秒。计划、追问的总时限默认 120 秒（5–150），报告默认 300 秒（30–600）；连接阶段最多 5 秒，整体时限涵盖响应体读取。长调用持有该面试写租约，但 GET 查询不需要租约。允许幂等回答重放、查询运行中的 retry，其他冲突写入返回 409。

`generation` 是独立于面试业务阶段的任务快照，包含 `id / task / status / phase / queued_at / started_at / deadline_at / finished_at / timeout_seconds`。任务状态为 `queued → running → completed | failed`；运行阶段只在收到真实结果后才从 `generating` 更新到 `validating`。旧记录没有此字段时仍可从原阶段重试。

FastAPI lifespan 启动每进程 2 个 daemon Worker 和一个心跳线程，直接扫描 SQLite 队列，不依赖 Redis。排队任务重启后可领取；Worker 心跳每 2 秒更新，超过 15 秒失联或任务超过截止时间 30 秒，恢复程序把运行中的任务标记失败并撤销租约。正常停机主动注销 Worker。中断任务需要用户显式重试；旧 Worker 即使稍后拿到结果，也无法越过租约校验覆盖新状态。此队列适用于本机小规模应用，并发数按后端进程计算。

每次保存递增 `revision`，前端比较版本，防止迟到的查询覆盖新的提交响应。生成中每 1.5 秒查询完整记录，空闲时每 5 秒；历史列表每 5 秒查询；隐藏标签页至少间隔 10 秒。查询串行，离开页面取消请求，恢复焦点立即刷新。查询失败自动退避并显示连接状态，不修改真实任务状态。

回答携带 `request_id` 与 `question_id`。相同内容重复请求返回现有记录；同一 ID 换内容、对过期问题发新请求、完成后继续回答均被拒绝。回答先落库，再生成下一题。

## 模型契约与证据

- `plan`：恰好 `main_count` 个 `{topic, question}`。
- `decision`：仅接受 `followup` 或 `next`；不能改变主问题序号。两次追问后由后端强制进入下一题或报告。
- `report`：固定四维，分数为 0–100 的整数或 null；有分数必须有证据。
- 证据的 `answer_id` 必须存在，`quote` 必须是对应回答的连续原文；任一不符则整份报告拒绝保存并允许重试。这保证引用匹配，不保证评价一定合理。
- 演示报告只展示结构与真实回答引文，分数始终为 null。
- 无检索集成时，后端固定来源数组为空，并注明未查证外部资料。

默认路径将本地 Skill 与题库作为系统提示发送。专用路径通过 `OPENCLAW_AGENT_ID=interviewer` 和 `x-openclaw-agent-id` 请求头路由，使用学校工作区内的 Skill 与参考资料，允许 Agent 调用 `read`；不再向该路径注入原先“禁止读取文件”的提示。两条路径都把简历、JD、回答作为资料 JSON 传递，后端继续验证流程和证据。

已复制的学校配置显示全局工具为 coding profile，并附加多种飞书工具；原 main 工作区有多种课程与办公 Skill。新面试官的配置使用独立工作区、Skill 白名单、仅 read 的工具白名单，以及工作区文件访问范围。源文件和安装步骤见 [部署说明](../openclaw/DEPLOYMENT.md)。学校端已完成安装、原版本配置校验与 CLI 加载确认；脱敏运行诊断已确认 interviewer 路由和 Skill / rubric 的 read 调用。完整真实报告仍需验收。

## API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/health` | 模式、是否配置 Token；不探测模型 |
| POST | `/api/resumes/parse` | multipart `file`，返回解析文本 |
| GET | `/api/interviews` | 最近 100 条概要 |
| POST | `/api/interviews` | `{role, resume, jd?, main_count?}`，返回 201、preparing 记录与排队任务 |
| GET | `/api/interviews/{id}` | 恢复完整记录 |
| POST | `/api/interviews/{id}/retry` | 重试计划、下一题或报告；已有任务时幂等返回 |
| POST | `/api/interviews/{id}/start` | 确认计划并开始 |
| POST | `/api/interviews/{id}/answers` | `{request_id, question_id, text}` |
| POST | `/api/interviews/{id}/finish` | 提前结束并生成报告 |
| GET | `/api/interviews/{id}/export` | Markdown 复盘和问答 |

业务错误返回 400/409，资源缺失为 404，输入模型校验为 422。生成任务的提交返回 202 和快照，立即完成的操作返回 200；模型错误在后台写入记录的 `error` 与 `generation.status=failed`，随后由 GET 查询返回，前端显示错误与重试入口。异常不输出 Gateway 响应或 Token。

## 前端职责

`App.tsx` 保留导航、模式和历史概要；`pages/` 负责准备、面试和历史页面。`components/` 将生成状态、答题编辑、问答回看与复盘分开，`hooks.ts` 统一管理串行轮询和短请求，`session.ts` 管理状态文案及版本合并。

答题草稿以 `offerlab:answer:{interview_id}:{question_id}` 为键写入 localStorage，携带稳定的请求 ID。相同内容的失败重试复用 ID，编辑内容后换 ID；服务端确认保存后清除。服务端的 question_id 校验阻止两个页面重复回答旧问题。草稿存储失败不会阻止输入，但会提示不要关闭页面。

等待面板展示已保存、模型生成、结果校验，耗时来自服务端时间戳，刷新不会归零。不伪造进度百分比、模型思考或预计完成时间，也不把未完成的 JSON 当作正式报告。失去状态连接与模型生成失败使用不同提示；导航始终可用。
