import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link, useParams } from 'react-router'
import { finishDialog, getDialog, sendMessage, type DialogMessage } from '../api/ai'
import { useApi } from '../hooks/useApi'

export function TalkPage() {
  const dialogId = Number(useParams().dialogId)
  const load = useCallback(() => getDialog(dialogId), [dialogId])
  const { data: dialog, error, loading, setData } = useApi(load)
  const [text, setText] = useState('')
  const [pending, setPending] = useState<string | null>(null) // реплика, ждущая ответа
  const [sendError, setSendError] = useState('')
  const [finishing, setFinishing] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  const messageCount = dialog?.messages.length ?? 0
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
  }, [messageCount, pending])

  if (loading && !dialog) return <p className="muted">Загружаем разговор…</p>
  if (error || !dialog) return <p className="alert">{error || 'Разговор не найден'}</p>

  const finished = dialog.ended_at !== null

  async function handleSend(event?: FormEvent) {
    event?.preventDefault()
    const content = text.trim()
    if (!content || pending || !dialog) return
    setPending(content)
    setText('')
    setSendError('')
    try {
      const { user_message, reply } = await sendMessage(dialog.id, content)
      setData({ ...dialog, messages: [...dialog.messages, user_message, reply] })
    } catch (err) {
      setText(content) // вернём текст, чтобы его не пришлось набирать заново
      setSendError(err instanceof Error ? err.message : 'Сообщение не отправлено')
    } finally {
      setPending(null)
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void handleSend()
    }
  }

  async function handleFinish() {
    if (!dialog) return
    setFinishing(true)
    setSendError('')
    try {
      setData(await finishDialog(dialog.id))
    } catch (err) {
      setSendError(err instanceof Error ? err.message : 'Не удалось завершить разговор')
    } finally {
      setFinishing(false)
    }
  }

  return (
    <div className="talk stack">
      <Link to="/talk" className="back-link">
        ← Все разговоры
      </Link>
      <header className="review-cta">
        <div>
          <p className="eyebrow">Разговор с Emma</p>
          <h1>{dialog.title}</h1>
        </div>
        {!finished && (
          <button
            className="button-ghost"
            onClick={handleFinish}
            disabled={finishing || pending !== null}
          >
            {finishing ? 'Готовим отзыв…' : 'Завершить и получить отзыв'}
          </button>
        )}
      </header>

      <section className="chat" aria-live="polite">
        {dialog.messages.map((m) => (
          <ChatMessage key={m.id} message={m} />
        ))}
        {pending && (
          <>
            <div className="bubble bubble-user">{pending}</div>
            <div className="bubble bubble-assistant typing">Emma печатает…</div>
          </>
        )}
        <div ref={endRef} />
      </section>

      {sendError && (
        <p className="alert" role="alert">
          {sendError}
        </p>
      )}

      {finished ? (
        <section className="panel stack">
          <h2>Отзыв наставника</h2>
          <p className="feedback-text">{dialog.summary}</p>
          <Link className="button-primary" to="/talk">
            Новый разговор
          </Link>
        </section>
      ) : (
        <form className="chat-input" onSubmit={handleSend}>
          <textarea
            id="chat-message"
            aria-label="Ваше сообщение"
            placeholder="Напишите по-английски…"
            value={text}
            maxLength={1000}
            rows={2}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button className="button-primary" disabled={!text.trim() || pending !== null}>
            Отправить
          </button>
        </form>
      )}
      {!finished && (
        <p className="muted chat-hint">Enter — отправить, Shift+Enter — новая строка</p>
      )}
    </div>
  )
}

function ChatMessage({ message }: { message: DialogMessage }) {
  const isUser = message.role === 'user'
  return (
    <div className={`chat-row ${isUser ? 'chat-row-user' : ''}`}>
      <div className={`bubble ${isUser ? 'bubble-user' : 'bubble-assistant'}`}>
        {message.content}
      </div>
      {message.corrections.length > 0 && (
        <ul className="corrections" aria-label="Исправления">
          {message.corrections.map((c, i) => (
            <li key={i}>
              <span>
                <s>{c.fragment}</s> → <strong>{c.correction}</strong>
              </span>
              {c.explanation && <span className="muted"> — {c.explanation}</span>}
              <span className="tag">{c.error_type.name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
