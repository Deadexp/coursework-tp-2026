import { expect, test, type Page } from '@playwright/test'

// Тесты идут по настоящему контенту из backend/content/course.json (нужен `python -m app.seed`).
const TRANSLATIONS: Record<string, string> = {
  usually: 'обычно',
  always: 'всегда',
  watch: 'смотреть',
  live: 'жить',
  every: 'каждый',
}

async function signUp(page: Page) {
  const email = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`
  await page.goto('/register')
  await page.getByLabel('Имя').fill('Анна')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Пароль', { exact: true }).fill('e2e-password-123')
  await page.getByLabel('Повторите пароль').fill('e2e-password-123')
  await page.getByRole('button', { name: 'Создать аккаунт' }).click()
  await expect(page.getByRole('heading', { name: 'Привет, Анна!' })).toBeVisible()
}

function menu(page: Page, name: string) {
  return page.getByRole('navigation', { name: 'Основное меню' }).getByRole('link', { name })
}

function exercise(page: Page, prompt: string) {
  return page.locator('article.exercise', { hasText: prompt })
}

test('курс: тема, теория и все виды упражнений', async ({ page }) => {
  await signUp(page)
  await expect(page.locator('.topic-row')).toHaveCount(5)

  await page
    .getByRole('link', { name: /Present Simple/ })
    .first()
    .click()
  await expect(
    page.getByRole('heading', { name: 'Present Simple', level: 1 }).first(),
  ).toBeVisible()
  await expect(page.getByText('Простое настоящее время')).toBeVisible()

  const choice = exercise(page, 'My cat ___ fish every day.')
  await choice.getByRole('button', { name: 'eat', exact: true }).click()
  await expect(choice.getByText('Пока неверно')).toBeVisible()
  await expect(choice.getByText('Ошибка записана в навык «Present Simple»')).toBeVisible()
  await choice.getByRole('button', { name: 'Ещё раз' }).click()
  await choice.getByRole('button', { name: 'eats', exact: true }).click()
  await expect(choice.getByText('Верно!')).toBeVisible()
  await expect(choice.getByText('Решено')).toBeVisible()

  const gap = exercise(page, 'She ___ (work) in a bank.')
  await gap.getByLabel('Ваш ответ').fill('works')
  await gap.getByRole('button', { name: 'Проверить' }).click()
  await expect(gap.getByText('Верно!')).toBeVisible()

  const order = exercise(page, 'во сколько вы обычно встаёте')
  for (const word of ['I', 'usually', 'get', 'up', 'at', 'seven']) {
    await order.locator('.chips').getByRole('button', { name: word, exact: true }).click()
  }
  await order.getByRole('button', { name: 'Проверить' }).click()
  await expect(order.getByText('Верно!')).toBeVisible()

  await expect(page.getByText('Решено 3 из 6')).toBeVisible()
  await page.getByRole('link', { name: '← Все темы' }).click()
  await expect(page.locator('.topic-row', { hasText: 'Present Simple' })).toContainText('3/6')
})

test('словарь: слова темы, повторение и трудные слова', async ({ page }) => {
  await signUp(page)
  await page
    .getByRole('link', { name: /Present Simple/ })
    .first()
    .click()
  await page.getByRole('button', { name: 'Добавить в словарь' }).click()
  await expect(page.getByText('Добавлено 5 слов')).toBeVisible()

  await menu(page, 'Повторение').click()
  let forgotten = ''
  for (let i = 0; i < 5; i++) {
    // Ждём следующую карточку: ответ на предыдущую сохраняется на сервере.
    await expect(page.getByText(`${i + 1} из 5`)).toBeVisible()
    const word = (await page.locator('.flashcard-word').innerText()).trim()
    const card = page.locator('.flashcard')
    if (i === 0) {
      forgotten = word
      await card.locator('.choice').filter({ hasNotText: TRANSLATIONS[word] }).first().click()
      await card.getByRole('button', { name: 'Дальше' }).click()
    } else {
      await card.getByRole('button', { name: TRANSLATIONS[word], exact: true }).click()
      await card.getByRole('button', { name: 'Легко' }).click()
    }
  }
  await expect(page.getByRole('heading', { name: 'Готово!' })).toBeVisible()
  await expect(page.getByText('сразу вспомнили 4')).toBeVisible()

  await page.getByRole('link', { name: 'На главную' }).click()
  await expect(page.getByText('На сегодня всё повторено')).toBeVisible()
  await expect(page.locator('.word-pills')).toContainText(forgotten)
})

test('словарь: поиск, своё слово и удаление', async ({ page }) => {
  await signUp(page)
  await menu(page, 'Словарь').click()

  await page.getByLabel('Поиск слова').fill('слон')
  const result = page.locator('.search-results li', { hasText: 'elephant' })
  await result.getByRole('button', { name: 'Добавить' }).click()
  await expect(result.getByText('В словаре')).toBeVisible()
  await expect(page.locator('.vocab-table')).toContainText('elephant')

  await page.getByLabel('Слово по-английски').fill('wolf')
  await page.getByLabel('Перевод').fill('волк')
  await page.locator('.own-word').getByRole('button', { name: 'Добавить' }).click()
  await expect(page.locator('.vocab-table')).toContainText('wolf')
  await expect(page.getByText('2 слова')).toBeVisible()

  await page.getByRole('button', { name: 'Удалить wolf' }).click()
  await expect(page.locator('.vocab-table')).not.toContainText('wolf')
})
