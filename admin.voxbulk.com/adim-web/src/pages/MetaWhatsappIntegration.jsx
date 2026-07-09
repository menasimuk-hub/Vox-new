import React from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft,
  Check,
  Copy,
  Info,
  Inbox,
  KeyRound,
  MessageSquare,
  Plug,
  RefreshCw,
  Save,
  ShieldCheck,
} from 'lucide-react'
import '../styles/telnyx-settings-hub.css'

const invalidInputStyle = { borderColor: 'rgba(220,38,38,0.85)' }

function statusPill(summary) {
  if (!summary) return { cls: 'p-amber', text: 'Loading' }
  if (summary.error) return { cls: 'p-red', text: 'Auth / error' }
  if (!summary.exists) return { cls: 'p-amber', text: 'Not set' }
  if (!summary.is_enabled) return { cls: 'p-amber', text: 'Disabled' }
  if (summary.configured) return { cls: 'p-green', text: 'Configured' }
  return { cls: 'p-amber', text: 'Incomplete' }
}

function copyText(value) {
  const text = String(value || '')
  if (!text) return
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).catch(() => {})
  }
}

function Field({ label, hint, error, children }) {
  return (
    <div className='telnyxField'>
      <label className='label'>{label}</label>
      {children}
      {error ? <div className='muted telnyxFieldError'>{error}</div> : null}
      {hint ? <div className='muted telnyxFieldHint'>{hint}</div> : null}
    </div>
  )
}

function CopyInline({ value }) {
  const [copied, setCopied] = React.useState(false)
  const text = String(value || '')
  return (
    <button
      type='button'
      className='tsh-copy-inline'
      onClick={() => {
        copyText(text)
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1500)
      }}
      disabled={!text}
    >
      <code>{text || '—'}</code>
      {copied ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}
    </button>
  )
}

const META_TABS = [
  { id: 'credentials', label: 'Meta credentials', icon: KeyRound },
  { id: 'webhooks', label: 'Webhooks', icon: ShieldCheck },
  { id: 'messages', label: 'Messages', icon: Inbox },
  { id: 'test', label: 'Test send', icon: MessageSquare },
]

