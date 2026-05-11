import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'

const TEMPLATE_META = [
  { key: 'new_user', title: 'New user', description: 'Welcome / account created' },
  { key: 'forgot_password', title: 'Forgot password', description: 'Password recovery message' },
  { key: 'new_invoice', title: 'New invoice', description: 'Invoice available' },
  { key: 'payment_failed', title: 'Cancel / failed payment', description: 'Payment could not be processed' },
  { key: 'general_notification', title: 'General activity', description: 'Notifications and activity' },
]

/** Copy/paste HTML demos — placeholders use double curly braces: {{name}} */
const DEMO_HTML_BY_KEY = {
  new_user: `<!DOCTYPE html><html><body style="font-family:system-ui,sans-serif;max-width:560px;margin:24px auto;color:#0f172a;">
  <p>Hi <strong>{{user_email}}</strong>,</p>
  <p>Welcome to VOXBULK — your account is ready.</p>
  <p style="color:#64748b;font-size:13px;">This email uses HTML. Replace placeholders like <code>{{user_email}}</code>.</p>
</body></html>`,
  forgot_password: `<p>Hello,</p><p>We received a password reset for <strong>{{user_email}}</strong>.</p><p>If this was not you, ignore this email.</p>`,
  new_invoice: `<p>Hello,</p><p>New invoice <strong>#{{invoice_id}}</strong> — amount <strong>{{amount_gbp_pence}}</strong> pence ({{currency}}), status {{invoice_status}}.</p>`,
  payment_failed: `<p>Payment issue for <strong>{{user_email}}</strong>.</p><p>Amount due: <strong>{{amount}}</strong> · Invoice <strong>{{invoice_number}}</strong>.</p>`,
  general_notification: `<p>Hello {{user_name}},</p><p>{{message}}</p><p style="font-size:12px;color:#64748b;">Sent by VOXBULK notifications.</p>`,
}

const COMMON_PLACEHOLDERS = [
  '{{user_email}}',
  '{{amount}}',
  '{{invoice_number}}',
  '{{invoice_id}}',
  '{{amount_gbp_pence}}',
  '{{currency}}',
  '{{invoice_status}}',
  '{{user_name}}',
  '{{message}}',
]

function secureModeFromFlags(useTls, useSsl) {
  if (useSsl) return 'ssl'
  if (useTls) return 'starttls'
  return 'none'
}

function flagsFromSecureMode(mode) {
  if (mode === 'ssl') return { use_tls: false, use_ssl: true }
  if (mode === 'starttls') return { use_tls: true, use_ssl: false }
  return { use_tls: false, use_ssl: false }
}

/** Normalise SMTP test-send JSON (success uses `detail`; some paths use `message`) */
function smtpTestResultMessage(payload) {
  if (payload != null && typeof payload === 'object') {
    if (typeof payload.message === 'string' && payload.message.trim()) return payload.message.trim()
    if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail.trim()
    if (Array.isArray(payload.detail))
      return payload.detail.map((x) => (x && typeof x === 'object' && x.msg ? x.msg : JSON.stringify(x))).join('; ')
  }
  return 'Test email sent.'
}

function smtpStatusPill(cfg) {
  if (!cfg) return { cls: 'p-amber', text: 'Loading' }
  if (!cfg.is_enabled) return { cls: 'p-amber', text: 'Disabled' }
  if (cfg.configured) return { cls: 'p-green', text: 'Ready' }
  return { cls: 'p-amber', text: 'Incomplete' }
}

