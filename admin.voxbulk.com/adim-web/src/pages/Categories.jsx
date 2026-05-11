import React, { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../lib/api'

const PATCH_DEBOUNCE_MS = 550

function slugify(s) {
  return String(s || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
}

export default function Categories() {
  const [items, setItems] = useState(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const pendingPatchRef = useRef(new Map())
  const debounceTimersRef = useRef(new Map())

  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [description, setDescription] = useState('')

  const load = async () => {
    setError('')
    try {
      const rows = await apiFetch('/admin/categories')
      setItems(Array.isArray(rows) ? rows : [])
    } catch (e) {
      setItems([])
      setError(e?.message || 'Failed to load categories')
    }
  }

  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    return () => {
      for (const t of debounceTimersRef.current.values()) clearTimeout(t)
      debounceTimersRef.current.clear()
      pendingPatchRef.current.clear()
    }
  }, [])

  async function flushCategoryPatch(categoryId) {
    const timers = debounceTimersRef.current
    const pend = pendingPatchRef.current
    const tid = timers.get(categoryId)
    if (tid) {
      clearTimeout(tid)
      timers.delete(categoryId)
    }
    const payload = pend.get(categoryId)
    pend.delete(categoryId)
    if (!payload || typeof payload !== 'object' || Object.keys(payload).length === 0) return
    setSaving(true)
    setError('')
    try {
      await apiFetch(`/admin/categories/${categoryId}`, { method: 'PATCH', body: JSON.stringify(payload) })
      await load()
    } catch (e) {
      setError(e?.message || 'Save failed')
      await load()
    } finally {
      setSaving(false)
    }
  }

  function scheduleCategoryPatch(categoryId, fragment) {
    const pend = pendingPatchRef.current
    const timers = debounceTimersRef.current
    const prev = pend.get(categoryId) || {}
    pend.set(categoryId, { ...prev, ...fragment })
    const prevT = timers.get(categoryId)
    if (prevT) clearTimeout(prevT)
    const t = setTimeout(() => {
      timers.delete(categoryId)
      const payload = pend.get(categoryId)
      pend.delete(categoryId)
      if (!payload || Object.keys(payload).length === 0) return
      setSaving(true)
      setError('')
      apiFetch(`/admin/categories/${categoryId}`, { method: 'PATCH', body: JSON.stringify(payload) })
        .then(() => load())
        .catch(async (e) => {
          setError(e?.message || 'Save failed')
          await load()
        })
        .finally(() => setSaving(false))
    }, PATCH_DEBOUNCE_MS)
    timers.set(categoryId, t)
  }

  function updateCategoryField(categoryId, field, value) {
    setItems((list) =>
      Array.isArray(list) ? list.map((c) => (c.id === categoryId ? { ...c, [field]: value } : c)) : list
    )
    scheduleCategoryPatch(categoryId, { [field]: value })
  }

  const create = async () => {
    const n = name.trim()
    if (!n) {
      window.alert('Name is required.')
      return
    }
    const s = (slug || slugify(n)).trim()
    if (!s) {
      window.alert('Slug is required.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await apiFetch('/admin/categories', {
        method: 'POST',
        body: JSON.stringify({
          name: n,
          slug: s,
          description: description.trim() ? description.trim() : null,
        }),
      })
      setName('')
      setSlug('')
      setDescription('')
      await load()
    } catch (e) {
      setError(e?.message || 'Create failed')
    } finally {
      setSaving(false)
    }
  }

  const remove = async (id) => {
    if (!window.confirm('Delete this category? Organisations will be unassigned.')) return
    await flushCategoryPatch(id)
    setSaving(true)
    setError('')
    try {
      await apiFetch(`/admin/categories/${id}`, { method: 'DELETE' })
      await load()
    } catch (e) {
      setError(e?.message || 'Delete failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Categories</h1>
          <p>Create and manage dashboard setup categories. Services API entries connect to these by slug.</p>
        </div>
        <div className='actions'>
          <button className='btn' onClick={load} disabled={saving}>
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className='card' style={{ marginBottom: 16, borderColor: '#fecaca' }}>
          <div className='cardBody' style={{ color: '#b91c1c', fontSize: 14 }}>
            {error}
          </div>
        </div>
      )}

      <div className='categoriesPageGrid'>
        <div className='stack'>
          <div className='card'>
            <div className='cardHead'>
              <h3>New category</h3>
              <span className='pill p-cyan'>Global</span>
            </div>
            <div className='cardBody stack' style={{ display: 'grid', gap: 12 }}>
              <label className='formField'>
                <span className='label' style={{ textTransform: 'none', letterSpacing: 'normal', fontWeight: 600 }}>
                  Name
                </span>
                <input className='input' value={name} onChange={(e) => setName(e.target.value)} placeholder='Dental' />
              </label>
              <label className='formField'>
                <span className='label' style={{ textTransform: 'none', letterSpacing: 'normal', fontWeight: 600 }}>
                  Slug
                </span>
                <input
                  className='input'
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  placeholder='dental'
                />
                <div className='muted' style={{ fontSize: 12 }}>
                  Used internally and by Services API category mapping. Leave blank to auto-generate from name.
                </div>
              </label>
              <label className='formField'>
                <span className='label' style={{ textTransform: 'none', letterSpacing: 'normal', fontWeight: 600 }}>
                  Description (optional)
                </span>
                <textarea
                  className='input'
                  rows={4}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder='Notes about this category…'
                />
              </label>
              <button type='button' className='btn primary' onClick={create} disabled={saving}>
                {saving ? 'Saving…' : 'Create category'}
              </button>
            </div>
          </div>
        </div>

        <div className='stack' style={{ minWidth: 0 }}>
          <div className='card'>
            <div className='cardHead'>
              <h3>All categories</h3>
              <span className='pill p-cyan'>{Array.isArray(items) ? `${items.length}` : '—'}</span>
            </div>
            <div className='cardBody'>
              <div className='tableWrap'>
                <table className='table categoriesTable'>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Slug</th>
                      <th>Description</th>
                      <th>Created</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {!items && (
                      <tr>
                        <td colSpan={5}>Loading…</td>
                      </tr>
                    )}
                    {items &&
                      items.map((c) => (
                        <tr key={c.id}>
                          <td className='cat-cellName'>
                            <input
                              className='input'
                              aria-label={`Category name for ${c.slug || c.id}`}
                              value={c.name || ''}
                              onChange={(e) => updateCategoryField(c.id, 'name', e.target.value)}
                              onBlur={() => flushCategoryPatch(c.id)}
                              disabled={saving}
                            />
                          </td>
                          <td>
                            <input
                              className='input catSlugInput'
                              aria-label={`Slug for ${c.name || c.id}`}
                              value={c.slug || ''}
                              onChange={(e) => updateCategoryField(c.id, 'slug', e.target.value)}
                              onBlur={() => flushCategoryPatch(c.id)}
                              disabled={saving}
                            />
                          </td>
                          <td>
                            <textarea
                              className='input'
                              rows={2}
                              aria-label={`Description for ${c.name || c.slug}`}
                              value={c.description || ''}
                              onChange={(e) => updateCategoryField(c.id, 'description', e.target.value || null)}
                              onBlur={() => flushCategoryPatch(c.id)}
                              disabled={saving}
                              placeholder='Optional description…'
                            />
                          </td>
                          <td>{c.created_at ? new Date(c.created_at).toLocaleString() : '—'}</td>
                          <td>
                            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                              <button type='button' className='btn soft' onClick={() => remove(c.id)} disabled={saving}>
                                Delete
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    {items && items.length === 0 && (
                      <tr>
                        <td colSpan={5}>No categories yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className='muted' style={{ fontSize: 12, marginTop: 10 }}>
                Edits save after a short pause or when you leave a field.
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

