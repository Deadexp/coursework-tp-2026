const BASE_URL = '/api'
const TOKEN_KEY = 'access_token'

export const tokenStorage = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

/** Ошибка API: HTTP-статус, общее сообщение и ошибки по полям формы (из 422 FastAPI). */
export class ApiError extends Error {
  status: number
  fieldErrors: Record<string, string>

  constructor(status: number, message: string, fieldErrors: Record<string, string> = {}) {
    super(message)
    this.status = status
    this.fieldErrors = fieldErrors
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = tokenStorage.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let response: Response
  try {
    response = await fetch(BASE_URL + path, { ...init, headers })
  } catch {
    throw new ApiError(0, 'Нет связи с сервером. Проверьте, что backend запущен.')
  }
  if (!response.ok) throw await toApiError(response)
  if (response.status === 204) return null as T
  return (await response.json()) as T
}

type ValidationIssue = { loc?: (string | number)[]; msg: string }

async function toApiError(response: Response): Promise<ApiError> {
  const body: { detail?: unknown } | null = await response.json().catch(() => null)
  const detail = body?.detail

  if (Array.isArray(detail)) {
    const fieldErrors: Record<string, string> = {}
    for (const issue of detail as ValidationIssue[]) {
      const field = issue.loc?.at(-1)
      if (typeof field === 'string') fieldErrors[field] = issue.msg
    }
    return new ApiError(response.status, 'Проверьте введённые данные', fieldErrors)
  }
  return new ApiError(response.status, typeof detail === 'string' ? detail : response.statusText)
}
