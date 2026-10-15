import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router'
import { getTopic } from '../api/learning'
import { addTopicWords } from '../api/vocabulary'
import { ExerciseCard } from '../components/exercises/ExerciseCard'
import { Markdown } from '../components/Markdown'
import { ProgressBar } from '../components/ProgressBar'
import { plural } from '../format'
import { useApi } from '../hooks/useApi'

export function TopicPage() {
  const topicId = Number(useParams().topicId)
  const load = useCallback(() => getTopic(topicId), [topicId])
  const { data: topic, error, loading, setData } = useApi(load)
  const [wordsMessage, setWordsMessage] = useState('')

  if (loading && !topic) return <p className="muted">Загружаем тему…</p>
  if (error || !topic) return <p className="alert">{error || 'Тема не найдена'}</p>

  const solved = topic.exercises.filter((e) => e.solved).length

  function markSolved(id: number) {
    if (!topic) return
    setData({
      ...topic,
      exercises: topic.exercises.map((e) => (e.id === id ? { ...e, solved: true } : e)),
    })
  }

  async function handleAddWords() {
    try {
      const { added } = await addTopicWords(topicId)
      setWordsMessage(
        added === 0
          ? 'Все слова темы уже в вашем словаре.'
          : `Добавлено ${added} ${plural(added, 'слово', 'слова', 'слов')} — они уже ждут в повторении.`,
      )
    } catch (err) {
      setWordsMessage(err instanceof Error ? err.message : 'Не удалось добавить слова')
    }
  }

  return (
    <div className="stack-lg">
      <Link to="/" className="back-link">
        ← Все темы
      </Link>

      <header className="stack">
        <p className="eyebrow">
          Тема · <span className="badge">{topic.cefr_level}</span>
        </p>
        <h1>{topic.title}</h1>
        <div className="topic-progress">
          <ProgressBar value={solved} max={topic.exercises.length} label="Прогресс темы" />
          <span className="muted">
            Решено {solved} из {topic.exercises.length}
          </span>
        </div>
      </header>

      <section className="panel">
        <Markdown>{topic.theory}</Markdown>
      </section>

      <section className="stack">
        <h2>Упражнения</h2>
        {topic.exercises.map((exercise, index) => (
          <ExerciseCard
            key={exercise.id}
            exercise={exercise}
            number={index + 1}
            onSolved={markSolved}
          />
        ))}
      </section>

      <section className="panel review-cta">
        <div>
          <h2>Слова темы</h2>
          <p className="muted">
            {wordsMessage || 'Добавьте слова этой темы в свой словарь, чтобы повторять их.'}
          </p>
        </div>
        <button className="button-ghost" onClick={handleAddWords}>
          Добавить в словарь
        </button>
      </section>
    </div>
  )
}
