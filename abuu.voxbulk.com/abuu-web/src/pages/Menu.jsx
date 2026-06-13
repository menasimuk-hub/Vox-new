import React, { useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'

function shekel(agorot) {
  return `${(Number(agorot || 0) / 100).toFixed(2)} ₪`
}

export default function Menu() {
  const [categories, setCategories] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await apiFetch('/abuu/restaurant/menu')
        if (!cancelled) setCategories(Array.isArray(data) ? data : [])
      } catch (e) {
        if (!cancelled) setError(e.message || 'Load failed')
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
      <h2>Menu</h2>
      {error ? <p className='error'>{error}</p> : null}
      {loading ? (
        <p className='muted'>Loading…</p>
      ) : (
        categories.map((cat) => (
          <section key={cat.id} style={{ marginBottom: 20 }}>
            <h3>{cat.name_ar || cat.name_en}</h3>
            <table className='table'>
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Type</th>
                  <th>Price</th>
                  <th>Available</th>
                </tr>
              </thead>
              <tbody>
                {(cat.items || []).map((item) => (
                  <tr key={item.id}>
                    <td>{item.name_ar || item.name_en}</td>
                    <td>{item.item_type}</td>
                    <td>{shekel(item.price_agorot)}</td>
                    <td>{item.is_available ? 'Yes' : 'No'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))
      )}
    </div>
  )
}
