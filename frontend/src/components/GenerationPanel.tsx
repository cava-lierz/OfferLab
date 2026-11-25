import { useEffect, useState } from 'react'
import { isPending, taskNames } from '../session'
import type { Interview } from '../types'

export function GenerationPanel({ session, busy, onRetry }: {
  session: Interview; busy: boolean; onRetry: () => void
}) {
  const [now, setNow] = useState(Date.now())
  const pending = isPending(session)
  useEffect(() => {
    if (!pending) return
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [pending, session.generation?.id])
  const job = session.generation
  const task = session.status === 'preparing' ? 'plan' : session.status === 'reporting' ? 'report' : 'decision'
  const title = taskNames[job && pending ? job.task : task]
  const seconds = Math.max(0, Math.floor(now / 1000 - (job?.started_at ?? job?.queued_at ?? now / 1000)))
  const overdue = job?.deadline_at != null && now / 1000 > job.deadline_at
  const phase = job?.status === 'queued' ? '已进入队列，等待处理'
    : job?.phase === 'validating' ? '已收到模型结果，正在校验'
    : overdue ? '正在确认本次处理结果' : '正在等待模型返回结果'
  return <section className={'generation-panel ' + (session.error ? 'generation-failed' : '')} aria-label={`${title}生成状态`}>
    <div className="generation-header">
      <span className={pending ? 'generation-orb' : 'generation-icon'} aria-hidden="true">{pending ? '✦' : session.error ? '!' : '▤'}</span>
      <div><div className="tiny-label">{session.answers.length ? `已保存 ${session.answers.length} 次回答` : '面试材料已保存'}</div>
        <h2>{pending ? `${title}正在准备中` : session.error ? `${title}暂未生成` : `准备生成${title}`}</h2>
      </div>
    </div>
    <p role="status">{pending ? phase : session.error || '依据已保存的材料和回答生成，完成后会显示在这里。'}</p>
    {pending && <>
      <div className="generation-timing"><span>{job?.status === 'queued' ? '已排队' : '已处理'} <strong>{seconds}</strong> 秒</span><span>页面自动更新</span></div>
      <ol className="generation-steps" aria-label="生成步骤">
        <li className="complete">✓ 已保存</li><li className={job?.phase === 'generating' ? 'current' : ''}>模型生成</li><li className={job?.phase === 'validating' ? 'current' : ''}>校验结果</li>
      </ol>
      <p className="generation-hint">{job?.status === 'queued' ? '其他任务正在处理中，排队不会消耗本次模型的等待时限。' : `本次模型调用最多等待 ${job?.timeout_seconds ?? 120} 秒，这不是预计完成时间。`}</p>
      {seconds >= 30 && <p className="generation-hint">模型响应较慢，暂未收到可展示的最终结果。你可以先回看下方材料或回答。</p>}
    </>}
    <div className="generation-actions">
      {!pending && <button className="primary" disabled={busy} onClick={onRetry}>{busy ? '正在提交…' : session.error ? '重新生成' : `生成${title}`}</button>}
      <a className="text-button" href="#history">返回历史记录 →</a>
    </div>
    <p className="generation-hint">{pending ? '可以离开或刷新此页面，后台会继续处理。请保持本机后端运行；之后从历史记录查看结果。' : '已保存的材料和回答会保留，重新生成不会重复提交回答。'}</p>
  </section>
}
