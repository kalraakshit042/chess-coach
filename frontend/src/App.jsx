import { useState, useCallback } from 'react'
import UsernameInput from './components/UsernameInput'
import LoadingState from './components/LoadingState'
import RepertoireView from './components/RepertoireView'
import { analyzeWithStream } from './utils/api'

const VIEW = { HOME: 'home', LOADING: 'loading', RESULTS: 'results', ERROR: 'error' }

export default function App() {
  const [view, setView] = useState(VIEW.HOME)
  const [username, setUsername] = useState('')
  const [progress, setProgress] = useState(null)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)
  const [cancelFn, setCancelFn] = useState(null)

  const handleAnalyze = useCallback((user, months, speed, testMode) => {
    setUsername(user)
    setView(VIEW.LOADING)
    setProgress(null)
    setError(null)

    const cancel = analyzeWithStream(
      user,
      months,
      speed,
      testMode,
      // onProgress
      (data) => setProgress(data),
      // onComplete
      (data) => {
        setResults(data)
        setView(VIEW.RESULTS)
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
  }, [])

  const handleReset = useCallback(() => {
    if (cancelFn) cancelFn()
    setView(VIEW.HOME)
    setProgress(null)
    setResults(null)
    setError(null)
    setCancelFn(null)
  }, [cancelFn])

  return (
    <div className="min-h-screen bg-chess-bg">
      {view === VIEW.HOME && (
        <UsernameInput
          onAnalyze={handleAnalyze}
          isLoading={false}
        />
      )}

      {view === VIEW.LOADING && (
        <LoadingState
          progress={progress}
          username={username}
        />
      )}

      {view === VIEW.RESULTS && results && (
        <RepertoireView
          data={results}
          onReset={handleReset}
        />
      )}

      {view === VIEW.ERROR && (
        <ErrorView
          message={error}
          username={username}
          onReset={handleReset}
        />
      )}
    </div>
  )
}

function ErrorView({ message, username, onReset }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen px-4">
      <div className="text-center max-w-md">
        <div className="text-5xl mb-4">♙</div>
        <h2 className="text-xl font-bold text-white mb-3">Analysis Failed</h2>
        <div className="card p-5 mb-6">
          <p className="text-chess-text text-sm leading-relaxed">{message}</p>
          {message?.includes('backend') && (
            <div className="mt-3 text-xs text-chess-muted bg-chess-bg rounded p-3 font-mono">
              Make sure the backend is running:<br />
              <span className="text-chess-accent">cd backend && uvicorn main:app --reload</span>
            </div>
          )}
        </div>
        <button onClick={onReset} className="btn-primary">
          Try Again
        </button>
      </div>
    </div>
  )
}
