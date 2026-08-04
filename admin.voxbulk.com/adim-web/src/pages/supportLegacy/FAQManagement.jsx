import React, { useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'

const emptyCategory = { name: '', slug: '', sort_order: 0 }
const emptyItem = { category_id: '', question: '', answer: '', is_featured: false, is_published: true, sort_order: 0 }

export default function FAQManagement() {
  const [categories, setCategories] = useState([])
  const [items, setItems] = useState([])
  const [categoryForm, setCategoryForm] = useState(emptyCategory)
  const [itemForm, setItemForm] = useState(emptyItem)
  const [editingCategoryId, setEditingCategoryId] = useState(null)
  const [editingItemId, setEditingItemId] = useState(null)
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')

  const load = async () => {
    setError('')
    try {
      const qs = search.trim() ? `?search=${encodeURIComponent(search.trim())}&limit=200` : '?limit=200'
      const [cats, rows] = await Promise.all([apiFetch('/admin/faq/categories'), apiFetch(`/admin/faq/items${qs}`)])
      setCategories(Array.isArray(cats) ? cats : [])
      setItems(Array.isArray(rows) ? rows : [])
    } catch (e) {
      setError(e?.message || 'Could not load FAQs')
    }
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const saveCategory = async () => {
    if (!categoryForm.name.trim()) return
    await apiFetch(editingCategoryId ? `/admin/faq/categories/${editingCategoryId}` : '/admin/faq/categories', {
      method: editingCategoryId ? 'PUT' : 'POST',
      body: JSON.stringify({ ...categoryForm, sort_order: Number(categoryForm.sort_order || 0), slug: categoryForm.slug || null }),
    })
    setCategoryForm(emptyCategory)
    setEditingCategoryId(null)
    await load()
  }

  const editCategory = (c) => {
    setEditingCategoryId(c.id)
    setCategoryForm({ name: c.name || '', slug: c.slug || '', sort_order: c.sort_order || 0 })
  }

  const saveItem = async () => {
    if (!itemForm.question.trim() || !itemForm.answer.trim()) return
    await apiFetch(editingItemId ? `/admin/faq/items/${editingItemId}` : '/admin/faq/items', {
      method: editingItemId ? 'PUT' : 'POST',
      body: JSON.stringify({
        ...itemForm,
        category_id: itemForm.category_id ? Number(itemForm.category_id) : null,
        sort_order: Number(itemForm.sort_order || 0),
      }),
    })
    setItemForm(emptyItem)
    setEditingItemId(null)
    await load()
  }

  const editItem = (i) => {
    setEditingItemId(i.id)
    setItemForm({
      category_id: i.category_id || '',
      question: i.question || '',
      answer: i.answer || '',
      is_featured: !!i.is_featured,
      is_published: !!i.is_published,
      sort_order: i.sort_order || 0,
    })
  }

  const updateItemQuick = async (i, patch) => {
    await apiFetch(`/admin/faq/items/${i.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        category_id: i.category_id || null,
        question: i.question,
        answer: i.answer,
        is_featured: !!i.is_featured,
        is_published: !!i.is_published,
        sort_order: Number(i.sort_order || 0),
        ...patch,
      }),
    })
    await load()
  }

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>FAQ Management</h1>
          <p>Create searchable, category-based FAQ content for the user dashboard.</p>
        </div>
        <div className="actions"><input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search FAQs..." /><button className="btn soft" onClick={load}>Search</button></div>
      </div>
      {error ? <div className="card" style={{ marginBottom: 16, borderColor: '#fecaca' }}><div className="cardBody" style={{ color: '#b91c1c' }}>{error}</div></div> : null}
      <div className="grid-12">
        <div className="span-4 card">
          <div className="cardHead"><h3>{editingCategoryId ? 'Edit category' : 'Create category'}</h3></div>
          <div className="cardBody stack">
            <input className="input" value={categoryForm.name} onChange={(e) => setCategoryForm({ ...categoryForm, name: e.target.value })} placeholder="Name" />
            <input className="input" value={categoryForm.slug} onChange={(e) => setCategoryForm({ ...categoryForm, slug: e.target.value })} placeholder="Slug (optional)" />
            <input className="input" type="number" value={categoryForm.sort_order} onChange={(e) => setCategoryForm({ ...categoryForm, sort_order: e.target.value })} placeholder="Sort order" />
            <div className="actions"><button className="btn primary" onClick={saveCategory}>{editingCategoryId ? 'Save category' : 'Create category'}</button>{editingCategoryId ? <button className="btn soft" onClick={() => { setEditingCategoryId(null); setCategoryForm(emptyCategory) }}>Cancel</button> : null}</div>
            <div className="list">{categories.map((c) => <div className="listRow" key={c.id}><span>{c.name}</span><span><button className="btn soft" onClick={() => editCategory(c)}>Edit</button> <button className="btn soft" onClick={async () => { await apiFetch(`/admin/faq/categories/${c.id}`, { method: 'DELETE' }); await load() }}>Delete</button></span></div>)}</div>
          </div>
        </div>
        <div className="span-8 card">
          <div className="cardHead"><h3>{editingItemId ? 'Edit FAQ' : 'Create FAQ'}</h3></div>
          <div className="cardBody stack">
            <select className="input" value={itemForm.category_id} onChange={(e) => setItemForm({ ...itemForm, category_id: e.target.value })}><option value="">No category</option>{categories.map((c) => <option value={c.id} key={c.id}>{c.name}</option>)}</select>
            <textarea className="input" rows={3} value={itemForm.question} onChange={(e) => setItemForm({ ...itemForm, question: e.target.value })} placeholder="Question" />
            <textarea className="input" rows={6} value={itemForm.answer} onChange={(e) => setItemForm({ ...itemForm, answer: e.target.value })} placeholder="Answer" />
            <input className="input" type="number" value={itemForm.sort_order} onChange={(e) => setItemForm({ ...itemForm, sort_order: e.target.value })} placeholder="Sort order" />
            <div className="actions"><label><input type="checkbox" checked={itemForm.is_published} onChange={(e) => setItemForm({ ...itemForm, is_published: e.target.checked })} /> Published</label><label><input type="checkbox" checked={itemForm.is_featured} onChange={(e) => setItemForm({ ...itemForm, is_featured: e.target.checked })} /> Featured</label></div>
            <div className="actions"><button className="btn primary" onClick={saveItem}>{editingItemId ? 'Save FAQ' : 'Create FAQ'}</button>{editingItemId ? <button className="btn soft" onClick={() => { setEditingItemId(null); setItemForm(emptyItem) }}>Cancel</button> : null}</div>
            <table className="table"><thead><tr><th>Question</th><th>Category</th><th>Order</th><th>Status</th><th /></tr></thead><tbody>{items.length ? items.map((i) => <tr key={i.id}><td>{i.question}</td><td>{i.category_name || '—'}</td><td><input className="input" type="number" value={i.sort_order} onChange={(e) => updateItemQuick(i, { sort_order: Number(e.target.value || 0) })} /></td><td><button className={`pill ${i.is_published ? 'p-green' : 'p-amber'}`} onClick={() => updateItemQuick(i, { is_published: !i.is_published })}>{i.is_published ? 'Published' : 'Draft'}</button> <button className={`pill ${i.is_featured ? 'p-cyan' : ''}`} onClick={() => updateItemQuick(i, { is_featured: !i.is_featured })}>{i.is_featured ? 'Featured' : 'Normal'}</button></td><td><button className="btn soft" onClick={() => editItem(i)}>Edit</button> <button className="btn soft" onClick={async () => { await apiFetch(`/admin/faq/items/${i.id}`, { method: 'DELETE' }); await load() }}>Delete</button></td></tr>) : <tr><td colSpan="5">No FAQs found.</td></tr>}</tbody></table>
          </div>
        </div>
      </div>
    </>
  )
}

