const API_BASE = '/api'

/**
 * Analyze a Lichess user's games with streaming progress updates.
 * @param {string} username
 * @param {number} months
 * @param {function} onProgress - called with progress events
 * @param {function} onComplete - called with the final analysis result
 * @param {function} onError - called with error message string
 * @returns {function} cancel - call to abort the request
 */
export function analyzeWithStream(username, months = 12, speed = 'all', testMode = false, onProgress, onComplete, onError) {
  const controller = new AbortController()

  async function run() {
    try {
      const response = await fetch(`${API_BASE}/analyze/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, months, speed, test_mode: testMode }),
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
        buffer = lines.pop() // keep incomplete line

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

/**
 * Non-streaming analyze endpoint (fallback).
 */
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
