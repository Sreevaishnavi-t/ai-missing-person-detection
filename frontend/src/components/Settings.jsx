import { useState } from 'react'
import { rebuildIndex, clearAllMatches, BASE_URL } from '../api'
import ConfirmModal from './ConfirmModal'

export default function Settings({
  showToast,
  isRunning,
  source,
  onSourceChange,
  onClearAll,
  threshold,
  onThresholdChange,
  skipFrames,
  onSkipFramesChange,
  autoShot,
  onAutoShotChange
}) {
  const [rebuilding, setRebuilding] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [showConfirmClear, setShowConfirmClear] = useState(false)

  const [mode, setMode] = useState(() => {
    if (source === 0 || source === '0') return '0'
    if (source === 1 || source === '1') return '1'
    return 'custom'
  })
  const [customPath, setCustomPath] = useState(() =>
    (source !== 0 && source !== 1) ? String(source) : ''
  )

  function handleModeChange(e) {
    const val = e.target.value
    setMode(val)
    if (val === '0') {
      onSourceChange(0)
      localStorage.setItem('detectionSource', '0')
    } else if (val === '1') {
      onSourceChange(1)
      localStorage.setItem('detectionSource', '1')
    }
  }

  function handleCustomPathChange(e) {
    const val = e.target.value
    setCustomPath(val)
    onSourceChange(val)
    localStorage.setItem('detectionSource', val)
  }

  async function handleRebuild() {
    if (isRunning) {
      showToast('Stop detection before rebuilding the index.', 'error')
      return
    }
    setRebuilding(true)
    try {
      const res = await rebuildIndex()
      showToast(res.message || 'FAISS index rebuilt successfully.', 'success')
    } catch (err) {
      showToast(`Rebuild failed: ${err.message}`, 'error')
    } finally {
      setRebuilding(false)
    }
  }

  async function executeClearMatches() {
    setShowConfirmClear(false)
    setClearing(true)
    try {
      const data = await clearAllMatches()
      showToast(`Cleared ${data.deleted} match record${data.deleted !== 1 ? 's' : ''}.`, 'success')
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

        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">Active:</span>
          <code className="text-xs bg-slate-900 text-blue-400 px-2 py-0.5 rounded
                           truncate max-w-[180px]" title={String(source)}>
            {String(source) || '—'}
          </code>
        </div>

        {isRunning && (
          <p className="text-xs text-amber-500">
            ⚠ Stop detection first to change settings.
          </p>
        )}
      </div>

      <div className="border-t border-slate-700" />

      {/* ── Confidence Threshold ── */}
      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
            Confidence Threshold
          </label>
          <span className="text-xs font-bold text-blue-400 bg-slate-900 px-2 py-0.5 rounded">
            {(threshold ?? 0.45).toFixed(2)}
          </span>
        </div>
        <input
          type="range"
          min={0.30} max={0.90} step={0.01}
          value={threshold ?? 0.45}
          disabled={isRunning}
          onChange={(e) => onThresholdChange && onThresholdChange(Number(e.target.value))}
          className="w-full accent-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
        />
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
          value={skipFrames ?? 3}
          disabled={isRunning}
          onChange={(e) => onSkipFramesChange && onSkipFramesChange(Number(e.target.value))}
          className="w-full accent-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
        />
        <p className="text-xs text-slate-600">
          {skipFrames === 1
            ? 'Max accuracy · max CPU'
            : `~${Math.round(30 / (skipFrames || 3))}fps detection from 30fps source`}
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
          onClick={() => !isRunning && onAutoShotChange && onAutoShotChange(!autoShot)}
          disabled={isRunning}
          className={`relative inline-flex h-6 w-11 items-center rounded-full
                      transition-colors focus:outline-none focus:ring-2
                      focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-900
                      disabled:opacity-50 disabled:cursor-not-allowed
                      ${autoShot ? 'bg-blue-600' : 'bg-slate-600'}`}
          role="switch"
          aria-checked={autoShot}
        >
          <span className={`inline-block h-4 w-4 transform rounded-full bg-white
                            transition-transform
                            ${autoShot ? 'translate-x-6' : 'translate-x-1'}`} />
        </button>
      </div>

      <div className="border-t border-slate-700" />

      {/* ── Clear all matches ── */}
      <div className="space-y-2">
        <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
          Danger Zone
        </p>
        <button
          onClick={() => setShowConfirmClear(true)}
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
        <a href={`${BASE_URL}/docs`} target="_blank" rel="noreferrer"
           className="flex items-center gap-2 text-xs text-blue-400 hover:text-blue-300">
          <span>↗</span> Swagger UI (test all endpoints)
        </a>
        <a href={`${BASE_URL}/stream`} target="_blank" rel="noreferrer"
           className="flex items-center gap-2 text-xs text-blue-400 hover:text-blue-300">
          <span>↗</span> Raw MJPEG stream
        </a>
      </div>

      {showConfirmClear && (
        <ConfirmModal
          title="Clear Match History"
          message="This will permanently delete all match records from the database. Screenshots on disk will be kept."
          onConfirm={executeClearMatches}
          onCancel={() => setShowConfirmClear(false)}
        />
      )}
    </div>
  )
}
