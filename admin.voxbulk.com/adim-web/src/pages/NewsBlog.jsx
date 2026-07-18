import React, { useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch, apiUpload, getApiBaseUrl } from '../lib/api'

const css = `
.nb-page{ --nb-bg:#F4F1EA; --nb-surface:#FFFFFF; --nb-surface-2:#FBF9F4; --nb-border:#E4DDCC; --nb-ink:#2B2620; --nb-muted:#8A8072; --nb-accent:#2E3A59; --nb-accent-hover:#232C44; --nb-accent-soft:#E5E8EF; --nb-danger:#B5473F; --nb-danger-soft:#F6E8E6; --nb-live:#2E3A59; --nb-hidden-bg:#EFEAE0; --nb-radius:10px; --nb-shadow:0 1px 2px rgba(43,38,32,0.06), 0 4px 12px rgba(43,38,32,0.05); max-width:1040px; margin:0 auto; padding:8px 4px 48px; color:var(--nb-ink); }
.nb-page *{ box-sizing:border-box; }
.nb-header{ display:flex; align-items:baseline; justify-content:space-between; margin-bottom:28px; }
.nb-header h1{ font-size:22px; font-weight:650; margin:0; letter-spacing:-0.01em; }
.nb-header p{ margin:4px 0 0; color:var(--nb-muted); font-size:13px; }
.nb-tabs{ display:flex; gap:4px; background:var(--nb-surface-2); border:1px solid var(--nb-border); border-radius:999px; padding:4px; width:max-content; margin-bottom:22px; }
.nb-tab{ border:none; background:transparent; color:var(--nb-muted); font-size:13.5px; font-weight:600; padding:8px 20px; border-radius:999px; cursor:pointer; }
.nb-tab.active{ background:var(--nb-accent); color:#fff; }
.nb-toolbar{ display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; }
.nb-count{ font-size:13px; color:var(--nb-muted); }
.nb-btn{ font-family:inherit; font-size:13.5px; font-weight:600; border-radius:8px; padding:9px 16px; border:1px solid transparent; cursor:pointer; display:inline-flex; align-items:center; gap:6px; }
.nb-btn-primary{ background:var(--nb-accent); color:#fff; }
.nb-btn-primary:hover{ background:var(--nb-accent-hover); }
.nb-btn-ghost{ background:transparent; color:var(--nb-ink); border-color:var(--nb-border); }
.nb-btn-ghost:hover{ background:var(--nb-surface-2); }
.nb-btn:disabled{ opacity:0.55; cursor:not-allowed; }
.nb-card{ background:var(--nb-surface); border:1px solid var(--nb-border); border-radius:var(--nb-radius); overflow:hidden; box-shadow:var(--nb-shadow); }
.nb-table{ width:100%; border-collapse:collapse; }
.nb-table thead th{ text-align:left; font-size:11.5px; text-transform:uppercase; letter-spacing:.04em; color:var(--nb-muted); font-weight:650; padding:12px 18px; border-bottom:1px solid var(--nb-border); background:var(--nb-surface-2); }
.nb-table tbody td{ padding:12px 18px; border-bottom:1px solid var(--nb-border); font-size:14px; vertical-align:middle; }
.nb-table tbody tr:last-child td{ border-bottom:none; }
.nb-table tbody tr:hover{ background:#FBF9F4; }
.nb-thumb{ width:44px; height:44px; border-radius:8px; object-fit:cover; border:1px solid var(--nb-border); background:var(--nb-surface-2); display:flex; align-items:center; justify-content:center; color:var(--nb-muted); font-size:10px; flex-shrink:0; }
.nb-title-cell{ display:flex; align-items:center; gap:12px; }
.nb-row-title{ font-weight:600; }
.nb-row-meta{ font-size:12px; color:var(--nb-muted); margin-top:2px; }
.nb-status{ display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:600; padding:4px 10px; border-radius:999px; }
.nb-status.live{ background:var(--nb-accent-soft); color:var(--nb-live); }
.nb-status.hidden{ background:var(--nb-hidden-bg); color:var(--nb-muted); }
.nb-status .dot{ width:6px; height:6px; border-radius:50%; background:currentColor; }
.nb-actions{ display:flex; gap:4px; justify-content:flex-end; }
.nb-icon-btn{ width:30px; height:30px; border-radius:7px; border:1px solid transparent; background:transparent; display:inline-flex; align-items:center; justify-content:center; cursor:pointer; color:var(--nb-muted); }
.nb-icon-btn:hover{ background:var(--nb-surface-2); color:var(--nb-ink); border-color:var(--nb-border); }
.nb-icon-btn.danger:hover{ background:var(--nb-danger-soft); color:var(--nb-danger); }
.nb-empty{ padding:56px 20px; text-align:center; color:var(--nb-muted); font-size:14px; }
.nb-empty strong{ display:block; color:var(--nb-ink); font-size:15px; margin-bottom:4px; }
.nb-editor{ background:var(--nb-surface); border:1px solid var(--nb-border); border-radius:var(--nb-radius); box-shadow:var(--nb-shadow); padding:26px; }
.nb-editor h2{ margin:0 0 20px; font-size:17px; font-weight:650; }
.nb-field{ margin-bottom:18px; }
.nb-field label{ display:block; font-size:12.5px; font-weight:650; color:var(--nb-muted); margin-bottom:6px; text-transform:uppercase; letter-spacing:.03em; }
.nb-field input, .nb-field textarea{ width:100%; padding:10px 12px; border:1px solid var(--nb-border); border-radius:8px; font-size:14px; font-family:inherit; background:var(--nb-surface-2); color:var(--nb-ink); }
.nb-field textarea{ min-height:220px; font-family:Consolas,Menlo,monospace; font-size:13.5px; line-height:1.55; resize:vertical; }
.nb-field textarea.text-mode{ font-family:inherit; font-size:14px; }
.nb-image-row{ display:flex; gap:14px; align-items:flex-start; }
.nb-image-preview{ width:72px; height:72px; border-radius:8px; border:1px solid var(--nb-border); object-fit:cover; flex-shrink:0; background:var(--nb-surface-2); }
.nb-body-toggle{ display:inline-flex; background:var(--nb-surface-2); border:1px solid var(--nb-border); border-radius:8px; padding:3px; margin-bottom:10px; }
.nb-body-toggle button{ border:none; background:transparent; font-size:12.5px; font-weight:650; padding:6px 14px; border-radius:6px; cursor:pointer; color:var(--nb-muted); }
.nb-body-toggle button.active{ background:var(--nb-accent); color:#fff; }
.nb-editor-actions{ display:flex; justify-content:flex-end; gap:10px; margin-top:22px; border-top:1px solid var(--nb-border); padding-top:18px; }
.nb-msg{ margin-bottom:14px; font-size:13px; color:var(--nb-muted); }
.nb-msg.error{ color:var(--nb-danger); }
.nb-modal-overlay{ position:fixed; inset:0; background:rgba(43,38,32,0.45); display:flex; align-items:flex-start; justify-content:center; padding:48px 20px; z-index:80; overflow-y:auto; }
.nb-modal{ background:#fff; border-radius:12px; width:100%; max-width:640px; box-shadow:0 20px 50px rgba(0,0,0,0.25); overflow:hidden; }
.nb-modal-head{ display:flex; justify-content:space-between; align-items:center; padding:14px 20px; border-bottom:1px solid var(--nb-border); background:var(--nb-surface-2); }
.nb-modal-head span{ font-size:12.5px; font-weight:650; color:var(--nb-muted); text-transform:uppercase; letter-spacing:.03em; }
.nb-modal-close{ border:none; background:transparent; cursor:pointer; color:var(--nb-muted); width:28px; height:28px; border-radius:6px; }
.nb-modal-body{ padding:26px 28px 34px; max-height:75vh; overflow-y:auto; }
.nb-preview-title{ font-size:22px; font-weight:700; margin:0 0 14px; }
.nb-preview-image{ width:100%; max-height:280px; object-fit:cover; border-radius:8px; margin-bottom:18px; border:1px solid var(--nb-border); }
.nb-preview-content{ font-size:15px; line-height:1.65; }
.nb-preview-content pre{ white-space:pre-wrap; font-family:inherit; margin:0; }
.nb-hint{ font-size:12px; color:var(--nb-muted); margin-top:6px; }
`

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
