import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { connectionBadge, modeBadge } from '../lib/partnersCatalog'
import './partners.css'

const INBOUND_URL = 'https://api.voxbulk.com/partner/v1/screenings'
const TABS = [
  { id: 'connection', label: 'Connection' },
  { id: 'keys', label: 'API keys' },
  { id: 'webhook', label: 'Webhook' },
  { id: 'activity', label: 'Activity' },
]

function copyText(text) {
  if (!text || !navigator?.clipboard) return
  navigator.clipboard.writeText(text).catch(() => {})
}

export default function PartnersBreezyPage() {
  const [tab, setTab] = useState('connection')
  const [enabled, setEnabled] = useState(false)
  const [mode, setMode] = useState('sandbox')
  const [releaseMode, setReleaseMode] = useState('testing')
  const [connection, setConnection] = useState('none')
  const [mappedOrg, setMappedOrg] = useState('')
  const [orgOptions, setOrgOptions] = useState([])
  const [resultWebhook, setResultWebhook] = useState('')
  const [webhookSecret, setWebhookSecret] = useState('')
  const [keys, setKeys] = useState([])
  const [recentJobs, setRecentJobs] = useState([])
  const [revealedKey, setRevealedKey] = useState(null)
  const [flash, setFlash] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [actionError, setActionError] = useState('')

  const notify = useCallback((msg, isError = false) => {
    const text = String(msg || '')
    setFlash(text)
    if (isError) setActionError(text)
    else if (text) setActionError('')
    window.setTimeout(() => setFlash(''), 5000)
  }, [])

  const applyPayload = useCallback((data) => {
    const p = data?.provider || {}
    setEnabled(!!p.enabled)
    setMode(p.mode || 'sandbox')
    setReleaseMode(p.release_mode === 'live' ? 'live' : 'testing')
    setMappedOrg(p.mapped_org_id || '')
    setResultWebhook(p.result_webhook_url || '')
    setKeys(data?.keys || [])
    setRecentJobs(data?.recent_jobs || [])
    const hasActive = (data?.keys || []).some((k) => k.is_active)
    if (p.last_health_ok === false) setConnection('error')
    else if (p.enabled && hasActive && p.mapped_org_id) setConnection(p.mode === 'live' ? 'connected' : 'sandbox')
    else setConnection('none')
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [data, orgs] = await Promise.all([
        apiFetch('/admin/partners/breezy'),
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
  }, [load])

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
      release_mode: releaseMode === 'live' ? 'live' : 'testing',
      mapped_org_id: mappedOrg || null,
      result_webhook_url: resultWebhook || '',
    }
    if (webhookSecret) body.webhook_secret = webhookSecret
    return body
  }

  const saveConfig = async () => {
    setBusy('save')
    try {
      const data = await apiFetch('/admin/partners/breezy', {
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
      const res = await apiFetch(`/admin/partners/breezy/keys?environment=${environment}`, { method: 'POST' })
      setRevealedKey({ environment, api_key: res.api_key })
      notify(`${environment} key ready — copy now`)
      await load()
    } catch (e) {
      notify(e?.message || 'Key failed', true)
    } finally {
      setBusy('')
    }
  }

  const testConnection = async () => {
    setBusy('health')
    setActionError('')
    try {
      const res = await apiFetch('/admin/partners/breezy/health', { method: 'POST' })
      notify(res.message || (res.ok ? 'Connection OK' : 'Connection failed'), !res.ok)
      await load()
    } catch (e) {
      notify(e?.message || 'Connection test failed', true)
    } finally {
      setBusy('')
    }
  }

  const testWebhook = async () => {
    setBusy('webhook')
    try {
      const res = await apiFetch('/admin/partners/breezy/test-webhook', { method: 'POST' })
      notify(res.message || (res.ok ? 'Webhook OK' : 'Webhook failed'), !res.ok)
    } catch (e) {
      notify(e?.message || 'Webhook test failed', true)
    } finally {
      setBusy('')
    }
  }

  return (
    <div className='partners-page partners-breezy'>
      <Link className='partners-back' to='/partners/dashboard'>
        <i className='ti ti-arrow-left' /> Partners
      </Link>

      <div className='partners-header'>
        <div>
          <h1>Breezy HR</h1>
          <div className='partners-sub'>
            Enable Partner API access. Organisations connect their own Breezy API token in Dashboard → Integrations.
          </div>
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
            <span className='partners-field-label'>API mode</span>
            <select className='partners-control' style={{ maxWidth: 180 }} value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value='sandbox'>Sandbox</option>
              <option value='live'>Live</option>
            </select>
          </div>
          <div className='partners-field-row'>
            <span className='partners-field-label'>Dashboard release</span>
            <select
              className='partners-control'
              style={{ maxWidth: 180 }}
              value={releaseMode}
              onChange={(e) => setReleaseMode(e.target.value)}
              title='Testing: only Test group emails see Breezy HR. Live: everyone.'
            >
              <option value='testing'>Testing</option>
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
          <p className='partners-helper' style={{ marginTop: 8 }}>
            Mapped org receives Partner API screenings. Customers still paste their Breezy PAT in the dashboard — no
            OAuth client is required.
          </p>
          <div className='partners-btn-group'>
            <button type='button' className='partners-btn partners-btn-primary' disabled={!!busy} onClick={saveConfig}>
              Save
            </button>
            <button type='button' className='partners-btn partners-btn-secondary' disabled={!!busy} onClick={testConnection}>
              Test health
            </button>
          </div>
          {actionError ? (
            <div className='partners-warn' style={{ marginTop: 14 }}>
              <strong>Error:</strong>
              <div style={{ marginTop: 6, userSelect: 'text', wordBreak: 'break-word' }}>{actionError}</div>
            </div>
          ) : null}
        </section>
      ) : null}

      {tab === 'keys' ? (
        <section className='partners-section'>
          <div className='partners-field-row'>
            <span className='partners-field-label'>X-Partner-Name</span>
            <span className='partners-readonly'>
              breezy
              <button type='button' className='partners-copy-btn' onClick={() => copyText('breezy')}>
                <i className='ti ti-copy' />
              </button>
            </span>
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
          <div className='partners-warn'>
            Keys show once — copy immediately. Use <code>position_id:candidate_id</code> as{' '}
            <code>partner_reference_id</code> so results can write back into Breezy.
          </div>
        </section>
      ) : null}

      {tab === 'webhook' ? (
        <section className='partners-section'>
          <p className='partners-helper' style={{ marginBottom: 16 }}>
            Optional URL that receives screening results (score, status, report link) after analysis.
          </p>
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

      {tab === 'activity' ? (
        <section className='partners-section'>
          <h3 style={{ margin: '0 0 12px', fontSize: 14 }}>Recent screenings</h3>
          {recentJobs.length === 0 ? (
            <div className='partners-footer-note' style={{ marginTop: 0 }}>
              No Partner API screenings yet.
            </div>
          ) : (
            <div className='partners-table-wrap'>
              <table className='partners-table'>
                <thead>
                  <tr>
                    <th>Reference</th>
                    <th>Candidate</th>
                    <th>Status</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {recentJobs.map((j) => (
                    <tr key={j.id}>
                      <td>{j.partner_reference_id}</td>
                      <td>{j.candidate_name}</td>
                      <td>{j.result_status || j.status}</td>
                      <td>{j.created_at || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}
    </div>
  )
}
