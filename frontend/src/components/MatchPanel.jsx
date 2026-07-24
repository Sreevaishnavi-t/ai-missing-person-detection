import { useState, useEffect } from 'react'
import { fetchResults, updateMatchStatus, BASE_URL } from '../api'

/*
  MatchPanel — right panel with two tabs: "Matches" and "Settings".

  Guide spec (section 3 + 6):
    Matches tab:
      • Polls GET /results every 3 seconds — no manual refresh needed
      • Each match card shows:
          - Screenshot thumbnail (annotated frame)
          - Person name
          - Confidence badge: Green ≥ 80%, Amber 60–79%, Red < 60%
          - Confidence bar (visual fill)
          - Timestamp (HH:MM:SS)
          - Save button — downloads the screenshot
          - Dismiss button — removes from panel locally (not from SQLite)

    Settings tab (section 6):
      • Confidence threshold slider (0.30–0.90, default 0.45)
      • Skip frames slider (1–10, default 3)
      • Auto-screenshot toggle (default ON)
      • Clear all matches — danger button, clears the panel
      • Rebuild FAISS index — action button

  Props:
    showToast  {(msg, type) => void}  Parent notification dispatcher
    isRunning  {boolean}              Passed to Settings for rebuild warning

  Why Settings lives here (not a top navbar tab):
    The guide explicitly says "Access Settings from the third tab in the
    right panel". Keeping it here means the dashboard three-column layout
    is always visible — operators adjust settings while watching the feed.
*/

const POLL_MS = 3000

// Guide section 3: Green ≥ 80%, Amber 60–79%, Red < 60%
function confidenceBadge(score) {
  const pct = Math.round(score * 100)
  if (score >= 0.80) return { pct, badgeCls: 'bg-green-600  text-green-100',  barCls: 'bg-green-500'  }
  if (score >= 0.60) return { pct, badgeCls: 'bg-amber-600  text-amber-100',  barCls: 'bg-amber-500'  }
  return               { pct, badgeCls: 'bg-red-700    text-red-100',    barCls: 'bg-red-500'    }
}

