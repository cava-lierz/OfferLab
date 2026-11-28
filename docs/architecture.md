# 实现与接口约定

## 数据流

```text
浏览器 :5173 ⇄ Vite /api 代理 ⇄ FastAPI :8000
                                  │ 保存 / 查询
                                  ▼
                       SQLite 快照与持久化任务队列
                                  │ 领取任务
                                  ▼
                       前台任务 Worker × 2 + 分题复盘 Worker × 1
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

参考：[OpenClaw HTTP 接口](https://docs.openclaw.ai/gateway/openai-http-api)、[FastAPI 文档](https://fastapi.tiangolo.com/tutorial/)、[Vite 文档](https://vite.dev/guide/)。在线文档可能对应新版本，本项目当前适配学校 OpenClaw `2026.5.22`。

## 状态与持久化

```text
preparing --生成计划--> ready --开始面试--> active
active --先保存回答--> awaiting_next --需要追问--> active
awaiting_next --本题结束且还有大题--> between_questions
between_questions --点击下一题，入队分题复盘--> active（下一道预设大题）
awaiting_next --最后一题结束--> reporting --生成复盘--> completed
active / awaiting_next / between_questions --提前结束--> reporting
```

创建接口保存材料并排队生成计划，返回 201 和持久化 ID。回答接口在同一次 SQLite 写入中保存回答与排队任务，返回 202，无需等待模型。`Engine.submit` 处理短操作，`Engine.process_job` 由后台线程执行一次模型调用；同步 `act` 仅作为核心测试适配器。`retry` 只推进当前待处理步骤，已经排队或运行时返回同一个任务，不重复调用。模型失败后保留阶段及错误，绝不以演示内容替换真实调用。自然结束先进入 `reporting`，用户点击生成复盘。

面试主体用单表 JSON 快照保存小规模面试数据，避免多表间的部分更新；问答、报告、证据作为嵌套结构持久化。列表最多返回最近 100 场概要，不包含简历和回答。

SQLite 原子条件更新实现每场面试独占租约，Worker 领取任务时延长至 `max(180, timeout + 30)` 秒。计划、追问的总时限默认 120 秒（5–150），报告默认 300 秒（30–600）；连接阶段最多 5 秒，整体时限涵盖响应体读取。长调用持有该面试写租约，但 GET 查询不需要租约。允许幂等回答重放、查询运行中的 retry，其他冲突写入返回 409。

`generation` 是独立于面试业务阶段的任务快照，包含 `id / task / status / phase / queued_at / started_at / deadline_at / finished_at / timeout_seconds`。任务状态为 `queued → running → completed | failed`；运行阶段只在收到真实结果后才从 `generating` 更新到 `validating`。旧记录没有此字段时仍可从原阶段重试。

FastAPI lifespan 启动每进程 2 个前台任务 Worker、1 个分题复盘 Worker 和一个心跳线程，直接扫描 SQLite 队列，不依赖 Redis。排队任务重启后可领取；Worker 心跳每 2 秒更新，超过 15 秒失联或任务超过截止时间 30 秒，恢复程序把运行中的任务标记失败并撤销租约。正常停机主动注销 Worker。中断任务需要用户显式重试；旧 Worker 即使稍后拿到结果，也无法越过租约校验覆盖新状态。此队列适用于本机小规模应用，并发数按后端进程计算。

每次保存递增 `revision`，前端比较版本，防止迟到的查询覆盖新的提交响应。生成中每 1.5 秒查询完整记录，空闲时每 5 秒；历史列表每 5 秒查询；隐藏标签页至少间隔 10 秒。查询串行，离开页面取消请求，恢复焦点立即刷新。查询失败自动退避并显示连接状态，不修改真实任务状态。

回答携带 `request_id` 与 `question_id`。相同内容重复请求返回现有记录；同一 ID 换内容、对过期问题发新请求、完成后继续回答均被拒绝。回答先落库，再生成下一题。

## 分题复盘与并行处理

计划阶段仍预先生成全部主问题，前端仅展示数量，开始后逐题呈现。题内追问决策不变；决定不再追问或达到两次追问上限后，进入 `between_questions`。`POST /next` 携带当前问题 ID，原子保存下一题及上一组问答的复盘任务，直接返回 200，不等待模型。相同问题 ID 重复切题不会跳过题目；未结束本题或过期的 ID 返回 409。

分题任务使用独立的 `question_reviews` 表，以 `(interview_id, main_index)` 唯一标识。快照只包含该大题及其追问的回答，领取任务时原子设置 attempt、worker 和截止时间，不占用面试写租约。结果写回自己的记录，不覆盖面试、回答或 revision。唯一一个分题 Worker 在没有已排队的前台任务时领取工作；已开始的模型调用不抢占，模型服务本身仍可能限制并发。

分题分析复用现有 `report` 契约和四维引文校验，因此无需重装学校 Agent。最终报告读取已完成的分题分析，并保留所有原始回答核对证据；缺失、失败或仍运行的分析不阻塞总报告，未开始的分题任务在提交总报告时跳过。最后一道大题直接由总报告覆盖。已中断的分题分析标记失败，过期结果不能回写，也不自动重复付费调用；总报告直接分析原文。

该机制把部分复盘工作与答题时间重叠，不保证模型本身变快，并增加每个已切换大题的一次模型调用（最多 `main_count - 1` 次）。实际时延取决于模型并发和答题时长，需真实调用验收。既有 SQLite 数据启动时自动增建表；旧面试可继续使用，无需清空数据。

## 模型契约与证据

- `plan`：恰好 `main_count` 个 `{topic, question}`。
- `decision`：仅接受 `followup` 或 `next`；不能改变主问题序号。两次追问后由后端强制进入下一题或报告。
- `report`：固定四维，分数为 0–100 的整数或 null；有分数必须有证据。
- 证据的 `answer_id` 必须存在，`quote` 必须是对应回答的连续原文；任一不符则整份报告拒绝保存并允许重试。这保证引用匹配，不保证评价一定合理。
- 演示报告只展示结构与真实回答引文，分数始终为 null。
- 专用面试官可在计划内返回考查依据及 research（状态、来源标题、URL）。应用校验结构和链接并保存，备课来源在准备页、报告和导出中可见。旧计划缺少这些字段时仍可继续。检索调用的独立证据来自学校会话轨迹。

默认路径将本地 Skill 与题库作为系统提示发送。专用路径通过 `OPENCLAW_AGENT_ID=interviewer` 和 `x-openclaw-agent-id` 请求头路由，使用学校工作区内的 Skill 与参考资料，允许 Agent 调用 `read`、`web_search` 和 `web_fetch`；不再向该路径注入原先“禁止读取文件”的提示。两条路径都把简历、JD、回答作为资料 JSON 传递，后端继续验证流程和证据。

已复制的学校配置显示全局工具为 coding profile，并附加多种飞书工具；原 main 工作区有多种课程与办公 Skill。新面试官的配置使用独立工作区、Skill 白名单、面试工具白名单，以及工作区文件访问范围。源文件和安装步骤见 [部署说明](../openclaw/DEPLOYMENT.md)。学校端已完成安装、原版本配置校验与 CLI 加载确认；脱敏运行诊断已确认 interviewer 路由和 Skill / rubric 的 read 调用。2026-11-26 开发者确认已切到个人 DeepSeek；更新安装器保留 Agent 已选模型。完整真实报告仍需验收，按日期的证据见 [验证记录](verification.md)。

## API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/health` | 模式、是否配置 Token；不探测模型 |
| POST | `/api/resumes/parse` | multipart `file`，返回解析文本 |
| GET | `/api/interviews` | 最近 100 条概要 |
| POST | `/api/interviews` | `{role, resume, jd?, main_count?}`，返回 201、preparing 记录与排队任务 |
| GET | `/api/interviews/{id}` | 恢复完整记录 |
| DELETE | `/api/interviews/{id}` | 单场本机面试与关联复盘原子删除。重复请求均返回 204，随后查询返回 404 |
| POST | `/api/interviews/{id}/retry` | 重试计划、下一题或报告；已有任务时幂等返回 |
| POST | `/api/interviews/{id}/start` | 确认计划并开始 |
| POST | `/api/interviews/{id}/next` | `{question_id}`，切到下一道预设大题并入队分题复盘，返回 200 |
| POST | `/api/interviews/{id}/answers` | `{request_id, question_id, text}` |
| POST | `/api/interviews/{id}/finish` | 提前结束并生成报告 |
| GET | `/api/interviews/{id}/export` | Markdown 复盘和问答 |

