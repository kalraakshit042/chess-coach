import { useState } from 'react'
import OpeningCard from './OpeningCard'

export default function RepertoireView({ data, onReset }) {
  const [activeTab, setActiveTab] = useState('white')

  const { username, total_games, white_games, black_games,
          white_openings, black_openings, user_rating } = data

  const currentOpenings = activeTab === 'white' ? white_openings : black_openings

  const strongCount = (openings) => openings.filter((o) => o.verdict === 'Strong').length
  const weakCount = (openings) => openings.filter((o) => o.verdict === 'Weak').length

  return (
    <div className="min-h-screen px-4 py-8 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8 flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-chess-accent text-2xl">♞</span>
            <h1 className="text-2xl font-bold text-white">{username}</h1>
            {user_rating && (
              <span className="text-sm text-chess-muted bg-chess-surface border border-chess-border
                               px-2 py-0.5 rounded font-mono">
                ~{user_rating}
              </span>
            )}
          </div>
          <p className="text-chess-text text-sm">
            {total_games} rated games analyzed
            <span className="text-chess-muted mx-2">·</span>
            <span className="text-chess-muted">{white_games} as white</span>
            <span className="text-chess-muted mx-1">/</span>
            <span className="text-chess-muted">{black_games} as black</span>
          </p>
        </div>

        <button onClick={onReset} className="btn-ghost text-sm">
          ← New Analysis
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-chess-surface rounded-lg p-1 w-fit border border-chess-border">
        {[
          { id: 'white', label: '♔ As White', count: white_openings.length },
          { id: 'black', label: '♚ As Black', count: black_openings.length },
        ].map(({ id, label, count }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`px-5 py-2 rounded-md text-sm font-medium transition-all duration-150
              ${activeTab === id
                ? 'bg-chess-accent text-chess-bg'
                : 'text-chess-text hover:text-white'
              }`}
          >
            {label}
            <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full
              ${activeTab === id ? 'bg-chess-bg/30' : 'bg-chess-muted/30'}`}>
              {count}
            </span>
          </button>
        ))}
      </div>

      {/* Summary bar */}
      {currentOpenings.length > 0 && (
        <div className="card p-4 mb-6 flex flex-wrap gap-4 text-sm">
          <SummaryBadge
            color="green"
            label="Strong"
            count={strongCount(currentOpenings)}
            total={currentOpenings.length}
          />
          <SummaryBadge
            color="yellow"
            label="Needs Work"
            count={currentOpenings.filter((o) => o.verdict === 'Needs Work').length}
            total={currentOpenings.length}
          />
          <SummaryBadge
            color="red"
            label="Weak"
            count={weakCount(currentOpenings)}
            total={currentOpenings.length}
          />
        </div>
      )}

      {/* Opening cards */}
      {currentOpenings.length === 0 ? (
        <div className="card p-8 text-center">
          <div className="text-4xl mb-3 opacity-30">♟</div>
          <p className="text-chess-text">
            No openings found as {activeTab} with 3+ games in the analyzed period.
          </p>
          <p className="text-chess-muted text-sm mt-2">
            Play more games or try a longer time range.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {currentOpenings.map((opening, i) => (
            <OpeningCard key={`${opening.stats.eco}-${i}`} opening={opening} />
          ))}
        </div>
      )}

      {/* Footer */}
      <div className="mt-12 text-center">
        <p className="text-xs text-chess-muted">
          Analysis powered by{' '}
          <span className="text-chess-accent">Claude AI</span> and{' '}
          <span className="text-chess-accent">Stockfish</span>.
          For educational purposes only.
        </p>
        <p className="text-xs text-chess-muted mt-1">
          Built with the{' '}
          <a
            href="https://docs.anthropic.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-chess-accent hover:underline"
          >
            Claude API
          </a>
        </p>
      </div>
    </div>
  )
}

function SummaryBadge({ color, label, count, total }) {
  const colorMap = {
    green: 'text-green-400',
    yellow: 'text-yellow-400',
    red: 'text-red-400',
  }
  return (
    <div className="flex items-center gap-2">
      <span className={`font-semibold ${colorMap[color]}`}>{count}</span>
      <span className="text-chess-muted">{label}</span>
    </div>
  )
}
