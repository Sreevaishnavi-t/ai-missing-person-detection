import { useState } from 'react'
import Watchlist   from './components/Watchlist'
import LiveFeed    from './components/LiveFeed'
import MatchPanel  from './components/MatchPanel'
import EnrollModal from './components/EnrollModal'
import Toast       from './components/Toast'

/*
  App — root layout following the WatchlistAI Developer Operations Guide.

  Layout (guide page 1):
  ┌──────────────────────────────────────────────────────────────────────┐
  │  Navbar: logo · status dot · "Enroll Person" shortcut button        │
  ├──────────────────┬───────────────────────────┬───────────────────────┤
  │  LEFT SIDEBAR    │      CENTRE PANEL         │    RIGHT PANEL        │
  │  Watchlist       │      LiveFeed             │    MatchPanel         │
  │  (w-60)          │      (flex-1)             │    (w-80)             │
  │                  │                           │                       │
  │  Enrolled list   │  MJPEG stream             │  Tab: Matches         │
  │  + trash icons   │  + Start/Stop buttons     │  Tab: Settings        │
  │                  │                           │                       │
  │  [Enroll new]    │                           │  (guide section 6)    │
  │  button at       │                           │                       │
  │  bottom          │                           │                       │
  └──────────────────┴───────────────────────────┴───────────────────────┘

  Guide reference:
    Section 1 step 2: "Enroll new person" at the BOTTOM of the left sidebar
    Section 3: Matches tab in the right panel
    Section 6: Settings tab in the right panel (NOT a top-level navbar tab)
*/

export default function App() {
  const [isRunning,    setIsRunning]    = useState(false)
  const [watchlistKey, setWatchlistKey] = useState(0)
  const [showEnroll,   setShowEnroll]   = useState(false)
  const [toast,        setToast]        = useState(null)

  // Video source — persisted to localStorage, editable in Settings panel
  const [source, setSource] = useState(() => {
    const saved = localStorage.getItem('detectionSource')
    if (saved === null) return 0
    const num = Number(saved)
    return Number.isNaN(num) ? saved : num
  })

  function showToast(message, type = 'info') {
    setToast({ message, type })
  }

  function handleEnrollSuccess(entry) {
    setShowEnroll(false)
    setWatchlistKey((k) => k + 1)  // triggers Watchlist re-fetch
    showToast(`"${entry.name}" enrolled successfully.`, 'success')
  }

  function handleDeleted() {
    setWatchlistKey((k) => k + 1)  // triggers Watchlist re-fetch
  }

  return (
    <div className="h-screen bg-slate-900 text-slate-100 flex flex-col overflow-hidden">

      {/* ── Navbar ────────────────────────────────────────────────────── */}
      <header className="flex-shrink-0 bg-slate-900/95 backdrop-blur-md
                         border-b border-slate-800 z-30">
        <div className="px-4 sm:px-5 flex items-center h-13 gap-4">

          {/* Brand */}
          <div className="flex items-center gap-2.5 flex-shrink-0">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-blue-500"
                 viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd"
                    d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0
                       0017.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8
                       11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541
                       3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0
                       00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                    clipRule="evenodd" />
            </svg>
            <span className="font-bold text-slate-100 text-sm tracking-tight">
              WatchlistAI
            </span>
            <span className="hidden sm:inline text-slate-600 text-sm">·</span>
            <span className="hidden sm:inline text-slate-500 text-xs">
              Missing Person Detection
            </span>
          </div>

          {/* Status dot — green + pulse when running */}
          <div className="flex items-center gap-2 text-xs ml-2">
            <span
              className={`h-2.5 w-2.5 rounded-full flex-shrink-0
                ${isRunning ? 'bg-green-500 animate-pulse' : 'bg-slate-600'}`}
              aria-label={isRunning ? 'Detection running' : 'Detection stopped'}
            />
            <span className={`hidden md:inline text-xs font-medium
              ${isRunning ? 'text-green-400' : 'text-slate-500'}`}>
              {isRunning ? 'Detection running' : 'Stopped'}
            </span>
          </div>

          <div className="flex-1" />

          {/* Quick enroll shortcut in navbar */}
          <button
            onClick={() => setShowEnroll(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs
                       font-semibold bg-blue-600 hover:bg-blue-500 text-white
                       transition-colors focus:outline-none focus:ring-2
                       focus:ring-blue-500 focus:ring-offset-2
                       focus:ring-offset-slate-900"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5"
                 viewBox="0 0 20 20" fill="currentColor">
              <path d="M8 9a3 3 0 100-6 3 3 0 000 6zM8 11a6 6 0 016 6H2a6 6 0 016-6z" />
              <path d="M16 7a1 1 0 10-2 0v1h-1a1 1 0 100 2h1v1a1 1 0 102 0v-1h1a1 1 0 100-2h-1V7z" />
            </svg>
            <span className="hidden sm:inline">Enroll Person</span>
          </button>
        </div>
      </header>

      {/* ── Three-column dashboard ────────────────────────────────────── */}
      <main className="flex-1 min-h-0 flex gap-4 p-4 overflow-hidden">

        {/* LEFT — Watchlist sidebar
            Guide: left sidebar with enrolled persons + "Enroll new person" at bottom */}
        <div className="w-60 flex-shrink-0 bg-slate-800 rounded-2xl
                        border border-slate-700 overflow-hidden flex flex-col p-4">
          <Watchlist
            refreshKey={watchlistKey}
            onDeleted={handleDeleted}
            showToast={showToast}
            onEnroll={() => setShowEnroll(true)}
          />
        </div>

        {/* CENTRE — Live feed
            Guide: MJPEG stream + Start/Stop buttons */}
        <div className="flex-1 min-w-0 bg-slate-800 rounded-2xl
                        border border-slate-700 flex flex-col p-4">
          <LiveFeed
            isRunning={isRunning}
            onRunningChange={setIsRunning}
            source={source}
            showToast={showToast}
          />
        </div>

        {/* RIGHT — Match panel (Matches tab + Settings tab)
            Guide section 3 + 6: "Access Settings from the third tab in the right panel" */}
        <div className="w-80 flex-shrink-0 bg-slate-800 rounded-2xl
                        border border-slate-700 overflow-hidden flex flex-col p-4">
          <MatchPanel
            showToast={showToast}
            isRunning={isRunning}
            source={source}
            onSourceChange={setSource}
          />
        </div>

      </main>

      {/* ── Enroll modal ─────────────────────────────────────────────── */}
      {showEnroll && (
        <EnrollModal
          onSuccess={handleEnrollSuccess}
          onClose={() => setShowEnroll(false)}
        />
      )}

      {/* ── Toast ────────────────────────────────────────────────────── */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onDismiss={() => setToast(null)}
        />
      )}
    </div>
  )
}