业务错误返回 400/409，资源缺失为 404，输入模型校验为 422。生成任务的提交返回 202 和快照，立即完成的操作返回 200；模型错误在后台写入记录的 `error` 与 `generation.status=failed`，随后由 GET 查询返回，前端显示错误与重试入口。异常不输出 Gateway 响应或 Token。

## 前端职责

`App.tsx` 保留导航、模式和历史概要；`pages/` 负责准备、面试和历史页面。`components/` 将生成状态、答题编辑、问答回看与复盘分开，`hooks.ts` 统一管理串行轮询和短请求，`session.ts` 管理状态文案及版本合并。

答题草稿以 `offerlab:answer:{interview_id}:{question_id}` 为键写入 localStorage，携带稳定的请求 ID。相同内容的失败重试复用 ID，编辑内容后换 ID；服务端确认保存后清除。服务端的 question_id 校验阻止两个页面重复回答旧问题。草稿存储失败不会阻止输入，但会提示不要关闭页面。

等待时仅展示带无障碍标签的旋转加载图标，不展示计秒、排队、生成阶段或超时时限；减少动态效果设置下放慢旋转。历史列表采用同样的图标。时间戳仍用于后端恢复与诊断。分题复盘不在答题界面展示分析内容或占用加载状态，失败与重试提示仅用于面试必需的任务。计划页和进度栏不提前展示题目或未来主题。
