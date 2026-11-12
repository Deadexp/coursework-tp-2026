import { request } from './client'

export type PlacementLevel = 'A1' | 'A2' | 'B1'

export interface IPlacementQuestion {
  id: string
  position: number
  level: PlacementLevel
  skill: 'grammar' | 'vocabulary' | 'reading'
  prompt: string
  passage: string | null
  options: string[]
}

export interface IPlacementAnswer {
  question_id: string
  option_index: number
}

export interface IPlacementResult {
  recommended_level: PlacementLevel
  correct: number
  total: number
  scores: { level: PlacementLevel; correct: number; total: number }[]
  summary: string
  limitations: string
  answers: (IPlacementAnswer & {
    correct_option_index: number
    is_correct: boolean
    explanation: string
  })[]
}

export interface IPlacementAttempt {
  id: number
  version: string
  status: 'in_progress' | 'completed'
  started_at: string
  submitted_at: string | null
  applied_at: string | null
  total: number
  questions: IPlacementQuestion[]
  result: IPlacementResult | null
}

export const startPlacement = () =>
  request<IPlacementAttempt>('/placement/attempts', { method: 'POST' })
export const getPlacement = (id: number) => request<IPlacementAttempt>(`/placement/attempts/${id}`)
export const placementHistory = () => request<IPlacementAttempt[]>('/placement/history')
export const submitPlacement = (id: number, answers: IPlacementAnswer[]) =>
  request<IPlacementAttempt>(`/placement/attempts/${id}/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answers }),
  })
export const applyPlacement = (id: number) =>
  request<IPlacementAttempt>(`/placement/attempts/${id}/apply`, { method: 'POST' })
