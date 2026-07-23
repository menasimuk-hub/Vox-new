import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { connectionBadge, modeBadge } from '../lib/partnersCatalog'
import './partners.css'

const REDIRECT_URI = 'https://api.voxbulk.com/partner/v1/oauth/zoho/callback'
const INBOUND_URL = 'https://api.voxbulk.com/partner/v1/screenings'
const HEALTH_URL = 'https://api.voxbulk.com/partner/v1/health'

function copyText(text) {
  if (!text || !navigator?.clipboard) return
  navigator.clipboard.writeText(text).catch(() => {})
}

function dcToForm(raw) {
  const v = String(raw || 'com').toLowerCase()
  if (v === 'com' || v === 'us') return 'US'
  return v.toUpperCase()
}

function formToDc(v) {
  const x = String(v || 'US').toUpperCase()
  return x === 'US' ? 'com' : x.toLowerCase()
}

export default function PartnersZohoPage() {
  const [enabled, setEnabled] = useState(false)
  const [mode, setMode] = useState('sandbox')
  const [connection, setConnection] = useState('none')
  const [mappedOrg, setMappedOrg] = useState('')
  const [orgOptions, setOrgOptions] = useState([])
  const [resultWebhook, setResultWebhook] = useState('')
  const [webhookSecret, setWebhookSecret] = useState('')
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [dataCentre, setDataCentre] = useState('US')
  const [keys, setKeys] = useState([])
  const [recentJobs, setRecentJobs] = useState([])
  const [recruit, setRecruit] = useState(null)
  const [revealedKey, setRevealedKey] = useState(null)
  const [lastHealth, setLastHealth] = useState(null)
  const [flash, setFlash] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [testLog, setTestLog] = useState('')

  const [testName, setTestName] = useState('Test Candidate')
  const [testPhone, setTestPhone] = useState('+447700900000')
  const [testEmail, setTestEmail] = useState('')
  const [testJob, setTestJob] = useState('Dental Nurse')
  const [testRef, setTestRef] = useState('')
  const [testLang, setTestLang] = useState('en')
  const [lastScreening, setLastScreening] = useState(null)

  const notify = useCallback((msg) => {
    setFlash(msg)
    window.setTimeout(() => setFlash(''), 4000)
  }, [])

  const applyPayload = useCallback((data) => {
    const p = data?.provider || {}
    const cfg = p.config || {}
    setEnabled(!!p.enabled)
    setMode(p.mode || 'sandbox')
    setMappedOrg(p.mapped_org_id || '')
    setResultWebhook(p.result_webhook_url || '')
    setClientId(cfg.client_id || '')
    setClientSecret(cfg.client_secret || '')
    setDataCentre(dcToForm(cfg.data_centre || cfg.data_center))
    setKeys(data?.keys || [])
    setRecentJobs(data?.recent_jobs || [])
    setRecruit(data?.recruit || null)
    setLastHealth(
      p.last_health_at
        ? { at: p.last_health_at, ok: p.last_health_ok, message: p.last_health_message }
        : null,
    )
    const hasActive = (data?.keys || []).some((k) => k.is_active)
    if (p.last_health_ok === false) setConnection('error')
    else if (p.enabled && hasActive && p.mapped_org_id) setConnection(p.mode === 'live' ? 'connected' : 'sandbox')
    else setConnection('none')
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [data, orgs] = await Promise.all([
        apiFetch('/admin/partners/zoho'),
        apiFetch('/admin/partners/org-options').catch(() => ({ items: [] })),
      ])
      applyPayload(data)
      setOrgOptions(orgs?.items || [])
    } catch (e) {
      notify(e?.message || 'Failed to load Zoho partner')
    } finally {
      setLoading(false)
    }
  }, [applyPayload, notify])

  useEffect(() => {
    load()
    try {
      const params = new URLSearchParams(window.location.search)
      if (params.get('oauth') === 'connected') notify('Zoho Recruit connected')
      if (params.get('oauth') === 'error') notify(params.get('message') || 'Zoho OAuth failed')
      if (params.get('oauth')) window.history.replaceState({}, '', window.location.pathname)
    } catch {
      /* ignore */
    }
  }, [load, notify])

  const conn = connectionBadge(connection)
  const modeB = modeBadge(mode)

  const keyLabel = (environment) => {
    const active = keys.find((k) => k.environment === environment && k.is_active)
    if (!active) return 'Not generated'
    if (revealedKey?.environment === environment) return revealedKey.api_key
    return `${active.key_prefix}…`
  }

  const saveConfig = async () => {
    setBusy('save')
    try {
      const body = {
        enabled,
        mode,
        mapped_org_id: mappedOrg || null,
        result_webhook_url: resultWebhook || '',
        config: {
          client_id: clientId,
          client_secret: clientSecret,
          redirect_uri: REDIRECT_URI,
          data_centre: formToDc(dataCentre),
          data_center: formToDc(dataCentre),
        },
      }
      if (webhookSecret) body.webhook_secret = webhookSecret
      const data = await apiFetch('/admin/partners/zoho', { method: 'PATCH', body: JSON.stringify(body) })
      applyPayload(data)
      setWebhookSecret('')
      notify('Saved')
    } catch (e) {
      notify(e?.message || 'Save failed')
    } finally {
      setBusy('')
    }
  }

  const generateKey = async (environment) => {
    setBusy(`key-${environment}`)
    try {
      const res = await apiFetch(`/admin/partners/zoho/keys?environment=${environment}`, { method: 'POST' })
      setRevealedKey({ environment, api_key: res.api_key })
      notify(`${environment} API key generated — copy it now`)
      await load()
    } catch (e) {
      notify(e?.message || 'Key generation failed')
    } finally {
      setBusy('')
    }
  }

  const pingHealth = async () => {
    setBusy('health')
    try {
      const res = await apiFetch('/admin/partners/zoho/health', { method: 'POST' })
      setLastHealth({ at: res.checked_at, ok: res.ok, message: res.message })
      setTestLog(res.message || '')
      notify(res.message || (res.ok ? 'Health OK' : 'Health failed'))
      await load()
    } catch (e) {
      notify(e?.message || 'Health check failed')
    } finally {
      setBusy('')
    }
  }

  const connectZoho = async () => {
    setBusy('oauth')
    try {
      const body = {
        enabled,
        mode,
        mapped_org_id: mappedOrg || null,
        result_webhook_url: resultWebhook || '',
        config: {
          client_id: clientId,
          client_secret: clientSecret,
          redirect_uri: REDIRECT_URI,
          data_centre: formToDc(dataCentre),
          data_center: formToDc(dataCentre),
        },
      }
      if (webhookSecret) body.webhook_secret = webhookSecret
      await apiFetch('/admin/partners/zoho', { method: 'PATCH', body: JSON.stringify(body) })
      const res = await apiFetch('/admin/partners/zoho/oauth/start')
      if (!res?.authorize_url) throw new Error('No authorize URL')
      window.location.href = res.authorize_url
    } catch (e) {
      notify(e?.message || 'OAuth start failed')
      setBusy('')
    }
  }

  const testRecruit = async () => {
    setBusy('recruit')
    try {
      const res = await apiFetch('/admin/partners/zoho/test-recruit', { method: 'POST' })
      setTestLog(res.message || JSON.stringify(res))
      if (res.recruit) setRecruit(res.recruit)
      notify(res.message || (res.ok ? 'Recruit OK' : 'Recruit failed'))
    } catch (e) {
      notify(e?.message || 'Recruit test failed')
    } finally {
      setBusy('')
    }
  }

  const testWebhook = async () => {
    setBusy('webhook')
    try {
      const res = await apiFetch('/admin/partners/zoho/test-webhook', { method: 'POST' })
      setTestLog(res.message || '')
      notify(res.message || (res.ok ? 'Webhook OK' : 'Webhook failed'))
    } catch (e) {
      notify(e?.message || 'Webhook test failed')
    } finally {
      setBusy('')
    }
  }

  const sendScreening = async (lang) => {
    setBusy(`screen-${lang}`)
    setLastScreening(null)
    try {
      const data = await apiFetch('/admin/partners/zoho/test-screening', {
        method: 'POST',
        body: JSON.stringify({
          partner_reference_id: testRef || `zoho-test-${Date.now()}`,
          job_title: testJob || 'Test role',
          screening_questions: ['Tell me about your experience.', 'Why this role?'],
          candidate_name: testName || 'Test Candidate',
          candidate_phone: testPhone || '+447700900000',
          candidate_email: testEmail || undefined,
          preferred_language: lang,
          callback_url: resultWebhook || undefined,
        }),
      })
      setLastScreening(data)
      setTestLog(`Screening ${data.status}: ${data.screening_link}`)
      notify(data.screening_link?.includes('/book/') ? 'Real booking link created' : 'Screening created')
      await load()
    } catch (e) {
      notify(e?.message || 'Test screening failed')
      setTestLog(e?.message || 'failed')
    } finally {
      setBusy('')
    }
  }

  return (
    <div className='partners-page'>
      <Link className='partners-back' to='/partners/dashboard'>
        <i className='ti ti-arrow-left' /> Provider Dashboard
      </Link>

      <div className='partners-header'>
        <div>
          <h1>Zoho Recruit</h1>
          <div className='partners-sub'>OAuth, Partner API keys, live screening tests, score writeback</div>
        </div>
      </div>

      <div className='partners-status-row'>
        <span className={`partners-badge ${conn.cls}`}>{conn.text}</span>
        <span className={`partners-badge ${modeB.cls}`}>{modeB.text}</span>
        <span className={`partners-badge ${recruit?.connected ? 'partners-badge-green' : 'partners-badge-grey'}`}>
          {recruit?.connected ? '● Recruit connected' : '○ Recruit not connected'}
        </span>
        {flash ? <span className='partners-helper'>{flash}</span> : null}
        {loading ? <span className='partners-helper'>Loading…</span> : null}
      </div>

      {/* 1 · Workspace */}
      <section className='partners-section'>
        <h3>1 · Workspace</h3>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Enabled</span>
          <button
            type='button'
            className={`partners-toggle ${enabled ? 'on' : ''}`}
            aria-pressed={enabled}
            onClick={() => setEnabled((v) => !v)}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Mode</span>
          <select className='partners-control' style={{ maxWidth: 180 }} value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value='sandbox'>Sandbox</option>
            <option value='live'>Live</option>
          </select>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Mapped org</span>
          <select
            className='partners-control'
            style={{ maxWidth: 360 }}
            value={mappedOrg}
            onChange={(e) => setMappedOrg(e.target.value)}
          >
            <option value=''>Select organisation…</option>
            {orgOptions.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Last health</span>
          <span className='partners-field-value'>
            {lastHealth ? `${lastHealth.ok ? 'OK' : 'Fail'} · ${lastHealth.message || ''}` : '—'}
          </span>
        </div>
        <div className='partners-btn-group'>
          <button type='button' className='partners-btn partners-btn-primary' disabled={!!busy} onClick={saveConfig}>
            <i className='ti ti-device-floppy' /> Save
          </button>
          <button type='button' className='partners-btn partners-btn-secondary' disabled={!!busy} onClick={pingHealth}>
            <i className='ti ti-heartbeat' /> Test health
          </button>
        </div>
      </section>

      {/* 2 · Zoho OAuth */}
      <section className='partners-section'>
        <h3>2 · Zoho Recruit OAuth</h3>
        <div className='partners-helper' style={{ marginBottom: 12 }}>
          api-console.zoho.com → Server-based app · Client name <strong>VoxBulk AI Voice Screening</strong> · Homepage{' '}
          <strong>https://voxbulk.com</strong>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Client ID</span>
          <input className='partners-control' style={{ maxWidth: 340 }} value={clientId} onChange={(e) => setClientId(e.target.value)} />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Client Secret</span>
          <input
            className='partners-control'
            type='password'
            style={{ maxWidth: 340 }}
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            placeholder='Paste from Zoho (kept encrypted)'
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Redirect URI</span>
          <span className='partners-readonly'>
            {REDIRECT_URI}
            <button type='button' className='partners-copy-btn' onClick={() => copyText(REDIRECT_URI)} title='Copy'>
              <i className='ti ti-copy' />
            </button>
          </span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Data centre</span>
          <select
            className='partners-control'
            style={{ maxWidth: 160 }}
            value={dataCentre}
            onChange={(e) => setDataCentre(e.target.value)}
          >
            <option value='US'>US</option>
            <option value='EU'>EU</option>
            <option value='UK'>UK</option>
            <option value='IN'>IN</option>
            <option value='AU'>AU</option>
            <option value='AE'>AE</option>
            <option value='SA'>SA</option>
          </select>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Recruit status</span>
          <span className='partners-field-value'>
            {recruit?.connected
              ? `Connected${recruit.account_name ? ` · ${recruit.account_name}` : ''}`
              : 'Not connected'}
          </span>
        </div>
        <div className='partners-btn-group'>
          <button type='button' className='partners-btn partners-btn-primary' disabled={!!busy} onClick={connectZoho}>
            <i className='ti ti-plug' /> Connect Zoho Recruit
          </button>
          <button type='button' className='partners-btn partners-btn-secondary' disabled={!!busy} onClick={testRecruit}>
            <i className='ti ti-flask' /> Test Recruit API
          </button>
        </div>
      </section>

      {/* 3 · Partner API keys */}
      <section className='partners-section'>
        <h3>3 · Partner API keys</h3>
        <div className='partners-helper' style={{ marginBottom: 12 }}>
          Headers: <code>X-API-Key</code> + <code>X-Partner-Name: zoho</code> → <code>POST {INBOUND_URL}</code>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Sandbox key</span>
          <span className='partners-readonly'>
            {keyLabel('sandbox')}
            {revealedKey?.environment === 'sandbox' ? (
              <button type='button' className='partners-copy-btn' onClick={() => copyText(revealedKey.api_key)}>
                <i className='ti ti-copy' />
              </button>
            ) : null}
          </span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Live key</span>
          <span className='partners-readonly'>
            {keyLabel('live')}
            {revealedKey?.environment === 'live' ? (
              <button type='button' className='partners-copy-btn' onClick={() => copyText(revealedKey.api_key)}>
                <i className='ti ti-copy' />
              </button>
            ) : null}
          </span>
        </div>
        <div className='partners-btn-group'>
          <button type='button' className='partners-btn partners-btn-secondary' disabled={!!busy} onClick={() => generateKey('sandbox')}>
            <i className='ti ti-key' /> Generate / rotate sandbox
          </button>
          <button type='button' className='partners-btn partners-btn-secondary' disabled={!!busy} onClick={() => generateKey('live')}>
            <i className='ti ti-key' /> Generate / rotate live
          </button>
        </div>
        <div className='partners-warn'>Keys are shown once. Copy immediately.</div>
      </section>

      {/* 4 · Webhooks */}
      <section className='partners-section'>
        <h3>4 · Result webhook</h3>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Outbound URL</span>
          <input
            className='partners-control'
            style={{ maxWidth: 420 }}
            value={resultWebhook}
            onChange={(e) => setResultWebhook(e.target.value)}
            placeholder='https://… (optional catcher / Zoho function URL)'
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>HMAC secret</span>
          <input
            className='partners-control'
            type='password'
            style={{ maxWidth: 280 }}
            value={webhookSecret}
            onChange={(e) => setWebhookSecret(e.target.value)}
            placeholder='Leave blank to keep existing'
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Health URL</span>
          <span className='partners-readonly'>
            {HEALTH_URL}
            <button type='button' className='partners-copy-btn' onClick={() => copyText(HEALTH_URL)}>
              <i className='ti ti-copy' />
            </button>
          </span>
        </div>
        <div className='partners-btn-group'>
          <button type='button' className='partners-btn partners-btn-primary' disabled={!!busy} onClick={saveConfig}>
            <i className='ti ti-device-floppy' /> Save webhook
          </button>
          <button type='button' className='partners-btn partners-btn-secondary' disabled={!!busy} onClick={testWebhook}>
            <i className='ti ti-send' /> Test webhook
          </button>
        </div>
      </section>

      {/* 5 · Live screening test */}
      <section className='partners-section'>
        <h3>5 · Live screening test</h3>
        <div className='partners-helper' style={{ marginBottom: 12 }}>
          Creates a real interview draft + <strong>/book/…</strong> link and attempts WhatsApp invite. Use Zoho Candidate ID as
          Partner ref for writeback after the call.
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Language</span>
          <select className='partners-control' style={{ maxWidth: 120 }} value={testLang} onChange={(e) => setTestLang(e.target.value)}>
            <option value='en'>en</option>
            <option value='ar'>ar</option>
          </select>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Candidate name</span>
          <input className='partners-control' style={{ maxWidth: 240 }} value={testName} onChange={(e) => setTestName(e.target.value)} />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Phone (E.164)</span>
          <input className='partners-control' style={{ maxWidth: 240 }} value={testPhone} onChange={(e) => setTestPhone(e.target.value)} />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Email (optional)</span>
          <input className='partners-control' style={{ maxWidth: 280 }} value={testEmail} onChange={(e) => setTestEmail(e.target.value)} />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Job title</span>
          <input className='partners-control' style={{ maxWidth: 280 }} value={testJob} onChange={(e) => setTestJob(e.target.value)} />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Zoho Candidate ID</span>
          <input
            className='partners-control'
            style={{ maxWidth: 280 }}
            value={testRef}
            onChange={(e) => setTestRef(e.target.value)}
            placeholder='partner_reference_id'
          />
        </div>
        <div className='partners-btn-group'>
          <button type='button' className='partners-btn partners-btn-primary' disabled={!!busy} onClick={() => sendScreening('en')}>
            <i className='ti ti-phone-call' /> Test screening (EN)
          </button>
          <button type='button' className='partners-btn partners-btn-primary' disabled={!!busy} onClick={() => sendScreening('ar')}>
            <i className='ti ti-phone-call' /> Test screening (AR)
          </button>
          <button
            type='button'
            className='partners-btn partners-btn-secondary'
            disabled={!!busy}
            onClick={() => sendScreening(testLang)}
          >
            <i className='ti ti-player-play' /> Run with selected language
          </button>
        </div>
        {lastScreening ? (
          <div className='partners-test-result'>
            <span className='partners-badge partners-badge-green'>● {lastScreening.status}</span>
            <div style={{ marginTop: 8 }}>
              Booking link:{' '}
              <a href={lastScreening.screening_link} target='_blank' rel='noreferrer' style={{ color: '#2563eb' }}>
                {lastScreening.screening_link}
              </a>
            </div>
            <div style={{ marginTop: 4, fontSize: 13 }}>ID: {lastScreening.screening_id}</div>
          </div>
        ) : null}
        {testLog ? <div className='partners-footer-note' style={{ marginTop: 12 }}>{testLog}</div> : null}
      </section>

      {/* 6 · Recent jobs */}
      <section className='partners-section'>
        <h3>6 · Recent jobs</h3>
        {recentJobs.length === 0 ? (
          <div className='partners-footer-note' style={{ marginTop: 0 }}>
            No jobs yet.
          </div>
        ) : (
          <div className='partners-table-wrap'>
            <table className='partners-table'>
              <thead>
                <tr>
                  <th>Ref</th>
                  <th>Candidate</th>
                  <th>Job</th>
                  <th>Lang</th>
                  <th>Status</th>
                  <th>Score</th>
                  <th>Link</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {recentJobs.map((j) => (
                  <tr key={j.id}>
                    <td>{j.partner_reference_id}</td>
                    <td>{j.candidate_name}</td>
                    <td>{j.job_title}</td>
                    <td>{j.preferred_language}</td>
                    <td>{j.result_status || j.status}</td>
                    <td>{j.candidate_score ?? '—'}</td>
                    <td>
                      {j.screening_link ? (
                        <a href={j.screening_link} target='_blank' rel='noreferrer' style={{ color: '#2563eb' }}>
                          open
                        </a>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>{j.created_at || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
