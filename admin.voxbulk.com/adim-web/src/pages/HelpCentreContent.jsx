import React, { useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'

const emptyCategory = { name: '', description: '' }
const emptyReply = { category_id: '', title: '', question: '', answer: '', is_active: true }

export default function HelpCentreContent() {
  const [categories, setCategories] = useState([])
  const [replies, setReplies] = useState([])
  const [categoryForm, setCategoryForm] = useState(emptyCategory)
  const [replyForm, setReplyForm] = useState(emptyReply)
  const [editingReplyId, setEditingReplyId] = useState(null)
  const [error, setError] = useState('')

  const load = async () => {
    setError('')
    try {
      const [cats, reps] = await Promise.all([
        apiFetch('/admin/support/canned/categories'),
        apiFetch('/admin/support/canned/replies'),
      ])
      setCategories(Array.isArray(cats) ? cats : [])
      setReplies(Array.isArray(reps) ? reps : [])
    } catch (e) {
      setError(e?.message || 'Could not load canned replies')
    }
  }

  useEffect(() => {
    load()
  }, [])

  const saveCategory = async () => {
    if (!categoryForm.name.trim()) return
    await apiFetch('/admin/support/canned/categories', {
      method: 'POST',
      body: JSON.stringify(categoryForm),
    })
    setCategoryForm(emptyCategory)
    await load()
  }

  const saveReply = async () => {
    if (!replyForm.title.trim() || !replyForm.question.trim() || !replyForm.answer.trim()) return
    const body = {
      ...replyForm,
      category_id: replyForm.category_id ? Number(replyForm.category_id) : null,
    }
    await apiFetch(editingReplyId ? `/admin/support/canned/replies/${editingReplyId}` : '/admin/support/canned/replies', {
      method: editingReplyId ? 'PUT' : 'POST',
      body: JSON.stringify(body),
    })
    setReplyForm(emptyReply)
    setEditingReplyId(null)
    await load()
  }

  const editReply = (r) => {
    setEditingReplyId(r.id)
    setReplyForm({
      category_id: r.category_id || '',
      title: r.title || '',
      question: r.question || '',
      answer: r.answer || '',
      is_active: !!r.is_active,
    })
  }

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Help Centre Content</h1>
          <p>Create categories and Q&A canned replies for support agents. These appear inside the admin ticket popup.</p>
        </div>
        <button className="btn soft" onClick={load}>Refresh</button>
      </div>
      {error ? <div className="card" style={{ marginBottom: 16, borderColor: '#fecaca' }}><div className="cardBody" style={{ color: '#b91c1c' }}>{error}</div></div> : null}
      <div className="grid-12">
        <div className="span-4 card">
          <div className="cardHead"><h3>Canned reply categories</h3></div>
          <div className="cardBody stack">
            <input className="input" value={categoryForm.name} onChange={(e) => setCategoryForm({ ...categoryForm, name: e.target.value })} placeholder="Category name" />
            <textarea className="input" rows={3} value={categoryForm.description} onChange={(e) => setCategoryForm({ ...categoryForm, description: e.target.value })} placeholder="Description" />
            <button className="btn primary" onClick={saveCategory}>Create category</button>
            <div className="list">
              {categories.map((c) => <div className="listRow" key={c.id}><span>{c.name}</span><button className="btn soft" onClick={async () => { await apiFetch(`/admin/support/canned/categories/${c.id}`, { method: 'DELETE' }); await load() }}>Delete</button></div>)}
            </div>
          </div>
        </div>
        <div className="span-8 card">
          <div className="cardHead"><h3>{editingReplyId ? 'Edit canned reply' : 'Create canned reply'}</h3></div>
          <div className="cardBody stack">
            <select className="input" value={replyForm.category_id} onChange={(e) => setReplyForm({ ...replyForm, category_id: e.target.value })}><option value="">No category</option>{categories.map((c) => <option value={c.id} key={c.id}>{c.name}</option>)}</select>
            <input className="input" value={replyForm.title} onChange={(e) => setReplyForm({ ...replyForm, title: e.target.value })} placeholder="Short title" />
            <textarea className="input" rows={3} value={replyForm.question} onChange={(e) => setReplyForm({ ...replyForm, question: e.target.value })} placeholder="Question / when to use" />
            <textarea className="input" rows={6} value={replyForm.answer} onChange={(e) => setReplyForm({ ...replyForm, answer: e.target.value })} placeholder="Answer inserted into ticket reply" />
            <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}><input type="checkbox" checked={replyForm.is_active} onChange={(e) => setReplyForm({ ...replyForm, is_active: e.target.checked })} /> Active</label>
            <div className="actions"><button className="btn primary" onClick={saveReply}>{editingReplyId ? 'Save changes' : 'Create reply'}</button>{editingReplyId ? <button className="btn soft" onClick={() => { setEditingReplyId(null); setReplyForm(emptyReply) }}>Cancel</button> : null}</div>
            <table className="table"><thead><tr><th>Title</th><th>Category</th><th>Active</th><th /></tr></thead><tbody>{replies.length ? replies.map((r) => <tr key={r.id}><td>{r.title}</td><td>{r.category_name || '—'}</td><td>{r.is_active ? 'Yes' : 'No'}</td><td><button className="btn soft" onClick={() => editReply(r)}>Edit</button> <button className="btn soft" onClick={async () => { await apiFetch(`/admin/support/canned/replies/${r.id}`, { method: 'DELETE' }); await load() }}>Delete</button></td></tr>) : <tr><td colSpan="4">No canned replies yet.</td></tr>}</tbody></table>
          </div>
        </div>
      </div>
    </>
  )
}

