import { request } from './client'

export interface IProgressStats {
  level: string
  words: number
  due: number
  reviews: number
  attempted: number
  correct: number
  quizzes_completed: number
  daily_completed: number
  grammar_attempted: number
  grammar_correct: number
  last_daily_date: string | null
}

export interface IReminderSettings {
  enabled: boolean
  time: string
  timezone: string
}

export const getProgress = () => request<IProgressStats>('/practice/progress')
export const getReminderSettings = () => request<IReminderSettings>('/reminders/settings')
export const saveReminderSettings = (settings: IReminderSettings) =>
  request<IReminderSettings>('/reminders/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
