import { useAuth } from '../auth/context'
import { APP_NAME } from '../config'

export function HomePage() {
  const { user, logout } = useAuth()
  if (!user) return null

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">{APP_NAME}</span>
        <div className="topbar-user">
          <span>{user.display_name}</span>
          <button className="button-ghost" onClick={logout}>
            Выйти
          </button>
        </div>
      </header>
      <main className="home">
        <h1>Привет, {user.display_name}!</h1>
        <p className="muted">
          Ваш уровень: <span className="badge">{user.cefr_level}</span>
        </p>
        <section className="placeholder">
          Здесь появятся ваш план занятий, прогресс и рекомендации.
        </section>
      </main>
    </div>
  )
}
