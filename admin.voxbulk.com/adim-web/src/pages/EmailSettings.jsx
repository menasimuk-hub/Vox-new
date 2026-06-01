import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import {
  MESSAGING_TABS,
  bodyPreview,
  emailDisplayDescription,
  emailDisplayTitle,
  slugifyTemplateKey,
  subjectPreview,
  waDisplayDescription,
  waDisplayTitle,
} from '../lib/messagingConstants'

function uniqueEmailTemplateKey(baseKey, existingKeys) {
  const keys = new Set(existingKeys)
  let candidate = slugifyTemplateKey(`${baseKey}_copy`)
  if (candidate.length < 3) candidate = `${baseKey}_copy`.slice(0, 64)
  if (!keys.has(candidate)) return candidate
  for (let n = 2; n < 1000; n += 1) {
    const next = slugifyTemplateKey(`${baseKey}_copy_${n}`)
    if (!keys.has(next)) return next
  }
  return slugifyTemplateKey(`${baseKey}_${Date.now()}`)
}

function StatusDot({ enabled }) {
  return (
    <span
      className={`statusDot ${enabled ? 'on' : 'off'}`}
      title={enabled ? 'Enabled' : 'Disabled'}
      aria-label={enabled ? 'Enabled' : 'Disabled'}
    />
  )
}

function TemplateActions({ onEdit, onDuplicate, onDelete, canDelete, showDuplicate = false }) {
  return (
    <div className="templateRowActions">
      <button type="button" className="emailIconBtn primary" title="Edit" onClick={onEdit}>
        <i className="ti ti-edit" />
      </button>
      {showDuplicate ? (
        <button type="button" className="emailIconBtn" title="Duplicate" onClick={onDuplicate}>
          <i className="ti ti-copy" />
        </button>
      ) : null}
      <button
        type="button"
        className="emailIconBtn danger"
        title={canDelete ? 'Delete' : 'System templates cannot be deleted'}
        onClick={canDelete ? onDelete : undefined}
        disabled={!canDelete}
      >
        <i className="ti ti-trash" />
      </button>
    </div>
  )
}

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

function imapDefaultsForSecureMode(mode) {
  const flags = flagsFromSecureMode(mode)
  return {
    imap_use_ssl: flags.use_ssl,
    imap_use_tls: flags.use_tls,
    imap_port: mode === 'ssl' ? 993 : 143,
  }
}

function smtpHostToImapHost(host) {
  const h = String(host || '').trim()
  if (!h) return ''
  if (/^smtp\./i.test(h)) return h.replace(/^smtp\./i, 'imap.')
  if (/^mail\./i.test(h)) return h.replace(/^mail\./i, 'imap.')
  const parts = h.split('.')
  if (parts.length >= 2) return `imap.${parts.slice(-2).join('.')}`
  return `imap.${h}`
}

