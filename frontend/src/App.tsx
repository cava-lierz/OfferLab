import { useEffect, useState } from 'react'
import { usePolling, useRoute } from './hooks'
import { clearInterviewDrafts } from './drafts'
import { deleteInterview } from './api'
import { mergeHistory, newest } from './session'
import PreparePage from './pages/PreparePage'
import HistoryPage from './pages/HistoryPage'
import InterviewPage from './pages/InterviewPage'
import type { Health, History, Interview, Preparation } from './types'
import './generation.css'

const empty: Preparation = { role: '', resume: '', jd: '', main_count: 5 }

export default function App() {
  const route = useRoute()
  const [health, setHealth] = useState<Health | null>(null)
  const [history, setHistory] = useState<History[]>([])
  const [form, setForm] = useState<Preparation>(empty)
  const sessionId = route.startsWith('interview/') ? route.slice(10) : null
  const view = route === 'history' ? 'history' : sessionId ? 'interview' : 'prepare'
  const healthPoll = usePolling<Health>('/health', setHealth, 30_000)
  const historyPoll = usePolling<History[]>('/interviews', items => {
    setHistory(previous => {
      const known = new Map(previous.map(item => [item.id, item]))
      return items.map(item => newest(known.get(item.id) ?? null, item))
    })
  }, 5000)
  useEffect(() => { historyPoll.refresh() }, [route])
  function update(state: Interview, created = false) {
    const { id, role, status, mode, created_at, updated_at, main_count, generation, error, revision } = state
    const summary: History = { id, role, status, mode, created_at, updated_at, main_count, generation, error, revision, answered: state.answers.length }
    setHistory(previous => {
      if (!created && !previous.some(item => item.id === state.id)) return previous
      return mergeHistory(previous, [summary])
    })
  }
  async function remove(id: string) {
    await deleteInterview(id)
    clearInterviewDrafts(id)
    historyPoll.refresh()
    setHistory(previous => previous.filter(item => item.id !== id))
  }
  return <div className="app-shell">
    <aside className="sidebar">
      <a href="#prepare" className="brand"><span className="brand-mark">O<span /></span><span>OfferLab<small>面试练习室</small></span></a>
      <div className="nav-label">你的练习空间</div>
      <nav aria-label="主导航">
        <a className={view === 'prepare' ? 'selected' : ''} href="#prepare"><span aria-hidden="true">✦</span> 开始练习</a>
        <a className={view === 'interview' ? 'selected' : ''} href={sessionId ? '#interview/' + sessionId : '#history'}><span aria-hidden="true">◫</span> 面试与复盘</a>
        <a className={view === 'history' ? 'selected' : ''} href="#history"><span aria-hidden="true">◷</span> 历史记录 <span className="count">{history.length}</span></a>
      </nav>
      <div className="sidebar-note"><div className="tiny-label">PRACTICE MAKES PROGRESS</div><p>每一次表达，<br />都可以更进一步。</p><span>从经历中提炼你的价值。</span></div>
      <div className="sidebar-footer"><span className="avatar">练</span><div>个人练习空间<small>本机保存 · 文字面试</small></div></div>
    </aside>

    <main>
      <header className="topbar"><span>工作台 <span className="slash">/</span> {view === 'prepare' ? '面试准备' : view === 'history' ? '历史记录' : '面试与复盘'}</span>
        <span className={'mode-pill ' + (health?.mode === 'demo' ? 'demo' : '')}>{health ? health.mode === 'demo' ? '演示模式' : 'OpenClaw 模式' : '服务未连接'}</span>
      </header>
      <div className="page-content">
        {historyPoll.error && view === 'history' && <div className="alert error" role="alert"><span>暂时无法更新历史记录。{historyPoll.error}</span><button className="text-button" onClick={historyPoll.refresh}>刷新记录</button></div>}

        {health?.mode === 'demo' && <div className="demo-banner">当前使用本地演示数据，用于体验完整流程；问题与反馈不是实时模型生成。</div>}
        {health?.mode === 'openclaw' && !health.token_configured && <div className="alert error">Gateway Token 尚未配置，请运行本机配置脚本并重启后端。</div>}

        {healthPoll.error && <div className="alert error" role="alert">后端连接暂时不可用，正在重连。<button className="text-button" onClick={healthPoll.refresh}>检查连接</button></div>}
        {view === 'prepare' && <PreparePage health={health} form={form} setForm={setForm} onCreated={state => { historyPoll.refresh(); update(state, true) }} />}
        {view === 'history' && <HistoryPage history={history} loaded={historyPoll.loaded} onDelete={remove} />}
        {sessionId && <InterviewPage key={sessionId} id={sessionId} onUpdate={update} onPrepare={value => { setForm(value); window.location.hash = 'prepare' }} />}
        <footer className="page-footer">OfferLab <span>把经历说清楚，把下一步想明白。</span></footer>
      </div>
    </main>
  </div>
}
