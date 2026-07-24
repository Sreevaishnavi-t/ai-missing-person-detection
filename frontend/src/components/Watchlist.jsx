import { useState, useEffect } from 'react'
import { fetchWatchlist, deleteFromWatchlist } from '../api'
import ConfirmModal from './ConfirmModal'

export default function Watchlist({ refreshKey, onDeleted, showToast, onEnroll }) {
  const [people, setPeople] = useState([])
  const [loading, setLoading] = useState(true)
  const [deleteTarget, setDeleteTarget] = useState(null)

  useEffect(() => {
    fetchWatchlist().then(data => { setPeople(data); setLoading(false) }).catch(() => setLoading(false))
  }, [refreshKey])

  const confirmDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteFromWatchlist(deleteTarget.id)
      onDeleted()
      showToast(`Deleted ${deleteTarget.name} from watchlist.`, 'success')
    } catch (e) {
      showToast(`Error deleting: ${e.message}`, 'error')
    } finally {
      setDeleteTarget(null)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <h2 className="text-sm font-semibold text-neutral-400 uppercase tracking-wider mb-3 px-1">Watchlist</h2>
      <div className="flex-1 overflow-y-auto space-y-2">
        {loading ? (
          <p className="text-neutral-500 text-xs">Loading...</p>
        ) : people.length === 0 ? (
          <p className="text-xs text-neutral-500">Click "Enroll Person" to add someone.</p>
        ) : (
          people.map(p => (
            <div key={p.id} className="flex items-center justify-between bg-neutral-700/40 p-2.5 rounded-lg border border-neutral-700/50">
              <div>
                <p className="text-sm font-medium text-neutral-100">{p.name}</p>
                <p className="text-xs text-neutral-500">{new Date(p.enrolled_at).toLocaleDateString()}</p>
              </div>
              <button
                onClick={() => setDeleteTarget(p)}
                className="text-neutral-400 hover:text-red-400 px-2 py-1 text-xs font-semibold rounded hover:bg-red-900/30 transition-colors"
                title={`Delete ${p.name}`}
              >
                ✕
              </button>
            </div>
          ))
        )}
      </div>
      <div className="mt-3 pt-3 border-t border-neutral-700">
        <button onClick={onEnroll} className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-lg text-sm transition-colors">
          Enroll Person
        </button>
      </div>

      {deleteTarget && (
        <ConfirmModal
          title="Remove from Watchlist"
          message={`Are you sure you want to delete "${deleteTarget.name}" from the watchlist? This will rebuild the search index.`}
          onConfirm={confirmDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  )
}
