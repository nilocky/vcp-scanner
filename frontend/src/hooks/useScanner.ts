import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { VCPAssessment, VCPResult } from '../types'

export interface Filters {
  minContractions: number
  minTightness: number // max final depth_pct accepted (lower = tighter)
  minAiScore: number
  includePremature: boolean
}

export const defaultFilters: Filters = {
  minContractions: 3,
  minTightness: 8,
  minAiScore: 0,
  includePremature: false,
}

export interface Row {
  symbol: string
  verdict: string
  contractions: number
  finalDepthPct: number
  volumeDryup: number | null
  pivot: number | null
  stop: number | null
  aiScore: number | null
  riskReward: number | null
}

export function useScanner() {
  const [rows, setRows] = useState<Row[]>([])
  const [aiEnabled, setAiEnabled] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(async (filters: Filters) => {
    setLoading(true)
    setError(null)
    try {
      let ai: VCPAssessment[] = []
      try {
        ai = (await api.aiScan()).results
        setAiEnabled(true)
      } catch {
        setAiEnabled(false) // no LLM key -> fall back to rule-based scan
      }
      const scan = await api.scan(filters.includePremature)
      const bySymbol = new Map(ai.map((a) => [a.ticker, a]))

      const filtered = scan.results
        .filter((r: VCPResult) => {
          const last = r.contractions[r.contractions.length - 1]
          return (
            r.contractions.length >= filters.minContractions &&
            (!last || last.depth_pct <= filters.minTightness) &&
            (!bySymbol.has(r.symbol) ||
              (bySymbol.get(r.symbol)!.vcp_confidence_score ?? 0) >=
                filters.minAiScore)
          )
        })
        .map((r: VCPResult): Row => {
          const a = bySymbol.get(r.symbol)
          const last = r.contractions[r.contractions.length - 1]
          return {
            symbol: r.symbol,
            verdict: r.verdict,
            contractions: r.contractions.length,
            finalDepthPct: last?.depth_pct ?? NaN,
            volumeDryup: r.volume_dryup_ratio,
            pivot: r.pivot_buy_price,
            stop: r.stop_loss,
            aiScore: a?.vcp_confidence_score ?? null,
            riskReward: a?.risk_reward_ratio ?? null,
          }
        })

      filtered.sort((x, y) => {
        const xs = x.aiScore ?? -1
        const ys = y.aiScore ?? -1
        return xs !== ys ? ys - xs : x.finalDepthPct - y.finalDepthPct
      })

      setRows(filtered)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    run(defaultFilters)
  }, [run])

  return { rows, loading, error, aiEnabled, run }
}
