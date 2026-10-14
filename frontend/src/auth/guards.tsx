import { Navigate, Outlet, useLocation } from 'react-router'
import { useAuth } from './context'

/** Пускает только вошедших; остальных отправляет на вход и запоминает, куда они шли. */
export function RequireAuth() {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <div className="page-loading" aria-label="Загрузка" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <Outlet />
}

/** Страницы входа/регистрации не нужны тому, кто уже вошёл. */
export function GuestOnly() {
  const { user, loading } = useAuth()

  if (loading) return <div className="page-loading" aria-label="Загрузка" />
  if (user) return <Navigate to="/" replace />
  return <Outlet />
}
