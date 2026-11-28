import type { Excerpt, Interview } from '../types'

export function locationLabel(item: Excerpt) {
  return item.page !== undefined ? `第 ${item.page} 页` : `L${item.start}–${item.end}`
}
export function ProjectExcerpt({ item, pdfUrl }: { item: Excerpt; pdfUrl?: string }) {
  const href = item.page !== undefined ? `${pdfUrl}#page=${item.page}` : item.url
  return <div className="project-excerpt">
    <a href={href} target="_blank" rel="noreferrer">{item.path} · {locationLabel(item)} ↗</a>
    {item.page !== undefined ? <>
      {item.code && <p className="preserve">{item.code}</p>}
      {item.truncated && <small>显示本页前 3,000 字，点击页码可核对原件。</small>}
      {item.note && <p><strong>我的页面说明</strong>　{item.note}</p>}
    </> : <pre tabIndex={0} aria-label={`${item.path} 源码片段`}><code>{item.code}</code></pre>}
  </div>
}

export function ProjectReplay({ session }: { session: Interview }) {
  const project = session.project
  if (!project) return null
  const pdfUrl = `/api/interviews/${session.id}/portfolio.pdf`
  return <section className="card project-replay">
    <h2>项目答辩回放</h2><h3>简历原句</h3><blockquote>{session.resume}</blockquote>
    <p><a href={project.kind === 'pdf' ? pdfUrl : project.url} target="_blank" rel="noreferrer">{project.title} ↗</a> · {project.kind === 'pdf' ? '文件指纹' : '提交'} <code>{project.sha.slice(0, 7)}</code></p>
    {session.answers.map((answer, i) => {
      const ref = project.excerpts.find(item => item.id === answer.excerpt_id)
      return <div className="exchange" key={answer.id}><h3>第 {i + 1} 轮 · {answer.question.text}</h3>
        <p className="preserve">{answer.text}</p>{ref && <><strong>你指出的片段</strong><ProjectExcerpt item={ref} pdfUrl={pdfUrl} /></>}
      </div>
    })}
  </section>
}
