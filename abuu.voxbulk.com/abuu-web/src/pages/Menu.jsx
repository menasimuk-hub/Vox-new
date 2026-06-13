import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'

function shekel(agorot) {
  return `${(Number(agorot || 0) / 100).toFixed(2)} ₪`
}

const emptyItem = { name_en: '', name_ar: '', item_type: 'meat', price_agorot: 4500, is_available: true }

export default function Menu() {
  const [categories, setCategories] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [newCat, setNewCat] = useState({ name_en: '', name_ar: '' })
  const [newItem, setNewItem] = useState({ categoryId: '', ...emptyItem })

  const load = useCallback(async () => {
    const data = await apiFetch('/abuu/restaurant/menu')
    setCategories(Array.isArray(data) ? data : [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const createCategory = async () => {
    setBusy('cat')
    try {
      await apiFetch('/abuu/restaurant/menu/categories', {
        method: 'POST',
        body: JSON.stringify(newCat),
      })
      setNewCat({ name_en: '', name_ar: '' })
      await load()
    } catch (e) {
      setError(e.message || 'Create category failed')
    } finally {
      setBusy('')
    }
  }

  const createItem = async () => {
    if (!newItem.categoryId) return
    setBusy('item')
    try {
      await apiFetch(`/abuu/restaurant/menu/categories/${newItem.categoryId}/items`, {
        method: 'POST',
        body: JSON.stringify(newItem),
      })
      setNewItem({ categoryId: newItem.categoryId, ...emptyItem })
      await load()
    } catch (e) {
      setError(e.message || 'Create item failed')
    } finally {
      setBusy('')
    }
  }

  const toggleItem = async (item) => {
    setBusy(item.id)
    try {
      await apiFetch(`/abuu/restaurant/menu/items/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_available: !item.is_available }),
      })
      await load()
    } catch (e) {
      setError(e.message || 'Update failed')
    } finally {
      setBusy('')
    }
  }

  const deleteItem = async (itemId) => {
    setBusy(itemId)
    try {
      await apiFetch(`/abuu/restaurant/menu/items/${itemId}`, { method: 'DELETE' })
      await load()
    } catch (e) {
      setError(e.message || 'Delete failed')
    } finally {
      setBusy('')
    }
  }

  const uploadPhoto = async (itemId, file) => {
    setBusy(itemId)
    try {
      const form = new FormData()
      form.append('file', file)
      const token = localStorage.getItem('access_token')
      const resp = await fetch(`/api/abuu/restaurant/menu/items/${itemId}/photo`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.detail || 'Upload failed')
      }
      await load()
    } catch (e) {
      setError(e.message || 'Upload failed')
    } finally {
      setBusy('')
    }
  }

  return (
    <div className='card'>
      <h2>Menu</h2>
      {error ? <p className='error'>{error}</p> : null}
      <div className='form' style={{ marginBottom: 16 }}>
        <h3>New category</h3>
        <input placeholder='Name EN' value={newCat.name_en} onChange={(e) => setNewCat({ ...newCat, name_en: e.target.value })} />
        <input placeholder='Name AR' value={newCat.name_ar} onChange={(e) => setNewCat({ ...newCat, name_ar: e.target.value })} />
        <button type='button' className='btn primary' disabled={busy === 'cat'} onClick={createCategory}>
          Add category
        </button>
      </div>
      {loading ? (
        <p className='muted'>Loading…</p>
      ) : (
        categories.map((cat) => (
          <section key={cat.id} style={{ marginBottom: 20 }}>
            <h3>{cat.name_ar || cat.name_en}</h3>
            {(cat.subcategories || []).map((sub) => (
              <div key={sub.id} className='muted small'>
                Sub: {sub.name_ar || sub.name_en}
              </div>
            ))}
            <table className='table'>
              <thead>
                <tr>
                  <th>Photo</th>
                  <th>Item</th>
                  <th>Type</th>
                  <th>Price</th>
                  <th>Available</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(cat.items || []).map((item) => (
                  <tr key={item.id}>
                    <td>
                      {item.photo_url ? (
                        <img src={item.photo_url} alt='' style={{ width: 48, height: 48, objectFit: 'cover', borderRadius: 4 }} />
                      ) : (
                        <input
                          type='file'
                          accept='image/*'
                          disabled={busy === item.id}
                          onChange={(e) => {
                            const file = e.target.files?.[0]
                            if (file) uploadPhoto(item.id, file)
                          }}
                        />
                      )}
                    </td>
                    <td>{item.name_ar || item.name_en}</td>
                    <td>{item.item_type}</td>
                    <td>{shekel(item.price_agorot)}</td>
                    <td>{item.is_available ? 'Yes' : 'No'}</td>
                    <td>
                      <button type='button' className='btn sm' disabled={busy === item.id} onClick={() => toggleItem(item)}>
                        Toggle
                      </button>
                      <button type='button' className='btn sm' disabled={busy === item.id} onClick={() => deleteItem(item.id)}>
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))
      )}
      <div className='form'>
        <h3>New item</h3>
        <select value={newItem.categoryId} onChange={(e) => setNewItem({ ...newItem, categoryId: e.target.value })}>
          <option value=''>Category…</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name_ar || c.name_en}
            </option>
          ))}
        </select>
        <input placeholder='Name EN' value={newItem.name_en} onChange={(e) => setNewItem({ ...newItem, name_en: e.target.value })} />
        <input placeholder='Name AR' value={newItem.name_ar} onChange={(e) => setNewItem({ ...newItem, name_ar: e.target.value })} />
        <select value={newItem.item_type} onChange={(e) => setNewItem({ ...newItem, item_type: e.target.value })}>
          {['meat', 'salad', 'drinks', 'sides', 'desserts'].map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input type='number' placeholder='Price agorot' value={newItem.price_agorot} onChange={(e) => setNewItem({ ...newItem, price_agorot: Number(e.target.value) })} />
        <button type='button' className='btn primary' disabled={busy === 'item'} onClick={createItem}>
          Add item
        </button>
      </div>
    </div>
  )
}