export default function EmailSettings() {
  const [loadError, setLoadError] = useState('')
  const [saveError, setSaveError] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [smtp, setSmtp] = useState(null)
  const [passwordDraft, setPasswordDraft] = useState('')

  const [secureMode, setSecureMode] = useState('starttls')
  const [testTo, setTestTo] = useState('')
  const [testBusy, setTestBusy] = useState(false)
  const [testMsg, setTestMsg] = useState('')

  const [templatesByKey, setTemplatesByKey] = useState({})
  const [templatesLoading, setTemplatesLoading] = useState(true)
  const [templatesError, setTemplatesError] = useState('')
  const [templateSaving, setTemplateSaving] = useState('')

  const loadSmtp = useCallback(async () => {
    setLoadError('')
    const data = await apiFetch('/admin/email/smtp')
    setSmtp(data)
    setSecureMode(secureModeFromFlags(Boolean(data?.use_tls), Boolean(data?.use_ssl)))
  }, [])

  const loadTemplates = useCallback(async () => {
    setTemplatesError('')
    const rows = await apiFetch('/admin/email/templates')
    const next = {}
    if (Array.isArray(rows)) {
      for (const r of rows) {
        if (r?.template_key) next[r.template_key] = r
      }
    }
    setTemplatesByKey(next)
  }, [])

  useEffect(() => {
    try {
      const stored =
        typeof window !== 'undefined' ? window.localStorage.getItem('retover_admin_test_email_to') || '' : ''
      if (stored.trim()) setTestTo(stored.trim())
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setTemplatesLoading(true)
      try {
        await Promise.all([loadSmtp(), loadTemplates()])
      } catch (e) {
        if (!cancelled) setLoadError(e?.message || 'Failed to load')
      } finally {
        if (!cancelled) setLoading(false)
        if (!cancelled) setTemplatesLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loadSmtp, loadTemplates])

  const saveSmtp = async () => {
    setSaving(true)
    setSaveError('')
    try {
      const payload = {
        host: String(smtp?.host || ''),
        port: Number(smtp?.port || 587),
        username: String(smtp?.username || ''),
        from_name: String(smtp?.from_name || ''),
        from_email: String(smtp?.from_email || ''),
        ...flagsFromSecureMode(secureMode),
        is_enabled: Boolean(smtp?.is_enabled),
      }
      if (passwordDraft.trim()) payload.password = passwordDraft.trim()
      const data = await apiFetch('/admin/email/smtp', { method: 'PUT', body: JSON.stringify(payload) })
      setSmtp(data)
      setPasswordDraft('')
    } catch (e) {
      setSaveError(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const sendTest = async () => {
    setTestBusy(true)
    setTestMsg('')
    const to = testTo.trim()
    if (to) {
      try {
        window.localStorage.setItem('retover_admin_test_email_to', to)
      } catch {
        /* ignore */
      }
    }
    try {
      const res = await apiFetch('/admin/email/smtp/test', { method: 'POST', body: JSON.stringify({ to }) })
      setTestMsg(smtpTestResultMessage(res))
    } catch (e) {
      setTestMsg(e?.message || 'Send failed')
    } finally {
      setTestBusy(false)
    }
  }

  const updateTemplateField = (key, field, value) => {
    setTemplatesByKey((s) => ({
      ...s,
      [key]: { ...(s[key] || { template_key: key }), [field]: value },
    }))
  }

  const saveTemplate = async (key) => {
    setTemplateSaving(key)
    setTemplatesError('')
    try {
      const t = templatesByKey[key] || {}
      const body = {
        subject: String(t.subject || ''),
        body: String(t.body || ''),
        is_enabled: Boolean(t.is_enabled),
      }
      const updated = await apiFetch(`/admin/email/templates/${encodeURIComponent(key)}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      })
      setTemplatesByKey((s) => ({ ...s, [key]: updated }))
    } catch (e) {
      setTemplatesError(e?.message || 'Template save failed')
    } finally {
      setTemplateSaving('')
    }
  }

  const pill = smtpStatusPill(smtp)

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Email &amp; SMTP</h1>
          <p>Configure outbound email (SMTP), send a test message, and edit platform email templates.</p>
        </div>
        <div className="actions">
          <button type="button" className="btn" onClick={() => window.location.reload()}>
            Refresh
          </button>
        </div>
      </div>

      <div className="pageShell" style={{ margin: '0 auto', width: '100%', maxWidth: 980 }}>
        <div className="stack" style={{ gap: 20 }}>
          {(loadError || saveError) && (
            <div className="note" style={{ borderColor: 'rgba(255,0,0,0.35)' }}>
              {loadError || saveError}
            </div>
          )}

          <div className="card">
            <div className="cardHead">
              <h3>SMTP</h3>
              <span className={`pill ${pill.cls}`}>{pill.text}</span>
            </div>
            <div className="cardBody">
              {loading ? (
                <div className="note">Loading…</div>
              ) : (
                <>
                  <div className="miniGrid" style={{ marginBottom: 14 }}>
                    <div className="mini">
                      <label>Password on file</label>
                      <strong>{smtp?.password_set ? 'Set' : 'Not set'}</strong>
                    </div>
                    <div className="mini">
                      <label>Missing fields</label>
                      <strong>{(smtp?.incomplete_fields || []).join(', ') || '—'}</strong>
                    </div>
                    <div className="mini">
                      <label>Last update</label>
                      <strong>{smtp?.updated_at ? new Date(smtp.updated_at).toLocaleString() : '—'}</strong>
                    </div>
                  </div>

                  <div className="note" style={{ marginBottom: 14 }}>
                    Passwords are encrypted at rest and are never returned to the browser. Leave the password field blank
                    to keep the current one.
                  </div>

                  <div className="stack" style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={Boolean(smtp?.is_enabled)}
                        onChange={(e) => setSmtp((s) => ({ ...s, is_enabled: e.target.checked }))}
                      />
                      <span className="label" style={{ margin: 0 }}>
                        SMTP enabled (required for sending)
                      </span>
                    </label>

                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className="label">Host</label>
                      <input
                        className="input"
                        value={String(smtp?.host || '')}
                        onChange={(e) => setSmtp((s) => ({ ...s, host: e.target.value }))}
                        placeholder="smtp.yourprovider.com"
                        autoComplete="off"
                      />
                    </div>

                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className="label">Port</label>
                      <input
                        className="input"
                        type="number"
                        min={1}
                        max={65535}
                        value={smtp?.port ?? 587}
                        onChange={(e) => setSmtp((s) => ({ ...s, port: Number(e.target.value) }))}
                      />
                    </div>

                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className="label">Security</label>
                      <select
                        className="input"
                        value={secureMode}
                        onChange={(e) => setSecureMode(e.target.value)}
                      >
                        <option value="starttls">STARTTLS (typical port 587)</option>
                        <option value="ssl">SSL / TLS (implicit, typical port 465)</option>
                        <option value="none">None (not recommended)</option>
                      </select>
                    </div>

                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className="label">Username</label>
                      <input
                        className="input"
                        value={String(smtp?.username || '')}
                        onChange={(e) => setSmtp((s) => ({ ...s, username: e.target.value }))}
                        placeholder="SMTP username (if required)"
                        autoComplete="off"
                      />
                    </div>

                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className="label">Password</label>
                      <input
                        className="input"
                        type="password"
                        value={passwordDraft}
                        onChange={(e) => setPasswordDraft(e.target.value)}
                        placeholder={smtp?.password_set ? 'Leave blank to keep current' : 'SMTP password'}
                        autoComplete="new-password"
                      />
                    </div>

                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className="label">From name</label>
                      <input
                        className="input"
                        value={String(smtp?.from_name || '')}
                        onChange={(e) => setSmtp((s) => ({ ...s, from_name: e.target.value }))}
                        placeholder="VOXBULK"
                      />
                    </div>

                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className="label">From email</label>
                      <input
                        className="input"
                        type="email"
                        value={String(smtp?.from_email || '')}
                        onChange={(e) => setSmtp((s) => ({ ...s, from_email: e.target.value }))}
                        placeholder="no-reply@yourdomain.com"
                      />
                    </div>
                  </div>

                  <div className="actions" style={{ marginTop: 14 }}>
                    <button type="button" className="btn primary" onClick={saveSmtp} disabled={saving}>
                      {saving ? 'Saving…' : 'Save SMTP settings'}
                    </button>
                  </div>

                  <div
                    style={{
                      marginTop: 22,
                      paddingTop: 18,
                      borderTop: '1px solid var(--border, #e5e7eb)',
                    }}
                  >
                    <h4 style={{ margin: '0 0 8px', fontSize: 15 }}>Test send</h4>
                    <p className="muted" style={{ margin: '0 0 12px', fontSize: 13 }}>
                      Sends a real message using the saved SMTP configuration.
                    </p>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'flex-end' }}>
                      <div style={{ flex: '1 1 220px', display: 'grid', gap: 6 }}>
                        <label className="label">Recipient</label>
                        <input
                          className="input"
                          type="email"
                          value={testTo}
                          onChange={(e) => setTestTo(e.target.value)}
                          placeholder="you@example.com"
                        />
                      </div>
                      <button type="button" className="btn soft" onClick={sendTest} disabled={testBusy || !testTo.trim()}>
                        {testBusy ? 'Sending…' : 'Send test email'}
                      </button>
                    </div>
                    {testMsg ? (
                      <div className="note" style={{ marginTop: 12 }}>
                        {testMsg}
                      </div>
                    ) : null}
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="card">
            <div className="cardHead">
              <h3>Email templates</h3>
              <span className="pill p-cyan">Platform</span>
            </div>
            <div className="cardBody">
              {templatesError ? (
                <div className="note" style={{ borderColor: 'rgba(255,0,0,0.35)' }}>
                  {templatesError}
                </div>
              ) : null}
              {templatesLoading ? (
                <div className="note">Loading templates…</div>
              ) : (
                <div className="stack" style={{ gap: 16 }}>
                  {TEMPLATE_META.map((meta) => {
                    const row = templatesByKey[meta.key] || {
                      template_key: meta.key,
                      subject: '',
                      body: '',
                      is_enabled: true,
                    }
                    return (
                      <div key={meta.key} className="card" style={{ margin: 0 }}>
                        <div className="cardHead">
                          <div>
                            <h3 style={{ fontSize: 15, margin: 0 }}>{meta.title}</h3>
                            <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                              {meta.description} · <code>{meta.key}</code>
                            </div>
                          </div>
                          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                            <input
                              type="checkbox"
                              checked={Boolean(row.is_enabled)}
                              onChange={(e) => updateTemplateField(meta.key, 'is_enabled', e.target.checked)}
                            />
                            <span className="muted" style={{ fontSize: 12 }}>
                              Enabled
                            </span>
                          </label>
                        </div>
                        <div className="cardBody" style={{ paddingTop: 12 }}>
                          <div style={{ display: 'grid', gap: 8, marginBottom: 10 }}>
                            <label className="label">Subject</label>
                            <input
                              className="input"
                              value={String(row.subject || '')}
                              onChange={(e) => updateTemplateField(meta.key, 'subject', e.target.value)}
                            />
                          </div>
                          <div style={{ display: 'grid', gap: 8 }}>
                            <label className="label">Body (HTML)</label>
                            <textarea
                              className="input"
                              rows={10}
                              value={String(row.body || '')}
                              onChange={(e) => updateTemplateField(meta.key, 'body', e.target.value)}
                              style={{ resize: 'vertical', fontFamily: 'ui-monospace, monospace', fontSize: 12 }}
                              placeholder="<p>Your HTML… use {{placeholders}}</p>"
                            />
                            <details style={{ fontSize: 12 }}>
                              <summary style={{ cursor: 'pointer', color: '#475569' }}>
                                Demo HTML for this template (copy placeholders)
                              </summary>
                              <pre
                                style={{
                                  marginTop: 8,
                                  padding: 10,
                                  background: '#f8fafc',
                                  borderRadius: 8,
                                  overflow: 'auto',
                                  fontSize: 11,
                                  lineHeight: 1.45,
                                }}
                              >
                                {DEMO_HTML_BY_KEY[meta.key] || '<p>Edit your HTML here.</p>'}
                              </pre>
                              <p className="muted" style={{ marginTop: 8 }}>
                                Common codes: {COMMON_PLACEHOLDERS.join(' · ')} — match{" "}
                                <code>{"{{snake_case}}"}</code> to backend variables when sending.
                              </p>
                            </details>
                          </div>
                          <div className="actions" style={{ marginTop: 12 }}>
                            <button
                              type="button"
                              className="btn primary"
                              disabled={templateSaving === meta.key}
                              onClick={() => saveTemplate(meta.key)}
                            >
                              {templateSaving === meta.key ? 'Saving…' : 'Save template'}
                            </button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