function fmtTime(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

function messageStatusClass(status) {
  const s = String(status || '').toLowerCase()
  if (s.includes('fail') || s.includes('error')) return 'p-red'
  if (s.includes('deliver') || s === 'sent' || s === 'received') return 'p-green'
  return 'p-amber'
}

export default function MetaWhatsappIntegration({
  activeSummary,
  activeConfig,
  activeDraft,
  activeEnabled,
  metaStatus,
  metaWebhookUrl,
  metaTestResult,
  metaSendResult,
  metaTemplates,
  metaTemplatesBusy,
  metaProbeResult,
  metaTestNumber,
  setMetaTestNumber,
  metaTemplateName,
  setMetaTemplateName,
  metaTemplateLang,
  setMetaTemplateLang,
  providerError,
  providerSaving,
  defaultWebhookBase,
  setProviderEnabled,
  setProviderField,
  setProviderDrafts,
  saveIntegrationProvider,
  testMetaConnection,
  probeMetaWebhook,
  loadMetaTemplates,
  testMetaSend,
  metaInboundMessages,
  metaMessageFilters,
  setMetaMessageFilters,
  loadMetaInboundMessages,
  syncMetaWhatsappTemplates,
  metaWaSyncBusy,
  metaWaSyncResult,
}) {
  const pill = statusPill(activeSummary)
  const [activeTab, setActiveTab] = React.useState('credentials')

  const secretFields = [
    { key: 'access_token', label: 'Permanent access token', draftKey: 'access_token_draft', info: 'System user token from Meta Business settings (Never expire).' },
    { key: 'app_secret', label: 'App secret', draftKey: 'app_secret_draft', info: 'Meta Developer app → App settings → Basic → App Secret.' },
    { key: 'webhook_verify_token', label: 'Webhook verify token', draftKey: 'webhook_verify_token_draft', info: 'Same string you enter in Meta → WhatsApp → Configuration → Verify token.' },
  ]

  const idFields = [
    { key: 'app_id', label: 'App ID', info: 'Meta Developer app ID (VOXBULK).' },
    { key: 'waba_id', label: 'WhatsApp Business Account ID', info: 'WABA ID, e.g. 1033532842963987.' },
    { key: 'phone_number_id', label: 'Phone number ID', info: 'Cloud API phone number ID (not the +44 E.164).' },
    { key: 'whatsapp_from', label: 'WhatsApp from number', info: 'Display E.164, e.g. +447822002055.' },
    { key: 'graph_api_version', label: 'Graph API version', info: 'Default v25.0 — change when Meta upgrades.' },
    { key: 'default_messaging_org_id', label: 'Default messaging org ID', info: 'Optional org UUID for inbound WhatsApp logs.' },
  ]

  return (
    <div className='telnyxHub'>
      <div className='tsh-header'>
        <div className='tsh-header-main'>
          <Link to='/integrations/kpi' className='tsh-back'>
            <ArrowLeft size={16} aria-hidden /> Integrations
          </Link>
          <div className='tsh-title-row'>
            <Plug size={22} aria-hidden className='tsh-title-icon' />
            <div>
              <h1>Meta WhatsApp</h1>
              <p className='tsh-subtitle'>Direct Cloud API · surveys · feedback · templates</p>
            </div>
          </div>
          <div className='tsh-header-meta'>
            <span className={`pill ${pill.cls}`}>{pill.text}</span>
            <label className='tsh-enable-toggle'>
              <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('meta_whatsapp', e.target.checked)} />
              <span>Enabled</span>
            </label>
          </div>
        </div>
        <div className='tsh-header-actions'>
          <button type='button' className='tsh-btn tsh-btn-outline' onClick={testMetaConnection}>
            <RefreshCw size={14} aria-hidden /> Test connection
          </button>
          <button type='button' className='tsh-btn tsh-btn-primary' onClick={() => saveIntegrationProvider('meta_whatsapp')} disabled={providerSaving}>
            <Save size={14} aria-hidden /> {providerSaving ? 'Saving…' : 'Save Meta WhatsApp'}
          </button>
        </div>
      </div>

      {!metaStatus.valid && Object.keys(metaStatus.errors).length ? (
        <div className='tsh-banner tsh-banner-info'>
          <Info size={14} aria-hidden />{' '}
          Complete before save: {Object.values(metaStatus.errors).join(' · ')}
        </div>
      ) : null}
      {providerError ? (
        <div className='tsh-banner tsh-banner-danger'>
          <Info size={14} aria-hidden /> {providerError}
        </div>
      ) : null}
      {metaTestResult ? (
        <div className={`tsh-banner ${metaTestResult.ok ? 'tsh-banner-success' : 'tsh-banner-danger'}`}>
          {metaTestResult.detail || metaTestResult.message || JSON.stringify(metaTestResult)}
        </div>
      ) : null}

      <div className='tsh-tabs'>
        {META_TABS.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              type='button'
              className={`tsh-tab ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <Icon size={15} aria-hidden /> {tab.label}
            </button>
          )
        })}
      </div>

      {activeTab === 'credentials' ? (
        <div className='stack' style={{ gap: 20 }}>
          <div className='card'>
            <div className='cardHead'>
              <div className='cardHeadText'>
                <h3>Secrets</h3>
                <p className='cardSub'>Encrypted at rest — never returned after save</p>
              </div>
              <span className='pill p-cyan'>Encrypted</span>
            </div>
            <div className='cardBody stack'>
              {secretFields.map((f) => (
                <Field
                  key={f.key}
                  label={f.label}
                  hint={f.info}
                  error={metaStatus.errors[f.key]}
                >
                  <input
                    className='input'
                    type='password'
                    style={metaStatus.errors[f.key] ? invalidInputStyle : undefined}
                    value={String(activeDraft[f.draftKey] || '')}
                    onChange={(e) =>
                      setProviderDrafts((s) => ({
                        ...s,
                        meta_whatsapp: { ...(s.meta_whatsapp || {}), [f.draftKey]: e.target.value },
                      }))
                    }
                    placeholder={activeSummary?.secret_set?.[f.key] ? 'Leave blank to keep current' : `Paste ${f.label.toLowerCase()}`}
                  />
                </Field>
              ))}
            </div>
          </div>

          <div className='card'>
            <div className='cardHead'>
              <div className='cardHeadText'>
                <h3>IDs &amp; API</h3>
                <p className='cardSub'>Safe to change when you migrate WABA or phone number</p>
              </div>
            </div>
            <div className='cardBody stack'>
              {idFields.map((f) => (
                <Field key={f.key} label={f.label} hint={f.info} error={metaStatus.errors[f.key]}>
                  <input
                    className='input'
                    style={metaStatus.errors[f.key] ? invalidInputStyle : undefined}
                    value={String(activeConfig[f.key] || (f.key === 'graph_api_version' ? 'v25.0' : ''))}
                    onChange={(e) => setProviderField('meta_whatsapp', f.key, e.target.value)}
                  />
                </Field>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      {activeTab === 'webhooks' ? (
        <div className='card'>
          <div className='cardHead'>
            <div className='cardHeadText'>
              <h3>Webhooks</h3>
              <p className='cardSub'>Paste into Meta Developer → WhatsApp → Configuration</p>
            </div>
            <span className='pill p-cyan'>Public URL</span>
          </div>
          <div className='cardBody stack'>
            <Field
              label='Webhook base URL'
              error={metaStatus.errors.webhook_base_url}
              hint='Production API host or ngrok https URL (no path). Example: https://api.voxbulk.com'
            >
              <input
                className='input'
                style={metaStatus.errors.webhook_base_url ? invalidInputStyle : undefined}
                value={String(activeConfig.webhook_base_url || defaultWebhookBase || 'https://api.voxbulk.com')}
                onChange={(e) => setProviderField('meta_whatsapp', 'webhook_base_url', e.target.value)}
              />
            </Field>
            <div className='tableWrap'>
              <table className='table'>
                <thead>
                  <tr>
                    <th style={{ width: '34%' }}>Endpoint</th>
                    <th>URL</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong style={{ fontWeight: 500 }}>WhatsApp inbound + status</strong></td>
                    <td><CopyInline value={metaWebhookUrl} /></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className='muted telnyxFieldHint'>
              Subscribe to <strong>messages</strong> and <strong>message_template_status_update</strong> in Meta.
              Telnyx handles SMS and voice only — do not paste this URL into Telnyx.
            </div>
            <div className='actions'>
              <button type='button' className='btn soft' onClick={probeMetaWebhook}>
                Probe webhook verify
              </button>
            </div>
            {metaProbeResult ? (
              <div className={`note ${metaProbeResult.ok ? '' : ''}`} style={metaProbeResult.ok ? undefined : { borderColor: 'rgba(220,38,38,0.35)' }}>
                {metaProbeResult.ok ? 'Webhook verify OK' : 'Webhook verify failed'} — HTTP {metaProbeResult.status_code}
                {metaProbeResult.body ? <> · body: <code>{metaProbeResult.body}</code></> : null}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {activeTab === 'messages' ? (
        <div className='card telnyxInboundCard'>
          <div className='cardHead'>
            <div className='cardHeadText'>
              <h3>Messages</h3>
              <p className='cardSub'>Inbound &amp; outbound WhatsApp via Meta Cloud API</p>
            </div>
            <div className='actions tsh-msg-toolbar'>
              <button type='button' className='tsh-btn tsh-btn-outline' onClick={() => loadMetaInboundMessages(false)} disabled={providerSaving || !activeSummary?.exists}>
                Search
              </button>
              <button type='button' className='tsh-btn tsh-btn-outline' onClick={() => loadMetaInboundMessages(true)} disabled={providerSaving || !activeSummary?.exists}>
                <RefreshCw size={14} aria-hidden />
              </button>
            </div>
          </div>
          <div className='cardBody'>
            <div className='telnyxMessageFilters'>
              <Field label='From date'>
                <input className='input' type='datetime-local' value={metaMessageFilters?.date_from || ''} onChange={(e) => setMetaMessageFilters((s) => ({ ...s, date_from: e.target.value }))} />
              </Field>
              <Field label='To date'>
                <input className='input' type='datetime-local' value={metaMessageFilters?.date_to || ''} onChange={(e) => setMetaMessageFilters((s) => ({ ...s, date_to: e.target.value }))} />
              </Field>
              <Field label='From number'>
                <input className='input' value={metaMessageFilters?.from_number || ''} onChange={(e) => setMetaMessageFilters((s) => ({ ...s, from_number: e.target.value }))} placeholder='+447…' />
              </Field>
              <Field label='To number'>
                <input className='input' value={metaMessageFilters?.to_number || ''} onChange={(e) => setMetaMessageFilters((s) => ({ ...s, to_number: e.target.value }))} placeholder='+447…' />
              </Field>
            </div>
            {metaInboundMessages?.length ? (
              <div className='tableWrap'>
                <table className='table telnyxInboundTable'>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Direction</th>
                      <th>From</th>
                      <th>To</th>
                      <th>Message</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metaInboundMessages.map((m) => (
                      <tr key={m.id}>
                        <td className='muted'>{fmtTime(m.created_at)}</td>
                        <td>
                          <span className={`pill ${String(m.direction || '').toLowerCase() === 'outbound' ? 'p-cyan' : 'p-green'}`}>
                            {m.direction || 'inbound'}
                          </span>
                        </td>
                        <td>{m.from_number || '—'}</td>
                        <td>{m.to_number || '—'}</td>
                        <td className='telnyxMessageBody'>{String(m.body || '').trim() || '—'}</td>
                        <td>
                          <span className={`pill ${messageStatusClass(m.status)}`}>{m.status || 'received'}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className='note telnyxEmptyInbound'>
                No Meta WhatsApp messages yet. Send a test template or reply from WhatsApp, then refresh.
              </div>
            )}
          </div>
        </div>
      ) : null}

      {activeTab === 'test' ? (
        <div className='card'>
          <div className='cardHead'>
            <div className='cardHeadText'>
              <h3>Test template send</h3>
              <p className='cardSub'>Sends via Meta Graph API using your saved credentials</p>
            </div>
          </div>
          <div className='cardBody stack'>
            <div className='actions'>
              <button type='button' className='btn soft' onClick={syncMetaWhatsappTemplates} disabled={metaWaSyncBusy || providerSaving}>
                {metaWaSyncBusy ? 'Syncing…' : 'Sync templates from Meta'}
              </button>
              <button type='button' className='btn soft' onClick={loadMetaTemplates} disabled={metaTemplatesBusy}>
                {metaTemplatesBusy ? 'Loading…' : 'Preview approved templates'}
              </button>
            </div>
            {metaWaSyncResult ? (
              <div className='note'>
                Synced {metaWaSyncResult.synced ?? metaWaSyncResult.approved ?? 0} template(s) from Meta WABA
                {metaWaSyncResult.approved != null ? <> · {metaWaSyncResult.approved} approved</> : null}
              </div>
            ) : null}
            {metaTemplates?.length ? (
              <div className='muted telnyxFieldHint'>
                First template: <code>{metaTemplates[0]?.name}</code> ({metaTemplates[0]?.language})
              </div>
            ) : null}
            <Field label='To number (E.164)' hint='Your mobile for testing, e.g. +447954823445'>
              <input className='input' value={metaTestNumber} onChange={(e) => setMetaTestNumber(e.target.value)} placeholder='+447…' />
            </Field>
            <Field label='Template name' hint='Leave blank to use first approved template from WABA'>
              <input className='input' value={metaTemplateName} onChange={(e) => setMetaTemplateName(e.target.value)} placeholder='cfs_…' />
            </Field>
            <Field label='Template language' hint='e.g. en, en_GB, ar'>
              <input className='input' value={metaTemplateLang} onChange={(e) => setMetaTemplateLang(e.target.value)} placeholder='en' />
            </Field>
            <button type='button' className='btn primary' onClick={testMetaSend}>
              Send test WhatsApp
            </button>
            {metaSendResult ? (
              <div className='note' style={metaSendResult.ok === false ? { borderColor: 'rgba(220,38,38,0.35)' } : undefined}>
                {metaSendResult.detail || metaSendResult.message || JSON.stringify(metaSendResult)}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  )
}

export function metaWhatsappValidation(config, draft, summary, { telnyxWebhookBase } = {}) {
  const errors = {}
  const has = (key, draftKey) => Boolean(summary?.secret_set?.[key]) || Boolean(String(draft?.[draftKey] || '').trim())
  if (!has('access_token', 'access_token_draft')) errors.access_token = 'Permanent access token (Secrets tab)'
  if (!has('app_secret', 'app_secret_draft')) errors.app_secret = 'App secret (Secrets tab)'
  if (!has('webhook_verify_token', 'webhook_verify_token_draft')) errors.webhook_verify_token = 'Webhook verify token (Secrets tab)'
  if (!String(config?.phone_number_id || '').trim()) errors.phone_number_id = 'Phone number ID'
  if (!String(config?.waba_id || '').trim()) errors.waba_id = 'WABA ID'
  const webhookBase = String(config?.webhook_base_url || telnyxWebhookBase || '').trim()
  if (!webhookBase) errors.webhook_base_url = 'Webhook base URL (Webhooks tab)'
  else if (/^https?:\/\/localhost/i.test(webhookBase)) {
    errors.webhook_base_url = 'Use https://api.voxbulk.com or ngrok (not localhost)'
  }
  return { errors, valid: Object.keys(errors).length === 0 }
}
