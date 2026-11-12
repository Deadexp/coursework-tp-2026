import { useCallback, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import {
  applyPlacement,
  getPlacement,
  startPlacement,
  submitPlacement,
  type IPlacementAttempt,
} from '../api/placement'
import { useAuth } from '../auth/context'
import { ProgressBar } from '../components/ProgressBar'
import { useApi } from '../hooks/useApi'
import '../profile.css'

const SKILLS = { grammar: 'Грамматика', vocabulary: 'Лексика', reading: 'Чтение' }

export function PlacementPage() {
  const [params] = useSearchParams()
  return <PlacementSession key={params.get('attempt') || 'new'} />
}

function restoreDraft(key: string): Record<string, number> {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) || '{}') as Record<string, unknown>
    return Object.fromEntries(
      Object.entries(value).filter(
        ([, choice]) =>
          typeof choice === 'number' && Number.isInteger(choice) && choice >= 0 && choice < 4,
      ),
    ) as Record<string, number>
  } catch {
    return {}
  }
}

function PlacementSession() {
  const [params, setParams] = useSearchParams()
  const attemptId = Number(params.get('attempt'))
  const validId = Number.isSafeInteger(attemptId) && attemptId > 0
  const { user, refreshUser } = useAuth()
  const load = useCallback(
    () => (validId ? getPlacement(attemptId) : Promise.resolve(null)),
    [attemptId, validId],
  )
  const { data: attempt, loading, error, setData } = useApi(load)
  const draftKey = `placement-draft:${user?.id}:${attemptId}`
  const [answers, setAnswers] = useState<Record<string, number>>(() => restoreDraft(draftKey))
  const [position, setPosition] = useState(0)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [message, setMessage] = useState('')

  async function start() {
    setBusy(true)
    setActionError('')
    try {
      const created = await startPlacement()
      setParams({ attempt: String(created.id) })
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Не удалось начать тест.')
    } finally {
      setBusy(false)
    }
  }

  function choose(questionId: string, optionIndex: number) {
    const next = { ...answers, [questionId]: optionIndex }
    setAnswers(next)
    try {
      sessionStorage.setItem(draftKey, JSON.stringify(next))
    } catch {
      /* Answers stay in memory. */
    }
  }

  async function submit(current: IPlacementAttempt) {
    const missing = current.questions.findIndex((question) => answers[question.id] === undefined)
    if (missing >= 0) {
      setPosition(missing)
      setActionError('Ответьте на все вопросы перед завершением теста.')
      return
    }
    setBusy(true)
    setActionError('')
    try {
      setData(
        await submitPlacement(
          current.id,
          current.questions.map((question) => ({
            question_id: question.id,
            option_index: answers[question.id],
          })),
        ),
      )
      try {
        sessionStorage.removeItem(draftKey)
      } catch {
        /* The server has saved the result. */
      }
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : 'Не удалось отправить ответы. Попробуйте ещё раз.',
      )
    } finally {
      setBusy(false)
    }
  }

  async function apply(current: IPlacementAttempt) {
    setBusy(true)
    setActionError('')
    try {
      setData(await applyPlacement(current.id))
      await refreshUser()
      setMessage('Уровень сохранён в профиле сайта и Telegram.')
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Не удалось сохранить уровень.')
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <p className="muted">Загружаем тест…</p>
  if (error)
    return (
      <div className="stack">
        <p className="alert" role="alert">
          {error}
        </p>
        <Link to="/profile">Вернуться в профиль</Link>
      </div>
    )

  const result = attempt?.result
  const question = attempt?.questions[position]
  const answered = attempt
    ? attempt.questions.filter((item) => answers[item.id] !== undefined).length
    : 0

  return (
    <div className="placement-page stack-lg">
      <Link className="back-link" to="/profile">
        ← Личный кабинет
      </Link>
      <header className="stack">
        <p className="eyebrow">Английский · A1–B1</p>
        <h1>{result ? 'Ваш результат' : 'Тест на определение уровня'}</h1>
      </header>
      {actionError && (
        <p className="alert" role="alert">
          {actionError}
        </p>
      )}
      {message && <p role="status">{message}</p>}

      {!attempt && (
        <section className="panel stack">
          <h2>С какого уровня начать?</h2>
          <p>
            Ответьте на 24 вопроса: грамматика, слова и небольшие тексты. Вы сможете возвращаться к
            предыдущим вопросам. Правильные ответы появятся после завершения.
          </p>
          <ul>
            <li>Выделите примерно 10–15 минут и отвечайте без переводчика.</li>
            <li>Если не знаете ответ, выберите наиболее вероятный вариант.</li>
            <li>
              Черновик ответов сохраняется в этой вкладке браузера. Итоговый результат хранится в
              аккаунте.
            </li>
          </ul>
          <p className="muted">
            Это учебная диагностика для выбора материалов A1–B1, а не сертифицированный экзамен
            CEFR. Тест не оценивает произношение, говорение и аудирование. Результат выше B1 не
            определяется.
          </p>
          <div>
            <button className="button-primary" disabled={busy} onClick={() => void start()}>
              {busy ? 'Готовим вопросы…' : 'Начать тест'}
            </button>
          </div>
        </section>
      )}

      {attempt && !result && question && (
        <>
          <div className="stack">
            <ProgressBar value={answered} max={attempt.total} label="Отвеченные вопросы" />
            <p className="muted">
              Отвечено {answered} из {attempt.total}. Вопрос {position + 1} ·{' '}
              {SKILLS[question.skill]}
            </p>
          </div>
          <section className="panel stack" aria-labelledby="placement-question">
            {question.passage && (
              <blockquote className="placement-passage">{question.passage}</blockquote>
            )}
            <fieldset className="placement-options" disabled={busy}>
              <legend id="placement-question">{question.prompt}</legend>
              {question.options.map((option, index) => (
                <label
                  className={`placement-option ${answers[question.id] === index ? 'selected' : ''}`}
                  key={`${question.id}:${index}`}
                >
                  <input
                    type="radio"
                    name={`question-${question.id}`}
                    checked={answers[question.id] === index}
                    onChange={() => choose(question.id, index)}
                  />
                  <span>{option}</span>
                </label>
              ))}
            </fieldset>
            <div className="placement-navigation">
              <button
                className="button-ghost"
                disabled={busy || position === 0}
                onClick={() => setPosition((value) => value - 1)}
              >
                Назад
              </button>
              {position < attempt.questions.length - 1 ? (
                <button
                  className="button-primary"
                  disabled={busy}
                  onClick={() => setPosition((value) => value + 1)}
                >
                  Следующий вопрос
                </button>
              ) : (
                <button
                  className="button-primary"
                  disabled={busy}
                  onClick={() => void submit(attempt)}
                >
                  {busy ? 'Проверяем…' : 'Завершить тест'}
                </button>
              )}
            </div>
          </section>
          <nav className="placement-question-nav" aria-label="Перейти к вопросу">
            {attempt.questions.map((item, index) => (
              <button
                className={`placement-number ${answers[item.id] !== undefined ? 'answered' : ''}`}
                key={item.id}
                aria-label={`Вопрос ${index + 1}${answers[item.id] !== undefined ? ', отвечен' : ''}`}
                aria-current={index === position ? 'step' : undefined}
                disabled={busy}
                onClick={() => setPosition(index)}
              >
                {index + 1}
              </button>
            ))}
          </nav>
        </>
      )}

      {attempt && result && (
        <>
          <section className="panel stack">
            <p className="placement-level">{result.recommended_level}</p>
            <h2>Рекомендуемый стартовый уровень</h2>
            <p>
              Правильных ответов:{' '}
              <strong>
                {result.correct} из {result.total}
              </strong>
              .
            </p>
            <p>{result.summary}</p>
            <div className="profile-stats placement-scores">
              {result.scores.map((score) => (
                <div className="panel profile-stat" key={score.level}>
                  <span>Блок {score.level}</span>
                  <strong>
                    {score.correct}/{score.total}
                  </strong>
                </div>
              ))}
            </div>
            <p className="muted">{result.limitations}</p>
            <div className="row">
              <button
                className="button-primary"
                disabled={busy || Boolean(attempt.applied_at)}
                onClick={() => void apply(attempt)}
              >
                {attempt.applied_at
                  ? 'Уровень уже сохранён'
                  : busy
                    ? 'Сохраняем…'
                    : `Сохранить уровень ${result.recommended_level}`}
              </button>
              <Link className="button-ghost" to="/">
                Открыть курс
              </Link>
            </div>
          </section>
          <details className="panel placement-explanations">
            <summary>Разбор всех ответов</summary>
            <ol className="stack">
              {result.answers.map((answer) => {
                const item = attempt.questions.find(
                  (question) => question.id === answer.question_id,
                )
                return (
                  <li key={answer.question_id} className="placement-explanation">
                    <strong>{item?.prompt}</strong>
                    <p className={answer.is_correct ? 'placement-correct' : 'placement-incorrect'}>
                      {answer.is_correct ? 'Верно' : 'Ошибка'} · Ваш ответ:{' '}
                      {item?.options[answer.option_index]}
                    </p>
                    {!answer.is_correct && (
                      <p>Правильный ответ: {item?.options[answer.correct_option_index]}</p>
                    )}
                    <p className="muted">{answer.explanation}</p>
                  </li>
                )
              })}
            </ol>
          </details>
          <div>
            <button className="button-ghost" disabled={busy} onClick={() => void start()}>
              Пройти новый тест
            </button>
          </div>
        </>
      )}
    </div>
  )
}
