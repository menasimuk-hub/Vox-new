import React, { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { TemplateDbKeyField, TemplateMetaGrid } from '../components/TemplateDbKeyField'
import {
  COMMON_PLACEHOLDERS,
  DEFAULT_NEW_EMAIL_HTML,
  DEMO_HTML_BY_KEY,
  SYSTEM_EMAIL_META,
  TEST_VARS_BY_KEY,
  emailDisplayDescription,
  emailDisplayTitle,
  mergeSystemEmailDraft,
  slugifyTemplateKey,
  smtpTestResultMessage,
} from '../lib/messagingConstants'

const EMPTY_NEW = {
  template_key: '',
  title: '',
  subject: '',
  body: DEFAULT_NEW_EMAIL_HTML,
  is_enabled: true,
}

export default function EmailTemplateEdit() {
  const { templateKey } = useParams()
  const navigate = useNavigate()
  const isNew = !templateKey || templateKey === 'new'

  const [loading, setLoading] = useState(!isNew)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState('')
  const [testBusy, setTestBusy] = useState(false)
  const [testMsg, setTestMsg] = useState('')
  const [testTo, setTestTo] = useState('')
  const [draft, setDraft] = useState(isNew ? EMPTY_NEW : { template_key: '', title: '', subject: '', body: '', is_enabled: true })
  const [isSystem, setIsSystem] = useState(false)

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem('retover_admin_test_email_to') || ''
      if (stored.trim()) setTestTo(stored.trim())
    } catch {
      /* ignore */
    }
  }, [])

  const load = useCallback(async () => {
    if (isNew) {
      setDraft(EMPTY_NEW)
      return
    }
    setError('')
    setLoading(true)
    try {
      const row = await apiFetch(`/admin/email/templates/${encodeURIComponent(templateKey)}`)
      setDraft(
        row.is_system
          ? mergeSystemEmailDraft(row)
          : {
              template_key: row.template_key,
              title: row.title || '',
              subject: row.subject || '',
              body: row.body || '',
              is_enabled: row.is_enabled !== false,
            },
      )
      setIsSystem(Boolean(row.is_system))
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
        title: draft.title.trim() || SYSTEM_EMAIL_META[draft.template_key]?.title || draft.template_key,
        subject: draft.subject,
        body: draft.body,
        is_enabled: draft.is_enabled,
      }
      if (isNew) {
        const key = slugifyTemplateKey(draft.template_key || draft.title)
        if (!key) throw new Error('Template key is required')
        const created = await apiFetch('/admin/email/templates', {
          method: 'POST',
          body: JSON.stringify({ ...payload, template_key: key }),
        })
        navigate(`/settings/email/templates/${encodeURIComponent(created.template_key)}/edit`, { replace: true })
        return
      }
      await apiFetch(`/admin/email/templates/${encodeURIComponent(templateKey)}`, {
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

  const sendTest = async () => {
    const to = testTo.trim()
    if (!to) {
      setTestMsg('Enter a test recipient email.')
      return
    }
    if (isNew) {
      setTestMsg('Save the template first.')
      return
    }
    if (templateKey === 'forgot_password') {
      setTestMsg('Use the public forgot-password flow for this template.')
      return
    }
    setTestBusy(true)
    setTestMsg('')
    try {
      window.localStorage.setItem('retover_admin_test_email_to', to)
      const res = await apiFetch('/admin/email/notify/send-templated', {
        method: 'POST',
        body: JSON.stringify({
          template_key: templateKey,
          to,
          variables: TEST_VARS_BY_KEY[templateKey] || {},
        }),
      })
      setTestMsg(smtpTestResultMessage(res))
    } catch (e) {
      setTestMsg(e?.message || 'Send failed')
    } finally {
      setTestBusy(false)
    }
  }

  const loadDemo = () => {
    const demo = DEMO_HTML_BY_KEY[draft.template_key || templateKey]
    if (demo) setDraft((d) => ({ ...d, body: demo }))
  }

  const heading = isNew ? 'Create email template' : `Edit · ${emailDisplayTitle(draft)}`

  return (
    <>
      <div className="pageTop">
        <div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            <Link to="/settings/email?tab=email" style={{ color: 'var(--grn)' }}>
              ← Back to email templates
            </Link>
          </div>
          <h1>{heading}</h1>
          <p>{isNew ? 'Create a template — key is stored in the database for outbound sends.' : emailDisplayDescription(draft)}</p>
        </div>
      </div>

      <div className="pageShell emailPageShell">
        {error ? <div className="note" style={{ borderColor: 'rgba(255,0,0,0.35)', marginBottom: 14 }}>{error}</div> : null}
        {loading ? (
          <div className="note">Loading…</div>
        ) : (
          <div className="card emailTemplateEditCard msgTemplateEditor">
            <div className="cardHead">
              <h3>{isNew ? 'New email template' : 'Email template editor'}</h3>
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
                <TemplateMetaGrid>
                  <div className="msgFieldBlock" style={{ marginBottom: 0 }}>
                    <label className="label">Template name</label>
                    <input
                      className="input"
                      value={draft.title}
                      onChange={(e) =>
                        setDraft((d) => ({
                          ...d,
                          title: e.target.value,
                          template_key: d.template_key || slugifyTemplateKey(e.target.value),
                        }))
                      }
                      placeholder="e.g. Welcome email"
                    />
                  </div>
                  <div className="msgFieldBlock" style={{ marginBottom: 0, gridColumn: 'span 2' }}>
                    <TemplateDbKeyField
                      isNew
                      value={draft.template_key}
                      onChange={(e) => setDraft((d) => ({ ...d, template_key: slugifyTemplateKey(e.target.value) }))}
                    />
                  </div>
                </TemplateMetaGrid>
              ) : (
                <>
                  <TemplateDbKeyField readOnly value={draft.template_key} />
                  <TemplateMetaGrid className="span2col">
                    <div className="mini">
                      <label>Display name</label>
                      <strong>{emailDisplayTitle(draft)}</strong>
                    </div>
                    <div className="mini">
                      <label>Type</label>
                      <strong>{isSystem ? 'System (built-in)' : 'Custom'}</strong>
                    </div>
                  </TemplateMetaGrid>
                  {!isSystem ? (
                    <div className="msgFieldBlock">
                      <label className="label">Display name</label>
                      <input
                        className="input"
                        value={draft.title}
                        onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
                      />
                    </div>
                  ) : null}
                </>
              )}

              <div className="emailEditorSplit">
                <div className="emailEditorFields">
                  <label className="label">Subject line</label>
                  <textarea
                    className="input msgFieldSubjectBox"
                    value={draft.subject}
                    onChange={(e) => setDraft((d) => ({ ...d, subject: e.target.value }))}
                    placeholder="Email subject — supports {{placeholders}}"
                  />
                  <label className="label emailBodyLabel">HTML body</label>
                  <textarea
                    className="input msgFieldBodyBox"
                    value={draft.body}
                    onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))}
                    placeholder="<p>Your HTML… use {{placeholders}}</p>"
                  />
                  <p className="fieldHint">Placeholders: {COMMON_PLACEHOLDERS.join(' · ')}</p>
                </div>

                <div className="msgFieldBlock msgFieldBlockTight emailEditorPreviewCol">
                  <label className="label">
                    <i className="ti ti-eye" style={{ marginRight: 6 }} />
                    Live preview
                  </label>
                  <div className="emailPreviewBox emailPreviewBoxTall">
                    {draft.body ? (
                      <div className="emailPreviewInner" dangerouslySetInnerHTML={{ __html: draft.body }} />
                    ) : (
                      <p className="muted" style={{ margin: 0 }}>
                        HTML preview appears here.
                      </p>
                    )}
                  </div>
                </div>
              </div>

              <div className="actions" style={{ flexWrap: 'wrap', marginTop: 20 }}>
                <button type="button" className="btn primary" onClick={save} disabled={saving}>
                  <i className="ti ti-device-floppy" />
                  {saving ? 'Saving…' : isNew ? 'Create template' : 'Save template'}
                </button>
                {!isNew && isSystem && templateKey !== 'forgot_password' ? (
                  <button type="button" className="btn soft" onClick={sendTest} disabled={testBusy}>
                    <i className="ti ti-send" />
                    {testBusy ? 'Sending…' : 'Send test email'}
                  </button>
                ) : null}
                {DEMO_HTML_BY_KEY[draft.template_key || templateKey] ? (
                  <button type="button" className="btn soft" onClick={loadDemo}>
                    <i className="ti ti-code" />
                    Restore default HTML
                  </button>
                ) : null}
                {feedback ? <span className="muted" style={{ fontSize: 12, alignSelf: 'center' }}>{feedback}</span> : null}
              </div>

              {!isNew && isSystem ? (
                <div className="msgFieldBlock" style={{ marginTop: 16, maxWidth: 420 }}>
                  <label className="label">Test recipient</label>
                  <input
                    className="input"
                    type="email"
                    value={testTo}
                    onChange={(e) => setTestTo(e.target.value)}
                    placeholder="you@example.com"
                  />
                </div>
              ) : null}
              {testMsg ? <div className="note" style={{ marginTop: 12, marginBottom: 0 }}>{testMsg}</div> : null}
            </div>
          </div>
        )}
      </div>
    </>
  )
}
