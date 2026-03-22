const API_BASE = import.meta.env.VITE_API_URL || '/api'

// ── SSE helper ────────────────────────────────────────────────────────────────

function readSSEStream(url, body, onProgress, onComplete, onError) {
  const controller = new AbortController()

  async function run() {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Request failed' }))
        onError(err.detail || 'Request failed')
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        let eventType = null
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const dataStr = line.slice(6).trim()
            try {
              const data = JSON.parse(dataStr)
              if (eventType === 'progress') {
                onProgress(data)
              } else if (eventType === 'complete') {
                onComplete(data)
              } else if (eventType === 'error') {
                onError(data.message || 'Unknown error')
                return
              }
            } catch {
              // ignore parse errors
            }
            eventType = null
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        onError(err.message || 'Network error. Is the backend running?')
      }
    }
  }

  run()
  return () => controller.abort()
}

// ── Phase 1: Overview ─────────────────────────────────────────────────────────

/**
 * Fetch opening overview for a user (fast — no Stockfish).
 * Returns the full OverviewResponse object.
 */
export async function fetchOverview(username, months = 12, speed = 'all') {
  const response = await fetch(`${API_BASE}/overview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, months, speed }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail || 'Failed to fetch overview')
  }

  return response.json()
}

// ── Phase 2: Analyse one opening ──────────────────────────────────────────────

/**
 * Run Stockfish on all games in one opening. SSE stream.
 * @returns {function} cancel - call to abort
 */
export function analyseOpening(
  username, months, speed,
  openingKey, eco, openingName, color,
  onProgress, onComplete, onError,
) {
  return readSSEStream(
    `${API_BASE}/analyse-opening`,
    {
      username,
      months,
      speed,
      opening_key: openingKey,
      eco,
      opening_name: openingName,
      color,
    },
    onProgress,
    onComplete,
    onError,
  )
}

// ── Legacy stream endpoint (kept for fallback) ────────────────────────────────

export function analyzeWithStream(username, months = 12, speed = 'all', onProgress, onComplete, onError) {
  return readSSEStream(
    `${API_BASE}/analyze/stream`,
    { username, months, speed },
    onProgress,
    onComplete,
    onError,
  )
}

export async function analyze(username, months = 12, speed = 'all') {
  const response = await fetch(`${API_BASE}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, months, speed }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail || 'Analysis failed')
  }

  return response.json()
}

// ── Formatting utils ──────────────────────────────────────────────────────────

export function getVerdictClass(verdict) {
  switch (verdict) {
    case 'Strong': return 'verdict-strong'
    case 'Needs Work': return 'verdict-needs-work'
    case 'Weak': return 'verdict-weak'
    default: return 'verdict-needs-work'
  }
}

export function formatWinRate(wins, draws, losses) {
  const total = wins + draws + losses
  if (total === 0) return '0%'
  return `${Math.round((wins / total) * 100)}%`
}

export function formatEstimatedTime(seconds) {
  if (seconds <= 0) return 'Instant (cached)'
  if (seconds < 60) return `~${seconds}s`
  const mins = Math.round(seconds / 60)
  return `~${mins} min`
}

export function acplColor(acpl) {
  if (acpl === null || acpl === undefined) return 'text-chess-muted'
  if (acpl < 30)  return 'text-green-400'
  if (acpl < 60)  return 'text-chess-accent'   // amber — Good
  if (acpl < 100) return 'text-yellow-400'      // Fair
  return 'text-red-400'                         // Poor
}
