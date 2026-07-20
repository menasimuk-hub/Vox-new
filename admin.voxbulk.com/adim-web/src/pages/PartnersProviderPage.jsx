import React, { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import {
  DEMO_PARTNER_KPI,
  connectionBadge,
  getPartnerProvider,
  modeBadge,
} from '../lib/partnersCatalog'
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

export default function PartnersProviderPage() {
  const { providerKey } = useParams()
  const provider = getPartnerProvider(providerKey)
  const kpi = DEMO_PARTNER_KPI.rows.find((r) => r.key === provider?.key)

  const [enabled, setEnabled] = useState(true)
  const [mode, setMode] = useState(kpi?.mode || 'sandbox')
  const [checked, setChecked] = useState(() => SETUP_STEPS.map(() => false))
  const [testResult, setTestResult] = useState(null)
  const [savedFlash, setSavedFlash] = useState('')

  const inboundUrl = `https://api.voxbulk.com/partner/v1/screenings`
  const healthUrl = `https://api.voxbulk.com/partner/v1/health`
  const redirectUri = `https://api.voxbulk.com/partner/v1/oauth/${providerKey}/callback`

  const [form, setForm] = useState(() => ({
    mappedOrg: 'VoxBulk UK',
    resultWebhook: `https://partner.example.com/webhooks/voxbulk`,
    webhookSecret: '',
    connectionFee: '1.50',
    perMinute: '0.35',
    commission: String(provider?.commissionDefault ?? 18),
    estCost: '5.00',
    clientId: `${providerKey || 'partner'}_client_abc`,
    clientSecret: '',
    redirectUri,
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
    candidateName: 'Sarah Ahmed',
    phone: '+447700900123',
    jobTitle: 'Customer support agent',
    partnerRef: `${String(providerKey || 'P').toUpperCase()}-TEST-001`,
    questions: 'Tell me about your experience with CRM?\nHow do you handle pressure?',
  }))

  useEffect(() => {
    if (!provider) return
    setEnabled(true)
    setMode(kpi?.mode || 'sandbox')
    setChecked(SETUP_STEPS.map(() => false))
    setTestResult(null)
    setForm({
      mappedOrg: 'VoxBulk UK',
      resultWebhook: 'https://partner.example.com/webhooks/voxbulk',
      webhookSecret: '',
      connectionFee: '1.50',
      perMinute: '0.35',
      commission: String(provider.commissionDefault ?? 18),
      estCost: '5.00',
      clientId: `${provider.key}_client_abc`,
      clientSecret: '',
      redirectUri: `https://api.voxbulk.com/partner/v1/oauth/${provider.key}/callback`,
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
      candidateName: 'Sarah Ahmed',
      phone: '+447700900123',
      jobTitle: 'Customer support agent',
      partnerRef: `${provider.short.toUpperCase()}-TEST-001`,
      questions: 'Tell me about your experience with CRM?\nHow do you handle pressure?',
    })
  }, [provider?.key])

  const sharePct = useMemo(() => {
    const c = Number(form.commission) || 0
    return Math.max(0, 100 - c)
  }, [form.commission])

  if (!provider) {
    return <Navigate to='/partners/dashboard' replace />
  }

  const conn = connectionBadge(kpi?.connection || 'none')
  const modeB = modeBadge(mode === '—' ? null : mode)

  const flash = (msg) => {
    setSavedFlash(msg)
    window.setTimeout(() => setSavedFlash(''), 2500)
  }

  const onSave = () => flash('Settings saved locally (API wiring comes next).')
  const onPing = () => flash('Health ping: OK (demo).')
  const onSendTest = () => {
    setTestResult({
      status: 'Accepted',
      link: 'https://screening.voxbulk.com/demo-abc123',
      eta: '4 min',
    })
    flash('Test job accepted (demo).')
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
        <span className='partners-tagline'>Dual English + Arabic AI voice screening</span>
      </div>

      {/* A */}
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
          <span className='partners-field-value'>—</span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Mapped org</span>
          <select
            className='partners-control'
            style={{ maxWidth: 240 }}
            value={form.mappedOrg}
            onChange={(e) => setForm((f) => ({ ...f, mappedOrg: e.target.value }))}
          >
            <option>VoxBulk UK</option>
            <option>VoxBulk ME</option>
          </select>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Developer portal</span>
          <a href={provider.portalUrl} target='_blank' rel='noreferrer' style={{ color: '#2563eb' }}>
            {provider.portalUrl}
          </a>
        </div>
        <div className='partners-btn-group'>
          <button type='button' className='partners-btn partners-btn-primary' onClick={onSave}>
            <i className='ti ti-device-floppy' /> Save
          </button>
          <button type='button' className='partners-btn partners-btn-secondary' onClick={onPing}>
            <i className='ti ti-heartbeat' /> Ping health
          </button>
        </div>
      </section>

      {/* B */}
      <section className='partners-section'>
        <h3>B · API Credentials</h3>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Partner name</span>
          <span className='partners-readonly'>{provider.partnerNameHeader}</span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Sandbox API key</span>
          <span className='partners-readonly'>•••••••••••• (generate to reveal)</span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Live API key</span>
          <span className='partners-readonly'>•••••••••••• (generate to reveal)</span>
        </div>
        <div className='partners-btn-group'>
          <button type='button' className='partners-btn partners-btn-secondary' onClick={() => flash('Sandbox key generation needs Partner API.')}>
            <i className='ti ti-key' /> Generate sandbox
          </button>
          <button type='button' className='partners-btn partners-btn-secondary' onClick={() => flash('Rotate sandbox needs Partner API.')}>
            <i className='ti ti-refresh' /> Rotate sandbox
          </button>
          <button type='button' className='partners-btn partners-btn-secondary' onClick={() => flash('Live key generation needs Partner API.')}>
            <i className='ti ti-key' /> Generate live
          </button>
          <button type='button' className='partners-btn partners-btn-secondary' onClick={() => flash('Rotate live needs Partner API.')}>
            <i className='ti ti-refresh' /> Rotate live
          </button>
        </div>
        <div className='partners-warn'>
          Keys shown once. Send as headers <strong>X-API-Key</strong> + <strong>X-Partner-Name</strong>.
        </div>
      </section>

      {/* C */}
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

      {/* D */}
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

      {/* E */}
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
            <li>Use sandbox keys and set Mode to Sandbox</li>
            <li>Send a test job with sample candidate data</li>
            <li>Verify the result webhook is called</li>
            <li>Check the report in Recent jobs</li>
          </ul>
        </div>
      </section>

      {/* F */}
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
          <span className='partners-helper'>auto-generate later</span>
        </div>
        <div className='partners-field-row'>
          <span className='partners-field-label'>Questions</span>
          <textarea
            className='partners-control'
            rows={3}
            style={{ minWidth: 280 }}
            value={form.questions}
            onChange={(e) => setForm((f) => ({ ...f, questions: e.target.value }))}
          />
        </div>
        <div className='partners-btn-group'>
          <button type='button' className='partners-btn partners-btn-primary' onClick={onSendTest}>
            <i className='ti ti-send' /> Send test job
          </button>
          <button type='button' className='partners-btn partners-btn-secondary' onClick={() => flash('Simulate webhook (demo).')}>
            <i className='ti ti-refresh' /> Simulate webhook
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

      {/* G */}
      <section className='partners-section'>
        <h3>G · Recent jobs</h3>
        <div className='partners-footer-note' style={{ marginBottom: 12, marginTop: 0 }}>
          Job history will appear here once the Partner API ledger is connected. Demo rows below.
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className='partners-mini-table'>
            <thead>
              <tr>
                <th>Ref ID</th>
                <th>Job</th>
                <th>Candidate</th>
                <th>Lang</th>
                <th>Status</th>
                <th>Score</th>
                <th>Charge</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{provider.short.toUpperCase()}-101</td>
                <td>Support agent</td>
                <td>Sarah Ahmed</td>
                <td>
                  <span className='partners-badge partners-badge-green'>en</span>
                </td>
                <td>
                  <span className='partners-badge partners-badge-green'>Passed</span>
                </td>
                <td>87</td>
                <td>£7.80</td>
              </tr>
              <tr>
                <td>{provider.short.toUpperCase()}-102</td>
                <td>Sales rep</td>
                <td>Mohammed Al-Fahd</td>
                <td>
                  <span className='partners-badge partners-badge-amber'>ar</span>
                </td>
                <td>
                  <span className='partners-badge partners-badge-amber'>Review</span>
                </td>
                <td>64</td>
                <td>£8.50</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
