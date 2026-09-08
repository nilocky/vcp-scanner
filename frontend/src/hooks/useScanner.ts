import { useCallback, useEffect, useState } from 'react'
import { api, type SavedScan } from '../api'
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
  rs: number | null
  relativeVolume: number | null
  pctOffHigh: number | null
}

function toRow(r: VCPResult, a?: VCPAssessment): Row {
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
    rs: r.rs ?? null,
    relativeVolume: r.relative_volume ?? null,
    pctOffHigh: r.pct_off_52w_high ?? null,
  }
}

async function fetchAi(symbols: string[]): Promise<Map<string, VCPAssessment>> {
  const map = new Map<string, VCPAssessment>()
  await Promise.allSettled(
    symbols.map(async (s) => {
      try {
        map.set(s, await api.ai(s))
      } catch {
        // no assessment available for this symbol
      }
    }),
  )
  return map
}

export function useScanner() {
  const [rows, setRows] = useState<Row[]>([])
  const [aiEnabled, setAiEnabled] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedScans, setSavedScans] = useState<SavedScan[]>([])

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

      const missing = filtered.filter((r) => !bySymbol.has(r.symbol)).map((r) => r.symbol)
      if (missing.length) {
        for (const [s, a] of await fetchAi(missing)) bySymbol.set(s, a)
        setAiEnabled(true)
      }

      const mapped = filtered.map((r: VCPResult): Row => toRow(r, bySymbol.get(r.symbol)))
      mapped.sort((x, y) => {
        const xs = x.aiScore ?? -1
        const ys = y.aiScore ?? -1
        return xs !== ys ? ys - xs : x.finalDepthPct - y.finalDepthPct
      })

      setRows(mapped)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  const loadWatchlist = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const watch = await api.watchlist()
      const bySymbol = await fetchAi(watch.results.map((r) => r.symbol))
      if (bySymbol.size > 0) setAiEnabled(true)
      const rows = watch.results
        .map((r) => toRow(r, bySymbol.get(r.symbol)))
        .sort((a, b) => a.finalDepthPct - b.finalDepthPct)
      setRows(rows)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadWatchlist()
  }, [loadWatchlist])

  const loadSavedScans = useCallback(async () => {
    try {
      setSavedScans(await api.listScans())
    } catch {
      // saved scans unavailable; leave the list empty
    }
  }, [])

  useEffect(() => {
    loadSavedScans()
  }, [loadSavedScans])

  const applySaved = useCallback(
    (filters: Filters) => {
      run(filters)
    },
    [run],
  )

  const removeScan = useCallback(async (id: number) => {
    try {
      await api.deleteScan(id)
      setSavedScans((prev) => prev.filter((s) => s.id !== id))
    } catch {
      // ignore delete failures
    }
  }, [])

  return {
    rows,
    loading,
    error,
    aiEnabled,
    run,
    loadWatchlist,
    savedScans,
    applySaved,
    loadSavedScans,
    removeScan,
  }
}
