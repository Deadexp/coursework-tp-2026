import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import {
  addOwnWord,
  addWord,
  listVocabulary,
  removeWord,
  searchWords,
  uploadWordImage,
  type SearchResult,
} from '../api/vocabulary'
import { formatNextReview, plural } from '../format'
import { useApi } from '../hooks/useApi'
import { TelegramConnection } from '../components/TelegramConnection'
import { VocabularyModules } from '../components/VocabularyModules'
import { WordImage } from '../components/WordImage'

export function VocabularyPage() {
  const { data: words, error, loading, reload } = useApi(useCallback(() => listVocabulary(), []))
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [own, setOwn] = useState({ text: '', translation: '' })
  const [message, setMessage] = useState('')
  const [ownImage, setOwnImage] = useState<File | null>(null)
  const [saving, setSaving] = useState(false)
  const imageInput = useRef<HTMLInputElement>(null)
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
    setSaving(true)
    try {
      const saved = await addOwnWord(own.text.trim(), own.translation.trim())
      let imageSaved = true
      if (ownImage) {
        try { await uploadWordImage(saved.word.id, ownImage) }
        catch { imageSaved = false }
      }
      setOwn({ text: '', translation: '' })
      setOwnImage(null)
      if (imageInput.current) imageInput.current.value = ''
      setMessage(imageSaved ? 'Слово добавлено.' :
        'Слово добавлено, но картинка не загрузилась. Добавьте её в списке слов ниже.')
      void reload()
    } catch (err) {
      setMessage(
        err instanceof Error && err.message.includes('already')
          ? 'Это слово уже в словаре.'
          : 'Не удалось добавить слово.',
      )
    } finally { setSaving(false) }
  }

  async function handleImage(wordId: number, file?: File) {
    if (!file) return
    if (file.size > 5 * 1024 * 1024) {
      setMessage('Картинка должна быть не больше 5 МБ.')
      return
    }
    try {
      await uploadWordImage(wordId, file)
      setMessage('Картинка сохранена. Она появится в боте при открытии карточек.')
      void reload()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Не удалось сохранить картинку.')
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

      <VocabularyModules
        vocabularyRevision={words?.map(({ word }) => word.id).join(',') ?? ''}
        onAdded={() => void reload()}
      />

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
              disabled={saving}
              aria-label="Слово по-английски"
              placeholder="Слово, например wolf"
              value={own.text}
              onChange={(e) => setOwn((o) => ({ ...o, text: e.target.value }))}
            />
            <input
              className="answer-input"
              id="own-translation"
              disabled={saving}
              aria-label="Перевод"
              placeholder="Перевод, например волк"
              value={own.translation}
              onChange={(e) => setOwn((o) => ({ ...o, translation: e.target.value }))}
            />
            <button
              className="button-primary"
              disabled={saving || !own.text.trim() || !own.translation.trim()
                || (ownImage !== null && ownImage.size > 5 * 1024 * 1024)}
            >
              Добавить
            </button>
            <label className="stack">
              Картинка (необязательно, JPEG, PNG или WebP до 5 МБ)
              <input ref={imageInput} disabled={saving}
                type="file" accept="image/jpeg,image/png,image/webp"
                onChange={(event) => setOwnImage(event.target.files?.[0] ?? null)} />
            </label>
            {ownImage && ownImage.size > 5 * 1024 * 1024 && (
              <p className="alert">Картинка должна быть не больше 5 МБ.</p>
            )}
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
            Пока пусто. Выберите тематический набор выше, найдите слово или добавьте своё.
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
                      <WordImage word={word} />
                      <strong>{word.text}</strong>
                      {word.transcription && <span className="muted"> {word.transcription}</span>}
                    </td>
                    <td>{word.translation}</td>
                    <td className="nowrap">{formatNextReview(next_review_at)}</td>
                    <td className="cell-action">
                      <label className="button-link">
                        {word.image_url ? 'Заменить картинку' : 'Добавить картинку'}
                        <input type="file" accept="image/jpeg,image/png,image/webp"
                          aria-label={`Картинка для ${word.text}`}
                          onChange={(event) => {
                            void handleImage(word.id, event.target.files?.[0])
                            event.target.value = ''
                          }} />
                      </label>
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
