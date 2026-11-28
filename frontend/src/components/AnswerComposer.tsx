import { useState } from 'react'
import type { FormEvent } from 'react'
import { LoadingIndicator } from './LoadingIndicator'
import { api } from '../api'
import { clearDraft, draftKey, readDraft, saveDraft } from '../drafts'
import { useMutation } from '../hooks'
import type { Interview, Project, Question } from '../types'
import { ProjectExcerpt } from './ProjectEvidence'

export function AnswerComposer({ interviewId, question, project, onSaved }: {
  interviewId: string; question: Question; project?: Project; onSaved: (state: Interview) => void
}) {
  const key = draftKey(interviewId, question.id)
  const [draft, setDraft] = useState(() => readDraft(key))
  const [stored, setStored] = useState(true)
  const [showRefs, setShowRefs] = useState(Boolean(draft.excerpt_id))
  const needsRef = project && question.followup === 1 && !draft.excerpt_id
  function edit(text: string, excerpt_id?: string) {
    const next = { text, excerpt_id, request_id: crypto.randomUUID() }
    setDraft(next); setStored(saveDraft(key, next))
  }
  const { busy, error, run } = useMutation()
  function submit(e: FormEvent) {
    e.preventDefault()
    if (!draft.text.trim() || needsRef) return
    setStored(saveDraft(key, draft))
    void run(async () => {
      const updated = await api<Interview>(`/interviews/${interviewId}/answers`, {
        request_id: draft.request_id, question_id: question.id, text: draft.text.trim(), excerpt_id: draft.excerpt_id,
      })
      // Clear only after the server confirms this exact answer is durable.
      if (updated.answers.some(answer => answer.request_id === draft.request_id)) clearDraft(key)
      onSaved(updated)
    })
  }
  return <form onSubmit={submit} className="current-question">
    <div className="question-meta">面试官 · {question.topic} {project ? `· 第 ${question.followup + 1}/2 轮` : question.followup > 0 && `· 追问 ${question.followup}/2`}</div>
    <h2>{question.text}</h2><label htmlFor="answer">你的回答</label>
    <textarea id="answer" required maxLength={8000} rows={7} value={draft.text} disabled={busy}
      onChange={e => edit(e.target.value, draft.excerpt_id)} placeholder="可以从背景、你的行动和结果展开。尽量用具体细节说明。" />
    {project && <div><button type="button" className="secondary" aria-expanded={showRefs} onClick={() => setShowRefs(!showRefs)}>指给我看</button>
      <p className="muted">{draft.excerpt_id ? `已引用 ${draft.excerpt_id}` : question.followup ? '请选一处片段支撑本轮回答。' : '你可以引用自己负责的片段。'}</p>
      {showRefs && project.excerpts.map(item => <div key={item.id} className="project-choice">
        <label><input type="radio" name="evidence" disabled={busy} checked={draft.excerpt_id === item.id} onChange={() => edit(draft.text, item.id)} /> 引用 {item.id} · 第 {item.start}–{item.end} 行</label>
        <ProjectExcerpt item={item} /></div>)}
    </div>}
    {error && <div className="alert error" role="alert">{error} 原内容再次提交会核对保存状态。</div>}
    <div className="answer-footer"><span>{draft.text.length} / 8000 · {stored ? '草稿保存在当前浏览器' : '浏览器无法保存草稿，请暂勿关闭页面'}</span>
      <button className="primary" disabled={busy || !draft.text.trim() || needsRef}>{busy ? <LoadingIndicator /> : '提交回答'}</button>
    </div>
  </form>
}
