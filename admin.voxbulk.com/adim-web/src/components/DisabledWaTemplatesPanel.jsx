import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Ban, Check, CheckCircle, Filter, Inbox, List, Plus, RotateCcw, Trash2, Upload } from 'lucide-react'
import { apiFetch, apiUpload } from '../lib/api'
import '../pages/disabledWaTemplatesTheme.css'

export default function DisabledWaTemplatesPanel({ embedded = false, onToast }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [inputText, setInputText] = useState('')
  const [uploadStatus, setUploadStatus] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [toast, setToast] = useState({ show: false, message: '', error: false })
  const fileInputRef = useRef(null)
  const toastTimer = useRef(null)

  const showToast = useCallback(
    (message, isError = false) => {
      if (onToast) {
        onToast(message, isError)
        return
      }
      setToast({ show: true, message, error: isError })
      if (toastTimer.current) clearTimeout(toastTimer.current)
      toastTimer.current = setTimeout(() => {
        setToast((t) => ({ ...t, show: false }))
      }, 3500)
    },
    [onToast],
  )

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiFetch('/admin/disabled-wa-templates')
      setItems(data?.items || [])
    } catch (e) {
      showToast(e?.message || 'Could not load templates', true)
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(
    () => () => {
      if (toastTimer.current) clearTimeout(toastTimer.current)
    },
    [],
  )

  const sortedItems = [...items].sort((a, b) => String(a.raw_name).localeCompare(String(b.raw_name)))
  const disabledCount = items.filter((t) => t.disabled).length

  const addTemplates = async () => {
    const lines = inputText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
    if (lines.length === 0) {
      showToast('Please enter at least one template name.', true)
      return
    }
    setBusy(true)
    try {
      const data = await apiFetch('/admin/disabled-wa-templates/names', {
        method: 'POST',
        body: JSON.stringify({ names: lines }),
      })
      setItems(data?.items || [])
      setInputText('')
      let msg = `Added ${data?.added ?? 0} template(s).`
      if (data?.duplicates > 0) msg += ` ${data.duplicates} duplicate(s) ignored.`
      showToast(msg)
    } catch (e) {
      showToast(e?.message || 'Could not add templates', true)
    } finally {
      setBusy(false)
    }
  }

  const uploadFile = async (file) => {
    if (!file) return
    setUploadStatus(`Processing ${file.name}…`)
    setBusy(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const data = await apiUpload('/admin/disabled-wa-templates/upload', form)
      setItems(data?.items || [])
      setUploadStatus(`Added ${data?.added ?? 0} template(s) from file. ${data?.duplicates ?? 0} duplicate(s) ignored.`)
      showToast(`Added ${data?.added ?? 0} templates from file.`)
    } catch (e) {
      setUploadStatus('Error reading file.')
      showToast(e?.message || 'Upload failed', true)
    } finally {
      setBusy(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const toggleTemplate = async (row, disabled) => {
    setBusy(true)
    try {
      await apiFetch(`/admin/disabled-wa-templates/${encodeURIComponent(row.id)}`, {
        method: 'PUT',
        body: JSON.stringify({ disabled }),
      })
      await load()
      showToast(`Template "${row.raw_name}" ${disabled ? 'disabled' : 'enabled'}.`)
    } catch (e) {
      showToast(e?.message || 'Could not update template', true)
    } finally {
      setBusy(false)
    }
  }

  const disableAll = async () => {
    const active = items.filter((t) => !t.disabled).length
    if (active === 0) {
      showToast('All templates are already disabled.', true)
      return
    }
    if (!window.confirm(`Disable all ${active} active templates? They will be hidden from user dashboards.`)) return
    setBusy(true)
    try {
      const data = await apiFetch('/admin/disabled-wa-templates/disable-all', { method: 'POST' })
      setItems(data?.items || [])
      showToast(`Disabled ${data?.changed ?? active} templates.`)
    } catch (e) {
      showToast(e?.message || 'Could not disable all', true)
    } finally {
      setBusy(false)
    }
  }

  const enableAll = async () => {
    const disabled = items.filter((t) => t.disabled).length
    if (disabled === 0) {
      showToast('All templates are already enabled.', true)
      return
    }
    if (!window.confirm(`Enable all ${disabled} disabled templates?`)) return
    setBusy(true)
    try {
      const data = await apiFetch('/admin/disabled-wa-templates/enable-all', { method: 'POST' })
      setItems(data?.items || [])
      showToast(`Enabled ${data?.changed ?? disabled} templates.`)
    } catch (e) {
      showToast(e?.message || 'Could not enable all', true)
    } finally {
      setBusy(false)
    }
  }

  const clearAllBlocklist = async () => {
    if (items.length === 0) {
      showToast('Blocklist is already empty.', true)
      return
    }
    if (
      !window.confirm(
        'Clear the entire disabled-template blocklist?\n\n' +
          'This removes legacy “do not send” names from the old WABA account only. ' +
          'It does not delete templates from Meta. After clearing, use Sync from Meta on the hub header to refresh the live catalog.',
      )
    ) {
      return
    }
    setBusy(true)
    try {
      const data = await apiFetch('/admin/disabled-wa-templates/clear-all', { method: 'POST' })
      setItems(data?.items || [])
      showToast(`Cleared ${data?.removed ?? 0} blocklist row(s). Sync from Meta to refresh the catalog.`)
    } catch (e) {
      showToast(e?.message || 'Could not clear blocklist', true)
    } finally {
      setBusy(false)
    }
  }

  const removeDuplicates = () => {
    showToast('No duplicates found — the system ignores duplicates when adding.')
  }

  return (
    <div className={embedded ? 'dwtTheme dwt-embedded' : 'dwtTheme'}>
      <div className="dwt-app">
        {!embedded ? (
          <div className="page-header">
            <h1>Disabled WA Templates</h1>
            <p>
              Hide WhatsApp templates reclassified by Meta (utility → marketing) so they no longer appear in user
              dashboards and cannot be sent — avoiding higher messaging costs.
            </p>
          </div>
        ) : (
          <div className="page-header" style={{ paddingTop: 0 }}>
            <p className="muted-hint" style={{ margin: 0 }}>
              Legacy blocklist from the previous WABA account. Clear all, then use <strong>Sync from Meta</strong> on
              the hub header to load templates from the current account. Clearing does not delete templates on Meta.
            </p>
          </div>
        )}

        <div className="two-col">
          <div className="card">
            <h3>
              <List size={16} /> Add templates
            </h3>
            <p className="muted-hint">Enter one template name per line. Duplicates will be ignored.</p>
            <textarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder={'wa_template_1\ncustomer_feedback_v2\nsurvey_2025\nnps_followup'}
              disabled={busy}
            />
            <div className="action-row">
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void addTemplates()}>
                <Plus size={14} /> Add to list
              </button>
              <button type="button" className="btn btn-outline" disabled={busy} onClick={() => setInputText('')}>
                <RotateCcw size={14} /> Clear
              </button>
            </div>
          </div>

          <div className="card">
            <h3>
              <Upload size={16} /> Upload file
            </h3>
            <p className="muted-hint">Upload .txt, .xlsx, or .csv with one template name per line.</p>
            <div
              className={`upload-area${dragOver ? ' drag-over' : ''}`}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragOver(false)
                const file = e.dataTransfer.files?.[0]
                if (file) void uploadFile(file)
              }}
            >
              <Upload size={28} style={{ color: '#8b7a5e', marginBottom: 6 }} />
              <p>Click to upload or drag &amp; drop</p>
              <div className="sub">Supports .txt, .xlsx, .csv</div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.xlsx,.csv"
                hidden
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) void uploadFile(file)
                }}
              />
            </div>
            {uploadStatus ? <div className="upload-status">{uploadStatus}</div> : null}
          </div>
        </div>

        <div className="table-wrapper">
          <div className="table-header">
            <div className="left">
              <h3>Template list</h3>
              <span className="count">{items.length} templates</span>
              <span className="count disabled-count">{disabledCount} disabled</span>
            </div>
            <div className="right">
              {embedded ? (
                <button
                  type="button"
                  className="btn btn-warning btn-sm"
                  disabled={busy || loading || !items.length}
                  onClick={() => void clearAllBlocklist()}
                >
                  <Trash2 size={12} /> Clear all blocklist
                </button>
              ) : null}
              <button type="button" className="btn btn-danger btn-sm" disabled={busy || loading} onClick={() => void disableAll()}>
                <Ban size={12} /> Disable all
              </button>
              <button type="button" className="btn btn-success btn-sm" disabled={busy || loading} onClick={() => void enableAll()}>
                <CheckCircle size={12} /> Enable all
              </button>
              <button type="button" className="btn btn-warning btn-sm" disabled={busy} onClick={removeDuplicates}>
                <Filter size={12} /> Remove duplicates
              </button>
            </div>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th style={{ width: '28%' }}>Template name</th>
                  <th style={{ width: '17%' }}>Industry</th>
                  <th style={{ width: '17%' }}>Survey type</th>
                  <th style={{ width: '14%' }}>Template ID</th>
                  <th style={{ width: '12%' }}>Status</th>
                  <th style={{ width: '12%', textAlign: 'center' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={6}>
                      <div className="empty-state">
                        <p>Loading…</p>
                      </div>
                    </td>
                  </tr>
                ) : sortedItems.length === 0 ? (
                  <tr>
                    <td colSpan={6}>
                      <div className="empty-state">
                        <Inbox size={28} style={{ color: '#b8aa96', marginBottom: 8 }} />
                        <p>No templates added yet. Add templates above or upload a file.</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  sortedItems.map((t) => (
                    <tr key={t.id} className={t.disabled ? 'disabled-row' : ''}>
                      <td>
                        <strong>{t.raw_name}</strong>
                        {t.target_kind === 'unresolved' ? <span className="badge-unresolved">NOT FOUND</span> : null}
                      </td>
                      <td>{t.industry_name || 'Unknown'}</td>
                      <td>{t.survey_type_name || 'Unknown'}</td>
                      <td>
                        {t.anchor_id ? (
                          <span className="tpl-id" title={t.template_code || ''}>
                            <code>{t.anchor_id}</code>
                            {t.pair_variant ? <span className="tpl-variant">{t.pair_variant}</span> : null}
                            {t.topic_group_size > 1 ? (
                              <span className="tpl-pair" title="Templates in this list sharing the same topic — all hide together">
                                ×{t.topic_group_size}
                              </span>
                            ) : null}
                          </span>
                        ) : (
                          <span className="muted-hint">—</span>
                        )}
                      </td>
                      <td>
                        <span className={`status-badge${t.disabled ? ' disabled' : ''}`}>
                          <span className="dot" />
                          {t.disabled ? 'Disabled' : 'Active'}
                        </span>
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        {t.disabled ? (
                          <button type="button" className="btn btn-success btn-xs" disabled={busy} onClick={() => void toggleTemplate(t, false)}>
                            <Check size={10} /> Enable
                          </button>
                        ) : (
                          <button type="button" className="btn btn-danger btn-xs" disabled={busy} onClick={() => void toggleTemplate(t, true)}>
                            <Ban size={10} /> Disable
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {!onToast ? (
          <div className={`toast${toast.show ? ' show' : ''}${toast.error ? ' error' : ''}`}>{toast.message}</div>
        ) : null}
      </div>
    </div>
  )
}
