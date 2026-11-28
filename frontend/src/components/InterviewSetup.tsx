import { PreparationSources } from './PreparationSources'
import type { Interview } from '../types'
import { LoadingIndicator } from './LoadingIndicator'
import { ProjectExcerpt } from './ProjectEvidence'

export function InterviewSetup({ session, busy, onStart, onPrepare }: {
  session: Interview; busy: boolean; onStart: () => void; onPrepare: () => void
}) {
  return <div className="interview-grid">
      <section className="card"><h2>{session.status === 'ready' ? '准备好开始面试了' : '本场练习安排'}</h2>
        <p className="muted">{session.project ? '两轮问答。先介绍你负责的改动，再引用片段说明依据。' : `${session.main_count} 道主问题，每道最多追问 2 次。题目会逐一出现，按自己的节奏回答即可。`}</p>
        {session.status === 'ready' && <button className="primary mt-6" disabled={busy} onClick={onStart}>{busy ? <LoadingIndicator /> : '开始面试'}</button>}
      </section>
      <section className="card material-summary"><h3>本场材料</h3><p className="muted">{session.project ? '确认简历原句与所选的项目片段。' : '请确认简历解析结果与目标一致。'}</p>
        {session.project?.target_role && <p>目标岗位：{session.project.target_role}<br />招聘要求：{session.jd}</p>}
        <PreparationSources research={session.research} />
        <details><summary>查看简历文本</summary><p className="preserve">{session.resume}</p></details>
        {session.project ? <details><summary>查看已选项目片段</summary>{session.project.excerpts.map(row => <ProjectExcerpt key={row.id} item={row} pdfUrl={`/api/interviews/${session.id}/portfolio.pdf`} />)}</details> : <details><summary>查看岗位描述</summary><p className="preserve">{session.jd || '未填写岗位描述'}</p></details>}
        {session.practice_focus && <p className="preserve">本次练习重点：{session.practice_focus}</p>}
        {session.project ? <a className="text-button" href="#project">重新选择项目材料</a> : <button className="text-button mt-6" onClick={onPrepare}>修改材料并创建新面试</button>}
      </section>
    </div>
}
