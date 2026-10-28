import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('access_token', 'mock-user-token'))
  await page.route('**/api/users/me', (route) =>
    route.fulfill({
      json: {
        id: 1,
        email: 'ui@example.com',
        display_name: 'Анна',
        cefr_level: 'A1',
        created_at: '2030-01-01T00:00:00Z',
      },
    }),
  )
  await page.route('**/api/vocabulary', (route) => route.fulfill({ json: [] }))
})

test('подключение Telegram и явное обновление статуса', async ({ page }) => {
  let linked = false
  await page.route('**/api/telegram/status', (route) => route.fulfill({ json: { linked } }))
  await page.route('**/api/telegram/link-code', async (route) => {
    expect(route.request().headers()['authorization']).toBe('Bearer mock-user-token')
    expect(route.request().method()).toBe('POST')
    await route.fulfill({
      status: 201,
      json: {
        url: 'https://t.me/course_test_bot?start=synthetic-test-link',
        expires_at: '2030-01-01T12:10:00Z',
      },
    })
  })
  await page.goto('/vocabulary')
  await page.getByRole('button', { name: 'Подключить Telegram', exact: true }).click()
  await expect(page.getByRole('link', { name: 'Открыть бота в Telegram' })).toHaveAttribute(
    'href',
    'https://t.me/course_test_bot?start=synthetic-test-link',
  )
  await expect(page.getByText(/Ссылка одноразовая/)).toBeVisible()
  linked = true
  await page.getByRole('button', { name: 'Обновить статус Telegram' }).click()
  await expect(page.getByRole('status')).toContainText('Telegram подключён')
  await expect(page.getByRole('link', { name: 'Открыть бота в Telegram' })).toHaveCount(0)
})

test('ошибка подключения не скрывает личный словарь', async ({ page }) => {
  await page.route('**/api/telegram/status', (route) => route.fulfill({ json: { linked: false } }))
  await page.route('**/api/telegram/link-code', (route) =>
    route.fulfill({ status: 503, json: { detail: 'Telegram not configured' } }),
  )
  await page.goto('/vocabulary')
  await page.getByRole('button', { name: 'Подключить Telegram', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Не удалось получить ссылку')
  await expect(page.getByRole('heading', { name: 'Мой словарь', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Обновить список слов' })).toBeEnabled()
})
