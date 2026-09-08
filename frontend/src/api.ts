import type {
  HistoryResponse,
  VCPScanResponse,
  VCPResult,
  VCPAssessment,
  VLIAssessmentResponse,
} from './types'
import type { Filters } from './hooks/useScanner'

const base = '/api/v1'

export interface SavedScan {
  id: number
  name: string
  filters: Filters
  created_at: number
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base}${path}`, init)
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body && typeof body.detail === 'string') detail = body.detail
    } catch {
      // non-JSON error body; keep the HTTP status
    }
    throw new Error(`${path}: ${detail}`)
  }
  return res.json() as Promise<T>
}

const get = <T>(path: string) => request<T>(path)
const post = <T>(path: string, body: unknown) =>
  request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
const del = <T>(path: string) => request<T>(path, { method: 'DELETE' })

export const api = {
  scan: (includePremature = false) =>
    get<VCPScanResponse>(
      includePremature ? '/vcp/scan?include_premature=true' : '/vcp/scan',
    ),
  watchlist: () => get<VCPScanResponse>('/watchlist'),
  aiScan: () => get<VLIAssessmentResponse>('/vcp/ai/scan'),
  history: (symbol: string) =>
    get<HistoryResponse>(`/history/${encodeURIComponent(symbol)}`),
  vcp: (symbol: string) =>
    get<VCPResult>(`/vcp/${encodeURIComponent(symbol)}`),
  ai: (symbol: string) =>
    get<VCPAssessment>(`/vcp/ai/${encodeURIComponent(symbol)}`),
  listScans: () => get<SavedScan[]>('/scans'),
  saveScan: (name: string, filters: Filters) =>
    post<SavedScan>('/scans', { name, filters }),
  deleteScan: (id: number) => del<{ ok: boolean }>(`/scans/${id}`),
}