function smtpTestResultMessage(payload) {
  if (payload != null && typeof payload === 'object') {
    if (typeof payload.message === 'string' && payload.message.trim()) return payload.message.trim()
    if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail.trim()
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
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = MESSAGING_TABS.some((t) => t.id === searchParams.get('tab'))
    ? searchParams.get('tab')
    : 'email'

  const setTab = (id) => setSearchParams({ tab: id })

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

  const [careerMailbox, setCareerMailbox] = useState(null)
  const [careerPasswordDraft, setCareerPasswordDraft] = useState('')
  const [careerSecureMode, setCareerSecureMode] = useState('ssl')
  const [careerSaving, setCareerSaving] = useState(false)
  const [careerTestBusy, setCareerTestBusy] = useState(false)
  const [careerSyncBusy, setCareerSyncBusy] = useState(false)
  const [careerActionMsg, setCareerActionMsg] = useState('')

  const [emailTemplates, setEmailTemplates] = useState([])
  const [waTemplates, setWaTemplates] = useState([])
  const [smsTemplates, setSmsTemplates] = useState([])
  const [listError, setListError] = useState('')
  const [listsLoading, setListsLoading] = useState(true)

  const loadSmtp = useCallback(async () => {
    const data = await apiFetch('/admin/email/smtp')
    setSmtp(data)
    setSecureMode(secureModeFromFlags(Boolean(data?.use_tls), Boolean(data?.use_ssl)))
  }, [])

  const loadCareerMailbox = useCallback(async () => {
    const data = await apiFetch('/admin/email/career-mailbox')
    setCareerMailbox(data)
    setCareerSecureMode(secureModeFromFlags(Boolean(data?.imap_use_tls), Boolean(data?.imap_use_ssl)))
  }, [])

  const loadLists = useCallback(async () => {
    setListError('')
    try {
      const email = await apiFetch('/admin/email/templates')
      setEmailTemplates(Array.isArray(email) ? email : [])
    } catch (e) {
      setListError(e?.message || 'Could not load email templates')
      setEmailTemplates([])
    }
    try {
      const wa = await apiFetch('/admin/messaging/whatsapp/templates')
      setWaTemplates(Array.isArray(wa) ? wa : [])
    } catch {
      setWaTemplates([])
    }
    try {
      const sms = await apiFetch('/admin/messaging/sms/templates')
      setSmsTemplates(Array.isArray(sms) ? sms : [])
    } catch {
      setSmsTemplates([])
    }
  }, [])

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem('voxbulk_admin_test_email_to') || ''
      if (stored.trim()) setTestTo(stored.trim())
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setListsLoading(true)
      setLoadError('')
      try {
        await loadSmtp()
        await loadCareerMailbox()
      } catch (e) {
        if (!cancelled) setLoadError(e?.message || 'Failed to load SMTP')
      }
      try {
        await loadLists()
      } catch (e) {
        if (!cancelled) setListError(e?.message || 'Failed to load templates')
      } finally {
        if (!cancelled) setLoading(false)
        if (!cancelled) setListsLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loadSmtp, loadLists, loadCareerMailbox])

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

  const saveCareerMailbox = async () => {
    setCareerSaving(true)
    setSaveError('')
    try {
      const enc = imapDefaultsForSecureMode(careerSecureMode)
      const payload = {
        mailbox_email: String(careerMailbox?.mailbox_email || 'careers@voxbulk.com'),
        imap_host: String(careerMailbox?.imap_host || ''),
        imap_port: Number(careerMailbox?.imap_port || enc.imap_port),
        imap_use_ssl: enc.imap_use_ssl,
        imap_use_tls: enc.imap_use_tls,
        imap_username: String(careerMailbox?.imap_username || ''),
        sync_interval_minutes: Number(careerMailbox?.sync_interval_minutes || 15),
        is_enabled: Boolean(careerMailbox?.is_enabled),
      }
      if (careerPasswordDraft.trim()) payload.password = careerPasswordDraft.trim()
      const data = await apiFetch('/admin/email/career-mailbox', { method: 'PUT', body: JSON.stringify(payload) })
      setCareerMailbox(data)
      setCareerPasswordDraft('')
      setCareerSecureMode(secureModeFromFlags(Boolean(data?.imap_use_tls), Boolean(data?.imap_use_ssl)))
    } catch (e) {
      setSaveError(e?.message || 'Save failed')
    } finally {
      setCareerSaving(false)
    }
  }

  const copyCareerFromSmtp = () => {
    if (!smtp) return
    const smtpMode = secureModeFromFlags(Boolean(smtp.use_tls), Boolean(smtp.use_ssl))
    const imapMode = smtpMode === 'ssl' ? 'ssl' : smtpMode === 'starttls' ? 'starttls' : 'none'
    const enc = imapDefaultsForSecureMode(imapMode)
    setCareerSecureMode(imapMode)
    setCareerMailbox((s) => ({
      ...(s || {}),
      imap_host: smtpHostToImapHost(smtp.host) || String(smtp.host || ''),
      imap_username: String(smtp.username || smtp.from_email || ''),
      mailbox_email: String(smtp.from_email || s?.mailbox_email || 'careers@voxbulk.com'),
      imap_port: enc.imap_port,
      imap_use_ssl: enc.imap_use_ssl,
      imap_use_tls: enc.imap_use_tls,
    }))
    setCareerActionMsg(
      smtpMode === 'ssl'
        ? 'Copied from SMTP (port 465). Use IMAP port 993 with SSL/TLS — same username; enter the same mailbox password below if not saved yet.'
        : 'Copied host and username from SMTP — check IMAP port and encryption match your provider.',
    )
  }

  const testCareerMailbox = async () => {
    setCareerTestBusy(true)
    setCareerActionMsg('')
    try {
      const res = await apiFetch('/admin/email/career-mailbox/test', { method: 'POST', body: '{}' })
      setCareerActionMsg(res?.detail || 'IMAP connection OK')
    } catch (e) {
      setCareerActionMsg(e?.message || 'Connection failed')
    } finally {
      setCareerTestBusy(false)
    }
  }

  const syncCareerMailboxNow = async () => {
    setCareerSyncBusy(true)
    setCareerActionMsg('')
    try {
      const res = await apiFetch('/admin/email/career-mailbox/sync-now', { method: 'POST', body: '{}' })
      setCareerActionMsg(res?.message || 'Sync completed')
      await loadCareerMailbox()
    } catch (e) {
      setCareerActionMsg(e?.message || 'Sync failed')
    } finally {
      setCareerSyncBusy(false)
    }
  }

  const sendSmtpTest = async () => {
    setTestBusy(true)
    setTestMsg('')
    const to = testTo.trim()
    if (to) {
      try {
        window.localStorage.setItem('voxbulk_admin_test_email_to', to)
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

  const deleteEmail = async (key) => {
    if (!window.confirm(`Delete email template "${key}"?`)) return
    setListError('')
    try {
      await apiFetch(`/admin/email/templates/${encodeURIComponent(key)}`, { method: 'DELETE' })
      await loadLists()
    } catch (e) {
      setListError(e?.message || 'Delete failed')
    }
  }

  const duplicateEmail = async (row) => {
    setListError('')
    try {
      const templateKey = uniqueEmailTemplateKey(row.template_key, emailTemplates.map((t) => t.template_key))
      const created = await apiFetch('/admin/email/templates', {
        method: 'POST',
        body: JSON.stringify({
          template_key: templateKey,
          title: `${emailDisplayTitle(row)} (Copy)`,
          subject: row.subject || '',
          body: row.body || '',
          is_enabled: Boolean(row.is_enabled),
        }),
      })
      await loadLists()
      navigate(`/settings/email/templates/${encodeURIComponent(created.template_key)}/edit`)
    } catch (e) {
      setListError(e?.message || 'Duplicate failed')
    }
  }

  const deleteWa = async (key) => {
    if (!window.confirm(`Delete WhatsApp template "${key}"?`)) return
    setListError('')
    try {
      await apiFetch(`/admin/messaging/whatsapp/templates/${encodeURIComponent(key)}`, { method: 'DELETE' })
      await loadLists()
    } catch (e) {
      setListError(e?.message || 'Delete failed')
    }
  }

  const deleteSms = async (key) => {
    if (!window.confirm(`Delete SMS template "${key}"?`)) return
    setListError('')
    try {
      await apiFetch(`/admin/messaging/sms/templates/${encodeURIComponent(key)}`, { method: 'DELETE' })
      await loadLists()
    } catch (e) {
      setListError(e?.message || 'Delete failed')
    }
  }

  const pill = smtpStatusPill(smtp)

  function careerStatusPill(cfg) {
    if (!cfg) return { cls: 'p-amber', text: 'Loading' }
    if (!cfg.is_enabled) return { cls: 'p-amber', text: 'Disabled' }
    if (cfg.configured) return { cls: 'p-green', text: 'Ready' }
    return { cls: 'p-amber', text: 'Incomplete' }
  }

  const careerPill = careerStatusPill(careerMailbox)

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Messaging &amp; SMTP</h1>
          <p>SMTP email, email templates, WhatsApp templates, and SMS templates — full-width admin hub.</p>
        </div>
        <div className="actions">
          <button type="button" className="btn soft" onClick={() => window.location.reload()}>
            <i className="ti ti-refresh" /> Refresh
          </button>
        </div>
      </div>

      <div className="pageShell emailPageShell">
        {(loadError || saveError || listError) && (
          <div className="note" style={{ borderColor: 'rgba(255,0,0,0.35)', marginBottom: 14 }}>
            {loadError || saveError || listError}
          </div>
        )}

        <div className="emailHub">
          <div className="emailTabBar" role="tablist">
            {MESSAGING_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={activeTab === tab.id}
                className={`emailTabBtn ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => setTab(tab.id)}
              >
                <i className={`ti ${tab.icon}`} />
                {tab.label}
              </button>
            ))}
          </div>

          {activeTab === 'careers' && (
            <div className="emailTabPanel" role="tabpanel">
              <div className="emailSectionTitle">
                <i className="ti ti-inbox" />
                Career CV intake mailbox (IMAP)
                <span className={`pill ${careerPill.cls}`} style={{ marginLeft: 8 }}>
                  {careerPill.text}
                </span>
              </div>
              {loading ? (
                <div className="note">Loading…</div>
              ) : (
                <div className="grid-12" style={{ gap: 16 }}>
                  <div className="span-8 stack" style={{ gap: 14 }}>
                    <div className="note">
                      Candidates email CVs to <strong>careers@voxbulk.com</strong> with a job reference (<code>VB-INT-…</code>) in the subject or body.
                      Inbound mail is fetched via <strong>IMAP</strong> (receive). Auto-replies use your <strong>SMTP</strong> tab (send). Processed emails are deleted from the inbox to keep it clear.
                    </div>
                    <div className="note" style={{ marginBottom: 0 }}>
                      If SMTP uses <strong>port 465 (SSL/TLS)</strong>, set IMAP to <strong>port 993 + SSL/TLS</strong> — same username and password, host is usually <code>imap.</code> instead of <code>smtp.</code>
                    </div>
                    <div className="miniGrid">
                      <div className="mini">
                        <label>Password on file</label>
                        <strong>{careerMailbox?.password_set ? 'Set' : 'Not set'}</strong>
                      </div>
                      <div className="mini">
                        <label>Missing fields</label>
                        <strong>{(careerMailbox?.incomplete_fields || []).join(', ') || '—'}</strong>
                      </div>
                      <div className="mini">
                        <label>Last sync</label>
                        <strong>{careerMailbox?.last_sync_at ? new Date(careerMailbox.last_sync_at).toLocaleString() : '—'}</strong>
                      </div>
                      <div className="mini">
                        <label>Last sync result</label>
                        <strong>{careerMailbox?.last_sync_ok ? 'OK' : careerMailbox?.last_sync_at ? 'Failed' : '—'}</strong>
                      </div>
                    </div>
                    {careerMailbox?.last_sync_message ? (
                      <div className="note" style={{ marginBottom: 0 }}>{careerMailbox.last_sync_message}</div>
                    ) : null}
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={Boolean(careerMailbox?.is_enabled)}
                        onChange={(e) => setCareerMailbox((s) => ({ ...s, is_enabled: e.target.checked }))}
                      />
                      <span className="label" style={{ margin: 0 }}>
                        Career mailbox sync enabled
                      </span>
                    </label>
                    <div className="actions" style={{ marginTop: 4 }}>
                      <button type="button" className="btn soft" onClick={copyCareerFromSmtp} disabled={!smtp?.host}>
                        <i className="ti ti-copy" /> Copy from SMTP settings
                      </button>
                    </div>
                    <div className="emailFormGrid">
                      <div className="span-2">
                        <label className="label">Mailbox address</label>
                        <input className="input" value={String(careerMailbox?.mailbox_email || '')} onChange={(e) => setCareerMailbox((s) => ({ ...s, mailbox_email: e.target.value }))} placeholder="careers@voxbulk.com" />
                      </div>
                      <div>
                        <label className="label">IMAP host</label>
                        <input className="input" value={String(careerMailbox?.imap_host || '')} onChange={(e) => setCareerMailbox((s) => ({ ...s, imap_host: e.target.value }))} placeholder="imap.yourprovider.com" />
                      </div>
                      <div>
                        <label className="label">IMAP port</label>
                        <input className="input" type="number" min={1} max={65535} value={careerMailbox?.imap_port ?? imapDefaultsForSecureMode(careerSecureMode).imap_port} onChange={(e) => setCareerMailbox((s) => ({ ...s, imap_port: Number(e.target.value) }))} />
                      </div>
                      <div>
                        <label className="label">Encryption</label>
                        <select
                          className="input"
                          value={careerSecureMode}
                          onChange={(e) => {
                            const mode = e.target.value
                            const enc = imapDefaultsForSecureMode(mode)
                            setCareerSecureMode(mode)
                            setCareerMailbox((s) => ({ ...s, imap_port: enc.imap_port, imap_use_ssl: enc.imap_use_ssl, imap_use_tls: enc.imap_use_tls }))
                          }}
                        >
                          <option value="starttls">STARTTLS (143)</option>
                          <option value="ssl">SSL / TLS (993) — same as SMTP 465</option>
                          <option value="none">None</option>
                        </select>
                      </div>
                      <div>
                        <label className="label">IMAP username</label>
                        <input className="input" value={String(careerMailbox?.imap_username || '')} onChange={(e) => setCareerMailbox((s) => ({ ...s, imap_username: e.target.value }))} placeholder="Usually same as mailbox email" />
                      </div>
                      <div>
                        <label className="label">Password</label>
                        <input className="input" type="password" value={careerPasswordDraft} onChange={(e) => setCareerPasswordDraft(e.target.value)} placeholder={careerMailbox?.password_set ? 'Leave blank to keep' : 'Same as SMTP mailbox password'} autoComplete="new-password" />
                      </div>
                      <div>
                        <label className="label">Sync every (minutes)</label>
                        <input className="input" type="number" min={5} max={240} value={careerMailbox?.sync_interval_minutes ?? 15} onChange={(e) => setCareerMailbox((s) => ({ ...s, sync_interval_minutes: Number(e.target.value) }))} />
                      </div>
                    </div>
                    <div className="actions">
                      <button type="button" className="btn primary" onClick={saveCareerMailbox} disabled={careerSaving}>
                        <i className="ti ti-device-floppy" /> {careerSaving ? 'Saving…' : 'Save career mailbox'}
                      </button>
                    </div>
                  </div>
                  <div className="span-4">
                    <div className="card" style={{ margin: 0 }}>
                      <div className="cardHead"><h3>Test &amp; sync</h3></div>
                      <div className="cardBody">
                        <button type="button" className="btn soft" onClick={testCareerMailbox} disabled={careerTestBusy} style={{ width: '100%', marginBottom: 10 }}>
                          <i className="ti ti-plug-connected" /> {careerTestBusy ? 'Testing…' : 'Test IMAP connection'}
                        </button>
                        <button type="button" className="btn soft" onClick={syncCareerMailboxNow} disabled={careerSyncBusy} style={{ width: '100%' }}>
                          <i className="ti ti-refresh" /> {careerSyncBusy ? 'Syncing…' : 'Sync now'}
                        </button>
                        {careerActionMsg ? <div className="note" style={{ marginTop: 12, marginBottom: 0 }}>{careerActionMsg}</div> : null}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'smtp' && (
            <div className="emailTabPanel" role="tabpanel">
              <div className="emailSectionTitle">
                <i className="ti ti-mail-cog" />
                SMTP server configuration
                <span className={`pill ${pill.cls}`} style={{ marginLeft: 8 }}>
                  {pill.text}
                </span>
              </div>
              {loading ? (
                <div className="note">Loading…</div>
              ) : (
                <div className="grid-12" style={{ gap: 16 }}>
                  <div className="span-8 stack" style={{ gap: 14 }}>
                    <div className="miniGrid">
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
                      <div className="mini">
                        <label>From address</label>
                        <strong>{smtp?.from_email || '—'}</strong>
                      </div>
                    </div>
                    <div className="note">
                      Passwords are encrypted at rest. Leave password blank to keep the current one.
                    </div>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={Boolean(smtp?.is_enabled)}
                        onChange={(e) => setSmtp((s) => ({ ...s, is_enabled: e.target.checked }))}
                      />
                      <span className="label" style={{ margin: 0 }}>
                        SMTP enabled
                      </span>
                    </label>
                    <div className="emailFormGrid">
                      <div>
                        <label className="label">SMTP host</label>
                        <input className="input" value={String(smtp?.host || '')} onChange={(e) => setSmtp((s) => ({ ...s, host: e.target.value }))} placeholder="smtp.yourprovider.com" autoComplete="off" />
                      </div>
                      <div>
                        <label className="label">Port</label>
                        <input className="input" type="number" min={1} max={65535} value={smtp?.port ?? 587} onChange={(e) => setSmtp((s) => ({ ...s, port: Number(e.target.value) }))} />
                      </div>
                      <div>
                        <label className="label">Username</label>
                        <input className="input" value={String(smtp?.username || '')} onChange={(e) => setSmtp((s) => ({ ...s, username: e.target.value }))} autoComplete="off" />
                      </div>
                      <div>
                        <label className="label">Password</label>
                        <input className="input" type="password" value={passwordDraft} onChange={(e) => setPasswordDraft(e.target.value)} placeholder={smtp?.password_set ? 'Leave blank to keep' : 'SMTP password'} autoComplete="new-password" />
                      </div>
                      <div>
                        <label className="label">Encryption</label>
                        <select className="input" value={secureMode} onChange={(e) => setSecureMode(e.target.value)}>
                          <option value="starttls">STARTTLS (587)</option>
                          <option value="ssl">SSL / TLS (465)</option>
                          <option value="none">None</option>
                        </select>
                      </div>
                      <div>
                        <label className="label">From name</label>
                        <input className="input" value={String(smtp?.from_name || '')} onChange={(e) => setSmtp((s) => ({ ...s, from_name: e.target.value }))} />
                      </div>
                      <div className="span-2">
                        <label className="label">From email</label>
                        <input className="input" type="email" value={String(smtp?.from_email || '')} onChange={(e) => setSmtp((s) => ({ ...s, from_email: e.target.value }))} />
                      </div>
                    </div>
                    <div className="actions">
                      <button type="button" className="btn primary" onClick={saveSmtp} disabled={saving}>
                        <i className="ti ti-device-floppy" /> {saving ? 'Saving…' : 'Save SMTP settings'}
                      </button>
                    </div>
                  </div>
                  <div className="span-4">
                    <div className="card" style={{ margin: 0 }}>
                      <div className="cardHead"><h3>Test send</h3></div>
                      <div className="cardBody">
                        <label className="label">Recipient</label>
                        <input className="input" type="email" value={testTo} onChange={(e) => setTestTo(e.target.value)} style={{ marginBottom: 12 }} />
                        <button type="button" className="btn soft" onClick={sendSmtpTest} disabled={testBusy || !testTo.trim()} style={{ width: '100%' }}>
                          <i className="ti ti-send" /> {testBusy ? 'Sending…' : 'Send test email'}
                        </button>
                        {testMsg ? <div className="note" style={{ marginTop: 12, marginBottom: 0 }}>{testMsg}</div> : null}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'email' && (
            <div className="emailTabPanel" role="tabpanel">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
                <div className="emailSectionTitle" style={{ margin: 0 }}>
                  <i className="ti ti-template" />
                  Email templates
                </div>
                <button type="button" className="btn primary" onClick={() => navigate('/settings/email/templates/new')}>
                  <i className="ti ti-plus" /> Create email template
                </button>
              </div>
              <div className="card" style={{ margin: 0 }}>
                <div className="cardBody" style={{ padding: 0 }}>
                  {listsLoading ? (
                    <div className="note" style={{ margin: 16 }}>Loading…</div>
                  ) : (
                    <div className="tableWrap messagingTableWrap">
                      <table className="table messagingTable">
                        <thead>
                          <tr>
                            <th>Template</th>
                            <th>Key</th>
                            <th>Subject</th>
                            <th className="colStatus" aria-label="Status" />
                            <th className="colActions">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {emailTemplates.map((row) => (
                            <tr key={row.template_key}>
                              <td>
                                <strong>{emailDisplayTitle(row)}</strong>
                                <div className="muted messagingTableDesc">{emailDisplayDescription(row)}</div>
                              </td>
                              <td><code>{row.template_key}</code></td>
                              <td className="colSubject">{subjectPreview(row.subject)}</td>
                              <td className="colStatus"><StatusDot enabled={row.is_enabled !== false} /></td>
                              <td>
                                <TemplateActions
                                  showDuplicate
                                  onEdit={() => navigate(`/settings/email/templates/${encodeURIComponent(row.template_key)}/edit`)}
                                  onDuplicate={() => duplicateEmail(row)}
                                  onDelete={() => deleteEmail(row.template_key)}
                                  canDelete={!row.is_system}
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'whatsapp' && (
            <div className="emailTabPanel" role="tabpanel">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
                <div className="emailSectionTitle" style={{ margin: 0 }}>
                  <i className="ti ti-brand-whatsapp" />
                  WhatsApp templates
                </div>
                <button type="button" className="btn primary" onClick={() => navigate('/settings/email/whatsapp/new')}>
                  <i className="ti ti-plus" /> Create WhatsApp template
                </button>
              </div>
              <div className="note" style={{ marginBottom: 14 }}>
                Outbound WhatsApp uses Telnyx — configure API key and numbers under{' '}
                <a href="/integrations/telnyx" style={{ color: 'var(--grn)' }}>Integrations → Telnyx</a>.
              </div>
              <div className="card" style={{ margin: 0 }}>
                <div className="cardBody" style={{ padding: 0 }}>
                  {listsLoading ? (
                    <div className="note" style={{ margin: 16 }}>Loading…</div>
                  ) : !waTemplates.length ? (
                    <div className="note" style={{ margin: 16 }}>No templates yet — create one.</div>
                  ) : (
                    <div className="tableWrap messagingTableWrap">
                      <table className="table messagingTable">
                        <thead>
                          <tr>
                            <th>Name</th>
                            <th>Key</th>
                            <th>Preview</th>
                            <th className="colStatus" aria-label="Status" />
                            <th className="colActions">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {waTemplates.map((row) => (
                            <tr key={row.template_key}>
                              <td>
                                <strong>{waDisplayTitle(row)}</strong>
                                <div className="muted messagingTableDesc">{waDisplayDescription(row)}</div>
                              </td>
                              <td><code>{row.template_key}</code></td>
                              <td className="colPreview">{bodyPreview(row.body)}</td>
                              <td className="colStatus"><StatusDot enabled={row.is_enabled !== false} /></td>
                              <td>
                                <TemplateActions
                                  onEdit={() => navigate(`/settings/email/whatsapp/${encodeURIComponent(row.template_key)}/edit`)}
                                  onDelete={() => deleteWa(row.template_key)}
                                  canDelete={!row.is_system}
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'sms' && (
            <div className="emailTabPanel" role="tabpanel">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
                <div className="emailSectionTitle" style={{ margin: 0 }}>
                  <i className="ti ti-message" />
                  SMS templates
                </div>
                <button type="button" className="btn primary" onClick={() => navigate('/settings/email/sms/new')}>
                  <i className="ti ti-plus" /> Create SMS template
                </button>
              </div>
              <div className="note" style={{ marginBottom: 14 }}>
                SMS sends via Telnyx — set <code>default_outbound_number</code> in{' '}
                <a href="/integrations/telnyx" style={{ color: 'var(--grn)' }}>Integrations → Telnyx</a>.
              </div>
              <div className="card" style={{ margin: 0 }}>
                <div className="cardBody" style={{ padding: 0 }}>
                  {listsLoading ? (
                    <div className="note" style={{ margin: 16 }}>Loading…</div>
                  ) : !smsTemplates.length ? (
                    <div className="note" style={{ margin: 16 }}>No templates yet — create one.</div>
                  ) : (
                    <div className="tableWrap messagingTableWrap">
                      <table className="table messagingTable">
                        <thead>
                          <tr>
                            <th>Name</th>
                            <th>Key</th>
                            <th>Preview</th>
                            <th className="colStatus" aria-label="Status" />
                            <th className="colActions">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {smsTemplates.map((row) => (
                            <tr key={row.template_key}>
                              <td><strong>{row.name}</strong></td>
                              <td><code>{row.template_key}</code></td>
                              <td className="colPreview">{bodyPreview(row.body)}</td>
                              <td className="colStatus"><StatusDot enabled={row.is_enabled !== false} /></td>
                              <td>
                                <TemplateActions
                                  onEdit={() => navigate(`/settings/email/sms/${encodeURIComponent(row.template_key)}/edit`)}
                                  onDelete={() => deleteSms(row.template_key)}
                                  canDelete
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
