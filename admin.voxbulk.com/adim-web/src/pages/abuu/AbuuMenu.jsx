import React, { useCallback, useEffect, useState } from 'react'
import {
  createAbuuMenuCategory,
  createAbuuMenuItem,
  fetchAbuuRestaurants,
  uploadAbuuMenuItemPhoto,
} from '../../lib/abuuApi'
import { apiFetch } from '../../lib/api'

export default function AbuuMenu() {
  const [restaurants, setRestaurants] = useState([])
  const [restaurantId, setRestaurantId] = useState('')
  const [menu, setMenu] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [newCat, setNewCat] = useState({ name_en: '', name_ar: '' })
  const [newItem, setNewItem] = useState({ category_id: '', name_en: '', name_ar: '', item_type: 'meat', price_agorot: 4500 })

  const loadRestaurants = useCallback(async () => {
    const rows = await fetchAbuuRestaurants({ limit: 200 })
    setRestaurants(Array.isArray(rows) ? rows : [])
  }, [])

  const loadMenu = useCallback(async () => {
    if (!restaurantId) {
      setMenu([])
      return
    }
    const rows = await apiFetch(`/admin/abuu/restaurants/${restaurantId}/menu`)
    setMenu(Array.isArray(rows) ? rows : [])
  }, [restaurantId])

  useEffect(() => {
    loadRestaurants().catch((e) => setError(e.message))
  }, [loadRestaurants])

  useEffect(() => {
    setLoading(true)
    loadMenu()
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [loadMenu])

  const onCreateCategory = async () => {
    try {
      await createAbuuMenuCategory(restaurantId, newCat)
      setNewCat({ name_en: '', name_ar: '' })
      await loadMenu()
    } catch (e) {
      setError(e.message)
    }
  }

  const onCreateItem = async () => {
    try {
      await createAbuuMenuItem(newItem.category_id, newItem)
      await loadMenu()
    } catch (e) {
      setError(e.message)
    }
  }

  const onUploadPhoto = async (itemId, file) => {
    try {
      await uploadAbuuMenuItemPhoto(itemId, file)
      await loadMenu()
    } catch (e) {
      setError(e.message)
    }
  }

  const categories = menu.flatMap((cat) => [cat, ...(cat.subcategories || [])])

  return (
    <div className='card'>
      <div className='cardBody'>
        <label className='billingFilter'>
          Restaurant
          <select value={restaurantId} onChange={(e) => setRestaurantId(e.target.value)}>
            <option value=''>Select…</option>
            {restaurants.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name_en}
              </option>
            ))}
          </select>
        </label>
        {error ? <p className='formError'>{error}</p> : null}
        {!restaurantId ? <p className='muted'>Select a restaurant to manage menu.</p> : null}
        {restaurantId ? (
          <>
            <div className='billingPageToolbar' style={{ marginTop: 12 }}>
              <input placeholder='Category EN' value={newCat.name_en} onChange={(e) => setNewCat({ ...newCat, name_en: e.target.value })} />
              <input placeholder='Category AR' value={newCat.name_ar} onChange={(e) => setNewCat({ ...newCat, name_ar: e.target.value })} />
              <button type='button' className='btn primary sm' onClick={onCreateCategory}>
                Add category
              </button>
            </div>
            {loading ? (
              <p className='muted'>Loading menu…</p>
            ) : (
              menu.map((cat) => (
                <div key={cat.id} style={{ marginTop: 16 }}>
                  <h3>{cat.name_en} / {cat.name_ar}</h3>
                  <table className='table billingTable'>
                    <thead>
                      <tr>
                        <th>Photo</th>
                        <th>Item</th>
                        <th>Price</th>
                        <th>Upload</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(cat.items || []).map((item) => (
                        <tr key={item.id}>
                          <td>
                            {item.photo_url ? (
                              <img src={item.photo_url} alt='' style={{ width: 48, height: 48, objectFit: 'cover', borderRadius: 4 }} />
                            ) : (
                              <span className='muted'>—</span>
                            )}
                          </td>
                          <td>{item.name_en}</td>
                          <td>{(item.price_agorot / 100).toFixed(2)} ₪</td>
                          <td>
                            <input
                              type='file'
                              accept='image/*'
                              onChange={(e) => {
                                const file = e.target.files?.[0]
                                if (file) onUploadPhoto(item.id, file)
                              }}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))
            )}
            <div className='billingPageToolbar' style={{ marginTop: 12 }}>
              <select value={newItem.category_id} onChange={(e) => setNewItem({ ...newItem, category_id: e.target.value })}>
                <option value=''>Category for item…</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name_en}
                  </option>
                ))}
              </select>
              <input placeholder='Item EN' value={newItem.name_en} onChange={(e) => setNewItem({ ...newItem, name_en: e.target.value })} />
              <input placeholder='Item AR' value={newItem.name_ar} onChange={(e) => setNewItem({ ...newItem, name_ar: e.target.value })} />
              <input type='number' placeholder='Agorot' value={newItem.price_agorot} onChange={(e) => setNewItem({ ...newItem, price_agorot: Number(e.target.value) })} />
              <button type='button' className='btn sm' onClick={onCreateItem}>
                Add item
              </button>
            </div>
          </>
        ) : null}
      </div>
    </div>
  )
}
