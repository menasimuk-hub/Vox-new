import React, { useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch, apiUpload, getApiBaseUrl } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Pill } from '@/components/ui/Badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import { Modal, ModalContent, ModalHeader, ModalTitle, ModalDescription } from '@/components/ui/Modal'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'

function resolveImageUrl(url) {
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('data:')) return url
  const base = (getApiBaseUrl() || '').replace(/\/+$/, '')
  return `${base}${url.startsWith('/') ? url : `/${url}`}`
}

const emptyDraft = () => ({
  title: '',
  image_url: '',
  body_mode: 'text',
  body: '',
  excerpt: '',
  category: '',
  author: 'VoxBulk',
  author_role: '',
  published_at: new Date().toISOString().slice(0, 10),
  read_mins: 3,
})

export default function NewsBlog() {
  const [tab, setTab] = useState('blog')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [msg, setMsg] = useState('')
  const [view, setView] = useState('list')
  const [editingId, setEditingId] = useState(null)
  const [draft, setDraft] = useState(emptyDraft())
  const [previewOpen, setPreviewOpen] = useState(false)
  const fileRef = useRef(null)

  const filtered = useMemo(() => items.filter((i) => i.kind === tab), [items, tab])

  const load = async () => {
    setLoading(true)
    setMsg('')
    try {
      const data = await apiFetch('/admin/blog-news')
      setItems(data?.items || [])
    } catch (e) {
      setMsg(e?.message || 'Could not load Blog & News')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const openCreate = () => {
    setEditingId(null)
    setDraft({
      ...emptyDraft(),
      category: tab === 'news' ? 'Announcement' : 'General',
      body_mode: tab === 'news' ? 'text' : 'html',
    })
    setView('editor')
  }

  const openEdit = (item) => {
    setEditingId(item.id)
    setDraft({
      title: item.title || '',
      image_url: item.image_url || '',
      body_mode: item.body_mode || 'text',
      body: item.body || '',
      excerpt: item.excerpt || '',
      category: item.category || '',
      author: item.author || 'VoxBulk',
      author_role: item.author_role || '',
      published_at: (item.published_at || '').slice(0, 10),
      read_mins: item.read_mins || 3,
    })
    setView('editor')
  }

  const closeEditor = () => {
    setView('list')
    setEditingId(null)
  }

  const save = async () => {
    if (!draft.title.trim()) {
      setMsg('Please add a title before saving.')
      return
    }
    setSaving(true)
    setMsg('')
    try {
      const payload = {
        kind: tab,
        title: draft.title.trim(),
        excerpt: draft.excerpt,
        category: draft.category,
        author: draft.author,
        author_role: draft.author_role,
        image_url: draft.image_url || null,
        body_mode: draft.body_mode,
        body: draft.body,
        published_at: draft.published_at || null,
        read_mins: Number(draft.read_mins) || 3,
      }
      if (editingId) {
        await apiFetch(`/admin/blog-news/${editingId}`, { method: 'PUT', body: JSON.stringify(payload) })
      } else {
        await apiFetch('/admin/blog-news', { method: 'POST', body: JSON.stringify(payload) })
      }
      await load()
      closeEditor()
    } catch (e) {
      setMsg(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const toggleVisible = async (item) => {
    try {
      await apiFetch(`/admin/blog-news/${item.id}/toggle-visible`, { method: 'POST' })
      await load()
    } catch (e) {
      setMsg(e?.message || 'Could not update visibility')
    }
  }

  const remove = async (item) => {
    if (!window.confirm('Delete this item? This cannot be undone.')) return
    try {
      await apiFetch(`/admin/blog-news/${item.id}`, { method: 'DELETE' })
      await load()
    } catch (e) {
      setMsg(e?.message || 'Delete failed')
    }
  }

  const onUpload = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    setMsg('')
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await apiUpload('/admin/blog-news/upload-image', fd)
      setDraft((d) => ({ ...d, image_url: res.image_url || '' }))
      setMsg(res.note || 'Image compressed to 1200×900 WebP.')
    } catch (e) {
      setMsg(e?.message || 'Image upload failed')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const previewSrc = resolveImageUrl(draft.image_url)

  return (
    <div className="nb-page">
      <style>{css}</style>
      <div className="nb-header">
        <div>
          <h1>Blog & News</h1>
          <p>Manage journal essays and newsroom updates for voxbulk.com</p>
        </div>
      </div>

      <div className="nb-tabs">
        <button type="button" className={`nb-tab ${tab === 'blog' ? 'active' : ''}`} onClick={() => { setTab('blog'); closeEditor() }}>
          Blog
        </button>
        <button type="button" className={`nb-tab ${tab === 'news' ? 'active' : ''}`} onClick={() => { setTab('news'); closeEditor() }}>
          News
        </button>
      </div>

      {msg ? <div className={`nb-msg ${msg.toLowerCase().includes('fail') || msg.toLowerCase().includes('could not') || msg.toLowerCase().includes('please') ? 'error' : ''}`}>{msg}</div> : null}

      {view === 'list' ? (
        <div>
          <div className="nb-toolbar">
            <span className="nb-count">
              {loading ? 'Loading…' : `${filtered.length} ${filtered.length === 1 ? 'item' : 'items'}`}
            </span>
            <button type="button" className="nb-btn nb-btn-primary" onClick={openCreate}>
              + Add {tab === 'blog' ? 'post' : 'news'}
            </button>
          </div>
          <div className="nb-card">
            {!loading && filtered.length === 0 ? (
              <div className="nb-empty">
                <strong>Nothing here yet</strong>
                Click Add to create the first entry.
              </div>
            ) : (
              <table className="nb-table">
                <thead>
                  <tr>
                    <th style={{ width: '52%' }}>Title</th>
                    <th>Status</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((item) => {
                    const src = resolveImageUrl(item.image_url)
                    return (
                      <tr key={item.id}>
                        <td>
                          <div className="nb-title-cell">
                            {src ? (
                              <img className="nb-thumb" src={src} alt="" />
                            ) : (
                              <div className="nb-thumb">No img</div>
                            )}
                            <div>
                              <div className="nb-row-title">{item.title || 'Untitled'}</div>
                              <div className="nb-row-meta">
                                {item.body_mode === 'html' ? 'HTML content' : 'Plain text'}
                                {item.published_at ? ` · ${item.published_at}` : ''}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className={`nb-status ${item.is_visible ? 'live' : 'hidden'}`}>
                            <span className="dot" />
                            {item.is_visible ? 'Visible' : 'Hidden'}
                          </span>
                        </td>
                        <td>
                          <div className="nb-actions">
                            <button type="button" className="nb-icon-btn" title="Edit" onClick={() => openEdit(item)}>
                              ✎
                            </button>
                            <button
                              type="button"
                              className="nb-icon-btn"
                              title={item.is_visible ? 'Hide' : 'Show'}
                              onClick={() => toggleVisible(item)}
                            >
                              {item.is_visible ? '👁' : '○'}
                            </button>
                            <button type="button" className="nb-icon-btn danger" title="Delete" onClick={() => remove(item)}>
                              ⌫
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      ) : (
        <div className="nb-editor">
          <h2>{editingId ? 'Edit' : 'Add'} {tab === 'blog' ? 'post' : 'news item'}</h2>

          <div className="nb-field">
            <label>Title</label>
            <input
              type="text"
              value={draft.title}
              onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
              placeholder="Enter a title"
            />
          </div>

          <div className="nb-field">
            <label>Image</label>
            <div className="nb-image-row">
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    type="url"
                    value={draft.image_url}
                    onChange={(e) => setDraft((d) => ({ ...d, image_url: e.target.value }))}
                    placeholder="Paste an image URL, or upload a file"
                    style={{ flex: 1 }}
                  />
                  <button type="button" className="nb-btn nb-btn-ghost" disabled={uploading} onClick={() => fileRef.current?.click()}>
                    {uploading ? 'Compressing…' : 'Upload'}
                  </button>
                  <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={onUpload} />
                </div>
                <div className="nb-hint">Any format accepted. Saved as 1200×900 WebP for a consistent, fast theme.</div>
              </div>
              {previewSrc ? <img className="nb-image-preview" src={previewSrc} alt="" /> : null}
            </div>
          </div>

          {tab === 'blog' ? (
            <>
              <div className="nb-field">
                <label>Excerpt</label>
                <input
                  type="text"
                  value={draft.excerpt}
                  onChange={(e) => setDraft((d) => ({ ...d, excerpt: e.target.value }))}
                  placeholder="Short summary shown on the journal index"
                />
              </div>
              <div className="nb-field" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label>Category</label>
                  <input
                    type="text"
                    value={draft.category}
                    onChange={(e) => setDraft((d) => ({ ...d, category: e.target.value }))}
                  />
                </div>
                <div>
                  <label>Read mins</label>
                  <input
                    type="text"
                    value={draft.read_mins}
                    onChange={(e) => setDraft((d) => ({ ...d, read_mins: e.target.value }))}
                  />
                </div>
              </div>
              <div className="nb-field" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label>Author</label>
                  <input
                    type="text"
                    value={draft.author}
                    onChange={(e) => setDraft((d) => ({ ...d, author: e.target.value }))}
                  />
                </div>
                <div>
                  <label>Author role</label>
                  <input
                    type="text"
                    value={draft.author_role}
                    onChange={(e) => setDraft((d) => ({ ...d, author_role: e.target.value }))}
                  />
                </div>
              </div>
            </>
          ) : null}

          <div className="nb-field">
            <label>Published date</label>
            <input
              type="text"
              value={draft.published_at}
              onChange={(e) => setDraft((d) => ({ ...d, published_at: e.target.value }))}
              placeholder="YYYY-MM-DD"
            />
          </div>

          <div className="nb-field">
            <label>Body</label>
            <div className="nb-body-toggle">
              <button
                type="button"
                className={draft.body_mode === 'text' ? 'active' : ''}
                onClick={() => setDraft((d) => ({ ...d, body_mode: 'text' }))}
              >
                Text
              </button>
              <button
                type="button"
                className={draft.body_mode === 'html' ? 'active' : ''}
                onClick={() => setDraft((d) => ({ ...d, body_mode: 'html' }))}
              >
                HTML
              </button>
            </div>
            <textarea
              className={draft.body_mode === 'text' ? 'text-mode' : ''}
              value={draft.body}
              onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))}
              placeholder={draft.body_mode === 'html' ? '<p>Write raw HTML here...</p>' : 'Write the content here...'}
            />
          </div>

          <div className="nb-editor-actions">
            <button type="button" className="nb-btn nb-btn-ghost" onClick={closeEditor}>Cancel</button>
            <button type="button" className="nb-btn nb-btn-ghost" onClick={() => setPreviewOpen(true)}>Preview</button>
            <button type="button" className="nb-btn nb-btn-primary" disabled={saving} onClick={save}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      )}

      {previewOpen ? (
        <div className="nb-modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setPreviewOpen(false) }}>
          <div className="nb-modal">
            <div className="nb-modal-head">
              <span>Preview</span>
              <button type="button" className="nb-modal-close" onClick={() => setPreviewOpen(false)}>×</button>
            </div>
            <div className="nb-modal-body">
              <h1 className="nb-preview-title">{draft.title || 'Untitled'}</h1>
              {previewSrc ? <img className="nb-preview-image" src={previewSrc} alt="" /> : null}
              <div className="nb-preview-content">
                {draft.body_mode === 'html' ? (
                  <div dangerouslySetInnerHTML={{ __html: draft.body }} />
                ) : (
                  <pre>{draft.body}</pre>
                )}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
