export const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export async function fetchWatchlist() {
  const res = await fetch(`${BASE_URL}/watchlist`)
  if (!res.ok) throw new Error(`GET /watchlist failed: ${res.status}`)
  return res.json()
}

export async function deleteFromWatchlist(id) {
  const res = await fetch(`${BASE_URL}/watchlist/${id}`, { method: 'DELETE' })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? `Delete failed (${res.status})`)
  return data
}

export async function enrollPerson(fd) {
  const res = await fetch(`${BASE_URL}/enroll`, {
    method: 'POST',
    body: fd,
  })

  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? `Enrollment failed (${res.status})`)
  return data
}

export async function startDetection(source = 0, stopOnMatch = false) {
  const res = await fetch(`${BASE_URL}/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source, stop_on_match: stopOnMatch }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? `Start failed (${res.status})`)
  return data
}

export async function stopDetection() {
  const res = await fetch(`${BASE_URL}/stop`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? `Stop failed (${res.status})`)
  return data
}

export async function fetchResults(limit = 50) {
  const res = await fetch(`${BASE_URL}/results?limit=${limit}`)
  if (!res.ok) throw new Error(`GET /results failed: ${res.status}`)
  return res.json()
}

export async function fetchStatus() {
  const res = await fetch(`${BASE_URL}/status`)
  if (!res.ok) throw new Error(`GET /status failed: ${res.status}`)
  return res.json()
}

export async function updateMatchStatus(id, status) {
  const res = await fetch(`${BASE_URL}/results/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status })
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? `Update failed (${res.status})`)
  return data
}
