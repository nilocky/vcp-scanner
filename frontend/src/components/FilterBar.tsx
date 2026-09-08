import { useState } from 'react'
import type { Filters } from '../hooks/useScanner'

interface Props {
  aiEnabled: boolean
  loading: boolean
  onScan: (f: Filters) => void
}

export function FilterBar({ aiEnabled, loading, onScan }: Props) {
  const [minContractions, setMinContractions] = useState(3)
  const [minTightness, setMinTightness] = useState(8)
  const [minAiScore, setMinAiScore] = useState(0)
  const [includePremature, setIncludePremature] = useState(false)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    onScan({ minContractions, minTightness, minAiScore, includePremature })
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-wrap items-end gap-4 border-b border-slate-800 p-4"
    >
      <label className="flex flex-col text-xs text-slate-400">
        Min contractions
        <input
          type="number"
          min={2}
          max={6}
          value={minContractions}
          onChange={(e) => setMinContractions(+e.target.value)}
          className="mt-1 w-24 rounded bg-slate-800 px-2 py-1 text-slate-100"
        />
      </label>
      <label className="flex flex-col text-xs text-slate-400">
        Max final depth %
        <input
          type="number"
          min={1}
          max={30}
          step={0.5}
          value={minTightness}
          onChange={(e) => setMinTightness(+e.target.value)}
          className="mt-1 w-24 rounded bg-slate-800 px-2 py-1 text-slate-100"
        />
      </label>
      {aiEnabled && (
<label className="flex flex-col text-xs text-slate-400">
        Min AI score
          <input
            type="number"
            min={0}
            max={100}
            value={minAiScore}
            onChange={(e) => setMinAiScore(+e.target.value)}
            className="mt-1 w-24 rounded bg-slate-800 px-2 py-1 text-slate-100"
          />
      </label>
      )}
      <label className="flex items-center gap-2 self-end pb-2 text-xs text-slate-400">
        <input
          type="checkbox"
          checked={includePremature}
          onChange={(e) => setIncludePremature(e.target.checked)}
          className="h-4 w-4 rounded accent-amber-500"
        />
        Watch list (premature)
      </label>
      <button
        type="submit"
        disabled={loading}
        className="rounded bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
      >
        {loading ? 'Scanning…' : 'Scan'}
      </button>
    </form>
  )
}
