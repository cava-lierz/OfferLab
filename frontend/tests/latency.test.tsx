import assert from 'node:assert/strict'
import { test } from 'node:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { GenerationPanel } from '../src/components/GenerationPanel'
import { Transcript } from '../src/components/Transcript'
import { mergeHistory, newest, statusLabel } from '../src/session'
import { clearDraft, draftKey, readDraft, saveDraft } from '../src/drafts'
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
test('queue uses durable timestamps and does not offer a duplicate generation button', () => {
  const state: Interview = { ...base, generation: { id: 'job', task: 'report', status: 'queued', phase: 'queued', queued_at: Date.now() / 1000 - 45, timeout_seconds: 300 } }
  const html = panel(state)
  assert.match(html, /已进入队列/)
  assert.match(html, /已排队/)
  assert.match(html, /<strong>45<\/strong>/)
  assert.match(html, /可以离开或刷新/)
  assert.doesNotMatch(html, /<button|预计完成时间|%/)
  assert.equal(statusLabel(state), '复盘报告排队中')
})
test('running state distinguishes real validation and the timeout is not an ETA', () => {
  const html = panel({ ...base, generation: { id: 'job', task: 'report', status: 'running', phase: 'validating', queued_at: 1, started_at: Date.now() / 1000 - 80, deadline_at: Date.now() / 1000 + 220, timeout_seconds: 300 } })
  assert.match(html, /已收到模型结果，正在校验/)
  assert.match(html, /不是预计完成时间/)
  assert.doesNotMatch(html, /<button/)
})
test('failed and legacy records expose retry without hiding saved answers', () => {
  const html = panel({ ...base, error: '模型超时' })
  assert.match(html, /重新生成/)
  assert.match(html, /模型超时/)
  assert.match(html, /不会重复提交回答/)
  assert.match(panel(base), /生成复盘报告/)
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
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('blocked') } })
  assert.equal(saveDraft(key, draft), false)
  assert.equal(readDraft(key).text, '')
  assert.doesNotThrow(() => clearDraft(key))
})
