import { expect, test, type Page } from '@playwright/test'

// Ответы ИИ подменяются в браузере (page.route): тест проверяет интерфейс,
// не тратит деньги на API и не зависит от модели. Логику сервера проверяют pytest-тесты.

const now = new Date().toISOString()
const opening = {
  id: 1,
  role: 'assistant',
  content: 'Hi! What can I get you?',
  created_at: now,
  corrections: [],
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

test('разговор с собеседником: ответ, исправления и отзыв', async ({ page }) => {
  let dialog = {
    id: 7,
    scenario: 'cafe',
    title: 'В кафе',
    started_at: now,
    ended_at: null as string | null,
    summary: null as string | null,
    messages: [opening] as unknown[],
  }
  await page.route('**/api/dialogs', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 201, json: dialog })
      : route.fulfill({ json: [] }),
  )
  await page.route('**/api/dialogs/7', (route) => route.fulfill({ json: dialog }))
  await page.route('**/api/dialogs/7/messages', async (route) => {
    const { content } = route.request().postDataJSON()
    const user_message = {
      id: 2,
      role: 'user',
      content,
      created_at: now,
      corrections: [
        {
          fragment: 'a coffees',
          correction: 'a coffee',
          explanation: 'После a — единственное число.',
          error_type: { code: 'articles', name: 'Артикли' },
        },
      ],
    }
    const reply = {
      id: 3,
      role: 'assistant',
      content: 'Sure! Small or large?',
      created_at: now,
      corrections: [],
    }
    dialog = { ...dialog, messages: [opening, user_message, reply] }
    await route.fulfill({ status: 201, json: { user_message, reply } })
  })
  await page.route('**/api/dialogs/7/finish', (route) => {
    dialog = {
      ...dialog,
      ended_at: now,
      summary: 'Хороший разговор.\n\nНад чем поработать:\n• Артикли',
    }
    return route.fulfill({ json: dialog })
  })

  await signUp(page)
  await page
    .getByRole('navigation', { name: 'Основное меню' })
    .getByRole('link', { name: 'Собеседник' })
    .click()
  await expect(page.getByRole('button', { name: /В кафе/ })).toBeVisible() // сценарии — настоящие, с сервера
  await page.getByRole('button', { name: /В кафе/ }).click()

  await expect(page).toHaveURL('/talk/7')
  await expect(page.getByText('Hi! What can I get you?')).toBeVisible()

  await page.getByLabel('Ваше сообщение').fill('I want a coffees')
  await page.getByLabel('Ваше сообщение').press('Enter')

  await expect(page.getByText('Sure! Small or large?')).toBeVisible()
  const fixes = page.getByRole('list', { name: 'Исправления' })
  await expect(fixes).toContainText('a coffee')
  await expect(fixes).toContainText('Артикли')

  await page.getByRole('button', { name: 'Завершить и получить отзыв' }).click()
  await expect(page.getByRole('heading', { name: 'Отзыв наставника' })).toBeVisible()
  await expect(page.getByText('• Артикли')).toBeVisible()
  await expect(page.getByLabel('Ваше сообщение')).toHaveCount(0)
})

test('ИИ недоступен: понятная ошибка, текст сообщения не теряется', async ({ page }) => {
  const dialog = {
    id: 8,
    scenario: 'free',
    title: 'Свободная тема',
    started_at: now,
    ended_at: null,
    summary: null,
    messages: [opening],
  }
  await page.route('**/api/dialogs/8', (route) => route.fulfill({ json: dialog }))
  await page.route('**/api/dialogs/8/messages', (route) =>
    route.fulfill({ status: 503, json: { detail: 'Языковая модель временно недоступна' } }),
  )

  await signUp(page)
  await page.goto('/talk/8')
  await page.getByLabel('Ваше сообщение').fill('Hello there')
  await page.getByRole('button', { name: 'Отправить' }).click()

  await expect(page.getByRole('alert')).toHaveText('Языковая модель временно недоступна')
  await expect(page.getByLabel('Ваше сообщение')).toHaveValue('Hello there')
})

test('план наставника на главной: шаги со ссылками и отметка', async ({ page }) => {
  let plan: unknown = null
  const item = {
    id: 1,
    position: 1,
    type: 'topic',
    topic_id: 2,
    title: 'Present Simple',
    reason: 'Вы часто пропускаете -s после he/she.',
    done: false,
  }
  await page.route('**/api/recommendations/plan', (route) => {
    if (route.request().method() === 'POST') {
      plan = {
        id: 1,
        summary: 'Сегодня — Present Simple и повторение слов.',
        created_at: now,
        items: [
          item,
          {
            id: 2,
            position: 2,
            type: 'word_review',
            topic_id: null,
            title: 'Повторить слова',
            reason: '5 слов ждут повторения.',
            done: false,
          },
        ],
      }
      return route.fulfill({ status: 201, json: plan })
    }
    return route.fulfill({ json: plan })
  })
  await page.route('**/api/recommendations/plan/items/1/done', (route) =>
    route.fulfill({ json: { ...item, done: true } }),
  )

  await signUp(page)
  await expect(page.getByRole('heading', { name: 'План на сегодня' })).toBeVisible()
  await page.getByRole('button', { name: 'Составить план' }).click()

  await expect(page.getByText('Сегодня — Present Simple и повторение слов.')).toBeVisible()
  const steps = page.locator('.plan-steps')
  await expect(steps.getByRole('link', { name: 'Present Simple' })).toHaveAttribute(
    'href',
    '/topics/2',
  )
  await expect(steps.getByRole('link', { name: 'Повторить слова' })).toHaveAttribute(
    'href',
    '/review',
  )
  await steps.getByRole('button', { name: 'Отметить' }).first().click()
  await expect(steps.getByText('Сделано')).toBeVisible()
})
