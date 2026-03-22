import { useState } from 'react'
import { formatEstimatedTime } from '../utils/api'

function getVerdict(wins, draws, losses) {
  const total = wins + draws + losses
  if (total === 0) return 'Needs Work'
  const score = wins / total + (draws / total) * 0.5
  if (score >= 0.55) return 'Strong'
  if (score >= 0.40) return 'Needs Work'
  return 'Weak'
}

const SECTION_STYLES = {
  Strong:       { dot: 'bg-green-500',  label: 'text-green-400',  divider: 'border-green-900/40',  bar: 'bg-green-500' },
  'Needs Work': { dot: 'bg-yellow-500', label: 'text-yellow-400', divider: 'border-yellow-900/40', bar: 'bg-yellow-500' },
  Weak:         { dot: 'bg-red-500',    label: 'text-red-400',    divider: 'border-red-900/40',    bar: 'bg-red-500' },
}

function OpeningRow({ opening, verdict, onAnalyse }) {
  const { name, eco, games, wins, draws, losses, avg_opponent_rating, estimated_analysis_seconds } = opening
  const total = wins + draws + losses
  const winPct  = total > 0 ? Math.round((wins  / total) * 100) : 0
  const drawPct = total > 0 ? Math.round((draws / total) * 100) : 0
  const lossPct = total > 0 ? 100 - winPct - drawPct : 0
  const isCached = estimated_analysis_seconds === 0
  const s = SECTION_STYLES[verdict]

  // Build compact W/D/L label — skip zero values
  const parts = []
  if (winPct > 0)  parts.push(<span key="w" className="text-green-400">{winPct}%W</span>)
  if (drawPct > 0) parts.push(<span key="d" className="text-chess-muted">{drawPct}%D</span>)
  if (lossPct > 0) parts.push(<span key="l" className="text-red-400">{lossPct}%L</span>)

  return (
    <div className="flex items-center gap-3 py-3 px-4 rounded-lg bg-chess-surface border border-chess-border hover:border-chess-border/80 transition-colors">
      {/* ECO */}
      <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-chess-accent/20 text-chess-accent border border-chess-accent/30 flex-shrink-0">
        {eco}
      </span>

      {/* Name */}
      <span className="text-white text-sm font-medium flex-1 min-w-0 truncate">{name}</span>

      {/* Bar + win% */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <div className="flex h-1.5 w-20 rounded-full overflow-hidden bg-chess-muted/30">
          {winPct > 0  && <div className={`${s.bar} transition-all`} style={{ width: `${winPct}%` }} />}
          {drawPct > 0 && <div className="bg-chess-muted transition-all" style={{ width: `${drawPct}%` }} />}
          {lossPct > 0 && <div className="bg-red-500 transition-all" style={{ width: `${lossPct}%` }} />}
        </div>
        <span className="text-white font-bold text-sm tabular-nums w-9 text-right">{winPct}%</span>
      </div>

      {/* W/D/L labels (compact, skip zeros) */}
      <div className="hidden sm:flex items-center gap-1 text-xs flex-shrink-0 w-28">
        {parts.reduce((acc, el, i) => [...acc, i > 0 ? <span key={`sep-${i}`} className="text-chess-border">·</span> : null, el], [])}
      </div>

      {/* Games */}
      <span className="hidden md:block text-xs text-chess-muted flex-shrink-0 w-16 text-right">
        {games}g
      </span>

      {/* Avg opp rating */}
      {avg_opponent_rating && (
        <span className="hidden lg:block text-xs text-chess-muted flex-shrink-0 w-16 text-right">
          ≈{Math.round(avg_opponent_rating)}
        </span>
      )}

      {/* Time estimate + button */}
      <div className="flex items-center gap-2 flex-shrink-0">
        {!isCached && (
          <span className="hidden sm:block text-xs text-chess-muted">{formatEstimatedTime(estimated_analysis_seconds)}</span>
        )}
        <button
          onClick={() => onAnalyse(opening)}
          className="btn-primary text-xs py-1 px-3"
        >
          Analyse
        </button>
      </div>
    </div>
  )
}

const PAGE_SIZE = 10
const INITIAL = 3

function Section({ label, items, onAnalyse }) {
  const [visibleCount, setVisibleCount] = useState(INITIAL)
  const s = SECTION_STYLES[label]
  const visible = items.slice(0, visibleCount)
  const remaining = items.length - visibleCount

  return (
    <div>
      {/* Section header */}
      <div className={`flex items-center gap-2 mb-2 pb-2 border-b ${s.divider}`}>
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${s.dot}`} />
        <span className={`text-sm font-semibold ${s.label}`}>{label}</span>
        <span className="text-xs text-chess-muted">({items.length})</span>
      </div>

      {/* Rows */}
      <div className="flex flex-col gap-1.5">
        {visible.map(opening => (
          <OpeningRow
            key={opening.key}
            opening={opening}
            verdict={label}
            onAnalyse={onAnalyse}
          />
        ))}
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between mt-2">
        {visibleCount > INITIAL && (
          <button
            onClick={() => setVisibleCount(INITIAL)}
            className="text-xs text-chess-muted hover:text-chess-accent transition-colors py-1"
          >
            ↑ Show less
          </button>
        )}
        {remaining > 0 && (
          <button
            onClick={() => setVisibleCount(v => Math.min(v + PAGE_SIZE, items.length))}
            className="text-xs text-chess-muted hover:text-chess-accent transition-colors py-1 ml-auto"
          >
            ↓ Show {Math.min(PAGE_SIZE, remaining)} more
          </button>
        )}
      </div>
    </div>
  )
}

export default function OverviewPage({ data, onAnalyse, onReset }) {
  const [tab, setTab] = useState('white')

  const { username, total_games, white_games, black_games, white_openings, black_openings, user_rating } = data
  const openings = tab === 'white' ? white_openings : black_openings

  // Sort by games desc within each verdict group
  const byVerdict = { Strong: [], 'Needs Work': [], Weak: [] }
  for (const o of openings) {
    byVerdict[getVerdict(o.wins, o.draws, o.losses)].push(o)
  }

  const sections = ['Strong', 'Needs Work', 'Weak']
    .filter(v => byVerdict[v].length > 0)
    .map(v => ({ label: v, items: byVerdict[v] }))

  return (
    <div className="min-h-screen px-4 py-10">
      <div className="max-w-3xl mx-auto">

        {/* Header */}
        <div className="flex items-start justify-between mb-8 flex-wrap gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-2xl select-none">♞</span>
              <h1 className="text-2xl font-bold text-white">{username}</h1>
              {user_rating && (
                <span className="text-sm px-2 py-0.5 rounded bg-chess-accent/20 text-chess-accent border border-chess-accent/30">
                  {user_rating}
                </span>
              )}
            </div>
            <p className="text-chess-muted text-sm">
              {total_games} games — {white_games} as white, {black_games} as black
            </p>
          </div>
          <button onClick={onReset} className="text-xs text-chess-muted hover:text-white transition-colors">
            ← New search
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-8 p-1 bg-chess-surface rounded-lg w-fit border border-chess-border">
          {['white', 'black'].map(side => (
            <button
              key={side}
              onClick={() => setTab(side)}
              className={`px-5 py-2 rounded text-sm font-medium transition-colors capitalize
                ${tab === side
                  ? 'bg-chess-accent text-chess-bg'
                  : 'text-chess-text hover:text-white'
                }`}
            >
              As {side}
              <span className="ml-2 text-xs opacity-70">
                ({(side === 'white' ? white_openings : black_openings).length})
              </span>
            </button>
          ))}
        </div>

        {/* Sections */}
        {openings.length === 0 ? (
          <div className="card p-8 text-center">
            <p className="text-chess-muted">No games found as {tab}.</p>
          </div>
        ) : (
          <div className="space-y-8">
            {sections.map(({ label, items }) => (
              <Section
                key={label}
                label={label}
                items={items}
                onAnalyse={onAnalyse}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
