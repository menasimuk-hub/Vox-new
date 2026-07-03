import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Pencil } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import '../../styles/admin-industries.css'
import { Panel } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Pill } from '@/components/ui/Badge'
import { Switch } from '@/components/ui/Switch'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'

const DEFAULT_BUTTONS = [
  { id: 'great', label: 'Great' },
  { id: 'ok', label: 'OK' },
  { id: 'poor', label: 'Poor' },
]

const STEP_ROLE_OPTIONS = ['rating', 'yes_no', 'open_text', 'choice', 'nps']

const WA_FOOTER = 'Reply STOP to opt out'

function statusBadge(status) {
  const s = String(status || 'draft').toLowerCase()
  if (['approved', 'synced', 'live'].includes(s)) {
    return <Pill tone="success">Approved</Pill>
  }
  if (s === 'submitted' || s === 'pending') {
    return <Pill tone="warning">Pending</Pill>
  }
  return <Pill tone="neutral">Draft</Pill>
}

function buttonLabel(b) {
  if (!b) return ''
  if (typeof b === 'string') return b
  return b.label || b.text || b.title || ''
}

function detectVariables(body) {
  const matches = String(body || '').match(/\{\{\s*\d+\s*\}\}/g)
  if (!matches) return []
  return Array.from(new Set(matches))
}

