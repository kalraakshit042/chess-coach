import { useState } from 'react'

export default function UsernameInput({ onAnalyze, isLoading }) {
  const [username, setUsername] = useState('')
  const [months, setMonths] = useState(12)
  const [speed, setSpeed] = useState('all')
  function handleSubmit(e) {
    e.preventDefault()
    const trimmed = username.trim()
    if (!trimmed) return
    onAnalyze(trimmed, months, speed)
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen px-4 py-16">
      {/* Hero */}
      <div className="text-center mb-12">
        <div className="text-6xl mb-4 select-none">♞</div>
        <h1 className="text-4xl md:text-5xl font-bold text-white mb-3 tracking-tight">
          Chess Coach
        </h1>
        <p className="text-chess-text text-lg max-w-md mx-auto leading-relaxed">
          Analyze your Lichess opening repertoire with AI coaching powered by{' '}
          <span className="text-chess-accent font-medium">Claude</span> and{' '}
          <span className="text-chess-accent font-medium">Stockfish</span>.
        </p>
      </div>

      {/* Input Form */}
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md space-y-4"
      >
        <div className="card p-6 space-y-4">
          <div>
            <label
              htmlFor="username"
              className="block text-sm font-medium text-chess-text mb-2"
            >
              Lichess Username
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. Magnus"
              className="w-full bg-chess-bg border border-chess-border rounded-lg px-4 py-3
                         text-white placeholder-chess-muted focus:outline-none
                         focus:border-chess-accent transition-colors duration-150"
              disabled={isLoading}
              autoComplete="off"
              spellCheck={false}
            />
          </div>

          <div>
            <label
              htmlFor="months"
              className="block text-sm font-medium text-chess-text mb-2"
            >
              Time Range
            </label>
            <select
              id="months"
              value={months}
              onChange={(e) => setMonths(Number(e.target.value))}
              className="w-full bg-chess-bg border border-chess-border rounded-lg px-4 py-3
                         text-white focus:outline-none focus:border-chess-accent
                         transition-colors duration-150 cursor-pointer"
              disabled={isLoading}
            >
              <option value={1}>Last 1 month</option>
              <option value={3}>Last 3 months</option>
              <option value={6}>Last 6 months</option>
              <option value={12}>Last 12 months</option>
            </select>
          </div>

          <div>
            <label
              htmlFor="speed"
              className="block text-sm font-medium text-chess-text mb-2"
            >
              Game Type
            </label>
            <select
              id="speed"
              value={speed}
              onChange={(e) => setSpeed(e.target.value)}
              className="w-full bg-chess-bg border border-chess-border rounded-lg px-4 py-3
                         text-white focus:outline-none focus:border-chess-accent
                         transition-colors duration-150 cursor-pointer"
              disabled={isLoading}
            >
              <option value="all">All games</option>
              <option value="rapid">Rapid only</option>
              <option value="blitz">Blitz only</option>
              <option value="bullet">Bullet only</option>
            </select>
          </div>

          <button
            type="submit"
            className="btn-primary w-full"
            disabled={isLoading || !username.trim()}
          >
            {isLoading ? (
              <span className="flex items-center justify-center gap-2">
                <SpinnerIcon />
                Analyzing...
              </span>
            ) : (
              'Analyze My Games'
            )}
          </button>
        </div>
      </form>

      {/* Features */}
      <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl w-full px-4">
        {[
          { icon: '♟', title: 'Opening Repertoire', desc: 'See every opening you play with 3+ games, sorted by frequency.' },
          { icon: '⚡', title: 'Engine Accuracy', desc: 'Stockfish evaluates your positions to calculate centipawn loss.' },
          { icon: '🎯', title: 'AI Coaching', desc: 'Claude gives specific, actionable feedback — not generic tips.' },
        ].map(({ icon, title, desc }) => (
          <div key={title} className="card p-4 text-center">
            <div className="text-2xl mb-2">{icon}</div>
            <div className="text-white font-medium text-sm mb-1">{title}</div>
            <div className="text-chess-text text-xs leading-relaxed">{desc}</div>
          </div>
        ))}
      </div>

      {/* Disclaimer */}
      <p className="mt-10 text-xs text-chess-muted text-center max-w-sm px-4">
        Analysis powered by Claude AI and Stockfish. For educational purposes only.
        No account required — just your Lichess username.
      </p>
    </div>
  )
}

function SpinnerIcon() {
  return (
    <svg
      className="animate-spin h-4 w-4"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12" cy="12" r="10"
        stroke="currentColor" strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  )
}
