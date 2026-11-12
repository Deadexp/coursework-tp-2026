import { useCallback, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { getReminderSettings, saveReminderSettings, type IReminderSettings } from '../api/profile'
import { useApi } from '../hooks/useApi'

const ZONES = [
  'Europe/Moscow',
  'Europe/Kaliningrad',
  'Europe/Samara',
  'Asia/Yekaterinburg',
  'Asia/Novosibirsk',
  'Asia/Irkutsk',
  'Asia/Vladivostok',
  'Europe/London',
  'Europe/Berlin',
  'America/New_York',
  'Asia/Tokyo',
  'UTC',
]

export function ReminderSettings() {
  const { data, error, loading, setData } = useApi(useCallback(() => getReminderSettings(), []))
  const [draft, setDraft] = useState<Partial<IReminderSettings>>({})
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [saveError, setSaveError] = useState('')
  const settings: IReminderSettings = {
    enabled: draft.enabled ?? data?.enabled ?? false,
    time: draft.time ?? data?.time ?? '19:00',
    timezone: draft.timezone ?? data?.timezone ?? 'Europe/Moscow',
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setMessage('')
    setSaveError('')
    try {
      setData(await saveReminderSettings(settings))
      setDraft({})
      setMessage(
        settings.enabled ? 'Напоминания включены. Настройки сохранены.' : 'Напоминания выключены.',
      )
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Не удалось сохранить настройки.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="panel stack" aria-labelledby="reminders-title">
      <div>
        <p className="eyebrow">Telegram</p>
        <h2 id="reminders-title">Напоминания о занятиях</h2>
      </div>
      <p className="muted">
        Одно напоминание в выбранное время. Сначала{' '}
        <Link to="/vocabulary">подключите Telegram</Link> к аккаунту.
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      <form className="stack" onSubmit={submit}>
        <label className="reminder-toggle">
          <input
            type="checkbox"
            checked={settings.enabled}
            disabled={loading || saving || !data}
            onChange={(event) => setDraft((prev) => ({ ...prev, enabled: event.target.checked }))}
          />
          Присылать напоминания в Telegram
        </label>
        <div className="reminder-fields">
          <label className="field">
            <span>Время</span>
            <input
              className="answer-input"
              type="time"
              required
              value={settings.time}
              disabled={loading || saving || !data}
              onChange={(event) => setDraft((prev) => ({ ...prev, time: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>Часовой пояс</span>
            <input
              className="answer-input"
              list="reminder-timezones"
              required
              value={settings.timezone}
              disabled={loading || saving || !data}
              onChange={(event) => setDraft((prev) => ({ ...prev, timezone: event.target.value }))}
            />
            <datalist id="reminder-timezones">
              {ZONES.map((zone) => (
                <option key={zone} value={zone} />
              ))}
            </datalist>
          </label>
        </div>
        <p className="muted">
          Europe/Moscow — московское время. Пока проект работает локально, для доставки нужны
          включённый компьютер, Docker и интернет.
        </p>
        {saveError && (
          <p className="alert" role="alert">
            {saveError}
          </p>
        )}
        {message && <p role="status">{message}</p>}
        <div>
          <button className="button-primary" disabled={loading || saving || !data}>
            {saving ? 'Сохраняем…' : 'Сохранить напоминания'}
          </button>
        </div>
      </form>
    </section>
  )
}
