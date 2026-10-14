import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'e2e-password-123'

function uniqueEmail() {
  return `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`
}

async function registerUser(page: Page, email: string, name = 'Анна') {
  await page.goto('/register')
  await page.getByLabel('Имя').fill(name)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await page.getByLabel('Повторите пароль').fill(PASSWORD)
  await page.getByRole('button', { name: 'Создать аккаунт' }).click()
}

test('регистрация сразу пускает в личный кабинет', async ({ page }) => {
  await registerUser(page, uniqueEmail())

  await expect(page).toHaveURL('/')
  await expect(page.getByRole('heading', { name: 'Привет, Анна!' })).toBeVisible()
})

test('выход и повторный вход', async ({ page }) => {
  const email = uniqueEmail()
  await registerUser(page, email)
  await page.getByRole('button', { name: 'Выйти' }).click()
  await expect(page).toHaveURL('/login')

  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Войти' }).click()

  await expect(page.getByRole('heading', { name: 'Привет, Анна!' })).toBeVisible()
})

test('вход сохраняется после перезагрузки страницы', async ({ page }) => {
  await registerUser(page, uniqueEmail())
  await expect(page).toHaveURL('/')

  await page.reload()

  await expect(page.getByRole('heading', { name: 'Привет, Анна!' })).toBeVisible()
})

test('неверный пароль показывает ошибку', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill(uniqueEmail())
  await page.getByLabel('Пароль', { exact: true }).fill('wrong-password')
  await page.getByRole('button', { name: 'Войти' }).click()

  await expect(page.getByRole('alert')).toHaveText('Неверный email или пароль')
})

test('форма регистрации проверяет поля до отправки', async ({ page }) => {
  await page.goto('/register')
  await page.getByLabel('Email').fill('not-an-email')
  await page.getByLabel('Пароль', { exact: true }).fill('short')
  await page.getByLabel('Повторите пароль').fill('other')
  await page.getByRole('button', { name: 'Создать аккаунт' }).click()

  await expect(page.getByText('Как к вам обращаться?')).toBeVisible()
  await expect(page.getByText('Введите email, например anna@mail.ru')).toBeVisible()
  await expect(page.getByText('Минимум 8 символов')).toBeVisible()
  await expect(page.getByText('Пароли не совпадают')).toBeVisible()
})

test('повторная регистрация с тем же email', async ({ page }) => {
  const email = uniqueEmail()
  await registerUser(page, email)
  await page.getByRole('button', { name: 'Выйти' }).click()

  await registerUser(page, email)

  await expect(page.getByText('Этот email уже зарегистрирован')).toBeVisible()
})

test('закрытая страница отправляет на вход', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL('/login')
})
