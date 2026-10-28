import { useCallback, useState } from 'react'
import { createTelegramLink, telegramStatus, type TelegramLink } from '../api/telegram'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/context'
import { useApi } from '../hooks/useApi'

export function TelegramConnection() {
  const { data, error, loading, reload } = useApi(useCallback(() => telegramStatus(), []))
  const { logout } = useAuth()
  const [link, setLink] = useState<TelegramLink | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  async function connect() {
    setBusy(true)
    setMessage('')
    setLink(null)
    try {
      setLink(await createTelegramLink())
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) logout()
      setMessage(
        err instanceof ApiError && err.status === 409
          ? 'Telegram уже подключён. Обновите статус.'
          : 'Не удалось получить ссылку. Проверьте связь и настройки Telegram на сервере.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel stack" aria-labelledby="telegram-title">
      <h2 id="telegram-title">Telegram</h2>
      {data?.linked ? (
        <p role="status">Telegram подключён. На сайте и в боте один личный словарь.</p>
      ) : (
        <>
          <p className="muted">
            Подключите бота, чтобы добавлять и повторять те же слова в Telegram. После изменений в
            боте обновите список слов на сайте.
          </p>
          <button className="button-primary" disabled={busy || loading || !data} onClick={connect}>
            {busy ? 'Готовим ссылку…' : 'Подключить Telegram'}
          </button>
          {link && (
            <div className="stack">
              <a className="button-primary" href={link.url} target="_blank" rel="noreferrer">
                Открыть бота в Telegram
              </a>
              <p className="muted">
                Нажмите «Запустить» в боте. Ссылка одноразовая, действует 10 минут, до{' '}
                {new Date(link.expires_at).toLocaleTimeString('ru-RU')}. Не передавайте её другим.
                Новая ссылка отменяет предыдущую.
              </p>
            </div>
          )}
        </>
      )}
      <button className="button-ghost" disabled={loading} onClick={() => void reload()}>
        Обновить статус Telegram
      </button>
      {(error || message) && <p role="alert">{message || error}</p>}
    </section>
  )
}
