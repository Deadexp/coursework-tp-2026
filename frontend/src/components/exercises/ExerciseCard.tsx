import { useState, type FormEvent } from 'react'
import { submitAttempt, type AttemptResult, type Exercise } from '../../api/learning'

const TASK: Record<Exercise['type'], string> = {
  multiple_choice: 'Выберите вариант',
  fill_gap: 'Вставьте пропущенное',
  translate: 'Переведите на английский',
  word_order: 'Соберите предложение',
}

type Props = { exercise: Exercise; number: number; onSolved: (id: number) => void }

export function ExerciseCard({ exercise, number, onSolved }: Props) {
  const [answer, setAnswer] = useState('')
  const [placed, setPlaced] = useState<number[]>([]) // индексы слов для word_order
  const [chosen, setChosen] = useState<string | null>(null)
  const [result, setResult] = useState<AttemptResult | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const words = exercise.words ?? []

  async function check(value: string) {
    if (!value.trim()) return
    setSubmitting(true)
    setError('')
    try {
      const res = await submitAttempt(exercise.id, value)
      setResult(res)
      if (res.is_correct) onSolved(exercise.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось проверить ответ')
    } finally {
      setSubmitting(false)
    }
  }

  function reset() {
    setAnswer('')
    setPlaced([])
    setChosen(null)
    setResult(null)
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const value = exercise.type === 'word_order' ? placed.map((i) => words[i]).join(' ') : answer
    void check(value)
  }

  const answered = result !== null
  const state = !answered ? '' : result.is_correct ? 'is-correct' : 'is-wrong'

  return (
    <article className={`exercise ${state}`} aria-labelledby={`ex-${exercise.id}`}>
      <div className="exercise-head">
        <span className="exercise-task">
          {number}. {TASK[exercise.type]}
        </span>
        {exercise.solved && <span className="tag tag-success">Решено</span>}
      </div>
      <p className="exercise-prompt" id={`ex-${exercise.id}`}>
        {exercise.prompt}
      </p>

      {exercise.type === 'multiple_choice' && (
        <div className="choices">
          {(exercise.options ?? []).map((option) => {
            const isRight = answered && result.correct_answers.includes(option)
            const isChosenWrong = answered && chosen === option && !result.is_correct
            return (
              <button
                key={option}
                type="button"
                className={`choice ${isRight ? 'choice-right' : ''} ${isChosenWrong ? 'choice-wrong' : ''}`}
                disabled={answered || submitting}
                onClick={() => {
                  setChosen(option)
                  void check(option)
                }}
              >
                {option}
              </button>
            )
          })}
        </div>
      )}

      {(exercise.type === 'fill_gap' || exercise.type === 'translate') && (
        <form className="answer-row" onSubmit={handleSubmit}>
          <input
            className="answer-input"
            aria-label="Ваш ответ"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            disabled={answered}
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
            placeholder={exercise.type === 'translate' ? 'Перевод' : 'Пропущенное слово'}
          />
          {!answered && (
            <button className="button-primary" disabled={submitting || !answer.trim()}>
              Проверить
            </button>
          )}
        </form>
      )}

      {exercise.type === 'word_order' && (
        <form className="word-order" onSubmit={handleSubmit}>
          <div className="sentence" aria-label="Ваше предложение">
            {placed.length === 0 && <span className="muted">Нажимайте на слова по порядку</span>}
            {placed.map((index) => (
              <button
                key={index}
                type="button"
                className="chip chip-placed"
                disabled={answered}
                onClick={() => setPlaced((p) => p.filter((i) => i !== index))}
              >
                {words[index]}
              </button>
            ))}
          </div>
          <div className="chips">
            {words.map((word, index) =>
              placed.includes(index) ? null : (
                <button
                  key={index}
                  type="button"
                  className="chip"
                  disabled={answered}
                  onClick={() => setPlaced((p) => [...p, index])}
                >
                  {word}
                </button>
              ),
            )}
          </div>
          {!answered && (
            <button
              className="button-primary"
              disabled={submitting || placed.length !== words.length}
            >
              Проверить
            </button>
          )}
        </form>
      )}

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      {answered && (
        <div className="feedback" role="status">
          <p className="feedback-title">{result.is_correct ? 'Верно!' : 'Пока неверно'}</p>
          {!result.is_correct && (
            <p>
              Правильный ответ: <strong>{result.correct_answers.join(' / ')}</strong>
            </p>
          )}
          {result.explanation && <p>{result.explanation}</p>}
          {result.error_type && (
            <p className="muted">
              Ошибка записана в навык «{result.error_type.name}» — система учтёт её в рекомендациях.
            </p>
          )}
          <button type="button" className="button-ghost" onClick={reset}>
            Ещё раз
          </button>
        </div>
      )}
    </article>
  )
}