function formatTime(isoStr) {
  // Guide: "Exact time the match was detected (HH:MM:SS)"
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

// ── MatchCard ─────────────────────────────────────────────────────────────
function MatchCard({ match, onDismiss, onStatusUpdate }) {
  const { pct, badgeCls, barCls } = confidenceBadge(match.confidence)
  const imgSrc = match.screenshot_url ? `${BASE_URL}${match.screenshot_url}` : null

  function handleSave() {
    // Guide: "Downloads the annotated screenshot to your downloads folder"
    if (!imgSrc) return
    const a = document.createElement('a')
    a.href = imgSrc
    a.download = match.screenshot_url.split('/').pop()
    a.click()
  }

  return (
    <li className="bg-slate-700/40 hover:bg-slate-700/60 rounded-xl overflow-hidden
                   border border-slate-700/50 transition-colors">

      {/* Screenshot thumbnail */}
      <div className="relative aspect-video bg-slate-900">
        {imgSrc ? (
          <img
            src={imgSrc}
            alt={`Match: ${match.person_name}`}
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center
                          text-slate-600 text-xs">
            No screenshot
          </div>
        )}
        {/* Confidence badge overlaid on image */}
        <span className={`absolute top-1.5 right-1.5 text-xs font-bold
                          px-1.5 py-0.5 rounded-full ${badgeCls}`}>
          {pct}%
        </span>
      </div>

      {/* Card body */}
      <div className="px-3 py-2 space-y-2">

        {/* Name + timestamp */}
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-semibold text-slate-100 truncate"
             title={match.person_name}>
            {match.person_name}
          </p>
          <p className="text-xs text-slate-500 flex-shrink-0"
             title={relativeTime(match.timestamp)}>
            {formatTime(match.timestamp)}
          </p>
        </div>

        {/* Confidence bar — visual fill */}
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

        {/* Actions based on status */}
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

// ── SettingsPanel ─────────────────────────────────────────────────────────
// Guide section 6: all controls that live in the Settings tab of the right panel
function SettingsPanel({ showToast, isRunning, source, onSourceChange, onClearAll }) {
  const [threshold,   setThreshold]   = useState(0.45)
  const [skipFrames,  setSkipFrames]  = useState(3)
  const [autoShot,    setAutoShot]    = useState(true)
  const [rebuilding,  setRebuilding]  = useState(false)
  const [clearing,    setClearing]    = useState(false)

  // ── Source selection ──────────────────────────────────────────────────
  // We keep a local `mode` string ('0', '1', or 'custom') separate from the
  // `source` prop (which holds the actual value passed to the backend).
  // This fixes two bugs:
  //   1. DOM <option> values are always strings; comparing "0" === 0 is false
  //      in strict equality, causing isPreset to mis-fire.
  //   2. When the user picks "custom", we need to show the text box immediately
  //      even before they've typed anything — mode controls that, not source.
  const [mode, setMode] = useState(() => {
    if (source === 0 || source === '0') return '0'
    if (source === 1 || source === '1') return '1'
    return 'custom'
  })
  const [customPath, setCustomPath] = useState(() =>
    (source !== 0 && source !== 1) ? String(source) : ''
  )

  function handleModeChange(e) {
    const val = e.target.value   // '0', '1', or 'custom'
    setMode(val)
    if (val === '0') {
      onSourceChange(0)
      localStorage.setItem('detectionSource', '0')
    } else if (val === '1') {
      onSourceChange(1)
      localStorage.setItem('detectionSource', '1')
    }
    // For 'custom' we wait until the user types in the text box
  }

  function handleCustomPathChange(e) {
    const val = e.target.value
    setCustomPath(val)
    onSourceChange(val)
    localStorage.setItem('detectionSource', val)
  }

  async function handleRebuild() {
    // Guide: "Rebuild FAISS index — Re-reads all photos in data/watchlist/"
    if (isRunning) {
      showToast('Stop detection before rebuilding the index.', 'error')
      return
    }
    setRebuilding(true)
    try {
      const res = await fetch('http://localhost:8000/rebuild-index', { method: 'POST' })
      if (!res.ok) throw new Error(`Rebuild failed (${res.status})`)
      showToast('FAISS index rebuilt successfully.', 'success')
    } catch {
      // Endpoint may not exist yet — show a clear message
      showToast('Rebuild endpoint not available yet. Add POST /rebuild-index to the backend.', 'info')
    } finally {
      setRebuilding(false)
    }
  }

  async function handleClearMatches() {
    if (!window.confirm(
      'This will permanently delete all match records from the database.\n' +
      'Screenshots on disk are NOT deleted.\n\n' +
      'Cannot be undone. Continue?'
    )) return

    setClearing(true)
    try {
      const res = await fetch('http://localhost:8000/results/all', { method: 'DELETE' })
      if (!res.ok) throw new Error(`Server returned ${res.status}`)
      const data = await res.json()
      showToast(`Cleared ${data.deleted} match record${data.deleted !== 1 ? 's' : ''}.`, 'success')
      // Tell MatchPanel to empty its local state immediately
      if (onClearAll) onClearAll()
    } catch (err) {
      showToast(`Clear failed: ${err.message}`, 'error')
    } finally {
      setClearing(false)
    }
  }

  return (
    <div className="space-y-5 overflow-y-auto flex-1 pr-1">

      {/* ── Detection Source ── */}
      <div className="space-y-2">
        <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
          Detection Source
        </p>
        <p className="text-xs text-slate-500">
          Choose what OpenCV reads frames from. Change this before pressing Start Detection.
        </p>

        {/* Mode dropdown */}
        <select
          value={mode}
          onChange={handleModeChange}
          disabled={isRunning}
          className="w-full bg-slate-900 border border-slate-600 rounded-lg
                     px-3 py-2 text-sm text-slate-100
                     focus:outline-none focus:ring-2 focus:ring-blue-500
                     disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <option value="0">Built-in webcam (0)</option>
          <option value="1">USB / external cam (1)</option>
          <option value="custom">Video file or RTSP URL…</option>
        </select>

        {/* Text box — shown when 'custom' is selected */}
        {mode === 'custom' && (
          <input
            type="text"
            value={customPath}
            onChange={handleCustomPathChange}
            disabled={isRunning}
            placeholder="e.g.  C:\videos\cctv.mp4   or   rtsp://192.168.1.1/stream"
            className="w-full bg-slate-900 border border-blue-600 rounded-lg
                       px-3 py-2 text-sm text-slate-100 placeholder-slate-600
                       focus:outline-none focus:ring-2 focus:ring-blue-500
                       disabled:opacity-50 disabled:cursor-not-allowed"
            autoFocus
          />
        )}

        {/* Active source display */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">Active:</span>
          <code className="text-xs bg-slate-900 text-blue-400 px-2 py-0.5 rounded
                           truncate max-w-[180px]" title={String(source)}>
            {String(source) || '—'}
          </code>
        </div>

        {isRunning && (
          <p className="text-xs text-amber-500">
            ⚠ Stop detection first to change source.
          </p>
        )}
      </div>

      <div className="border-t border-slate-700" />
      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
            Confidence Threshold
          </label>
          <span className="text-xs font-bold text-blue-400 bg-slate-900 px-2 py-0.5 rounded">
            {threshold.toFixed(2)}
          </span>
        </div>
        <input
          type="range"
          min={0.30} max={0.90} step={0.01}
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
          className="w-full accent-blue-500"
        />
        {/* Guide colour bands explanation */}
        <div className="grid grid-cols-3 gap-1 text-xs">
          <div className="bg-red-900/40 rounded px-2 py-1 text-red-300 text-center">
            <div className="font-semibold">0.30–0.45</div>
            <div className="text-red-400/70">Loose</div>
          </div>
          <div className="bg-amber-900/40 rounded px-2 py-1 text-amber-300 text-center">
            <div className="font-semibold">0.45–0.60</div>
            <div className="text-amber-400/70">Balanced</div>
          </div>
          <div className="bg-green-900/40 rounded px-2 py-1 text-green-300 text-center">
            <div className="font-semibold">0.60–0.90</div>
            <div className="text-green-400/70">Strict</div>
          </div>
        </div>
      </div>

      {/* ── Skip frames ── */}
      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
            Skip Every N Frames
          </label>
          <span className="text-xs font-bold text-blue-400 bg-slate-900 px-2 py-0.5 rounded">
            {skipFrames === 1 ? 'Every frame' : `Every ${skipFrames}rd`}
          </span>
        </div>
        <input
          type="range"
          min={1} max={10} step={1}
          value={skipFrames}
          onChange={(e) => setSkipFrames(Number(e.target.value))}
          className="w-full accent-blue-500"
        />
        <p className="text-xs text-slate-600">
          {skipFrames === 1
            ? 'Max accuracy · max CPU'
            : `~${Math.round(30 / skipFrames)}fps detection from 30fps source`}
        </p>
      </div>

      {/* ── Auto-screenshot toggle ── */}
      <div className="flex items-center justify-between p-3 bg-slate-900/60
                      rounded-xl border border-slate-700">
        <div>
          <p className="text-sm font-medium text-slate-200">Auto-screenshot on match</p>
          <p className="text-xs text-slate-500 mt-0.5">
            Save annotated frame to data/screenshots/ on every match
          </p>
        </div>
        <button
          onClick={() => setAutoShot((v) => !v)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full
                      transition-colors focus:outline-none focus:ring-2
                      focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-900
                      ${autoShot ? 'bg-blue-600' : 'bg-slate-600'}`}
          role="switch"
          aria-checked={autoShot}
        >
          <span className={`inline-block h-4 w-4 transform rounded-full bg-white
                            transition-transform
                            ${autoShot ? 'translate-x-6' : 'translate-x-1'}`} />
        </button>
      </div>

      {/* ── Divider ── */}
      <div className="border-t border-slate-700" />

      {/* ── Clear all matches ── */}
      <div className="space-y-2">
        <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
          Danger Zone
        </p>
        <button
          onClick={handleClearMatches}
          disabled={clearing}
          className="w-full py-2.5 rounded-lg text-sm font-semibold
                     bg-red-900/40 hover:bg-red-800/60 border border-red-800
                     text-red-300 transition-colors disabled:opacity-50
                     disabled:cursor-not-allowed"
        >
          {clearing ? 'Clearing…' : '🗑 Clear All Match History'}
        </button>
        <p className="text-xs text-slate-600">
          Removes all records from SQLite. Screenshots on disk are kept.
        </p>
      </div>

      {/* ── Rebuild FAISS index ── */}
      <div className="space-y-2">
        <button
          onClick={handleRebuild}
          disabled={rebuilding || isRunning}
          className="w-full py-2.5 rounded-lg text-sm font-semibold
                     bg-slate-700 hover:bg-slate-600 border border-slate-600
                     text-slate-200 transition-colors disabled:opacity-50
                     disabled:cursor-not-allowed"
        >
          {rebuilding ? 'Rebuilding…' : '⟳ Rebuild FAISS Index'}
        </button>
        <p className="text-xs text-slate-600">
          {isRunning
            ? 'Stop detection first before rebuilding.'
            : 'Re-reads all watchlist photos and regenerates embeddings.'}
        </p>
      </div>

      {/* ── API info ── */}
      <div className="border-t border-slate-700 pt-4 space-y-2">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
          Quick Links
        </p>
        <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer"
           className="flex items-center gap-2 text-xs text-blue-400 hover:text-blue-300">
          <span>↗</span> Swagger UI (test all endpoints)
        </a>
        <a href="http://localhost:8000/stream" target="_blank" rel="noreferrer"
           className="flex items-center gap-2 text-xs text-blue-400 hover:text-blue-300">
          <span>↗</span> Raw MJPEG stream
        </a>
      </div>
    </div>
  )
}

// ── MatchPanel (exported) — right panel with Matches | Settings tabs ──────
export default function MatchPanel({ showToast, isRunning, source, onSourceChange }) {
  const [tab,        setTab]        = useState('matches')
  const [matches,    setMatches]    = useState([])
  const [loading,    setLoading]    = useState(true)
  // dismissed holds IDs removed locally via Dismiss (not deleted from SQLite)
  const [dismissed,  setDismissed]  = useState(new Set())

  // Poll GET /results every 3 seconds.
  // We poll regardless of isRunning so you can still see historical matches
  // when detection is stopped — but we stop adding NEW matches to the log
  // from the detector side.  The poll simply reflects what's in SQLite.
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
    // Guide: "Removes this match from the panel — does not delete from SQLite"
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

  return (
    <div className="flex flex-col h-full">

      {/* ── Tab header: Matches | Settings ── */}
      <div className="flex gap-1 mb-4 border-b border-slate-700 pb-2">
        {[
          { id: 'matches',  label: 'Matches' },
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
              <span className="ml-1.5 bg-red-700 text-white rounded-full
                               px-1.5 py-0.5 text-xs animate-pulse">
                {pending.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Matches tab ── */}
      {tab === 'matches' && (
        <>
          {loading ? (
            <div className="flex items-center justify-center flex-1 text-slate-500 text-sm gap-2">
              <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg"
                   fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10"
                        stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Loading…
            </div>
          ) : matches.filter(m => !dismissed.has(m.id)).length === 0 ? (
            <div className="flex flex-col items-center justify-center flex-1
                            text-slate-600 text-sm gap-2 py-8 text-center">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 opacity-20"
                   fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
                      d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0
                         002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0
                         002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
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
            </div>
          )}

          {/* Guide tip: auto-refreshes */}
          <p className="text-xs text-slate-700 text-center mt-2">
            Auto-refreshes every 3 s
          </p>
        </>
      )}

      {/* ── Settings tab ── */}
      {tab === 'settings' && (
        <SettingsPanel
          showToast={showToast}
          isRunning={isRunning}
          source={source}
          onSourceChange={onSourceChange}
          onClearAll={() => { setMatches([]); setDismissed(new Set()) }}
        />
      )}
    </div>
  )
}
