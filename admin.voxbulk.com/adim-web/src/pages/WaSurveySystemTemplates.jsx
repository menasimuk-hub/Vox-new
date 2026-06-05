import React, { useCallback, useEffect, useMemo, useState } from 'react'

import { Link } from 'react-router-dom'

import { apiFetch } from '../lib/api'

import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'

import { resolveTelnyxSyncLabel, telnyxSyncPillClass, validateCategoryBeforeSync } from '../lib/waSurveyTelnyxSync'

import WaSurveyTemplateModal from '../components/WaSurveyTemplateModal'



const KIND_OPTIONS = [

  { value: 'welcome', label: 'Welcome' },

  { value: 'thank_you', label: 'Thank you' },

  { value: 'tell_us_more', label: 'Tell us more' },

]



const PRIVACY_OPTIONS = [

  { value: 'off', label: 'Named (uses first name variable)' },

  { value: 'on', label: 'Noname (anonymous wording)' },

]



function kindLabel(kind) {

  return KIND_OPTIONS.find((k) => k.value === kind)?.label || kind

}



function formatWhen(iso) {

  if (!iso) return '—'

  try {

    return new Date(iso).toLocaleString()

  } catch {

    return iso

  }

}



function fullBody(tpl) {
  return String(tpl?.body_text || tpl?.body_preview || '').trim() || 'No body text yet'
}

function bodyPreview(tpl) {
  const text = fullBody(tpl)
  return text.length > 180 ? `${text.slice(0, 180)}…` : text
}



function variantBadgeClass(label) {

  return String(label || '').toLowerCase() === 'noname' ? 'muted' : 'ok'

}



