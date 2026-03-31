import { useState, useCallback, useEffect } from 'react'
import { Analytics } from '@vercel/analytics/react'
import UsernameInput from './components/UsernameInput'
import OverviewPage from './components/OverviewPage'
import AnalysisResultPage from './components/AnalysisResultPage'
import { fetchOverview, analyseOpening } from './utils/api'

const VIEW = {
  HOME: 'home',
  LOADING_OVERVIEW: 'loading_overview',
  OVERVIEW: 'overview',
  LOADING_ANALYSIS: 'loading_analysis',
  ANALYSIS_RESULT: 'analysis_result',
  ERROR: 'error',
}

export default function App() {
  const [view, setView] = useState(VIEW.HOME)
  const [username, setUsername] = useState('')
  const [queryParams, setQueryParams] = useState({ months: 12, speed: 'all' })
  const [overviewData, setOverviewData] = useState(null)
  const [analysisProgress, setAnalysisProgress] = useState(null)
  const [analysisResult, setAnalysisResult] = useState(null)
  const [selectedOpening, setSelectedOpening] = useState(null)
  const [error, setError] = useState(null)
  const [cancelFn, setCancelFn] = useState(null)

  // ── Phase 1: load overview ────────────────────────────────────────────────

  const handleLoadOverview = useCallback(async (user, months, speed) => {
    setUsername(user)
    setQueryParams({ months, speed })
    setView(VIEW.LOADING_OVERVIEW)
    setError(null)
    setOverviewData(null)

    try {
      const data = await fetchOverview(user, months, speed)
      setOverviewData(data)
      setView(VIEW.OVERVIEW)
    } catch (err) {
      setError(err.message || 'Failed to load overview.')
      setView(VIEW.ERROR)
    }
  }, [])

  // ── Phase 2: analyse one opening ─────────────────────────────────────────

  const handleAnalyseOpening = useCallback((opening) => {
    setSelectedOpening(opening)
    setView(VIEW.LOADING_ANALYSIS)
    setAnalysisProgress(null)
    setAnalysisResult(null)

    const cancel = analyseOpening(
      username,
      queryParams.months,
      queryParams.speed,
      opening.key,
      opening.eco,
      opening.name,
      opening.color,
      // onProgress
      (data) => setAnalysisProgress(data),
      // onComplete
      (data) => {
        setAnalysisResult(data)
        setView(VIEW.ANALYSIS_RESULT)
        setCancelFn(null)
      },
      // onError
      (msg) => {
        setError(msg)
        setView(VIEW.ERROR)
        setCancelFn(null)
      },
    )

    setCancelFn(() => cancel)
  }, [username, queryParams])

  const handleBackToOverview = useCallback(() => {
    if (cancelFn) cancelFn()
    setCancelFn(null)
    setView(VIEW.OVERVIEW)
    setAnalysisProgress(null)
    setAnalysisResult(null)
  }, [cancelFn])

  const handleReset = useCallback(() => {
    if (cancelFn) cancelFn()
    setCancelFn(null)
    setView(VIEW.HOME)
    setOverviewData(null)
    setAnalysisProgress(null)
    setAnalysisResult(null)
    setSelectedOpening(null)
    setError(null)
  }, [cancelFn])

  return (
    <div className="min-h-screen bg-chess-bg">

      {view === VIEW.HOME && (
        <UsernameInput onAnalyze={handleLoadOverview} isLoading={false} />
      )}

      {view === VIEW.LOADING_OVERVIEW && (
        <OverviewLoadingView username={username} />
      )}

      {view === VIEW.OVERVIEW && overviewData && (
        <OverviewPage
          data={overviewData}
          onAnalyse={handleAnalyseOpening}
          onReset={handleReset}
        />
      )}

      {view === VIEW.LOADING_ANALYSIS && selectedOpening && (
        <AnalysisLoadingView
          opening={selectedOpening}
          progress={analysisProgress}
          onCancel={handleBackToOverview}
        />
      )}

      {view === VIEW.ANALYSIS_RESULT && analysisResult && (
        <AnalysisResultPage
          result={analysisResult}
          opening={selectedOpening}
          onBack={handleBackToOverview}
        />
      )}

      {view === VIEW.ERROR && (
        <ErrorView
          message={error}
          onReset={handleReset}
          onBack={overviewData ? handleBackToOverview : null}
        />
      )}

      <footer className="text-center py-4 text-chess-muted text-sm px-4">
        Built by{' '}
        <a
          href="https://www.akshitkalra.com/"
          target="_blank"
          rel="noopener noreferrer"
          className="text-chess-accent hover:underline"
        >
          Akshit Kalra
        </a>
      </footer>
      <Analytics />
    </div>
  )
}

// ── Overview Loading ──────────────────────────────────────────────────────────

