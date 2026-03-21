import { useState } from 'react'
import { getVerdictClass } from '../utils/api'
import ChessBoard, { PositionBoard } from './ChessBoard'

export default function OpeningCard({ opening }) {
  const [expanded, setExpanded] = useState(false)
  const {
    stats, verdict, verdict_color,
    accuracy_summary, tactical_summary, positional_summary, recommendation,
    key_positions, key_moments, resources, avg_centipawn_loss,
  } = opening

  const verdictClass = getVerdictClass(verdict)
  const total = stats.games
  const winPct  = total > 0 ? Math.round((stats.wins   / total) * 100) : 0
  const drawPct = total > 0 ? Math.round((stats.draws  / total) * 100) : 0
  const lossPct = total > 0 ? Math.round((stats.losses / total) * 100) : 0

  // Use key_moments (Claude-annotated) first, fall back to key_positions (Stockfish only)
  const hasKeyMoments = key_moments && key_moments.length > 0
  const hasFallbackPositions = key_positions && key_positions.length > 0

  return (
    <div className="card overflow-hidden transition-all duration-200 hover:border-chess-muted">
      {/* Header */}
      <button
        className="w-full text-left px-5 py-4 flex items-start gap-4"
        onClick={() => setExpanded(v => !v)}
      >
        {/* ECO badge */}
        <div className="flex-shrink-0 w-12 h-12 bg-chess-bg rounded-lg flex items-center justify-center
                        border border-chess-border font-mono text-xs font-semibold text-chess-accent">
          {stats.eco !== '?' ? stats.eco.slice(0, 3) : '?'}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-white font-semibold text-sm leading-tight truncate">{stats.name}</h3>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${verdictClass}`}>
              {verdict}
            </span>
          </div>

          <div className="mt-1.5 flex items-center gap-3 flex-wrap">
            <span className="text-xs text-chess-muted">{stats.games} games</span>
            <WinBar wins={stats.wins} draws={stats.draws} losses={stats.losses} />
            <span className="text-xs text-green-400">{winPct}%W</span>
            <span className="text-xs text-chess-muted">{drawPct}%D</span>
            <span className="text-xs text-red-400">{lossPct}%L</span>
            {stats.avg_opponent_rating && (
              <span className="text-xs text-chess-muted">
                avg opp: <span className="text-chess-text">{Math.round(stats.avg_opponent_rating)}</span>
              </span>
            )}
            {avg_centipawn_loss != null && (
              <span className="text-xs text-chess-muted">
                ACPL: <span className={acplColor(avg_centipawn_loss)}>{Math.round(avg_centipawn_loss)}</span>
              </span>
            )}
          </div>
        </div>

        <div className={`flex-shrink-0 text-chess-muted transition-transform duration-200 mt-1 ${expanded ? 'rotate-180' : ''}`}>
          <ChevronIcon />
        </div>
      </button>

      {/* Expandable content */}
      {expanded && (
        <div className="border-t border-chess-border px-5 py-4 space-y-5">

          {/* Analysis text */}
          <AnalysisSection icon="🎯" label="Accuracy"   text={accuracy_summary} />
          <AnalysisSection icon="⚡" label="Tactics"    text={tactical_summary} />
          <AnalysisSection icon="♟" label="Positional"  text={positional_summary} />

          {/* Recommendation */}
          <div className="bg-chess-bg rounded-lg p-4 border-l-2 border-chess-accent">
            <div className="text-xs font-semibold text-chess-accent uppercase tracking-wider mb-1.5">
              Recommendation
            </div>
            <p className="text-sm text-chess-text leading-relaxed">{recommendation}</p>
          </div>

          {/* Key Moments — Claude-annotated positions with boards */}
          {hasKeyMoments && (
            <div>
              <div className="text-xs font-semibold text-chess-accent uppercase tracking-wider mb-3">
                Key Positions
              </div>
              <div className="space-y-4">
                {key_moments.map((km, i) => (
                  <KeyMomentCard key={i} moment={km} />
                ))}
              </div>
            </div>
          )}

          {/* Fallback: Stockfish-only positions (no Claude annotation) */}
          {!hasKeyMoments && hasFallbackPositions && (
            <ChessBoard positions={key_positions} />
          )}

          {/* Resources */}
          {resources && resources.length > 0 && (
            <ResourcesSection resources={resources} />
          )}
        </div>
      )}
    </div>
  )
}

