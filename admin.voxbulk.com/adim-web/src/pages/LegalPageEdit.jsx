import React, { useCallback, useEffect, useState } from 'react'

import { Link, useParams } from 'react-router-dom'

import { copyText, fetchLegalPage, saveLegalPage } from '../lib/legalPagesApi'



const DEFAULT_HTML = `<div class="page-header">

  <div class="page-tag">Legal document</div>

  <div class="page-title">Page title</div>

</div>

<div class="section">

  <div class="section-title">1. Section heading</div>

  <p>Your legal copy…</p>

</div>`



export default function LegalPageEdit() {

  const { slug } = useParams()

  const [loading, setLoading] = useState(true)

  const [saving, setSaving] = useState(false)

  const [offline, setOffline] = useState(false)

  const [apiBase, setApiBase] = useState(null)

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

      const result = await fetchLegalPage(slug)

      const row = result.row

      setDraft({

        slug: row.slug || slug,

        title: row.title || '',

        public_path: row.public_path || '/legal-policies',

        meta_description: row.meta_description || '',

        body: row.body || '',

        is_published: row.is_published !== false,

      })

      setOffline(Boolean(result.offline))

      setApiBase(result.apiBase)

      if (result.offline) {

        setFeedback('Loaded bundled / local draft content. Save stores in this browser until the API is live.')

      }

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

      const payload = {

        title: draft.title.trim(),

        meta_description: draft.meta_description.trim() || null,

        body: draft.body,

        is_published: draft.is_published,

      }

      const result = await saveLegalPage(slug, payload, apiBase)

      setOffline(Boolean(result.offline))

      setApiBase(result.apiBase)

      if (result.offline) {

        setFeedback(

          'Saved in this browser only. To publish on voxbulk.com now: copy HTML → update voxbulk.com/frontend/src/data/legalDefaultBodies.json → rebuild public frontend.',

        )

      } else {

        setFeedback('Page saved to the database. Refresh voxbulk.com/legal-policies to see changes.')

      }

    } catch (e) {

      setError(e?.message || 'Save failed')

    } finally {

      setSaving(false)

    }

  }



  const copyHtml = async () => {

    const ok = await copyText(draft.body || '')

    setFeedback(ok ? 'HTML copied to clipboard.' : 'Could not copy — select the HTML manually.')

  }



  const insertStarter = () => {

    setDraft((d) => ({ ...d, body: DEFAULT_HTML }))

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

            <a

              href={`https://voxbulk.com/legal-policies?tab=${encodeURIComponent(draft.slug || slug || 'terms')}`}

              target='_blank'

              rel='noreferrer'

            >

              voxbulk.com/legal-policies?tab={draft.slug || slug}

            </a>

          </p>

        </div>

      </div>



      <div className='pageShell emailPageShell'>

        {offline ? (

          <div className='note' style={{ borderColor: 'rgba(245,166,35,0.45)', marginBottom: 14 }}>

            Offline mode — API save unavailable. Edits are stored in this browser; use Copy HTML to update the live site file.

          </div>

        ) : null}

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

                    placeholder='<div class="page-header">…</div>'

                  />

                  <p className='fieldHint'>

                    Use the same HTML classes as the live page: page-header, page-title, section, section-title, info-box, table-wrap, etc.

                  </p>

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

                  {saving ? 'Saving…' : offline ? 'Save local draft' : 'Save page'}

                </button>

                <button type='button' className='btn soft' onClick={copyHtml}>

                  Copy HTML

                </button>

                <button type='button' className='btn soft' onClick={insertStarter}>

                  Insert starter HTML

                </button>

                <button

                  type='button'

                  className='btn soft'

                  onClick={() =>

                    window.open(

                      `https://voxbulk.com/legal-policies?tab=${encodeURIComponent(draft.slug || slug || 'terms')}`,

                      '_blank',

                      'noopener,noreferrer',

                    )

                  }

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


