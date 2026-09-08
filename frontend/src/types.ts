export interface Contraction {
  peak_ts: number
  trough_ts: number
  depth_pct: number
  days: number
}

export interface VCPResult {
  symbol: string
  contractions: Contraction[]
  volume_dryup_ratio: number | null
  pivot_buy_price: number | null
  stop_loss: number | null
  verdict: string
  relative_volume?: number | null
  pct_off_52w_high?: number | null
  rs?: number | null
}

export interface VCPScanResponse {
  scanned: number
  qualified: number
  results: VCPResult[]
}

export interface ContractionStage {
  stage: string
  depth_pct: number
  days: number
}

export interface VCPAssessment {
  ticker: string
  vcp_confidence_score: number
  base_type: string
  contraction_stages: ContractionStage[]
  volume_dryup_confirmed: boolean
  pivot_buy_price: number
  suggested_stop_loss: number
  risk_reward_ratio: number
  verdict: string
  ai_commentary: string
}

export interface VLIAssessmentResponse {
  scanned: number
  results: VCPAssessment[]
}

export interface Bar {
  ts: number
  open: number
  high: number
  low: number
  close: number
  volume: number | null
}

export interface HistoryResponse {
  symbol: string
  count: number
  bars: Bar[]
}
