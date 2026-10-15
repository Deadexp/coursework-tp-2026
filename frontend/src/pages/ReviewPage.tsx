import { useCallback, useState } from 'react'
import { Link } from 'react-router'
import { dueCards, recordReview } from '../api/vocabulary'
import { ProgressBar } from '../components/ProgressBar'
import { plural } from '../format'
import { useApi } from '../hooks/useApi'

// Оценки SM-2 для кнопок — как в docs/api-vocabulary.md.
const RATINGS = [
  { quality: 3, label: 'С трудом' },
  { quality: 4, label: 'Хорошо' },
  { quality: 5, label: 'Легко' },
]

export function ReviewPage() {
  const { data: cards, error, loading, reload } = useApi(useCallback(() => dueCards(20), []))
  const [index, setIndex] = useState(0)
  const [chosen, setChosen] = useState<string | null>(null)
  const [correctCount, setCorrectCount] = useState(0)
  const [saving, setSaving] = useState(false)

  if (loading && !cards) return <p className="muted">Готовим карточки…</p>
  if (error || !cards) return <p className="alert">{error}</p>

  if (cards.length === 0) {
    return (
      <div className="panel review-done stack">
        <h1>На сегодня всё</h1>
        <p className="muted">
          Слов для повторения нет. Новые слова можно добавить в словаре или на странице темы.
        </p>
        <Link className="button-primary" to="/vocabulary">
          Открыть словарь
        </Link>
      </div>
    )
  }

  if (index >= cards.length) {
    return (
      <div className="panel review-done stack">
        <h1>Готово!</h1>
        <p>
          Повторено {cards.length} {plural(cards.length, 'слово', 'слова', 'слов')}, сразу вспомнили{' '}
          {correctCount}.
        </p>
        <p className="muted">
          Слова, которые не удалось вспомнить, вернутся завтра. Лёгкие — через несколько дней.
        </p>
        <div className="row">
          <button
            className="button-primary"
            onClick={() => {
              setIndex(0)
              setCorrectCount(0)
              void reload()
            }}
          >
            Проверить ещё
          </button>
          <Link className="button-ghost" to="/">
            На главную
          </Link>
        </div>
      </div>
    )
  }

  const card = cards[index]
  const isCorrect = chosen === card.word.translation

  async function rate(quality: number) {
    setSaving(true)
    try {
      await recordReview(card.word.id, quality)
      if (quality >= 3) setCorrectCount((n) => n + 1)
      setChosen(null)
      setIndex((i) => i + 1)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="review stack-lg">
      <div className="review-progress">
        <ProgressBar value={index} max={cards.length} label="Прогресс повторения" />
        <span className="muted nowrap">
          {index + 1} из {cards.length}
        </span>
      </div>

      <section className="panel flashcard" aria-live="polite">
        <p className="flashcard-word">{card.word.text}</p>
        {card.word.transcription && <p className="muted">{card.word.transcription}</p>}

        <div className="choices choices-grid">
          {card.choices.map((choice) => {
            const right = chosen !== null && choice === card.word.translation
            const wrong = chosen === choice && !isCorrect
            return (
              <button
                key={choice}
                className={`choice ${right ? 'choice-right' : ''} ${wrong ? 'choice-wrong' : ''}`}
                disabled={chosen !== null}
                onClick={() => setChosen(choice)}
              >
                {choice}
              </button>
            )
          })}
        </div>

        {chosen !== null && (
          <div className="stack">
            {card.word.example && <p className="example">«{card.word.example}»</p>}
            {isCorrect ? (
              <>
                <p className="feedback-title">Верно! Насколько легко вспомнилось?</p>
                <div className="row">
                  {RATINGS.map((r) => (
                    <button
                      key={r.quality}
                      className="button-ghost"
                      disabled={saving}
                      onClick={() => rate(r.quality)}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <>
                <p className="feedback-title">
                  Правильно: {card.word.translation}. Слово вернётся завтра.
                </p>
                <button className="button-primary" disabled={saving} onClick={() => rate(1)}>
                  Дальше
                </button>
              </>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
