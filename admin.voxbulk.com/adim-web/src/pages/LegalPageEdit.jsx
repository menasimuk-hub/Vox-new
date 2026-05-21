import React, { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const DEFAULT_HTML = `<h2>Page title</h2>
<p>Replace this with your legal copy. You can use standard HTML tags:</p>
<ul>
  <li><strong>Headings</strong> — h2, h3</li>
  <li><strong>Paragraphs</strong> — p</li>
  <li><strong>Lists</strong> — ul, ol, li</li>
  <li><strong>Links</strong> — a href="…"</li>
</ul>
<p>Last updated: {{date}}</p>`

export default function LegalPageEdit() {
  const { slug } = useParams()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState('')
  const [draft, setDraft] = useState({
    slug: '',
    title: '',
    public_path: '',
    meta_description: '',
    body: '',
    is_published: true,
  })

  const load = useCallback(async () => {
    if (!slug) return
    setError('')
    setLoading(true)
    try {
      const row = await apiFetch(`/admin/legal-pages/${encodeURIComponent(slug)}`)
      setDraft({
        slug: row.slug || slug,
        title: row.title || '',
        public_path: row.public_path || '',
        meta_description: row.meta_description || '',
        body: row.body || '',
        is_published: row.is_published !== false,
      })
    } catch (e) {
      setError(e?.message || 'Could not load page')
    } finally {
      setLoading(false)
    }
  }, [slug])

  useEffect(() => {
    load()
  }, [load])

  const save = async () => {
    setSaving(true)
    setError('')
    setFeedback('')
    try {
      await apiFetch(`/admin/legal-pages/${encodeURIComponent(slug)}`, {
        method: 'PUT',
        body: JSON.stringify({
          title: draft.title.trim(),
          meta_description: draft.meta_description.trim() || null,
          body: draft.body,
          is_published: draft.is_published,
        }),
      })
      setFeedback('Page saved. View it on the public site after a refresh.')
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const insertStarter = () => {
    const today = new Date().toLocaleDateString('en-GB')
    setDraft((d) => ({
      ...d,
      body: DEFAULT_HTML.replace('{{date}}', today),
    }))
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <div className='muted' style={{ fontSize: 12, marginBottom: 6 }}>
            <Link to='/settings/legal' style={{ color: 'var(--grn)' }}>
              ← Back to legal pages
            </Link>
          </div>
          <h1>Edit · {draft.title || slug}</h1>
          <p>
            Public URL:{' '}
            <a href={`https://voxbulk.com${draft.public_path || ''}`} target='_blank' rel='noreferrer'>
              voxbulk.com{draft.public_path}
            </a>
          </p>
        </div>
      </div>

      <div className='pageShell emailPageShell'>
        {error ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)', marginBottom: 14 }}>{error}</div> : null}
        {loading ? (
          <div className='note'>Loading…</div>
        ) : (
          <div className='card emailTemplateEditCard msgTemplateEditor'>
            <div className='cardHead'>
              <h3>HTML content</h3>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input
                  type='checkbox'
                  checked={Boolean(draft.is_published)}
                  onChange={(e) => setDraft((d) => ({ ...d, is_published: e.target.checked }))}
                />
                <span className='muted' style={{ fontSize: 12 }}>
                  Published on public site
                </span>
              </label>
            </div>
            <div className='cardBody'>
              <div className='msgFieldBlock'>
                <label className='label'>Page title</label>
                <input
                  className='input'
                  value={draft.title}
                  onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
                />
              </div>
              <div className='msgFieldBlock'>
                <label className='label'>Meta description (SEO)</label>
                <input
                  className='input'
                  value={draft.meta_description}
                  onChange={(e) => setDraft((d) => ({ ...d, meta_description: e.target.value }))}
                  placeholder='Short summary for search engines'
                />
              </div>

              <div className='emailEditorSplit'>
                <div className='emailEditorFields'>
                  <label className='label emailBodyLabel'>HTML body</label>
                  <textarea
                    className='input msgFieldBodyBox'
                    value={draft.body}
                    onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))}
                    placeholder='<h2>Terms</h2><p>Your legal text…</p>'
                  />
                  <p className='fieldHint'>Paste full HTML for this page. Plain text works too — wrap paragraphs in &lt;p&gt; tags for best layout.</p>
                </div>

                <div className='msgFieldBlock msgFieldBlockTight emailEditorPreviewCol'>
                  <label className='label'>
                    <i className='ti ti-eye' style={{ marginRight: 6 }} />
                    Live preview
                  </label>
                  <div className='emailPreviewBox emailPreviewBoxTall'>
                    {draft.body ? (
                      <div className='emailPreviewInner legalPreviewInner' dangerouslySetInnerHTML={{ __html: draft.body }} />
                    ) : (
                      <p className='muted' style={{ margin: 0 }}>
                        HTML preview appears here.
                      </p>
                    )}
                  </div>
                </div>
              </div>

              <div className='actions emailTemplateTestRow' style={{ flexWrap: 'wrap', marginTop: 20 }}>
                <button type='button' className='btn primary' onClick={save} disabled={saving || !draft.title.trim()}>
                  <i className='ti ti-device-floppy' />
                  {saving ? 'Saving…' : 'Save page'}
                </button>
                <button type='button' className='btn soft' onClick={insertStarter}>
                  Insert starter HTML
                </button>
                <button
                  type='button'
                  className='btn soft'
                  onClick={() => window.open(`https://voxbulk.com${draft.public_path}`, '_blank', 'noopener,noreferrer')}
                >
                  View public page
                </button>
                {feedback ? <span className='muted' style={{ fontSize: 12, alignSelf: 'center' }}>{feedback}</span> : null}
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
