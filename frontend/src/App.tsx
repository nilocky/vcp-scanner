import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { AiDrawer } from './components/AiDrawer'
import { CandidateTable } from './components/CandidateTable'
import { ChartViewer } from './components/ChartViewer'
import { FilterBar } from './components/FilterBar'
import { useScanner } from './hooks/useScanner'
import type { Bar, VCPAssessment, VCPResult } from './types'

export default function App() {
  const {
    rows,
    loading,
    error,
    aiEnabled,
    run,
    savedScans,
    applySaved,
    loadSavedScans,
  } = useScanner()
  const [selected, setSelected] = useState<string | null>(null)
  const [bars, setBars] = useState<Bar[]>([])
  const [vcp, setVcp] = useState<VCPResult | null>(null)
  const [assessment, setAssessment] = useState<VCPAssessment | null>(null)
  const [aiError, setAiError] = useState<string | null>(null)
  const [aiOpen, setAiOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  const select = useCallback(async (symbol: string) => {
    setSelected(symbol)
    setBars([])
    setVcp(null)
    setAssessment(null)
    setAiError(null)
    setDetailLoading(true)
    setDetailError(null)
    try {
      const [h, v, a] = await Promise.all([
        api.history(symbol),
        api.vcp(symbol),
        api.ai(symbol).catch((e: unknown) => {
          setAiError(e instanceof Error ? e.message : String(e))
          return null
        }),
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

      <FilterBar
        aiEnabled={aiEnabled}
        loading={loading}
        savedScans={savedScans}
        onScan={run}
        onSave={async (name, f) => {
          await api.saveScan(name, f)
          loadSavedScans()
        }}
        onLoad={applySaved}
      />

      {error && (
        <div className="border-b border-red-900 bg-red-950/50 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <div className="flex w-1/2 min-w-0 flex-col border-r border-slate-800">
          <div className="border-b border-slate-800 px-4 py-2 text-xs text-slate-500">
            {rows.length} candidate{rows.length === 1 ? '' : 's'}
          </div>
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
            <div className="flex items-center gap-2">
              {detailLoading && <span className="text-xs text-slate-500">Loading…</span>}
              {selected && (
                <button
                  onClick={() => setAiOpen(true)}
                  className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300 hover:bg-slate-700"
                >
                  AI Thesis
                </button>
              )}
            </div>
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
        error={aiError}
        open={aiOpen}
        onClose={() => setAiOpen(false)}
      />
    </div>
  )
}