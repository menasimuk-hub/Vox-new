import React, { useEffect, useState } from 'react'
import { fetchAbuuRestaurants } from '../../lib/abuuApi'

export default function AbuuRestaurants() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        const data = await fetchAbuuRestaurants({ limit: 100 })
        if (!cancelled) setRows(Array.isArray(data) ? data : [])
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className='card'>
      <div className='cardBody'>
        {error ? <p className='formError'>{error}</p> : null}
        {loading ? (
          <p className='muted'>Loading restaurants…</p>
        ) : (
          <div className='tableWrap'>
            <table className='table'>
              <thead>
                <tr>
                  <th>Name (EN)</th>
                  <th>Name (AR)</th>
                  <th>Status</th>
                  <th>Available</th>
                  <th>Radius (km)</th>
                  <th>Login</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.name_en}</td>
                    <td dir='rtl'>{row.name_ar}</td>
                    <td>{row.status}</td>
                    <td>{row.is_available ? 'Yes' : 'No'}</td>
                    <td>{row.delivery_radius_km}</td>
                    <td>{row.login_email || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
