import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { connectionBadge, modeBadge } from '../lib/partnersCatalog'
import './partners.css'

const REDIRECT_URI = 'https://api.voxbulk.com/partner/v1/oauth/zoho/callback'
const INBOUND_URL = 'https://api.voxbulk.com/partner/v1/screenings'
const WIDGET_URL = 'https://dashboard.voxbulk.com/zoho-recruit-widget/'
const TABS = [
  { id: 'connection', label: 'Connection' },
  { id: 'credentials', label: 'App credentials' },
  { id: 'keys', label: 'API keys' },
  { id: 'webhook', label: 'Webhook' },
  { id: 'zoho-app', label: 'Zoho app' },
]

function copyText(text) {
  if (!text || !navigator?.clipboard) return
  navigator.clipboard.writeText(text).catch(() => {})
}

export default function PartnersZohoPage() {
  const [tab, setTab] = useState('connection')
  const [enabled, setEnabled] = useState(false)
  const [mode, setMode] = useState('sandbox')
  const [releaseMode, setReleaseMode] = useState('testing')
  const [connection, setConnection] = useState('none')
  const [mappedOrg, setMappedOrg] = useState('')
  const [orgOptions, setOrgOptions] = useState([])
  const [resultWebhook, setResultWebhook] = useState('')
  const [webhookSecret, setWebhookSecret] = useState('')
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [keys, setKeys] = useState([])
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
    const cfg = p.config || {}
    setEnabled(!!p.enabled)
    setMode(p.mode || 'sandbox')
    setReleaseMode(p.release_mode === 'live' ? 'live' : 'testing')
    setMappedOrg(p.mapped_org_id || '')
    setResultWebhook(p.result_webhook_url || '')
    setClientId(cfg.client_id || '')
    setClientSecret(cfg.client_secret || '')
    setKeys(data?.keys || [])
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
      config: {
        client_id: clientId,
        client_secret: clientSecret,
        redirect_uri: REDIRECT_URI,
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

  const testConnection = async () => {
    setBusy('health')
    setActionError('')
    try {
      const res = await apiFetch('/admin/partners/zoho/health', { method: 'POST' })
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
      const res = await apiFetch('/admin/partners/zoho/test-webhook', { method: 'POST' })
      notify(res.message || (res.ok ? 'Webhook OK' : 'Webhook failed'), !res.ok)
    } catch (e) {
      notify(e?.message || 'Webhook test failed', true)
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
          <div className='partners-sub'>Platform config and connection test — users connect Recruit from the dashboard</div>
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
            <span className='partners-field-label'>Mode</span>
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
              title='Testing: only Test group emails see Zoho Recruit + its FAQs. Live: everyone.'
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
          <div className='partners-btn-group'>
            <button type='button' className='partners-btn partners-btn-primary' disabled={!!busy} onClick={saveConfig}>
              Save
            </button>
            <button type='button' className='partners-btn partners-btn-secondary' disabled={!!busy} onClick={testConnection}>
              Test connection
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

      {tab === 'credentials' ? (
        <section className='partners-section'>
          <p className='partners-helper' style={{ marginBottom: 16 }}>
            Zoho API Console app used when organisations connect Recruit from the dashboard. Data centre is chosen per user, not here.
          </p>
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
          <div className='partners-btn-group'>
            <button type='button' className='partners-btn partners-btn-primary' disabled={!!busy} onClick={saveConfig}>
              Save
            </button>
          </div>
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
          <div className='partners-warn'>Keys show once. Copy immediately. Used by the Marketplace widget and Partner API.</div>
          <div className='partners-field-row' style={{ marginTop: 12 }}>
            <span className='partners-field-label'>Inbound URL</span>
            <span className='partners-readonly'>
              {INBOUND_URL}
              <button type='button' className='partners-copy-btn' onClick={() => copyText(INBOUND_URL)}>
                <i className='ti ti-copy' />
              </button>
            </span>
          </div>
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

      {tab === 'zoho-app' ? (
        <section className='partners-section'>
          <p className='partners-helper' style={{ marginBottom: 14 }}>
            Ship VoxBulk inside Zoho Recruit via <strong>Zoho Marketplace</strong>. Customers Install the listing; screenings
            still run through the Partner API and score writeback. Until Zoho approves the listing, use Dashboard →
            Integrations → Recruiting → Launch screening.
          </p>
          <div className='partners-field-row'>
            <span className='partners-field-label'>Widget URL</span>
            <span className='partners-readonly'>
              {WIDGET_URL}
              <button type='button' className='partners-copy-btn' onClick={() => copyText(WIDGET_URL)}>
                <i className='ti ti-copy' />
              </button>
            </span>
          </div>
          <div className='partners-field-row'>
            <span className='partners-field-label'>Extension ZIP</span>
            <span className='partners-readonly'>
              zoho-recruit-extension/dist/VoxBulk-Zoho-Recruit-Widget.zip
            </span>
          </div>
          <ol style={{ margin: '0 0 16px', paddingLeft: 20, lineHeight: 1.6, fontSize: 13, color: '#334155' }}>
            <li>Confirm this org: Enabled, Client ID/Secret, API key, Mapped org connected on Recruiting</li>
            <li>Pack / use the extension ZIP from the repo (<code>zoho-recruit-extension/</code>)</li>
            <li>
              Open{' '}
              <a href='https://marketplace.zoho.com/' target='_blank' rel='noreferrer'>
                Zoho Marketplace
              </a>{' '}
              vendor console → submit a Zoho Recruit extension
            </li>
            <li>Upload the ZIP (or register the Widget URL if the form asks for external hosting)</li>
            <li>Fill listing: name, screenshots, privacy policy, support URL — see repo checklist</li>
            <li>Submit for Zoho review; after approval, customers Install from Marketplace</li>
            <li>Customer pastes Partner API key once in the widget, then Launch from Candidate</li>
          </ol>
          <div className='partners-warn'>
            Full submit checklist:{' '}
            <code>zoho-recruit-extension/MARKETPLACE_SUBMIT.md</code>. Do not use Setup → Functions / Deluge for this
            product path.
          </div>
          <div className='partners-btn-group'>
            <button type='button' className='partners-btn partners-btn-secondary' onClick={() => copyText(WIDGET_URL)}>
              Copy widget URL
            </button>
            <a className='partners-btn partners-btn-secondary' href={WIDGET_URL} target='_blank' rel='noreferrer'>
              Open widget
            </a>
            <a
              className='partners-btn partners-btn-secondary'
              href='https://marketplace.zoho.com/'
              target='_blank'
              rel='noreferrer'
            >
              Zoho Marketplace
            </a>
          </div>
        </section>
      ) : null}
    </div>
  )
}
