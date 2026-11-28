import { useState } from 'react'
import { api, ApiError } from '../api'
import { clearCreation, creationId } from '../creation'
import { useMutation } from '../hooks'
import { locationLabel, ProjectExcerpt } from '../components/ProjectEvidence'
import type { Health, Interview, Project } from '../types'

const example = 'https://github.com/cava-lierz/OfferLab/pull/1'

export default function ProjectPage({ health, onCreated }: { health: Health | null; onCreated: (value: Interview) => void }) {
  const [source, setSource] = useState<'pr' | 'pdf'>('pr')
  const [url, setUrl] = useState('')
  const [claim, setClaim] = useState('')
  const [role, setRole] = useState('')
  const [requirement, setRequirement] = useState('')
  const [project, setProject] = useState<Project | null>(null)
  const [ids, setIds] = useState<string[]>([])
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [file, setFile] = useState('')
  const { busy, error, run, clearError } = useMutation()
  function reset() { setProject(null); setIds([]); setNotes({}); clearError() }
  function accept(data: Project) {
    if (data.id !== project?.id) { setIds([]); setNotes({}); setFile(data.excerpts[0].path) }
    setProject(data)
  }
  async function upload(pdf: File) {
    if (pdf.size > 5 * 1024 * 1024) throw new Error('请选择不超过 5 MB 的 PDF。')
    const form = new FormData(); form.append('file', pdf)
    accept(await api<Project>('/projects/pdf', form))
  }
  const selected = project?.excerpts.filter(row => ids.includes(row.id)) || []
  const missingNote = selected.some(row => row.page !== undefined && !row.code && !notes[row.id]?.trim())
  async function start() {
    if (!project) return
    const fields = { claim: claim.trim(), target_role: role.trim(), requirement: requirement.trim(), preview_id: project.id,
      excerpt_ids: selected.map(row => row.id), page_notes: Object.fromEntries(selected.filter(row => notes[row.id]?.trim()).map(row => [row.id, notes[row.id].trim()])) }
    const request_id = await creationId(fields)
    try {
      const value = await api<Interview>('/projects/interviews', { ...fields, request_id })
      clearCreation(request_id); onCreated(value)
      if (window.location.hash === '#project') window.location.hash = `interview/${value.id}`
    } catch (err) {
      if (err instanceof ApiError && [409, 410].includes(err.status)) clearCreation(request_id)
      throw err
    }
  }
  function useExample() {
    reset(); setUrl(example); setRole('后端开发工程师'); setRequirement('能处理并发与异常重试，并用测试验证数据一致性。')
    setClaim('我为面试创建流程增加了断线重试，避免同一次提交重复建场。')
  }
  return <>
    <section className="page-heading compact"><h1>用自己的项目面试</h1><p>带一条招聘要求和一份作品，练习如何向这个岗位的面试官说明你的贡献。</p></section>
    <section className="card preparation project-setup">
      <label htmlFor="project-role">目标岗位</label><input id="project-role" list="project-roles" maxLength={80} disabled={busy} value={role} onChange={e => setRole(e.target.value)} placeholder="选择或输入岗位" />
      <datalist id="project-roles">{['后端开发工程师', '测试开发工程师', '产品经理', '数据分析师', '科研助理'].map(r => <option key={r} value={r} />)}</datalist>
      <label htmlFor="project-requirement">想练的一条招聘要求</label><textarea id="project-requirement" rows={2} maxLength={500} disabled={busy} value={requirement} onChange={e => setRequirement(e.target.value)} placeholder="粘贴职位描述中的原句" />
      <label htmlFor="project-claim">简历上的项目经历</label><textarea id="project-claim" rows={2} maxLength={800} disabled={busy} value={claim} onChange={e => setClaim(e.target.value)} placeholder="用一句话写下你的贡献，至少 5 字" />
      <div className="project-actions" role="group" aria-label="作品类型">{(['pr', 'pdf'] as const).map(kind => <button key={kind} className={kind === source ? 'primary' : 'secondary'} disabled={busy} aria-pressed={source === kind} onClick={() => { if (kind !== source) { reset(); setSource(kind) } }}>{kind === 'pdf' ? 'PDF 作品' : 'GitHub PR'}</button>)}</div>
      {source === 'pr' ? <><label htmlFor="project-url">公开 GitHub PR 链接</label><input id="project-url" type="url" disabled={busy} value={url} onChange={e => { reset(); setUrl(e.target.value) }} placeholder="https://github.com/owner/repo/pull/1" />
        <div className="project-actions"><button className="secondary" disabled={busy || !url.trim()} onClick={() => void run(async () => accept(await api<Project>('/projects/preview', { url })))}>读取改动</button>
          <button className="text-button" disabled={busy} onClick={useExample}>使用 OfferLab 示例</button></div></> : <>
        <label htmlFor="portfolio-pdf">上传原型、项目报告或实验结果（PDF）</label><p className="muted">最多 5 MB、20 页。原件保存在本机；面试使用所选页的文字和你的说明。</p>
        <input type="file" id="portfolio-pdf" disabled={busy} accept="application/pdf,.pdf" onChange={e => { const pdf = e.target.files?.[0]; e.target.value = ''; if (pdf) { reset(); void run(() => upload(pdf)) } }} /></>}
      {busy && <p role="status">正在处理…</p>}
      {project && <><h2>{project.title}</h2><p>选择能说明你贡献的 1–3 处依据。已选 {ids.length} 处。</p>
        {project.kind === 'pdf' ? <p className="muted">共 {project.page_count} 页。没有可提取文字的页面，请补充说明。</p> : <><p className="muted">提交 {project.sha.slice(0, 7)} · 已读取 {project.scanned_files}/{project.file_count} 个文件。</p>
          <label htmlFor="project-file">改动文件</label><select id="project-file" value={file} onChange={e => setFile(e.target.value)}>{[...new Set(project.excerpts.map(row => row.path))].map(path => <option key={path}>{path}</option>)}</select></>}
        {project.excerpts.filter(row => project.kind === 'pdf' || row.path === file).map(row => <div className="project-choice" key={row.id}>
          <label><input type="checkbox" disabled={busy || (!ids.includes(row.id) && ids.length >= 3)} checked={ids.includes(row.id)} onChange={e => setIds(e.target.checked ? [...ids, row.id] : ids.filter(id => id !== row.id))} /> 选用 {locationLabel(row)}</label>
          <ProjectExcerpt item={row} pdfUrl={`/api/projects/previews/${project.id}/portfolio.pdf`} />
          {row.page !== undefined && ids.includes(row.id) && <label>第 {row.page} 页的说明{row.code ? '（选填）' : '（必填）'}<textarea maxLength={500} value={notes[row.id] || ''} onChange={e => setNotes({ ...notes, [row.id]: e.target.value })} /></label>}</div>)}
        <p className="muted">{health?.mode === 'openclaw' ? '目标岗位、招聘要求、简历原句、选中的文字、页面说明与回答会发往学校 Gateway。' : '本场在本机演示模式下生成问答和复盘。'}</p>
        <button className="primary" disabled={busy || !health || !role.trim() || !requirement.trim() || !ids.length || claim.trim().length < 5 || missingNote} onClick={() => void run(start)}>准备项目面试</button>
      </>}
      {error && <p className="alert error" role="alert">{error}</p>}
    </section>
  </>
}
