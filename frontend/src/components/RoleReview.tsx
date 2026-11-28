import { useState } from 'react'
import { api } from '../api'
import { useMutation } from '../hooks'
import type { Coaching, Interview } from '../types'
import { locationLabel } from './ProjectEvidence'

export function RoleReview({ session, review, onSaved }: {
  session: Interview; review: Coaching; onSaved: (value: Interview) => void
}) {
  const saved = session.adopted_resume_line ?? null
  const [edit, setEdit] = useState<{ text: string; previous: string | null } | null>(null)
  const [notice, setNotice] = useState('')
  const { busy, error, run, clearError } = useMutation()
  const ref = session.project?.excerpts.find(item => item.id === review.excerpt_id)
  const text = edit?.text ?? saved ?? review.resume_line
  const changedElsewhere = edit !== null && edit.previous !== saved
  const reset = () => { setEdit(null); setNotice(''); clearError() }
  return <section className="card project-replay role-review">
    <h2>岗位定向复盘</h2><h3>{session.project?.target_role}</h3><p className="preserve">招聘要求：{session.jd}</p>
    <div className="review-evidence"><div><strong>我的回答</strong><blockquote>{review.answer_quote}</blockquote></div>
      {ref && <div><strong>{review.source_field === 'note' ? '我的页面说明' : '作品原文'}</strong><blockquote className="preserve">{review.work_quote}</blockquote>
        <a href={ref.page !== undefined ? `/api/interviews/${session.id}/portfolio.pdf#page=${ref.page}` : ref.url} target="_blank" rel="noreferrer">{ref.path} · {locationLabel(ref)} ↗</a></div>}</div>
    <h3>已有依据</h3><p>{review.match}</p><h3>还可以补充什么</h3><p>{review.gap}</p>
    <h3>带走一条简历表述</h3><p><strong>原句</strong>　{session.resume}</p><p><strong>本场建议</strong>　{review.resume_line || '请先补充有作品依据的个人动作，再填写表述。'}</p>
    <label htmlFor="resume-line">{saved ? '已采纳的表述（可修改）' : '核对后采纳，可直接编辑'}</label>
    <textarea id="resume-line" rows={3} maxLength={500} value={text} disabled={busy} onChange={e => { setEdit({ text: e.target.value, previous: edit ? edit.previous : saved }); setNotice('') }} />
    {changedElsewhere && <p role="alert">这条表述已在其他页面更新。<button className="text-button" onClick={reset}>读取已保存版本</button></p>}
    <div className="project-actions"><button className="primary" disabled={busy || changedElsewhere || !text.trim() || saved === text.trim()} onClick={() => void run(async () => {
      const value = await api<Interview>(`/interviews/${session.id}/resume-line`, { text, previous: edit ? edit.previous : saved })
      onSaved(value); setEdit(null); setNotice('已保存，可随报告导出。')
    })}>{saved ? '保存修改' : '采纳到本场记录'}</button>
    <button className="secondary" disabled={!text.trim()} onClick={() => void run(async () => { await navigator.clipboard.writeText(text); setNotice('已复制表述。') })}>复制表述</button></div>
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
  </section>
}
