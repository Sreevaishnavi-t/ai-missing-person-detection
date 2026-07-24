import { useState } from 'react'
import { enrollPerson } from '../api'

export default function EnrollModal({ onSuccess, onClose }) {
  const [name, setName] = useState('')
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!name || !file) return
    setLoading(true)
    try {
      const fd = new FormData()
      fd.append('name', name)
      fd.append('file', file)
      const res = await enrollPerson(fd)
      onSuccess(res)
    } catch(e) {
      alert('Error enrolling: ' + e.message)
    }
    setLoading(false)
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-neutral-800 p-6 rounded-2xl w-full max-w-md">
        <h2 className="text-xl font-bold text-neutral-100 mb-4">Enroll Person</h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <input type="text" placeholder="Name" className="bg-neutral-900 p-2 rounded text-neutral-100" value={name} onChange={e => setName(e.target.value)} required />
          <input type="file" accept="image/*" onChange={e => setFile(e.target.files[0])} required className="bg-neutral-900 p-2 rounded text-neutral-100" />
          <div className="flex gap-2 justify-end mt-4">
            <button type="button" onClick={onClose} className="px-4 py-2 bg-neutral-700 text-neutral-200 rounded">Cancel</button>
            <button type="submit" disabled={loading} className="px-4 py-2 bg-blue-600 text-white rounded">{loading ? '...' : 'Enroll'}</button>
          </div>
        </form>
      </div>
    </div>
  )
}
