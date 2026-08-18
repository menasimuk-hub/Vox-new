import React, { useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch, apiUpload, getApiBaseUrl } from '../lib/api'
import { sanitizeCmsHtml } from '../lib/sanitizeHtml'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Pill } from '@/components/ui/Badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import { Modal } from '@/components/ui/Modal'
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
    <div className="ds-scope space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">Blog & News</h1>
          <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
            Manage journal essays and newsroom updates for voxbulk.com
          </p>
        </div>
      </div>

      <Tabs value={tab} onValueChange={(next) => { setTab(next); closeEditor() }}>
        <TabsList>
          <TabsTrigger value="blog">Blog</TabsTrigger>
          <TabsTrigger value="news">News</TabsTrigger>
        </TabsList>
      </Tabs>

      {msg ? (
        <div
          className={`rounded-md border px-3 py-2 text-sm ${
            msg.toLowerCase().includes('fail') || msg.toLowerCase().includes('could not') || msg.toLowerCase().includes('please')
              ? 'border-destructive/40 bg-destructive/10 text-destructive'
              : 'border-border bg-surface text-foreground'
          }`}
        >
          {msg}
        </div>
      ) : null}

      {view === 'list' ? (
        <Panel
          title={`${filtered.length} ${filtered.length === 1 ? 'item' : 'items'}`}
          subtitle={loading ? 'Loading…' : `${tab === 'blog' ? 'Blog posts' : 'News items'} for the public site.`}
          action={
            <Button size="sm" className="h-8" onClick={openCreate}>
              Add {tab === 'blog' ? 'post' : 'news'}
            </Button>
          }
        >
          <StripeTable>
            <TableHeader>
              <TableRow>
                <TableHead style={{ width: '52%' }}>Title</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {!loading && filtered.length === 0 && (
                <TableEmpty colSpan={3}>
                  <div className="py-8">
                    <strong className="block text-[15px] text-foreground">Nothing here yet</strong>
                    <p className="mt-1 text-[13px] text-muted-foreground">Click Add to create the first entry.</p>
                  </div>
                </TableEmpty>
              )}
              {filtered.map((item) => {
                const src = resolveImageUrl(item.image_url)
                return (
                  <TableRow key={item.id}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        {src ? (
                          <img
                            className="h-11 w-11 shrink-0 rounded-md border border-border object-cover"
                            src={src}
                            alt=""
                          />
                        ) : (
                          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md border border-border bg-surface-muted text-[10px] text-muted-foreground">
                            No img
                          </div>
                        )}
                        <div className="min-w-0">
                          <div className="text-[13px] font-semibold text-foreground">{item.title || 'Untitled'}</div>
                          <div className="mt-0.5 text-[11px] text-muted-foreground">
                            {item.body_mode === 'html' ? 'HTML content' : 'Plain text'}
                            {item.published_at ? ` · ${item.published_at}` : ''}
                          </div>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Pill tone={item.is_visible ? 'success' : 'neutral'}>
                        {item.is_visible ? 'Visible' : 'Hidden'}
                      </Pill>
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0"
                          title="Edit"
                          onClick={() => openEdit(item)}
                        >
                          <i className="ti ti-pencil text-[14px]" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0"
                          title={item.is_visible ? 'Hide' : 'Show'}
                          onClick={() => toggleVisible(item)}
                        >
                          <i className={`ti ${item.is_visible ? 'ti-eye' : 'ti-eye-off'} text-[14px]`} />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0 text-destructive hover:bg-destructive/10"
                          title="Delete"
                          onClick={() => remove(item)}
                        >
                          <i className="ti ti-trash text-[14px]" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </StripeTable>
        </Panel>
      ) : (
        <Panel
          title={`${editingId ? 'Edit' : 'Add'} ${tab === 'blog' ? 'post' : 'news item'}`}
          subtitle={`Fill in the details below${tab === 'blog' ? ' for the journal' : ''}.`}
        >
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Title
              </label>
              <Input
                type="text"
                value={draft.title}
                onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
                placeholder="Enter a title"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Image
              </label>
              <div className="flex items-start gap-3">
                <div className="flex-1 space-y-2">
                  <div className="flex gap-2">
                    <Input
                      type="url"
                      value={draft.image_url}
                      onChange={(e) => setDraft((d) => ({ ...d, image_url: e.target.value }))}
                      placeholder="Paste an image URL, or upload a file"
                      className="flex-1"
                    />
                    <Button variant="outline" disabled={uploading} onClick={() => fileRef.current?.click()}>
                      {uploading ? 'Compressing…' : 'Upload'}
                    </Button>
                    <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onUpload} />
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    Any format accepted. Saved as 1200×900 WebP for a consistent, fast theme.
                  </p>
                </div>
                {previewSrc ? (
                  <img
                    className="h-18 w-18 shrink-0 rounded-md border border-border object-cover"
                    src={previewSrc}
                    alt=""
                  />
                ) : null}
              </div>
            </div>

            {tab === 'blog' ? (
              <>
                <div>
                  <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                    Excerpt
                  </label>
                  <Input
                    type="text"
                    value={draft.excerpt}
                    onChange={(e) => setDraft((d) => ({ ...d, excerpt: e.target.value }))}
                    placeholder="Short summary shown on the journal index"
                  />
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Category
                    </label>
                    <Input
                      type="text"
                      value={draft.category}
                      onChange={(e) => setDraft((d) => ({ ...d, category: e.target.value }))}
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Read mins
                    </label>
                    <Input
                      type="text"
                      value={draft.read_mins}
                      onChange={(e) => setDraft((d) => ({ ...d, read_mins: e.target.value }))}
                    />
                  </div>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Author
                    </label>
                    <Input
                      type="text"
                      value={draft.author}
                      onChange={(e) => setDraft((d) => ({ ...d, author: e.target.value }))}
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Author role
                    </label>
                    <Input
                      type="text"
                      value={draft.author_role}
                      onChange={(e) => setDraft((d) => ({ ...d, author_role: e.target.value }))}
                    />
                  </div>
                </div>
              </>
            ) : null}

            <div>
              <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Published date
              </label>
              <Input
                type="text"
                value={draft.published_at}
                onChange={(e) => setDraft((d) => ({ ...d, published_at: e.target.value }))}
                placeholder="YYYY-MM-DD"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Body
              </label>
              <div className="mb-2 inline-flex rounded-md border border-border bg-surface-muted/50 p-1">
                <Button
                  type="button"
                  size="sm"
                  variant={draft.body_mode === 'text' ? 'default' : 'ghost'}
                  className="h-7"
                  onClick={() => setDraft((d) => ({ ...d, body_mode: 'text' }))}
                >
                  Text
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={draft.body_mode === 'html' ? 'default' : 'ghost'}
                  className="h-7"
                  onClick={() => setDraft((d) => ({ ...d, body_mode: 'html' }))}
                >
                  HTML
                </Button>
              </div>
              <textarea
                className={`w-full resize-y rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                  draft.body_mode === 'html' ? 'min-h-[220px] font-mono text-[13.5px] leading-relaxed' : 'min-h-[220px]'
                }`}
                value={draft.body}
                onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))}
                placeholder={draft.body_mode === 'html' ? '<p>Write raw HTML here...</p>' : 'Write the content here...'}
              />
            </div>

            <div className="flex justify-end gap-2 border-t border-border pt-4">
              <Button variant="outline" onClick={closeEditor}>
                Cancel
              </Button>
              <Button variant="outline" onClick={() => setPreviewOpen(true)}>
                Preview
              </Button>
              <Button disabled={saving} onClick={save}>
                {saving ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </div>
        </Panel>
      )}

      <Modal
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        title="Preview"
        description="Content preview as it will appear on the public site."
        className="max-w-2xl"
      >
        <div className="max-h-[70vh] space-y-4 overflow-y-auto">
          <h1 className="text-[22px] font-bold text-foreground">{draft.title || 'Untitled'}</h1>
          {previewSrc ? (
            <img className="max-h-[280px] w-full rounded-md border border-border object-cover" src={previewSrc} alt="" />
          ) : null}
          <div className="text-[15px] leading-relaxed text-foreground">
            {draft.body_mode === 'html' ? (
              <div dangerouslySetInnerHTML={{ __html: sanitizeCmsHtml(draft.body) }} />
            ) : (
              <pre className="whitespace-pre-wrap font-sans">{draft.body}</pre>
            )}
          </div>
        </div>
      </Modal>
    </div>
  )
}
