import axios, { AxiosError } from 'axios'

/**
 * Relative baseURL: the Vite dev server proxies /api to uvicorn, and in
 * production the app is served behind the same origin as the API.
 */
export const api = axios.create({
  baseURL: '/api',
  timeout: 15_000,
})

/** FastAPI puts error bodies under `detail` — as a string, or our structured object. */
export function apiErrorMessage(error: unknown): string {
  if (error instanceof AxiosError) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (detail && typeof detail === 'object' && 'message' in detail) {
      return String((detail as { message: unknown }).message)
    }
    // Pydantic validation errors arrive as a list of per-field objects.
    if (Array.isArray(detail) && detail.length > 0) {
      return detail
        .map((d: { loc?: unknown[]; msg?: string }) =>
          d.loc ? `${d.loc.slice(1).join('.')}: ${d.msg ?? ''}` : (d.msg ?? '')
        )
        .join('; ')
    }
    return error.message
  }
  return error instanceof Error ? error.message : 'Unknown error'
}
