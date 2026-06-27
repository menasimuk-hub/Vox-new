import React from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Copy,
  Info,
  Inbox,
  KeyRound,
  MessageSquare,
  Pencil,
  Plug,
  Plus,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Trash2,
  Users,
  Video,
  X,
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

function joinMissingFields(x) {
  const arr = Array.isArray(x) ? x : []
  return arr.length ? arr.join(', ') : ''
}

function fmtTime(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return '—'
  }
}

function messageStatusClass(status) {
  const s = String(status || '').toLowerCase()
  if (s.includes('fail') || s.includes('error') || s.includes('undeliver')) return 'p-red'
  if (s === 'delivered' || s === 'read' || s === 'received') return 'p-green'
  if (s === 'queued' || s === 'sent' || s === 'sending') return 'p-amber'
  return 'p-cyan'
}

function waTemplateStatusPill(status) {
  const s = String(status || '').toUpperCase()
  if (s === 'APPROVED') return { cls: 'p-green', label: 'Approved' }
  if (s === 'REJECTED' || s === 'DELETED' || s === 'DISABLED') return { cls: 'p-red', label: s }
  if (s === 'PENDING' || s.includes('PENDING')) return { cls: 'p-amber', label: s }
  return { cls: 'p-cyan', label: s || 'Unknown' }
}

function looksLikePhoneNotProfile(value) {
  const raw = String(value || '').trim()
  if (!raw) return false
  if (raw.startsWith('+')) return true
  const digits = raw.replace(/\D/g, '')
  const uuidRe = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
  return digits.length >= 10 && !uuidRe.test(raw)
}

const ROUTE_REGION_PRESETS = ['global', 'gb', 'us', 'ca', 'au', 'eu']

export function normalizeRouteRows(raw) {
  if (!Array.isArray(raw)) return []
  return raw.map((row) => ({
    number: String(row?.number || '').trim(),
    label: String(row?.label || '').trim(),
    regions: Array.isArray(row?.regions) ? row.regions.map((r) => String(r || '').trim().toLowerCase()).filter(Boolean) : ['global'],
  }))
}

export function compactRouteRows(raw) {
  return normalizeRouteRows(raw).filter((row) => row.number)
}

