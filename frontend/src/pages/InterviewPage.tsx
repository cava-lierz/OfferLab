import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { clearDraft, draftKey } from '../drafts'
import { useMutation, usePolling } from '../hooks'
import { isPending, newest, statusLabel } from '../session'
import { AnswerComposer } from '../components/AnswerComposer'
import { GenerationPanel } from '../components/GenerationPanel'
import { ReportView } from '../components/ReportView'
import { Transcript } from '../components/Transcript'
import type { Interview, Preparation } from '../types'

export default function InterviewPage({ id, onUpdate, onPrepare }: {
  id: string; onUpdate: (state: Interview) => void; onPrepare: (form: Preparation) => void
}) {
  const [session, setSession] = useState<Interview | null>(null)
  const [finishConfirm, setFinishConfirm] = useState(false)
  const { busy, error, run } = useMutation()
  const accepted = useRef<Interview | null>(null)
  const currentQuestion = useRef<HTMLDivElement>(null)
  function accept(value: Interview) {
    if (value.id !== id) return
    const latest = newest(accepted.current, value)
    accepted.current = latest
    setSession(latest); onUpdate(latest)
    for (const answer of latest.answers) clearDraft(draftKey(id, answer.question.id))
  }
  const polling = usePolling<Interview>('/interviews/' + id, accept, session && isPending(session) ? 1500 : 5000)
  const questionId = session?.status === 'active' ? session.current?.id : null
  useEffect(() => {
    if (questionId) currentQuestion.current?.focus({ preventScroll: true })
  }, [questionId])

  function action(name: string) {
    void run(async () => {
      const updated = await api<Interview>(`/interviews/${id}/${name}`, {})
      accept(updated); setFinishConfirm(false); polling.refresh()
    })
  }
  if (!session) return <div className="card empty">
    <h2>{polling.error ? '暂时无法加载记录' : '正在读取已保存的面试…'}</h2>
    {polling.error && <p role="alert">{polling.error}</p>}
    <button className="text-button" onClick={polling.refresh}>重新读取</button> · <a href="#history">返回历史记录</a>
  </div>
  const pending = isPending(session)
  const needsGeneration = ['preparing', 'awaiting_next', 'reporting'].includes(session.status)
  const prepare = () => onPrepare({ role: session.role, resume: session.resume, jd: session.jd, main_count: session.main_count })
  return <>
    <section className="page-heading compact"><div className="eyebrow">{session.status === 'completed' ? 'REFLECT. REFINE. REPEAT.' : 'ONE QUESTION AT A TIME'}</div>
      <h1>{session.role}<span className="heading-status">{statusLabel(session)}</span></h1>
      <p>{session.mode === 'demo' ? '本场为演示模式 · 不进行能力评分' : '本场通过学校 OpenClaw 生成问题与反馈'} · 已保存 {session.answers.length} 次回答</p>
    </section>
    {polling.error && <div className="alert error" role="alert"><span>状态更新暂时中断，后台任务可能仍在运行。正在自动重连，当前显示最近保存的记录。</span><button className="text-button" onClick={polling.refresh}>立即刷新状态</button></div>}
    {error && <div className="alert error" role="alert">{error}<button className="text-button" onClick={polling.refresh}>核对已保存记录</button></div>}
    {needsGeneration && <GenerationPanel session={session} busy={busy} onRetry={() => action('retry')} />}

    {(session.status === 'preparing' || session.status === 'ready') && <div className="interview-grid">
      <section className="card"><h2>{session.status === 'ready' ? '你的面试计划已准备好' : '本场练习安排'}</h2>
        <p className="muted">{session.main_count} 道主问题，每道最多追问 2 次。计划生成后由你确认，再开始回答。</p>
        {session.plan.map((item, i) => <div className="plan-item" key={i}><span>{String(i + 1).padStart(2, '0')}</span><div><h3>{item.topic}</h3><p>{item.question}</p></div></div>)}
        {session.status === 'ready' && <button className="primary mt-6" disabled={busy} onClick={() => action('start')}>{busy ? '正在开始…' : '确认计划，开始面试'}</button>}
        {session.status === 'preparing' && <div className="preparation-checklist"><p>✓ 简历与目标岗位已保存</p><p>✓ 主问题数量已确定</p><p>生成期间可以检查右侧材料，或稍后从历史记录继续。</p></div>}
      </section>
      <section className="card material-summary"><h3>本场材料</h3><p className="muted">请确认简历解析结果与目标一致。</p>
        <details><summary>查看简历文本</summary><p className="preserve">{session.resume}</p></details>
        <details><summary>查看岗位描述</summary><p className="preserve">{session.jd || '未填写岗位描述'}</p></details>
        <button className="text-button mt-6" onClick={prepare}>修改材料并创建新面试</button>
      </section>
    </div>}

    {['active', 'awaiting_next', 'reporting'].includes(session.status) && <div className="interview-grid">
      <section className="card conversation">
        {session.status === 'reporting' && <div className="transcript-heading"><h2>回看已保存的回答</h2><p className="muted">报告将依据这些回答生成。未提交的草稿不计入。</p></div>}
        <Transcript answers={session.answers} />
        {session.status === 'active' && session.current && <div ref={currentQuestion} tabIndex={-1} className="question-focus">
          <div className="question-ready" role="status">{session.answers.length ? '下一道问题已准备好' : '面试已开始，按自己的节奏回答'}</div>
          <AnswerComposer key={session.current.id} interviewId={id} question={session.current} onSaved={value => { accept(value); polling.refresh() }} />
        </div>}
      </section>
      <aside className="right-column"><section className="card progress-card"><h3>本场进度</h3>
        <div className="progress-number">{Math.min((session.current?.main_index ?? 0) + 1, session.main_count)}<span> / {session.main_count} 道主问题</span></div>
        <progress aria-label="当前主问题" value={(session.current?.main_index ?? 0) + 1} max={session.main_count} />
        <ol>{session.plan.map((item, index) => <li key={index} className={index === session.current?.main_index ? 'active-topic' : ''}>{item.topic}</li>)}</ol>
        {session.status !== 'reporting' && <><button className="secondary w-full" disabled={busy || pending || !session.answers.length} onClick={() => setFinishConfirm(true)}>提前结束并复盘</button>
          {pending && <p className="muted mt-6">当前问题处理完后，可以继续作答或提前结束。</p>}
          {finishConfirm && <div className="confirm-box"><p>结束后将依据已保存的回答生成报告，未提交的草稿不会计入。</p><button className="primary" disabled={busy || pending} onClick={() => action('finish')}>确认结束</button><button className="text-button" disabled={busy} onClick={() => setFinishConfirm(false)}>继续回答</button></div>}</>}
      </section><div className="tip"><strong>{session.status === 'reporting' ? '复盘会关注什么' : '给自己一点思考时间'}</strong><p>{session.status === 'reporting' ? '表达结构、项目深度、岗位匹配与反思能力。反馈会结合回答原文，并给出下一步练习建议。' : '不确定时可以坦诚说明。清楚地解释思考过程，也是一种表达能力。'}</p></div></aside>
    </div>}
    {session.status === 'completed' && <ReportView session={session} onPractice={onPrepare} />}
  </>
}
