import { LoadingIndicator } from '../components/LoadingIndicator'
import type { History } from '../types'
import { isPending, statusLabel } from '../session'

export default function HistoryPage({ history, loaded }: { history: History[]; loaded: boolean }) {
  const completed = history.filter(item => item.status === 'completed').length
  if (!loaded && !history.length) return <div className="generation-loading"><LoadingIndicator /></div>
  return <>
          <section className="page-heading"><div className="eyebrow">YOUR PRACTICE JOURNAL</div><h1>每一次练习，都算数。</h1><p>回到上一次对话，或从复盘中找到下一步。</p></section>
          <div className="stats"><div><strong>{history.length}</strong><span>场练习记录</span></div><div><strong>{completed}</strong><span>场已完成</span></div><div><strong>{history.reduce((sum, item) => sum + item.answered, 0)}</strong><span>次已保存回答</span></div></div>
          <section className="card"><div className="section-title"><h2>最近的面试</h2><a className="primary button-link" href="#prepare">新建面试</a></div>
            {!history.length ? <div className="empty"><span>◷</span><h3>第一场练习，从现在开始</h3><p>完成准备后，你的面试与复盘会保存在这里。</p></div> : <div className="history-list">{history.map(item => <a className="history-row" href={'#interview/' + item.id} key={item.id}><div className="history-icon">◫</div><div className="grow"><h3>{item.role}</h3><p>{new Date(item.created_at * 1000).toLocaleString('zh-CN')} · {item.answered} 次回答 · {item.mode === 'demo' ? '演示模式' : 'OpenClaw'}</p></div><span className={'status ' + (item.status === 'completed' ? 'done' : '')}>{isPending(item) ? <LoadingIndicator /> : statusLabel(item)}</span><span className="history-action">{item.status === 'completed' ? '查看复盘' : isPending(item) ? '查看面试' : '继续练习'}</span></a>)}</div>}
          </section>
        </>
}
