import { isPending, taskNames } from '../session'
import type { Interview } from '../types'
import { LoadingIndicator } from './LoadingIndicator'

export function GenerationPanel({ session, busy, onRetry }: {
  session: Interview; busy: boolean; onRetry: () => void
}) {
  if (isPending(session)) return <div className="generation-loading"><LoadingIndicator /></div>
  const task = session.status === 'preparing' ? 'plan' : session.status === 'reporting' ? 'report' : 'decision'
  const title = taskNames[task]
  return <section className={'generation-panel ' + (session.error ? 'generation-failed' : '')} aria-label={`${title}`}>
    <h2>{session.error ? `${title}暂未完成` : `准备查看${title}`}</h2>
    {session.error && <p role="alert">{session.error}</p>}
    <div className="generation-actions">
      <button className="primary" disabled={busy} onClick={onRetry}>{busy ? <LoadingIndicator /> : session.error ? '重试' : `生成${title}`}</button>
      <a className="text-button" href="#history">返回历史记录 →</a>
    </div>
    <p className="generation-hint">已保存的材料和回答会保留，重试不会重复提交回答。</p>
  </section>
}
