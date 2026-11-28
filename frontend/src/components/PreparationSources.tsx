import type { PreparationResearch } from '../types'

export function PreparationSources({ research }: { research?: PreparationResearch | null }) {
  if (!research) return null
  const notes = {
    skipped: '面试官按岗位要求直接备课。',
    unavailable: '面试官反馈联网工具暂不可用，本场按岗位要求备课。',
    no_match: '面试官反馈本次检索未找到合适的备课资料。',
  }
  if (research.status !== 'used') return <p className="muted">{notes[research.status]}</p>
  return <details>
    <summary>面试官提供的备课参考（{research.sources.length}）</summary>
    <ul>{research.sources.map(item => <li key={item.url}>
      <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
    </li>)}</ul>
  </details>
}