function OverviewLoadingView({ username }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen px-4">
      <div className="text-center">
        <div className="text-5xl mb-4 animate-bounce select-none">♞</div>
        <h2 className="text-xl font-bold text-white mb-2">Loading {username}</h2>
        <p className="text-chess-text text-sm mb-6">Fetching games from Lichess...</p>
        <div className="flex gap-1.5 justify-center">
          {[0, 1, 2].map((d) => (
            <div
              key={d}
              className="w-2 h-2 bg-chess-accent rounded-full animate-bounce"
              style={{ animationDelay: `${d * 0.15}s` }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Analysis Loading (SSE progress) ──────────────────────────────────────────

const STEP_MESSAGES = {
  starting:   null,
  analysing:  null,
  knowledge:  'Preparing your analysis…',
  coaching:   'Generating coaching insights…',
}

const IDLE_MESSAGES = [
  'Running Stockfish on every move…',
  'Calculating centipawn loss…',
  'Finding your worst blunders…',
  'Scanning for tactical patterns…',
  'Crunching positions with depth 15…',
  'Identifying key moments…',
]

function AnalysisLoadingView({ opening, progress, onCancel }) {
  const [idleIdx, setIdleIdx] = useState(0)
  const [dots, setDots] = useState('')

  const step = progress?.step || 'starting'
  const done = progress?.done ?? 0
  const totalNew = progress?.total_new ?? progress?.new ?? 0
  const totalGames = progress?.total ?? opening.games
  const isIdle = totalNew === 0 || done === 0

  // Cycle idle messages every 2.5s
  useEffect(() => {
    if (!isIdle) return
    const id = setInterval(() => setIdleIdx(i => (i + 1) % IDLE_MESSAGES.length), 2500)
    return () => clearInterval(id)
  }, [isIdle])

  // Animate dots
  useEffect(() => {
    const id = setInterval(() => setDots(d => d.length >= 3 ? '' : d + '.'), 500)
    return () => clearInterval(id)
  }, [])

  const stepMsg = step && STEP_MESSAGES[step]
  const message = stepMsg
    || progress?.message
    || (isIdle ? IDLE_MESSAGES[idleIdx] : `Analysing game ${done} of ${totalNew}…`)

  const progressPct = totalNew > 0
    ? Math.round(((progress?.cached ?? 0) + done) / totalGames * 100)
    : step === 'starting' ? 5 : 95

  return (
    <div className="flex flex-col items-center justify-center min-h-screen px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3 animate-bounce select-none">♞</div>
          <h2 className="text-xl font-bold text-white mb-1">Analysing {opening.name}</h2>
          <div className="flex items-center justify-center gap-2 mt-1">
            <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-chess-accent/20 text-chess-accent border border-chess-accent/30">
              {opening.eco}
            </span>
            <span className="text-chess-muted text-sm capitalize">as {opening.color}</span>
          </div>
        </div>

        <div className="card p-5 mb-4">
          <p className="text-sm text-chess-text leading-relaxed min-h-[1.5rem]">
            {message}{dots}
          </p>

          {totalNew > 0 && done > 0 && (
            <div className="mt-3 flex gap-4 text-xs">
              <span className="text-chess-text">
                <span className="text-white font-semibold">{done}</span>/{totalNew} games
              </span>
              {progress?.cached > 0 && (
                <span className="text-chess-text">
                  <span className="text-white font-semibold">{progress.cached}</span> from cache
                </span>
              )}
            </div>
          )}
        </div>

        {/* Progress bar */}
        <div className="h-1.5 bg-chess-muted rounded-full overflow-hidden mb-6">
          <div
            className="h-full bg-chess-accent rounded-full transition-all duration-500"
            style={{ width: `${progressPct}%` }}
          />
        </div>

        <div className="text-center">
          <button
            onClick={onCancel}
            className="text-xs text-chess-muted hover:text-white transition-colors"
          >
            ← Cancel and go back
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Error View ────────────────────────────────────────────────────────────────

function ErrorView({ message, onReset, onBack }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen px-4">
      <div className="text-center max-w-md">
        <div className="text-5xl mb-4">♙</div>
        <h2 className="text-xl font-bold text-white mb-3">Something went wrong</h2>
        <div className="card p-5 mb-6">
          <p className="text-chess-text text-sm leading-relaxed">{message}</p>
          {message?.includes('backend') && (
            <div className="mt-3 text-xs text-chess-muted bg-chess-bg rounded p-3 font-mono">
              Make sure the backend is running:<br />
              <span className="text-chess-accent">cd backend && uvicorn main:app --reload</span>
            </div>
          )}
        </div>
        <div className="flex gap-3 justify-center">
          {onBack && (
            <button onClick={onBack} className="btn-ghost">
              ← Go Back
            </button>
          )}
          <button onClick={onReset} className="btn-primary">
            Start Over
          </button>
        </div>
      </div>
    </div>
  )
}
