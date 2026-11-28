import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { clearDraft, clearInterviewDrafts, draftKey } from '../drafts'
import { useMutation, usePolling } from '../hooks'
import { isPending, newest, statusLabel } from '../session'
import { InterviewSetup } from '../components/InterviewSetup'
import { AnswerComposer } from '../components/AnswerComposer'
import { LoadingIndicator } from '../components/LoadingIndicator'
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
  useEffect(() => {
    if (polling.missing) clearInterviewDrafts(id)
  }, [polling.missing, id])
  const questionId = session?.status === 'active' ? session.current?.id : null
  useEffect(() => {
    if (questionId) currentQuestion.current?.focus({ preventScroll: true })
  }, [questionId])

  function action(name: string) {
    void run(async () => {
      const updated = await api<Interview>(`/interviews/${id}/${name}`, name === 'next' ? { question_id: session?.current?.id } : {})
      accept(updated); setFinishConfirm(false); polling.refresh()
    })
  }
  if (polling.missing) return <div className="card empty"><h2>面试记录已删除或不存在</h2><a href="#history">返回历史记录</a></div>
  if (!session && !polling.error) return <div className="generation-loading"><LoadingIndicator /></div>
  if (!session) return <div className="card empty">
    <h2>暂时无法加载记录</h2>
    {polling.error && <p role="alert">{polling.error}</p>}
    <button className="text-button" onClick={polling.refresh}>重新读取</button> · <a href="#history">返回历史记录</a>
  </div>
  const pending = isPending(session)
  const needsGeneration = ['preparing', 'awaiting_next', 'reporting'].includes(session.status)
  const prepare = () => onPrepare({ role: session.role, resume: session.resume, jd: session.jd, main_count: session.main_count })
  return <>
    <section className="page-heading compact"><div className="eyebrow">{session.status === 'completed' ? 'REFLECT. REFINE. REPEAT.' : 'ONE QUESTION AT A TIME'}</div>
      <h1>{session.role}{!pending && <span className="heading-status">{statusLabel(session)}</span>}</h1>
      <p>{session.mode === 'demo' ? '本场为演示模式 · 不进行能力评分' : '本场通过学校 OpenClaw 生成问题与反馈'} · 已保存 {session.answers.length} 次回答</p>
    </section>
    {polling.error && <div className="alert error" role="alert"><span>状态更新暂时中断，后台任务可能仍在运行。正在自动重连，当前显示最近保存的记录。</span><button className="text-button" onClick={polling.refresh}>立即刷新状态</button></div>}
    {error && <div className="alert error" role="alert">{error}<button className="text-button" onClick={polling.refresh}>核对已保存记录</button></div>}
    {needsGeneration && <GenerationPanel session={session} busy={busy} onRetry={() => action('retry')} />}

    {(session.status === 'preparing' || session.status === 'ready') && <InterviewSetup session={session} busy={busy} onStart={() => action('start')} onPrepare={prepare} />}

    {['active', 'awaiting_next', 'between_questions', 'reporting'].includes(session.status) && <div className="interview-grid">
      <section className="card conversation">
        {session.status === 'reporting' && <div className="transcript-heading"><h2>回看已保存的回答</h2><p className="muted">报告将依据这些回答生成。未提交的草稿不计入。</p></div>}
        {session.status === 'reporting' ? <Transcript answers={session.answers} /> : session.answers.length > 0 && <details className="answer-history" key={session.current?.id}>
          <summary>回看已保存的 {session.answers.length} 次回答</summary>
          <Transcript answers={session.answers} />
        </details>}
        {session.status === 'between_questions' && <div className="question-focus">
          <h2>本题已完成</h2>
          <p className="muted">准备好后，继续下一道主问题。</p>
          <button className="primary mt-6" disabled={busy} onClick={() => action('next')}>{busy ? <LoadingIndicator /> : '下一题'}</button>
        </div>}
        {session.status === 'active' && session.current && <div ref={currentQuestion} tabIndex={-1} className="question-focus">
          <div className="question-ready" role="status">{session.answers.length ? '下一道问题已准备好' : '面试已开始，按自己的节奏回答'}</div>
          <AnswerComposer key={session.current.id} interviewId={id} question={session.current} onSaved={value => { accept(value); polling.refresh() }} />
        </div>}
      </section>
      <aside className="right-column"><section className="card progress-card"><h3>本场进度</h3>
        <div className="progress-number">{Math.min((session.current?.main_index ?? 0) + 1, session.main_count)}<span> / {session.main_count} 道主问题</span></div>
        <progress aria-label="当前主问题" value={(session.current?.main_index ?? 0) + 1} max={session.main_count} />
        {session.status !== 'reporting' && <><button className="secondary w-full" disabled={busy || pending || !session.answers.length} onClick={() => setFinishConfirm(true)}>提前结束并复盘</button>
          {finishConfirm && <div className="confirm-box"><p>结束后将依据已保存的回答生成报告，未提交的草稿不会计入。</p><button className="primary" disabled={busy || pending} onClick={() => action('finish')}>确认结束</button><button className="text-button" disabled={busy} onClick={() => setFinishConfirm(false)}>继续回答</button></div>}</>}
      </section><div className="tip"><strong>{session.status === 'reporting' ? '复盘会关注什么' : '给自己一点思考时间'}</strong><p>{session.status === 'reporting' ? '表达结构、项目深度、岗位匹配与反思能力。反馈会结合回答原文，并给出下一步练习建议。' : '不确定时可以坦诚说明。清楚地解释思考过程，也是一种表达能力。'}</p></div></aside>
    </div>}
    {session.status === 'completed' && <ReportView session={session} onPractice={onPrepare} />}
  </>
}
