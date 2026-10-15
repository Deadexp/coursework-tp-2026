import { NavLink, Outlet } from 'react-router'
import { useAuth } from '../auth/context'
import { APP_NAME } from '../config'

const LINKS = [
  { to: '/', label: 'Курс', end: true },
  { to: '/vocabulary', label: 'Словарь', end: false },
  { to: '/review', label: 'Повторение', end: false },
]

export function AppLayout() {
  const { user, logout } = useAuth()

  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand">
          {APP_NAME}
        </NavLink>
        <nav className="topnav" aria-label="Основное меню">
          {LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end}>
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="topbar-user">
          <span className="topbar-name">{user?.display_name}</span>
          <button className="button-ghost" onClick={logout}>
            Выйти
          </button>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </div>
  )
}
