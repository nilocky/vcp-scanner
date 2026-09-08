import { useState } from 'react'
import type { Row } from '../hooks/useScanner'

interface Props {
  rows: Row[]
  selected: string | null
  aiEnabled: boolean
  onSelect: (symbol: string) => void
}

type SortKey = keyof Row
type SortDir = 'asc' | 'desc'

const SORTABLE: { key: SortKey; label: string }[] = [
  { key: 'symbol', label: 'Symbol' },
  { key: 'verdict', label: 'Status' },
  { key: 'contractions', label: 'Contractions' },
  { key: 'finalDepthPct', label: 'Final depth' },
  { key: 'volumeDryup', label: 'Vol dry-up' },
  { key: 'pivot', label: 'Pivot' },
  { key: 'stop', label: 'Stop' },
  { key: 'rs', label: 'RS' },
  { key: 'relativeVolume', label: 'Vol buzz' },
  { key: 'pctOffHigh', label: '% off high' },
  { key: 'aiScore', label: 'Confidence' },
]

function pct(v: number | null) {
  return v == null ? '—' : `${(v * 100).toFixed(0)}%`
}

function num(v: number | null | undefined, digits = 2) {
  return v == null || Number.isNaN(v) ? '—' : v.toFixed(digits)
}

function sortValue(v: unknown): number | string {
  if (v == null || (typeof v === 'number' && Number.isNaN(v))) return Number.NEGATIVE_INFINITY
  return v as number | string
}

export function CandidateTable({ rows, selected, aiEnabled, onSelect }: Props) {
  const [sortKey, setSortKey] = useState<SortKey | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir(key === 'symbol' || key === 'verdict' ? 'asc' : 'desc')
    }
  }

  const sorted = sortKey
    ? [...rows].sort((a, b) => {
        const av = sortValue(a[sortKey])
        const bv = sortValue(b[sortKey])
        const cmp =
          typeof av === 'string' && typeof bv === 'string'
            ? av.localeCompare(bv)
            : (av as number) - (bv as number)
        return sortDir === 'asc' ? cmp : -cmp
      })
    : rows

  const indicator = (key: SortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''

  const Th = ({ col }: { col: { key: SortKey; label: string } }) => (
    <th className="px-3 py-2">
      <button
        type="button"
        onClick={() => toggleSort(col.key)}
        className={`font-semibold hover:text-slate-200 ${sortKey === col.key ? 'text-slate-200' : ''}`}
      >
        {col.label}
        {indicator(col.key)}
      </button>
    </th>
  )

  return (
    <div className="overflow-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="sticky top-0 border-b border-slate-800 bg-slate-900 text-left text-xs text-slate-400">
            {SORTABLE.map((col) => (
              <Th key={col.key} col={col} />
            ))}
            {aiEnabled && (
              <th className="px-3 py-2">
                <button
                  type="button"
                  onClick={() => toggleSort('riskReward')}
                  className={`font-semibold hover:text-slate-200 ${sortKey === 'riskReward' ? 'text-slate-200' : ''}`}
                >
                  R/R
                  {indicator('riskReward')}
                </button>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr
              key={r.symbol}
              onClick={() => onSelect(r.symbol)}
              className={`cursor-pointer border-b border-slate-800/50 hover:bg-slate-800/50 ${
                selected === r.symbol ? 'bg-slate-800' : ''
              } ${r.verdict === 'PREMATURE' ? 'opacity-70' : ''}`}
            >
              <td className="px-3 py-2 font-semibold text-emerald-400">
                {r.symbol}
              </td>
              <td className="px-3 py-2">
                {r.verdict === 'PREMATURE' ? (
                  <span className="rounded bg-amber-900 px-1.5 py-0.5 text-xs font-semibold text-amber-300">
                    watch
                  </span>
                ) : (
                  <span className="rounded bg-emerald-900 px-1.5 py-0.5 text-xs font-semibold text-emerald-300">
                    setup
                  </span>
                )}
              </td>
              <td className="px-3 py-2">{r.contractions}</td>
              <td className="px-3 py-2">{num(r.finalDepthPct, 1)}%</td>
              <td className="px-3 py-2">{pct(r.volumeDryup)}</td>
              <td className="px-3 py-2">{num(r.pivot)}</td>
              <td className="px-3 py-2">{num(r.stop)}</td>
              <td className="px-3 py-2">{num(r.rs, 0)}</td>
              <td className="px-3 py-2">
                {r.relativeVolume == null ? '—' : `${r.relativeVolume.toFixed(1)}x`}
              </td>
              <td className="px-3 py-2">{pct(r.pctOffHigh)}</td>
              <td className="px-3 py-2">
                {r.aiScore == null ? '—' : (
                  <span
                    className={`rounded px-1.5 py-0.5 text-xs font-semibold ${
                      r.aiScore >= 70
                        ? 'bg-emerald-900 text-emerald-300'
                        : r.aiScore >= 50
                          ? 'bg-amber-900 text-amber-300'
                          : 'bg-red-900 text-red-300'
                    }`}
                  >
                    {r.aiScore}
                  </span>
                )}
              </td>
              {aiEnabled && <td className="px-3 py-2">{num(r.riskReward, 1)}</td>}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td
                colSpan={aiEnabled ? 12 : 11}
                className="px-3 py-8 text-center text-slate-500"
              >
                No candidates match the current filters.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}