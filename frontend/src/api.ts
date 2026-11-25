export async function api<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  try {
    const response = await fetch('/api' + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body instanceof FormData || body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
      signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15_000)]) : AbortSignal.timeout(15_000),
    })
    if (!response.ok) {
      const error = await response.json().catch(() => null)
      throw new Error(typeof error?.detail === 'string' ? error.detail : response.status === 422 ? '输入格式不正确，请检查字数和必填项。' : '服务暂时不可用，请稍后重试。')
    }
    return await response.json() as T
  } catch (error) {
    if (error instanceof TypeError || error instanceof DOMException) {
      throw new Error('连接中断或等待超时。材料和回答可能已保存，请刷新记录确认后再继续。')
    }
    throw error
  }
}
