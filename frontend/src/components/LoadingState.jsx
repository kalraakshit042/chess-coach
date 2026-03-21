export default function LoadingState({ progress, username }) {
  const step = progress?.step || 'fetching'
  const message = progress?.message || `Fetching games for ${username}...`

  const steps = [
    { id: 'fetching', label: 'Fetching games', icon: '♜' },
    { id: 'games_fetched', label: 'Grouping openings', icon: '♝' },
    { id: 'openings_grouped', label: 'Engine analysis', icon: '♞' },
    { id: 'engine_analysis', label: 'Engine analysis', icon: '♞' },
    { id: 'claude_analysis', label: 'AI coaching', icon: '♛' },
  ]

  const stepOrder = ['fetching', 'games_fetched', 'openings_grouped', 'engine_analysis', 'claude_analysis']
  const currentIndex = stepOrder.indexOf(step)

  return (
    <div className="flex flex-col items-center justify-center min-h-screen px-4 py-16">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="text-5xl mb-3 animate-bounce select-none">♞</div>
          <h2 className="text-2xl font-bold text-white mb-1">Analyzing {username}</h2>
          <p className="text-chess-text text-sm">This may take 1–3 minutes...</p>
        </div>

        {/* Progress Steps */}
        <div className="card p-6 mb-6 space-y-3">
          {steps.filter((s, i) => stepOrder.indexOf(s.id) === i || s.id !== 'openings_grouped').map((s, i) => {
            const sIndex = stepOrder.indexOf(s.id)
            const isDone = sIndex < currentIndex
            const isActive = sIndex === currentIndex

            return (
              <div key={s.id} className="flex items-center gap-3">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-mono
                    transition-all duration-300
                    ${isDone ? 'bg-green-700 text-green-200' : ''}
                    ${isActive ? 'bg-chess-accent text-chess-bg animate-pulse' : ''}
                    ${!isDone && !isActive ? 'bg-chess-muted text-chess-text opacity-40' : ''}
                  `}
                >
                  {isDone ? '✓' : s.icon}
                </div>
                <span
                  className={`text-sm transition-colors duration-300
                    ${isDone ? 'text-green-400' : ''}
                    ${isActive ? 'text-white font-medium' : ''}
                    ${!isDone && !isActive ? 'text-chess-muted' : ''}
                  `}
                >
                  {s.label}
                </span>
                {isActive && (
                  <div className="ml-auto flex gap-1">
                    {[0, 1, 2].map((d) => (
                      <div
                        key={d}
                        className="w-1.5 h-1.5 bg-chess-accent rounded-full animate-bounce"
                        style={{ animationDelay: `${d * 0.15}s` }}
                      />
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Current message */}
        <div className="card p-4">
          <p className="text-sm text-chess-text leading-relaxed">{message}</p>

          {/* Show game count if available */}
          {progress?.total_games && (
            <div className="mt-3 flex gap-4 text-xs">
              <span className="text-chess-text">
                <span className="text-white font-semibold">{progress.total_games}</span> total games
              </span>
              <span className="text-chess-text">
                <span className="text-white font-semibold">{progress.white_games}</span> as white
              </span>
              <span className="text-chess-text">
                <span className="text-white font-semibold">{progress.black_games}</span> as black
              </span>
            </div>
          )}

          {/* Show opening counts if available */}
          {progress?.white_openings_count !== undefined && (
            <div className="mt-3 flex gap-4 text-xs">
              <span className="text-chess-text">
                <span className="text-white font-semibold">{progress.white_openings_count}</span> white openings
              </span>
              <span className="text-chess-text">
                <span className="text-white font-semibold">{progress.black_openings_count}</span> black openings
              </span>
            </div>
          )}
        </div>

        {/* Shimmer progress bar */}
        <div className="mt-4 h-1 bg-chess-muted rounded-full overflow-hidden">
          <div
            className="h-full shimmer rounded-full transition-all duration-700"
            style={{ width: `${Math.min(100, (currentIndex + 1) * 22)}%` }}
          />
        </div>
      </div>
    </div>
  )
}
