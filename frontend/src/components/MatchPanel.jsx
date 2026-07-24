import { useState, useEffect } from 'react'
import { fetchResults, updateMatchStatus, BASE_URL } from '../api'
import Settings from './Settings'

const POLL_MS = 3000

function confidenceBadge(score) {
  const pct = Math.round(score * 100)
  if (score >= 0.80) return { pct, badgeCls: 'bg-green-600  text-green-100',  barCls: 'bg-green-500'  }
  if (score >= 0.60) return { pct, badgeCls: 'bg-amber-600  text-amber-100',  barCls: 'bg-amber-500'  }
  return               { pct, badgeCls: 'bg-red-700    text-red-100',    barCls: 'bg-red-500'    }
}

function formatTime(isoStr) {
  return new Date(isoStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function relativeTime(isoStr) {
  const diff = Math.floor((Date.now() - new Date(isoStr)) / 1000)
  if (diff < 10)    return 'just now'
  if (diff < 60)    return `${diff}s ago`
  if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return new Date(isoStr).toLocaleDateString()
}

function MatchCard({ match, onDismiss, onStatusUpdate }) {
  const { pct, badgeCls, barCls } = confidenceBadge(match.confidence)
  const imgSrc = match.screenshot_url ? `${BASE_URL}${match.screenshot_url}` : null

  function handleSave() {
    if (!imgSrc) return
    const a = document.createElement('a')
    a.href = imgSrc
    a.download = match.screenshot_url.split('/').pop()
    a.click()
  }

  return (
    <li className="bg-slate-700/40 hover:bg-slate-700/60 rounded-xl overflow-hidden
                   border border-slate-700/50 transition-colors">
      <div className="relative aspect-video bg-slate-900">
        {imgSrc ? (
          <img
            src={imgSrc}
            alt={`Match: ${match.person_name}`}
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-slate-600 text-xs">
            No screenshot
          </div>
        )}
        <span className={`absolute top-1.5 right-1.5 text-xs font-bold px-1.5 py-0.5 rounded-full ${badgeCls}`}>
          {pct}%
        </span>
      </div>

      <div className="px-3 py-2 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-semibold text-slate-100 truncate" title={match.person_name}>
            {match.person_name}
          </p>
          <p className="text-xs text-slate-500 flex-shrink-0" title={relativeTime(match.timestamp)}>
            {formatTime(match.timestamp)}
          </p>
        </div>

        <div>
          <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${barCls}`}
              style={{ width: `${pct}%` }}
              role="progressbar"
              aria-valuenow={pct}
              aria-valuemin={0}
              aria-valuemax={100}
            />
          </div>
        </div>

        <div className="flex gap-2 pt-0.5">
          {match.status === 'pending' ? (
            <>
              <button
                onClick={() => onStatusUpdate(match.id, 'approved')}
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium bg-green-900/40 hover:bg-green-800 border border-green-800 text-green-300 transition-colors"
              >
                Approve
              </button>
              <button
                onClick={() => onStatusUpdate(match.id, 'rejected')}
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium bg-red-900/40 hover:bg-red-800 border border-red-800 text-red-300 transition-colors"
              >
                Reject
              </button>
            </>
          ) : match.status === 'rejected' ? (
            <>
              <button
                onClick={() => onStatusUpdate(match.id, 'pending')}
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium bg-slate-700 hover:bg-slate-600 text-slate-200 transition-colors"
              >
                ↩ Restore to Pending
              </button>
              <button
                onClick={() => onDismiss(match.id)}
                className="py-1.5 px-2 rounded-lg text-xs font-medium bg-slate-800 hover:bg-red-900/50 text-slate-400 hover:text-red-300 transition-colors"
              >
                Dismiss
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleSave}
                disabled={!imgSrc}
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium bg-slate-600 hover:bg-slate-500 text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Save
              </button>
              <button
                onClick={() => onDismiss(match.id)}
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium bg-slate-700 hover:bg-red-900/50 text-slate-400 hover:text-red-300 transition-colors"
              >
                Dismiss
              </button>
            </>
          )}
        </div>
      </div>
    </li>
  )
}

export default function MatchPanel({
  showToast,
  isRunning,
  source,
  onSourceChange,
  threshold,
  onThresholdChange,
  skipFrames,
  onSkipFramesChange,
  autoShot,
  onAutoShotChange
}) {
  const [tab, setTab] = useState('matches')
  const [matches, setMatches] = useState([])
  const [loading, setLoading] = useState(true)
  const [dismissed, setDismissed] = useState(new Set())
  const [showRejected, setShowRejected] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const data = await fetchResults(50)
        if (!cancelled) {
          setMatches(data)
          setLoading(false)
        }
      } catch (err) {
        if (!cancelled) showToast(`Results: ${err.message}`, 'error')
      }
    }

    poll()
    const id = setInterval(poll, POLL_MS)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  function handleDismiss(id) {
    setDismissed((prev) => new Set([...prev, id]))
  }

  async function handleStatusUpdate(id, newStatus) {
    try {
      const updated = await updateMatchStatus(id, newStatus)
      setMatches(matches.map(m => m.id === id ? updated : m))
      showToast(`Match ${newStatus}.`, 'success')
    } catch (err) {
      showToast(`Failed to update status: ${err.message}`, 'error')
    }
  }

  const pending = matches.filter((m) => m.status === 'pending' && !dismissed.has(m.id))
  const approved = matches.filter((m) => m.status === 'approved' && !dismissed.has(m.id))
  const rejected = matches.filter((m) => m.status === 'rejected' && !dismissed.has(m.id))

  return (
    <div className="flex flex-col h-full">
      <div className="flex gap-1 mb-4 border-b border-slate-700 pb-2">
        {[
          { id: 'matches', label: 'Matches' },
          { id: 'settings', label: 'Settings' },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors
              ${tab === t.id
                ? 'bg-slate-700 text-slate-100'
                : 'text-slate-500 hover:text-slate-300 hover:bg-slate-700/50'
              }`}
          >
            {t.label}
            {t.id === 'matches' && pending.length > 0 && (
              <span className="ml-1.5 bg-red-700 text-white rounded-full px-1.5 py-0.5 text-xs animate-pulse">
                {pending.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {tab === 'matches' && (
        <>
          {loading ? (
            <div className="flex items-center justify-center flex-1 text-slate-500 text-sm gap-2">
              <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Loading…
            </div>
          ) : matches.filter(m => !dismissed.has(m.id)).length === 0 ? (
            <div className="flex flex-col items-center justify-center flex-1 text-slate-600 text-sm gap-2 py-8 text-center">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 opacity-20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              <p>No matches yet.</p>
              <p className="text-xs text-slate-700 max-w-[180px]">
                Enroll a person and start detection — matches appear here automatically.
              </p>
            </div>
          ) : (
            <div className="space-y-4 overflow-y-auto flex-1 pr-1">
              {pending.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-slate-400 uppercase mb-2">Needs Approval</h3>
                  <ul className="space-y-3">
                    {pending.map((m) => (
                      <MatchCard key={m.id} match={m} onDismiss={handleDismiss} onStatusUpdate={handleStatusUpdate} />
                    ))}
                  </ul>
                </div>
              )}
              {approved.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-slate-400 uppercase mb-2 mt-4">Verified Matches</h3>
                  <ul className="space-y-3">
                    {approved.map((m) => (
                      <MatchCard key={m.id} match={m} onDismiss={handleDismiss} onStatusUpdate={handleStatusUpdate} />
                    ))}
                  </ul>
                </div>
              )}
              {rejected.length > 0 && (
                <div>
                  <button
                    onClick={() => setShowRejected(!showRejected)}
                    className="text-xs font-semibold text-slate-500 hover:text-slate-400 uppercase mb-2 mt-4 flex items-center gap-1.5"
                  >
                    <span>{showRejected ? '▼' : '▶'}</span> Rejected Matches ({rejected.length})
                  </button>
                  {showRejected && (
                    <ul className="space-y-3">
                      {rejected.map((m) => (
                        <MatchCard key={m.id} match={m} onDismiss={handleDismiss} onStatusUpdate={handleStatusUpdate} />
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          )}

          <p className="text-xs text-slate-700 text-center mt-2">
            Auto-refreshes every 3 s
          </p>
        </>
      )}

      {tab === 'settings' && (
        <Settings
          showToast={showToast}
          isRunning={isRunning}
          source={source}
          onSourceChange={onSourceChange}
          onClearAll={() => { setMatches([]); setDismissed(new Set()) }}
          threshold={threshold}
          onThresholdChange={onThresholdChange}
          skipFrames={skipFrames}
          onSkipFramesChange={onSkipFramesChange}
          autoShot={autoShot}
          onAutoShotChange={setAutoShot}
        />
      )}
    </div>
  )
}
