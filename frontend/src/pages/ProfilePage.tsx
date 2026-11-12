import { useCallback } from 'react'
import { Link } from 'react-router'
import { listTopics } from '../api/learning'
import { placementHistory } from '../api/placement'
import { getProgress } from '../api/profile'
import { useAuth } from '../auth/context'
import { ProgressBar } from '../components/ProgressBar'
import { ReminderSettings } from '../components/ReminderSettings'
import { useApi } from '../hooks/useApi'
import '../profile.css'

const percent = (correct: number, total: number) =>
  total ? `${Math.round((correct / total) * 100)}%` : '—'

export function ProfilePage() {
  const { user } = useAuth()
  const load = useCallback(async () => {
    const [progress, topics, history] = await Promise.all([
      getProgress(),
      listTopics(),
      placementHistory(),
    ])
    return { progress, topics, history }
  }, [])
  const { data, error, loading, reload } = useApi(load)

  if (loading && !data) return <p className="muted">Загружаем профиль…</p>
  if (!data)
    return (
      <p className="alert" role="alert">
        {error || 'Не удалось загрузить профиль.'}
      </p>
    )

  const { progress, topics, history } = data
  const solved = topics.reduce((total, topic) => total + topic.exercises_solved, 0)
  const exercises = topics.reduce((total, topic) => total + topic.exercises_total, 0)
  const finished = topics.filter(
    (topic) => topic.exercises_total > 0 && topic.exercises_solved === topic.exercises_total,
  ).length

  return (
    <div className="stack-lg">
      <header className="hello">
        <div>
          <p className="eyebrow">Личный кабинет</p>
          <h1>{user?.display_name}</h1>
          <p className="muted">
            {user?.email} · Уровень <span className="badge">{progress.level}</span>
          </p>
        </div>
        <button className="button-ghost" disabled={loading} onClick={() => void reload()}>
          {loading ? 'Обновляем…' : 'Обновить статистику'}
        </button>
      </header>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      <section className="profile-stats" aria-label="Статистика обучения">
        {[
          ['Слов в словаре', progress.words],
          ['Пора повторить', progress.due],
          ['Повторений карточек', progress.reviews],
          ['Тем пройдено', `${finished} / ${topics.length}`],
          ['Точность в грамматике', percent(progress.grammar_correct, progress.grammar_attempted)],
          ['Точность в словарных заданиях', percent(progress.correct, progress.attempted)],
        ].map(([label, value]) => (
          <article className="panel profile-stat" key={label}>
            <span className="muted">{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </section>

      <section className="panel stack">
        <h2>Прогресс курса</h2>
        <p>
          Решено {solved} из {exercises} упражнений.
        </p>
        <ProgressBar value={solved} max={exercises} label="Общий прогресс курса" />
        <p className="muted">
          Завершено словарных тестов: {progress.quizzes_completed}. Практик дня:{' '}
          {progress.daily_completed}. Статистика объединяет занятия на сайте и в подключённом боте;
          точность считается по всем сохранённым ответам.
        </p>
        <div className="row">
          <Link className="button-primary" to="/">
            Продолжить курс
          </Link>
          <Link className="button-ghost" to="/review">
            Повторить слова
          </Link>
        </div>
      </section>

      <section className="panel stack">
        <div className="review-cta">
          <div>
            <p className="eyebrow">Стартовый уровень</p>
            <h2>Тест по английскому</h2>
          </div>
          <Link className="button-primary" to="/placement">
            Пройти тест
          </Link>
        </div>
        <p className="muted">
          24 вопроса по грамматике, лексике и чтению. Результат поможет выбрать материал A1–B1.
          Уровень профиля изменится только после вашего подтверждения.
        </p>
        <h3>История тестирования</h3>
        {history.length === 0 ? (
          <p className="muted">Вы ещё не проходили тест.</p>
        ) : (
          <ul className="placement-history">
            {history.slice(0, 8).map((attempt) => (
              <li key={attempt.id}>
                <div>
                  <strong>
                    {attempt.result
                      ? `${attempt.result.recommended_level} · ${attempt.result.correct}/${attempt.total}`
                      : 'Тест не завершён'}
                  </strong>
                  <span className="muted">
                    {new Date(attempt.started_at).toLocaleString('ru-RU')}
                    {attempt.applied_at ? ' · Результат применён' : ''}
                  </span>
                </div>
                <Link to={`/placement?attempt=${attempt.id}`}>
                  {attempt.result ? 'Результат' : 'Продолжить'}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <ReminderSettings />
    </div>
  )
}
