import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api'
import { errorMessage } from './session'

export function useRoute() {
  const read = () => window.location.hash.slice(1) || 'prepare'
  const [route, setRoute] = useState(read)
  useEffect(() => {
    const changed = () => setRoute(read())
    window.addEventListener('hashchange', changed)
    return () => window.removeEventListener('hashchange', changed)
  }, [])
  return route
}

// One request at a time, abort on navigation, resume immediately on tab focus.
export function usePolling<T>(path: string, accept: (value: T) => void, intervalMs: number) {
  const [error, setError] = useState('')
  const [missing, setMissing] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [refreshToken, setRefreshToken] = useState(0)
  const acceptRef = useRef(accept)
  const intervalRef = useRef(intervalMs)
  acceptRef.current = accept
  intervalRef.current = intervalMs
  // Ignore older list requests as soon as a create or delete is acknowledged.
  const generation = useRef(0)
  const refresh = useCallback(() => setRefreshToken(++generation.current), [])
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    let inFlight = false
    let failures = 0
    async function poll() {
      if (inFlight || controller.signal.aborted) return
      clearTimeout(timer)
      inFlight = true
      try {
        const value = await api<T>(path, undefined, controller.signal)
        if (!controller.signal.aborted && refreshToken === generation.current) {
          setMissing(false)
          acceptRef.current(value); setError(''); setLoaded(true); failures = 0
        }
      } catch (e) {
        if (!controller.signal.aborted && refreshToken === generation.current) {
          setMissing(e instanceof ApiError && e.status === 404)
          setError(errorMessage(e)); failures++
        }
      } finally {
        inFlight = false
        if (!controller.signal.aborted) {
          const delay = Math.max(intervalRef.current, document.hidden ? 10_000 : 0, Math.min(failures * 2000, 10_000))
          timer = setTimeout(poll, delay)
        }
      }
    }
    const wake = () => { if (!document.hidden) void poll() }
    void poll()
    window.addEventListener('focus', wake)
    document.addEventListener('visibilitychange', wake)
    return () => {
      controller.abort(); clearTimeout(timer)
      window.removeEventListener('focus', wake)
      document.removeEventListener('visibilitychange', wake)
    }
  }, [path, refreshToken])
  return { error, loaded, missing, refresh }
}

export function useMutation() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const lock = useRef(false)
  async function run(work: () => Promise<void>) {
    if (lock.current) return
    lock.current = true; setBusy(true); setError('')
    try { await work() } catch (e) { setError(errorMessage(e)) }
    finally { lock.current = false; setBusy(false) }
  }
  return { busy, error, run, clearError: () => setError('') }
}
