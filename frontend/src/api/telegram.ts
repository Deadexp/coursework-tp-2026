import { request } from './client'

export type TelegramStatus = { linked: boolean }
export type TelegramLink = { url: string; expires_at: string }

export const telegramStatus = () => request<TelegramStatus>('/telegram/status')
export const createTelegramLink = () =>
  request<TelegramLink>('/telegram/link-code', { method: 'POST' })
