import { expect, test, type Page } from '@playwright/test'

async function register(page: Page) {
  await page.goto('/register')
  await page.getByLabel('Имя').fill('Тест профиля')
  await page
    .getByLabel('Email')
    .fill(`e2e-profile-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`)
  await page.getByLabel('Пароль', { exact: true }).fill('coursework-e2e-password')
  await page.getByLabel('Повторите пароль').fill('coursework-e2e-password')
  await page.getByRole('button', { name: 'Создать аккаунт' }).click()
  await expect(page).toHaveURL('/')
}

test('профиль показывает статистику и не включает напоминания без Telegram', async ({ page }) => {
  await register(page)
  await page.getByRole('link', { name: 'Личный кабинет', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Тест профиля', exact: true })).toBeVisible()
  await expect(page.getByText('Слов в словаре', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'История тестирования' })).toBeVisible()
  await page.getByLabel('Присылать напоминания в Telegram').check()
  await page.getByRole('button', { name: 'Сохранить напоминания' }).click()
  await expect(page.getByRole('alert')).toContainText('Сначала подключите Telegram')
})

test('тест сохраняет черновик, результат и применённый уровень', async ({ page }) => {
  await register(page)
  await page.goto('/placement')
  await page.getByRole('button', { name: 'Начать тест', exact: true }).click()
  await expect(page).toHaveURL(/placement\?attempt=\d+/)
  await page.getByRole('radio').first().check()
  await page.reload()
  await expect(page.getByRole('radio').first()).toBeChecked()
  for (let index = 0; index < 24; index++) {
    await page.getByRole('radio').first().check()
    await page
      .getByRole('button', {
        name: index === 23 ? 'Завершить тест' : 'Следующий вопрос',
        exact: true,
      })
      .click()
  }
  await expect(page.getByRole('heading', { name: 'Ваш результат', exact: true })).toBeVisible()
  await page.getByRole('button', { name: /^Сохранить уровень / }).click()
  await expect(page.getByRole('button', { name: 'Уровень уже сохранён' })).toBeDisabled()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Ваш результат', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Уровень уже сохранён' })).toBeDisabled()
  await page.getByRole('link', { name: '← Личный кабинет', exact: true }).click()
  await expect(page.getByText('Результат применён', { exact: false })).toBeVisible()
})
