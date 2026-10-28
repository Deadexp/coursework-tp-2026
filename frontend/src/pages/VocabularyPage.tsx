import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import {
  addOwnWord,
  addWord,
  listVocabulary,
  removeWord,
  searchWords,
  type SearchResult,
} from '../api/vocabulary'
import { formatNextReview, plural } from '../format'
import { useApi } from '../hooks/useApi'
import { TelegramConnection } from '../components/TelegramConnection'

export function VocabularyPage() {
  const { data: words, error, loading, reload } = useApi(useCallback(() => listVocabulary(), []))
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [own, setOwn] = useState({ text: '', translation: '' })
  const [message, setMessage] = useState('')
  // Пока строка поиска пуста, старые результаты не показываем.
  const visibleResults = query.trim() ? results : []

  useEffect(() => {
    const q = query.trim()
    if (!q) return
    const timer = setTimeout(() => {
      searchWords(q).then(setResults, () => setResults([]))
    }, 300)
    return () => clearTimeout(timer)
  }, [query])

  async function handleAdd(result: SearchResult) {
    await addWord(result.id)
    setResults((rs) => rs.map((r) => (r.id === result.id ? { ...r, in_vocabulary: true } : r)))
    void reload()
  }

  async function handleAddOwn(event: FormEvent) {
    event.preventDefault()
    setMessage('')
    try {
      await addOwnWord(own.text.trim(), own.translation.trim())
      setOwn({ text: '', translation: '' })
      setMessage('Слово добавлено.')
      void reload()
    } catch (err) {
      setMessage(
        err instanceof Error && err.message.includes('already')
          ? 'Это слово уже в словаре.'
          : 'Не удалось добавить слово.',
      )
    }
  }

  async function handleRemove(wordId: number) {
    await removeWord(wordId)
    void reload()
  }

  return (
    <div className="stack-lg">
      <header className="hello">
        <div>
          <h1>Мой словарь</h1>
          <p className="muted">
            {words ? `${words.length} ${plural(words.length, 'слово', 'слова', 'слов')}` : '…'}
          </p>
        </div>
        <Link className="button-primary" to="/review">
          Повторить
        </Link>
      </header>

      <TelegramConnection />

      <button className="button-ghost" disabled={loading} onClick={() => void reload()}>
        Обновить список слов
      </button>

      <div className="vocab-tools">
        <section className="panel stack">
          <h2>Найти в общем словаре</h2>
          <input
            className="answer-input"
            type="search"
            id="word-search"
            aria-label="Поиск слова"
            placeholder="Слово или перевод, например «кош»"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query.trim() && visibleResults.length === 0 && (
            <p className="muted">Ничего не найдено.</p>
          )}
          <ul className="search-results">
            {visibleResults.map((r) => (
              <li key={r.id}>
                <span>
                  <strong>{r.text}</strong> — {r.translation}
                </span>
                {r.in_vocabulary ? (
                  <span className="tag tag-success">В словаре</span>
                ) : (
                  <button className="button-ghost button-small" onClick={() => handleAdd(r)}>
                    Добавить
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>

        <section className="panel stack">
          <h2>Добавить своё слово</h2>
          <form className="own-word" onSubmit={handleAddOwn}>
            <input
              className="answer-input"
              id="own-text"
              aria-label="Слово по-английски"
              placeholder="Слово, например wolf"
              value={own.text}
              onChange={(e) => setOwn((o) => ({ ...o, text: e.target.value }))}
            />
            <input
              className="answer-input"
              id="own-translation"
              aria-label="Перевод"
              placeholder="Перевод, например волк"
              value={own.translation}
              onChange={(e) => setOwn((o) => ({ ...o, translation: e.target.value }))}
            />
            <button
              className="button-primary"
              disabled={!own.text.trim() || !own.translation.trim()}
            >
              Добавить
            </button>
          </form>
          {message && <p className="muted">{message}</p>}
        </section>
      </div>

      <section className="stack">
        <h2>Слова</h2>
        {loading && !words && <p className="muted">Загружаем словарь…</p>}
        {error && <p className="alert">{error}</p>}
        {words && words.length === 0 && (
          <p className="panel muted">
            Пока пусто. Найдите слово выше или откройте любую тему и нажмите «Добавить в словарь».
          </p>
        )}
        {words && words.length > 0 && (
          <div className="table-wrap">
            <table className="vocab-table">
              <thead>
                <tr>
                  <th>Слово</th>
                  <th>Перевод</th>
                  <th>Повторение</th>
                  <th>
                    <span className="visually-hidden">Действия</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {words.map(({ word, next_review_at }) => (
                  <tr key={word.id}>
                    <td>
                      <strong>{word.text}</strong>
                      {word.transcription && <span className="muted"> {word.transcription}</span>}
                    </td>
                    <td>{word.translation}</td>
                    <td className="nowrap">{formatNextReview(next_review_at)}</td>
                    <td className="cell-action">
                      <button
                        className="button-link"
                        onClick={() => handleRemove(word.id)}
                        aria-label={`Удалить ${word.text}`}
                      >
                        Удалить
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
