import type { History, Interview, Status } from './types'

export const statuses: Record<Status, string> = {
  preparing: '等待生成计划', ready: '计划待确认', active: '面试进行中',
  awaiting_next: '等待下一题', reporting: '待生成复盘', completed: '已完成',
}
export const taskNames = { plan: '面试计划', decision: '下一道问题', report: '复盘报告' }
export function isPending(state: Pick<Interview, 'generation'>) {
  return state.generation?.status === 'queued' || state.generation?.status === 'running'
}
export function statusLabel(state: History | Interview) {
  if (isPending(state) && state.generation) {
    return `${taskNames[state.generation.task]}${state.generation.status === 'queued' ? '排队中' : '生成中'}`
  }
  return state.error ? '生成失败 · 可重试' : statuses[state.status]
}
// A late poll must never overwrite a newer mutation response.
export function newest<T extends { id: string; revision?: number }>(current: T | null, incoming: T): T {
  return current?.id === incoming.id && (current.revision ?? 0) > (incoming.revision ?? 0) ? current : incoming
}
export function mergeHistory(current: History[], incoming: History[]) {
  const byId = new Map(current.map(item => [item.id, item]))
  for (const item of incoming) byId.set(item.id, newest(byId.get(item.id) ?? null, item))
  return [...byId.values()].sort((a, b) => b.created_at - a.created_at).slice(0, 100)
}
export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '操作失败，请重试。'
}
