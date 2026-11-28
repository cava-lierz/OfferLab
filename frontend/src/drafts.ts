export type Draft = { text: string; request_id: string }
export const draftKey = (interviewId: string, questionId: string) => `offerlab:answer:${interviewId}:${questionId}`
export function readDraft(key: string): Draft {
  try {
    const value = JSON.parse(localStorage.getItem(key) || 'null')
    if (typeof value?.text === 'string' && typeof value?.request_id === 'string') return value
  } catch { /* Storage may be unavailable; typing still works. */ }
  return { text: '', request_id: crypto.randomUUID() }
}
export function saveDraft(key: string, draft: Draft): boolean {
  try { localStorage.setItem(key, JSON.stringify(draft)); return true } catch { return false }
}
export function clearDraft(key: string) {
  try { localStorage.removeItem(key) } catch { /* No stored draft to clear. */ }
}

export function clearInterviewDrafts(interviewId: string) {
  const prefix = draftKey(interviewId, '')
  try {
    for (let index = localStorage.length - 1; index >= 0; index--) {
      const key = localStorage.key(index)
      if (key?.startsWith(prefix)) localStorage.removeItem(key)
    }
  } catch { /* Browser storage may be unavailable. */ }
}
