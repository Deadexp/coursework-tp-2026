import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/context'

type State<T> = { data: T | undefined; error: string; loading: boolean }

/** Загружает данные при монтировании. `load` должен быть стабильным (useCallback). */
export function useApi<T>(load: () => Promise<T>) {
  const { logout } = useAuth()
  const [state, setState] = useState<State<T>>({ data: undefined, error: '', loading: true })

  const onError = useCallback(
    (err: unknown) => {
      if (err instanceof ApiError && err.status === 401) logout()
      setState((s) => ({
        ...s,
        loading: false,
        error: err instanceof Error ? err.message : 'Не удалось загрузить данные',
      }))
    },
    [logout],
  )

  useEffect(() => {
    let cancelled = false
    load().then(
      (data) => !cancelled && setState({ data, error: '', loading: false }),
      (err) => !cancelled && onError(err),
    )
    return () => {
      cancelled = true
    }
  }, [load, onError])

  const reload = useCallback(
    () => load().then((data) => setState({ data, error: '', loading: false }), onError),
    [load, onError],
  )
  const setData = useCallback((data: T) => setState((s) => ({ ...s, data })), [])

  return { ...state, reload, setData }
}
