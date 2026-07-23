import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { connectionBadge, modeBadge } from '../lib/partnersCatalog'
import './partners.css'

const REDIRECT_URI = 'https://api.voxbulk.com/partner/v1/oauth/zoho/callback'
const INBOUND_URL = 'https://api.voxbulk.com/partner/v1/screenings'
const TABS = [
  { id: 'connection', label: 'Connection' },
  { id: 'oauth', label: 'Zoho OAuth' },
  { id: 'keys', label: 'API keys' },
  { id: 'webhook', label: 'Webhook' },
  { id: 'test', label: 'Test' },
]

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
  const [tab, setTab] = useState('oauth')
  const [enabled, setEnabled] = useState(false)
  const [mode, setMode] = useState('sandbox')
  const [connection, setConnection] = useState('none')
  const [mappedOrg, setMappedOrg] = useState('')
  const [orgOptions, setOrgOptions] = useState([])
  const [resultWebhook, setResultWebhook] = useState('')
  const [webhookSecret, setWebhookSecret] = useState('')
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [dataCentre, setDataCentre] = useState('EU')
  const [keys, setKeys] = useState([])
  const [recentJobs, setRecentJobs] = useState([])
  const [recruit, setRecruit] = useState(null)
  const [revealedKey, setRevealedKey] = useState(null)
  const [flash, setFlash] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [actionError, setActionError] = useState('')
  const [testName, setTestName] = useState('')
  const [testPhone, setTestPhone] = useState('')
  const [testEmail, setTestEmail] = useState('')
  const [testJob, setTestJob] = useState('')
  const [testRef, setTestRef] = useState('')
  const [lastScreening, setLastScreening] = useState(null)

  const notify = useCallback((msg, isError = false) => {
    const text = String(msg || '')
    setFlash(text)
    if (isError) setActionError(text)
    else if (text) setActionError('')
    window.setTimeout(() => setFlash(''), 5000)
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
    setDataCentre(dcToForm(cfg.data_centre || cfg.data_center || 'eu'))
    setKeys(data?.keys || [])
    setRecentJobs(data?.recent_jobs || [])
    setRecruit(data?.recruit || null)
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
      notify(e?.message || 'Failed to load', true)
    } finally {
      setLoading(false)
    }
  }, [applyPayload, notify])

  useEffect(() => {
    load()
    try {
      const params = new URLSearchParams(window.location.search)
      if (params.get('oauth') === 'connected') {
        notify('Zoho Recruit connected')
        setTab('oauth')
      }
      if (params.get('oauth') === 'error') notify(params.get('message') || 'OAuth failed', true)
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

  const buildSaveBody = () => {
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
    return body
  }

  const saveConfig = async () => {
    setBusy('save')
    try {
      const data = await apiFetch('/admin/partners/zoho', {
        method: 'PATCH',
        body: JSON.stringify(buildSaveBody()),
      })
      applyPayload(data)
      setWebhookSecret('')
      notify('Saved')
    } catch (e) {
      notify(e?.message || 'Save failed', true)
    } finally {
      setBusy('')
    }
  }

  const generateKey = async (environment) => {
    setBusy(`key-${environment}`)
    try {
      const res = await apiFetch(`/admin/partners/zoho/keys?environment=${environment}`, { method: 'POST' })
      setRevealedKey({ environment, api_key: res.api_key })
      notify(`${environment} key ready — copy now`)
      await load()
    } catch (e) {
      notify(e?.message || 'Key failed', true)
    } finally {
      setBusy('')
    }
  }

  const pingHealth = async () => {
    setBusy('health')
    try {
      const res = await apiFetch('/admin/partners/zoho/health', { method: 'POST' })
      notify(res.message || (res.ok ? 'Health OK' : 'Health failed'))
      await load()
    } catch (e) {
      notify(e?.message || 'Health failed')
    } finally {
      setBusy('')
    }
  }

  const connectZoho = async () => {
    setBusy('oauth')
    try {
      await apiFetch('/admin/partners/zoho', { method: 'PATCH', body: JSON.stringify(buildSaveBody()) })
      const res = await apiFetch('/admin/partners/zoho/oauth/start')
      if (!res?.authorize_url) throw new Error('No authorize URL')
      window.location.href = res.authorize_url
    } catch (e) {
      notify(e?.message || 'OAuth start failed', true)
      setBusy('')
    }
  }

  const testRecruit = async () => {
    setBusy('recruit')
    setActionError('')
    try {
      const res = await apiFetch('/admin/partners/zoho/test-recruit', { method: 'POST' })
      if (res.recruit) setRecruit(res.recruit)
      notify(res.message || (res.ok ? 'Recruit OK' : 'Recruit failed'), !res.ok)
    } catch (e) {
      notify(e?.message || 'Recruit test failed', true)
    } finally {
      setBusy('')
    }
  }

  const testWebhook = async () => {
    setBusy('webhook')
    try {
      const res = await apiFetch('/admin/partners/zoho/test-webhook', { method: 'POST' })
      notify(res.message || (res.ok ? 'Webhook OK' : 'Webhook failed'), !res.ok)
    } catch (e) {
      notify(e?.message || 'Webhook test failed', true)
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
          screening_questions: ['Tell me about your experience.'],
          candidate_name: testName || 'Test Candidate',
          candidate_phone: testPhone || '+447700900000',
          candidate_email: testEmail || undefined,
          preferred_language: lang,
          callback_url: resultWebhook || undefined,
        }),
      })
      setLastScreening(data)
      notify(data.screening_link?.includes('/book/') ? 'Booking link created' : 'Screening created')
      await load()
    } catch (e) {
      notify(e?.message || 'Screening failed', true)
    } finally {
      setBusy('')
    }
  }

  return (
    <div className='partners-page partners-zoho'>
      <Link className='partners-back' to='/partners/dashboard'>
        <i className='ti ti-arrow-left' /> Partners
      </Link>

      <div className='partners-header'>
        <div>
          <h1>Zoho Recruit</h1>
          <div className='partners-sub'>Connect OAuth, issue Partner API keys, run a live screening</div>
        </div>
        <div className='partners-btn-group' style={{ margin: 0 }}>
          <button type='button' className='partners-btn partners-btn-primary' disabled={!!busy} onClick={saveConfig}>
            Save
          </button>
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

      <div className='partners-tabs'>
        {TABS.map((t) => (
          <button
            key={t.id}
            type='button'
            className={`partners-tab${tab === t.id ? ' active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'connection' ? (
        <section className='partners-section'>
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
          <div className='partners-btn-group'>
            <button type='button' className='partners-btn partners-btn-primary' disabled={!!busy} onClick={saveConfig}>
              Save
            </button>
            <button type='button' className='partners-btn partners-btn-secondary' disabled={!!busy} onClick={pingHealth}>
              Test health
            </button>
          </div>
        </section>
      ) : null}

      {tab === 'oauth' ? (
        <section className='partners-section'>
          <div className='partners-field-row'>
            <span className='partners-field-label'>Client ID</span>
            <input className='partners-control' style={{ maxWidth: 360 }} value={clientId} onChange={(e) => setClientId(e.target.value)} />
          </div>
          <div className='partners-field-row'>
            <span className='partners-field-label'>Client Secret</span>
            <input
              className='partners-control'
              type='password'
              style={{ maxWidth: 360 }}
              value={clientSecret}
              onChange={(e) => setClientSecret(e.target.value)}
            />
          </div>
          <div className='partners-field-row'>
            <span className='partners-field-label'>Redirect URI</span>
            <span className='partners-readonly'>
              {REDIRECT_URI}
              <button type='button' className='partners-copy-btn' onClick={() => copyText(REDIRECT_URI)}>
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
              <option value='EU'>EU</option>
              <option value='UK'>UK</option>
              <option value='US'>US</option>
              <option value='IN'>IN</option>
              <option value='AU'>AU</option>
              <option value='AE'>AE</option>
              <option value='SA'>SA</option>
            </select>
          </div>
          <div className='partners-field-row'>
            <span className='partners-field-label'>Status</span>
            <span className='partners-field-value'>
              {recruit?.connected
                ? `Connected${recruit.account_name ? ` · ${recruit.account_name}` : ''}`
                : 'Not connected'}
            </span>
          </div>
          <div className='partners-btn-group'>
            <button type='button' className='partners-btn partners-btn-primary' disabled={!!busy} onClick={connectZoho}>
              Connect Zoho Recruit
            </button>
            <button type='button' className='partners-btn partners-btn-secondary' disabled={!!busy} onClick={testRecruit}>
              Test Recruit API
            </button>
          </div>
          {actionError ? (
            <div className='partners-warn' style={{ marginTop: 14 }}>
              <strong>Error (copy this):</strong>
              <div style={{ marginTop: 6, userSelect: 'text', wordBreak: 'break-word' }}>{actionError}</div>
              <button
                type='button'
                className='partners-btn partners-btn-secondary'
                style={{ marginTop: 10 }}
                onClick={() => copyText(actionError)}
              >
                Copy error
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      {tab === 'keys' ? (
        <section className='partners-section'>
          <div className='partners-field-row'>
            <span className='partners-field-label'>X-Partner-Name</span>
            <span className='partners-readonly'>zoho</span>
          </div>
          <div className='partners-field-row'>
            <span className='partners-field-label'>Inbound URL</span>
            <span className='partners-readonly'>
              {INBOUND_URL}
              <button type='button' className='partners-copy-btn' onClick={() => copyText(INBOUND_URL)}>
                <i className='ti ti-copy' />
              </button>
            </span>
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
              Generate sandbox
            </button>
            <button type='button' className='partners-btn partners-btn-secondary' disabled={!!busy} onClick={() => generateKey('live')}>
              Generate live
            </button>
          </div>
          <div className='partners-warn'>Keys show once. Copy immediately.</div>
        </section>
      ) : null}

      {tab === 'webhook' ? (
        <section className='partners-section'>
          <div className='partners-field-row'>
            <span className='partners-field-label'>Result URL</span>
            <input
              className='partners-control'
              style={{ maxWidth: 420 }}
              value={resultWebhook}
              onChange={(e) => setResultWebhook(e.target.value)}
              placeholder='https://…'
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
              placeholder='Leave blank to keep'
            />
          </div>
          <div className='partners-btn-group'>
            <button type='button' className='partners-btn partners-btn-primary' disabled={!!busy} onClick={saveConfig}>
              Save
            </button>
            <button type='button' className='partners-btn partners-btn-secondary' disabled={!!busy} onClick={testWebhook}>
              Test webhook
            </button>
          </div>
        </section>
      ) : null}

      {tab === 'test' ? (
        <section className='partners-section'>
          <div className='partners-field-row'>
            <span className='partners-field-label'>Name</span>
            <input className='partners-control' style={{ maxWidth: 240 }} value={testName} onChange={(e) => setTestName(e.target.value)} />
          </div>
          <div className='partners-field-row'>
            <span className='partners-field-label'>Phone</span>
            <input
              className='partners-control'
              style={{ maxWidth: 240 }}
              value={testPhone}
              onChange={(e) => setTestPhone(e.target.value)}
              placeholder='+44…'
            />
          </div>
          <div className='partners-field-row'>
            <span className='partners-field-label'>Email</span>
            <input className='partners-control' style={{ maxWidth: 280 }} value={testEmail} onChange={(e) => setTestEmail(e.target.value)} />
          </div>
          <div className='partners-field-row'>
            <span className='partners-field-label'>Job title</span>
            <input className='partners-control' style={{ maxWidth: 280 }} value={testJob} onChange={(e) => setTestJob(e.target.value)} />
          </div>
          <div className='partners-field-row'>
            <span className='partners-field-label'>Zoho Candidate ID</span>
            <input className='partners-control' style={{ maxWidth: 280 }} value={testRef} onChange={(e) => setTestRef(e.target.value)} />
          </div>
          <div className='partners-btn-group'>
            <button type='button' className='partners-btn partners-btn-primary' disabled={!!busy} onClick={() => sendScreening('en')}>
              Test EN
            </button>
            <button type='button' className='partners-btn partners-btn-primary' disabled={!!busy} onClick={() => sendScreening('ar')}>
              Test AR
            </button>
          </div>
          {lastScreening ? (
            <div className='partners-test-result'>
              <span className='partners-badge partners-badge-green'>● {lastScreening.status}</span>
              <div style={{ marginTop: 8 }}>
                <a href={lastScreening.screening_link} target='_blank' rel='noreferrer' style={{ color: '#2563eb' }}>
                  {lastScreening.screening_link}
                </a>
              </div>
            </div>
          ) : null}

          {recentJobs.length > 0 ? (
            <div className='partners-table-wrap' style={{ marginTop: 20 }}>
              <table className='partners-table'>
                <thead>
                  <tr>
                    <th>Ref</th>
                    <th>Candidate</th>
                    <th>Status</th>
                    <th>Link</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {recentJobs.slice(0, 10).map((j) => (
                    <tr key={j.id}>
                      <td>{j.partner_reference_id}</td>
                      <td>{j.candidate_name}</td>
                      <td>{j.result_status || j.status}</td>
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
          ) : null}
        </section>
      ) : null}
    </div>
  )
}
