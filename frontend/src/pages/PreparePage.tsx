import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api'
import { useMutation } from '../hooks'
import type { Health, Interview, Preparation } from '../types'

const example: Preparation = {
  role: '产品经理实习生', main_count: 3,
  resume: '【虚构演示简历】我是大三学生，参与开发校园二手交易小程序，负责需求访谈与流程设计。访谈了 12 位同学，发现商品信息不完整、约定交易时间困难两个问题。我设计了结构化发布表单和可选交易时段，与两位开发同学合作完成原型及上线。试运行两周收集了 30 条反馈，后续希望改进信息审核流程。',
  jd: '【演示 JD】参与用户需求调研、竞品分析与产品设计，能清楚表达方案，愿意结合数据和反馈持续迭代。',
}

export default function PreparePage({ health, form, setForm, onCreated }: {
  health: Health | null; form: Preparation; setForm: React.Dispatch<React.SetStateAction<Preparation>>
  onCreated: (state: Interview) => void
}) {
  const { busy, error, run } = useMutation()
  const [notice, setNotice] = useState('')
  function create(e: FormEvent) {
    e.preventDefault()
    void run(async () => {
      const created = await api<Interview>('/interviews', form)
      onCreated(created)
      if ((window.location.hash.slice(1) || 'prepare') === 'prepare') window.location.hash = 'interview/' + created.id
    })
  }
  return <>
    {error && <div className="alert error" role="alert">{error} <a href="#history">查看已保存记录</a></div>}
    {notice && <div className="alert success" role="status">{notice}</div>}
          <section className="page-heading"><div className="eyebrow">READY FOR YOUR NEXT OPPORTUNITY</div><h1>让下一次面试，更有准备。</h1><p>带上你的经历和目标岗位，开始一场专属于你的模拟面试。</p></section>
          <div className="steps"><span className="current"><b>1</b> 准备材料</span><i /><span><b>2</b> 确认计划</span><i /><span><b>3</b> 对话练习</span><i /><span><b>4</b> 回顾成长</span></div>
          <div className="preparation-grid">
            <form className="card preparation" onSubmit={create}>
              <div className="section-title"><h2>准备你的面试</h2><button type="button" className="text-button" disabled={busy} onClick={() => { setForm(example); setNotice('已填入虚构示例，可修改后使用。') }}>使用示例体验</button></div>
              <label htmlFor="role">目标岗位 <span className="required">*</span></label>
              <input id="role" placeholder="例如：产品经理实习生、算法工程师……" required maxLength={100} value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} />
              <div className="label-row"><label htmlFor="resume">简历与项目经历 <span className="required">*</span></label><span>至少 20 字</span></div>
              <label className="upload-box"><span className="upload-icon" aria-hidden="true">↥</span><strong>上传简历，或在下方粘贴文本</strong><span>文本型 PDF / TXT · 最大 5 MB</span>
                <input type="file" accept=".pdf,.txt" disabled={busy} onChange={e => {
                  const file = e.target.files?.[0]; e.target.value = ''; if (!file) return
                  void run(async () => {
                    if (file.size > 5 * 1024 * 1024) throw new Error('文件不能超过 5 MB。')
                    const body = new FormData(); body.append('file', file)
                    const result = await api<{ text: string }>('/resumes/parse', body)
                    setForm(previous => ({ ...previous, resume: result.text })); setNotice('解析完成，请检查并修正下方文本后继续。')
                  })
                }} />
              </label>
              <textarea id="resume" className="resume-input" required minLength={20} maxLength={20000} placeholder="粘贴你的教育背景、项目经历、个人职责和成果……" value={form.resume} onChange={e => setForm({ ...form, resume: e.target.value })} />
              <div className="label-row"><label htmlFor="jd">岗位描述 <span className="optional">选填</span></label><span>帮助问题更贴近岗位</span></div>
              <textarea id="jd" maxLength={12000} placeholder="粘贴 JD 中的工作职责、任职要求。暂不支持自动读取岗位链接。" value={form.jd} onChange={e => setForm({ ...form, jd: e.target.value })} />
              <div className="form-bottom"><label htmlFor="count">主问题数量 <select id="count" value={form.main_count} onChange={e => setForm({ ...form, main_count: Number(e.target.value) })}>{[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n} 道</option>)}</select></label><button className="primary" disabled={busy || !health} type="submit">{busy ? '正在保存…' : '保存材料并生成计划'}</button></div>
              <p className="privacy-note">材料保存在本机；OpenClaw 模式下会发送至学校 Gateway 用于生成问题和反馈。</p>
            </form>
            <aside className="right-column">
              <div className="feature-card"><div className="eyebrow">YOUR NEXT CHAPTER</div><h2>练习的不只是回答，<br />还有表达自己的方式。</h2><div className="orbit-art" aria-hidden="true"><div className="orbit-ring r1" /><div className="orbit-ring r2" /><div className="orbit-ring r3" /><div className="orbit-center">✦</div><span className="orbit-tag tag-one">经历</span><span className="orbit-tag tag-two">思考</span><span className="orbit-tag tag-three">表达</span></div></div>
              <div className="card expectations"><h3>这次练习，你将获得</h3><div><span>◎</span><p><strong>围绕经历的个性化提问</strong><small>从你的简历与目标岗位出发</small></p></div><div><span>◈</span><p><strong>有边界的深入追问</strong><small>每道主问题最多追问 2 次</small></p></div><div><span>▤</span><p><strong>有回答依据的复盘</strong><small>原文引用与下一步练习建议</small></p></div></div>
              <div className="tip"><strong>开始前的小建议</strong><p>用具体事例说明“你做了什么”，比罗列技能更有帮助。无需完美，真实表达就好。</p></div>
            </aside>
          </div>
</>
}
