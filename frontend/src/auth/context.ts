import { createContext, useContext } from 'react'
import type { RegisterData, User } from '../api/auth'

export type AuthValue = {
  user: User | null
  /** true, пока проверяется сохранённый токен при загрузке страницы */
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (data: RegisterData) => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<AuthValue | null>(null)

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>')
  return value
}
