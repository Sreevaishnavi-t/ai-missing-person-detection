import { useState, useEffect } from 'react'
import { startDetection, stopDetection, fetchStatus } from '../api'
import { BASE_URL } from '../api'

export default function LiveFeed({
  isRunning,
  onRunningChange,
  source = 0,
  showToast,
  threshold = 0.45,
  skipFrames = 3,
  autoShot = true
}) {
  const [loading,   setLoading]   = useState(false)
  const [streamKey, setStreamKey] = useState(() => Date.now())
  const [stopOnMatch, setStopOnMatch] = useState(true)

  // Poll status endpoint to sync frontend with backend thread state
  useEffect(() => {
    if (!isRunning) return
    const interval = setInterval(async () => {
      try {
        const { is_running } = await fetchStatus()
        if (!is_running) {
          onRunningChange(false)
        }
      } catch (e) {
        // Ignore network errors in polling
      }
    }, 2000)
    return () => clearInterval(interval)
  }, [isRunning, onRunningChange])

  async function handleStart() {
    setLoading(true)
    try {
      await startDetection(source, stopOnMatch, threshold, skipFrames, autoShot)
      onRunningChange(true)
      setStreamKey(Date.now())
    } catch (err) {
      showToast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  async function handleStop() {
    setLoading(true)
    try {
      await stopDetection()
      onRunningChange(false)
    } catch (err) {
      showToast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* ── Stream viewport ─────────────────────────────────────────── */}
      <div className="relative rounded-xl overflow-hidden bg-slate-900 border border-slate-700 flex-1 min-h-0 flex items-center justify-center">
        {isRunning ? (
          <>
            <img
              key={streamKey}
              src={`${BASE_URL}/stream?k=${streamKey}`}
              alt="Live detection feed"
              className="w-full h-full object-contain"
            />
            {/* Scanner animation overlay */}
            <div className="absolute inset-0 pointer-events-none overflow-hidden">
              <div className="w-full h-1 bg-green-500/50 shadow-[0_0_15px_3px_rgba(34,197,94,0.5)] animate-[scan_3s_ease-in-out_infinite]" />
            </div>
          </>
        ) : (
          /* Offline placeholder */
          <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-600 gap-3 select-none">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-20 w-20 opacity-20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={0.8} d="M15 10l4.553-2.069A1 1 0 0121 8.867v6.266a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            <p className="text-sm">Press <span className="text-blue-400 font-medium">Start Detection</span> to begin</p>
          </div>
        )}

        {/* LIVE badge */}
        {isRunning && (
          <div className="absolute top-3 left-3 flex items-center gap-1.5 bg-black/60 backdrop-blur-sm rounded-full px-3 py-1 text-xs font-semibold text-white">
            <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse ring-2 ring-red-500/50" />
            LIVE
          </div>
        )}

        {/* Source label */}
        <div className="absolute bottom-3 right-3 bg-black/50 backdrop-blur-sm rounded-full px-2.5 py-0.5 text-xs text-slate-400">
          Source: {typeof source === 'number' ? `webcam (${source})` : source}
        </div>
      </div>

      {/* ── Controls ────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2 px-1">
          <input 
            type="checkbox" 
            id="stopOnMatch" 
            checked={stopOnMatch} 
            onChange={(e) => setStopOnMatch(e.target.checked)}
            disabled={isRunning}
            className="w-4 h-4 rounded bg-slate-800 border-slate-600 text-blue-500 focus:ring-blue-500 focus:ring-offset-slate-900"
          />
          <label htmlFor="stopOnMatch" className="text-sm text-slate-300 select-none cursor-pointer">
            Stop on first match
          </label>
        </div>
        <div className="flex gap-3">
          <button onClick={handleStart} disabled={isRunning || loading} className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-900">
            {loading && !isRunning ? (
              <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 0 0 8 8v4a1 1 0 0 0 1.555.832l3-2a1 1 0 0 0 0-1.664l-3-2z" clipRule="evenodd" />
              </svg>
            )}
            {loading && !isRunning ? 'Starting…' : 'Start Detection'}
          </button>
          <button onClick={handleStop} disabled={!isRunning || loading} className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold bg-slate-700 hover:bg-slate-600 active:bg-slate-800 text-slate-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2 focus:ring-offset-slate-900">
            {loading && isRunning ? (
              <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a1 1 0 00-1 1v4a1 1 0 001 1h4a1 1 0 001-1V8a1 1 0 00-1-1H8z" clipRule="evenodd" />
              </svg>
            )}
            {loading && isRunning ? 'Stopping…' : 'Stop Detection'}
          </button>
        </div>
      </div>
    </div>
  )
}
