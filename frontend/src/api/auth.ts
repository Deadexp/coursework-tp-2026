import { request } from './client'

export type User = {
  id: number
  email: string
  display_name: string
  cefr_level: string
  created_at: string
}

export type RegisterData = { email: string; password: string; display_name: string }

export function register(data: RegisterData) {
  return request<User>('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function login(email: string, password: string) {
  // OAuth2-форма: email передаётся в поле username.
  return request<{ access_token: string }>('/auth/login', {
    method: 'POST',
    body: new URLSearchParams({ username: email, password }),
  })
}

export function fetchMe() {
  return request<User>('/users/me')
}
