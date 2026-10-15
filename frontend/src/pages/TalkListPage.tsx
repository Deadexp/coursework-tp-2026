import { useCallback, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import {
  listDialogs,
  listScenarios,
  startDialog,
  type DialogSummary,
  type Scenario,
} from '../api/ai'
import { useApi } from '../hooks/useApi'

type Data = { scenarios: Scenario[]; dialogs: DialogSummary[] }

const dateFormat = new Intl.DateTimeFormat('ru', {
  day: 'numeric',
  month: 'long',
  hour: '2-digit',
  minute: '2-digit',
})

export function TalkListPage() {
  const navigate = useNavigate()
  const load = useCallback(async (): Promise<Data> => {
    const [scenarios, dialogs] = await Promise.all([listScenarios(), listDialogs()])
    return { scenarios, dialogs }
  }, [])
  const { data, error, loading } = useApi(load)
  const [starting, setStarting] = useState<string | null>(null)
  const [startError, setStartError] = useState('')

  async function handleStart(code: string) {
    setStarting(code)
    setStartError('')
    try {
      const dialog = await startDialog(code)
      navigate(`/talk/${dialog.id}`)
    } catch (err) {
      setStartError(err instanceof Error ? err.message : 'Не удалось начать разговор')
      setStarting(null)
    }
  }

  if (loading && !data) return <p className="muted">Загружаем…</p>
  if (error || !data) return <p className="alert">{error}</p>

  return (
    <div className="stack-lg">
      <header className="stack">
        <h1>Разговор с носителем языка</h1>
        <p className="muted">
          Emma — виртуальная собеседница из Лондона. Она говорит на вашем уровне, а ошибки в ваших
          сообщениях отмечаются отдельно и учитываются в плане занятий.
        </p>
      </header>

      {startError && (
        <p className="alert" role="alert">
          {startError}
        </p>
      )}

      <section className="scenario-grid" aria-label="Сценарии">
        {data.scenarios.map((s) => (
          <button
            key={s.code}
            className="scenario"
            onClick={() => handleStart(s.code)}
            disabled={starting !== null}
          >
            <strong>{s.title}</strong>
            <span className="muted">
              {starting === s.code ? 'Emma подключается…' : s.description}
            </span>
          </button>
        ))}
      </section>

      {data.dialogs.length > 0 && (
        <section className="stack">
          <h2>Ваши разговоры</h2>
          <ul className="dialog-list">
            {data.dialogs.map((d) => (
              <li key={d.id}>
                <Link to={`/talk/${d.id}`} className="topic-row dialog-row">
                  <span className="topic-title">{d.title}</span>
                  <span className="muted">{dateFormat.format(new Date(d.started_at))}</span>
                  <span className={d.ended_at ? 'tag tag-success' : 'muted'}>
                    {d.ended_at ? 'Завершён' : `${d.messages} сообщ.`}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