function KeyMomentCard({ moment }) {
  const { game_url, move_number, fen, move_played, better_move, explanation, eval_swing } = moment

  // Only render if we have a valid FEN
  if (!fen) {
    return (
      <div className="bg-chess-bg rounded-lg border border-chess-border p-4">
        <div className="flex items-start justify-between gap-3 mb-2">
          <span className="text-xs text-chess-muted">Move {move_number}</span>
          {game_url && (
            <a href={game_url} target="_blank" rel="noopener noreferrer"
               className="text-xs text-chess-accent hover:underline">
              View game ↗
            </a>
          )}
        </div>
        <p className="text-sm text-chess-text leading-relaxed">{explanation}</p>
        {(move_played || better_move) && (
          <div className="mt-2 flex gap-4 text-xs font-mono">
            {move_played && <span className="text-red-400">Played: {move_played}</span>}
            {better_move && <span className="text-green-400">Better: {better_move}</span>}
          </div>
        )}
      </div>
    )
  }

  return (
    <PositionBoard
      fen={fen}
      movePlayed={move_played}
      betterMove={better_move}
      gameUrl={game_url}
      explanation={explanation}
      moveNumber={move_number}
      evalSwing={eval_swing}
    />
  )
}

function ResourcesSection({ resources }) {
  const icons = { lichess: '♞', youtube: '▶', book: '📖' }
  const colors = {
    lichess: 'text-chess-accent border-chess-border hover:border-chess-accent',
    youtube: 'text-red-400 border-chess-border hover:border-red-700',
    book:    'text-blue-400 border-chess-border hover:border-blue-700',
  }

  return (
    <div>
      <div className="text-xs font-semibold text-chess-accent uppercase tracking-wider mb-3">
        Study Resources
      </div>
      <div className="flex flex-wrap gap-2">
        {resources.map((r, i) => (
          <a
            key={i}
            href={r.url}
            target="_blank"
            rel="noopener noreferrer"
            className={`flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg border
                        bg-chess-bg transition-colors duration-150 ${colors[r.resource_type] || colors.lichess}`}
          >
            <span>{icons[r.resource_type] || '🔗'}</span>
            <span>{r.title}</span>
          </a>
        ))}
      </div>
    </div>
  )
}

function AnalysisSection({ icon, label, text }) {
  if (!text) return null
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-sm">{icon}</span>
        <span className="text-xs font-semibold text-chess-accent uppercase tracking-wider">{label}</span>
      </div>
      <p className="text-sm text-chess-text leading-relaxed pl-5">{text}</p>
    </div>
  )
}

function WinBar({ wins, draws, losses }) {
  const total = wins + draws + losses
  if (total === 0) return null
  const wPct = (wins  / total) * 100
  const dPct = (draws / total) * 100
  const lPct = (losses/ total) * 100
  return (
    <div className="flex h-1.5 w-20 rounded-full overflow-hidden bg-chess-muted gap-px">
      {wPct > 0 && <div className="bg-green-500" style={{ width: `${wPct}%` }} />}
      {dPct > 0 && <div className="bg-chess-text" style={{ width: `${dPct}%` }} />}
      {lPct > 0 && <div className="bg-red-500"   style={{ width: `${lPct}%` }} />}
    </div>
  )
}

function acplColor(acpl) {
  if (acpl < 30) return 'text-green-400'
  if (acpl < 60) return 'text-yellow-400'
  return 'text-red-400'
}

function ChevronIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}
