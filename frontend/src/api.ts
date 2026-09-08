import type {
  HistoryResponse,
  VCPScanResponse,
  VCPResult,
  VCPAssessment,
  VLIAssessmentResponse,
} from './types'

const base = '/api/v1'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${base}${path}`)
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
  return res.json() as Promise<T>
}

export const api = {
  scan: (includePremature = false) =>
    get<VCPScanResponse>(
      includePremature ? '/vcp/scan?include_premature=true' : '/vcp/scan',
    ),
  aiScan: () => get<VLIAssessmentResponse>('/vcp/ai/scan'),
  history: (symbol: string) =>
    get<HistoryResponse>(`/history/${encodeURIComponent(symbol)}`),
  vcp: (symbol: string) =>
    get<VCPResult>(`/vcp/${encodeURIComponent(symbol)}`),
  ai: (symbol: string) =>
    get<VCPAssessment>(`/vcp/ai/${encodeURIComponent(symbol)}`),
}
