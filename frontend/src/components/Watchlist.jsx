import { useState, useEffect } from 'react'
import { fetchWatchlist, deleteFromWatchlist } from '../api'

export default function Watchlist({ refreshKey, onDeleted, showToast, onEnroll }) {
  const [people, setPeople] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchWatchlist().then(data => { setPeople(data); setLoading(false) }).catch(() => setLoading(false))
  }, [refreshKey])

  const handleDelete = async (id) => {
    try { await deleteFromWatchlist(id); onDeleted(); showToast('Deleted') } catch (e) { showToast('Error deleting', 'error') }
  }

  return (
    <div className="flex flex-col h-full">
      <h2 className="text-sm font-semibold text-neutral-400 uppercase tracking-wider mb-3 px-1">Watchlist</h2>
      <div className="flex-1 overflow-y-auto space-y-2">
        {loading ? <p className="text-neutral-500">Loading...</p> : people.length === 0 ? <p className="text-xs text-neutral-700">Click "Enroll Person" to add someone.</p> : people.map(p => (
          <div key={p.id} className="flex items-center justify-between bg-neutral-700/40 p-2 rounded">
            <div>
              <p className="text-sm font-medium text-neutral-100">{p.name}</p>
              <p className="text-xs text-neutral-500">{new Date(p.enrolled_at).toLocaleDateString()}</p>
            </div>
            <button onClick={() => handleDelete(p.id)} className="text-neutral-500 hover:text-red-400">x</button>
          </div>
        ))}
      </div>
      <div className="mt-3 pt-3 border-t border-neutral-700">
        <button onClick={onEnroll} className="w-full py-2 bg-blue-600 rounded text-sm">Enroll Person</button>
      </div>
    </div>
  )
}
