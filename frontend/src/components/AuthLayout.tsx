import type { ReactNode } from 'react'
import { APP_NAME } from '../config'

const FEATURES = [
  ['Адаптивные уроки', 'Система замечает ваши ошибки и подбирает, что повторить'],
  ['Telegram-бот', 'Повторяйте слова из словаря за пять минут в день'],
  ['Собеседник-носитель', 'Практикуйте живой диалог с ИИ на своём уровне'],
] as const

export function AuthLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="auth">
      <aside className="auth-promo">
        <p className="brand">{APP_NAME}</p>
        <h2 className="auth-promo-title">Английский, который подстраивается под вас</h2>
        <ul className="feature-list">
          {FEATURES.map(([name, text]) => (
            <li key={name}>
              <strong>{name}</strong>
              <span>{text}</span>
            </li>
          ))}
        </ul>
      </aside>
      <main className="auth-main">
        <div className="auth-card">
          <p className="brand brand-mobile">{APP_NAME}</p>
          <h1>{title}</h1>
          {children}
        </div>
      </main>
    </div>
  )
}