export default function FeedbackSurveyTypeEdit() {
  const { typeId } = useParams()
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [item, setItem] = useState(null)
  const [editing, setEditing] = useState(null)

  const load = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const data = await apiFetch(`/admin/customer-feedback/survey-types/${typeId}`)
      setItem(data?.item || null)
    } catch (e) {
      setError(e?.message || 'Could not load survey type')
    } finally {
      setLoading(false)
    }
  }, [typeId])

  useEffect(() => {
    load()
  }, [load])

  const saveSurveyType = async () => {
    if (!item) return
    setBusy('save-type')
    setError('')
    try {
      await apiFetch('/admin/customer-feedback/survey-types', {
        method: 'POST',
        body: JSON.stringify({
          id: item.id,
          industry_id: item.industry_id,
          name: item.name,
          slug: item.slug,
          description: item.description,
          sort_order: item.sort_order,
          is_active: item.is_active,
        }),
      })
      setMsg('Survey type saved.')
      await load()
    } catch (e) {
      setError(e?.message || 'Could not save survey type')
    } finally {
      setBusy('')
    }
  }

  const syncTelnyx = async () => {
    setBusy('sync')
    setError('')
    try {
      const data = await apiFetch(`/admin/customer-feedback/survey-types/${typeId}/sync-telnyx`, { method: 'POST' })
      setMsg(`Submitted ${data?.submitted || 0} template(s) to Telnyx.`)
      await load()
    } catch (e) {
      setError(e?.message || 'Sync failed')
    } finally {
      setBusy('')
    }
  }

  const openTemplate = (tpl) => {
    const rawButtons = Array.isArray(tpl.buttons) && tpl.buttons.length ? tpl.buttons : DEFAULT_BUTTONS
    setEditing({
      ...tpl,
      buttons: rawButtons.map((b) => buttonLabel(b)),
    })
    setMsg('')
    setError('')
  }

  const setEditField = (key, value) => setEditing((f) => ({ ...f, [key]: value }))

  const setButton = (idx, value) => {
    setEditing((f) => {
      const buttons = [...(f.buttons || ['', '', ''])]
      buttons[idx] = value
      return { ...f, buttons }
    })
  }

  const saveTemplate = async () => {
    if (!editing) return
    setBusy(`tpl-${editing.id || 'new'}`)
    setError('')
    try {
      const buttons = (editing.buttons || [])
        .map((label) => String(label || '').trim())
        .filter(Boolean)
        .map((label) => ({ id: label.toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 24) || 'btn', label }))
      await apiFetch('/admin/customer-feedback/wa-templates', {
        method: 'POST',
        body: JSON.stringify({
          id: editing.id,
          industry_id: item.industry_id,
          survey_type_id: item.id,
          step_order: editing.step_order,
          template_key: editing.template_key,
          body_text: editing.body_text,
          step_role: editing.step_role,
          language: editing.language,
          meta_category: editing.meta_category,
          buttons,
          is_active: editing.is_active,
        }),
      })
      setMsg('Template saved.')
      setEditing(null)
      await load()
    } catch (e) {
      setError(e?.message || 'Could not save template')
    } finally {
      setBusy('')
    }
  }

  const createTemplate = async () => {
    setBusy('create')
    setError('')
    try {
      const nextOrder = (item?.templates?.length || 0) + 1
      const data = await apiFetch('/admin/customer-feedback/wa-templates', {
        method: 'POST',
        body: JSON.stringify({
          industry_id: item.industry_id,
          survey_type_id: item.id,
          step_order: nextOrder,
          template_key: 'rating',
          step_role: 'rating',
          body_text: `How was your experience with ${item.name}?`,
          language: 'en_GB',
          meta_category: 'utility',
          buttons: DEFAULT_BUTTONS,
          is_active: true,
        }),
      })
      await load()
      openTemplate(data?.item || {})
    } catch (e) {
      setError(e?.message || 'Could not create template')
    } finally {
      setBusy('')
    }
  }

  const visibleTemplates = useMemo(
    () =>
      (item?.templates || []).filter(
        (tpl) =>
          String(tpl.meta_category || '').toLowerCase() !== 'marketing' &&
          String(tpl.template_key || '').toLowerCase() !== 'marketing_opt_in',
      ),
    [item],
  )

  if (loading) {
    return (
      <div className="ds-scope">
        <Panel>
          <div className="text-[12px] text-muted-foreground">Loading…</div>
        </Panel>
      </div>
    )
  }

  if (!item) {
    return (
      <div className="ds-scope">
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error || 'Survey type not found'}
        </div>
      </div>
    )
  }

  // ── Template editor (two-column with live WhatsApp preview) — bespoke phone mockup, kept as-is ──
  if (editing) {
    const previewButtons = (editing.buttons || []).map((b) => String(b || '').trim()).filter(Boolean)
    const variables = detectVariables(editing.body_text)
    const bodyLen = String(editing.body_text || '').length
    const isApproved = ['approved', 'synced', 'live'].includes(String(editing.telnyx_sync_status || '').toLowerCase())
    const stepRoleOptions = editing.step_role && !STEP_ROLE_OPTIONS.includes(editing.step_role)
      ? [editing.step_role, ...STEP_ROLE_OPTIONS]
      : STEP_ROLE_OPTIONS
    return (
      <div className="pageWrap indHub">
        <button type="button" className="ind-breadcrumb" onClick={() => setEditing(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
          ← <span>{item.name}</span>
        </button>

        {error ? <div className="alert error">{error}</div> : null}

        <div className="editor-page">
          <div className="editor-left">
            <div className="editor-topbar">
              <div className="left">
                <div className="editor-title">{editing.template_key || 'Template'} — Question</div>
                <span className="btn-utility">{String(editing.meta_category || 'utility').toUpperCase()}</span>
              </div>
              <div className="right">
                <button type="button" className="btn btn-save bsm" disabled={Boolean(busy)} onClick={saveTemplate}>
                  ● {busy.startsWith('tpl-') ? 'Saving…' : 'Save'}
                </button>
                <button type="button" className="btn btn-close bsm" onClick={() => setEditing(null)}>✕ Close</button>
              </div>
            </div>

            <div className={`meta-bar${isApproved ? ' ok' : ''}`}>
              {isApproved
                ? 'This template is approved on Meta. Editing the body will require re-approval.'
                : 'Meta reviews this template. Push to Meta checks for approval updates — it does not send content changes.'}
            </div>

            <div className="editor-fields">
              <div className="fields-row">
                <div className="field-block">
                  <div className="field-block-head">
                    <div className="left"><div className="step-num">1</div><span className="field-label">Survey step role</span></div>
                  </div>
                  <div className="field-block-body">
                    <div className="sel">
                      <select value={editing.step_role || ''} onChange={(e) => setEditField('step_role', e.target.value)}>
                        {stepRoleOptions.map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    </div>
                    <div className="hint">Live modal steps: rating, yes/no, open text…</div>
                  </div>
                </div>

                <div className="field-block">
                  <div className="field-block-head">
                    <div className="left"><div className="step-num">2</div><span className="field-label">Category</span></div>
                    <span className="field-note">Required</span>
                  </div>
                  <div className="field-block-body">
                    <div className="sel">
                      <select value={editing.meta_category || 'utility'} onChange={(e) => setEditField('meta_category', e.target.value)}>
                        <option value="utility">Utility</option>
                      </select>
                    </div>
                  </div>
                </div>

                <div className="field-block">
                  <div className="field-block-head">
                    <div className="left"><div className="step-num">3</div><span className="field-label">Template language</span></div>
                    <span className="field-note">Meta locale</span>
                  </div>
                  <div className="field-block-body">
                    <input type="text" value={editing.language || 'en_GB'} onChange={(e) => setEditField('language', e.target.value)} />
                    <div className="hint">UK accounts need en_GB.</div>
                  </div>
                </div>

                <div className="field-block">
                  <div className="field-block-head">
                    <div className="left"><div className="step-num">4</div><span className="field-label">Step order</span></div>
                  </div>
                  <div className="field-block-body">
                    <input type="text" inputMode="numeric" value={editing.step_order ?? 1} onChange={(e) => setEditField('step_order', Number(e.target.value) || 1)} />
                  </div>
                </div>
              </div>

              <div className="fields-row-2">
                <div className="field-block">
                  <div className="field-block-head">
                    <div className="left"><div className="step-num">5</div><span className="field-label">Template key</span></div>
                    <span className="field-note">Internal id</span>
                  </div>
                  <div className="field-block-body">
                    <input type="text" value={editing.template_key || ''} onChange={(e) => setEditField('template_key', e.target.value)} />
                  </div>
                </div>

                <div className="field-block">
                  <div className="field-block-head">
                    <div className="left"><div className="step-num">6</div><span className="field-label">Body</span></div>
                    <span className="field-note">Required · max 1024</span>
                  </div>
                  <div className="field-block-body">
                    <textarea value={editing.body_text || ''} onChange={(e) => setEditField('body_text', e.target.value)} />
                    <div className="char-count">{bodyLen}/1024</div>
                  </div>
                </div>
              </div>

              <div className="fields-row-2">
                <div className="field-block">
                  <div className="field-block-head">
                    <div className="left"><div className="step-num">7</div><span className="field-label">Footer</span></div>
                    <span className="field-note">Compliance · fixed</span>
                  </div>
                  <div className="field-block-body">
                    <input type="text" value={WA_FOOTER} readOnly />
                    <div className="hint">Opt-out footer is enforced by Telnyx.</div>
                  </div>
                </div>

                <div className="field-block">
                  <div className="field-block-head">
                    <div className="left"><div className="step-num">8</div><span className="field-label">Variables</span></div>
                    <span className="field-note">Auto-detected</span>
                  </div>
                  <div className="field-block-body">
                    {variables.length
                      ? <div className="hint">{variables.join('  ')}</div>
                      : <div className="empty-note">No variables in this template body.</div>}
                  </div>
                </div>
              </div>

              <div className="field-block">
                <div className="field-block-head">
                  <div className="left"><div className="step-num">9</div><span className="field-label">Buttons</span></div>
                  <span className="field-note">Quick reply · max 10 chars each</span>
                </div>
                <div className="field-block-body">
                  <div className="btn-list">
                    {[0, 1, 2].map((i) => (
                      <div className="btn-list-item" key={i}>
                        <div className="idx">{i + 1}</div>
                        <input
                          type="text"
                          maxLength={20}
                          value={(editing.buttons && editing.buttons[i]) || ''}
                          placeholder={i === 0 ? 'e.g. Excellent' : i === 1 ? 'e.g. Good' : 'e.g. Poor'}
                          onChange={(e) => setButton(i, e.target.value)}
                          style={{ maxWidth: 200 }}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12, color: '#555' }}>
                <span className="ind-toggle">
                  <input type="checkbox" checked={Boolean(editing.is_active)} onChange={(e) => setEditField('is_active', e.target.checked)} />
                  <span className="ind-toggle-track" aria-hidden />
                </span>
                {editing.is_active ? 'Active' : 'Inactive'}
              </label>
            </div>
          </div>

          {/* RIGHT: live WhatsApp preview */}
          <div className="editor-right">
            <div className="preview-topbar">
              <div className="avatar">VB</div>
              <div className="info">
                <div className="name">VoxBulk Surveys</div>
                <div className="sub">{item.industry_name || 'WhatsApp'}</div>
              </div>
              <div className="dots">⋮</div>
            </div>

            <div className="preview-chat">
              <div className="preview-label">Preview · WhatsApp</div>
              <div>
                <div className="wa-bubble">
                  <div className="wa-body">{editing.body_text || 'Your message will appear here…'}</div>
                  <div className="wa-footer">{WA_FOOTER}</div>
                  <div className="wa-time">12:34 ✓✓</div>
                </div>
                {previewButtons.length ? (
                  <div className="wa-btn-wrap">
                    {previewButtons.map((b, i) => <div className="wa-btn" key={i}>{b}</div>)}
                  </div>
                ) : null}
              </div>
            </div>

            <div className="preview-input-bar">
              <input placeholder="Reply…" disabled />
              <div className="send-btn">
                <svg viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2z" /></svg>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ── Survey type details + templates list ──
  return (
    <div className="ds-scope space-y-4">
      <div className="flex flex-wrap items-center gap-1.5 text-[12px] text-muted-foreground">
        <Link to="/customer-feedback/industries" className="hover:text-foreground">Industries</Link>
        <span>/</span>
        <Link to={`/customer-feedback/industries/${item.industry_id}`} className="hover:text-foreground">
          {item.industry_name || 'Industry'}
        </Link>
        <span>/</span>
        <span className="text-foreground">{item.name}</span>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>
      ) : null}
      {msg ? (
        <div className="rounded-md border border-success/40 bg-success-soft px-3 py-2 text-sm text-success">{msg}</div>
      ) : null}

      <Panel
        title="Survey type details"
        action={
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" className="h-8" disabled={Boolean(busy)} onClick={syncTelnyx}>
              {busy === 'sync' ? 'Pushing…' : 'Push to Meta'}
            </Button>
            <Button type="button" size="sm" className="h-8" disabled={busy === 'save-type'} onClick={saveSurveyType}>
              {busy === 'save-type' ? 'Saving…' : 'Save changes'}
            </Button>
          </div>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label className="text-[12px]">Name</Label>
            <Input className="h-8" value={item.name || ''} onChange={(e) => setItem((f) => ({ ...f, name: e.target.value }))} />
          </div>
          <div className="space-y-1">
            <Label className="text-[12px]">Slug</Label>
            <Input className="h-8" value={item.slug || ''} onChange={(e) => setItem((f) => ({ ...f, slug: e.target.value }))} />
          </div>
          <div className="space-y-1">
            <Label className="text-[12px]">Sort order</Label>
            <Input className="h-8" type="number" value={item.sort_order ?? 100} onChange={(e) => setItem((f) => ({ ...f, sort_order: Number(e.target.value) }))} />
          </div>
          <div className="space-y-1">
            <Label className="text-[12px]">Description</Label>
            <Input className="h-8" value={item.description || ''} onChange={(e) => setItem((f) => ({ ...f, description: e.target.value }))} placeholder="Optional…" />
          </div>
          <div className="flex items-center gap-2 text-[12px]">
            <Switch checked={Boolean(item.is_active)} onCheckedChange={(v) => setItem((f) => ({ ...f, is_active: v }))} />
            <span className="text-muted-foreground">{item.is_active ? 'Active' : 'Inactive'}</span>
          </div>
        </div>
      </Panel>

      <Panel
        title="WhatsApp templates"
        action={
          <Button type="button" size="sm" className="h-8" disabled={Boolean(busy)} onClick={createTemplate}>
            {busy === 'create' ? 'Adding…' : '+ Add English template'}
          </Button>
        }
      >
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Key</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Language</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Telnyx</TableHead>
              <TableHead>Active</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visibleTemplates.map((tpl) => (
              <TableRow key={tpl.id}>
                <TableCell><strong className="font-medium">{tpl.template_key}</strong></TableCell>
                <TableCell>{tpl.step_role || '—'}</TableCell>
                <TableCell><code className="text-[11px]">{tpl.language}</code></TableCell>
                <TableCell>{tpl.meta_category}</TableCell>
                <TableCell>{statusBadge(tpl.telnyx_sync_status)}</TableCell>
                <TableCell>{tpl.is_active ? 'Yes' : 'No'}</TableCell>
                <TableCell className="text-right">
                  <Button type="button" variant="ghost" size="sm" className="h-7 w-7 px-0" title="Edit" onClick={() => openTemplate(tpl)}>
                    <Pencil size={14} />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {!visibleTemplates.length ? (
              <TableEmpty colSpan={7}>No templates yet. Import from MD on Industries or add one here.</TableEmpty>
            ) : null}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