export default function WaSurveySystemTemplates() {

  const [loading, setLoading] = useState(true)

  const [working, setWorking] = useState('')

  const [error, setError] = useState('')

  const [errorDetail, setErrorDetail] = useState('')

  const [msg, setMsg] = useState('')

  const [kinds, setKinds] = useState([])

  const [modalTemplateId, setModalTemplateId] = useState(null)

  const [modalTemplate, setModalTemplate] = useState(null)

  const [viewTemplate, setViewTemplate] = useState(null)

  const [createModal, setCreateModal] = useState(null)

  const [highlightId, setHighlightId] = useState(null)

  const [genKind, setGenKind] = useState('welcome')

  const [genInstruction, setGenInstruction] = useState('')

  const [genCount, setGenCount] = useState(2)

  const [genResult, setGenResult] = useState(null)

  const [selectedGen, setSelectedGen] = useState({})



  const clearFeedback = () => {

    setError('')

    setErrorDetail('')

    setMsg('')

  }



  const showError = (err, fallback = 'Request failed') => {

    const formatted = formatWaSurveyError(err, fallback)

    setError(formatted.message)

    setErrorDetail(formatted.detailText !== formatted.message ? formatted.detailText : '')

    setMsg('')

  }



  const showOk = (result, fallback = 'Done') => {

    const formatted = formatActionSuccess(result, fallback)

    setError('')

    setErrorDetail('')

    setMsg(formatted.message)

  }



  const load = useCallback(async () => {

    setLoading(true)

    clearFeedback()

    try {

      const data = await apiFetch('/admin/wa-survey/system-templates')

      setKinds(Array.isArray(data?.kinds) ? data.kinds : [])

    } catch (e) {

      showError(e, 'Could not load global system templates')

    } finally {

      setLoading(false)

    }

  }, [])



  useEffect(() => {

    void load()

  }, [load])



  useEffect(() => {

    if (!highlightId) return undefined

    const timer = window.setTimeout(() => setHighlightId(null), 4000)

    return () => window.clearTimeout(timer)

  }, [highlightId])



  const surveyTypeIdForKind = useMemo(() => {

    const map = {}

    for (const k of kinds) {

      if (k.kind && k.survey_type_id) map[k.kind] = k.survey_type_id

    }

    return map

  }, [kinds])



  const openCreateModal = (kind) => {

    setCreateModal({

      kind: kind || 'welcome',

      display_name: '',

      privacy_mode: 'off',

    })

  }



  const submitCreate = async (e) => {

    e.preventDefault()

    if (!createModal) return

    setWorking('create')

    clearFeedback()

    try {

      const result = await apiFetch('/admin/wa-survey/system-templates', {

        method: 'POST',

        body: JSON.stringify({

          system_template_kind: createModal.kind,

          display_name: createModal.display_name.trim() || undefined,

          privacy_mode: createModal.privacy_mode,

        }),

      })

      const created = result?.template

      showOk(result, `Created ${kindLabel(createModal.kind)} template.`)

      setCreateModal(null)

      if (created?.id) setHighlightId(created.id)

      await load()

    } catch (err) {

      showError(err, 'Could not create template')

    } finally {

      setWorking('')

    }

  }



  const deleteTemplate = async (tpl, kind) => {

    if (!window.confirm(`Delete “${tpl.display_name || tpl.name}”? This removes it from Telnyx when synced.`)) return

    setWorking(`delete-${tpl.id}`)

    clearFeedback()

    try {

      await apiFetch(`/admin/wa-survey/system-templates/${encodeURIComponent(tpl.id)}`, { method: 'DELETE' })

      showOk(null, 'Template deleted.')

      if (modalTemplateId === tpl.id) {

        setModalTemplateId(null)

        setModalTemplate(null)

      }

      if (viewTemplate?.id === tpl.id) setViewTemplate(null)

      await load()

    } catch (e) {

      showError(e, 'Could not delete template')

    } finally {

      setWorking('')

    }

  }



  const pushOne = async (tpl) => {

    const catErr = validateCategoryBeforeSync(tpl)

    if (catErr) {

      showError({ message: catErr }, 'Fix category before sync')

      return

    }

    setWorking(`push-${tpl.id}`)

    clearFeedback()

    try {

      const result = await apiFetch(`/admin/wa-survey/templates/${encodeURIComponent(tpl.id)}/push`, {

        method: 'POST',

        body: '{}',

      })

      showOk(result, 'Pushed to Telnyx.')

      await load()

    } catch (e) {

      showError(e, 'Telnyx sync failed')

    } finally {

      setWorking('')

    }

  }



  const runGenerate = async () => {

    setWorking('generate')

    clearFeedback()

    setGenResult(null)

    setSelectedGen({})

    try {

      const data = await apiFetch('/admin/wa-survey/system-templates/generate', {

        method: 'POST',

        body: JSON.stringify({

          system_template_kind: genKind,

          instruction: genInstruction,

          count: Number(genCount) || 1,

        }),

      })

      setGenResult(data)

      const next = {}

      ;(data?.templates || []).forEach((row, idx) => {

        if (row.valid && row.template) next[idx] = true

      })

      setSelectedGen(next)

      showOk(data, `Generated ${data.valid_count || 0} valid template(s).`)

    } catch (e) {

      showError(e, 'OpenAI generation failed')

    } finally {

      setWorking('')

    }

  }



  const saveGenerated = async () => {

    if (!genResult) return

    const picked = (genResult.templates || []).filter((row, idx) => selectedGen[idx] && row.valid && row.template)

    if (!picked.length) {

      showError({ message: 'Select at least one valid generated template.' }, 'Nothing selected')

      return

    }

    setWorking('save-gen')

    clearFeedback()

    try {

      const result = await apiFetch('/admin/wa-survey/system-templates/save-generated', {

        method: 'POST',

        body: JSON.stringify({

          system_template_kind: genResult.system_template_kind || genKind,

          instruction: genInstruction,

          templates: picked.map((row) => row.template),

        }),

      })

      showOk(result, 'Saved generated templates — see the matching group below.')

      setGenResult(null)

      setSelectedGen({})

      await load()

    } catch (e) {

      showError(e, 'Could not save generated templates')

    } finally {

      setWorking('')

    }

  }



  const openEdit = (tpl, section) => {

    setViewTemplate(null)

    setModalTemplate({

      ...tpl,

      system_template_kind: tpl.system_template_kind || section.kind,

    })

    setModalTemplateId(tpl.id)

  }



  const openView = (tpl, section) => {

    setModalTemplateId(null)

    setModalTemplate(null)

    setViewTemplate({

      ...tpl,

      system_template_kind: tpl.system_template_kind || section.kind,

    })

  }



  return (

    <div className="content">

      <div className="breadcrumb">

        <Link to="/settings/wa-survey">WA Survey</Link>

        <span> / Global System Templates</span>

      </div>



      <div className="pageHead">

        <div>

          <h1>Global System Templates</h1>

          <p className="muted">

            Shared welcome, thank-you, and tell-us-more WhatsApp templates under the hidden

            {' '}<code>system-survey-templates</code> industry. Each group maps to one system survey type.

            Templates stay visible here after save — grouped by kind below.

          </p>

        </div>

      </div>



      {error ? (

        <div className="note" style={{ borderColor: 'var(--red)', color: 'var(--red)' }}>

          {error}

          {errorDetail ? <div className="fieldHint">{errorDetail}</div> : null}

        </div>

      ) : null}

      {msg ? <div className="note">{msg}</div> : null}



      <section className="card">

        <div className="cardHead">

          <h2>Generate with OpenAI</h2>

        </div>

        <div className="cardBody orgProfileGrid2">

          <div className="formField">

            <label className="label" htmlFor="sys-kind">Template type</label>

            <select id="sys-kind" className="select" value={genKind} onChange={(e) => setGenKind(e.target.value)}>

              {KIND_OPTIONS.map((k) => (

                <option key={k.value} value={k.value}>{k.label}</option>

              ))}

            </select>

          </div>

          <div className="formField">

            <label className="label" htmlFor="sys-count">Variants to generate</label>

            <input

              id="sys-count"

              className="input"

              type="number"

              min={1}

              max={6}

              value={genCount}

              onChange={(e) => setGenCount(e.target.value)}

            />

            <p className="fieldHint">Typically 2 per type — not limited to 2.</p>

          </div>

          <div className="formField span-12" style={{ gridColumn: '1 / -1' }}>

            <label className="label" htmlFor="sys-instruction">Optional instructions</label>

            <textarea

              id="sys-instruction"

              className="input"

              rows={3}

              value={genInstruction}

              onChange={(e) => setGenInstruction(e.target.value)}

              placeholder="e.g. Warm UK tone, mention it only takes a minute…"

            />

          </div>

          <div className="actions">

            <button type="button" className="btn primary" disabled={working === 'generate'} onClick={() => void runGenerate()}>

              {working === 'generate' ? 'Generating…' : 'Generate drafts'}

            </button>

            {genResult ? (

              <button type="button" className="btn soft" disabled={working === 'save-gen'} onClick={() => void saveGenerated()}>

                {working === 'save-gen' ? 'Saving…' : 'Save selected'}

              </button>

            ) : null}

          </div>

        </div>

        {genResult?.templates?.length ? (

          <div className="cardBody" style={{ borderTop: '1px solid var(--line)' }}>

            <p className="formSectionTitle">Generated previews</p>

            <div className="tableWrap">

              <table className="table">

                <thead>

                  <tr>

                    <th>Use</th>

                    <th>Name</th>

                    <th>Body preview</th>

                    <th>Status</th>

                  </tr>

                </thead>

                <tbody>

                  {genResult.templates.map((row, idx) => {

                    const tpl = row.template || {}

                    const valid = Boolean(row.valid)

                    return (

                      <tr key={idx}>

                        <td>

                          <input

                            type="checkbox"

                            disabled={!valid}

                            checked={Boolean(selectedGen[idx])}

                            onChange={(e) => setSelectedGen((prev) => ({ ...prev, [idx]: e.target.checked }))}

                          />

                        </td>

                        <td>{tpl.title || tpl.template_name || '—'}</td>

                        <td>{String(tpl.body || '').slice(0, 120)}{String(tpl.body || '').length > 120 ? '…' : ''}</td>

                        <td>{valid ? 'Valid' : (row.errors || []).join('; ') || 'Invalid'}</td>

                      </tr>

                    )

                  })}

                </tbody>

              </table>

            </div>

          </div>

        ) : null}

      </section>



      {loading ? (

        <div className="card"><div className="cardBody muted">Loading…</div></div>

      ) : (

        kinds.map((section) => (

          <section className="card" key={section.kind} id={`system-templates-${section.kind}`}>

            <div className="cardHead">

              <h2>

                {section.label || kindLabel(section.kind)}

                <span className="muted" style={{ fontWeight: 500, marginLeft: 8 }}>

                  ({section.count ?? (section.templates || []).length} template{(section.count ?? (section.templates || []).length) === 1 ? '' : 's'})

                </span>

              </h2>

              <div className="actions">

                <button

                  type="button"

                  className="btn sm primary"

                  disabled={working === 'create'}

                  onClick={() => openCreateModal(section.kind)}

                >

                  New template

                </button>

              </div>

            </div>

            <div className="cardBody">

              <p className="fieldHint" style={{ marginBottom: 12 }}>

                Stored under survey type <code>{section.survey_type_slug || section.kind}</code>

                {section.survey_type_id ? <> · ID <code>{section.survey_type_id}</code></> : null}

                {' '}·{' '}

                {section.kind === 'welcome' && 'Customers pick one welcome template when creating a survey.'}

                {section.kind === 'thank_you' && 'Customers pick one thank-you template when creating a survey.'}

                {section.kind === 'tell_us_more' && 'Applied automatically after a low rating (not in customer picker).'}

              </p>

              {(section.templates || []).length ? (

                <div className="waSurveySystemTemplateList">

                  {section.templates.map((tpl) => (

                    <article

                      key={tpl.id}

                      className={`waSurveySystemTemplateCard${highlightId === tpl.id ? ' waSurveySystemTemplateCardHighlight' : ''}`}

                    >

                      <div className="waSurveySystemTemplateMain">

                        <div className="waSurveySystemTemplateTitleRow">

                          <p className="waSurveySystemTemplateTitle">{tpl.display_name || tpl.name || 'Untitled template'}</p>

                          <span className={`pill ${variantBadgeClass(tpl.variant_label)}`}>

                            {tpl.variant_label || 'Named'}

                          </span>

                          <span className="pill muted">{kindLabel(tpl.system_template_kind || section.kind)}</span>

                        </div>

                        <p className="waSurveySystemTemplateBody">{bodyPreview(tpl)}</p>

                        <div className="waSurveySystemTemplateMeta">

                          <span>ID {tpl.id}</span>

                          <span>{tpl.language || '—'}</span>

                          <span className={`pill ${telnyxSyncPillClass(resolveTelnyxSyncLabel(tpl))}`}>

                            {resolveTelnyxSyncLabel(tpl)}

                          </span>

                          <span>{tpl.active_for_survey ? 'Active' : 'Inactive'}</span>

                          <span>Updated {formatWhen(tpl.updated_at || tpl.created_at)}</span>

                        </div>

                      </div>

                      <div className="waSurveySystemTemplateActions">

                        <button type="button" className="btn sm soft" onClick={() => openView(tpl, section)}>

                          View

                        </button>

                        <button type="button" className="btn sm" onClick={() => openEdit(tpl, section)}>

                          Edit

                        </button>

                        <button

                          type="button"

                          className="btn sm soft"

                          disabled={working === `push-${tpl.id}`}

                          onClick={() => void pushOne(tpl)}

                        >

                          {working === `push-${tpl.id}` ? 'Syncing…' : 'Sync to Telnyx'}

                        </button>

                        <button

                          type="button"

                          className="btn sm soft danger"

                          disabled={working === `delete-${tpl.id}`}

                          onClick={() => void deleteTemplate(tpl, section.kind)}

                        >

                          {working === `delete-${tpl.id}` ? 'Deleting…' : 'Delete'}

                        </button>

                      </div>

                    </article>

                  ))}

                </div>

              ) : (

                <p className="muted">No templates yet — create one or generate with OpenAI.</p>

              )}

            </div>

          </section>

        ))

      )}



      {createModal ? (

        <div className="modalOverlay" role="presentation" onClick={() => setCreateModal(null)}>

          <form

            className="leadModal"

            role="dialog"

            aria-modal="true"

            onSubmit={submitCreate}

            onClick={(e) => e.stopPropagation()}

          >

            <div className="leadModalHead">

              <h3>Create global system template</h3>

              <button type="button" className="btn soft" onClick={() => setCreateModal(null)} aria-label="Close">×</button>

            </div>

            <div className="leadModalBody grid2">

              <label className="field">

                <span>Kind</span>

                <select

                  className="input"

                  value={createModal.kind}

                  onChange={(e) => setCreateModal({ ...createModal, kind: e.target.value })}

                >

                  {KIND_OPTIONS.map((k) => (

                    <option key={k.value} value={k.value}>{k.label}</option>

                  ))}

                </select>

              </label>

              <label className="field">

                <span>Named / Noname</span>

                <select

                  className="input"

                  value={createModal.privacy_mode}

                  onChange={(e) => setCreateModal({ ...createModal, privacy_mode: e.target.value })}

                >

                  {PRIVACY_OPTIONS.map((opt) => (

                    <option key={opt.value} value={opt.value}>{opt.label}</option>

                  ))}

                </select>

              </label>

              <label className="field" style={{ gridColumn: '1 / -1' }}>

                <span>Display name (optional)</span>

                <input

                  className="input"

                  value={createModal.display_name}

                  onChange={(e) => setCreateModal({ ...createModal, display_name: e.target.value })}

                  placeholder="e.g. Warm welcome — Named"

                />

              </label>

              <p className="muted" style={{ gridColumn: '1 / -1', margin: 0 }}>

                After save, the template appears in the <strong>{kindLabel(createModal.kind)}</strong> group above.

              </p>

            </div>

            <div className="leadModalFoot">

              <button type="button" className="btn ghost" onClick={() => setCreateModal(null)}>Cancel</button>

              <button type="submit" className="btn primary" disabled={working === 'create'}>

                {working === 'create' ? 'Creating…' : 'Create template'}

              </button>

            </div>

          </form>

        </div>

      ) : null}



      {viewTemplate ? (

        <div className="modalOverlay" role="presentation" onClick={() => setViewTemplate(null)}>

          <div

            className="leadModal waSurveySystemTemplateView"

            role="dialog"

            aria-modal="true"

            onClick={(e) => e.stopPropagation()}

          >

            <div className="leadModalHead">

              <h3>{viewTemplate.display_name || viewTemplate.name || 'Template details'}</h3>

              <button type="button" className="btn soft" onClick={() => setViewTemplate(null)} aria-label="Close">×</button>

            </div>

            <div className="leadModalBody">

              <div className="waSurveySystemTemplateViewMeta">

                <span className={`pill ${variantBadgeClass(viewTemplate.variant_label)}`}>{viewTemplate.variant_label || 'Named'}</span>

                <span className="pill muted">{kindLabel(viewTemplate.system_template_kind)}</span>

                <span className={`pill ${telnyxSyncPillClass(resolveTelnyxSyncLabel(viewTemplate))}`}>

                  {resolveTelnyxSyncLabel(viewTemplate)}

                </span>

              </div>

              <dl className="waSurveySystemTemplateViewDl">

                <div><dt>Template ID</dt><dd><code>{viewTemplate.id}</code></dd></div>

                <div><dt>Survey type</dt><dd><code>{viewTemplate.survey_type_id || '—'}</code></dd></div>

                <div><dt>Language</dt><dd>{viewTemplate.language || '—'}</dd></div>

                <div><dt>Category</dt><dd>{viewTemplate.category || '—'}</dd></div>

                <div><dt>Last updated</dt><dd>{formatWhen(viewTemplate.updated_at || viewTemplate.created_at)}</dd></div>

              </dl>

              <label className="field">

                <span>Body</span>

                <textarea className="input" rows={6} readOnly value={fullBody(viewTemplate)} />

              </label>

              {viewTemplate.footer ? (

                <label className="field">

                  <span>Footer</span>

                  <input className="input" readOnly value={viewTemplate.footer} />

                </label>

              ) : null}

              {Array.isArray(viewTemplate.example_values) && viewTemplate.example_values.length ? (

                <label className="field">

                  <span>Variables</span>

                  <input className="input" readOnly value={viewTemplate.example_values.join(', ')} />

                </label>

              ) : null}

              {Array.isArray(viewTemplate.buttons) && viewTemplate.buttons.length ? (

                <label className="field">

                  <span>Buttons</span>

                  <input

                    className="input"

                    readOnly

                    value={viewTemplate.buttons.map((b) => b.text || b.title).filter(Boolean).join(' · ')}

                  />

                </label>

              ) : null}

            </div>

            <div className="leadModalFoot">

              <button type="button" className="btn ghost" onClick={() => setViewTemplate(null)}>Close</button>

              <button

                type="button"

                className="btn primary"

                onClick={() => {

                  const section = { kind: viewTemplate.system_template_kind }

                  openEdit(viewTemplate, section)

                  setViewTemplate(null)

                }}

              >

                Edit template

              </button>

            </div>

          </div>

        </div>

      ) : null}



      <WaSurveyTemplateModal

        templateId={modalTemplateId}

        initialTemplate={modalTemplate}

        surveyTypeId={

          surveyTypeIdForKind[modalTemplate?.system_template_kind]

          || modalTemplate?.survey_type_id

          || kinds.find((k) => k.kind === modalTemplate?.system_template_kind)?.survey_type_id

        }

        systemTemplateMode

        systemTemplateKind={modalTemplate?.system_template_kind}

        open={Boolean(modalTemplateId)}

        onClose={() => {

          setModalTemplateId(null)

          setModalTemplate(null)

        }}

        onSaved={(saved) => {

          if (saved?.id) setHighlightId(saved.id)

          void load()

        }}

      />

    </div>

  )

}


