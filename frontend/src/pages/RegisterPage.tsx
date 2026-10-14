import { useState, type ChangeEvent, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/context'
import { AuthLayout } from '../components/AuthLayout'
import { TextField } from '../components/TextField'

const MIN_PASSWORD = 8

type Form = { display_name: string; email: string; password: string; confirm: string }
type Errors = Partial<Record<keyof Form, string>>

function validate(form: Form): Errors {
  const errors: Errors = {}
  if (!form.display_name.trim()) errors.display_name = 'Как к вам обращаться?'
  if (!/^\S+@\S+\.\S+$/.test(form.email)) errors.email = 'Введите email, например anna@mail.ru'
  if (form.password.length < MIN_PASSWORD) errors.password = `Минимум ${MIN_PASSWORD} символов`
  if (form.confirm !== form.password) errors.confirm = 'Пароли не совпадают'
  return errors
}

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()

  const [form, setForm] = useState<Form>({ display_name: '', email: '', password: '', confirm: '' })
  const [errors, setErrors] = useState<Errors>({})
  const [formError, setFormError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const update = (field: keyof Form) => (e: ChangeEvent<HTMLInputElement>) => {
    setForm((f) => ({ ...f, [field]: e.target.value }))
    setErrors((errs) => ({ ...errs, [field]: undefined }))
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setFormError('')
    const found = validate(form)
    setErrors(found)
    if (Object.keys(found).length > 0) return

    setSubmitting(true)
    try {
      await register({
        display_name: form.display_name.trim(),
        email: form.email,
        password: form.password,
      })
      navigate('/', { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setErrors({ email: 'Этот email уже зарегистрирован' })
      } else if (err instanceof ApiError && err.status === 422) {
        setErrors(err.fieldErrors)
        setFormError(err.message)
      } else {
        setFormError(err instanceof Error ? err.message : 'Что-то пошло не так')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout title="Регистрация">
      <form onSubmit={handleSubmit} noValidate>
        {formError && (
          <div className="alert" role="alert">
            {formError}
          </div>
        )}
        <TextField
          label="Имя"
          autoComplete="given-name"
          value={form.display_name}
          onChange={update('display_name')}
          error={errors.display_name}
        />
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          value={form.email}
          onChange={update('email')}
          error={errors.email}
        />
        <TextField
          label="Пароль"
          type="password"
          autoComplete="new-password"
          value={form.password}
          onChange={update('password')}
          error={errors.password}
        />
        <TextField
          label="Повторите пароль"
          type="password"
          autoComplete="new-password"
          value={form.confirm}
          onChange={update('confirm')}
          error={errors.confirm}
        />
        <button className="button-primary" type="submit" disabled={submitting}>
          {submitting ? 'Создаём аккаунт…' : 'Создать аккаунт'}
        </button>
      </form>
      <p className="auth-switch">
        Уже есть аккаунт? <Link to="/login">Войти</Link>
      </p>
    </AuthLayout>
  )
}
