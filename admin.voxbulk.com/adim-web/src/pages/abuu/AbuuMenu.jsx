import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  createAbuuMenuCategory,
  createAbuuMenuItem,
  fetchAbuuRestaurants,
  patchAbuuMenuItem,
  uploadAbuuMenuItemPhoto,
} from '../../lib/abuuApi'
import { apiFetch } from '../../lib/api'

function parseTags(raw) {
  if (!raw) return ''
  if (Array.isArray(raw)) return raw.join(', ')
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.join(', ') : String(raw)
  } catch {
    return String(raw)
  }
}

function tagsToJson(value) {
  const tags = String(value || '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
  return tags.length ? tags : null
}

export default function AbuuMenu() {
  const [restaurants, setRestaurants] = useState([])
  const [restaurantId, setRestaurantId] = useState('')
  const [menu, setMenu] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [unclassifiedOnly, setUnclassifiedOnly] = useState(false)
  const [newCat, setNewCat] = useState({ name_en: '', name_ar: '' })
  const [newItem, setNewItem] = useState({ category_id: '', name_en: '', name_ar: '', item_type: 'meat', price_agorot: 4500 })
  const [edits, setEdits] = useState({})

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
    setEdits({})
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

  const onSaveItemTags = async (item) => {
    const draft = edits[item.id] || {}
    try {
      await patchAbuuMenuItem(item.id, {
        item_type: draft.item_type ?? item.item_type,
        classification_status: draft.classification_status ?? item.classification_status,
        allergen_tags_json: tagsToJson(draft.allergens ?? parseTags(item.allergen_tags_json)),
        dietary_tags_json: tagsToJson(draft.dietary ?? parseTags(item.dietary_tags_json)),
        recipe_tags_json: tagsToJson(draft.recipe ?? parseTags(item.recipe_tags_json)),
      })
      await loadMenu()
    } catch (e) {
      setError(e.message)
    }
  }

  const categories = menu.flatMap((cat) => [cat, ...(cat.subcategories || [])])

  const visibleItems = useMemo(() => {
    const rows = []
    for (const cat of menu) {
      for (const item of cat.items || []) {
        if (unclassifiedOnly && item.classification_status === 'classified') continue
        rows.push({ cat, item })
      }
    }
    return rows
  }, [menu, unclassifiedOnly])

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
        {restaurantId ? (
          <label className='billingFilter' style={{ marginLeft: 12 }}>
            <input type='checkbox' checked={unclassifiedOnly} onChange={(e) => setUnclassifiedOnly(e.target.checked)} />
            {' '}Unclassified only
          </label>
        ) : null}
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
              <table className='table billingTable' style={{ marginTop: 16 }}>
                <thead>
                  <tr>
                    <th>Photo</th>
                    <th>Item</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Allergens</th>
                    <th>Dietary</th>
                    <th>Recipe</th>
                    <th>Price</th>
                    <th>Save</th>
                    <th>Upload</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleItems.map(({ cat, item }) => {
                    const draft = edits[item.id] || {}
                    return (
                      <tr key={item.id}>
                        <td>
                          {item.photo_url ? (
                            <img src={item.photo_url} alt='' style={{ width: 48, height: 48, objectFit: 'cover', borderRadius: 4 }} />
                          ) : (
                            <span className='muted'>—</span>
                          )}
                        </td>
                        <td>
                          <div>{item.name_en}</div>
                          <div className='muted'>{cat.name_en}</div>
                        </td>
                        <td>
                          <input
                            className='input sm'
                            value={draft.item_type ?? item.item_type ?? ''}
                            onChange={(e) => setEdits((s) => ({ ...s, [item.id]: { ...draft, item_type: e.target.value } }))}
                          />
                        </td>
                        <td>
                          <select
                            value={draft.classification_status ?? item.classification_status ?? 'unclassified'}
                            onChange={(e) => setEdits((s) => ({ ...s, [item.id]: { ...draft, classification_status: e.target.value } }))}
                          >
                            <option value='unclassified'>unclassified</option>
                            <option value='classified'>classified</option>
                          </select>
                        </td>
                        <td>
                          <input
                            className='input sm'
                            placeholder='dairy, nuts'
                            value={draft.allergens ?? parseTags(item.allergen_tags_json)}
                            onChange={(e) => setEdits((s) => ({ ...s, [item.id]: { ...draft, allergens: e.target.value } }))}
                          />
                        </td>
                        <td>
                          <input
                            className='input sm'
                            placeholder='halal, vegetarian'
                            value={draft.dietary ?? parseTags(item.dietary_tags_json)}
                            onChange={(e) => setEdits((s) => ({ ...s, [item.id]: { ...draft, dietary: e.target.value } }))}
                          />
                        </td>
                        <td>
                          <input
                            className='input sm'
                            placeholder='grilled, fried'
                            value={draft.recipe ?? parseTags(item.recipe_tags_json)}
                            onChange={(e) => setEdits((s) => ({ ...s, [item.id]: { ...draft, recipe: e.target.value } }))}
                          />
                        </td>
                        <td>{(item.price_agorot / 100).toFixed(2)} ₪</td>
                        <td>
                          <button type='button' className='btn sm' onClick={() => onSaveItemTags(item)}>
                            Save
                          </button>
                        </td>
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
                    )
                  })}
                </tbody>
              </table>
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
