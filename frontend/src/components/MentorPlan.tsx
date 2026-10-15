import { useCallback, useState } from 'react'
import { Link } from 'react-router'
import { createPlan, latestPlan, markPlanItemDone, type PlanItem } from '../api/ai'
import { useApi } from '../hooks/useApi'

function stepLink(item: PlanItem): string {
  if (item.type === 'topic' && item.topic_id) return `/topics/${item.topic_id}`
  if (item.type === 'word_review') return '/review'
  return '/talk'
}

/** План занятия от адаптивного наставника (LLM) на главной странице. */
export function MentorPlan() {
  const { data: plan, loading, setData } = useApi(useCallback(() => latestPlan(), []))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function handleCreate() {
    setBusy(true)
    setError('')
    try {
      setData(await createPlan())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось составить план')
    } finally {
      setBusy(false)
    }
  }

  async function handleDone(item: PlanItem) {
    const updated = await markPlanItemDone(item.id)
    if (plan) setData({ ...plan, items: plan.items.map((i) => (i.id === item.id ? updated : i)) })
  }

  if (loading && plan === undefined) return null

  return (
    <section className="panel stack mentor">
      <div className="review-cta">
        <div>
          <p className="eyebrow">Наставник · ИИ</p>
          <h2>План на сегодня</h2>
        </div>
        <button className="button-ghost" onClick={handleCreate} disabled={busy}>
          {busy ? 'Наставник думает…' : plan ? 'Составить заново' : 'Составить план'}
        </button>
      </div>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      {!plan && !busy && (
        <p className="muted">
          Наставник посмотрит на ваши ошибки в упражнениях и разговорах, прогресс по темам и словарь
          и предложит, чем заняться сегодня.
        </p>
      )}

      {plan && (
        <>
          <p>{plan.summary}</p>
          <ol className="plan-steps">
            {plan.items.map((item) => (
              <li key={item.id} className={item.done ? 'is-done' : ''}>
                <div className="plan-step-main">
                  <Link to={stepLink(item)} className="plan-step-title">
                    {item.title}
                  </Link>
                  {item.reason && <span className="muted">{item.reason}</span>}
                </div>
                {item.done ? (
                  <span className="tag tag-success">Сделано</span>
                ) : (
                  <button className="button-link" onClick={() => handleDone(item)}>
                    Отметить
                  </button>
                )}
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  )
}
