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
  { value: 'final_feedback', label: 'Closing question' },
]

const PRIVACY_OPTIONS = [
  { value: 'off', label: 'Named' },
  { value: 'on', label: 'Noname' },
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

function draftBody(tpl, raw) {
  const source = tpl && typeof tpl === 'object' ? tpl : raw
  return String(source?.body || source?.body_text || source?.body_preview || '').trim() || 'No body text yet'
}

function draftFooter(tpl) {
  return String(tpl?.footer || '').trim()
}

function variantBadgeClass(label) {
  return String(label || '').toLowerCase() === 'noname' ? 'muted' : 'ok'
}

function draftVariantLabel(tpl) {
  const variant = String(tpl?.variant_type || '').toLowerCase()
  const privacy = String(tpl?.privacy_mode || '').toLowerCase()
  if (variant === 'anonymous' || privacy === 'on') return 'Noname'
  return 'Named'
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
  const [genDraftEdits, setGenDraftEdits] = useState({})
  const [genDraftView, setGenDraftView] = useState(null)

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
    const timer = window.setTimeout(() => setHighlightId(null), 5000)
    return () => window.clearTimeout(timer)
  }, [highlightId])

  const surveyTypeIdForKind = useMemo(() => {
    const map = {}
    for (const k of kinds) {
      if (k.kind && k.survey_type_id) map[k.kind] = k.survey_type_id
    }
    return map
  }, [kinds])

  const mergedGenTemplates = useMemo(() => {
    if (!genResult?.templates) return []
    return genResult.templates.map((row, idx) => {
      const raw = row?.raw && typeof row.raw === 'object' ? row.raw : {}
      const base = row?.template && typeof row.template === 'object' ? row.template : raw
      const edits = genDraftEdits[idx] || {}
      return {
        idx,
        valid: Boolean(row.valid),
        errors: row.errors || [],
        raw,
        template: { ...base, ...edits },
      }
    })
  }, [genResult, genDraftEdits])

  const scrollToKind = (kind) => {
    const el = document.getElementById(`system-templates-${kind}`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const openCreateModal = (kind) => {
    setCreateModal({ kind: kind || 'welcome', display_name: '', privacy_mode: 'off' })
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
      showOk(result, `Saved to ${kindLabel(createModal.kind)} library.`)
      setCreateModal(null)
      if (created?.id) {
        setHighlightId(created.id)
        await load()
        scrollToKind(createModal.kind)
      } else {
        await load()
      }
    } catch (err) {
      showError(err, 'Could not create template')
    } finally {
      setWorking('')
    }
  }

  const deleteTemplate = async (tpl) => {
    if (!window.confirm(`Delete “${tpl.display_name || tpl.name}”? This removes it from Telnyx when synced.`)) return
    setWorking(`delete-${tpl.id}`)
    clearFeedback()
    try {
      await apiFetch(`/admin/wa-survey/system-templates/${encodeURIComponent(tpl.id)}`, { method: 'DELETE' })
      showOk(null, 'Template deleted from library.')
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

  const toggleTemplateActive = async (tpl) => {
    const nextActive = tpl.active_for_survey === false
    setWorking(`active-${tpl.id}`)
    clearFeedback()
    try {
      const result = await apiFetch(`/admin/wa-survey/templates/${encodeURIComponent(tpl.id)}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ active: nextActive }),
      })
      showOk(result, nextActive ? 'Template enabled.' : 'Template hidden from surveys.')
      await load()
    } catch (e) {
      showError(e, 'Could not update template visibility')
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
    setGenDraftEdits({})
    setGenDraftView(null)
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
      showOk(data, `Generated ${data.valid_count || 0} draft(s). Review below, then save into the library.`)
    } catch (e) {
      showError(e, 'OpenAI generation failed')
    } finally {
      setWorking('')
    }
  }

  const saveGeneratedRows = async (rows, { clearDrafts = false } = {}) => {
    const picked = rows.filter((row) => row.valid && row.template)
    if (!picked.length) {
      showError({ message: 'No valid drafts selected to save.' }, 'Nothing to save')
      return
    }
    const kind = genResult?.system_template_kind || genKind
    setWorking('save-gen')
    clearFeedback()
    try {
      const result = await apiFetch('/admin/wa-survey/system-templates/save-generated', {
        method: 'POST',
        body: JSON.stringify({
          system_template_kind: kind,
          instruction: genInstruction,
          templates: picked.map((row) => row.template),
        }),
      })
      const saved = Array.isArray(result?.saved_templates) ? result.saved_templates : []
      if (Array.isArray(result?.kinds) && result.kinds.length) {
        setKinds(result.kinds)
      } else {
        await load()
      }
      if (saved[0]?.id) {
        setHighlightId(saved[0].id)
        scrollToKind(kind)
      }
      showOk(result, `Saved ${result.saved_count || saved.length || picked.length} template(s) to ${kindLabel(kind)} library.`)
      if (clearDrafts) {
        setGenResult(null)
        setSelectedGen({})
        setGenDraftEdits({})
        setGenDraftView(null)
      }
    } catch (e) {
      showError(e, 'Could not save generated templates')
    } finally {
      setWorking('')
    }
  }

  const saveSelectedGenerated = () => {
    const rows = mergedGenTemplates.filter((row, idx) => selectedGen[idx])
    void saveGeneratedRows(rows, { clearDrafts: true })
  }

  const saveOneGenerated = (idx) => {
    const row = mergedGenTemplates.find((item) => item.idx === idx)
    if (!row) return
    void saveGeneratedRows([row], { clearDrafts: false })
  }

  const openEditGenerated = (idx) => {
    const row = mergedGenTemplates.find((item) => item.idx === idx)
    if (!row) return
    setGenDraftView({
      idx,
      template: row.template,
      kind: genResult?.system_template_kind || genKind,
    })
  }

  const openViewGenerated = (idx) => {
    openEditGenerated(idx)
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

  const renderSavedCard = (tpl, section) => (
    <article
      key={tpl.id}
      className={`waSurveySystemTemplateCard${highlightId === tpl.id ? ' waSurveySystemTemplateCardHighlight' : ''}${tpl.active_for_survey === false ? ' waSurveySystemTemplateCardMuted' : ''}`}
    >
      <div className="waSurveySystemTemplateMain">
        <div className="waSurveySystemTemplateTitleRow">
          <p className="waSurveySystemTemplateTitle">{tpl.display_name || tpl.name || 'Untitled template'}</p>
          <span className={`pill ${variantBadgeClass(tpl.variant_label)}`}>{tpl.variant_label || 'Named'}</span>
          <span className="pill muted">{kindLabel(tpl.system_template_kind || section.kind)}</span>
        </div>
        <p className="waSurveySystemTemplateBody">{draftBody(tpl)}</p>
        <div className="waSurveySystemTemplateMeta">
          <span>ID {tpl.id}</span>
          <span>{tpl.language || '—'}</span>
          <span className={`pill ${telnyxSyncPillClass(resolveTelnyxSyncLabel(tpl))}`}>
            {resolveTelnyxSyncLabel(tpl)}
          </span>
          <span className={`pill ${tpl.active_for_survey === false ? 'muted' : 'ok'}`}>
            {tpl.active_for_survey === false ? 'Hidden' : 'Active'}
          </span>
          <span>Updated {formatWhen(tpl.updated_at || tpl.created_at)}</span>
        </div>
      </div>
      <div className="waSurveySystemTemplateActions">
        <button type="button" className="btn sm soft" onClick={() => openView(tpl, section)}>View</button>
        <button type="button" className="btn sm" onClick={() => openEdit(tpl, section)}>Edit</button>
        <button
          type="button"
          className="btn sm soft"
          disabled={working === `active-${tpl.id}`}
          onClick={() => void toggleTemplateActive(tpl)}
          title={tpl.active_for_survey === false ? 'Show in survey flows again' : 'Hide from surveys — Telnyx sync still works'}
        >
          {working === `active-${tpl.id}`
            ? 'Updating…'
            : tpl.active_for_survey === false
              ? 'Enable'
              : 'Hide'}
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
          onClick={() => void deleteTemplate(tpl)}
        >
          {working === `delete-${tpl.id}` ? 'Deleting…' : 'Delete'}
        </button>
      </div>
    </article>
  )

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
            Generate drafts with OpenAI, save them into the library below, then edit / sync / delete from the grouped
            Welcome, Thank-you, and Tell us more sections.
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
          <h2>1. Generate drafts (temporary)</h2>
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
            <label className="label" htmlFor="sys-count">Variants</label>
            <input
              id="sys-count"
              className="input"
              type="number"
              min={1}
              max={6}
              value={genCount}
              onChange={(e) => setGenCount(e.target.value)}
            />
          </div>
          <div className="formField" style={{ gridColumn: '1 / -1' }}>
            <label className="label" htmlFor="sys-instruction">Optional instructions</label>
            <textarea
              id="sys-instruction"
              className="input"
              rows={3}
              value={genInstruction}
              onChange={(e) => setGenInstruction(e.target.value)}
            />
          </div>
          <div className="actions">
            <button type="button" className="btn primary" disabled={working === 'generate'} onClick={() => void runGenerate()}>
              {working === 'generate' ? 'Generating…' : 'Generate drafts'}
            </button>
            {genResult ? (
              <button type="button" className="btn soft" disabled={working === 'save-gen'} onClick={saveSelectedGenerated}>
                {working === 'save-gen' ? 'Saving…' : 'Save selected to library'}
              </button>
            ) : null}
          </div>
        </div>

        {mergedGenTemplates.length ? (
          <div className="cardBody waSurveyGenDraftArea" style={{ borderTop: '1px solid var(--line)' }}>
            <p className="formSectionTitle">Generated drafts — not saved until you click Save template</p>
            <div className="waSurveyGenDraftList">
              {mergedGenTemplates.map(({ idx, valid, errors, raw, template }) => (
                <article key={idx} className={`waSurveyGenDraftCard${valid ? '' : ' waSurveyGenDraftCardInvalid'}`}>
                  <div className="waSurveyGenDraftHead">
                    <strong>{template.title || template.template_name || `Draft ${idx + 1}`}</strong>
                    <span className={`pill ${variantBadgeClass(draftVariantLabel(template))}`}>
                      {draftVariantLabel(template)}
                    </span>
                    <span className="pill muted">{kindLabel(genResult?.system_template_kind || genKind)}</span>
                    <span className={`pill ${valid ? 'ok' : 'warn'}`}>{valid ? 'Valid' : 'Invalid'}</span>
                  </div>
                  <label className="field" style={{ marginBottom: 8 }}>
                    <span>Body</span>
                    <textarea className="input waSurveyGenDraftBody" readOnly value={draftBody(template, raw)} />
                  </label>
                  {draftFooter(template) ? (
                    <p className="fieldHint">Footer: {draftFooter(template)}</p>
                  ) : null}
                  {!valid && errors.length ? (
                    <p className="fieldHint" style={{ color: 'var(--red)' }}>{errors.join('; ')}</p>
                  ) : null}
                  <div className="waSurveySystemTemplateActions">
                    <label className="muted" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                      <input
                        type="checkbox"
                        disabled={!valid}
                        checked={Boolean(selectedGen[idx])}
                        onChange={(e) => setSelectedGen((prev) => ({ ...prev, [idx]: e.target.checked }))}
                      />
                      Select
                    </label>
                    <button type="button" className="btn sm soft" onClick={() => openViewGenerated(idx)}>View</button>
                    <button type="button" className="btn sm" onClick={() => openEditGenerated(idx)}>Edit</button>
                    <button
                      type="button"
                      className="btn sm primary"
                      disabled={!valid || working === 'save-gen'}
                      onClick={() => saveOneGenerated(idx)}
                    >
                      Save template
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      <section className="card">
        <div className="cardHead">
          <h2>2. Saved template library</h2>
          <span className="muted">Grouped by kind — counts update after every save</span>
        </div>
      </section>

      {loading ? (
        <div className="card"><div className="cardBody muted">Loading library…</div></div>
      ) : (
        kinds.map((section) => (
          <section className="card" key={section.kind} id={`system-templates-${section.kind}`}>
            <div className="cardHead">
              <h2>
                {section.label || kindLabel(section.kind)}
                <span className="muted" style={{ fontWeight: 500, marginLeft: 8 }}>
                  ({section.count ?? (section.templates || []).length} templates)
                </span>
              </h2>
              <div className="actions">
                <button type="button" className="btn sm primary" disabled={working === 'create'} onClick={() => openCreateModal(section.kind)}>
                  New template
                </button>
              </div>
            </div>
            <div className="cardBody">
              <p className="fieldHint" style={{ marginBottom: 12 }}>
                Stored on survey type <code>{section.survey_type_slug || section.kind}</code>
                {section.survey_type_id ? <> · <code>{section.survey_type_id}</code></> : null}
              </p>
              {(section.templates || []).length ? (
                <div className="waSurveySystemTemplateList">
                  {section.templates.map((tpl) => renderSavedCard(tpl, section))}
                </div>
              ) : (
                <p className="muted">No saved templates yet. Generate drafts above or create a blank template.</p>
              )}
            </div>
          </section>
        ))
      )}

      {createModal ? (
        <div className="modalOverlay" role="presentation" onClick={() => setCreateModal(null)}>
          <form className="leadModal" onSubmit={submitCreate} onClick={(e) => e.stopPropagation()}>
            <div className="leadModalHead">
              <h3>Create blank system template</h3>
              <button type="button" className="btn soft" onClick={() => setCreateModal(null)}>×</button>
            </div>
            <div className="leadModalBody grid2">
              <label className="field">
                <span>Kind</span>
                <select className="input" value={createModal.kind} onChange={(e) => setCreateModal({ ...createModal, kind: e.target.value })}>
                  {KIND_OPTIONS.map((k) => (
                    <option key={k.value} value={k.value}>{k.label}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Named / Noname</span>
                <select className="input" value={createModal.privacy_mode} onChange={(e) => setCreateModal({ ...createModal, privacy_mode: e.target.value })}>
                  {PRIVACY_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </label>
              <label className="field" style={{ gridColumn: '1 / -1' }}>
                <span>Display name</span>
                <input className="input" value={createModal.display_name} onChange={(e) => setCreateModal({ ...createModal, display_name: e.target.value })} />
              </label>
            </div>
            <div className="leadModalFoot">
              <button type="button" className="btn ghost" onClick={() => setCreateModal(null)}>Cancel</button>
              <button type="submit" className="btn primary" disabled={working === 'create'}>
                {working === 'create' ? 'Creating…' : 'Create in library'}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {viewTemplate ? (
        <div className="modalOverlay" role="presentation" onClick={() => setViewTemplate(null)}>
          <div className="leadModal waSurveySystemTemplateView" onClick={(e) => e.stopPropagation()}>
            <div className="leadModalHead">
              <h3>{viewTemplate.display_name || viewTemplate.name}</h3>
              <button type="button" className="btn soft" onClick={() => setViewTemplate(null)}>×</button>
            </div>
            <div className="leadModalBody">
              <textarea className="input waSurveyGenDraftBody" readOnly rows={8} value={draftBody(viewTemplate)} />
              {viewTemplate.footer ? <input className="input" readOnly value={viewTemplate.footer} /> : null}
            </div>
            <div className="leadModalFoot">
              <button type="button" className="btn ghost" onClick={() => setViewTemplate(null)}>Close</button>
              <button type="button" className="btn primary" onClick={() => { openEdit(viewTemplate, { kind: viewTemplate.system_template_kind }); setViewTemplate(null) }}>Edit</button>
            </div>
          </div>
        </div>
      ) : null}

      {genDraftView ? (
        <div className="modalOverlay" role="presentation" onClick={() => setGenDraftView(null)}>
          <form
            className="leadModal waSurveySystemTemplateView"
            onSubmit={(e) => {
              e.preventDefault()
              setGenDraftEdits((prev) => ({
                ...prev,
                [genDraftView.idx]: {
                  title: genDraftView.template.title,
                  template_name: genDraftView.template.template_name,
                  body: genDraftView.template.body,
                  footer: genDraftView.template.footer,
                },
              }))
              setGenDraftView(null)
              showOk(null, 'Draft edits kept locally — click Save template to persist.')
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="leadModalHead">
              <h3>Edit generated draft</h3>
              <button type="button" className="btn soft" onClick={() => setGenDraftView(null)}>×</button>
            </div>
            <div className="leadModalBody">
              <label className="field">
                <span>Name</span>
                <input
                  className="input"
                  value={genDraftView.template.title || genDraftView.template.template_name || ''}
                  onChange={(e) => setGenDraftView((prev) => ({
                    ...prev,
                    template: { ...prev.template, title: e.target.value, template_name: e.target.value },
                  }))}
                />
              </label>
              <label className="field">
                <span>Body</span>
                <textarea
                  className="input waSurveyGenDraftBody"
                  rows={8}
                  value={genDraftView.template.body || ''}
                  onChange={(e) => setGenDraftView((prev) => ({
                    ...prev,
                    template: { ...prev.template, body: e.target.value },
                  }))}
                />
              </label>
              <label className="field">
                <span>Footer</span>
                <input
                  className="input"
                  value={genDraftView.template.footer || ''}
                  onChange={(e) => setGenDraftView((prev) => ({
                    ...prev,
                    template: { ...prev.template, footer: e.target.value },
                  }))}
                />
              </label>
            </div>
            <div className="leadModalFoot">
              <button type="button" className="btn ghost" onClick={() => setGenDraftView(null)}>Cancel</button>
              <button type="submit" className="btn primary">Apply edits</button>
              <button
                type="button"
                className="btn soft"
                onClick={() => {
                  const row = mergedGenTemplates.find((item) => item.idx === genDraftView.idx)
                  if (row) void saveGeneratedRows([{ ...row, template: genDraftView.template }], { clearDrafts: false })
                  setGenDraftView(null)
                }}
              >
                Save template
              </button>
            </div>
          </form>
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
          if (saved?.id) {
            setHighlightId(saved.id)
            scrollToKind(saved.system_template_kind || modalTemplate?.system_template_kind || genKind)
          }
          void load()
        }}
      />
    </div>
  )
}