function TelnyxRouteTable({ title, hint, routes, onChange, numberPlaceholder = '+44…', labelPlaceholder = 'Label / tag' }) {
  const rows = normalizeRouteRows(routes)
  const updateRow = (index, patch) => {
    const next = rows.map((row, i) => (i === index ? { ...row, ...patch } : row))
    onChange(next)
  }
  const toggleRegion = (index, region) => {
    const row = rows[index]
    if (!row) return
    const set = new Set(row.regions || [])
    if (set.has(region)) set.delete(region)
    else set.add(region)
    updateRow(index, { regions: set.size ? [...set] : ['global'] })
  }
  const addRow = () => onChange([...rows, { number: '', label: '', regions: ['global'] }])
  const removeRow = (index) => onChange(rows.filter((_, i) => i !== index))
  return (
    <div className='stack telnyxRouteSection' style={{ gap: 8 }}>
      <div>
        <strong>{title}</strong>
        {hint ? <div className='muted telnyxFieldHint'>{hint}</div> : null}
      </div>
      {rows.length === 0 ? (
        <div className='muted telnyxRouteEmpty'>
          No numbers yet — click Add number or pick from your Telnyx account below.
        </div>
      ) : (
        <div className='telnyxRouteList'>
          {rows.map((row, index) => (
            <div key={`route-${index}`} className='telnyxRouteCard'>
              <div className='telnyxRouteCardTop'>
                <input
                  className='input'
                  value={row.number}
                  onChange={(e) => updateRow(index, { number: e.target.value })}
                  placeholder={numberPlaceholder}
                  aria-label='Phone number'
                />
                <button type='button' className='btn soft' onClick={() => removeRow(index)}>
                  Remove
                </button>
              </div>
              <input
                className='input telnyxRouteLabelInput'
                value={row.label}
                onChange={(e) => updateRow(index, { label: e.target.value })}
                placeholder={labelPlaceholder}
                aria-label='Label or tag'
              />
              <div className='telnyxRegionChips'>
                {ROUTE_REGION_PRESETS.map((region) => (
                  <button
                    key={region}
                    type='button'
                    className={`btn soft ${(row.regions || []).includes(region) ? 'primary' : ''}`}
                    style={{ padding: '2px 8px', fontSize: 12 }}
                    onClick={() => toggleRegion(index, region)}
                  >
                    {region.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      <button type='button' className='btn soft' onClick={addRow}>
        Add number
      </button>
    </div>
  )
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

function InfoTip({ text }) {
  if (!text) return null
  return (
    <span className='tsh-infotip' tabIndex={0} aria-label={text}>
      <Info size={13} aria-hidden />
      <span className='tsh-infotip-bubble' role='tooltip'>{text}</span>
    </span>
  )
}

function Pill({ tone = 'neutral', children }) {
  return <span className={`tsh-pill tsh-pill-${tone}`}>{children}</span>
}

function CopyInline({ value }) {
  const [copied, setCopied] = React.useState(false)
  const text = String(value || '')
  return (
    <button
      type='button'
      className='tsh-copyinline'
      onClick={() => {
        copyText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 1200)
      }}
      title='Copy'
    >
      <span className='tsh-copyinline-val'>{text}</span>
      {copied ? <Check size={13} aria-hidden /> : <Copy size={13} aria-hidden />}
    </button>
  )
}

function TshDialog({ open, onClose, title, desc, children, footer, width = 460 }) {
  if (!open) return null
  return (
    <div className='tsh-dialog-overlay' role='presentation' onClick={onClose}>
      <div
        className='tsh-dialog'
        role='dialog'
        aria-modal='true'
        aria-label={title}
        style={{ maxWidth: width }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className='tsh-dialog-head'>
          <div>
            <h3 className='tsh-dialog-title'>{title}</h3>
            {desc ? <p className='tsh-dialog-desc'>{desc}</p> : null}
          </div>
          <button type='button' className='tsh-dialog-x' onClick={onClose} aria-label='Close'>
            <X size={15} aria-hidden />
          </button>
        </div>
        <div className='tsh-dialog-body'>{children}</div>
        {footer ? <div className='tsh-dialog-foot'>{footer}</div> : null}
      </div>
    </div>
  )
}

function listToCsv(value) {
  if (Array.isArray(value)) return value.join(', ')
  return String(value || '')
}

function csvToList(raw) {
  return String(raw || '')
    .split(/[,;\s]+/)
    .map((x) => x.trim())
    .filter(Boolean)
}

function csvToIntList(raw) {
  return csvToList(raw)
    .map((x) => parseInt(x, 10))
    .filter((n) => !Number.isNaN(n))
}

const TELNYX_TABS = [
  { id: 'api', label: 'Telnyx API', icon: KeyRound },
  { id: 'whitelist', label: 'Allowlists', icon: ShieldCheck },
  { id: 'whatsapp', label: 'WhatsApp', icon: MessageSquare },
  { id: 'messages', label: 'Messages', icon: Inbox },
  { id: 'zoom', label: 'Zoom', icon: Video },
  { id: 'microsoft_teams', label: 'Teams', icon: Users },
]

function hubPillTone(summary, pill) {
  if (!summary || pill.cls === 'p-amber') return 'warning'
  if (pill.cls === 'p-red') return 'danger'
  if (pill.cls === 'p-green') return 'success'
  return 'info'
}

export default function TelnyxIntegration({
  activeSummary,
  activeConfig,
  activeDraft,
  activeEnabled,
  telnyxStatus,
  telnyxWebhookUrl,
  telnyxMessagingWebhookUrl,
  telnyxMediaStreamUrl,
  telnyxTestNumber,
  setTelnyxTestNumber,
  telnyxWaTemplateName,
  setTelnyxWaTemplateName,
  telnyxWaTemplateId,
  telnyxWaTemplates,
  telnyxWaSyncBusy,
  onSelectTelnyxWaTemplate,
  syncTelnyxWaTemplates,
  loadTelnyxWaTemplates,
  telnyxWaTemplateLang,
  setTelnyxWaTemplateLang,
  telnyxTestResult,
  telnyxSmsTestResult,
  telnyxMessagingSyncResult,
  telnyxZoomTestResult,
  telnyxZoomJoinUrl,
  telnyxZoomConnectionResult,
  telnyxTeamsTestResult,
  telnyxZoomVoiceProfiles,
  telnyxZoomVoiceProfilesBusy,
  telnyxInboundMessages,
  telnyxMessageDetailBusy,
  fetchTelnyxMessageDetail,
  telnyxActiveCallId,
  telnyxCallBusy,
  telnyxAccountNumbers,
  telnyxNumberHealth,
  telnyxHasUnsavedDraft,
  telnyxTestFromVoice,
  setTelnyxTestFromVoice,
  telnyxTestFromSms,
  setTelnyxTestFromSms,
  telnyxTestFromWa,
  setTelnyxTestFromWa,
  telnyxTestAllResults,
  telnyxTestAllBusy,
  testTelnyxAllSenders,
  providerError,
  providerSaving,
  defaultWebhookBase,
  setProviderEnabled,
  setProviderField,
  setProviderDrafts,
  applyTelnyxFromNumber,
  saveIntegrationProvider,
  saveTelnyxZoomOAuth,
  testTelnyx,
  testTelnyxCall,
  hangupTelnyxCall,
  testTelnyxSms,
  syncTelnyxMessagingDestinations,
  testTelnyxWhatsApp,
  testTelnyxZoom,
  createTelnyxZoomConnection,
  testTelnyxZoomConnection,
  createTelnyxTeamsConnection,
  testTelnyxTeamsConnection,
  loadTelnyxZoomVoiceProfiles,
  loadTelnyxInboundMessages,
  telnyxMessageFilters,
  setTelnyxMessageFilters,
}) {
  const pill = statusPill(activeSummary)
  const pillTone = hubPillTone(activeSummary, pill)
  const [activeTab, setActiveTab] = React.useState('api')
  const allowlist = activeConfig.phone_allowlist || {}
  const allowlistEnabled = activeConfig.phone_allowlist_enabled || { GB: true, AU: true, CA: true, USA: true }
  const allowlistExtra = {
    PS: { code: '970', name: 'Palestine', allow_any_prefix: true },
    ...(activeConfig.phone_allowlist_extra || {}),
  }
  const allowlistExtraEnabled = activeConfig.phone_allowlist_extra_enabled || {}
  const messagingDestinations = {
    GB: true,
    US: true,
    AU: true,
    CA: true,
    PS: true,
    ...(activeConfig.messaging_whitelisted_destinations || {}),
  }
  const messagingAllowAll = Boolean(activeConfig.messaging_allow_all_destinations)
  const [newCallIso, setNewCallIso] = React.useState('')
  const [newCallDial, setNewCallDial] = React.useState('')
  const [newMsgIso, setNewMsgIso] = React.useState('')
  const [editCred, setEditCred] = React.useState(null)
  const [prefixDialogCountry, setPrefixDialogCountry] = React.useState(null)
  const [showAddCallRegion, setShowAddCallRegion] = React.useState(false)

  const CRED_FIELDS = [
    { key: 'api_key', label: 'API key', secret: true, info: 'Secret v2 key from Telnyx Portal → API Keys (starts with KEY).' },
    { key: 'connection_id', label: 'Voice connection ID', mirror: ['voice_api_application_id'], info: 'Call Control application ID (landline / voice calls only).' },
    { key: 'outbound_voice_profile_id', label: 'Outbound voice profile ID', info: 'Optional. Used for outbound voice profile selection.' },
    { key: 'messaging_org_id', label: 'Messaging org ID', alt: 'default_messaging_org_id', info: 'Optional. Org UUID for inbound logs; first org used if blank.' },
    { key: 'messaging_profile_id', label: 'SMS messaging profile ID', info: 'UUID for the profile that owns your SMS mobile number.' },
    { key: 'whatsapp_messaging_profile_id', label: 'WhatsApp messaging profile ID', info: 'Only if your WA number uses a different profile than SMS.' },
  ]

  const credValue = (f) => String(activeConfig[f.key] || (f.alt ? activeConfig[f.alt] : '') || '')
  const credSecretSet = (f) => Boolean(activeSummary?.secret_set?.[f.key])
  const setCredValue = (f, val) => {
    setProviderField('telnyx', f.key, val)
    ;(f.mirror || []).forEach((m) => setProviderField('telnyx', m, val))
  }
  const editingCred = CRED_FIELDS.find((f) => f.key === editCred) || null

  const setAllowlistEnabled = (country, checked) => {
    setProviderField('telnyx', 'phone_allowlist_enabled', { ...allowlistEnabled, [country]: checked })
  }

  const setExtraAllowlistEnabled = (country, checked) => {
    setProviderField('telnyx', 'phone_allowlist_extra_enabled', { ...allowlistExtraEnabled, [country]: checked })
  }

  const setMessagingDestinationEnabled = (iso, checked) => {
    setProviderField('telnyx', 'messaging_whitelisted_destinations', { ...messagingDestinations, [iso]: checked })
  }

  const patchAllowlistCountry = (country, patch) => {
    const current = allowlist[country] || {}
    setProviderField('telnyx', 'phone_allowlist', { ...allowlist, [country]: { ...current, ...patch } })
  }

  const patchAllowlistExtra = (country, patch) => {
    const current = allowlistExtra[country] || {}
    setProviderField('telnyx', 'phone_allowlist_extra', { ...allowlistExtra, [country]: { ...current, ...patch } })
  }

  const addCallCountry = () => {
    const iso = String(newCallIso || '').trim().toUpperCase()
    const dial = String(newCallDial || '').trim().replace(/\D/g, '')
    if (!iso || iso.length !== 2) {
      window.alert('Enter a 2-letter ISO code (e.g. PS, AE).')
      return
    }
    if (!dial) {
      window.alert('Enter the dial code without + (e.g. 970 for Palestine).')
      return
    }
    patchAllowlistExtra(iso, { code: dial, name: iso, allow_any_prefix: true })
    setExtraAllowlistEnabled(iso, true)
    setNewCallIso('')
    setNewCallDial('')
  }

  const addMessagingCountry = () => {
    const iso = String(newMsgIso || '').trim().toUpperCase()
    if (!iso || iso.length !== 2) {
      window.alert('Enter a 2-letter ISO code (e.g. PS, AE).')
      return
    }
    setMessagingDestinationEnabled(iso, true)
    setNewMsgIso('')
  }

  const removeCallCountry = (iso) => {
    const nextExtra = { ...allowlistExtra }
    const nextEnabled = { ...allowlistExtraEnabled }
    delete nextExtra[iso]
    delete nextEnabled[iso]
    setProviderField('telnyx', 'phone_allowlist_extra', nextExtra)
    setProviderField('telnyx', 'phone_allowlist_extra_enabled', nextEnabled)
  }

  const removeMessagingCountry = (iso) => {
    const next = { ...messagingDestinations }
    delete next[iso]
    setProviderField('telnyx', 'messaging_whitelisted_destinations', next)
  }

  const callExtraRows = Object.keys(allowlistExtra).sort()
  const messagingRows = Object.keys(messagingDestinations).sort()
  const coreCallCountries = ['GB', 'AU', 'CA', 'USA']
  const dialHint = (country, cfg) => {
    if (cfg?.code) return `+${cfg.code}`
    if (country === 'USA' || country === 'CA') return '+1'
    if (country === 'GB') return '+44'
    if (country === 'AU') return '+61'
    return '—'
  }

  const patchAllowlistPrefixes = (country, field, raw) => {
    patchAllowlistCountry(country, { [field]: csvToList(raw) })
  }

  const patchCanadaAreaCodes = (raw) => {
    patchAllowlistCountry('CA', { area_codes: csvToIntList(raw) })
  }

  return (
    <div className='telnyxHub'>
      <Link to='/integrations/kpi' className='tsh-back'>
        <ArrowLeft size={14} aria-hidden />
        Integration KPI
      </Link>

      <div className='tsh-header'>
        <div className='tsh-header-left'>
          <div className='tsh-icon' aria-hidden>
            <Plug size={16} />
          </div>
          <div>
            <h1 className='tsh-title'>Telnyx</h1>
            <p className='tsh-subtitle'>Voice · SMS · WhatsApp · webhooks · external connections</p>
          </div>
          <div className='tsh-header-meta'>
            <span className={`tsh-pill tsh-pill-${pillTone}`}>
              {pillTone === 'success' ? <Check size={12} aria-hidden /> : null}
              {pill.text}
            </span>
            {activeSummary?.missing_fields?.length ? (
              <span className='tsh-missing'>Missing: {joinMissingFields(activeSummary.missing_fields)}</span>
            ) : null}
          </div>
        </div>
        <div className='tsh-header-actions'>
          <label className='tsh-enable'>
            <input
              type='checkbox'
              checked={activeEnabled}
              onChange={(e) => setProviderEnabled('telnyx', e.target.checked)}
            />
            <span className='tsh-switch' aria-hidden />
            <span className={activeEnabled ? 'tsh-enable-label-on' : 'tsh-enable-label-off'}>
              {activeEnabled ? 'Enabled' : 'Disabled'}
            </span>
          </label>
          <button
            type='button'
            className='tsh-btn tsh-btn-outline'
            onClick={testTelnyx}
            disabled={providerSaving || !activeSummary?.exists}
          >
            <Plug size={14} aria-hidden />
            Test
          </button>
          <button
            type='button'
            className='tsh-btn tsh-btn-primary'
            onClick={() => saveIntegrationProvider('telnyx')}
            disabled={providerSaving}
          >
            <Save size={14} aria-hidden />
            {providerSaving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      <div className='telnyxIntegrationPage'>
      {(providerError || telnyxHasUnsavedDraft || telnyxTestResult) ? (
        <div className='tsh-alerts'>
          {providerError ? (
            <div className='tsh-banner tsh-banner-error' role='alert'>
              {providerError}
            </div>
          ) : null}
          {telnyxHasUnsavedDraft ? (
            <div className='tsh-banner tsh-banner-warning' role='status'>
              <AlertTriangle size={14} aria-hidden style={{ flexShrink: 0, marginTop: 2 }} />
              <span>You have unsaved changes — save settings before testing new numbers.</span>
            </div>
          ) : null}
          {telnyxTestResult ? (
            <div className='tsh-banner tsh-banner-info' role='status'>
              {telnyxTestResult}
            </div>
          ) : null}
        </div>
      ) : null}
      {telnyxNumberHealth?.configured_checks?.length ? (
        <div className='card telnyxNumberHealth'>
          <div className='cardHead'>
            <h3>Number health</h3>
            <span className='pill p-cyan'>Telnyx API</span>
          </div>
          <div className='cardBody stack'>
            <div className='telnyxNumberHealthList'>
              {telnyxNumberHealth.configured_checks.map((row) => (
                <div key={`${row.role}-${row.number}`} className='telnyxNumberHealthRow'>
                  <div className='telnyxNumberHealthMain'>
                    <span className={`pill ${row.status === 'ok' ? 'p-green' : row.status === 'warn' ? 'p-amber' : 'p-red'}`}>
                      {row.status === 'ok' ? 'OK' : row.status === 'warn' ? 'Warn' : 'Error'}
                    </span>
                    <strong>{row.number}</strong>
                    <span className='pill p-cyan'>{String(row.role || '').toUpperCase()}</span>
                    {row.label ? <span className='muted'>{row.label}</span> : null}
                  </div>
                  {row.issues?.length ? <div className='muted telnyxFieldHint'>{row.issues.join(' · ')}</div> : null}
                </div>
              ))}
            </div>
            {telnyxNumberHealth.inventory_warnings?.length ? (
              <div className='note'>
                {telnyxNumberHealth.inventory_warnings.map((w) => (
                  <div key={w}>{w}</div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className='tsh-tabs' role='tablist' aria-label='Telnyx settings'>
        {TELNYX_TABS.map((tab) => {
          const Icon = tab.icon
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              type='button'
              role='tab'
              aria-selected={isActive}
              className={`tsh-tab${isActive ? ' tsh-tab-active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <Icon size={14} aria-hidden />
              {tab.label}
            </button>
          )
        })}
      </div>

      <div className='tsh-tab-panel'>
      {activeTab === 'api' ? (
      <>
      <div className='telnyxGrid3'>
        <div className='card'>
          <div className='cardHead'>
            <div className='cardHeadText'>
              <h3>Credentials</h3>
              <p className='cardSub'>Keys &amp; IDs from your Telnyx account</p>
            </div>
            <Pill tone='info'>{CRED_FIELDS.length} fields</Pill>
          </div>
          <div className='cardBody'>
            <div className='tableWrap'>
              <table className='table'>
                <thead>
                  <tr>
                    <th style={{ width: '42%' }}>Field</th>
                    <th>Value</th>
                    <th style={{ width: 1 }} />
                  </tr>
                </thead>
                <tbody>
                  {CRED_FIELDS.map((f) => {
                    const hasErr = Boolean(telnyxStatus.errors?.[f.key])
                    const val = credValue(f)
                    return (
                      <tr key={f.key}>
                        <td>
                          <span className='tsh-kv-field'>
                            {f.label}
                            <InfoTip text={f.info} />
                          </span>
                        </td>
                        <td className='tsh-kv-value'>
                          {f.secret ? (
                            <span className='tsh-kv-secret'>
                              <span className='tsh-kv-dots'>••••••••••••</span>
                              {credSecretSet(f) ? <Pill tone='success'>set</Pill> : <Pill tone='warning'>not set</Pill>}
                            </span>
                          ) : val ? (
                            <span title={val}>{val}</span>
                          ) : (
                            <span className='muted'>—</span>
                          )}
                          {hasErr ? <div className='muted telnyxFieldError'>{telnyxStatus.errors[f.key]}</div> : null}
                        </td>
                        <td>
                          <div className='tsh-actions-cell'>
                            <button
                              type='button'
                              className='tsh-icon-btn'
                              title={`Edit ${f.label}`}
                              onClick={() => setEditCred(f.key)}
                            >
                              <Pencil size={14} aria-hidden />
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className='card'>
          <div className='cardHead'>
            <div className='cardHeadText'>
              <h3>Outbound routes</h3>
              <p className='cardSub'>Numbers used per channel + region</p>
            </div>
            <span className='pill p-cyan'>Per region</span>
          </div>
          <div className='cardBody stack'>
            <div className='note'>
              Assign multiple numbers by destination region. <strong>Global</strong> is the fallback when no regional match.
              Outbound AI calls and WhatsApp surveys use these routes (legacy single fields below sync on save).
            </div>
            <TelnyxRouteTable
              title='Voice — AI outbound calls (landline)'
              hint='Landline or voice-capable number for AI outbound, e.g. +442046203055. Not for WhatsApp.'
              numberPlaceholder='+442046203055 landline'
              labelPlaceholder='UK landline — AI voice'
              routes={activeConfig.voice_routes}
              onChange={(next) => setProviderField('telnyx', 'voice_routes', next)}
            />
            <TelnyxRouteTable
              title='WhatsApp — surveys & feedback (mobile)'
              hint='Mobile WhatsApp-enabled number only — not a landline.'
              numberPlaceholder='+447… mobile'
              labelPlaceholder='Mobile — WhatsApp'
              routes={activeConfig.whatsapp_routes}
              onChange={(next) => setProviderField('telnyx', 'whatsapp_routes', next)}
            />
          </div>
        </div>

        <div className='card'>
          <div className='cardHead'>
            <div className='cardHeadText'>
              <h3>Default senders</h3>
              <p className='cardSub'>Mirror the first entry in each route list</p>
            </div>
            <span className='pill p-cyan'>Synced on save</span>
          </div>
          <div className='cardBody stack'>
            <div className='note'>
              Routes above are the source of truth. These fields mirror the first entry in each route list after save.
            </div>
            <Field
              label='Voice / outbound calls (landline)'
              error={telnyxStatus.errors.default_outbound_number}
              hint='Telnyx Call Control — AI voice outbound and test calls. Use your landline (+4420…).'
            >
              <input
                className='input'
                style={telnyxStatus.errors.default_outbound_number ? invalidInputStyle : undefined}
                value={String(activeConfig.default_outbound_number || activeConfig.from_phone_number || '')}
                onChange={(e) => {
                  setProviderField('telnyx', 'default_outbound_number', e.target.value)
                  setProviderField('telnyx', 'from_phone_number', e.target.value)
                }}
                placeholder='+4420… landline'
              />
            </Field>
            <Field label='SMS number (primary)' hint='Platform mobile for surveys and general SMS (single line — no route table).'>
              <input
                className='input'
                value={String(activeConfig.sms_from || '')}
                onChange={(e) => setProviderField('telnyx', 'sms_from', e.target.value)}
                placeholder='+447… mobile'
              />
            </Field>
            <Field label='WhatsApp (surveys & feedback)' hint='Mobile WhatsApp sender — synced from WhatsApp routes on save.'>
              <input
                className='input'
                value={String(activeConfig.whatsapp_from || '')}
                onChange={(e) => setProviderField('telnyx', 'whatsapp_from', e.target.value)}
                placeholder='+447822002055'
              />
            </Field>
            <div className='muted telnyxFieldHint'>
              SMS &amp; WhatsApp messaging profile IDs are edited in the <strong>Credentials</strong> card above.
            </div>
            {telnyxAccountNumbers.length ? (
              <div className='note telnyxNumberPick'>
                <strong>Numbers on your Telnyx account</strong>
                <div className='telnyxNumberChips'>
                  {telnyxAccountNumbers.map((num) => (
                    <div key={num} className='telnyxNumberChipRow'>
                      <span className='muted telnyxNumberChipLabel'>{num}</span>
                      <button type='button' className='btn soft' onClick={() => applyTelnyxFromNumber(num, 'voice')}>
                        Voice
                      </button>
                      <button type='button' className='btn soft' onClick={() => applyTelnyxFromNumber(num, 'sms')}>
                        SMS
                      </button>
                      <button type='button' className='btn soft' onClick={() => applyTelnyxFromNumber(num, 'whatsapp')}>
                        WhatsApp
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <div className='card'>
          <div className='cardHead'>
            <div className='cardHeadText'>
              <h3>Webhooks</h3>
              <p className='cardSub'>Public URLs — paste in Telnyx portal</p>
            </div>
            <span className='pill p-cyan'>Public URLs</span>
          </div>
          <div className='cardBody stack'>
            <Field
              label='Webhook base URL'
              error={telnyxStatus.errors.webhook_base_url}
              hint='Production API host or ngrok https URL (no path). Run: ngrok http 8000'
            >
              <input
                className='input'
                style={telnyxStatus.errors.webhook_base_url ? invalidInputStyle : undefined}
                value={String(activeConfig.webhook_base_url || defaultWebhookBase)}
                onChange={(e) => setProviderField('telnyx', 'webhook_base_url', e.target.value)}
                placeholder='https://your-api-host.com'
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
                  {[
                    { name: 'Voice (Call Control)', url: telnyxWebhookUrl },
                    { name: 'Messaging (SMS + WhatsApp inbound)', url: telnyxMessagingWebhookUrl },
                    { name: 'Status callback', url: String(activeConfig.status_callback_url || `${defaultWebhookBase}/telnyx/webhooks/status`) },
                    { name: 'Verified number', url: String(activeConfig.verified_number_webhook_url || `${defaultWebhookBase}/telnyx/webhooks/verified-numbers`) },
                    { name: 'Media stream (WSS)', url: String(activeConfig.media_stream_url || telnyxMediaStreamUrl) },
                  ].map((w) => (
                    <tr key={w.name}>
                      <td><strong style={{ fontWeight: 500 }}>{w.name}</strong></td>
                      <td><CopyInline value={w.url} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className='muted telnyxFieldHint'>
              Paste the messaging URL into Telnyx Messaging Profile <strong>and</strong> Messaging → WhatsApp → WABA webhook settings.
            </div>
          </div>
        </div>
      </div>

      <div className='telnyxGrid2'>
        <div className='card'>
          <div className='cardHead'>
            <div className='cardHeadText'>
              <h3>Test voice call</h3>
              <p className='cardSub'>Dial your mobile from a configured landline</p>
            </div>
            <span className='pill p-cyan'>Your mobile</span>
          </div>
          <div className='cardBody stack'>
            <Field label='Destination number (E.164)' hint='Your personal mobile, e.g. +447700900123'>
              <input className='input' value={telnyxTestNumber} onChange={(e) => setTelnyxTestNumber(e.target.value)} placeholder='+447700900123' />
            </Field>
            <Field label='From number (landline)' hint='Caller ID for the test call — pick your AI voice landline.'>
              <select className='input' value={telnyxTestFromVoice} onChange={(e) => setTelnyxTestFromVoice(e.target.value)}>
                <option value=''>Default (first voice route)</option>
                {compactRouteRows(activeConfig.voice_routes)
                  .map((r) => r.number)
                  .concat(
                    String(activeConfig.default_outbound_number || activeConfig.from_phone_number || '').trim()
                      ? [String(activeConfig.default_outbound_number || activeConfig.from_phone_number || '').trim()]
                      : []
                  )
                  .filter((n, i, a) => n && a.indexOf(n) === i)
                  .map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
              </select>
            </Field>
            <div className='telnyxTestBlock'>
              <div className='telnyxTestBlockTitle'>Voice</div>
              <div className='muted telnyxFieldHint'>Calls from landline → your mobile</div>
              <div className='actions telnyxTestActions'>
                <button
                  type='button'
                  className='btn soft'
                  onClick={testTelnyxCall}
                  disabled={providerSaving || telnyxCallBusy || !activeSummary?.exists || !telnyxTestNumber.trim()}
                >
                  {telnyxCallBusy && !telnyxActiveCallId ? 'Calling…' : 'Test call'}
                </button>
                <button
                  type='button'
                  className='btn soft'
                  onClick={hangupTelnyxCall}
                  disabled={providerSaving || telnyxCallBusy || !activeSummary?.exists || !telnyxActiveCallId}
                >
                  Hang up
                </button>
                <button
                  type='button'
                  className='btn soft'
                  onClick={testTelnyxAllSenders}
                  disabled={providerSaving || telnyxTestAllBusy || !activeSummary?.exists || !telnyxTestNumber.trim()}
                >
                  {telnyxTestAllBusy ? 'Testing all…' : 'Test all configured numbers'}
                </button>
              </div>
              {telnyxActiveCallId ? <div className='muted telnyxFieldHint'>Active call: {telnyxActiveCallId}</div> : null}
            </div>
            {telnyxTestAllResults?.length ? (
              <div className='telnyxTestAllResults'>
                {telnyxTestAllResults.map((row) => (
                  <div key={`${row.role}-${row.number}`} className='telnyxNumberHealthRow'>
                    <span className={`pill ${row.ok ? 'p-green' : 'p-red'}`}>{row.ok ? 'OK' : 'Fail'}</span>
                    <strong>{row.number}</strong>
                    <span className='pill p-cyan'>{String(row.role || '').toUpperCase()}</span>
                    <span className='muted'>{row.message}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        <div className='card'>
          <div className='cardHead'>
            <h3>Setup checklist</h3>
            <span className='pill p-cyan'>Telnyx portal</span>
          </div>
          <div className='cardBody'>
            <ol className='telnyxChecklist'>
              <li><strong>Landline</strong> → Call Control → voice webhook URL.</li>
              <li><strong>SMS mobile</strong> → Messaging Profile → messaging webhook URL.</li>
              <li><strong>WhatsApp number</strong> → Meta WABA in Telnyx → same messaging webhook + WABA webhooks.</li>
              <li>Save voice, SMS, and WhatsApp numbers here (they can be different lines).</li>
              <li>Save settings, then <strong>Test connection</strong>.</li>
            </ol>
          </div>
        </div>
      </div>
      </>
      ) : null}

      {activeTab === 'whitelist' ? (
        <div className='stack' style={{ gap: 20 }}>
          <div className='card'>
            <div className='cardHead'>
              <div className='cardHeadText'>
                <h3>Call allowlist — AI voice</h3>
                <p className='cardSub'>Per-region dial rules · click edit to manage prefixes</p>
              </div>
              <div className='actions'>
                <button type='button' className='tsh-btn tsh-btn-outline' onClick={() => setShowAddCallRegion(true)}>
                  <Plus size={14} aria-hidden /> Region
                </button>
              </div>
            </div>
            <div className='cardBody stack'>
              <div className='tsh-banner tsh-banner-info'>
                <Info size={14} aria-hidden style={{ flexShrink: 0, marginTop: 2 }} />
                <span><strong>Call allowlist</strong> controls which numbers AI voice can dial. Does not affect WhatsApp/SMS — see the messaging table below.</span>
              </div>
              <div className='tableWrap'>
                <table className='table'>
                  <thead>
                    <tr>
                      <th style={{ width: 1 }}>On</th>
                      <th>Region</th>
                      <th>Code</th>
                      <th>Rules</th>
                      <th style={{ textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {coreCallCountries.map((country) => {
                      const cfg = allowlist[country] || {}
                      const enabled = allowlistEnabled[country] !== false
                      const rules =
                        country === 'USA'
                          ? 'NANP +1 (non-Canada)'
                          : country === 'CA'
                            ? `${(cfg.area_codes || []).length || 0} area codes`
                            : `${(cfg.landline_prefixes || []).length || 0} landline · ${(cfg.mobile_prefixes || []).length || 0} mobile`
                      return (
                        <tr key={country}>
                          <td><input type='checkbox' checked={enabled} onChange={(e) => setAllowlistEnabled(country, e.target.checked)} /></td>
                          <td><strong>{country}</strong></td>
                          <td className='muted'>{dialHint(country, cfg)}</td>
                          <td className='muted'>{rules}</td>
                          <td>
                            <div className='tsh-actions-cell'>
                              <button type='button' className='tsh-icon-btn' title='Edit prefixes' onClick={() => setPrefixDialogCountry(country)}>
                                <Pencil size={14} aria-hidden />
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                    {callExtraRows.map((iso) => {
                      const cfg = allowlistExtra[iso] || {}
                      const enabled = allowlistExtraEnabled[iso] === true
                      return (
                        <tr key={`extra-${iso}`}>
                          <td><input type='checkbox' checked={enabled} onChange={(e) => setExtraAllowlistEnabled(iso, e.target.checked)} /></td>
                          <td><strong>{iso}</strong> <span className='muted'>{String(cfg.name || iso)}</span></td>
                          <td>
                            <input
                              className='input'
                              style={{ maxWidth: 90, height: 28 }}
                              value={String(cfg.code || '')}
                              onChange={(e) => patchAllowlistExtra(iso, { code: e.target.value.trim().replace(/\D/g, '') })}
                              placeholder='970'
                            />
                          </td>
                          <td className='muted'>Any prefix</td>
                          <td>
                            <div className='tsh-actions-cell'>
                              <button type='button' className='tsh-icon-btn danger' title='Remove' onClick={() => removeCallCountry(iso)}>
                                <Trash2 size={14} aria-hidden />
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className='card'>
            <div className='cardHead'>
              <div className='cardHeadText'>
                <h3>Messaging destinations — WhatsApp &amp; SMS</h3>
                <p className='cardSub'>Synced to Telnyx messaging profile whitelisted destinations</p>
              </div>
              <div className='actions'>
                <label className='telnyxEnableRow' style={{ fontSize: 11.5 }}>
                  <input
                    type='checkbox'
                    checked={messagingAllowAll}
                    onChange={(e) => setProviderField('telnyx', 'messaging_allow_all_destinations', e.target.checked)}
                  />
                  <span>Allow all (<code>*</code>)</span>
                </label>
                <button type='button' className='tsh-btn tsh-btn-primary' onClick={syncTelnyxMessagingDestinations} disabled={providerSaving}>
                  Sync
                </button>
              </div>
            </div>
            <div className='cardBody stack'>
              <div className='tsh-banner tsh-banner-info'>
                <Info size={14} aria-hidden style={{ flexShrink: 0, marginTop: 2 }} />
                <span>
                  Required for outbound WhatsApp/SMS (e.g. error: region <code>PS</code> not whitelisted for <code>+970…</code>).
                  This list does <strong>not</strong> control AI voice calls. Save settings first, then Sync.
                </span>
              </div>
              <div className='tableWrap'>
                <table className='table'>
                  <thead>
                    <tr>
                      <th style={{ width: 1 }}>On</th>
                      <th>ISO</th>
                      <th>Notes</th>
                      <th style={{ textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {messagingRows.length ? messagingRows.map((iso) => (
                      <tr key={`msg-${iso}`}>
                        <td>
                          <input
                            type='checkbox'
                            checked={messagingDestinations[iso] !== false}
                            disabled={messagingAllowAll}
                            onChange={(e) => setMessagingDestinationEnabled(iso, e.target.checked)}
                          />
                        </td>
                        <td><strong>{iso}</strong></td>
                        <td className='muted'>{iso === 'PS' ? 'Palestine (+970)' : ''}</td>
                        <td>
                          <div className='tsh-actions-cell'>
                            {!['GB', 'US', 'AU', 'CA', 'PS'].includes(iso) ? (
                              <button type='button' className='tsh-icon-btn danger' title='Remove' onClick={() => removeMessagingCountry(iso)}>
                                <Trash2 size={14} aria-hidden />
                              </button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    )) : (
                      <tr><td colSpan={4} className='muted'>No destinations — add PS or enable Allow all countries.</td></tr>
                    )}
                    <tr>
                      <td />
                      <td colSpan={3}>
                        <div className='actions' style={{ alignItems: 'center' }}>
                          <input
                            className='input'
                            style={{ width: 140, height: 28, textTransform: 'uppercase' }}
                            value={newMsgIso}
                            onChange={(e) => setNewMsgIso(e.target.value)}
                            placeholder='Add ISO (e.g. PS)'
                          />
                          <button type='button' className='tsh-btn tsh-btn-outline' onClick={addMessagingCountry} disabled={messagingAllowAll}>
                            <Plus size={14} aria-hidden /> Add
                          </button>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              {telnyxMessagingSyncResult ? <div className='note' style={{ whiteSpace: 'pre-wrap' }}>{telnyxMessagingSyncResult}</div> : null}
            </div>
          </div>
        </div>
      ) : null}

      {activeTab === 'whatsapp' ? (
      <div className='telnyxWaLayout'>
        <div className='card'>
          <div className='cardHead'>
            <div className='cardHeadText'>
              <h3>WhatsApp Business Account</h3>
              <p className='cardSub'>Required to push survey templates to Meta</p>
            </div>
            <span className='pill p-cyan'>WABA</span>
          </div>
          <div className='cardBody stack'>
            <Field
              label='WhatsApp Business Account ID'
              hint='Required to push WA Survey templates to Telnyx/Meta. Telnyx Portal → Messaging → WhatsApp → your WABA → copy the Meta WABA id (numeric). Leave blank to auto-detect from your Telnyx account on push/sync.'
            >
              <input
                className='input'
                value={String(activeConfig.whatsapp_waba_id || activeConfig.waba_id || '')}
                onChange={(e) => {
                  setProviderField('telnyx', 'whatsapp_waba_id', e.target.value)
                  setProviderField('telnyx', 'waba_id', e.target.value)
                }}
                placeholder='e.g. 2019979452207634'
              />
            </Field>
            <div className='note'>
              Sending WhatsApp messages only needs your <strong>WhatsApp number</strong> on the Telnyx API tab.
              Pushing new survey templates to Meta additionally needs this WABA id (or a connected WABA VoxBulk can auto-detect).
            </div>
          </div>
        </div>

        <div className='card telnyxWaTemplatesCard'>
          <div className='cardHead'>
            <div className='cardHeadText'>
              <h3>Templates</h3>
              <p className='cardSub'>Synced from Telnyx · only Approved are usable</p>
            </div>
            <div className='actions'>
              <button
                type='button'
                className='tsh-btn tsh-btn-outline'
                onClick={syncTelnyxWaTemplates}
                disabled={providerSaving || telnyxWaSyncBusy || !activeSummary?.exists}
              >
                <RefreshCw size={14} aria-hidden /> {telnyxWaSyncBusy ? 'Syncing…' : 'Sync'}
              </button>
              <button
                type='button'
                className='tsh-btn tsh-btn-outline'
                onClick={() => loadTelnyxWaTemplates(false)}
                disabled={providerSaving || !activeSummary?.exists}
              >
                Reload
              </button>
            </div>
          </div>
          <div className='cardBody telnyxWaTemplatesBody'>
            {(telnyxWaTemplates || []).length > 0 ? (
              <div className='tableWrap'>
                <table className='table'>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Category</th>
                      <th>Lang</th>
                      <th>Synced</th>
                      <th>Status</th>
                      <th style={{ width: 1 }} />
                    </tr>
                  </thead>
                  <tbody>
                    {(telnyxWaTemplates || []).map((t) => {
                      const pill = waTemplateStatusPill(t.status)
                      const id = String(t.template_id || t.id || '')
                      const selected = id && id === String(telnyxWaTemplateId || '')
                      const approved = String(t.status || '').toUpperCase() === 'APPROVED'
                      return (
                        <tr key={t.template_id || t.id || t.name} style={approved ? undefined : { opacity: 0.6 }}>
                          <td style={{ fontFamily: 'ui-monospace, monospace', fontWeight: 500 }}>{t.name}</td>
                          <td className='muted'>{t.meta_category || t.category || t.sales_template_key || '—'}</td>
                          <td className='muted'>{t.language || '—'}</td>
                          <td className='muted'>{t.synced_at ? fmtTime(t.synced_at) : '—'}</td>
                          <td><span className={`pill ${pill.cls}`}>{pill.label}</span></td>
                          <td>
                            <div className='tsh-actions-cell'>
                              <button
                                type='button'
                                className='tsh-btn tsh-btn-outline'
                                style={{ height: 26, padding: '0 8px' }}
                                disabled={!approved}
                                title={approved ? 'Use for test send' : 'Only approved templates can be selected'}
                                onClick={() => approved && onSelectTelnyxWaTemplate(id)}
                              >
                                {selected ? 'Selected' : 'Use'}
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className='note'>
                No templates cached yet. Click <strong>Sync</strong> to pull from Telnyx.
              </div>
            )}
            <div className='muted telnyxFieldHint' style={{ marginTop: 10 }}>
              Sync pulls live templates from Telnyx and removes stale rows. Only <strong>Approved</strong> templates can be used for test sends.
            </div>
          </div>
        </div>

        <div className='card'>
          <div className='cardHead'>
            <div className='cardHeadText'>
              <h3>Test outgoing</h3>
              <p className='cardSub'>Send a real WhatsApp or SMS to your mobile</p>
            </div>
            <span className='pill p-cyan'>Your mobile</span>
          </div>
          <div className='cardBody stack'>
            <Field label='Destination number (E.164)' hint='Your personal mobile, e.g. +447700900123'>
              <input className='input' value={telnyxTestNumber} onChange={(e) => setTelnyxTestNumber(e.target.value)} placeholder='+447700900123' />
            </Field>
            <div className='telnyxTestBlock'>
              <div className='telnyxTestBlockTitle'>Platform SMS</div>
              <div className='muted telnyxFieldHint'>Uses the primary SMS number from the Telnyx API tab.</div>
              <Field label='From number (SMS)'>
                <select className='input' value={telnyxTestFromSms} onChange={(e) => setTelnyxTestFromSms(e.target.value)}>
                  <option value=''>Default (sms_from)</option>
                  {String(activeConfig.sms_from || '')
                    .trim()
                    ? [String(activeConfig.sms_from).trim()].map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))
                    : null}
                </select>
              </Field>
              <div className='actions telnyxTestActions'>
                <button type='button' className='btn soft' onClick={testTelnyxSms} disabled={providerSaving || !activeSummary?.exists || !telnyxTestNumber.trim()}>
                  Test SMS
                </button>
              </div>
              {telnyxSmsTestResult ? <div className='note'>{telnyxSmsTestResult}</div> : null}
            </div>
            <div className='telnyxTestBlock'>
              <div className='telnyxTestBlockTitle'>Platform WhatsApp (surveys & feedback)</div>
              <div className='muted telnyxFieldHint'>Uses the platform WhatsApp number — survey templates and customer feedback.</div>
              <Field label='From number (WhatsApp)'>
                <select className='input' value={telnyxTestFromWa} onChange={(e) => setTelnyxTestFromWa(e.target.value)}>
                  <option value=''>Default (first WhatsApp route)</option>
                  {compactRouteRows(activeConfig.whatsapp_routes)
                    .map((r) => r.number)
                    .concat(
                      String(activeConfig.whatsapp_from || '').trim() ? [String(activeConfig.whatsapp_from).trim()] : []
                    )
                    .filter((n, i, a) => n && a.indexOf(n) === i)
                    .map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                </select>
              </Field>
              <Field
                label='WhatsApp template (approved only)'
                hint='Pick from the list on the left, or choose here.'
              >
                <select
                  className='input'
                  value={telnyxWaTemplateId}
                  onChange={(e) => onSelectTelnyxWaTemplate(e.target.value)}
                >
                  <option value=''>— Select approved template —</option>
                  {(telnyxWaTemplates || [])
                    .filter((t) => String(t.status || '').toUpperCase() === 'APPROVED')
                    .map((t) => (
                      <option key={t.template_id || t.id} value={t.template_id || ''}>
                        {t.name} · {t.language}
                        {t.template_id ? ` · ${String(t.template_id).slice(0, 8)}…` : ''}
                      </option>
                    ))}
                </select>
              </Field>
              <Field
                label='Or template name / UUID (manual)'
                hint='Optional override. Prefer the synced list on the left.'
              >
                <input
                  className='input'
                  value={telnyxWaTemplateName}
                  onChange={(e) => setTelnyxWaTemplateName(e.target.value)}
                  placeholder='voxbulk_sales_offer or UUID'
                />
              </Field>
              <Field label='Template language' hint='Auto-filled when you pick a synced template (your templates use en_US).'>
                <input
                  className='input'
                  value={telnyxWaTemplateLang}
                  onChange={(e) => setTelnyxWaTemplateLang(e.target.value)}
                  placeholder='en_US'
                />
              </Field>
              <div className='actions telnyxTestActions'>
                <button type='button' className='btn soft' onClick={testTelnyxWhatsApp} disabled={providerSaving || !activeSummary?.exists || !telnyxTestNumber.trim()}>
                  Test WhatsApp
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
      ) : null}

      {activeTab === 'messages' ? (
      <div className='card telnyxInboundCard'>
        <div className='cardHead'>
          <div className='cardHeadText'>
            <h3>Messages</h3>
            <p className='cardSub'>Inbound &amp; outbound SMS / WhatsApp log</p>
          </div>
          <div className='actions tsh-msg-toolbar'>
            <div className='tsh-search'>
              <Search size={14} aria-hidden />
              <input
                className='input'
                value={telnyxMessageFilters.q || ''}
                onChange={(e) => setTelnyxMessageFilters((s) => ({ ...s, q: e.target.value }))}
                placeholder='Search preview…'
              />
            </div>
            <button type='button' className='tsh-btn tsh-btn-outline' onClick={loadTelnyxInboundMessages} disabled={providerSaving || !activeSummary?.exists}>
              Search
            </button>
            <button type='button' className='tsh-btn tsh-btn-outline' onClick={() => loadTelnyxInboundMessages(true)} disabled={providerSaving || !activeSummary?.exists}>
              <RefreshCw size={14} aria-hidden />
            </button>
          </div>
        </div>
        <div className='cardBody'>
          <div className='telnyxMessageFilters'>
            <Field label='From date'>
              <input className='input' type='datetime-local' value={telnyxMessageFilters.date_from || ''} onChange={(e) => setTelnyxMessageFilters((s) => ({ ...s, date_from: e.target.value }))} />
            </Field>
            <Field label='To date'>
              <input className='input' type='datetime-local' value={telnyxMessageFilters.date_to || ''} onChange={(e) => setTelnyxMessageFilters((s) => ({ ...s, date_to: e.target.value }))} />
            </Field>
            <Field label='From number'>
              <input className='input' value={telnyxMessageFilters.from_number || ''} onChange={(e) => setTelnyxMessageFilters((s) => ({ ...s, from_number: e.target.value }))} placeholder='+447…' />
            </Field>
            <Field label='To number'>
              <input className='input' value={telnyxMessageFilters.to_number || ''} onChange={(e) => setTelnyxMessageFilters((s) => ({ ...s, to_number: e.target.value }))} placeholder='+447…' />
            </Field>
          </div>
          {telnyxInboundMessages.length ? (
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
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {telnyxInboundMessages.map((m) => (
                    <tr key={m.id}>
                      <td className='muted'>{fmtTime(m.created_at)}</td>
                      <td>
                        <span className={`pill ${String(m.direction || '').toLowerCase() === 'outbound' ? 'p-cyan' : 'p-green'}`}>
                          {m.direction || 'inbound'}
                        </span>
                      </td>
                      <td>{m.from_number || '—'}</td>
                      <td>{m.to_number || '—'}</td>
                      <td className='telnyxMessageBody'>
                        {String(m.body || '').trim() || '—'}
                        {m.delivery_error ? (
                          <div className='muted telnyxDeliveryError'>Delivery error: {m.delivery_error}</div>
                        ) : null}
                      </td>
                      <td>
                        <span className={`pill ${messageStatusClass(m.status)}`}>{m.status || 'received'}</span>
                      </td>
                      <td>
                        {m.external_message_id ? (
                          <button
                            type='button'
                            className='btn soft'
                            disabled={providerSaving || telnyxMessageDetailBusy === m.external_message_id}
                            onClick={() => fetchTelnyxMessageDetail(m.external_message_id)}
                          >
                            {telnyxMessageDetailBusy === m.external_message_id ? 'Loading…' : 'Telnyx detail'}
                          </button>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className='note telnyxEmptyInbound'>
              No messages yet. Run <strong>Test WhatsApp</strong> (pick a synced template for first contact), or text your business number from WhatsApp, then <strong>Refresh</strong>.
              Outbound tests appear here immediately; delivery errors update via webhook. Set the messaging webhook URL on both the <strong>Messaging Profile</strong> and <strong>WhatsApp → WABA</strong>.
            </div>
          )}
          {telnyxInboundMessages.length ? (
            <div className='tsh-pagination'>
              <span>Showing {telnyxInboundMessages.length} message{telnyxInboundMessages.length === 1 ? '' : 's'}</span>
              <div className='actions'>
                <button type='button' className='tsh-btn tsh-btn-outline' onClick={() => loadTelnyxInboundMessages(true)} disabled={providerSaving || !activeSummary?.exists}>
                  Refresh
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
      ) : null}

      {activeTab === 'zoom' ? (
        <div className='card'>
          <div className='cardHead'>
            <div className='cardHeadText'>
              <h3>Zoom external connection</h3>
              <p className='cardSub'>Telnyx-native first, OAuth fallback</p>
            </div>
            <div className='actions'>
              <button type='button' className='tsh-btn tsh-btn-outline' onClick={() => loadTelnyxZoomVoiceProfiles(false)} disabled={providerSaving || telnyxZoomVoiceProfilesBusy}>
                <RefreshCw size={14} aria-hidden /> Refresh
              </button>
              <button type='button' className='tsh-btn tsh-btn-primary' onClick={createTelnyxZoomConnection} disabled={providerSaving}>
                Create
              </button>
              <button type='button' className='tsh-btn tsh-btn-outline' onClick={testTelnyxZoomConnection} disabled={providerSaving}>
                Test
              </button>
            </div>
          </div>
          <div className='cardBody'>
            <div className='stack' style={{ gap: 12 }}>
              <p className='muted' style={{ fontSize: 14, marginBottom: 6 }}>
                Create and validate a real Telnyx Zoom external connection first, then run an interview meeting test.
              </p>
              <div className='note'>
                If your Telnyx account does not expose <code>/zoom/meetings</code>, VoxBulk falls back to Zoom OAuth.
                Add Zoom OAuth credentials here and save Telnyx settings.
              </div>
              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Zoom Account ID (OAuth fallback)</label>
                <input
                  className='input'
                  value={String(activeConfig.zoom_account_id || '')}
                  onChange={(e) => setProviderField('telnyx', 'zoom_account_id', e.target.value)}
                  placeholder='Zoom Server-to-Server account_id'
                />
              </div>
              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Zoom Client ID (OAuth fallback)</label>
                <input
                  className='input'
                  value={String(activeConfig.zoom_client_id || '')}
                  onChange={(e) => setProviderField('telnyx', 'zoom_client_id', e.target.value)}
                  placeholder='Zoom Server-to-Server client_id'
                />
              </div>
              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Zoom Client Secret (OAuth fallback)</label>
                <input
                  className='input'
                  type='password'
                  value={String(activeDraft.zoom_client_secret_draft || '')}
                  onChange={(e) =>
                    setProviderDrafts((s) => ({
                      ...s,
                      telnyx: { ...(s.telnyx || {}), zoom_client_secret_draft: e.target.value },
                    }))
                  }
                  placeholder={
                    activeSummary?.secret_set?.zoom_client_secret
                      ? 'Leave blank to keep current secret'
                      : 'Zoom Server-to-Server client_secret'
                  }
                />
              </div>
              <div className='actions' style={{ marginTop: 4 }}>
                <button
                  type='button'
                  className='btn primary'
                  onClick={() => saveTelnyxZoomOAuth()}
                  disabled={providerSaving}
                >
                  {providerSaving ? 'Saving…' : 'Save Zoom settings'}
                </button>
              </div>
              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Zoom API base URL (optional)</label>
                <input
                  className='input'
                  value={String(activeConfig.zoom_base_url || 'https://api.zoom.us/v2')}
                  onChange={(e) => setProviderField('telnyx', 'zoom_base_url', e.target.value)}
                />
              </div>
              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Outbound voice profile ID (required by Telnyx)</label>
                <div className='actions' style={{ gap: 8 }}>
                  <select
                    className='input'
                    value={String(activeConfig.zoom_outbound_voice_profile_id || '')}
                    onChange={(e) => setProviderField('telnyx', 'zoom_outbound_voice_profile_id', e.target.value)}
                  >
                    <option value=''>
                      {telnyxZoomVoiceProfilesBusy ? 'Loading Telnyx profiles…' : 'Auto-select from Telnyx'}
                    </option>
                    {Array.isArray(telnyxZoomVoiceProfiles)
                      ? telnyxZoomVoiceProfiles.map((row) => (
                          <option key={row.id} value={row.id}>
                            {row.name || row.id} ({row.id})
                          </option>
                        ))
                      : null}
                  </select>
                  <button type='button' className='btn soft' onClick={() => loadTelnyxZoomVoiceProfiles(false)} disabled={providerSaving || telnyxZoomVoiceProfilesBusy}>
                    {telnyxZoomVoiceProfilesBusy ? 'Loading…' : 'Refresh profiles'}
                  </button>
                </div>
                <div className='muted telnyxFieldHint'>
                  Leave it on auto if unsure. VoxBulk will use the first available Telnyx outbound profile.
                </div>
              </div>
              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Webhook event URL (optional)</label>
                <input
                  className='input'
                  value={String(activeConfig.zoom_webhook_event_url || '')}
                  onChange={(e) => setProviderField('telnyx', 'zoom_webhook_event_url', e.target.value)}
                  placeholder={`${String(activeConfig.webhook_base_url || 'https://api.voxbulk.com').replace(/\/+$/, '')}/telnyx/webhooks/zoom`}
                />
              </div>
              <div style={{ display: 'grid', gap: 6 }}>
                <label className='label'>Zoom external connection ID (optional for test)</label>
                <input
                  className='input'
                  value={String(activeConfig.zoom_external_connection_id || '')}
                  onChange={(e) => setProviderField('telnyx', 'zoom_external_connection_id', e.target.value)}
                  placeholder='Auto-filled after create'
                />
              </div>
              <div className='actions telnyxTestActions'>
                <button type='button' className='btn soft' onClick={createTelnyxZoomConnection} disabled={providerSaving}>
                  Create Zoom Connection
                </button>
                <button type='button' className='btn soft' onClick={testTelnyxZoomConnection} disabled={providerSaving}>
                  Test Zoom Connection
                </button>
              </div>
              {telnyxZoomConnectionResult ? <div className='note'>{telnyxZoomConnectionResult}</div> : null}
              <p className='muted' style={{ fontSize: 12, marginBottom: 6 }}>
                After interviews, point Telnyx Zoom webhooks to{' '}
                <code>{String(activeConfig.webhook_base_url || 'https://api.voxbulk.com').replace(/\/+$/, '')}/telnyx/webhooks/zoom</code>{' '}
                (or your API host + <code>/telnyx/webhooks/zoom</code>) so recordings and transcripts sync automatically.
              </p>
              <div className='note'>
                Interview delivery test (below) verifies meeting creation flow used by campaigns.
              </div>
              <div className='actions telnyxTestActions'>
                <button type='button' className='btn soft' onClick={testTelnyxZoom} disabled={providerSaving}>
                  Test Interview Meeting
                </button>
              </div>
              {telnyxZoomTestResult ? <div className='note'>{telnyxZoomTestResult}</div> : null}
              {telnyxZoomJoinUrl ? (
                <div className='note'>
                  <div style={{ marginBottom: 6 }}>
                    <strong>Meeting link ready</strong>
                  </div>
                  <div className='telnyxCopyRow'>
                    <input className='input' value={telnyxZoomJoinUrl} readOnly />
                    <button type='button' className='btn soft' onClick={() => copyText(telnyxZoomJoinUrl)}>
                      Copy
                    </button>
                    <a className='btn soft' href={telnyxZoomJoinUrl} target='_blank' rel='noreferrer'>
                      Open
                    </a>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {activeTab === 'microsoft_teams' ? (
        <div className='card'>
          <div className='cardHead'>
            <div className='cardHeadText'>
              <h3>Microsoft Teams — Operator Connect</h3>
              <p className='cardSub'>Telnyx creates external connections asynchronously</p>
            </div>
            <div className='actions'>
              <button type='button' className='tsh-btn tsh-btn-primary' onClick={createTelnyxTeamsConnection} disabled={providerSaving}>
                Create
              </button>
              <button type='button' className='tsh-btn tsh-btn-outline' onClick={testTelnyxTeamsConnection} disabled={providerSaving}>
                Test
              </button>
            </div>
          </div>
          <div className='cardBody'>
            <div className='stack' style={{ gap: 12 }}>
              <p className='muted' style={{ fontSize: 14, marginBottom: 6 }}>
                Telnyx creates Operator Connect external connections asynchronously. Use Create, then Test until it reports active.
              </p>
              <div className='actions telnyxTestActions'>
                <button type='button' className='btn soft' onClick={createTelnyxTeamsConnection} disabled={providerSaving}>
                  Create Teams Connection
                </button>
                <button type='button' className='btn soft' onClick={testTelnyxTeamsConnection} disabled={providerSaving}>
                  Test Teams Connection
                </button>
              </div>
              {telnyxTeamsTestResult ? <div className='note'>{telnyxTeamsTestResult}</div> : null}
            </div>
          </div>
        </div>
      ) : null}
      </div>
      </div>

      <TshDialog
        open={Boolean(editingCred)}
        onClose={() => setEditCred(null)}
        title={editingCred ? `Edit ${editingCred.label}` : ''}
        desc={editingCred?.info}
        footer={
          <>
            <button type='button' className='tsh-btn tsh-btn-outline' onClick={() => setEditCred(null)}>Cancel</button>
            <button type='button' className='tsh-btn tsh-btn-primary' onClick={() => setEditCred(null)}>Done</button>
          </>
        }
      >
        {editingCred ? (
          editingCred.secret ? (
            <Field label={editingCred.label} hint={credSecretSet(editingCred) ? 'A value is already set — paste a new one to replace it.' : undefined}>
              <input
                className='input'
                type='password'
                autoFocus
                value={String(activeDraft.api_key_draft || '')}
                onChange={(e) =>
                  setProviderDrafts((s) => ({
                    ...s,
                    telnyx: { ...(s.telnyx || {}), api_key_draft: e.target.value },
                  }))
                }
                placeholder={credSecretSet(editingCred) ? 'Paste new KEY… to replace' : 'KEYxxxxxxxx…'}
              />
            </Field>
          ) : (
            <Field label={editingCred.label}>
              <input
                className='input'
                autoFocus
                value={credValue(editingCred)}
                onChange={(e) => setCredValue(editingCred, e.target.value)}
              />
            </Field>
          )
        ) : null}
        <div className='muted telnyxFieldHint'>Changes apply when you click <strong>Save</strong> at the top of the page.</div>
      </TshDialog>

      <TshDialog
        open={Boolean(prefixDialogCountry)}
        onClose={() => setPrefixDialogCountry(null)}
        title={prefixDialogCountry ? `${prefixDialogCountry} — prefix rules` : ''}
        desc='Prefix rules for the AI voice allowlist. Comma-separated.'
        width={520}
        footer={
          <>
            <button type='button' className='tsh-btn tsh-btn-outline' onClick={() => setPrefixDialogCountry(null)}>Cancel</button>
            <button type='button' className='tsh-btn tsh-btn-primary' onClick={() => setPrefixDialogCountry(null)}>Done</button>
          </>
        }
      >
        {prefixDialogCountry ? (() => {
          const cfg = allowlist[prefixDialogCountry] || {}
          return (
            <>
              {(prefixDialogCountry === 'GB' || prefixDialogCountry === 'AU') ? (
                <>
                  <Field label='Landline prefixes (comma-separated)'>
                    <input className='input' value={listToCsv(cfg.landline_prefixes)} onChange={(e) => patchAllowlistPrefixes(prefixDialogCountry, 'landline_prefixes', e.target.value)} />
                  </Field>
                  <Field label='Mobile prefixes (comma-separated)'>
                    <input className='input' value={listToCsv(cfg.mobile_prefixes)} onChange={(e) => patchAllowlistPrefixes(prefixDialogCountry, 'mobile_prefixes', e.target.value)} />
                  </Field>
                </>
              ) : null}
              {prefixDialogCountry === 'CA' ? (
                <Field label='Canada area codes (comma-separated)'>
                  <textarea className='input' rows={4} value={listToCsv(cfg.area_codes)} onChange={(e) => patchCanadaAreaCodes(e.target.value)} />
                </Field>
              ) : null}
              {prefixDialogCountry === 'USA' ? (
                <Field label='Note'>
                  <input className='input' value={String(cfg.note || '')} onChange={(e) => patchAllowlistCountry(prefixDialogCountry, { note: e.target.value })} />
                </Field>
              ) : null}
              <div className='muted telnyxFieldHint'>Changes apply when you click <strong>Save</strong> at the top of the page.</div>
            </>
          )
        })() : null}
      </TshDialog>

      <TshDialog
        open={showAddCallRegion}
        onClose={() => setShowAddCallRegion(false)}
        title='Add call region'
        desc='Add a country for the AI voice allowlist.'
        footer={
          <>
            <button type='button' className='tsh-btn tsh-btn-outline' onClick={() => setShowAddCallRegion(false)}>Cancel</button>
            <button
              type='button'
              className='tsh-btn tsh-btn-primary'
              onClick={() => { addCallCountry(); setShowAddCallRegion(false) }}
            >
              Add
            </button>
          </>
        }
      >
        <div className='telnyxGrid2'>
          <Field label='ISO'>
            <input className='input' value={newCallIso} onChange={(e) => setNewCallIso(e.target.value)} placeholder='PS' />
          </Field>
          <Field label='Dial code (no +)'>
            <input className='input' value={newCallDial} onChange={(e) => setNewCallDial(e.target.value)} placeholder='970' />
          </Field>
        </div>
      </TshDialog>
    </div>
  )
}
