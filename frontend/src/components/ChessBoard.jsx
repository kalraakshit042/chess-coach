import { useState } from 'react'
import { Chessboard } from 'react-chessboard'
import { Chess } from 'chess.js'

/**
 * Converts a SAN move string to a [from, to] square pair given a FEN position.
 * Returns null if the move is invalid.
 */
function sanToSquares(fen, san) {
  if (!fen || !san) return null
  try {
    const chess = new Chess(fen)
    const move = chess.move(san)
    if (move) return [move.from, move.to]
  } catch {}
  return null
}

/**
 * Builds the customArrows array for react-chessboard.
 * move_played → red, better_move → green
 */
function buildArrows(fen, movePlayed, betterMove) {
  const arrows = []
  if (movePlayed) {
    const sq = sanToSquares(fen, movePlayed)
    if (sq) arrows.push([sq[0], sq[1], 'rgba(220,50,50,0.85)'])
  }
  if (betterMove && betterMove !== movePlayed) {
    const sq = sanToSquares(fen, betterMove)
    if (sq) arrows.push([sq[0], sq[1], 'rgba(50,200,80,0.85)'])
  }
  return arrows
}

/**
 * Single position board with move arrows and optional game link.
 */
export function PositionBoard({ fen, movePlayed, betterMove, gameUrl, explanation, moveNumber, evalSwing }) {
  const arrows = buildArrows(fen, movePlayed, betterMove)
  const swingPawns = evalSwing ? Math.abs(evalSwing / 100).toFixed(1) : null

  return (
    <div className="bg-chess-bg rounded-lg border border-chess-border p-4">
      <div className="flex flex-col md:flex-row gap-4 items-start">
        {/* Board */}
        <div className="flex-shrink-0">
          <Chessboard
            position={fen}
            arePiecesDraggable={false}
            boardWidth={200}
            customDarkSquareStyle={{ backgroundColor: '#769656' }}
            customLightSquareStyle={{ backgroundColor: '#eeeed2' }}
            customArrows={arrows}
          />
          {/* Legend */}
          <div className="mt-2 flex gap-3 text-xs">
            {movePlayed && (
              <span className="flex items-center gap-1">
                <span className="w-3 h-1.5 rounded-sm bg-red-500 inline-block" />
                <span className="text-chess-muted">Played: <span className="text-white font-mono">{movePlayed}</span></span>
              </span>
            )}
            {betterMove && betterMove !== movePlayed && (
              <span className="flex items-center gap-1">
                <span className="w-3 h-1.5 rounded-sm bg-green-500 inline-block" />
                <span className="text-chess-muted">Better: <span className="text-white font-mono">{betterMove}</span></span>
              </span>
            )}
          </div>
        </div>

        {/* Annotation */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className="text-xs text-chess-muted">Move {moveNumber}</span>
            {swingPawns && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-red-900/40 text-red-400 border border-red-800">
                -{swingPawns} pawns
              </span>
            )}
            {gameUrl && (
              <a
                href={gameUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-chess-accent hover:underline flex items-center gap-1"
              >
                View game ↗
              </a>
            )}
          </div>
          <p className="text-sm text-chess-text leading-relaxed">{explanation}</p>
        </div>
      </div>
    </div>
  )
}

/**
 * Legacy multi-position viewer (kept for KeyPosition fallback).
 */
export default function ChessBoard({ positions = [] }) {
  const [currentIndex, setCurrentIndex] = useState(0)

  if (!positions || positions.length === 0) return null

  const current = positions[currentIndex]

  return (
    <div className="mt-4 p-4 bg-chess-bg rounded-lg border border-chess-border">
      <div className="text-xs font-medium text-chess-accent uppercase tracking-wider mb-3">
        Key Position{positions.length > 1 ? 's' : ''}
      </div>

      <div className="flex flex-col md:flex-row gap-4 items-start">
        <div className="flex-shrink-0">
          <Chessboard
            position={current.fen}
            arePiecesDraggable={false}
            boardWidth={200}
            customDarkSquareStyle={{ backgroundColor: '#769656' }}
            customLightSquareStyle={{ backgroundColor: '#eeeed2' }}
            customArrows={buildArrows(current.fen, current.move_played_san, current.best_move_san)}
          />
          <div className="mt-2 flex gap-3 text-xs">
            {current.move_played_san && (
              <span className="flex items-center gap-1">
                <span className="w-3 h-1.5 rounded-sm bg-red-500 inline-block" />
                <span className="text-chess-muted">Played: <span className="text-white font-mono">{current.move_played_san}</span></span>
              </span>
            )}
            {current.best_move_san && current.best_move_san !== current.move_played_san && (
              <span className="flex items-center gap-1">
                <span className="w-3 h-1.5 rounded-sm bg-green-500 inline-block" />
                <span className="text-chess-muted">Better: <span className="text-white font-mono">{current.best_move_san}</span></span>
              </span>
            )}
          </div>
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm text-chess-text leading-relaxed">{current.comment}</p>
          {current.eval_before !== null && current.eval_after !== null && (
            <div className="mt-2 flex gap-3 text-xs">
              <span className="text-chess-muted">
                Before: <span className={current.eval_before >= 0 ? 'text-green-400' : 'text-red-400'}>
                  {current.eval_before >= 0 ? '+' : ''}{(current.eval_before / 100).toFixed(1)}
                </span>
              </span>
              <span className="text-chess-muted">
                After: <span className={current.eval_after >= 0 ? 'text-green-400' : 'text-red-400'}>
                  {current.eval_after >= 0 ? '+' : ''}{(current.eval_after / 100).toFixed(1)}
                </span>
              </span>
            </div>
          )}
          <p className="mt-2 text-xs text-chess-muted">Move {current.move_number}</p>
          {positions.length > 1 && (
            <div className="mt-3 flex gap-2">
              {positions.map((_, i) => (
                <button
                  key={i}
                  onClick={() => setCurrentIndex(i)}
                  className={`w-6 h-6 rounded text-xs transition-colors
                    ${i === currentIndex
                      ? 'bg-chess-accent text-chess-bg font-semibold'
                      : 'bg-chess-muted text-chess-text hover:bg-chess-border'}`}
                >
                  {i + 1}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
