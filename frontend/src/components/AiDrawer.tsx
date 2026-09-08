import type { VCPAssessment } from '../types'

interface Props {
  symbol: string | null
  assessment: VCPAssessment | null
  loading: boolean
  error: string | null
  onClose: () => void
}

export function AiDrawer({ symbol, assessment, loading, error, onClose }: Props) {
  return (
    <div
      className={`fixed inset-y-0 right-0 z-20 w-full max-w-md transform border-l border-slate-800 bg-slate-900 transition-transform ${
        symbol ? 'translate-x-0' : 'translate-x-full'
      }`}
    >
      <div className="flex items-center justify-between border-b border-slate-800 p-4">
        <h2 className="text-lg font-semibold text-slate-100">
          {symbol ? `${symbol} — AI Thesis` : ''}
        </h2>
        <button
          onClick={onClose}
          className="rounded bg-slate-800 px-2 py-1 text-sm text-slate-300 hover:bg-slate-700"
        >
          ✕
        </button>
      </div>

      <div className="overflow-y-auto p-4">
        {loading && <p className="text-slate-400">Evaluating…</p>}
        {error && <p className="text-red-400">{error}</p>}
        {!loading && !error && assessment && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-400">Confidence</span>
              <span
                className={`rounded px-2 py-1 text-lg font-bold ${
                  assessment.vcp_confidence_score >= 70
                    ? 'bg-emerald-900 text-emerald-300'
                    : assessment.vcp_confidence_score >= 50
                      ? 'bg-amber-900 text-amber-300'
                      : 'bg-red-900 text-red-300'
                }`}
              >
                {assessment.vcp_confidence_score}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="rounded bg-slate-800 p-3">
                <div className="text-xs text-slate-400">Base type</div>
                <div className="text-slate-100">{assessment.base_type}</div>
              </div>
              <div className="rounded bg-slate-800 p-3">
                <div className="text-xs text-slate-400">Verdict</div>
                <div className="text-slate-100">{assessment.verdict}</div>
              </div>
              <div className="rounded bg-slate-800 p-3">
                <div className="text-xs text-slate-400">Buy pivot</div>
                <div className="text-slate-100">
                  {assessment.pivot_buy_price.toFixed(2)}
                </div>
              </div>
              <div className="rounded bg-slate-800 p-3">
                <div className="text-xs text-slate-400">Stop loss</div>
                <div className="text-slate-100">
                  {assessment.suggested_stop_loss.toFixed(2)}
                </div>
              </div>
            </div>

            <div className="rounded bg-slate-800 p-3 text-sm">
              <div className="text-xs text-slate-400">Risk / Reward</div>
              <div className="text-slate-100">
                {assessment.risk_reward_ratio.toFixed(2)} : 1
              </div>
            </div>

            <div>
              <div className="mb-1 text-xs text-slate-400">Volume dry-up</div>
              <div className="text-sm text-slate-100">
                {assessment.volume_dryup_confirmed ? 'Confirmed' : 'Not confirmed'}
              </div>
            </div>

            <div>
              <div className="mb-1 text-xs text-slate-400">Contraction stages</div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-400">
                    <th className="py-1">Stage</th>
                    <th className="py-1">Depth</th>
                    <th className="py-1">Days</th>
                  </tr>
                </thead>
                <tbody>
                  {assessment.contraction_stages.map((s) => (
                    <tr key={s.stage} className="border-t border-slate-800">
                      <td className="py-1 text-slate-100">{s.stage}</td>
                      <td className="py-1 text-slate-100">{s.depth_pct.toFixed(1)}%</td>
                      <td className="py-1 text-slate-100">{s.days}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="rounded border border-slate-700 bg-slate-800/50 p-3">
              <div className="mb-1 text-xs text-slate-400">AI commentary</div>
              <p className="whitespace-pre-wrap text-sm text-slate-200">
                {assessment.ai_commentary}
              </p>
            </div>
          </div>
        )}
        {!loading && !error && !assessment && symbol && (
          <p className="text-slate-400">No AI assessment available (LLM key may be unset).</p>
        )}
      </div>
    </div>
  )
}