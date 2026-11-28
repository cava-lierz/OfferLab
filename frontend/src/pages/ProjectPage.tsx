import { useState } from 'react'
import { api, ApiError } from '../api'
import { clearCreation, creationId } from '../creation'
import { useMutation } from '../hooks'
import { ProjectExcerpt } from '../components/ProjectEvidence'
import type { Health, Interview, Project } from '../types'

const example = 'https://github.com/cava-lierz/OfferLab/pull/1'

export default function ProjectPage({ health, onCreated }: { health: Health | null; onCreated: (value: Interview) => void }) {
  const [url, setUrl] = useState('')
  const [claim, setClaim] = useState('')
  const [project, setProject] = useState<Project | null>(null)
  const [ids, setIds] = useState<string[]>([])
  const [file, setFile] = useState('')
  const { busy, error, run, clearError } = useMutation()
  function reset(next: string) { setUrl(next); setProject(null); setIds([]); clearError() }
  async function load() {
    const data = await api<Project>('/projects/preview', { url })
    setProject(data); setFile(data.excerpts[0].path); setIds([])
  }
  async function start() {
    if (!project) return
    const excerpt_ids = project.excerpts.filter(row => ids.includes(row.id)).map(row => row.id)
    const request_id = await creationId({ claim: claim.trim(), preview_id: project.id, excerpt_ids })
    try {
      const value = await api<Interview>('/projects/interviews', { claim, preview_id: project.id, excerpt_ids, request_id })
      clearCreation(request_id); onCreated(value)
      if (window.location.hash === '#project') window.location.hash = `interview/${value.id}`
    } catch (err) {
      if (err instanceof ApiError && [409, 410].includes(err.status)) clearCreation(request_id)
      throw err
    }
  }
  return <>
    <section className="page-heading compact"><h1>用自己的项目面试</h1><p>选一条简历经历和自己负责的改动。第一轮讲清贡献，第二轮指着代码或测试回答追问。</p></section>
    <section className="card preparation project-setup">
      <label htmlFor="project-claim">简历上的项目经历</label>
      <textarea id="project-claim" rows={2} maxLength={800} disabled={busy} value={claim} onChange={e => setClaim(e.target.value)} placeholder="例如：我为面试创建流程增加了断线重试，避免重复建场。" />
      <label htmlFor="project-url">公开 GitHub PR 链接</label>
      <input id="project-url" type="url" disabled={busy} value={url} onChange={e => reset(e.target.value)} placeholder="https://github.com/owner/repo/pull/1" />
      <div className="project-actions"><button type="button" className="secondary" disabled={busy || !url.trim()} onClick={() => void run(load)}>{busy && !project ? '正在读取…' : '读取改动'}</button>
        <button type="button" className="text-button" disabled={busy} onClick={() => { reset(example); setClaim('我为面试创建流程增加了断线重试，避免同一次提交重复建场。') }}>使用 OfferLab 示例</button></div>
      {project && <><h2>{project.title}</h2><p>选择你负责的 1–3 段改动。已选 {ids.length} 段。</p>
        <p className="muted">提交 {project.sha.slice(0, 7)} · 已读取 {project.scanned_files}/{project.file_count} 个文件，每个文件最多展示 8 段新增文本。</p>
        <label htmlFor="project-file">改动文件</label><select id="project-file" value={file} onChange={e => setFile(e.target.value)}>{[...new Set(project.excerpts.map(row => row.path))].map(path => <option key={path}>{path}</option>)}</select>
        {project.excerpts.filter(row => row.path === file).map(row => <div className="project-choice" key={row.id}>
          <label><input type="checkbox" disabled={busy || (!ids.includes(row.id) && ids.length >= 3)} checked={ids.includes(row.id)} onChange={e => setIds(e.target.checked ? [...ids, row.id] : ids.filter(id => id !== row.id))} /> 我负责第 {row.start}–{row.end} 行</label>
          <ProjectExcerpt item={row} /></div>)}
        <p className="muted">{health?.mode === 'openclaw' ? 'OpenClaw 模式会将简历原句、所选片段与回答发送至学校 Gateway。' : '演示模式在本机生成问答和复盘。'}</p>
        <button className="primary" disabled={busy || !health || !ids.length || claim.trim().length < 5} onClick={() => void run(start)}>准备项目面试</button>
      </>}
      {error && <p className="alert error" role="alert">{error}</p>}
    </section>
  </>
}
