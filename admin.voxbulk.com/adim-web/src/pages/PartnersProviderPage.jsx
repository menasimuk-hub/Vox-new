import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { connectionBadge, getPartnerProvider, modeBadge } from '../lib/partnersCatalog'
import './partners.css'

const SETUP_STEPS = [
  'Register on partner portal',
  'Create sandbox credentials',
  'Map VoxBulk organisation',
  'Set result webhook URL',
  'Run test job (EN)',
  'Run test job (AR)',
  'Confirm webhook received',
  'Submit marketplace listing',
  'Generate live keys & switch to Live',
]

function copyText(text) {
  if (!text || !navigator?.clipboard) return
  navigator.clipboard.writeText(text).catch(() => {})
}

function ExtraFields({ provider, form, setForm }) {
  const kind = provider.extraFields
  if (kind === 'zoho') {
    return (
      <div className='partners-extra-block'>
        <div className='partners-extra-title'>Zoho-specific fields</div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>OAuth Client ID</span>
          <input
            className='partners-control'
            style={{ maxWidth: 320 }}
            value={form.clientId}
            onChange={(e) => setForm((f) => ({ ...f, clientId: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Client Secret</span>
          <input
            className='partners-control'
            type='password'
            style={{ maxWidth: 320 }}
            value={form.clientSecret}
            onChange={(e) => setForm((f) => ({ ...f, clientSecret: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Redirect URI</span>
          <span className='partners-readonly'>
            {form.redirectUri}
            <button type='button' className='partners-copy-btn' onClick={() => copyText(form.redirectUri)} title='Copy'>
              <i className='ti ti-copy' />
            </button>
          </span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Data centre</span>
          <select
            className='partners-control'
            style={{ maxWidth: 180 }}
            value={form.dataCentre}
            onChange={(e) => setForm((f) => ({ ...f, dataCentre: e.target.value }))}
          >
            <option value='US'>US</option>
            <option value='EU'>EU</option>
            <option value='IN'>IN</option>
            <option value='AU'>AU</option>
            <option value='UK'>UK</option>
            <option value='AE'>AE</option>
            <option value='SA'>SA</option>
          </select>
        </div>
      </div>
    )
  }
  if (kind === 'breezy') {
    return (
      <div className='partners-extra-block'>
        <div className='partners-extra-title'>Breezy-specific fields</div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Bearer token</span>
          <input
            className='partners-control'
            type='password'
            style={{ maxWidth: 320 }}
            value={form.bearerToken}
            onChange={(e) => setForm((f) => ({ ...f, bearerToken: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Company ID</span>
          <input
            className='partners-control'
            style={{ maxWidth: 220 }}
            value={form.companyId}
            onChange={(e) => setForm((f) => ({ ...f, companyId: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Webhook events</span>
          <span className='partners-field-value'>
            <label style={{ marginRight: 12 }}>
              <input type='checkbox' checked readOnly /> candidateAdded
            </label>
            <label>
              <input type='checkbox' checked readOnly /> candidateStatusUpdated
            </label>
          </span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Incoming webhook secret</span>
          <input
            className='partners-control'
            type='password'
            style={{ maxWidth: 280 }}
            value={form.webhookSecret}
            onChange={(e) => setForm((f) => ({ ...f, webhookSecret: e.target.value }))}
          />
        </div>
      </div>
    )
  }
  if (kind === 'workable') {
    return (
      <div className='partners-extra-block'>
        <div className='partners-extra-title'>Workable-specific fields</div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Partner token</span>
          <input
            className='partners-control'
            type='password'
            style={{ maxWidth: 320 }}
            value={form.partnerToken}
            onChange={(e) => setForm((f) => ({ ...f, partnerToken: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Client ID</span>
          <input
            className='partners-control'
            style={{ maxWidth: 280 }}
            value={form.workableClientId}
            onChange={(e) => setForm((f) => ({ ...f, workableClientId: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Subdomain</span>
          <input
            className='partners-control'
            style={{ maxWidth: 220 }}
            value={form.subdomain}
            onChange={(e) => setForm((f) => ({ ...f, subdomain: e.target.value }))}
          />
        </div>
      </div>
    )
  }
  if (kind === 'bullhorn') {
    return (
      <div className='partners-extra-block'>
        <div className='partners-extra-title'>Bullhorn-specific fields</div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Client ID</span>
          <input
            className='partners-control'
            style={{ maxWidth: 280 }}
            value={form.clientId}
            onChange={(e) => setForm((f) => ({ ...f, clientId: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Client Secret</span>
          <input
            className='partners-control'
            type='password'
            style={{ maxWidth: 280 }}
            value={form.clientSecret}
            onChange={(e) => setForm((f) => ({ ...f, clientSecret: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Corporation ID</span>
          <input
            className='partners-control'
            style={{ maxWidth: 200 }}
            value={form.corpId}
            onChange={(e) => setForm((f) => ({ ...f, corpId: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>AppBridge</span>
          <button
            type='button'
            className={`partners-toggle ${form.appBridge ? 'on' : ''}`}
            aria-pressed={form.appBridge}
            onClick={() => setForm((f) => ({ ...f, appBridge: !f.appBridge }))}
          />
        </div>
      </div>
    )
  }
  return (
    <div className='partners-extra-block'>
      <div className='partners-extra-title'>Zapier workflow</div>
      <div className='partners-field-row'>
        <span className='partners-field-label'>Trigger</span>
        <span className='partners-readonly'>New Candidate Received</span>
      </div>
      <div className='partners-field-row'>
        <span className='partners-field-label'>Action</span>
        <span className='partners-readonly'>Run AI Screening</span>
      </div>
      <div className='partners-field-row'>
        <span className='partners-field-label'>Result</span>
        <span className='partners-readonly'>Send Score/Status Back</span>
      </div>
      <div className='partners-field-row'>
        <span className='partners-field-label'>Zapier app URL</span>
        <input
          className='partners-control'
          style={{ maxWidth: 360 }}
          value={form.zapierUrl}
          onChange={(e) => setForm((f) => ({ ...f, zapierUrl: e.target.value }))}
          placeholder='https://zapier.com/apps/…'
        />
      </div>
    </div>
  )
}

function defaultForm(providerKey, commissionDefault) {
  return {
    mappedOrg: '',
    resultWebhook: '',
    webhookSecret: '',
    connectionFee: '1.50',
    perMinute: '0.35',
    commission: String(commissionDefault ?? 18),
    estCost: '5.00',
    clientId: '',
    clientSecret: '',
    redirectUri: `https://api.voxbulk.com/partner/v1/oauth/${providerKey}/callback`,
    dataCentre: 'US',
    bearerToken: '',
    companyId: '',
    partnerToken: '',
    workableClientId: '',
    subdomain: '',
    corpId: '',
    appBridge: false,
    zapierUrl: '',
    testLang: 'en',
    candidateName: '',
    phone: '',
    jobTitle: '',
    partnerRef: '',
    questions: '',
  }
}

function buildConfig(provider, form) {
  const kind = provider.extraFields
  if (kind === 'zoho') {
    return {
      client_id: form.clientId,
      client_secret: form.clientSecret,
      redirect_uri: form.redirectUri,
      data_centre: form.dataCentre,
    }
  }
  if (kind === 'breezy') {
    return {
      bearer_token: form.bearerToken,
      company_id: form.companyId,
      inbound_webhook_secret: form.webhookSecret,
    }
  }
  if (kind === 'workable') {
    return {
      partner_token: form.partnerToken,
      client_id: form.workableClientId,
      subdomain: form.subdomain,
    }
  }
  if (kind === 'bullhorn') {
    return {
      client_id: form.clientId,
      client_secret: form.clientSecret,
      corporation_id: form.corpId,
      app_bridge: !!form.appBridge,
    }
  }
  return { zapier_url: form.zapierUrl }
}

export default function PartnersProviderPage() {
  const { providerKey } = useParams()
  const provider = getPartnerProvider(providerKey)

  const [enabled, setEnabled] = useState(false)
  const [mode, setMode] = useState('sandbox')
  const [connection, setConnection] = useState('none')
  const [checked, setChecked] = useState(() => SETUP_STEPS.map(() => false))
  const [testResult, setTestResult] = useState(null)
  const [savedFlash, setSavedFlash] = useState('')
  const [keys, setKeys] = useState([])
  const [recentJobs, setRecentJobs] = useState([])
  const [revealedKey, setRevealedKey] = useState(null)
  const [lastHealth, setLastHealth] = useState(null)
  const [orgOptions, setOrgOptions] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const inboundUrl = `https://api.voxbulk.com/partner/v1/screenings`
  const healthUrl = `https://api.voxbulk.com/partner/v1/health`

  const [form, setForm] = useState(() => defaultForm(providerKey, provider?.commissionDefault))

  const flash = useCallback((msg) => {
    setSavedFlash(msg)
    window.setTimeout(() => setSavedFlash(''), 3500)
  }, [])

  const applyProviderPayload = useCallback(
    (data) => {
      const p = data?.provider || {}
      const cfg = p.config || {}
      setEnabled(!!p.enabled)
      setMode(p.mode || 'sandbox')
      setKeys(data?.keys || [])
      setRecentJobs(data?.recent_jobs || [])
      setLastHealth(
        p.last_health_at
          ? { at: p.last_health_at, ok: p.last_health_ok, message: p.last_health_message }
          : null,
      )
      const hasActive = (data?.keys || []).some((k) => k.is_active)
      if (p.last_health_ok === false) setConnection('error')
      else if (p.enabled && hasActive && p.mapped_org_id) setConnection(p.mode === 'live' ? 'connected' : 'sandbox')
      else setConnection('none')

      setForm((prev) => ({
        ...prev,
        mappedOrg: p.mapped_org_id || '',
        resultWebhook: p.result_webhook_url || '',
        webhookSecret: '',
        connectionFee: String(p.connection_fee_gbp ?? 1.5),
        perMinute: String(p.per_minute_gbp ?? 0.35),
        commission: String(p.commission_pct ?? provider?.commissionDefault ?? 18),
        estCost: String(p.est_cost_per_completed_gbp ?? 5),
        clientId: cfg.client_id || '',
        clientSecret: cfg.client_secret || '',
        redirectUri: cfg.redirect_uri || `https://api.voxbulk.com/partner/v1/oauth/${provider.key}/callback`,
        dataCentre: cfg.data_centre || 'US',
        bearerToken: cfg.bearer_token || '',
        companyId: cfg.company_id || '',
        partnerToken: cfg.partner_token || '',
        workableClientId: cfg.client_id || '',
        subdomain: cfg.subdomain || '',
        corpId: cfg.corporation_id || '',
        appBridge: !!cfg.app_bridge,
        zapierUrl: cfg.zapier_url || '',
      }))
    },
    [provider],
  )

  const load = useCallback(async () => {
    if (!provider) return
    setLoading(true)
    try {
      const [data, orgs] = await Promise.all([
        apiFetch(`/admin/partners/${provider.key}`),
        apiFetch('/admin/partners/org-options').catch(() => ({ items: [] })),
      ])
      applyProviderPayload(data)
      setOrgOptions(orgs?.items || [])
    } catch (e) {
      flash(e?.message || 'Failed to load provider')
    } finally {
      setLoading(false)
    }
  }, [provider, applyProviderPayload, flash])

  useEffect(() => {
    if (!provider) return
    setChecked(SETUP_STEPS.map(() => false))
    setTestResult(null)
    setRevealedKey(null)
    setForm(defaultForm(provider.key, provider.commissionDefault))
    load()
  }, [provider?.key]) // eslint-disable-line react-hooks/exhaustive-deps

  const sharePct = useMemo(() => {
    const c = Number(form.commission) || 0
    return Math.max(0, 100 - c)
  }, [form.commission])

  if (!provider) {
    return <Navigate to='/partners/dashboard' replace />
  }

  const conn = connectionBadge(connection)
  const modeB = modeBadge(mode)

  const keyMeta = (environment) => {
    const active = keys.find((k) => k.environment === environment && k.is_active)
    if (!active) return 'Not generated'
    if (revealedKey?.environment === environment) return revealedKey.api_key
    return `${active.key_prefix}… (active)`
  }

  const onSave = async () => {
    setBusy(true)
    try {
      const body = {
        enabled,
        mode,
        mapped_org_id: form.mappedOrg || null,
        result_webhook_url: form.resultWebhook || '',
        connection_fee_gbp: Number(form.connectionFee) || 1.5,
        per_minute_gbp: Number(form.perMinute) || 0.35,
        commission_pct: Number(form.commission) || 0,
        est_cost_per_completed_gbp: Number(form.estCost) || 5,
        config: buildConfig(provider, form),
      }
      if (form.webhookSecret) body.webhook_secret = form.webhookSecret
      const data = await apiFetch(`/admin/partners/${provider.key}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      })
      applyProviderPayload(data)
      flash('Saved')
    } catch (e) {
      flash(e?.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const onPing = async () => {
    setBusy(true)
    try {
      const res = await apiFetch(`/admin/partners/${provider.key}/health`, { method: 'POST' })
      setLastHealth({ at: res.checked_at, ok: res.ok, message: res.message })
      flash(res.message || (res.ok ? 'Health OK' : 'Health failed'))
      await load()
    } catch (e) {
      flash(e?.message || 'Health check failed')
    } finally {
      setBusy(false)
    }
  }

  const onGenerateKey = async (environment) => {
    setBusy(true)
    try {
      const res = await apiFetch(`/admin/partners/${provider.key}/keys?environment=${environment}`, {
        method: 'POST',
      })
      setRevealedKey({ environment, api_key: res.api_key })
      flash(`${environment} key generated — copy it now`)
      await load()
    } catch (e) {
      flash(e?.message || 'Key generation failed')
    } finally {
      setBusy(false)
    }
  }

  const onSendTest = async () => {
    setBusy(true)
    setTestResult(null)
    try {
      const questions = String(form.questions || '')
        .split('\n')
        .map((q) => q.trim())
        .filter(Boolean)
      const partnerRef = form.partnerRef || `test-${Date.now()}`
      const data = await apiFetch(`/admin/partners/${provider.key}/test-screening`, {
        method: 'POST',
        body: JSON.stringify({
          partner_reference_id: partnerRef,
          job_title: form.jobTitle || 'Test role',
          screening_questions: questions,
          candidate_name: form.candidateName || 'Test Candidate',
          candidate_phone: form.phone || '+447700900000',
          preferred_language: form.testLang || 'en',
          callback_url: form.resultWebhook || undefined,
        }),
      })
      setTestResult({
        status: data.status || 'accepted',
        link: data.screening_link,
        eta: `${data.estimated_completion_minutes || 15} min`,
      })
      flash('Test screening accepted')
      await load()
    } catch (e) {
      flash(e?.message || 'Test job failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='partners-page'>
      <Link className='partners-back' to='/partners/dashboard'>
        <i className='ti ti-arrow-left' /> Provider Dashboard
      </Link>

      <div className='partners-header'>
        <div>
          <h1>{provider.label}</h1>
          <div className='partners-sub'>Configure keys, webhooks, pricing, and sandbox tests</div>
        </div>
      </div>

      <div className='partners-status-row'>
        <span className={`partners-badge ${conn.cls}`}>{conn.text}</span>
        <span className={`partners-badge ${modeB.cls}`}>{modeB.text}</span>
        {savedFlash ? <span className='partners-helper'>{savedFlash}</span> : null}
        {loading ? <span className='partners-helper'>Loading…</span> : null}
        <span className='partners-tagline'>Dual English + Arabic AI voice screening</span>
      </div>

      <section className='partners-section'>
        <h3>A · Connection &amp; Mode</h3>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Enabled</span>
          <button
            type='button'
            className={`partners-toggle ${enabled ? 'on' : ''}`}
            aria-pressed={enabled}
            onClick={() => setEnabled((v) => !v)}
          />
          <span className='partners-field-value'>{enabled ? 'On' : 'Off'}</span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Mode</span>
          <select
            className='partners-control'
            style={{ maxWidth: 180 }}
            value={mode || 'sandbox'}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value='sandbox'>Sandbox</option>
            <option value='live'>Live</option>
          </select>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Connection</span>
          <span className={`partners-badge ${conn.cls}`}>{conn.text}</span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Last health check</span>
          <span className='partners-field-value'>
            {lastHealth
              ? `${lastHealth.ok ? 'OK' : 'Fail'} · ${lastHealth.message || ''} · ${lastHealth.at || ''}`
              : '—'}
          </span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Mapped org</span>
          {orgOptions.length ? (
            <select
              className='partners-control'
              style={{ maxWidth: 320 }}
              value={form.mappedOrg}
              onChange={(e) => setForm((f) => ({ ...f, mappedOrg: e.target.value }))}
            >
              <option value=''>Select organisation…</option>
              {orgOptions.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name} ({o.id.slice(0, 8)}…)
                </option>
              ))}
            </select>
          ) : (
            <input
              className='partners-control'
              style={{ maxWidth: 280 }}
              placeholder='Organisation ID'
              value={form.mappedOrg}
              onChange={(e) => setForm((f) => ({ ...f, mappedOrg: e.target.value }))}
            />
          )}
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Developer portal</span>
          <a href={provider.portalUrl} target='_blank' rel='noreferrer' style={{ color: '#2563eb' }}>
            {provider.portalUrl}
          </a>
        </div>
        <div className='partners-btn-group'>
          <button type='button' className='partners-btn partners-btn-primary' onClick={onSave} disabled={busy}>
            <i className='ti ti-device-floppy' /> Save
          </button>
          <button type='button' className='partners-btn partners-btn-secondary' onClick={onPing} disabled={busy}>
            <i className='ti ti-heartbeat' /> Ping health
          </button>
        </div>
      </section>

      <section className='partners-section'>
        <h3>B · API Credentials</h3>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Partner name</span>
          <span className='partners-readonly'>{provider.partnerNameHeader}</span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Sandbox API key</span>
          <span className='partners-readonly'>
            {keyMeta('sandbox')}
            {revealedKey?.environment === 'sandbox' ? (
              <button type='button' className='partners-copy-btn' onClick={() => copyText(revealedKey.api_key)} title='Copy'>
                <i className='ti ti-copy' />
              </button>
            ) : null}
          </span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Live API key</span>
          <span className='partners-readonly'>
            {keyMeta('live')}
            {revealedKey?.environment === 'live' ? (
              <button type='button' className='partners-copy-btn' onClick={() => copyText(revealedKey.api_key)} title='Copy'>
                <i className='ti ti-copy' />
              </button>
            ) : null}
          </span>
        </div>
        <div className='partners-btn-group'>
          <button type='button' className='partners-btn partners-btn-secondary' disabled={busy} onClick={() => onGenerateKey('sandbox')}>
            <i className='ti ti-key' /> Generate sandbox
          </button>
          <button type='button' className='partners-btn partners-btn-secondary' disabled={busy} onClick={() => onGenerateKey('sandbox')}>
            <i className='ti ti-refresh' /> Rotate sandbox
          </button>
          <button type='button' className='partners-btn partners-btn-secondary' disabled={busy} onClick={() => onGenerateKey('live')}>
            <i className='ti ti-key' /> Generate live
          </button>
          <button type='button' className='partners-btn partners-btn-secondary' disabled={busy} onClick={() => onGenerateKey('live')}>
            <i className='ti ti-refresh' /> Rotate live
          </button>
        </div>
        <div className='partners-warn'>
          Keys shown once. Send as headers <strong>X-API-Key</strong> + <strong>X-Partner-Name</strong>.
        </div>
      </section>

      <section className='partners-section'>
        <h3>C · Webhooks &amp; Endpoints</h3>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Inbound receive URL</span>
          <span className='partners-readonly'>
            {inboundUrl}
            <button type='button' className='partners-copy-btn' onClick={() => copyText(inboundUrl)} title='Copy'>
              <i className='ti ti-copy' />
            </button>
          </span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Result webhook (outbound)</span>
          <input
            className='partners-control'
            style={{ maxWidth: 400 }}
            value={form.resultWebhook}
            onChange={(e) => setForm((f) => ({ ...f, resultWebhook: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Webhook secret</span>
          <input
            className='partners-control'
            type='password'
            style={{ maxWidth: 260 }}
            value={form.webhookSecret}
            onChange={(e) => setForm((f) => ({ ...f, webhookSecret: e.target.value }))}
            placeholder='Leave blank to keep existing'
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Health URL</span>
          <span className='partners-readonly'>
            {healthUrl}
            <button type='button' className='partners-copy-btn' onClick={() => copyText(healthUrl)} title='Copy'>
              <i className='ti ti-copy' />
            </button>
          </span>
        </div>
        <div className='partners-helper'>
          <i className='ti ti-info-circle' /> Auth: X-API-Key + X-Partner-Name
        </div>
        <ExtraFields provider={provider} form={form} setForm={setForm} />
      </section>

      <section className='partners-section'>
        <h3>D · Pricing &amp; commission</h3>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Connection fee (£)</span>
          <input
            className='partners-control'
            style={{ maxWidth: 120 }}
            value={form.connectionFee}
            onChange={(e) => setForm((f) => ({ ...f, connectionFee: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Per-minute rate (£)</span>
          <input
            className='partners-control'
            style={{ maxWidth: 120 }}
            value={form.perMinute}
            onChange={(e) => setForm((f) => ({ ...f, perMinute: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Platform commission %</span>
          <input
            className='partners-control'
            style={{ maxWidth: 100 }}
            value={form.commission}
            onChange={(e) => setForm((f) => ({ ...f, commission: e.target.value }))}
          />
          <span className='partners-helper'>
            {provider.short} default {provider.commissionDefault}%
          </span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Your share %</span>
          <span className='partners-field-value'>
            <strong>{sharePct}%</strong> (100 − commission)
          </span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Est. cost per completed</span>
          <input
            className='partners-control'
            style={{ maxWidth: 120 }}
            value={form.estCost}
            onChange={(e) => setForm((f) => ({ ...f, estCost: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Average price hint</span>
          <span className='partners-readonly'>Typical £7–£9</span>
        </div>
        <div className='partners-callout'>
          <i className='ti ti-speakerphone' style={{ color: '#2563eb' }} /> “Dual English + Arabic AI voice screening
          for UK and Middle East hiring.”
        </div>
      </section>

      <section className='partners-section'>
        <h3>E · Setup guide</h3>
        <div className='partners-checklist'>
          {SETUP_STEPS.map((step, i) => (
            <label key={step}>
              <input
                type='checkbox'
                checked={checked[i]}
                onChange={() =>
                  setChecked((prev) => {
                    const next = [...prev]
                    next[i] = !next[i]
                    return next
                  })
                }
              />
              <span>
                {i + 1}. {step}
              </span>
            </label>
          ))}
        </div>
        <div className='partners-tip'>
          <strong>How to test</strong>
          <ul>
            <li>Enable partner, map org, Save</li>
            <li>Generate sandbox key (copy once)</li>
            <li>Set Mode to Sandbox and Ping health</li>
            <li>Send a test job below</li>
          </ul>
        </div>
      </section>

      <section className='partners-section'>
        <h3>F · Test panel</h3>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Test language</span>
          <select
            className='partners-control'
            style={{ maxWidth: 120 }}
            value={form.testLang}
            onChange={(e) => setForm((f) => ({ ...f, testLang: e.target.value }))}
          >
            <option value='en'>en</option>
            <option value='ar'>ar</option>
          </select>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Candidate name</span>
          <input
            className='partners-control'
            style={{ maxWidth: 240 }}
            value={form.candidateName}
            onChange={(e) => setForm((f) => ({ ...f, candidateName: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Phone (E.164)</span>
          <input
            className='partners-control'
            style={{ maxWidth: 240 }}
            value={form.phone}
            onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Job title</span>
          <input
            className='partners-control'
            style={{ maxWidth: 280 }}
            value={form.jobTitle}
            onChange={(e) => setForm((f) => ({ ...f, jobTitle: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Partner ref ID</span>
          <input
            className='partners-control'
            style={{ maxWidth: 220 }}
            value={form.partnerRef}
            onChange={(e) => setForm((f) => ({ ...f, partnerRef: e.target.value }))}
          />
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Questions</span>
          <textarea
            className='partners-control'
            rows={3}
            style={{ minWidth: 280 }}
            value={form.questions}
            onChange={(e) => setForm((f) => ({ ...f, questions: e.target.value }))}
            placeholder='One question per line'
          />
        </div>
        <div className='partners-btn-group'>
          <button type='button' className='partners-btn partners-btn-primary' onClick={onSendTest} disabled={busy}>
            <i className='ti ti-send' /> Send test job
          </button>
          <a className='partners-btn partners-btn-secondary' href={healthUrl} target='_blank' rel='noreferrer'>
            <i className='ti ti-external-link' /> Health URL
          </a>
        </div>
        {testResult ? (
          <div className='partners-test-result'>
            <span className='partners-badge partners-badge-green'>● {testResult.status}</span>
            <span style={{ marginLeft: 12 }}>
              Screening link:{' '}
              <a href={testResult.link} style={{ color: '#2563eb' }}>
                {testResult.link}
              </a>
            </span>
            <div style={{ marginTop: 6, fontSize: 13 }}>Est. completion: {testResult.eta}</div>
          </div>
        ) : null}
      </section>

      <section className='partners-section'>
        <h3>G · Recent jobs</h3>
        {recentJobs.length === 0 ? (
          <div className='partners-footer-note' style={{ marginTop: 0 }}>
            No jobs yet. Rows appear here when this provider sends candidates through the Partner API.
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
                  <th>Charge</th>
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
                    <td>{j.total_charge_gbp != null ? `£${Number(j.total_charge_gbp).toFixed(2)}` : '—'}</td>
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
