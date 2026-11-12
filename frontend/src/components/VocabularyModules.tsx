import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { addVocabularyModule, getVocabularyModule, listVocabularyModules } from '../api/vocabulary'
import { plural } from '../format'
import { useApi } from '../hooks/useApi'
import '../vocabulary-modules.css'

type Props = { vocabularyRevision: string; onAdded: () => void }

function useVocabularyRefresh(revision: string, reload: () => Promise<void>) {
  const previousRevision = useRef(revision)
  useEffect(() => {
    if (previousRevision.current !== revision) {
      previousRevision.current = revision
      void reload()
    }
  }, [revision, reload])
}

export function VocabularyModules({ vocabularyRevision, onAdded }: Props) {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const { data: modules, loading, error, reload } = useApi(listVocabularyModules)
  useVocabularyRefresh(vocabularyRevision, reload)

  return (
    <section className="vocabulary-modules stack" aria-labelledby="vocabulary-modules-title">
      <div className="module-section-heading">
        <div className="stack module-heading-copy">
          <p className="eyebrow">Учимся по темам</p>
          <h2 id="vocabulary-modules-title">Слова, которые легко представить</h2>
          <p className="muted">
            Выберите тему, познакомьтесь с карточками и добавьте слова для повторения.
          </p>
        </div>
        {modules && <span className="badge">{modules.length} тем</span>}
      </div>

      {selectedId !== null ? (
        <VocabularyModuleViewer
          key={selectedId}
          moduleId={selectedId}
          vocabularyRevision={vocabularyRevision}
          onBack={() => setSelectedId(null)}
          onAdded={() => {
            onAdded()
            void reload()
          }}
        />
      ) : (
        <>
          {loading && !modules && <p className="muted">Загружаем темы словаря…</p>}
          {error && (
            <div className="alert" role="alert">
              <p>{error}</p>
              <button className="button-ghost button-small" onClick={() => void reload()}>
                Попробовать снова
              </button>
            </div>
          )}
          {modules?.length === 0 && <p className="muted">Темы словаря скоро появятся.</p>}
          <div className="module-grid">
            {modules?.map((module) => (
              <button
                key={module.id}
                className="module-tile"
                onClick={() => setSelectedId(module.id)}
                aria-label={`Открыть тему «${module.title}»`}
              >
                <div className="module-tile-top">
                  {module.cover_image_url && (
                    <img
                      src={module.cover_image_url}
                      alt=""
                      width="96"
                      height="96"
                      loading="lazy"
                    />
                  )}
                  <span className="badge">{module.cefr_level}</span>
                </div>
                <strong className="module-tile-title">{module.title}</strong>
                <span className="muted module-tile-description">{module.description}</span>
                <span className="module-tile-footer">
                  <span>
                    {module.word_count} {plural(module.word_count, 'слово', 'слова', 'слов')}
                  </span>
                  {module.in_vocabulary_count === module.word_count && module.word_count > 0 ? (
                    <span className="tag tag-success">В словаре</span>
                  ) : (
                    <span className="muted">{module.in_vocabulary_count} добавлено</span>
                  )}
                </span>
              </button>
            ))}
          </div>
        </>
      )}
    </section>
  )
}

type ViewerProps = Props & { moduleId: number; onBack: () => void }

function VocabularyModuleViewer({ moduleId, vocabularyRevision, onBack, onAdded }: ViewerProps) {
  const {
    data: module,
    loading,
    error,
    reload,
  } = useApi(useCallback(() => getVocabularyModule(moduleId), [moduleId]))
  useVocabularyRefresh(vocabularyRevision, reload)
  const [cardIndex, setCardIndex] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const [adding, setAdding] = useState(false)
  const [message, setMessage] = useState('')
  const [actionError, setActionError] = useState('')
  const word = module?.words[cardIndex]

  function showCard(index: number) {
    setCardIndex(index)
    setRevealed(false)
  }

  async function addAll() {
    setAdding(true)
    setMessage('')
    setActionError('')
    try {
      const result = await addVocabularyModule(moduleId)
      setMessage(
        result.added > 0
          ? `Добавлено ${result.added} ${plural(result.added, 'слово', 'слова', 'слов')}. Можно начать повторение.`
          : 'Все слова этой темы уже в вашем словаре.',
      )
      await reload()
      onAdded()
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : 'Не удалось добавить слова. Попробуйте снова.',
      )
    } finally {
      setAdding(false)
    }
  }

  return (
    <div className="panel module-viewer stack">
      <button className="button-link module-back" onClick={onBack}>
        ← Все темы словаря
      </button>
      {loading && !module && <p className="muted">Готовим карточки…</p>}
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {module && (
        <>
          <div className="module-section-heading">
            <div className="stack module-heading-copy">
              <p className="eyebrow">
                {module.cefr_level} · {module.word_count} карточек
              </p>
              <h3 className="module-viewer-title">{module.title}</h3>
              <p className="muted">{module.description}</p>
            </div>
            <button
              className="button-primary"
              disabled={adding || module.in_vocabulary_count === module.word_count}
              onClick={() => void addAll()}
            >
              {adding
                ? 'Добавляем…'
                : module.in_vocabulary_count === module.word_count
                  ? 'Все слова в словаре'
                  : 'Добавить все слова'}
            </button>
          </div>
          {actionError && (
            <p className="alert" role="alert">
              {actionError}
            </p>
          )}
          {message && (
            <p className="module-success" role="status">
              {message} <Link to="/review">Повторить</Link>
            </p>
          )}
          {word && (
            <>
              <article
                className="module-flashcard"
                aria-label={`Карточка ${cardIndex + 1} из ${module.words.length}`}
              >
                <div className="module-flashcard-art">
                  {word.image_url && <img src={word.image_url} alt="" width="208" height="208" />}
                </div>
                <div className="module-flashcard-copy stack" aria-live="polite">
                  {word.in_vocabulary && <span className="tag tag-success">В моём словаре</span>}
                  <p className="module-word" lang="en">
                    {word.text}
                  </p>
                  {word.transcription && <p className="muted">{word.transcription}</p>}
                  <button
                    className="button-ghost"
                    aria-expanded={revealed}
                    onClick={() => setRevealed((value) => !value)}
                  >
                    {revealed ? 'Скрыть перевод' : 'Показать перевод'}
                  </button>
                  {revealed && (
                    <div className="module-word-answer stack">
                      <p className="module-translation">{word.translation}</p>
                      {word.example && (
                        <p className="example" lang="en">
                          {word.example}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </article>
              <div className="module-card-controls">
                <button
                  className="button-ghost"
                  disabled={cardIndex === 0}
                  onClick={() => showCard(cardIndex - 1)}
                  aria-label="Предыдущая карточка"
                >
                  ← Назад
                </button>
                <span className="muted" aria-live="polite">
                  {cardIndex + 1} / {module.words.length}
                </span>
                <button
                  className="button-ghost"
                  disabled={cardIndex === module.words.length - 1}
                  onClick={() => showCard(cardIndex + 1)}
                  aria-label="Следующая карточка"
                >
                  Дальше →
                </button>
              </div>
              <div className="module-card-index" aria-label="Выбрать слово">
                {module.words.map((item, index) => (
                  <button
                    key={item.id}
                    className="chip"
                    aria-pressed={index === cardIndex}
                    onClick={() => showCard(index)}
                    lang="en"
                  >
                    {item.text}
                  </button>
                ))}
              </div>
            </>
          )}
          <p className="muted module-note">
            Знакомство с карточками не меняет расписание. Для тренировки памяти перейдите в
            «Повторить».
          </p>
        </>
      )}
    </div>
  )
}
