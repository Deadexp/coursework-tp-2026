import { expect, test } from '@playwright/test'

test('общий словарь: сайт, служебный API бота и общие результаты', async ({ page, request }) => {
  const serviceToken = process.env.E2E_BOT_SERVICE_TOKEN
  test.skip(!serviceToken, 'Нужен ключ только из изолированной тестовой среды')
  const telegramId = 9000000000 + (Date.now() % 1000000000)
  const headers = {
    'X-Service-Token': serviceToken!,
    'X-Telegram-ID': String(telegramId),
  }
  const email = `e2e-telegram-${Date.now()}@example.com`
  await page.goto('/register')
  await page.getByLabel('Имя').fill('Ксения')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Пароль', { exact: true }).fill('e2e-password-123')
  await page.getByLabel('Повторите пароль').fill('e2e-password-123')
  await page.getByRole('button', { name: 'Создать аккаунт' }).click()
  await expect(page.getByRole('heading', { name: 'Привет, Ксения!' })).toBeVisible()
  await page.goto('/vocabulary')
  await page.getByLabel('Слово по-английски').fill('bridge')
  await page.getByLabel('Перевод', { exact: true }).fill('мост')
  await page.locator('.own-word').getByRole('button', { name: 'Добавить' }).click()
  await expect(page.locator('.vocab-table')).toContainText('bridge')

  await page.getByRole('button', { name: 'Подключить Telegram', exact: true }).click()
  const link = page.getByRole('link', { name: 'Открыть бота в Telegram' })
  await expect(link).toBeVisible()
  const code = new URL((await link.getAttribute('href'))!).searchParams.get('start')
  const linked = await request.post('/api/telegram/link', {
    headers,
    data: { code, telegram_id: telegramId },
  })
  expect(linked.status()).toBe(200)
  await page.getByRole('button', { name: 'Обновить статус Telegram' }).click()
  await expect(page.getByRole('status')).toContainText('Telegram подключён')

  const dictionary = await request.get('/api/vocabulary/page', { headers })
  const rows = (await dictionary.json()).items
  expect(rows[0].word.text).toBe('bridge')
  const wordId = rows[0].word.id
  const added = await request.post('/api/vocabulary', {
    headers,
    data: { text: 'shared', translation: 'общий' },
  })
  expect(added.status()).toBe(201)
  await page.getByRole('button', { name: 'Обновить список слов' }).click()
  await expect(page.locator('.vocab-table')).toContainText('shared')

  const reviewed = await request.post(`/api/vocabulary/${wordId}/reviews`, {
    headers,
    data: { quality: 1, source: 'bot' },
  })
  expect(reviewed.status()).toBe(200)
  const nextReview = (await reviewed.json()).next_review_at
  const wordsAfterReview = await request.get('/api/vocabulary', { headers })
  expect(
    (await wordsAfterReview.json()).find((row: { word: { id: number } }) => row.word.id === wordId)
      .next_review_at,
  ).toBe(nextReview)

  expect((await request.delete(`/api/vocabulary/${wordId}`, { headers })).status()).toBe(204)
  await page.getByRole('button', { name: 'Обновить список слов' }).click()
  await expect(page.locator('.vocab-table')).not.toContainText('bridge')
  await expect(page.locator('.vocab-table')).toContainText('shared')
})
