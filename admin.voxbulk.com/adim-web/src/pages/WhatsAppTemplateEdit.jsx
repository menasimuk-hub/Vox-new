import React, { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { TemplateDbKeyField } from '../components/TemplateDbKeyField'
import { slugifyTemplateKey } from '../lib/messagingConstants'

const EMPTY = { template_key: '', name: '', body: '', is_enabled: true }

export default function WhatsAppTemplateEdit() {
  const { templateKey } = useParams()
  const navigate = useNavigate()
  const isNew = !templateKey || templateKey === 'new'

  const [loading, setLoading] = useState(!isNew)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState('')
  const [draft, setDraft] = useState(EMPTY)

  const load = useCallback(async () => {
    if (isNew) return
    setLoading(true)
    setError('')
    try {
      const row = await apiFetch(`/admin/messaging/whatsapp/templates/${encodeURIComponent(templateKey)}`)
      setDraft({
        template_key: row.template_key,
        name: row.name || '',
        body: row.body || '',
        is_enabled: row.is_enabled !== false,
      })
    } catch (e) {
      setError(e?.message || 'Could not load template')
    } finally {
      setLoading(false)
    }
  }, [isNew, templateKey])

  useEffect(() => {
    load()
  }, [load])

  const save = async () => {
    setSaving(true)
    setError('')
    setFeedback('')
    try {
      const payload = {
        name: draft.name.trim(),
        body: draft.body,
        is_enabled: draft.is_enabled,
      }
      if (isNew) {
        const key = slugifyTemplateKey(draft.template_key || draft.name)
        if (!key) throw new Error('Template key is required')
        const created = await apiFetch('/admin/messaging/whatsapp/templates', {
          method: 'POST',
          body: JSON.stringify({ ...payload, template_key: key }),
        })
        navigate(`/settings/email/whatsapp/${encodeURIComponent(created.template_key)}/edit`, { replace: true })
        return
      }
      await apiFetch(`/admin/messaging/whatsapp/templates/${encodeURIComponent(templateKey)}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
      setFeedback('Template saved.')
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="pageTop">
        <div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            <Link to="/settings/email?tab=whatsapp" style={{ color: 'var(--grn)' }}>
              ← Back to WhatsApp templates
            </Link>
          </div>
          <h1>{isNew ? 'Create WhatsApp template' : `Edit · ${draft.name || templateKey}`}</h1>
          <p>Template key is stored in the database and used when sending via Telnyx.</p>
        </div>
      </div>

      <div className="pageShell emailPageShell">
        {error ? <div className="note" style={{ borderColor: 'rgba(255,0,0,0.35)', marginBottom: 14 }}>{error}</div> : null}
        {loading ? (
          <div className="note">Loading…</div>
        ) : (
          <div className="card msgTemplateEditor">
            <div className="cardHead">
              <h3>WhatsApp message editor</h3>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={Boolean(draft.is_enabled)}
                  onChange={(e) => setDraft((d) => ({ ...d, is_enabled: e.target.checked }))}
                />
                <span className="muted" style={{ fontSize: 12 }}>
                  Enabled
                </span>
              </label>
            </div>
            <div className="cardBody">
              {isNew ? (
                <>
                  <div className="msgFieldBlock">
                    <label className="label">Template name</label>
                    <input
                      className="input"
                      value={draft.name}
                      onChange={(e) =>
                        setDraft((d) => ({
                          ...d,
                          name: e.target.value,
                          template_key: d.template_key || slugifyTemplateKey(e.target.value),
                        }))
                      }
                      placeholder="Promo message"
                    />
                  </div>
                  <TemplateDbKeyField
                    isNew
                    value={draft.template_key}
                    onChange={(e) => setDraft((d) => ({ ...d, template_key: slugifyTemplateKey(e.target.value) }))}
                  />
                </>
              ) : (
                <>
                  <TemplateDbKeyField readOnly value={draft.template_key} />
                  <div className="mini" style={{ marginBottom: 16 }}>
                    <label>Template name</label>
                    <strong>{draft.name}</strong>
                  </div>
                </>
              )}

              <div className="emailEditorSplit">
                <div className="msgFieldBlock msgFieldBlockTight">
                  <label className="label">Message content</label>
                  <textarea
                    className="input msgFieldEditorBox"
                    value={draft.body}
                    onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))}
                    placeholder="Hello {{first_name}}! Special offer for you."
                  />
                  <p className="fieldHint">
                    Plain text only — WhatsApp does not render HTML. Use {'{{first_name}}'}, {'{{clinic_name}}'} (business name), {'{{organisation_name}}'}, line breaks, and emoji.
                  </p>
                </div>

                <div className="msgFieldBlock msgFieldBlockTight waPreviewCol">
                  <label className="label">
                    <i className="ti ti-device-mobile" style={{ marginRight: 6 }} />
                    Mobile preview
                  </label>
                  <div className="waPreviewPane">
                    <div className="waPhonePortrait" aria-hidden="true">
                      <div className="waPhoneBezel">
                        <div className="waPhoneNotch" />
                        <div className="waPhoneScreen">
                          <div className="waPhoneStatusBar">
                            <span>9:41</span>
                            <span className="waPhoneStatusIcons">
                              <i className="ti ti-wifi" />
                              <i className="ti ti-battery-4" />
                            </span>
                          </div>
                          <div className="waPhoneChatHeader">
                            <span className="waPhoneBack">‹</span>
                            <span className="waPhoneAvatar">B</span>
                            <div className="waPhoneContact">
                              <strong>Your business</strong>
                              <span>online</span>
                            </div>
                          </div>
                          <div className="waPhoneChatBody">
                            <div className="waBubbleOutbound">
                              {draft.body || 'Preview message'}
                              <span className="waBubbleMeta">12:34</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="actions" style={{ marginTop: 20 }}>
                <button type="button" className="btn primary" onClick={save} disabled={saving}>
                  <i className="ti ti-device-floppy" />
                  {saving ? 'Saving…' : isNew ? 'Create template' : 'Save template'}
                </button>
                {feedback ? <span className="muted" style={{ fontSize: 12 }}>{feedback}</span> : null}
              </div>
              <div className="note" style={{ marginTop: 14, marginBottom: 0 }}>
                Outbound sends use Telnyx as <strong>plain text</strong> (not HTML). Reference template by key:{' '}
                <code>{draft.template_key || '(set on save)'}</code>
                — placeholders are replaced before send.
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
