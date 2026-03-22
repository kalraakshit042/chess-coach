import { useState } from 'react'
import ChessBoard from './ChessBoard'
import { acplColor } from '../utils/api'

// ── RichText: renders [move](url) markdown links inline ───────────────────────
const LINK_RE = /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g

function RichText({ text, className = '' }) {
  if (!text) return null
  const parts = []
  let last = 0
  let match
  const re = new RegExp(LINK_RE.source, 'g')
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index))
    parts.push(
      <a
        key={match.index}
        href={match[2]}
        target="_blank"
        rel="noopener noreferrer"
        className="text-chess-accent underline hover:text-chess-accent/80 font-mono text-xs"
      >
        {match[1]}
      </a>
    )
    last = match.index + match[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return <span className={className}>{parts}</span>
}

// ── Rule-based bullets from diagnosis ────────────────────────────────────────
function WhatYoureDoingWrong({ diagnosis }) {
  const { wins, losses, draws, dominant_phase, avg_mistake_move, win_avg_acpl, loss_avg_acpl } = diagnosis
  const total = wins + losses + draws

  const bullets = []

  // Phase — only show if we have real data
  if (avg_mistake_move) {
    const phase = dominant_phase === 'opening' ? 'opening' : dominant_phase === 'endgame' ? 'endgame' : 'middlegame'
    bullets.push(
      <li key="phase" className="text-chess-text">
        Mistakes happen in the <span className="text-white font-semibold">{phase}</span>
        {' — '}avg around move <span className="text-white font-semibold">{Math.round(avg_mistake_move)}</span>
      </li>
    )
  }

  // ACPL gap — only show if both samples are meaningful (≥3 games each)
  if (win_avg_acpl && loss_avg_acpl && wins >= 3 && losses >= 3) {
    const multiplier = (loss_avg_acpl / win_avg_acpl).toFixed(1)
    bullets.push(
      <li key="acpl" className="text-chess-text">
        Accuracy is <span className="text-red-400 font-semibold">{multiplier}× worse</span> in losses
        {' '}({loss_avg_acpl} ACPL when losing vs {win_avg_acpl} when winning)
      </li>
    )
  }

  // Blunder rate
  const totalPositions = Object.values(diagnosis.phase_distribution || {}).reduce((a, b) => a + b, 0)
  if (totalPositions > 0 && total > 0) {
    const bpg = (totalPositions / total).toFixed(1)
    bullets.push(
      <li key="blunders" className="text-chess-text">
        <span className="text-white font-semibold">{bpg} blunders</span> per game detected
      </li>
    )
  }

  if (bullets.length === 0) return null

  return (
    <div className="card p-5 mb-5">
      <p className="text-xs uppercase tracking-wider text-chess-muted font-semibold mb-3">
        What's Going Wrong
      </p>
      <ul className="space-y-2.5 text-sm list-disc list-inside">
        {bullets}
      </ul>
    </div>
  )
}

// ── Recommendation card ───────────────────────────────────────────────────────
const FOCUS_STYLES = {
  tactics:         { label: '⚡ Tactics',         border: 'border-l-yellow-500', bg: 'bg-yellow-900/10' },
  opening_theory:  { label: '📖 Opening Theory',  border: 'border-l-blue-500',   bg: 'bg-blue-900/10'   },
  positional:      { label: '♟ Positional Plans', border: 'border-l-purple-500', bg: 'bg-purple-900/10' },
  endgame:         { label: '♛ Endgame',          border: 'border-l-green-500',  bg: 'bg-green-900/10'  },
}

function RecommendationCard({ study_plan }) {
  const style = FOCUS_STYLES[study_plan.focus] || FOCUS_STYLES.positional
  return (
    <div className={`card p-5 mb-5 border-l-4 ${style.border} ${style.bg}`}>
      <p className="text-xs uppercase tracking-wider text-chess-muted font-semibold mb-1">
        {style.label}
      </p>
      <h4 className="text-white font-bold text-base mb-2">{study_plan.title}</h4>
      <p className="text-sm text-chess-text leading-relaxed mb-3">{study_plan.action}</p>
      {study_plan.lichess_hint && (
        <p className="text-xs text-chess-muted border-t border-chess-border pt-2 mt-2">
          Search on Lichess:{' '}
          <span className="text-chess-accent font-mono">"{study_plan.lichess_hint}"</span>
        </p>
      )}
    </div>
  )
}

// ── Phase distribution bar ────────────────────────────────────────────────────
const PHASE_LABELS = { opening: 'Opening (1–14)', middlegame: 'Middlegame (15–30)', endgame: 'Endgame (31+)' }
const PHASE_COLORS = { opening: 'bg-chess-accent', middlegame: 'bg-blue-500', endgame: 'bg-purple-500' }

