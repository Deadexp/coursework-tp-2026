import { request } from './client'

export type ExerciseType = 'multiple_choice' | 'fill_gap' | 'translate' | 'word_order'

export type TopicSummary = {
  id: number
  title: string
  cefr_level: string
  position: number
  exercises_total: number
  exercises_solved: number
}

export type Exercise = {
  id: number
  type: ExerciseType
  prompt: string
  options: string[] | null
  words: string[] | null
  solved: boolean
}

export type TopicDetail = {
  id: number
  title: string
  cefr_level: string
  theory: string
  exercises: Exercise[]
}

export type AttemptResult = {
  is_correct: boolean
  correct_answers: string[]
  explanation: string | null
  error_type: { code: string; name: string } | null
}

export const listTopics = () => request<TopicSummary[]>('/topics')

export const getTopic = (id: number) => request<TopicDetail>(`/topics/${id}`)

export const submitAttempt = (exerciseId: number, answer: string) =>
  request<AttemptResult>(`/exercises/${exerciseId}/attempts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answer, source: 'web' }),
  })
