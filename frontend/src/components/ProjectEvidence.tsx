import type { Excerpt, Interview } from '../types'

export function ProjectExcerpt({ item }: { item: Excerpt }) {
  return <div className="project-excerpt">
    <a href={item.url} target="_blank" rel="noreferrer">{item.path} · L{item.start}–{item.end} ↗</a>
    <pre tabIndex={0} aria-label={`${item.path} 源码片段`}><code>{item.code}</code></pre>
  </div>
}

export function ProjectReplay({ session }: { session: Interview }) {
  const project = session.project
  if (!project) return null
  return <section className="card project-replay">
    <h2>项目答辩回放</h2><h3>简历原句</h3><blockquote>{session.resume}</blockquote>
    <p><a href={project.url} target="_blank" rel="noreferrer">{project.title} ↗</a> · 提交 <code>{project.sha.slice(0, 7)}</code></p>
    {session.answers.map((answer, i) => {
      const ref = project.excerpts.find(item => item.id === answer.excerpt_id)
      return <div className="exchange" key={answer.id}><h3>第 {i + 1} 轮 · {answer.question.text}</h3>
        <p className="preserve">{answer.text}</p>{ref && <><strong>你指出的片段</strong><ProjectExcerpt item={ref} /></>}
      </div>
    })}
  </section>
}
