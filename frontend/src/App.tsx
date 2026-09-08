import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { AiDrawer } from './components/AiDrawer'
import { CandidateTable } from './components/CandidateTable'
import { ChartViewer } from './components/ChartViewer'
import { FilterBar } from './components/FilterBar'
import { useScanner } from './hooks/useScanner'
import type { Bar, VCPAssessment, VCPResult } from './types'

export default function App() {
  const { rows, loading, error, aiEnabled, run } = useScanner()
  const [selected, setSelected] = useState<string | null>(null)
  const [bars, setBars] = useState<Bar[]>([])
  const [vcp, setVcp] = useState<VCPResult | null>(null)
  const [assessment, setAssessment] = useState<VCPAssessment | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  const select = useCallback(async (symbol: string) => {
    setSelected(symbol)
    setBars([])
    setVcp(null)
    setAssessment(null)
    setDetailLoading(true)
    setDetailError(null)
    try {
      const [h, v, a] = await Promise.all([
        api.history(symbol),
        api.vcp(symbol),
        api.ai(symbol).catch(() => null),
      ])
      setBars(h.bars)
      setVcp(v)
      setAssessment(a)
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : String(e))
    } finally {
      setDetailLoading(false)
    }
  }, [])

  useEffect(() => {
    if (rows.length > 0 && !selected) select(rows[0].symbol)
  }, [rows, selected, select])

  return (
    <div className="flex h-screen flex-col bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 p-4">
        <h1 className="text-xl font-bold">VCP Scanner</h1>
        <p className="text-xs text-slate-500">
          Minervini Trend Template · Volatility Contraction Patterns
        </p>
      </header>

      <FilterBar aiEnabled={aiEnabled} loading={loading} onScan={run} />

      {error && (
        <div className="border-b border-red-900 bg-red-950/50 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <div className="flex w-1/2 min-w-0 flex-col border-r border-slate-800">
          <CandidateTable
            rows={rows}
            selected={selected}
            aiEnabled={aiEnabled}
            onSelect={select}
          />
        </div>
        <div className="flex w-1/2 min-w-0 flex-col">
          <div className="flex items-center justify-between p-3">
            <h2 className="text-sm font-semibold text-slate-300">
              {selected ?? 'Select a symbol'}
            </h2>
            {detailLoading && <span className="text-xs text-slate-500">Loading…</span>}
          </div>
          <div className="flex-1 overflow-auto p-3">
            {detailError && <p className="text-red-400">{detailError}</p>}
            <ChartViewer bars={bars} vcp={vcp} />
          </div>
        </div>
      </div>

      <AiDrawer
        symbol={selected}
        assessment={assessment}
        loading={detailLoading && !assessment}
        error={detailError}
        onClose={() => setSelected(null)}
      />
    </div>
  )
}