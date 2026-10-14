import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import * as api from '../api/auth'
import { tokenStorage } from '../api/client'
import { AuthContext } from './context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<api.User | null>(null)
  const [loading, setLoading] = useState(() => tokenStorage.get() !== null)

  useEffect(() => {
    if (!tokenStorage.get()) return
    api
      .fetchMe()
      .then(setUser)
      .catch(() => tokenStorage.clear()) // токен просрочен или битый — просто выходим
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await api.login(email, password)
    tokenStorage.set(access_token)
    setUser(await api.fetchMe())
  }, [])

  const register = useCallback(
    async (data: api.RegisterData) => {
      await api.register(data)
      await login(data.email, data.password)
    },
    [login],
  )

  const logout = useCallback(() => {
    tokenStorage.clear()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
