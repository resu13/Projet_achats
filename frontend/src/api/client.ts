let csrfToken: string | null = null

function getCsrfCookie(): string | null {
  const cookie = document.cookie.split('; ').find((part) => part.startsWith('csrftoken='))
  return cookie ? decodeURIComponent(cookie.slice('csrftoken='.length)) : null
}

async function getCsrfToken(baseUrl: string): Promise<string> {
  const cookieToken = getCsrfCookie()
  if (cookieToken) return cookieToken
  if (csrfToken) return csrfToken
  const response = await fetch(`${baseUrl}/api/auth/login`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Impossible d’obtenir le jeton CSRF (erreur ${response.status}).`)
  const body = await response.json() as { csrfToken?: string }
  if (!body.csrfToken) throw new Error('Le serveur n’a pas fourni de jeton CSRF.')
  csrfToken = body.csrfToken
  return csrfToken
}

function getErrorMessage(body: unknown, fallback: string): string {
  if (typeof body === 'string') return body
  if (Array.isArray(body)) {
    for (const item of body) {
      const message = getErrorMessage(item, '')
      if (message) return message
    }
    return fallback
  }
  if (typeof body !== 'object' || body === null) return fallback
  const data = body as Record<string, unknown>
  if (typeof data.message === 'string') return data.message
  if (typeof data.detail === 'string') return data.detail
  for (const value of Object.values(data)) {
    const message = getErrorMessage(value, '')
    if (message) return message
  }
  return fallback
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const baseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''
  const method = (init?.method ?? 'GET').toUpperCase()
  const headers = new Headers(init?.headers)
  if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    headers.set('X-CSRFToken', await getCsrfToken(baseUrl))
  }
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  })
  if (!response.ok) {
    const fallback = `Erreur ${response.status}`
    let message = fallback
    try {
      message = getErrorMessage(await response.json(), fallback)
    } catch (error) {
      if (!(error instanceof SyntaxError)) throw error
    }
    if (message === fallback && response.status === 403) message = 'Accès refusé : vous ne disposez pas des droits nécessaires.'
    if (message === fallback && response.status === 401) message = 'Votre session a expiré. Veuillez vous reconnecter.'
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export const jsonRequest = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  ...(body === undefined ? {} : { body: JSON.stringify(body) }),
})

export async function downloadFile(path: string, filename: string): Promise<void> {
  const baseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''
  const response = await fetch(`${baseUrl}${path}`, { credentials: 'include' })
  if (!response.ok) {
    const fallback = `Erreur ${response.status}`
    let message = fallback
    try {
      message = getErrorMessage(await response.json(), fallback)
    } catch (error) {
      if (!(error instanceof SyntaxError)) throw error
    }
    if (message === fallback && response.status === 403) message = 'Accès refusé : vous ne disposez pas des droits nécessaires.'
    if (message === fallback && response.status === 401) message = 'Votre session a expiré. Veuillez vous reconnecter.'
    throw new Error(message)
  }
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
