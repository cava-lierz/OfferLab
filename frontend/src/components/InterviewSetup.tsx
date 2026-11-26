import type { Interview } from '../types'
import { LoadingIndicator } from './LoadingIndicator'

export function InterviewSetup({ session, busy, onStart, onPrepare }: {
  session: Interview; busy: boolean; onStart: () => void; onPrepare: () => void
}) {
  return <div className="interview-grid">
      <section className="card"><h2>{session.status === 'ready' ? '准备好开始面试了' : '本场练习安排'}</h2>
        <p className="muted">{session.main_count} 道主问题，每道最多追问 2 次。题目会逐一出现，按自己的节奏回答即可。</p>
        {session.status === 'ready' && <button className="primary mt-6" disabled={busy} onClick={onStart}>{busy ? <LoadingIndicator /> : '开始面试'}</button>}
      </section>
      <section className="card material-summary"><h3>本场材料</h3><p className="muted">请确认简历解析结果与目标一致。</p>
        <details><summary>查看简历文本</summary><p className="preserve">{session.resume}</p></details>
        <details><summary>查看岗位描述</summary><p className="preserve">{session.jd || '未填写岗位描述'}</p></details>
        <button className="text-button mt-6" onClick={onPrepare}>修改材料并创建新面试</button>
      </section>
    </div>
}