function PhaseBar({ phaseDistribution }) {
  const { opening = 0, middlegame = 0, endgame = 0 } = phaseDistribution
  const total = opening + middlegame + endgame
  if (total === 0) return null
  const phases = [{ key: 'opening', count: opening }, { key: 'middlegame', count: middlegame }, { key: 'endgame', count: endgame }].filter(p => p.count > 0)
  return (
    <div className="mb-4">
      <p className="text-xs uppercase tracking-wider text-chess-muted font-semibold mb-3">Where Mistakes Happen</p>
      <div className="space-y-2">
        {phases.map(({ key, count }) => (
          <div key={key} className="flex items-center gap-3">
            <span className="text-xs text-chess-muted w-36 flex-shrink-0">{PHASE_LABELS[key]}</span>
            <div className="flex-1 h-1.5 bg-chess-border rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${PHASE_COLORS[key]}`} style={{ width: `${(count / total) * 100}%` }} />
            </div>
            <span className="text-xs text-white tabular-nums w-4 text-right">{count}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Win vs Loss accuracy ──────────────────────────────────────────────────────
const MIN_SAMPLE = 3  // minimum games to show ACPL stat

function WinLossSplit({ diagnosis }) {
  const { wins, losses, win_avg_acpl, loss_avg_acpl } = diagnosis
  const showWins   = win_avg_acpl  != null && wins   >= MIN_SAMPLE
  const showLosses = loss_avg_acpl != null && losses >= MIN_SAMPLE
  if (!showWins && !showLosses) return null
  return (
    <div className="mb-4">
      <p className="text-xs uppercase tracking-wider text-chess-muted font-semibold mb-3">Accuracy vs Results</p>
      <div className="grid grid-cols-2 gap-3">
        {showWins && (
          <div className="text-center p-3 rounded-lg bg-green-900/20 border border-green-900/40">
            <div className="text-xs text-green-400 mb-1">{wins} wins</div>
            <div className={`text-xl font-bold tabular-nums ${acplColor(win_avg_acpl)}`}>{win_avg_acpl}</div>
            <div className="text-xs text-chess-muted mt-0.5">avg ACPL</div>
          </div>
        )}
        {showLosses && (
          <div className="text-center p-3 rounded-lg bg-red-900/20 border border-red-900/40">
            <div className="text-xs text-red-400 mb-1">{losses} losses</div>
            <div className={`text-xl font-bold tabular-nums ${acplColor(loss_avg_acpl)}`}>{loss_avg_acpl}</div>
            <div className="text-xs text-chess-muted mt-0.5">avg ACPL</div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Deep dive section ─────────────────────────────────────────────────────────
function DeepDive({ insight, diagnosis, key_positions }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="card p-5 mb-5">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between text-left"
      >
        <p className="text-xs uppercase tracking-wider text-chess-muted font-semibold">
          Deep Dive Analysis
        </p>
        <span className="text-chess-muted text-xs">{open ? '↑ collapse' : '↓ expand'}</span>
      </button>

      {open && (
        <div className="mt-4 space-y-5">
          {/* Claude prose */}
          {insight && (
            <>
              <div>
                <p className="text-xs text-chess-muted font-medium mb-1">🔍 What's Going Wrong</p>
                <p className="text-sm text-chess-text leading-relaxed">
                  <RichText text={insight.whats_wrong} />
                </p>
              </div>
              {insight.critical_moment && (
                <div>
                  <p className="text-xs text-chess-muted font-medium mb-1">💥 The Critical Moment</p>
                  <p className="text-sm text-chess-text leading-relaxed">
                    <RichText text={insight.critical_moment} />
                  </p>
                </div>
              )}
              <div>
                <p className="text-xs text-chess-muted font-medium mb-1">🧠 The Pattern</p>
                <p className="text-sm text-chess-text leading-relaxed">
                  <RichText text={insight.pattern} />
                </p>
              </div>
              <div className="border-t border-chess-border pt-4" />
            </>
          )}

          {/* Charts */}
          <PhaseBar phaseDistribution={diagnosis.phase_distribution} />
          <WinLossSplit diagnosis={diagnosis} />

          {/* Worst position */}
          {diagnosis.critical_position && (
            <div>
              <p className="text-xs text-chess-muted font-medium mb-2">Your Worst Moment</p>
              <ChessBoard positions={[diagnosis.critical_position]} />
            </div>
          )}

          {/* Other key positions */}
          {key_positions?.length > 0 && (
            <div>
              <p className="text-xs text-chess-muted font-medium mb-2">Other Critical Positions</p>
              <ChessBoard positions={key_positions} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function AnalysisResultPage({ result, opening, onBack }) {
  const { opening_name, eco, color, games_analysed, avg_acpl, key_positions, diagnosis, insight } = result

  return (
    <div className="min-h-screen px-4 py-10">
      <div className="max-w-2xl mx-auto">

        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-sm text-chess-muted hover:text-white transition-colors mb-8"
        >
          ← Back to overview
        </button>

        {/* Header */}
        <div className="card p-5 mb-5">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <span className="text-xs px-1.5 py-0.5 rounded bg-chess-surface border border-chess-border text-chess-text capitalize">as {color}</span>
              </div>
              <h2 className="text-xl font-bold text-white mt-1">{opening_name}</h2>
              <p className="text-chess-muted text-sm mt-0.5">{games_analysed} games analysed</p>
            </div>
            {avg_acpl != null && (
              <div className="text-right">
                <div className={`text-3xl font-bold tabular-nums ${acplColor(avg_acpl)}`}>{avg_acpl}</div>
                <div className="text-xs text-chess-muted mb-2">avg centipawn loss</div>
                <div className="text-xs text-chess-muted space-x-2 whitespace-nowrap">
                  <span className="text-green-400">&lt;30 Excellent</span>
                  <span>·</span>
                  <span className="text-chess-accent">&lt;60 Good</span>
                  <span>·</span>
                  <span className="text-yellow-400">&lt;100 Fair</span>
                  <span>·</span>
                  <span className="text-red-400">100+ Poor</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 1. What you're doing wrong — rule-based bullets */}
        {diagnosis && <WhatYoureDoingWrong diagnosis={diagnosis} />}

        {/* 2. Recommendation — Claude study plan */}
        {insight?.study_plan && <RecommendationCard study_plan={insight.study_plan} />}

        {/* 3. Deep dive — collapsible */}
        {(insight || diagnosis) && (
          <DeepDive
            insight={insight}
            diagnosis={diagnosis}
            key_positions={key_positions}
          />
        )}

        <div className="mt-6 text-center">
          <button onClick={onBack} className="btn-primary">← Analyse Another Opening</button>
        </div>
      </div>
    </div>
  )
}
