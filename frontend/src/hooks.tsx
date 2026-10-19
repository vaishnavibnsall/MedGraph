import { useEffect, useState } from 'react'

interface State<T> {
  data: T | null
  loading: boolean
  error: string | null
}

/** Minimal async data hook with loading/error handling. */
export function useFetch<T>(fn: () => Promise<T>, deps: unknown[] = []): State<T> {
  const [state, setState] = useState<State<T>>({ data: null, loading: true, error: null })
  useEffect(() => {
    let cancelled = false
    setState((s) => ({ ...s, loading: true, error: null }))
    fn()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null })
      })
      .catch((e: Error) => {
        if (!cancelled) setState({ data: null, loading: false, error: e.message })
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return state
}

export function Loading() {
  return <div className="loading">Loading…</div>
}

export function ErrorBox({ msg }: { msg: string }) {
  return <div className="error">Failed to load: {msg}</div>
}
