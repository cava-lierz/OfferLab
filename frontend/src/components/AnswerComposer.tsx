import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api'
import { clearDraft, draftKey, readDraft, saveDraft } from '../drafts'
import { useMutation } from '../hooks'
import type { Interview, Question } from '../types'

export function AnswerComposer({ interviewId, question, onSaved }: {
  interviewId: string; question: Question; onSaved: (state: Interview) => void
}) {
  const key = draftKey(interviewId, question.id)
  const [draft, setDraft] = useState(() => readDraft(key))
  const [stored, setStored] = useState(true)
  const { busy, error, run } = useMutation()
  function submit(e: FormEvent) {
    e.preventDefault()
    if (!draft.text.trim()) return
    setStored(saveDraft(key, draft))
    void run(async () => {
      const updated = await api<Interview>(`/interviews/${interviewId}/answers`, {
        request_id: draft.request_id, question_id: question.id, text: draft.text.trim(),
      })
      // Clear only after the server confirms this exact answer is durable.
      if (updated.answers.some(answer => answer.request_id === draft.request_id)) clearDraft(key)
      onSaved(updated)
    })
  }
  return <form onSubmit={submit} className="current-question">
    <div className="question-meta">面试官 · {question.topic} {question.followup > 0 && `· 追问 ${question.followup}/2`}</div>
    <h2>{question.text}</h2><label htmlFor="answer">你的回答</label>
    <textarea id="answer" required maxLength={8000} rows={7} value={draft.text} disabled={busy}
      onChange={e => {
        const next = { text: e.target.value, request_id: crypto.randomUUID() }
        setDraft(next); setStored(saveDraft(key, next))
      }} placeholder="可以从背景、你的行动和结果展开。尽量用具体细节说明。" />
    {error && <div className="alert error" role="alert">{error} 原内容再次提交会核对保存状态。</div>}
    <div className="answer-footer"><span>{draft.text.length} / 8000 · {stored ? '草稿保存在当前浏览器' : '浏览器无法保存草稿，请暂勿关闭页面'}</span>
      <button className="primary" disabled={busy || !draft.text.trim()}>{busy ? '正在保存回答…' : '保存回答，继续面试'}</button>
    </div>
  </form>
}
