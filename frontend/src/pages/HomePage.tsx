import { useCallback } from 'react'
import { Link } from 'react-router'
import { listTopics, type TopicSummary } from '../api/learning'
import { listVocabulary, problemWords, type ProblemWord, type UserWord } from '../api/vocabulary'
import { useAuth } from '../auth/context'
import { MentorPlan } from '../components/MentorPlan'
import { ProgressBar } from '../components/ProgressBar'
import { plural } from '../format'
import { useApi } from '../hooks/useApi'

type Dashboard = {
  topics: TopicSummary[]
  vocabulary: UserWord[]
  problems: ProblemWord[]
  due: number
}

export function HomePage() {
  const { user } = useAuth()
  const load = useCallback(async (): Promise<Dashboard> => {
    const [topics, vocabulary, problems] = await Promise.all([
      listTopics(),
      listVocabulary(),
      problemWords(),
    ])
    const now = Date.now()
    const due = vocabulary.filter((w) => new Date(w.next_review_at).getTime() <= now).length
    return { topics, vocabulary, problems, due }
  }, [])
  const { data, error, loading } = useApi(load)

  if (loading && !data) return <p className="muted">Загружаем курс…</p>
  if (error || !data) return <p className="alert">{error}</p>

  const { topics, vocabulary, problems, due } = data
  const solved = topics.reduce((sum, t) => sum + t.exercises_solved, 0)
  const total = topics.reduce((sum, t) => sum + t.exercises_total, 0)
  const next = topics.find((t) => t.exercises_solved < t.exercises_total)

  return (
    <div className="stack-lg">
      <section className="hello">
        <div>
          <h1>Привет, {user?.display_name}!</h1>
          <p className="muted">
            Уровень <span className="badge">{user?.cefr_level}</span> · решено {solved} из {total}{' '}
            {plural(total, 'упражнения', 'упражнений', 'упражнений')}
          </p>
        </div>
        {next && (
          <Link className="button-primary" to={`/topics/${next.id}`}>
            {next.exercises_solved === 0 ? 'Начать' : 'Продолжить'}: {next.title}
          </Link>
        )}
      </section>

      <MentorPlan />

      <section className="panel review-cta">
        <div>
          <h2>Повторение слов</h2>
          <p className="muted">
            {vocabulary.length === 0
              ? 'Словарь пока пуст. Добавьте слова из любой темы или на странице «Словарь».'
              : due > 0
                ? `Сегодня пора повторить ${due} ${plural(due, 'слово', 'слова', 'слов')} из ${vocabulary.length}.`
                : `На сегодня всё повторено. В словаре ${vocabulary.length} ${plural(vocabulary.length, 'слово', 'слова', 'слов')}.`}
          </p>
        </div>
        {due > 0 ? (
          <Link className="button-primary" to="/review">
            Повторить {due}
          </Link>
        ) : (
          <Link className="button-ghost" to="/vocabulary">
            Открыть словарь
          </Link>
        )}
      </section>

      {problems.length > 0 && (
        <section className="panel">
          <h2>Трудные слова</h2>
          <p className="muted">Эти слова вы чаще всего забывали за последний месяц.</p>
          <ul className="word-pills">
            {problems.map((p) => (
              <li key={p.word.id}>
                <strong>{p.word.text}</strong> — {p.word.translation}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="stack">
        <h2>Темы курса</h2>
        <ol className="topic-list">
          {topics.map((topic) => {
            const done =
              topic.exercises_total > 0 && topic.exercises_solved === topic.exercises_total
            return (
              <li key={topic.id}>
                <Link className="topic-row" to={`/topics/${topic.id}`}>
                  <span className="topic-pos">{topic.position}</span>
                  <span className="topic-main">
                    <span className="topic-title">{topic.title}</span>
                    <ProgressBar
                      value={topic.exercises_solved}
                      max={topic.exercises_total}
                      label={`Прогресс темы ${topic.title}`}
                    />
                  </span>
                  <span className="topic-meta">
                    <span className="badge">{topic.cefr_level}</span>
                    <span className={done ? 'tag tag-success' : 'muted'}>
                      {done ? 'Пройдено' : `${topic.exercises_solved}/${topic.exercises_total}`}
                    </span>
                  </span>
                </Link>
              </li>
            )
          })}
        </ol>
      </section>
    </div>
  )
}
