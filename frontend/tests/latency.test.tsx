import assert from 'node:assert/strict'
import { test } from 'node:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { GenerationPanel } from '../src/components/GenerationPanel'
import { InterviewSetup } from '../src/components/InterviewSetup'
import { Transcript } from '../src/components/Transcript'
import { mergeHistory, newest, statusLabel } from '../src/session'
import { clearDraft, clearInterviewDrafts, draftKey, readDraft, saveDraft } from '../src/drafts'
import type { Interview } from '../src/types'

const base: Interview = {
  id: 'test', role: '测试岗位', resume: '', jd: '', main_count: 1, mode: 'openclaw',
  status: 'reporting', plan: [], current: null, answers: [], report: null,
  error: null, created_at: 1, updated_at: 1, revision: 1,
}
function panel(state: Interview) {
  return renderToStaticMarkup(<GenerationPanel session={state} busy={false} onRetry={() => {}} />)
}
test('late polling cannot replace newer saved answers or cross interview boundaries', () => {
  const latest = { ...base, revision: 8, status: 'completed' as const }
  assert.equal(newest(latest, { ...base, revision: 7 }), latest)
  assert.equal(newest(latest, { ...base, id: 'another' }).id, 'another')
  assert.equal(newest({ ...base, revision: undefined }, { ...base, revision: 1 }).revision, 1)
})
test('history polling preserves a record created after the list request started', () => {
  const created = { ...base, id: 'new', created_at: 2, answered: 0 }
  const older = { ...base, answered: 0 }
  assert.deepEqual(mergeHistory([created, older], [older]).map(item => item.id), ['new', 'test'])
  assert.equal(mergeHistory([{ ...older, revision: 8, answered: 3 }], [older])[0].answered, 3)
})
test('queued work only shows an accessible spinner without timing or duplicate submission', () => {
  const state: Interview = { ...base, generation: { id: 'job', task: 'report', status: 'queued', phase: 'queued', queued_at: Date.now() / 1000 - 45, timeout_seconds: 300 } }
  const html = panel(state)
  assert.match(html, /role="status" aria-label="加载中"/)
  assert.match(html, /loading-spinner/)
  assert.doesNotMatch(html, /<button|秒|排队|模型|校验|<strong>|%/)
  assert.equal(statusLabel(state), '加载中')
})
test('running validation has the same simple loading indicator', () => {
  const html = panel({ ...base, generation: { id: 'job', task: 'report', status: 'running', phase: 'validating', queued_at: 1, started_at: Date.now() / 1000 - 80, deadline_at: Date.now() / 1000 + 220, timeout_seconds: 300 } })
  assert.match(html, /loading-spinner/)
  assert.doesNotMatch(html, /<button|秒|排队|模型|校验|预计/)
})
test('failed and legacy records expose retry without hiding saved answers', () => {
  const html = panel({ ...base, error: '模型超时' })
  assert.match(html, /重试/)
  assert.match(html, /模型超时/)
  assert.match(html, /不会重复提交回答/)
  assert.match(panel(base), /生成复盘报告/)
})
test('prepared interview reveals neither planned questions nor future topics', () => {
  const state: Interview = { ...base, status: 'ready', main_count: 2,
    plan: [{ topic: '隐藏主题一', question: '隐藏问题一' }, { topic: '隐藏主题二', question: '隐藏问题二' }] }
  const html = renderToStaticMarkup(<InterviewSetup session={state} busy={false} onStart={() => {}} onPrepare={() => {}} />)
  assert.match(html, /开始面试/)
  assert.match(html, /2 道主问题/)
  assert.doesNotMatch(html, /隐藏主题|隐藏问题/)
})
test('saved transcript remains available while waiting and escapes user HTML', () => {
  const html = renderToStaticMarkup(<Transcript answers={[{ id: 'answer', request_id: 'req', text: '<script>example</script>', question: { id: 'q', text: '问题', topic: '项目', main_index: 0, followup: 1 } }]} />)
  assert.match(html, /已保存/)
  assert.match(html, /&lt;script&gt;/)
  assert.doesNotMatch(html, /<script>/)
})
test('draft survives remount with the same request id, is isolated, and clears on acknowledgement', () => {
  const items = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    get length() { return items.size },
    key: (index: number) => [...items.keys()][index] ?? null,
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => items.set(key, value),
    removeItem: (key: string) => items.delete(key),
  } })
  const key = draftKey('one', 'question')
  const draft = { text: '刷新前的回答', request_id: 'stable-request' }
  assert.equal(saveDraft(key, draft), true)
  assert.deepEqual(readDraft(key), draft)
  assert.equal(readDraft(draftKey('two', 'question')).text, '')
  clearDraft(key)
  assert.equal(readDraft(key).text, '')
  saveDraft(key, draft)
  saveDraft(draftKey('one', 'next'), draft)
  saveDraft(draftKey('one-more', 'other'), draft)
  clearInterviewDrafts('one')
  assert.deepEqual([...items.keys()], [draftKey('one-more', 'other')])
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('blocked') } })
  assert.equal(saveDraft(key, draft), false)
  assert.equal(readDraft(key).text, '')
  assert.doesNotThrow(() => clearDraft(key))
})

test('creation retries reuse one ID until the form changes or the server acknowledges it', async () => {
  const { creationId, clearCreation } = await import('../src/creation')
  const values = new Map<string, string>()
  const original = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage')
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  } })
  try {
    const form = { role: '开发', resume: '私有简历文本', jd: '', main_count: 1 }
    const first = await creationId(form)
    assert.equal(await creationId({ ...form }), first)
    assert.ok(![...values.values()].join('').includes(form.resume))
    const edited = { ...form, practice_focus: '个人贡献' }
    const second = await creationId(edited)
    assert.notEqual(second, first)
    clearCreation(first)
    assert.equal(await creationId(edited), second)
    clearCreation(second)
    assert.equal(values.size, 0)
    const next = await creationId(edited)
    assert.notEqual(next, second)
    clearCreation(next)
  } finally {
    if (original) Object.defineProperty(globalThis, 'sessionStorage', original)
    else Reflect.deleteProperty(globalThis, 'sessionStorage')
  }
})
