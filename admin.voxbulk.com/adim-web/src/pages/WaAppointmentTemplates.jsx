import React, { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'
import { resolveTelnyxSyncLabel, telnyxSyncPillClass } from '../lib/waSurveyTelnyxSync'
import { substituteTemplateVars } from '../lib/waAppointmentTemplateVars'
import WaAppointmentTemplateModal from '../components/WaAppointmentTemplateModal'
import WaPhonePreview from '../components/WaPhonePreview'
import '../styles/waTemplateEditor.css'

function formatWhen(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function previewBody(tpl) {
  const components = tpl?.draft_components || tpl?.remote_components
  let body = tpl?.body_preview || ''
  if (Array.isArray(components)) {
    const row = components.find((c) => String(c?.type || '').toUpperCase() === 'BODY')
    if (row?.text) body = row.text
  }
  const examples = Array.isArray(tpl?.example_values) ? tpl.example_values : ['Alex']
  return substituteTemplateVars(body, examples)
}

export default function WaAppointmentTemplates() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [templates, setTemplates] = useState([])
  const [editId, setEditId] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch('/admin/wa-appointment/templates')
      setTemplates(Array.isArray(data?.templates) ? data.templates : [])
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load appointment templates').message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const raw = searchParams.get('edit')
    if (!raw) return
    const id = Number.parseInt(raw, 10)
    if (Number.isFinite(id) && id > 0) setEditId(id)
  }, [searchParams])

  const closeEditor = () => {
    setEditId(null)
    if (searchParams.get('edit')) {
      const next = new URLSearchParams(searchParams)
      next.delete('edit')
      setSearchParams(next, { replace: true })
    }
  }

  const syncAll = async () => {
    setWorking('sync')
    setError('')
    setMsg('')
    try {
      const result = await apiFetch('/admin/wa-appointment/sync', { method: 'POST', body: '{}' })
      if (result?.ok === false) {
        throw Object.assign(new Error(result.message || 'Telnyx sync failed'), { data: { detail: result } })
      }
      setMsg(formatActionSuccess(result, 'Synced from Telnyx').message)
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Telnyx sync failed').detailText)
    } finally {
      setWorking('')
    }
  }

  const toggleHidden = async (tpl) => {
    setWorking(`hide-${tpl.id}`)
    try {
      await apiFetch(`/admin/wa-appointment/templates/${tpl.id}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ active_for_appointment: tpl.active_for_appointment === false }),
      })
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not update visibility').message)
    } finally {
      setWorking('')
    }
  }

  const deleteTemplate = async (tpl) => {
    if (!window.confirm(`Delete “${tpl.display_name || tpl.name}”? This removes it from Telnyx when synced.`)) return
    setWorking(`delete-${tpl.id}`)
    try {
      const result = await apiFetch(`/admin/wa-appointment/templates/${tpl.id}`, { method: 'DELETE' })
      setMsg(formatActionSuccess(result, 'Template deleted').message)
      if (editId === tpl.id) closeEditor()
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not delete template').message)
    } finally {
      setWorking('')
    }
  }

  const pushTemplate = async (tpl) => {
    setWorking(`push-${tpl.id}`)
    try {
      const result = await apiFetch(`/admin/wa-appointment/templates/${tpl.id}/push`, { method: 'POST', body: '{}' })
      setMsg(formatActionSuccess(result, 'Synced to Telnyx').message)
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Telnyx push failed').detailText)
    } finally {
      setWorking('')
    }
  }

  return (
    <div className="pageShell waApptTemplatesPage">
      <div className="pageTop">
        <div>
          <p className="muted" style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>Platform Settings</p>
          <h1>WA Appointment templates</h1>
          <p className="muted">
            UTILITY WhatsApp templates for Appointment Manager — edit copy, preview on mobile, sync to Telnyx.
          </p>
        </div>
        <div className="actions">
          <Link className="btn" to="/operations/running-appointments">Running appointments</Link>
          <button type="button" className="btn primary" disabled={working === 'sync'} onClick={() => void syncAll()}>
            {working === 'sync' ? 'Syncing…' : 'Sync from Telnyx'}
          </button>
        </div>
      </div>

      {error ? <div className="alert err">{error}</div> : null}
      {msg ? <div className="alert ok">{msg}</div> : null}

      {loading ? (
        <p className="muted">Loading templates…</p>
      ) : !templates.length ? (
        <div className="card">
          <div className="cardBody note">No templates seeded yet — deploy API migration 0130 and refresh.</div>
        </div>
      ) : (
        <div className="waApptTemplateGrid">
          {templates.map((tpl) => (
            <article key={tpl.id} className="waApptTemplateCard">
              <div className="waApptTemplateCard__preview">
                <WaPhonePreview
                  compact
                  title="VoxBulk"
                  body={previewBody(tpl)}
                  buttons={tpl.buttons || []}
                />
              </div>
              <div className="waApptTemplateCard__body">
                <div className="waApptTemplateCard__head">
                  <div>
                    <h3>{tpl.display_name || tpl.name}</h3>
                    <p className="muted">{tpl.description || tpl.sales_template_key}</p>
                  </div>
                  <span className={telnyxSyncPillClass(resolveTelnyxSyncLabel(tpl))}>
                    {resolveTelnyxSyncLabel(tpl)}
                  </span>
                </div>
                <div className="waApptTemplateCard__meta">
                  <code>{tpl.name}</code>
                  <span>{tpl.active_for_appointment === false ? 'Hidden' : 'Active'}</span>
                  <span className="muted">{formatWhen(tpl.updated_at || tpl.last_pushed_at)}</span>
                </div>
                <div className="waApptTemplateCard__actions">
                  <button type="button" className="btn soft sm" onClick={() => setEditId(tpl.id)}>Edit</button>
                  <button type="button" className="btn soft sm" disabled={!!working} onClick={() => void toggleHidden(tpl)}>
                    {tpl.active_for_appointment === false ? 'Show' : 'Hide'}
                  </button>
                  <button type="button" className="btn soft sm" disabled={!!working} onClick={() => void pushTemplate(tpl)}>Sync</button>
                  <button type="button" className="btn sm danger" disabled={!!working} onClick={() => void deleteTemplate(tpl)}>Delete</button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      <WaAppointmentTemplateModal
        templateId={editId}
        open={Boolean(editId)}
        onClose={closeEditor}
        onSaved={() => void load()}
      />
    </div>
  )
}
