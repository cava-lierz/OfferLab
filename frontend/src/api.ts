export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

async function request(path: string, options: RequestInit) {
  const timeout = AbortSignal.timeout(15_000)
  try {
    const response = await fetch('/api' + path, {
      ...options, signal: options.signal ? AbortSignal.any([options.signal, timeout]) : timeout,
    })
    if (!response.ok) {
      const error = await response.json().catch(() => null)
      throw new ApiError(response.status, typeof error?.detail === 'string' ? error.detail
        : response.status === 422 ? '输入格式不正确，请检查字数和必填项。' : '服务暂时不可用，请稍后重试。')
    }
    return response.status === 204 ? undefined : await response.json()
  } catch (error) {
    if (error instanceof TypeError || error instanceof DOMException) {
      throw new Error('连接中断或等待超时，请刷新记录确认操作结果。')
    }
    throw error
  }
}

export function api<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  return request(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body instanceof FormData || body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
    signal,
  })
}

export function deleteInterview(id: string): Promise<void> {
  return request('/interviews/' + encodeURIComponent(id), { method: 'DELETE' })
}
