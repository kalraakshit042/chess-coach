import { formatEstimatedTime } from '../utils/api'

const VERDICT_BORDER = {
  Strong: 'border-l-green-600',
  'Needs Work': 'border-l-yellow-600',
  Weak: 'border-l-red-600',
}

export default function OpeningOverviewCard({ opening, verdict, onAnalyse }) {
  const { name, eco, games, wins, draws, losses, avg_opponent_rating, estimated_analysis_seconds } = opening

  const total = wins + draws + losses
  const winPct  = total > 0 ? Math.round((wins  / total) * 100) : 0
  const drawPct = total > 0 ? Math.round((draws / total) * 100) : 0
  const lossPct = total > 0 ? 100 - winPct - drawPct : 0

  const isCached = estimated_analysis_seconds === 0
  const estLabel = formatEstimatedTime(estimated_analysis_seconds)
  const borderColor = VERDICT_BORDER[verdict] || 'border-l-chess-border'

  return (
    <div className={`card border-l-4 ${borderColor} p-5 flex flex-col gap-4 transition-colors`}>
      {/* Header: ECO badge + name + game count */}
      <div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-chess-accent/20 text-chess-accent border border-chess-accent/30">
            {eco}
          </span>
          <h3 className="text-white font-medium text-sm leading-snug">{name}</h3>
        </div>
        <p className="text-chess-muted text-xs mt-1">{games} game{games !== 1 ? 's' : ''}</p>
      </div>

      {/* W/D/L bar + win% */}
      <div>
        <div className="flex items-center gap-3">
          <div className="flex-1 flex h-2.5 rounded-full overflow-hidden">
            {winPct > 0 && (
              <div className="bg-green-500 transition-all" style={{ width: `${winPct}%` }} />
            )}
            {drawPct > 0 && (
              <div className="bg-chess-muted transition-all" style={{ width: `${drawPct}%` }} />
            )}
            {lossPct > 0 && (
              <div className="bg-red-500 transition-all" style={{ width: `${lossPct}%` }} />
            )}
          </div>
          <span className="text-white font-bold text-sm tabular-nums w-10 text-right flex-shrink-0">
            {winPct}%
          </span>
        </div>
        <div className="flex gap-3 mt-1.5 text-xs text-chess-muted">
          <span className="text-green-400">{winPct}% W</span>
          <span>{drawPct}% D</span>
          <span className="text-red-400">{lossPct}% L</span>
        </div>
      </div>

      {/* Footer: avg rating + time estimate + button */}
      <div className="flex items-center justify-between gap-3 pt-1 border-t border-chess-border">
        <div className="text-xs text-chess-muted">
          {avg_opponent_rating
            ? <>Avg opp: <span className="text-chess-text">{Math.round(avg_opponent_rating)}</span></>
            : <span className="italic">No rating data</span>
          }
        </div>
        <div className="flex items-center gap-2">
          {!isCached && (
            <span className="text-xs text-chess-muted">{estLabel}</span>
          )}
          <button
            onClick={() => onAnalyse(opening)}
            className="btn-primary text-xs py-1.5 px-3"
          >
            {isCached ? 'View Analysis' : 'Analyse'}
          </button>
        </div>
      </div>
    </div>
  )
}
