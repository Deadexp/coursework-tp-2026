import { request } from './client'

export type Word = {
  id: number
  text: string
  part_of_speech: string
  translation: string
  transcription: string | null
  example: string | null
}

export type UserWord = {
  word: Word
  added_at: string
  next_review_at: string
  interval_days: number
  repetitions: number
  ease_factor: number
}

export type SearchResult = Word & { in_vocabulary: boolean }
export type ReviewCard = { word: Word; choices: string[] }
export type ProblemWord = { word: Word; failures: number; last_failed_at: string }

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const listVocabulary = () => request<UserWord[]>('/vocabulary')

export const searchWords = (q: string) =>
  request<SearchResult[]>(`/words?${new URLSearchParams({ q })}`)

export const addWord = (wordId: number) =>
  request<UserWord>('/vocabulary', json({ word_id: wordId }))

export const addOwnWord = (text: string, translation: string) =>
  request<UserWord>('/vocabulary', json({ text, translation }))

export const addTopicWords = (topicId: number) =>
  request<{ added: number }>(`/vocabulary/topics/${topicId}`, { method: 'POST' })

export const removeWord = (wordId: number) =>
  request<null>(`/vocabulary/${wordId}`, { method: 'DELETE' })

export const dueCards = (limit = 20) => request<ReviewCard[]>(`/vocabulary/review?limit=${limit}`)

/** quality по SM-2: 1 — не вспомнил, 3 — с трудом, 4 — хорошо, 5 — легко (docs/api-vocabulary.md). */
export const recordReview = (wordId: number, quality: number) =>
  request<{ next_review_at: string; interval_days: number }>(
    `/vocabulary/${wordId}/reviews`,
    json({ quality, source: 'web' }),
  )

export const problemWords = () => request<ProblemWord[]>('/vocabulary/problem-words')
