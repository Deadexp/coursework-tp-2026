import { request } from './client'

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

// ---- Собеседник ----

export type Scenario = { code: string; title: string; description: string }

export type Correction = {
  fragment: string
  correction: string
  explanation: string | null
  error_type: { code: string; name: string }
}

export type DialogMessage = {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
  corrections: Correction[]
}

export type DialogSummary = {
  id: number
  scenario: string
  title: string
  started_at: string
  ended_at: string | null
  messages: number
}

export type Dialog = Omit<DialogSummary, 'messages'> & {
  summary: string | null
  messages: DialogMessage[]
}

export const listScenarios = () => request<Scenario[]>('/dialogs/scenarios')
export const listDialogs = () => request<DialogSummary[]>('/dialogs')
export const getDialog = (id: number) => request<Dialog>(`/dialogs/${id}`)
export const startDialog = (scenario: string) => request<Dialog>('/dialogs', json({ scenario }))
export const sendMessage = (id: number, content: string) =>
  request<{ user_message: DialogMessage; reply: DialogMessage }>(
    `/dialogs/${id}/messages`,
    json({ content }),
  )
export const finishDialog = (id: number) =>
  request<Dialog>(`/dialogs/${id}/finish`, { method: 'POST' })

// ---- Наставник ----

export type PlanItem = {
  id: number
  position: number
  type: 'topic' | 'exercise' | 'word_review' | 'dialog'
  topic_id: number | null
  title: string
  reason: string | null
  done: boolean
}

export type Plan = { id: number; summary: string; created_at: string; items: PlanItem[] }

export const latestPlan = () => request<Plan | null>('/recommendations/plan')
export const createPlan = () => request<Plan>('/recommendations/plan', { method: 'POST' })
export const markPlanItemDone = (id: number) =>
  request<PlanItem>(`/recommendations/plan/items/${id}/done`, { method: 'POST' })
