import { PreparationSources } from './PreparationSources'
import { ProjectReplay } from './ProjectEvidence'
import type { Interview, Preparation } from '../types'

export function ReportView({ session, onPractice }: {
  session: Interview; onPractice: (form: Preparation) => void
}) {
  const report = session.report
  if (!report) return null
  return <>
    <div className="report-hero">
      <div>
        <div className="eyebrow">INTERVIEW REFLECTION</div>
        <h2>把这一次，变成下一次的经验。</h2>
        <p>{report.summary}</p>
      </div>
      <a className="light-button button-link" href={`/api/interviews/${session.id}/export`}>导出 Markdown 报告</a>
    </div>
    {session.project && <ProjectReplay session={session} />}
    <div className="report-grid">
      {report.dimensions.map(item => <section className="card dimension" key={item.name}>
        <div className="section-title">
          <h2>{item.name}</h2>
          <span className="score">{item.score === null ? '未评分' : <>{item.score}<small>/100</small></>}</span>
        </div>
        <p>{item.feedback}</p>
        {item.evidence.map((quote, i) => <blockquote key={i}>
          <span>来自回答 {session.answers.findIndex(a => a.id === quote.answer_id) + 1}</span>
          <p>“{quote.quote}”</p>
        </blockquote>)}
        <div className="suggestion"><strong>下一步练习</strong><p>{item.suggestion}</p></div>
        {!session.project && <button className="text-button" onClick={() => onPractice({
          role: session.role,
          resume: session.resume,
          jd: session.jd,
          practice_focus: `${item.name}。${item.suggestion}`,
          main_count: 3,
        })}>围绕这一项重新练习</button>}
      </section>)}
    </div>
    <section className="card mt-6">
      <h3>资料来源与评价边界</h3>
      <p className="muted">{report.source_note} 评价仅用于训练反馈，不表示真实招聘录用概率。</p>
      <PreparationSources research={session.research} />
      <details>
        <summary>查看完整问答（{session.answers.length} 次回答）</summary>
        {session.answers.map((answer, i) => <div className="exchange" key={answer.id}>
          <h3>{i + 1}. {answer.question.text}</h3><p className="preserve">{answer.text}</p>
        </div>)}
      </details>
    </section>
  </>
}
