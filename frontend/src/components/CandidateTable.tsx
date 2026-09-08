import type { Row } from '../hooks/useScanner'

interface Props {
  rows: Row[]
  selected: string | null
  aiEnabled: boolean
  onSelect: (symbol: string) => void
}

function pct(v: number | null) {
  return v == null ? '—' : `${(v * 100).toFixed(0)}%`
}

function num(v: number | null | undefined, digits = 2) {
  return v == null || Number.isNaN(v) ? '—' : v.toFixed(digits)
}

export function CandidateTable({ rows, selected, aiEnabled, onSelect }: Props) {
  return (
    <div className="overflow-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="sticky top-0 border-b border-slate-800 bg-slate-900 text-left text-xs text-slate-400">
            <th className="px-3 py-2">Symbol</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Contractions</th>
            <th className="px-3 py-2">Final depth</th>
            <th className="px-3 py-2">Vol dry-up</th>
            <th className="px-3 py-2">Pivot</th>
            <th className="px-3 py-2">Stop</th>
            {aiEnabled && (
              <>
                <th className="px-3 py-2">AI</th>
                <th className="px-3 py-2">R/R</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
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
              {aiEnabled && (
                <>
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
                  <td className="px-3 py-2">{num(r.riskReward, 1)}</td>
                </>
              )}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td
                colSpan={aiEnabled ? 9 : 7}
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
