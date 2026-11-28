import type { Preparation } from './types'

type Attempt = { digest: string; id: string }
const key = 'offerlab:pending-create'
let pending: Attempt | null = null

// Keep only a fingerprint and the retry ID in this tab, including across reloads.
export async function creationId(form: Preparation): Promise<string> {
  const fields = [form.role, form.resume, form.jd, form.main_count, form.practice_focus || '']
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(fields)))
  const digest = Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('')
  try {
    pending ??= JSON.parse(sessionStorage.getItem(key) || 'null')
  } catch { /* The in-memory attempt still supports retries. */ }
  if (pending?.digest === digest && typeof pending.id === 'string') return pending.id
  pending = { digest, id: crypto.randomUUID() }
  try { sessionStorage.setItem(key, JSON.stringify(pending)) } catch { /* Keep in memory. */ }
  return pending.id
}

export function clearCreation(id: string) {
  if (pending?.id !== id) return
  pending = null
  try { sessionStorage.removeItem(key) } catch { /* Storage may be disabled. */ }
}
