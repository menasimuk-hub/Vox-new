import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { providerLabel } from '../lib/integrationsCatalog'
import IntegrationKpiHub from './IntegrationKpiHub'
import IntegrationProviderShell from './IntegrationProviderShell'
import TelnyxIntegration, { compactRouteRows } from './TelnyxIntegration'

const SOCIAL_PROVIDERS = [
  { key: 'google', label: 'Google' },
  { key: 'apple', label: 'Apple' },
  { key: 'linkedin', label: 'LinkedIn' },
]

function defaultSocialProviderState(key) {
  if (key === 'apple') {
    return {
      provider: key,
      exists: false,
      is_enabled: false,
      configured: false,
      updated_at: null,
      missing_fields: ['client_id', 'redirect_uri', 'team_id', 'key_id', 'private_key'],
      config: { client_id: '', redirect_uri: '', team_id: '', key_id: '' },
      secret_set: { private_key: false },
    }
  }
  return {
    provider: key,
    exists: false,
    is_enabled: false,
    configured: false,
    updated_at: null,
    missing_fields: ['client_id', 'client_secret', 'redirect_uri'],
    config: { client_id: '', redirect_uri: '' },
    secret_set: { client_secret: false },
  }
}

const PROVIDERS = [
  { key: 'dentally', label: 'Dentally' },
  { key: 'telnyx', label: 'Telnyx' },
  { key: 'azure_speech', label: 'Azure Speech' },
  { key: 'openai', label: 'OpenAI' },
  { key: 'deepseek', label: 'DeepSeek' },
  { key: 'groq', label: 'Groq' },
  { key: 'deepinfra', label: 'DeepInfra' },
  { key: 'deepgram', label: 'Deepgram' },
  { key: 'cartesia', label: 'Cartesia' },
  { key: 'elevenlabs', label: 'ElevenLabs' },
  { key: 'vapi', label: 'Vapi' },
  { key: 'gocardless', label: 'GoCardless' },
  { key: 'stripe', label: 'Stripe' },
  { key: 'airwallex', label: 'Airwallex' },
  { key: 'zoom', label: 'Zoom' },
  { key: 'calendly', label: 'Calendly' },
  { key: 'cal_com', label: 'Cal.com' },
  { key: 'google_calendar', label: 'Google Calendar' },
  { key: 'microsoft_calendar', label: 'Microsoft 365 Calendar' },
  { key: 'hubspot', label: 'HubSpot' },
]

const VISIBLE_TO_ORGS_PROVIDERS = ['calendly', 'cal_com', 'google_calendar', 'microsoft_calendar', 'hubspot']

const DEFAULT_WEBHOOK_BASE = 'https://localhost'

function joinMissingFields(x) {
  const arr = Array.isArray(x) ? x : []
  if (!arr.length) return ''
  return arr.join(', ')
}

function statusPill(summary) {
  if (!summary) return { cls: 'p-amber', text: 'Loading' }
  if (summary.error) return { cls: 'p-red', text: 'Auth / error' }
  if (!summary.exists) return { cls: 'p-amber', text: 'Not set' }
  if (!summary.is_enabled) return { cls: 'p-amber', text: 'Disabled' }
  if (summary.configured) return { cls: 'p-green', text: 'Configured' }
  return { cls: 'p-amber', text: 'Incomplete' }
}

function openAIValidation(config, draft, summary) {
  const errors = {}
  const hasApiKey = Boolean(summary?.secret_set?.api_key) || Boolean(String(draft?.api_key_draft || '').trim())
  const defaultModel = String(config?.default_model || config?.model || '').trim()
  const realtimeModel = String(config?.realtime_model || '').trim()
  const temperatureRaw = String(config?.temperature ?? '').trim()
  const maxTokensRaw = String(config?.max_output_tokens ?? '').trim()
  const temperature = Number(temperatureRaw)
  const maxTokens = Number(maxTokensRaw)

  if (!hasApiKey) errors.api_key = 'API key is required.'
  if (!defaultModel) errors.default_model = 'Default model is required.'
  if (!realtimeModel) errors.realtime_model = 'Realtime / response model is required.'
  if (!temperatureRaw || Number.isNaN(temperature) || temperature < 0 || temperature > 1) {
    errors.temperature = 'Temperature must be between 0.0 and 1.0.'
  }
  if (!maxTokensRaw || !Number.isInteger(maxTokens) || maxTokens <= 0) {
    errors.max_output_tokens = 'Max output tokens must be a positive integer.'
  }
  return { errors, valid: Object.keys(errors).length === 0 }
}

function azureSpeechValidation(config, draft, summary) {
  const errors = {}
  const hasApiKey = Boolean(summary?.secret_set?.api_key) || Boolean(String(draft?.api_key_draft || '').trim())
  const region = String(config?.region || '').trim()
  const ttsEnabled = config?.tts_enabled == null ? true : Boolean(config.tts_enabled)
  const defaultVoiceId = String(config?.default_voice_id == null ? 'en-GB-AbbiNeural' : config.default_voice_id).trim()

  if (!hasApiKey) errors.api_key = 'API key is required.'
  if (!region) errors.region = 'Region is required.'
  if (ttsEnabled && !defaultVoiceId) errors.default_voice_id = 'Default voice ID is required when TTS is enabled.'
  return { errors, valid: Object.keys(errors).length === 0 }
}

function deepSeekValidation(config, draft, summary) {
  const errors = {}
  const hasApiKey = Boolean(summary?.secret_set?.api_key) || Boolean(String(draft?.api_key_draft || '').trim())
  if (!hasApiKey) errors.api_key = 'API key is required.'
  if (!String(config?.base_url || '').trim()) errors.base_url = 'Base URL is required.'
  if (!String(config?.model || config?.default_model || '').trim()) errors.model = 'Model is required.'
  return { errors, valid: Object.keys(errors).length === 0 }
}

function zoomValidation(config, draft, summary) {
  const errors = {}
  const hasSecret = Boolean(summary?.secret_set?.client_secret) || Boolean(String(draft?.client_secret_draft || '').trim())
  if (!String(config?.account_id || '').trim()) errors.account_id = 'Account ID is required.'
  if (!String(config?.client_id || '').trim()) errors.client_id = 'Client ID is required.'
  if (!hasSecret) errors.client_secret = 'Client secret is required.'
  return { errors, valid: Object.keys(errors).length === 0 }
}

function oauthSchedulingValidation(config, draft, summary) {
  const errors = {}
  const hasSecret = Boolean(summary?.secret_set?.client_secret) || Boolean(String(draft?.client_secret_draft || '').trim())
  if (!String(config?.client_id || '').trim()) errors.client_id = 'Client ID is required.'
  if (!hasSecret) errors.client_secret = 'Client secret is required.'
  if (!String(config?.redirect_uri || '').trim()) errors.redirect_uri = 'Redirect URI is required.'
  return { errors, valid: Object.keys(errors).length === 0 }
}

function hubspotValidation(config, draft, summary) {
  const mode = String(config?.auth_mode || 'private_app').toLowerCase()
  if (mode === 'private_app') {
    return { errors: {}, valid: true }
  }
  return oauthSchedulingValidation(config, draft, summary)
}

function vapiValidation(config, draft, summary) {
  const errors = {}
  const hasPrivateKey = Boolean(summary?.secret_set?.api_key) || Boolean(String(draft?.api_key_draft || '').trim())
  if (!String(config?.public_key || '').trim()) errors.public_key = 'Public key is required for browser calls.'
  if (!String(config?.assistant_id || '').trim()) errors.assistant_id = 'Assistant ID is required for browser calls.'
  if (!hasPrivateKey) errors.api_key = 'Private API key is required for lead transcripts and recordings.'
  return { errors, valid: Object.keys(errors).length === 0 }
}

function deepinfraValidation(config, draft, summary) {
  const errors = {}
  const hasApiKey = Boolean(summary?.secret_set?.api_key) || Boolean(String(draft?.api_key_draft || '').trim())
  if (!hasApiKey) errors.api_key = 'API key is required.'
  if (!String(config?.base_url || '').trim()) errors.base_url = 'Base URL is required.'
  if (!String(config?.model_name || '').trim()) errors.model_name = 'Model name is required.'
  return { errors, valid: Object.keys(errors).length === 0 }
}

function groqValidation(config, draft, summary) {
  const errors = {}
  const hasApiKey = Boolean(summary?.secret_set?.api_key) || Boolean(String(draft?.api_key_draft || '').trim())
  const voice = String(config?.tts_voice || 'austin').trim().toLowerCase()
  if (!hasApiKey) errors.api_key = 'API key is required.'
  if (!String(config?.base_url || '').trim()) errors.base_url = 'Base URL is required.'
  if (String(config?.llm_model || 'llama-3.3-70b-versatile').trim() !== 'llama-3.3-70b-versatile') errors.llm_model = 'Groq LLM must use llama-3.3-70b-versatile.'
  if (String(config?.stt_model || 'whisper-large-v3-turbo').trim() !== 'whisper-large-v3-turbo') errors.stt_model = 'Groq STT must use whisper-large-v3-turbo.'
  if (!['austin', 'hannah', 'diana', 'daniel', 'autumn', 'troy'].includes(voice)) errors.tts_voice = 'Choose an available Orpheus voice.'
  return { errors, valid: Object.keys(errors).length === 0 }
}


function deepgramValidation(config, draft, summary) {
  const errors = {}
  const hasApiKey = Boolean(summary?.secret_set?.api_key) || Boolean(String(draft?.api_key_draft || '').trim())
  const endpointing = Number(config?.endpointing ?? 250)
  if (!hasApiKey) errors.api_key = 'API key is required.'
  if (!String(config?.base_url || '').trim()) errors.base_url = 'Base URL is required.'
  if (!String(config?.ws_url || '').trim()) errors.ws_url = 'WebSocket URL is required.'
  if (!String(config?.model || '').trim()) errors.model = 'Model is required.'
  if (!String(config?.language || '').trim()) errors.language = 'Language is required.'
  if (Number.isNaN(endpointing) || endpointing < 10 || endpointing > 2000) errors.endpointing = 'Endpointing must be between 10 and 2000 ms.'
  return { errors, valid: Object.keys(errors).length === 0 }
}

function cartesiaValidation(config, draft, summary) {
  const errors = {}
  const hasApiKey = Boolean(summary?.secret_set?.api_key) || Boolean(String(draft?.api_key_draft || '').trim())
  const sampleRate = Number(config?.sample_rate ?? 44100)
  if (!hasApiKey) errors.api_key = 'API key is required.'
  if (!String(config?.base_url || '').trim()) errors.base_url = 'Base URL is required.'
  if (!String(config?.model_id || '').trim()) errors.model_id = 'Model ID is required.'
  if (!String(config?.voice_id || '').trim()) errors.voice_id = 'Voice ID is required.'
  if (Number.isNaN(sampleRate) || sampleRate < 8000 || sampleRate > 48000) errors.sample_rate = 'Sample rate must be between 8000 and 48000.'
  return { errors, valid: Object.keys(errors).length === 0 }
}

function elevenLabsValidation(config, draft, summary) {
  const errors = {}
  const hasApiKey = Boolean(summary?.secret_set?.api_key) || Boolean(String(draft?.api_key_draft || '').trim())
  const voiceId = String(config?.default_voice_id || config?.voice_id || '').trim()
  const numberFields = [
    ['stability', 0, 1],
    ['similarity_boost', 0, 1],
    ['style', 0, 1],
    ['speed', 0.7, 1.2],
  ]
  if (!hasApiKey) errors.api_key = 'API key is required.'
  if (!voiceId) errors.default_voice_id = 'Default voice ID is required.'
  numberFields.forEach(([field, min, max]) => {
    const raw = String(config?.[field] ?? '').trim()
    if (!raw) return
    const value = Number(raw)
    if (Number.isNaN(value) || value < min || value > max) errors[field] = `${field.replace('_', ' ')} must be between ${min} and ${max}.`
  })
  return { errors, valid: Object.keys(errors).length === 0 }
}

function httpBaseToWs(base) {
  const clean = String(base || '').replace(/\/+$/, '')
  if (clean.startsWith('https://')) return `wss://${clean.slice(8)}`
  if (clean.startsWith('http://')) return `ws://${clean.slice(7)}`
  return `wss://${clean}`
}

function firstVoiceRouteNumber(config) {
  const routes = Array.isArray(config?.voice_routes) ? config.voice_routes : []
  for (const row of routes) {
    const n = String(row?.number || '').trim()
    if (n) return n
  }
  return ''
}

function telnyxValidation(config, draft, summary) {
  const errors = {}
  const hasDraftKey = Boolean(String(draft?.api_key_draft || '').trim())
  const hasApiKey = Boolean(summary?.secret_set?.api_key) || hasDraftKey
  const meta = summary?.api_key_meta
  if (!hasApiKey) errors.api_key = 'API key is required.'
  else if (!hasDraftKey && meta && meta.length > 0 && !meta.looks_valid) {
    errors.api_key = 'Stored credential is not a Telnyx KEY… API key. Paste the secret key from API Keys and Save.'
  }
  if (!String(config?.connection_id || config?.voice_api_application_id || '').trim()) errors.connection_id = 'Voice API application / connection ID is required.'
  const voiceNumber = String(config?.default_outbound_number || config?.from_phone_number || firstVoiceRouteNumber(config) || '').trim()
  if (!voiceNumber) errors.default_outbound_number = 'Add a voice/landline number in Voice routes or the default field below.'
  const webhookBase = String(config?.webhook_base_url || '').trim()
  if (webhookBase && /^https?:\/\/localhost/i.test(webhookBase)) {
    errors.webhook_base_url = 'For local testing use your ngrok HTTPS URL (not localhost).'
  }
  return { errors, valid: Object.keys(errors).length === 0 }
}

function copyText(value) {
  const text = String(value || '')
  if (!text) return
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).catch(() => {})
  }
}

const invalidInputStyle = { borderColor: 'rgba(220,38,38,0.85)' }

function WebhooksOverview({ summaries }) {
  const telnyx = summaries?.telnyx?.config || {}
  const gc = summaries?.gocardless?.config || {}
  const webhookBase = String(telnyx.webhook_base_url || 'https://your-api-host').replace(/\/+$/, '')

  const rows = [
    { label: 'Telnyx voice', url: telnyx.voice_webhook_url || `${webhookBase}/telnyx/webhooks/voice` },
    { label: 'Telnyx messaging (SMS / WhatsApp)', url: telnyx.messaging_webhook_url || `${webhookBase}/telnyx/webhooks/messages` },
    { label: 'Telnyx call status', url: telnyx.status_callback_url || `${webhookBase}/telnyx/webhooks/status` },
    { label: 'GoCardless billing', url: gc.webhook_url || 'https://your-api-host/webhooks/gocardless' },
    { label: 'Vapi call events', url: 'Configure in Vapi dashboard → Server URL (see Vapi integration)' },
  ]

  return (
    <IntegrationProviderShell summary={null}>
      <div className='card'>
        <div className='cardHead'>
          <h3>Inbound webhook URLs</h3>
          <span className='pill p-cyan'>Reference</span>
        </div>
        <div className='cardBody stack' style={{ gap: 14 }}>
          <div className='note'>
            Paste these URLs into Telnyx, GoCardless, and Vapi. Telnyx URLs update when you save Telnyx with your public API base URL (ngrok or production).
          </div>
          {rows.map((row) => (
            <div key={row.label} className='integrationWebhookRow'>
              <label className='label'>{row.label}</label>
              <code className='integrationWebhookUrl'>{row.url}</code>
            </div>
          ))}
        </div>
      </div>
    </IntegrationProviderShell>
  )
}

function SocialLoginSettings() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [providers, setProviders] = useState(() =>
    Object.fromEntries(SOCIAL_PROVIDERS.map((p) => [p.key, defaultSocialProviderState(p.key)]))
  )

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const rows = await apiFetch('/admin/social-login/providers')
      const next = { ...providers }
      if (Array.isArray(rows)) {
        for (const r of rows) {
          if (r?.provider && next[r.provider]) next[r.provider] = r
        }
      }
      setProviders(next)
    } catch (e) {
      setError(e?.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const setField = (providerKey, field, value) => {
    setProviders((s) => ({
      ...s,
      [providerKey]: {
        ...s[providerKey],
        config: { ...(s[providerKey].config || {}), [field]: value },
      },
    }))
  }

  const setEnabled = (providerKey, enabled) => {
    setProviders((s) => ({
      ...s,
      [providerKey]: { ...s[providerKey], is_enabled: Boolean(enabled) },
    }))
    // Auto-save when toggled
    setTimeout(() => {
      saveProvider(providerKey)
    }, 0)
  }

  const saveProvider = async (providerKey) => {
    setSaving(true)
    setError('')
    try {
      const p = providers[providerKey]
      const config = { ...(p?.config || {}) }
      if (providerKey === 'apple') {
        const draft = String(p?.[`${providerKey}_private_key_draft`] || '').trim()
        if (draft) config.private_key = draft
      } else {
        const draft = String(p?.[`${providerKey}_client_secret_draft`] || '').trim()
        if (draft) config.client_secret = draft
      }

      const updated = await apiFetch(`/admin/social-login/${providerKey}`, {
        method: 'PUT',
        body: JSON.stringify({ is_enabled: Boolean(p?.is_enabled), config }),
      })
      setProviders((s) => ({ ...s, [providerKey]: updated }))
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const updateSecretDraft = (providerKey, field, value) => {
    const secretKey = `${providerKey}_${field}_draft`
    setProviders((s) => ({
      ...s,
      [providerKey]: { ...s[providerKey], [secretKey]: value },
    }))
  }

  return (
    <div className='card'>
      <div className='cardHead'>
        <h3>Providers</h3>
        <span className='pill p-cyan'>Google · Apple · LinkedIn</span>
      </div>
      <div className='cardBody'>
        {error && (
          <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>
            {error}
          </div>
        )}
        {loading ? <div className='note'>Loading…</div> : null}
        {!loading && (
          <div className='stack' style={{ gap: 16 }}>
            {SOCIAL_PROVIDERS.map((sp) => {
              const row = providers[sp.key]
              const pill = statusPill(row)
              const last = row?.updated_at ? new Date(row.updated_at).toLocaleString() : '-'
              const missing = joinMissingFields(row?.missing_fields)
              const isApple = sp.key === 'apple'
              const secretIsSet = isApple
                ? Boolean(row?.secret_set?.private_key)
                : Boolean(row?.secret_set?.client_secret)
              return (
                <div key={sp.key} className='card' style={{ margin: 0 }}>
                  <div className='cardHead'>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                      <h3 style={{ fontSize: 15 }}>{sp.label}</h3>
                      <span className={`pill ${pill.cls}`}>{pill.text}</span>
                    </div>
                    <span className='muted' style={{ fontSize: 12 }}>
                      Updated: {last}
                    </span>
                  </div>
                  <div className='cardBody' style={{ paddingTop: 16 }}>
                    <div className='miniGrid'>
                      <div className='mini'>
                        <label>Status</label>
                        <strong>
                          {row?.exists
                            ? row?.is_enabled
                              ? row?.configured
                                ? 'Configured'
                                : 'Incomplete'
                              : 'Disabled'
                            : 'Not configured'}
                        </strong>
                      </div>
                      <div className='mini'>
                        <label>Last update</label>
                        <strong>{last}</strong>
                      </div>
                      <div className='mini'>
                        <label>Missing</label>
                        <strong>{missing || '-'}</strong>
                      </div>
                      <div className='mini'>
                        <label>{isApple ? 'Private key' : 'Client secret'}</label>
                        <strong>{secretIsSet ? 'Set' : 'Not set'}</strong>
                      </div>
                    </div>

                    <div style={{ display: 'grid', gap: 12, marginTop: 14 }}>
                      <div style={{ display: 'grid', gap: 6 }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                          <label className='label' style={{ margin: 0 }}>
                            Show on sign-in page
                          </label>
                          <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', position: 'relative', width: 50, height: 28 }}>
                            <input
                              type='checkbox'
                              checked={Boolean(row?.is_enabled)}
                              onChange={(e) => setEnabled(sp.key, e.target.checked)}
                              style={{ display: 'none' }}
                            />
                            <span
                              style={{
                                position: 'absolute',
                                top: 0,
                                left: 0,
                                right: 0,
                                bottom: 0,
                                backgroundColor: Boolean(row?.is_enabled) ? '#10b981' : '#d1d5db',
                                borderRadius: '9999px',
                                transition: 'background-color 0.3s ease',
                                border: '1px solid transparent',
                              }}
                            />
                            <span
                              style={{
                                position: 'absolute',
                                top: 2,
                                left: Boolean(row?.is_enabled) ? 24 : 2,
                                width: 24,
                                height: 24,
                                backgroundColor: 'white',
                                borderRadius: '9999px',
                                transition: 'left 0.3s ease',
                                boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                              }}
                            />
                          </label>
                        </div>
                      </div>

                      <div style={{ display: 'grid', gap: 6 }}>
                        <label className='label'>{isApple ? 'Services ID (Client ID)' : 'Client ID'}</label>
                        <input
                          className='input'
                          style={{ width: '100%', minWidth: 0 }}
                          value={String(row?.config?.client_id || '')}
                          onChange={(e) => setField(sp.key, 'client_id', e.target.value)}
                          placeholder={isApple ? 'com.example.web' : 'Client ID'}
                        />
                      </div>

                      {isApple ? (
                        <>
                          <div style={{ display: 'grid', gap: 6 }}>
                            <label className='label'>Team ID</label>
                            <input
                              className='input'
                              style={{ width: '100%', minWidth: 0 }}
                              value={String(row?.config?.team_id || '')}
                              onChange={(e) => setField(sp.key, 'team_id', e.target.value)}
                              placeholder='Apple Developer Team ID'
                            />
                          </div>
                          <div style={{ display: 'grid', gap: 6 }}>
                            <label className='label'>Key ID</label>
                            <input
                              className='input'
                              style={{ width: '100%', minWidth: 0 }}
                              value={String(row?.config?.key_id || '')}
                              onChange={(e) => setField(sp.key, 'key_id', e.target.value)}
                              placeholder='Sign in with Apple key ID'
                            />
                          </div>
                          <div style={{ display: 'grid', gap: 6 }}>
                            <label className='label'>Private key (.p8)</label>
                            <textarea
                              className='input'
                              style={{ width: '100%', minWidth: 0, minHeight: 120, fontFamily: 'monospace' }}
                              value={String(row?.[`${sp.key}_private_key_draft`] || '')}
                              onChange={(e) => updateSecretDraft(sp.key, 'private_key', e.target.value)}
                              placeholder={secretIsSet ? 'Leave blank to keep current key' : 'Paste Apple .p8 private key'}
                            />
                            <div className='muted' style={{ fontSize: 12 }}>
                              Existing keys are never shown. Leave blank to keep the current one.
                            </div>
                          </div>
                        </>
                      ) : (
                        <div style={{ display: 'grid', gap: 6 }}>
                          <label className='label'>Client secret</label>
                          <input
                            className='input'
                            style={{ width: '100%', minWidth: 0 }}
                            type='password'
                            value={String(row?.[`${sp.key}_client_secret_draft`] || '')}
                            onChange={(e) => updateSecretDraft(sp.key, 'client_secret', e.target.value)}
                            placeholder={secretIsSet ? 'Leave blank to keep current' : 'Required'}
                          />
                          <div className='muted' style={{ fontSize: 12 }}>
                            Existing secrets are never shown. Leave blank to keep the current one.
                          </div>
                        </div>
                      )}

                      <div style={{ display: 'grid', gap: 6 }}>
                        <label className='label'>Redirect / callback URL</label>
                        <input
                          className='input'
                          style={{ width: '100%', minWidth: 0 }}
                          value={String(row?.config?.redirect_uri || '')}
                          onChange={(e) => setField(sp.key, 'redirect_uri', e.target.value)}
                          placeholder='Redirect URL'
                        />
                      </div>
                    </div>

                    <div className='actions' style={{ marginTop: 12 }}>
                      <button className='btn soft' onClick={load} disabled={saving}>
                        Reload
                      </button>
                      <button className='btn primary' onClick={() => saveProvider(sp.key)} disabled={saving}>
                        {saving ? 'Saving…' : 'Save'}
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
  )
}

export default function Integrations() {
  const location = useLocation()
  const activeProvider = useMemo(() => {
    const m = location.pathname.match(/^\/integrations\/([^/]+)\/?$/)
    const key = (m?.[1] || '').toLowerCase()
    return PROVIDERS.some((p) => p.key === key) ? key : null
  }, [location.pathname])

  const isSocialLoginRoute = useMemo(() => {
    return /\/integrations\/social-login$/.test(location.pathname)
  }, [location.pathname])

  const isKpiRoute = useMemo(() => {
    return /^\/integrations\/?$/.test(location.pathname) || /\/integrations\/kpi\/?$/.test(location.pathname)
  }, [location.pathname])

  const isWebhooksRoute = useMemo(() => {
    return /\/integrations\/webhooks\/?$/.test(location.pathname)
  }, [location.pathname])

  const [summaries, setSummaries] = useState(() =>
    Object.fromEntries(PROVIDERS.map((p) => [p.key, null]))
  )
  const [providerDrafts, setProviderDrafts] = useState({})
  const [providerSaving, setProviderSaving] = useState(false)
  const [providerError, setProviderError] = useState('')
  const [azureTestResult, setAzureTestResult] = useState('')
  const [openAITestResult, setOpenAITestResult] = useState('')
  const [deepSeekTestResult, setDeepSeekTestResult] = useState('')
  const [zoomTestResult, setZoomTestResult] = useState('')
  const [calendlyTestResult, setCalendlyTestResult] = useState('')
  const [calComTestResult, setCalComTestResult] = useState('')
  const [googleCalendarTestResult, setGoogleCalendarTestResult] = useState('')
  const [microsoftCalendarTestResult, setMicrosoftCalendarTestResult] = useState('')
  const [hubspotTestResult, setHubspotTestResult] = useState('')
  const [groqTestResult, setGroqTestResult] = useState('')
  const [deepinfraTestResult, setDeepinfraTestResult] = useState('')
  const [deepinfraModerationTestResult, setDeepinfraModerationTestResult] = useState('')

  const DEEPINFRA_MODERATION_MODELS = [
    { id: 'mistralai/Mistral-Small-3.2-24B-Instruct-2506', label: 'Mistral Small 3.2 24B (recommended)' },
    { id: 'mistralai/Mistral-Small-24B-Instruct-2501', label: 'Mistral Small 24B 2501 (faster)' },
    { id: 'mistralai/Mistral-Nemo-Instruct-2407', label: 'Mistral Nemo 2407 (budget, multilingual)' },
    { id: 'mistralai/Mistral-7B-Instruct-v0.3', label: 'Mistral 7B (lightweight)' },
    { id: 'mistralai/Mistral-Small-3.1-24B-Instruct-2503', label: 'Mistral Small 3.1 (legacy → 3.2)' },
  ]
  const [deepgramTestResult, setDeepgramTestResult] = useState('')
  const [cartesiaTestResult, setCartesiaTestResult] = useState('')
  const [gocardlessTestResult, setGocardlessTestResult] = useState('')
  const [stripeTestResult, setStripeTestResult] = useState('')
  const [airwallexTestResult, setAirwallexTestResult] = useState('')
  const [vapiTestResult, setVapiTestResult] = useState('')
  const [elevenLabsTestResult, setElevenLabsTestResult] = useState('')
  const [telnyxTestResult, setTelnyxTestResult] = useState('')
  const [telnyxSmsTestResult, setTelnyxSmsTestResult] = useState('')
  const [telnyxMessagingSyncResult, setTelnyxMessagingSyncResult] = useState('')
  const [telnyxZoomTestResult, setTelnyxZoomTestResult] = useState('')
  const [telnyxInboundMessages, setTelnyxInboundMessages] = useState([])
  const [telnyxMessageDetailBusy, setTelnyxMessageDetailBusy] = useState('')
  const [telnyxMessageFilters, setTelnyxMessageFilters] = useState({
    date_from: '',
    date_to: '',
    from_number: '',
    to_number: '',
    q: '',
  })
  const [telnyxTestNumber, setTelnyxTestNumber] = useState('')
  const [telnyxWaTemplateName, setTelnyxWaTemplateName] = useState('')
  const [telnyxWaTemplateId, setTelnyxWaTemplateId] = useState('')
  const [telnyxWaTemplateLang, setTelnyxWaTemplateLang] = useState('en_US')
  const [telnyxWaTemplates, setTelnyxWaTemplates] = useState([])
  const [telnyxWaSyncBusy, setTelnyxWaSyncBusy] = useState(false)
  const [telnyxActiveCallId, setTelnyxActiveCallId] = useState('')
  const [telnyxCallBusy, setTelnyxCallBusy] = useState(false)
  const [telnyxAccountNumbers, setTelnyxAccountNumbers] = useState([])
  const [telnyxNumberHealth, setTelnyxNumberHealth] = useState(null)
  const [telnyxTestFromVoice, setTelnyxTestFromVoice] = useState('')
  const [telnyxTestFromSms, setTelnyxTestFromSms] = useState('')
  const [telnyxTestFromWa, setTelnyxTestFromWa] = useState('')
  const [telnyxTestAllResults, setTelnyxTestAllResults] = useState([])
  const [telnyxTestAllBusy, setTelnyxTestAllBusy] = useState(false)
  const [summariesRefreshing, setSummariesRefreshing] = useState(false)

  const reloadSummaries = useCallback(async () => {
    setSummariesRefreshing(true)
    const next = {}
    await Promise.all(
      PROVIDERS.map(async (p) => {
        try {
          const data = await apiFetch(`/admin/integrations/${p.key}`)
          next[p.key] = data
        } catch (e) {
          next[p.key] = { error: true, message: e?.message || 'Error' }
        }
      })
    )
    setSummaries((s) => ({ ...s, ...next }))
    setSummariesRefreshing(false)
  }, [])

  function formatTelnyxApiError(e) {
    const d = e?.data?.detail
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      const lines = []
      if (d.message) lines.push(String(d.message))
      if (d.hint && d.hint !== d.message) lines.push(String(d.hint))
      if (Array.isArray(d.telnyx_phone_numbers) && d.telnyx_phone_numbers.length) {
        lines.push(`Your Telnyx numbers: ${d.telnyx_phone_numbers.join(', ')}`)
      }
      if (lines.length) return lines.join('\n')
    }
    return e?.message || 'Telnyx request failed'
  }

  function upsertTelnyxRoute(routes, number, label) {
    const list = Array.isArray(routes) ? routes.map((r) => ({ ...r })) : []
    const idx = list.findIndex((r) => String(r?.number || '').trim() === number)
    const row = { number, label, regions: ['global'] }
    if (idx >= 0) list[idx] = { ...list[idx], ...row }
    else {
      const emptyIdx = list.findIndex((r) => !String(r?.number || '').trim())
      if (emptyIdx >= 0) list[emptyIdx] = row
      else list.push(row)
    }
    return list
  }

  function applyTelnyxFromNumber(number, target = 'voice') {
    setProviderDrafts((s) => {
      const saved = summaries.telnyx?.config || {}
      const draft = s.telnyx || {}
      const merged = { ...saved, ...(draft.config || {}) }
      const nextConfig = { ...(draft.config || {}) }
      if (target === 'sms') {
        nextConfig.sms_from = number
      } else if (target === 'whatsapp') {
        nextConfig.whatsapp_from = number
        nextConfig.whatsapp_routes = upsertTelnyxRoute(merged.whatsapp_routes, number, 'WhatsApp')
      } else {
        nextConfig.default_outbound_number = number
        nextConfig.from_phone_number = number
        nextConfig.fallback_caller_id = number
        nextConfig.voice_routes = upsertTelnyxRoute(merged.voice_routes, number, 'Voice')
      }
      return {
        ...s,
        telnyx: { ...draft, config: nextConfig },
      }
    })
  }

  useEffect(() => {
    let cancelled = false
    async function run() {
      const next = {}
      await Promise.all(
        PROVIDERS.map(async (p) => {
          try {
            const data = await apiFetch(`/admin/integrations/${p.key}`)
            next[p.key] = data
          } catch (e) {
            next[p.key] = { error: true, message: e?.message || 'Error' }
          }
        })
      )
      if (!cancelled) setSummaries((s) => ({ ...s, ...next }))
    }
    run()
    return () => {
      cancelled = true
    }
  }, [])

  const setProviderField = (providerKey, field, value) => {
    setProviderDrafts((s) => ({
      ...s,
      [providerKey]: {
        ...(s[providerKey] || {}),
        config: { ...((s[providerKey] || {}).config || {}), [field]: value },
      },
    }))
  }

  const setProviderEnabled = (providerKey, value) => {
    setProviderDrafts((s) => {
      const next = { ...(s[providerKey] || {}), is_enabled: Boolean(value) }
      // Booking/CRM providers: enabling should show on customer dashboards unless admin hides explicitly.
      if (VISIBLE_TO_ORGS_PROVIDERS.includes(providerKey) && Boolean(value)) {
        next.visible_to_orgs = true
      }
      return { ...s, [providerKey]: next }
    })
  }

  const setProviderVisible = (providerKey, value) => {
    setProviderDrafts((s) => ({
      ...s,
      [providerKey]: { ...(s[providerKey] || {}), visible_to_orgs: Boolean(value) },
    }))
  }

  const saveIntegrationProvider = async (providerKey) => {
    setProviderSaving(true)
    setProviderError('')
    try {
      const existing = summaries[providerKey] || {}
      const draft = providerDrafts[providerKey] || {}
      const config = { ...(existing.config || {}), ...(draft.config || {}) }
      if (providerKey === 'gocardless') {
        const token = String(draft.access_token_draft || '').trim()
        if (token) config.access_token = token
        const webhookSecret = String(draft.webhook_secret_draft || '').trim()
        if (webhookSecret) config.webhook_secret = webhookSecret
        for (const key of ['success_redirect_url', 'cancel_redirect_url']) {
          const value = String(config[key] || '').trim()
          const lower = value.toLowerCase()
          const looksInvalid =
            !value ||
            lower.includes('localhost') ||
            lower.includes('127.0.0.1') ||
            lower.includes(':5173') ||
            lower.includes(':5174') ||
            lower.includes(':5175') ||
            (lower.includes('voxbulk.com') && !lower.includes('dashboard.voxbulk.com'))
          if (looksInvalid) delete config[key]
        }
      }
      if (providerKey === 'stripe') {
        const secretKey = String(draft.secret_key_draft || '').trim()
        if (secretKey) config.secret_key = secretKey
        const webhookSecret = String(draft.webhook_secret_draft || '').trim()
        if (webhookSecret) config.webhook_secret = webhookSecret
      }
      if (providerKey === 'airwallex') {
        const apiKey = String(draft.api_key_draft || '').trim()
        if (apiKey) config.api_key = apiKey
        const webhookSecret = String(draft.webhook_secret_draft || '').trim()
        if (webhookSecret) config.webhook_secret = webhookSecret
      }
      if (providerKey === 'telnyx') {
        if (config.default_outbound_number && !config.from_phone_number) config.from_phone_number = config.default_outbound_number
        if (config.from_phone_number && !config.default_outbound_number) config.default_outbound_number = config.from_phone_number
        if (config.connection_id && !config.voice_api_application_id) config.voice_api_application_id = config.connection_id
        if (config.voice_api_application_id && !config.connection_id) config.connection_id = config.voice_api_application_id
        const stripTelnyxPaths = (raw) => {
          let base = String(raw || '').trim().replace(/\/+$/, '')
          for (const suffix of ['/telnyx/webhooks/messages', '/telnyx/webhooks/verified-numbers', '/telnyx/webhooks/status', '/telnyx/webhooks/voice', '/telnyx/media-stream']) {
            if (base.toLowerCase().endsWith(suffix)) base = base.slice(0, -suffix.length).replace(/\/+$/, '')
          }
          return base || DEFAULT_WEBHOOK_BASE
        }
        const webhookBase = stripTelnyxPaths(config.webhook_base_url || config.voice_webhook_url || DEFAULT_WEBHOOK_BASE)
        config.webhook_base_url = webhookBase
        config.messaging_webhook_url = `${webhookBase}/telnyx/webhooks/messages`
        config.voice_webhook_url = `${webhookBase}/telnyx/webhooks/voice`
        config.status_callback_url = `${webhookBase}/telnyx/webhooks/status`
        config.verified_number_webhook_url = `${webhookBase}/telnyx/webhooks/verified-numbers`
        config.media_stream_url = `${httpBaseToWs(webhookBase)}/telnyx/media-stream`
        config.voice_routes = compactRouteRows(config.voice_routes)
        config.whatsapp_routes = compactRouteRows(config.whatsapp_routes)
        if (config.voice_routes.length) {
          const firstVoice = config.voice_routes[0].number
          config.default_outbound_number = firstVoice
          config.from_phone_number = firstVoice
          config.fallback_caller_id = firstVoice
        } else {
          const outbound = String(config.default_outbound_number || config.from_phone_number || '').trim()
          if (outbound) {
            config.default_outbound_number = outbound
            config.from_phone_number = outbound
            config.fallback_caller_id = outbound
          }
        }
        if (config.whatsapp_routes.length) {
          config.whatsapp_from = config.whatsapp_routes[0].number
        }
        const token = String(draft.api_key_draft || '').trim()
        if (token) config.api_key = token
      }
      if (providerKey === 'azure_speech') {
        if (config.default_voice_id == null || String(config.default_voice_id).trim() === '') config.default_voice_id = 'en-GB-AbbiNeural'
        if (config.tts_enabled == null) config.tts_enabled = true
        if (config.stt_enabled == null) config.stt_enabled = false
        const token = String(draft.api_key_draft || '').trim()
        if (token) config.api_key = token
      }
      if (providerKey === 'openai') {
        const token = String(draft.api_key_draft || '').trim()
        if (token) config.api_key = token
      }
      if (providerKey === 'deepseek') {
        if (!config.base_url) config.base_url = 'https://api.deepseek.com'
        if (!config.model) config.model = 'deepseek-chat'
        const token = String(draft.api_key_draft || '').trim()
        if (token) config.api_key = token
      }
      if (providerKey === 'deepinfra') {
        if (!config.integration_name) config.integration_name = 'DeepInfra API'
        if (!config.model_name) config.model_name = 'openai/whisper-large-v3-turbo'
        if (!config.base_url) config.base_url = 'https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo'
        if (config.moderation_enabled == null) config.moderation_enabled = true
        if (!config.moderation_model) config.moderation_model = 'mistralai/Mistral-Small-3.2-24B-Instruct-2506'
        if (!config.moderation_base_url) config.moderation_base_url = 'https://api.deepinfra.com/v1/openai'
        const token = String(draft.api_key_draft || '').trim()
        if (token) config.api_key = token
      }
      if (providerKey === 'groq') {
        if (!config.base_url) config.base_url = 'https://api.groq.com/openai'
        config.llm_model = 'llama-3.3-70b-versatile'
        config.default_llm_model = 'llama-3.3-70b-versatile'
        config.stt_model = 'whisper-large-v3-turbo'
        config.default_stt_model = 'whisper-large-v3-turbo'
        if (!config.tts_model) config.tts_model = 'canopylabs/orpheus-v1-english'
        config.default_tts_model = config.tts_model
        config.tts_voice = ['austin', 'hannah', 'diana', 'daniel', 'autumn', 'troy'].includes(String(config.tts_voice || '').toLowerCase()) ? String(config.tts_voice).toLowerCase() : 'austin'
        config.default_tts_voice = config.tts_voice
        const token = String(draft.api_key_draft || '').trim()
        if (token) config.api_key = token
      }
      if (providerKey === 'deepgram') {
        if (!config.base_url) config.base_url = 'https://api.deepgram.com'
        if (!config.ws_url) config.ws_url = 'wss://api.deepgram.com'
        if (!config.model) config.model = 'nova-3'
        if (!config.language) config.language = 'en'
        if (!config.endpointing) config.endpointing = 250
        if (config.interim_results == null) config.interim_results = true
        const token = String(draft.api_key_draft || '').trim()
        if (token) config.api_key = token
      }
      if (providerKey === 'cartesia') {
        if (!config.base_url) config.base_url = 'https://api.cartesia.ai'
        if (!config.model_id) config.model_id = 'sonic-2'
        if (!config.voice_id) config.voice_id = 'a0e99841-438c-4a64-b679-ae501e7d6091'
        if (!config.container) config.container = 'mp3'
        if (!config.encoding) config.encoding = 'mp3'
        if (!config.sample_rate) config.sample_rate = 44100
        const token = String(draft.api_key_draft || '').trim()
        if (token) config.api_key = token
      }
      if (providerKey === 'vapi') {
        if (!config.base_url) config.base_url = 'https://api.vapi.ai'
        const token = String(draft.api_key_draft || '').trim()
        if (token) config.api_key = token
      }
      if (providerKey === 'elevenlabs') {
        if (!config.base_url) config.base_url = 'https://api.elevenlabs.io'
        if (!config.model_id) config.model_id = 'eleven_multilingual_v2'
        const token = String(draft.api_key_draft || '').trim()
        if (token) config.api_key = token
        if (!config.default_voice_id && config.voice_id) config.default_voice_id = config.voice_id
        if (!config.voice_id && config.default_voice_id) config.voice_id = config.default_voice_id
      }
      if (providerKey === 'zoom') {
        if (!config.base_url) config.base_url = 'https://api.zoom.us/v2'
        const secret = String(draft.client_secret_draft || '').trim()
        if (secret) config.client_secret = secret
      }
      if (providerKey === 'calendly' || providerKey === 'cal_com' || providerKey === 'google_calendar' || providerKey === 'microsoft_calendar' || providerKey === 'hubspot') {
        const secret = String(draft.client_secret_draft || '').trim()
        if (secret) config.client_secret = secret
      }
      if (providerKey === 'microsoft_calendar' && !config.tenant) {
        config.tenant = 'common'
      }
      if (providerKey === 'hubspot' && !config.auth_mode) {
        config.auth_mode = 'private_app'
      }
      const isEnabled = draft.is_enabled == null ? Boolean(existing.is_enabled) : Boolean(draft.is_enabled)
      let visibleToOrgs =
        draft.visible_to_orgs == null ? Boolean(existing.visible_to_orgs) : Boolean(draft.visible_to_orgs)
      if (
        VISIBLE_TO_ORGS_PROVIDERS.includes(providerKey) &&
        isEnabled &&
        draft.visible_to_orgs == null &&
        !existing.visible_to_orgs
      ) {
        visibleToOrgs = true
      }
      const updated = await apiFetch(`/admin/integrations/${providerKey}`, {
        method: 'PUT',
        body: JSON.stringify({
          is_enabled: isEnabled,
          visible_to_orgs: visibleToOrgs,
          config,
        }),
      })
      setSummaries((s) => ({ ...s, [providerKey]: updated }))
      setProviderDrafts((s) => ({ ...s, [providerKey]: {} }))
      if (providerKey === 'azure_speech') setAzureTestResult('')
      if (providerKey === 'openai') setOpenAITestResult('')
      if (providerKey === 'deepseek') setDeepSeekTestResult('')
      if (providerKey === 'groq') setGroqTestResult('')
      if (providerKey === 'deepinfra') setDeepinfraTestResult('')
      if (providerKey === 'deepgram') setDeepgramTestResult('')
      if (providerKey === 'cartesia') setCartesiaTestResult('')
      if (providerKey === 'vapi') setVapiTestResult('')
      if (providerKey === 'elevenlabs') setElevenLabsTestResult('')
      if (providerKey === 'telnyx') setTelnyxTestResult('')
      if (providerKey === 'zoom') setZoomTestResult('')
    } catch (e) {
      setProviderError(e?.message || 'Could not save provider')
    } finally {
      setProviderSaving(false)
    }
  }

  const activeSummary = activeProvider ? summaries[activeProvider] || {} : {}
  const activeDraft = activeProvider ? providerDrafts[activeProvider] || {} : {}
  const activeConfig = { ...(activeSummary.config || {}), ...(activeDraft.config || {}) }
  const activeEnabled = activeDraft.is_enabled == null ? Boolean(activeSummary.is_enabled) : Boolean(activeDraft.is_enabled)
  const activeVisible = activeDraft.visible_to_orgs == null ? Boolean(activeSummary.visible_to_orgs) : Boolean(activeDraft.visible_to_orgs)
  const showActiveVisibilityToggle = VISIBLE_TO_ORGS_PROVIDERS.includes(activeProvider || '')
  const openAIStatus = activeProvider === 'openai' ? openAIValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const azureStatus = activeProvider === 'azure_speech' ? azureSpeechValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const deepSeekStatus = activeProvider === 'deepseek' ? deepSeekValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const zoomStatus = activeProvider === 'zoom' ? zoomValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const calendlyStatus = activeProvider === 'calendly' ? oauthSchedulingValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const calComStatus = activeProvider === 'cal_com' ? oauthSchedulingValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const googleCalendarStatus = activeProvider === 'google_calendar' ? oauthSchedulingValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const microsoftCalendarStatus = activeProvider === 'microsoft_calendar' ? oauthSchedulingValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const hubspotStatus = activeProvider === 'hubspot' ? hubspotValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const groqStatus = activeProvider === 'groq' ? groqValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const deepinfraStatus = activeProvider === 'deepinfra' ? deepinfraValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const deepgramStatus = activeProvider === 'deepgram' ? deepgramValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const cartesiaStatus = activeProvider === 'cartesia' ? cartesiaValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const vapiStatus = activeProvider === 'vapi' ? vapiValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const elevenLabsStatus = activeProvider === 'elevenlabs' ? elevenLabsValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const telnyxStatus = activeProvider === 'telnyx' ? telnyxValidation(activeConfig, activeDraft, activeSummary) : { errors: {}, valid: true }
  const telnyxWebhookBase = String(activeConfig.webhook_base_url || DEFAULT_WEBHOOK_BASE).replace(/\/+$/, '')
  const telnyxWebhookUrl = activeConfig.voice_webhook_url || `${telnyxWebhookBase}/telnyx/webhooks/voice`
  const telnyxMessagingWebhookUrl = activeConfig.messaging_webhook_url || `${telnyxWebhookBase}/telnyx/webhooks/messages`
  const telnyxMediaStreamUrl = activeConfig.media_stream_url || `${httpBaseToWs(telnyxWebhookBase)}/telnyx/media-stream`

  const testAzureSpeechTts = async () => {
    setProviderError('')
    setAzureTestResult('Testing Azure TTS…')
    try {
      const result = await apiFetch('/admin/integrations/azure_speech/test-tts', { method: 'POST' })
      setAzureTestResult(`Azure TTS OK. Generated ${result.audio_bytes || 0} transient audio bytes.`)
    } catch (e) {
      setAzureTestResult('')
      setProviderError(e?.message || 'Azure TTS test failed')
    }
  }

  const testOpenAI = async () => {
    setProviderError('')
    setOpenAITestResult('Testing OpenAI…')
    try {
      const result = await apiFetch('/admin/integrations/openai/test', { method: 'POST' })
      if (!result.ok) {
        const payload = result.openai_payload ? JSON.stringify(result.openai_payload) : `HTTP ${result.status_code || 'error'}`
        setOpenAITestResult(`OpenAI failed: ${payload}`)
        return
      }
      setOpenAITestResult(`OpenAI OK: ${result.assistant_text || '(empty response)'}`)
    } catch (e) {
      setOpenAITestResult('')
      setProviderError(e?.message || 'OpenAI test failed')
    }
  }

  const testDeepSeek = async () => {
    setProviderError('')
    setDeepSeekTestResult('Testing DeepSeek…')
    try {
      const result = await apiFetch('/admin/integrations/deepseek/test', { method: 'POST' })
      if (!result.ok) {
        const payload = result.openai_payload ? JSON.stringify(result.openai_payload) : `HTTP ${result.status_code || 'error'}`
        setDeepSeekTestResult(`DeepSeek failed: ${payload}`)
        return
      }
      setDeepSeekTestResult(`DeepSeek OK: ${result.assistant_text || '(empty response)'}`)
    } catch (e) {
      setDeepSeekTestResult('')
      setProviderError(e?.message || 'DeepSeek test failed')
    }
  }

  const testZoom = async () => {
    setProviderError('')
    setZoomTestResult('Testing Zoom…')
    try {
      const result = await apiFetch('/admin/integrations/zoom/test', { method: 'POST' })
      if (!result.ok) {
        setZoomTestResult(`Zoom failed: ${result.detail || 'Unknown error'}`)
        return
      }
      setZoomTestResult(`Zoom OK: ${result.email || 'connected'}`)
    } catch (e) {
      setZoomTestResult('')
      setProviderError(e?.message || 'Zoom test failed')
    }
  }

  const testCalendly = async () => {
    setProviderError('')
    setCalendlyTestResult('Testing Calendly…')
    try {
      const result = await apiFetch('/admin/integrations/calendly/test', { method: 'POST' })
      setCalendlyTestResult(result.ok ? (result.detail || 'Calendly OK') : (result.detail || 'Calendly check failed'))
    } catch (e) {
      setCalendlyTestResult('')
      setProviderError(e?.message || 'Calendly test failed')
    }
  }

  const testCalCom = async () => {
    setProviderError('')
    setCalComTestResult('Testing Cal.com…')
    try {
      const result = await apiFetch('/admin/integrations/cal-com/test', { method: 'POST' })
      setCalComTestResult(result.ok ? (result.detail || 'Cal.com OK') : (result.detail || 'Cal.com check failed'))
    } catch (e) {
      setCalComTestResult('')
      setProviderError(e?.message || 'Cal.com test failed')
    }
  }

  const testGoogleCalendar = async () => {
    setProviderError('')
    setGoogleCalendarTestResult('Testing Google Calendar…')
    try {
      const result = await apiFetch('/admin/integrations/google-calendar/test', { method: 'POST' })
      setGoogleCalendarTestResult(result.ok ? (result.detail || 'Google Calendar OK') : (result.detail || 'Google Calendar check failed'))
    } catch (e) {
      setGoogleCalendarTestResult('')
      setProviderError(e?.message || 'Google Calendar test failed')
    }
  }

  const testMicrosoftCalendar = async () => {
    setProviderError('')
    setMicrosoftCalendarTestResult('Testing Microsoft Calendar…')
    try {
      const result = await apiFetch('/admin/integrations/microsoft-calendar/test', { method: 'POST' })
      setMicrosoftCalendarTestResult(result.ok ? (result.detail || 'Microsoft Calendar OK') : (result.detail || 'Microsoft Calendar check failed'))
    } catch (e) {
      setMicrosoftCalendarTestResult('')
      setProviderError(e?.message || 'Microsoft Calendar test failed')
    }
  }

  const testHubspot = async () => {
    setProviderError('')
    setHubspotTestResult('Testing HubSpot…')
    try {
      const result = await apiFetch('/admin/integrations/hubspot/test', { method: 'POST' })
      setHubspotTestResult(result.ok ? (result.detail || 'HubSpot OK') : (result.detail || 'HubSpot check failed'))
    } catch (e) {
      setHubspotTestResult('')
      setProviderError(e?.message || 'HubSpot test failed')
    }
  }

  const testDeepinfra = async () => {
    setProviderError('')
    setDeepinfraTestResult('Testing DeepInfra…')
    try {
      const result = await apiFetch('/admin/integrations/deepinfra/test', { method: 'POST' })
      setDeepinfraTestResult(
        result.ok
          ? `DeepInfra OK · model ${result.model_name || 'openai/whisper-large-v3-turbo'} · ${result.response_time_ms || '—'}ms · ${result.last_tested_at || ''}`
          : (result.error || 'DeepInfra check failed'),
      )
    } catch (e) {
      setDeepinfraTestResult('')
      setProviderError(e?.message || 'DeepInfra test failed')
    }
  }

  const testDeepinfraModeration = async () => {
    setProviderError('')
    setDeepinfraModerationTestResult('Testing script moderation…')
    try {
      const result = await apiFetch('/admin/integrations/deepinfra/test-moderation', { method: 'POST' })
      const category = result?.result?.category || 'unknown'
      setDeepinfraModerationTestResult(
        result.ok
          ? `Moderation OK · category ${category}`
          : (result?.result?.reason || 'Moderation test failed'),
      )
    } catch (e) {
      setDeepinfraModerationTestResult('')
      setProviderError(e?.message || 'Moderation test failed')
    }
  }

  const testGroq = async () => {
    setProviderError('')
    setGroqTestResult('Testing Groq?')
    try {
      const result = await apiFetch('/admin/integrations/groq/test', { method: 'POST' })
      setGroqTestResult(`Groq OK: LLM ${result.llm_model || 'llama-3.3-70b-versatile'}, STT ${result.stt_model || 'whisper-large-v3-turbo'}, voice ${result.tts_voice || 'austin'}`)
    } catch (e) {
      setGroqTestResult('')
      setProviderError(e?.message || 'Groq test failed')
    }
  }


  const testDeepgram = async () => {
    setProviderError('')
    setDeepgramTestResult('Testing Deepgram...')
    try {
      const result = await apiFetch('/admin/integrations/deepgram/test', { method: 'POST' })
      setDeepgramTestResult(`Deepgram OK: ${result.model || 'nova-3'} ${result.language || 'en'} partials ${result.interim_results ? 'on' : 'off'}`)
    } catch (e) {
      setDeepgramTestResult('')
      setProviderError(e?.message || 'Deepgram test failed')
    }
  }

  const testCartesia = async () => {
    setProviderError('')
    setCartesiaTestResult('Testing Cartesia...')
    try {
      const result = await apiFetch('/admin/integrations/cartesia/test', { method: 'POST' })
      setCartesiaTestResult(`Cartesia OK. Voice ${result.voice_id || 'default'} generated ${result.audio_bytes || 0} audio bytes.`)
    } catch (e) {
      setCartesiaTestResult('')
      setProviderError(e?.message || 'Cartesia test failed')
    }
  }

  const testGocardless = async () => {
    setProviderError('')
    setGocardlessTestResult('Testing GoCardless sandbox…')
    try {
      const result = await apiFetch('/admin/integrations/gocardless/test', { method: 'POST' })
      const name = result.creditor_name || result.creditor_id || 'creditor'
      setGocardlessTestResult(`GoCardless OK (${result.environment || 'sandbox'}) — ${name}`)
    } catch (e) {
      setGocardlessTestResult('')
      setProviderError(e?.message || 'GoCardless test failed')
    }
  }

  const testStripe = async () => {
    setProviderError('')
    setStripeTestResult('Testing Stripe…')
    try {
      const result = await apiFetch('/admin/integrations/stripe/test', { method: 'POST' })
      const currencies = (result.currencies || []).join(', ') || 'no balances'
      setStripeTestResult(`Stripe OK (${result.environment || 'test'}) — ${currencies}`)
    } catch (e) {
      setStripeTestResult('')
      setProviderError(e?.message || 'Stripe test failed')
    }
  }

  const testAirwallex = async () => {
    setProviderError('')
    setAirwallexTestResult('Testing Airwallex…')
    try {
      const result = await apiFetch('/admin/integrations/airwallex/test', { method: 'POST' })
      setAirwallexTestResult(`Airwallex OK (${result.environment || 'demo'})`)
    } catch (e) {
      setAirwallexTestResult('')
      setProviderError(e?.message || 'Airwallex test failed')
    }
  }

  const testVapi = async () => {
    setProviderError('')
    setVapiTestResult('Testing Vapi…')
    try {
      const result = await apiFetch('/admin/integrations/vapi/test', { method: 'POST' })
      if (result.verified) {
        const parts = []
        if (result.public_key_verified !== false) parts.push('Public key OK (Talk to us / browser)')
        if (result.server_key_verified) parts.push('Private API key OK (server)')
        else if (result.public_key_verified) parts.push('Private API key not set (optional)')
        const name = result.assistant_name || result.assistant_id || 'assistant'
        setVapiTestResult(`${parts.join(' · ')} — ${name}`)
      } else {
        setVapiTestResult(result.message || 'Vapi browser config is present.')
      }
    } catch (e) {
      setVapiTestResult('')
      const hint = e?.data?.detail?.hint || e?.data?.hint
      const base = e?.message || 'Vapi test failed'
      setProviderError(hint ? `${base}\n\n${hint}` : base)
    }
  }

  const testElevenLabs = async () => {
    setProviderError('')
    setElevenLabsTestResult('Testing ElevenLabs TTS…')
    try {
      const result = await apiFetch('/admin/integrations/elevenlabs/test-tts', {
        method: 'POST',
        body: JSON.stringify({ voice_id: activeConfig.default_voice_id || activeConfig.voice_id }),
      })
      setElevenLabsTestResult(`ElevenLabs OK. Voice ${result.voice_id || 'default'} generated ${result.audio_bytes || 0} audio bytes.`)
    } catch (e) {
      setElevenLabsTestResult('')
      setProviderError(e?.message || 'ElevenLabs test failed')
    }
  }

  const verifyTelnyxKey = async () => {
    const apiKey = String(activeDraft.api_key_draft || '').trim()
    if (!apiKey) {
      window.alert('Paste your full Telnyx API key in the field above first.')
      return
    }
    if (apiKey.length < 50) {
      setProviderError(`Key is only ${apiKey.length} characters. Telnyx secret keys are about 58 characters — you copied a partial key.`)
      return
    }
    setProviderError('')
    setTelnyxTestResult('Verifying pasted API key with Telnyx…')
    try {
      const result = await apiFetch('/admin/integrations/telnyx/verify-key', {
        method: 'POST',
        body: JSON.stringify({ api_key: apiKey }),
      })
      setTelnyxTestResult(result.message || `Key OK (${result.length} chars). Now click Save Telnyx.`)
    } catch (e) {
      setTelnyxTestResult('')
      setProviderError(formatTelnyxApiError(e))
    }
  }

  const telnyxHasUnsavedDraft =
    activeProvider === 'telnyx' &&
    Boolean(
      providerDrafts.telnyx &&
        (Object.keys(providerDrafts.telnyx.config || {}).length > 0 || providerDrafts.telnyx.is_enabled !== undefined)
    )

  const testTelnyx = async () => {
    setProviderError('')
    setTelnyxTestResult('Testing Telnyx connection…')
    try {
      const result = await apiFetch('/admin/integrations/telnyx/test', { method: 'POST' })
      if (Array.isArray(result.telnyx_phone_numbers)) setTelnyxAccountNumbers(result.telnyx_phone_numbers)
      setTelnyxNumberHealth({
        configured_checks: result.configured_checks || [],
        inventory_warnings: result.inventory_warnings || [],
        account_inventory: result.account_inventory || [],
      })
      setTelnyxTestResult(result.message || 'Telnyx settings look complete.')
    } catch (e) {
      setTelnyxTestResult('')
      setTelnyxNumberHealth(null)
      setProviderError(formatTelnyxApiError(e))
    }
  }

  const testTelnyxCall = async () => {
    const toNumber = telnyxTestNumber.trim()
    if (!toNumber) {
      window.alert('Enter a destination number for the test call.')
      return
    }
    setProviderError('')
    setTelnyxCallBusy(true)
    setTelnyxTestResult('Starting Telnyx test call…')
    try {
      const payload = { to_number: toNumber }
      if (telnyxTestFromVoice.trim()) payload.from_number = telnyxTestFromVoice.trim()
      const result = await apiFetch('/admin/integrations/telnyx/test-call', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      const callId = String(result.call_control_id || result.external_id || '').trim()
      if (callId) setTelnyxActiveCallId(callId)
      const fromLine = result.from_number ? ` from ${result.from_number}` : ''
      setTelnyxTestResult(
        `${result.message || 'Test call accepted'}${fromLine}${callId ? ` — use Hang up to end (${callId})` : ''}`
      )
    } catch (e) {
      setTelnyxTestResult('')
      const d = e?.data?.detail
      if (d && typeof d === 'object' && Array.isArray(d.telnyx_phone_numbers)) {
        setTelnyxAccountNumbers(d.telnyx_phone_numbers)
      }
      setProviderError(formatTelnyxApiError(e))
    } finally {
      setTelnyxCallBusy(false)
    }
  }

  const hangupTelnyxCall = async () => {
    const callId = telnyxActiveCallId.trim()
    if (!callId) {
      window.alert('No active test call. Place a test call first.')
      return
    }
    setProviderError('')
    setTelnyxCallBusy(true)
    setTelnyxTestResult('Sending hangup…')
    try {
      const result = await apiFetch('/admin/integrations/telnyx/hangup', {
        method: 'POST',
        body: JSON.stringify({ call_control_id: callId }),
      })
      setTelnyxActiveCallId('')
      setTelnyxTestResult(result.message || 'Call ended')
    } catch (e) {
      setProviderError(e?.message || 'Telnyx hangup failed')
    } finally {
      setTelnyxCallBusy(false)
    }
  }

  const testTelnyxSms = async () => {
    const toNumber = telnyxTestNumber.trim()
    if (!toNumber) {
      window.alert('Enter your mobile number in E.164 format (+44…).')
      return
    }
    setProviderError('')
    setTelnyxSmsTestResult('Sending test SMS…')
    try {
      const payload = { to_number: toNumber, body: 'VOXBULK Telnyx SMS test — reply if you received this.' }
      if (telnyxTestFromSms.trim()) payload.from_number = telnyxTestFromSms.trim()
      const result = await apiFetch('/admin/integrations/telnyx/test-sms', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setTelnyxSmsTestResult(`${result.message || 'SMS queued'}${result.external_id ? ` (${result.external_id})` : ''}`)
    } catch (e) {
      setTelnyxSmsTestResult('')
      setProviderError(e?.message || 'Telnyx SMS test failed')
    }
  }

  const syncTelnyxMessagingDestinations = async () => {
    setProviderError('')
    setTelnyxMessagingSyncResult('Saving and syncing messaging destinations to Telnyx…')
    try {
      await saveIntegrationProvider('telnyx')
      const result = await apiFetch('/admin/integrations/telnyx/messaging-destinations/sync-to-telnyx', { method: 'POST' })
      const updated = Array.isArray(result.profiles_updated) ? result.profiles_updated.length : 0
      const dest = Array.isArray(result.whitelisted_destinations) ? result.whitelisted_destinations.join(', ') : '—'
      setTelnyxMessagingSyncResult(`${result.message || 'Synced'}\nProfiles updated: ${updated}\nDestinations: ${dest}`)
      if (Array.isArray(result.errors) && result.errors.length) {
        setTelnyxMessagingSyncResult((prev) => `${prev}\n${result.errors.join('\n')}`)
      }
    } catch (e) {
      setTelnyxMessagingSyncResult('')
      setProviderError(e?.message || 'Could not sync messaging destinations to Telnyx')
    }
  }

  const loadTelnyxWaTemplates = async (silent = false) => {
    try {
      const result = await apiFetch('/admin/integrations/telnyx/whatsapp-templates?approved_only=false')
      const rows = Array.isArray(result.templates) ? result.templates : []
      setTelnyxWaTemplates(rows)
      const approved = rows.filter((t) => String(t.status || '').toUpperCase() === 'APPROVED')
      if (telnyxWaTemplateId && !approved.some((t) => String(t.template_id || '') === telnyxWaTemplateId)) {
        setTelnyxWaTemplateId('')
        setTelnyxWaTemplateName('')
      }
      if (!silent && !rows.length) {
        setTelnyxSmsTestResult('No templates in local cache — click Sync WhatsApp templates to pull from Telnyx.')
      }
    } catch (e) {
      if (!silent) setProviderError(e?.message || 'Could not load WhatsApp templates')
    }
  }

  const syncTelnyxWaTemplates = async () => {
    setTelnyxWaSyncBusy(true)
    setProviderError('')
    setTelnyxSmsTestResult('Syncing WhatsApp templates from Telnyx…')
    try {
      const result = await apiFetch('/admin/integrations/telnyx/whatsapp-templates/sync', { method: 'POST' })
      const rows = Array.isArray(result.templates) ? result.templates : []
      setTelnyxWaTemplates(rows)
      const approved = rows.filter((t) => String(t.status || '').toUpperCase() === 'APPROVED')
      if (telnyxWaTemplateId && !approved.some((t) => String(t.template_id || '') === telnyxWaTemplateId)) {
        setTelnyxWaTemplateId('')
        setTelnyxWaTemplateName('')
      }
      const removed = Number(result.removed || 0)
      const parts = [
        `${result.synced ?? rows.length} template(s) from Telnyx`,
        `${result.approved ?? approved.length} approved`,
      ]
      if (removed > 0) parts.push(`${removed} removed (no longer on Telnyx/Meta)`)
      setTelnyxSmsTestResult(`Sync complete — ${parts.join(' · ')}.`)
    } catch (e) {
      setTelnyxSmsTestResult('')
      setProviderError(e?.message || 'WhatsApp template sync failed')
    } finally {
      setTelnyxWaSyncBusy(false)
    }
  }

  const onSelectTelnyxWaTemplate = (value) => {
    const id = String(value || '').trim()
    setTelnyxWaTemplateId(id)
    const row = telnyxWaTemplates.find((t) => String(t.template_id || '') === id)
    if (row) {
      setTelnyxWaTemplateName(String(row.name || ''))
      setTelnyxWaTemplateLang(String(row.language || 'en_US'))
    } else {
      setTelnyxWaTemplateName('')
    }
  }

  const testTelnyxWhatsApp = async () => {
    const toNumber = telnyxTestNumber.trim()
    if (!toNumber) {
      window.alert('Enter your WhatsApp number in E.164 format (+44…).')
      return
    }
    const templateId = telnyxWaTemplateId.trim()
    const templateName = telnyxWaTemplateName.trim()
    if (!templateId && !templateName && !(telnyxWaTemplates || []).length) {
      const proceed = window.confirm(
        'No WhatsApp template selected and none synced yet.\n\n' +
          'Free-form text only works if you messaged the business number in the last 24 hours. ' +
          'For a first test, click Sync WhatsApp templates, pick an approved template, then try again.\n\n' +
          'Send free-form test anyway?',
      )
      if (!proceed) return
    }
    setProviderError('')
    setTelnyxSmsTestResult('Sending test WhatsApp…')
    try {
      const payload = { to_number: toNumber, body: 'VOXBULK Telnyx WhatsApp test' }
      const lang = telnyxWaTemplateLang.trim() || 'en_US'
      if (templateName) payload.template_name = templateName
      if (templateId) payload.template_id = templateId
      if (templateName || templateId) payload.template_language = lang
      if (telnyxTestFromWa.trim()) payload.from_number = telnyxTestFromWa.trim()
      const result = await apiFetch('/admin/integrations/telnyx/test-whatsapp', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      const tpl = result.template_name
        ? ` · template: ${result.template_name}`
        : result.template_id
          ? ` · template_id=${result.template_id}`
          : ''
      const parts = [
        result.message || 'WhatsApp queued',
        tpl,
        result.external_id ? ` · Telnyx id: ${result.external_id}` : '',
        result.status ? ` · send: ${result.status}` : '',
        result.delivery_status ? ` · delivery: ${result.delivery_status}` : '',
      ].filter(Boolean)
      if (result.delivery_error) {
        setProviderError(`Delivery: ${result.delivery_error}`)
      }
      setTelnyxSmsTestResult(parts.join(''))
      if (result.warning) {
        setProviderError(result.warning)
      }
      const rows = await loadTelnyxInboundMessages(true)
      if (!rows.length && !result.warning) {
        setProviderError(
          'Message was queued at Telnyx but nothing appears in Messages yet. ' +
            'If you used a UK number like 07…, retry after deploy; logging now normalizes numbers. ' +
            'Otherwise sync a template, set webhooks on Messaging Profile + WABA, then Refresh.',
        )
      }
    } catch (e) {
      setTelnyxSmsTestResult('')
      setProviderError(e?.message || 'Telnyx WhatsApp test failed')
    }
  }

  const testTelnyxAllSenders = async () => {
    const toNumber = telnyxTestNumber.trim()
    if (!toNumber) {
      window.alert('Enter a destination number for live tests.')
      return
    }
    const voiceNums = compactRouteRows(activeConfig.voice_routes).map((r) => r.number)
    const waNums = compactRouteRows(activeConfig.whatsapp_routes).map((r) => r.number)
    const smsNum = String(activeConfig.sms_from || '').trim()
    const total = voiceNums.length + waNums.length + (smsNum ? 1 : 0)
    if (!total) {
      window.alert('No configured senders — add numbers to voice/WhatsApp routes or SMS field, then Save.')
      return
    }
    const proceed = window.confirm(
      `This will run ${total} live test(s) to ${toNumber} (${voiceNums.length} voice call(s), ${smsNum ? 1 : 0} SMS, ${waNums.length} WhatsApp). Continue?`
    )
    if (!proceed) return
    setProviderError('')
    setTelnyxTestAllBusy(true)
    setTelnyxTestAllResults([])
    setTelnyxTestResult('Testing all configured numbers…')
    try {
      const result = await apiFetch('/admin/integrations/telnyx/test-all-senders', {
        method: 'POST',
        body: JSON.stringify({ to_number: toNumber, channels: ['voice', 'sms', 'whatsapp'] }),
      })
      setTelnyxTestAllResults(Array.isArray(result.results) ? result.results : [])
      setTelnyxTestResult(result.message || 'Test all senders complete.')
      const lastCall = (result.results || []).find((r) => r.role === 'voice' && r.ok && r.call_control_id)
      if (lastCall?.call_control_id) setTelnyxActiveCallId(String(lastCall.call_control_id))
    } catch (e) {
      setTelnyxTestResult('')
      setProviderError(formatTelnyxApiError(e))
    } finally {
      setTelnyxTestAllBusy(false)
    }
  }

  const testTelnyxZoom = async () => {
    setProviderError('')
    setTelnyxZoomTestResult('Testing Zoom connection via Telnyx…')
    try {
      const result = await apiFetch('/admin/integrations/telnyx/test-zoom', { method: 'POST' })
      if (result.ok) {
        const provider = result.meeting_provider === 'telnyx_zoom' ? 'Telnyx' : 'Zoom OAuth'
        setTelnyxZoomTestResult(
          `✓ ${provider} · Meeting ID: ${result.meeting_id || '—'} · ${result.message || 'Connection verified'}`,
        )
      } else {
        setTelnyxZoomTestResult(`✗ Zoom failed: ${result.detail || 'Unknown error'}`)
      }
    } catch (e) {
      setTelnyxZoomTestResult('')
      setProviderError(e?.message || 'Telnyx Zoom test failed')
    }
  }

  const loadTelnyxInboundMessages = async (silent = false, filters = telnyxMessageFilters) => {
    if (!silent) {
      setProviderError('')
      setTelnyxSmsTestResult('Loading messages…')
    }
    try {
      const params = new URLSearchParams({ limit: '50' })
      if (filters?.date_from) params.set('date_from', new Date(filters.date_from).toISOString())
      if (filters?.date_to) params.set('date_to', new Date(filters.date_to).toISOString())
      if (filters?.from_number) params.set('from_number', String(filters.from_number).trim())
      if (filters?.to_number) params.set('to_number', String(filters.to_number).trim())
      if (filters?.q) params.set('q', String(filters.q).trim())
      const result = await apiFetch(`/admin/integrations/telnyx/inbound-messages?${params.toString()}`)
      const rows = Array.isArray(result.messages) ? result.messages : []
      setTelnyxInboundMessages(rows)
      if (!silent) {
        setTelnyxSmsTestResult(
          rows.length
            ? `Loaded ${rows.length} message(s) (inbound + outbound).`
            : 'No messages in log yet — run Test WhatsApp or receive a reply, then Refresh.',
        )
      }
      return rows
    } catch (e) {
      setTelnyxInboundMessages([])
      if (!silent) {
        setTelnyxSmsTestResult('')
        setProviderError(e?.message || 'Could not load messages')
      }
      return []
    }
  }

  const fetchTelnyxMessageDetail = async (messageId) => {
    const mid = String(messageId || '').trim()
    if (!mid) return
    setProviderError('')
    setTelnyxMessageDetailBusy(mid)
    try {
      const detail = await apiFetch(`/admin/integrations/telnyx/messages/${encodeURIComponent(mid)}`)
      const errLines = Array.isArray(detail.errors)
        ? detail.errors
            .map((e) => {
              const code = String(e?.code || '').trim()
              const text = String(e?.detail || e?.title || '').trim()
              const meta = e?.meta && typeof e.meta === 'object' ? e.meta : {}
              const metaBits = ['whatsapp_error_code', 'whatsapp_error_title', 'error_user_msg', 'error_user_title', 'reason', 'message']
                .map((k) => String(meta[k] || '').trim())
                .filter(Boolean)
              const base = code && text ? `${code}: ${text}` : text || code
              return metaBits.length ? `${base}\n  Meta: ${metaBits.join(' · ')}` : base
            })
            .filter(Boolean)
        : []
      const summary = [
        `Telnyx message ${detail.id || mid}`,
        `Status: ${detail.status || 'unknown'}`,
        detail.error_summary ? `Error: ${detail.error_summary}` : null,
        errLines.length ? `Errors:\n${errLines.join('\n')}` : null,
      ]
        .filter(Boolean)
        .join('\n')
      window.alert(summary || 'No extra details from Telnyx.')
      await loadTelnyxInboundMessages(true)
    } catch (e) {
      setProviderError(e?.message || 'Telnyx message lookup failed')
    } finally {
      setTelnyxMessageDetailBusy('')
    }
  }

  useEffect(() => {
    if (activeProvider !== 'telnyx') return
    if (!summaries.telnyx?.exists) return
    loadTelnyxInboundMessages(true)
    loadTelnyxWaTemplates(true)
  }, [activeProvider, summaries.telnyx?.exists])

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>
            {isSocialLoginRoute
              ? 'Social Login'
              : isKpiRoute
                ? 'Integration KPI'
                : isWebhooksRoute
                  ? 'Webhooks'
                  : activeProvider === 'telnyx'
                    ? 'Telnyx'
                    : activeProvider
                      ? providerLabel(activeProvider)
                      : 'Integrations'}
          </h1>
          {isSocialLoginRoute ? (
            <p>Configure social login providers and control their availability on the public sign-in page.</p>
          ) : isKpiRoute ? (
            <p>Overview of every integration — green when enabled and connected, red when setup is incomplete.</p>
          ) : isWebhooksRoute ? (
            <p>Inbound webhook endpoints for Telnyx, GoCardless, and third-party callbacks.</p>
          ) : activeProvider === 'telnyx' ? (
            <p>Voice, SMS, and WhatsApp — credentials, phone numbers, webhooks, testing, and received messages.</p>
          ) : activeProvider ? (
            <p>Credentials, enable toggle, connection test, and status for {providerLabel(activeProvider)}.</p>
          ) : (
            <p>Integration settings and connection status.</p>
          )}
        </div>
        <div className='actions'>
          {!isKpiRoute && !isSocialLoginRoute ? (
            <Link to='/integrations/kpi' className='btn soft'>
              <i className='ti ti-layout-grid' /> KPI overview
            </Link>
          ) : null}
          <button className='btn' onClick={isKpiRoute ? reloadSummaries : () => window.location.reload()} disabled={summariesRefreshing}>
            {summariesRefreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {isSocialLoginRoute ? (
        <div className='pageShell integrationPageShell'>
          <IntegrationProviderShell summary={null}>
            <div className='stack'>
              <SocialLoginSettings />
              <div className='card'>
                <div className='cardHead'>
                  <h3>Security</h3>
                  <span className='pill p-cyan'>Secrets</span>
                </div>
                <div className='cardBody'>
                  <div className='note'>
                    Client secrets are accepted when saving but are never returned to the browser. Leave the secret field
                    blank to keep the current one.
                  </div>
                </div>
              </div>
            </div>
          </IntegrationProviderShell>
        </div>
      ) : activeProvider === 'telnyx' ? (
        <div className='pageShell telnyxPageShell'>
          <TelnyxIntegration
          activeSummary={activeSummary}
          activeConfig={activeConfig}
          activeDraft={activeDraft}
          activeEnabled={activeEnabled}
          telnyxStatus={telnyxStatus}
          telnyxWebhookUrl={telnyxWebhookUrl}
          telnyxMessagingWebhookUrl={telnyxMessagingWebhookUrl}
          telnyxMediaStreamUrl={telnyxMediaStreamUrl}
          telnyxTestNumber={telnyxTestNumber}
          setTelnyxTestNumber={setTelnyxTestNumber}
          telnyxWaTemplateName={telnyxWaTemplateName}
          setTelnyxWaTemplateName={setTelnyxWaTemplateName}
          telnyxWaTemplateId={telnyxWaTemplateId}
          telnyxWaTemplates={telnyxWaTemplates}
          telnyxWaSyncBusy={telnyxWaSyncBusy}
          onSelectTelnyxWaTemplate={onSelectTelnyxWaTemplate}
          syncTelnyxWaTemplates={syncTelnyxWaTemplates}
          loadTelnyxWaTemplates={loadTelnyxWaTemplates}
          telnyxWaTemplateLang={telnyxWaTemplateLang}
          setTelnyxWaTemplateLang={setTelnyxWaTemplateLang}
          telnyxTestResult={telnyxTestResult}
          telnyxSmsTestResult={telnyxSmsTestResult}
          telnyxMessagingSyncResult={telnyxMessagingSyncResult}
          telnyxZoomTestResult={telnyxZoomTestResult}
          telnyxInboundMessages={telnyxInboundMessages}
          telnyxMessageDetailBusy={telnyxMessageDetailBusy}
          fetchTelnyxMessageDetail={fetchTelnyxMessageDetail}
          telnyxActiveCallId={telnyxActiveCallId}
          telnyxCallBusy={telnyxCallBusy}
          telnyxAccountNumbers={telnyxAccountNumbers}
          telnyxNumberHealth={telnyxNumberHealth}
          telnyxHasUnsavedDraft={telnyxHasUnsavedDraft}
          telnyxTestFromVoice={telnyxTestFromVoice}
          setTelnyxTestFromVoice={setTelnyxTestFromVoice}
          telnyxTestFromSms={telnyxTestFromSms}
          setTelnyxTestFromSms={setTelnyxTestFromSms}
          telnyxTestFromWa={telnyxTestFromWa}
          setTelnyxTestFromWa={setTelnyxTestFromWa}
          telnyxTestAllResults={telnyxTestAllResults}
          telnyxTestAllBusy={telnyxTestAllBusy}
          testTelnyxAllSenders={testTelnyxAllSenders}
          providerError={providerError}
          providerSaving={providerSaving}
          defaultWebhookBase={DEFAULT_WEBHOOK_BASE}
          setProviderEnabled={setProviderEnabled}
          setProviderField={setProviderField}
          setProviderDrafts={setProviderDrafts}
          applyTelnyxFromNumber={applyTelnyxFromNumber}
          saveIntegrationProvider={saveIntegrationProvider}
          testTelnyx={testTelnyx}
          testTelnyxCall={testTelnyxCall}
          hangupTelnyxCall={hangupTelnyxCall}
          testTelnyxZoom={testTelnyxZoom}
          testTelnyxSms={testTelnyxSms}
          syncTelnyxMessagingDestinations={syncTelnyxMessagingDestinations}
          testTelnyxWhatsApp={testTelnyxWhatsApp}
          loadTelnyxInboundMessages={() => loadTelnyxInboundMessages(false)}
          telnyxMessageFilters={telnyxMessageFilters}
          setTelnyxMessageFilters={setTelnyxMessageFilters}
          />
        </div>
      ) : isKpiRoute ? (
        <div className='pageShell integrationPageShell'>
          <IntegrationKpiHub summaries={summaries} loading={summariesRefreshing} onRefresh={reloadSummaries} />
        </div>
      ) : isWebhooksRoute ? (
        <div className='pageShell integrationPageShell'>
          <WebhooksOverview summaries={summaries} />
        </div>
      ) : activeProvider ? (
        <div className='pageShell integrationPageShell'>
          <IntegrationProviderShell
            summary={activeSummary}
            providerError={providerError}
            showVisibilityToggle={showActiveVisibilityToggle}
            visibleToOrgs={activeVisible}
            onVisibleToOrgsChange={showActiveVisibilityToggle ? ((value) => setProviderVisible(activeProvider, value)) : undefined}
          >
            <div className='stack'>
            {activeProvider === 'azure_speech' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>Azure Speech setup</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('azure_speech', e.target.checked)} />
                      <span>Enable Azure Speech STT/TTS</span>
                    </label>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>API key</label>
                      <input className='input' style={azureStatus.errors.api_key ? invalidInputStyle : undefined} type='password' value={String(activeDraft.api_key_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, azure_speech: { ...(s.azure_speech || {}), api_key_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.api_key ? 'Leave blank to keep current key' : 'Paste Azure Speech key'} />
                      {azureStatus.errors.api_key ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{azureStatus.errors.api_key}</div> : null}
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Region</label>
                      <input className='input' style={azureStatus.errors.region ? invalidInputStyle : undefined} value={String(activeConfig.region || '')} onChange={(e) => setProviderField('azure_speech', 'region', e.target.value)} placeholder='uksouth' />
                      {azureStatus.errors.region ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{azureStatus.errors.region}</div> : null}
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>British female voice ID</label>
                      <input className='input' style={azureStatus.errors.default_voice_id ? invalidInputStyle : undefined} value={String(activeConfig.default_voice_id == null ? 'en-GB-AbbiNeural' : activeConfig.default_voice_id)} onChange={(e) => setProviderField('azure_speech', 'default_voice_id', e.target.value)} />
                      {azureStatus.errors.default_voice_id ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{azureStatus.errors.default_voice_id}</div> : null}
                    </div>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeConfig.stt_enabled === true} onChange={(e) => setProviderField('azure_speech', 'stt_enabled', e.target.checked)} />
                      <span>Enable Azure speech-to-text</span>
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeConfig.tts_enabled !== false} onChange={(e) => setProviderField('azure_speech', 'tts_enabled', e.target.checked)} />
                      <span>Enable Azure text-to-speech</span>
                    </label>
                    {!azureStatus.valid ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.35)' }}>Complete the required Azure Speech fields before saving.</div> : null}
                    {azureTestResult ? <div className='note'>{azureTestResult}</div> : null}
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('azure_speech')} disabled={providerSaving || !azureStatus.valid}>
                        {providerSaving ? 'Saving…' : 'Save Azure Speech'}
                      </button>
                      <button className='btn soft' onClick={testAzureSpeechTts} disabled={providerSaving || !activeSummary.configured}>
                        Test Azure TTS
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ) : activeProvider === 'openai' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>OpenAI live call setup</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('openai', e.target.checked)} />
                      <span>Enable OpenAI call reasoning</span>
                    </label>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>API key</label>
                      <input className='input' style={openAIStatus.errors.api_key ? invalidInputStyle : undefined} type='password' value={String(activeDraft.api_key_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, openai: { ...(s.openai || {}), api_key_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.api_key ? 'Leave blank to keep current key' : 'Paste OpenAI API key'} />
                      {openAIStatus.errors.api_key ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{openAIStatus.errors.api_key}</div> : null}
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Default model</label>
                      <input className='input' style={openAIStatus.errors.default_model ? invalidInputStyle : undefined} value={String(activeConfig.default_model || activeConfig.model || '')} onChange={(e) => { setProviderField('openai', 'default_model', e.target.value); setProviderField('openai', 'model', e.target.value) }} placeholder='gpt-realtime-1.5' />
                      {openAIStatus.errors.default_model ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{openAIStatus.errors.default_model}</div> : null}
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Realtime / response model</label>
                      <input className='input' style={openAIStatus.errors.realtime_model ? invalidInputStyle : undefined} value={String(activeConfig.realtime_model || '')} onChange={(e) => setProviderField('openai', 'realtime_model', e.target.value)} placeholder='gpt-realtime-1.5' />
                      {openAIStatus.errors.realtime_model ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{openAIStatus.errors.realtime_model}</div> : null}
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Base URL</label>
                      <input className='input' value={String(activeConfig.base_url || 'https://api.openai.com')} onChange={(e) => setProviderField('openai', 'base_url', e.target.value)} />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Temperature</label>
                      <input className='input' style={openAIStatus.errors.temperature ? invalidInputStyle : undefined} value={String(activeConfig.temperature ?? '')} onChange={(e) => setProviderField('openai', 'temperature', e.target.value)} placeholder='0.4' />
                      {openAIStatus.errors.temperature ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{openAIStatus.errors.temperature}</div> : null}
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Max output tokens</label>
                      <input className='input' style={openAIStatus.errors.max_output_tokens ? invalidInputStyle : undefined} value={String(activeConfig.max_output_tokens || '')} onChange={(e) => setProviderField('openai', 'max_output_tokens', e.target.value)} placeholder='500' />
                      {openAIStatus.errors.max_output_tokens ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{openAIStatus.errors.max_output_tokens}</div> : null}
                    </div>
                    {!openAIStatus.valid ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.35)' }}>Complete all required OpenAI fields before saving.</div> : null}
                    {openAITestResult ? <div className='note'>{openAITestResult}</div> : null}
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('openai')} disabled={providerSaving || !openAIStatus.valid}>
                        {providerSaving ? 'Saving…' : 'Save OpenAI'}
                      </button>
                      <button className='btn soft' onClick={testOpenAI} disabled={providerSaving || !activeSummary.configured}>
                        Test OpenAI
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ) : activeProvider === 'deepseek' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>DeepSeek demo setup</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('deepseek', e.target.checked)} />
                      <span>Enable DeepSeek for demo comparison</span>
                    </label>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>API key</label>
                      <input className='input' style={deepSeekStatus.errors.api_key ? invalidInputStyle : undefined} type='password' value={String(activeDraft.api_key_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, deepseek: { ...(s.deepseek || {}), api_key_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.api_key ? 'Leave blank to keep current key' : 'Paste DeepSeek API key'} />
                      {deepSeekStatus.errors.api_key ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{deepSeekStatus.errors.api_key}</div> : null}
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Base URL</label>
                      <input className='input' style={deepSeekStatus.errors.base_url ? invalidInputStyle : undefined} value={String(activeConfig.base_url || 'https://api.deepseek.com')} onChange={(e) => setProviderField('deepseek', 'base_url', e.target.value)} />
                      {deepSeekStatus.errors.base_url ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{deepSeekStatus.errors.base_url}</div> : null}
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Model</label>
                      <input className='input' style={deepSeekStatus.errors.model ? invalidInputStyle : undefined} value={String(activeConfig.model || activeConfig.default_model || 'deepseek-chat')} onChange={(e) => { setProviderField('deepseek', 'model', e.target.value); setProviderField('deepseek', 'default_model', e.target.value) }} />
                      {deepSeekStatus.errors.model ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{deepSeekStatus.errors.model}</div> : null}
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Temperature</label>
                      <input className='input' value={String(activeConfig.temperature ?? '0.45')} onChange={(e) => setProviderField('deepseek', 'temperature', e.target.value)} />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Max output tokens</label>
                      <input className='input' value={String(activeConfig.max_output_tokens || '120')} onChange={(e) => setProviderField('deepseek', 'max_output_tokens', e.target.value)} />
                    </div>
                    {!deepSeekStatus.valid ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.35)' }}>Complete the required DeepSeek fields before saving.</div> : null}
                    {deepSeekTestResult ? <div className='note'>{deepSeekTestResult}</div> : null}
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('deepseek')} disabled={providerSaving || !deepSeekStatus.valid}>
                        {providerSaving ? 'Saving…' : 'Save DeepSeek'}
                      </button>
                      <button className='btn soft' onClick={testDeepSeek} disabled={providerSaving || !activeSummary.configured}>
                        Test DeepSeek
                      </button>
                    </div>
                    <div className='note'>Use this in `/ai/agent-demo` by selecting DeepSeek. Voice still uses Azure Speech for fair LLM comparison.</div>
                  </div>
                </div>
              </div>
            ) : activeProvider === 'groq' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>Groq voice setup</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('groq', e.target.checked)} />
                      <span>Enable Groq for STT, LLM, and Orpheus TTS</span>
                    </label>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Groq API key</label>
                      <input className='input' style={groqStatus.errors.api_key ? invalidInputStyle : undefined} type='password' value={String(activeDraft.api_key_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, groq: { ...(s.groq || {}), api_key_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.api_key ? 'Leave blank to keep current key' : 'Paste Groq API key'} />
                      {groqStatus.errors.api_key ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{groqStatus.errors.api_key}</div> : null}
                    </div>
                    <label className='label'>Base URL</label>
                    <input className='input' style={groqStatus.errors.base_url ? invalidInputStyle : undefined} value={String(activeConfig.base_url || 'https://api.groq.com/openai')} onChange={(e) => setProviderField('groq', 'base_url', e.target.value)} />
                    <label className='label'>LLM model</label>
                    <input className='input' readOnly value='llama-3.3-70b-versatile' />
                    <label className='label'>Whisper STT model</label>
                    <input className='input' readOnly value='whisper-large-v3-turbo' />
                    <div className='muted' style={{ fontSize: 12 }}>Groq STT requests force language=&quot;en&quot;.</div>
                    <label className='label'>Orpheus TTS model</label>
                    <input className='input' value={String(activeConfig.tts_model || 'canopylabs/orpheus-v1-english')} onChange={(e) => setProviderField('groq', 'tts_model', e.target.value)} />
                    <label className='label'>Default Orpheus voice</label>
                    <select className='input' value={String(activeConfig.tts_voice || 'austin')} onChange={(e) => setProviderField('groq', 'tts_voice', e.target.value)}>
                      {['austin', 'hannah', 'diana', 'daniel', 'autumn', 'troy'].map((voice) => (
                        <option key={voice} value={voice}>{voice}</option>
                      ))}
                    </select>
                    {!groqStatus.valid ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.35)' }}>Complete the required Groq fields before saving.</div> : null}
                    {groqTestResult ? <div className='note'>{groqTestResult}</div> : null}
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('groq')} disabled={providerSaving || !groqStatus.valid}>
                        {providerSaving ? 'Saving?' : 'Save Groq'}
                      </button>
                      <button className='btn soft' onClick={testGroq} disabled={providerSaving || !activeSummary.configured}>
                        Test Groq
                      </button>
                    </div>
                  </div>
                </div>
              </div>

            ) : activeProvider === 'deepinfra' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>DeepInfra WA voice-note STT</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('deepinfra', e.target.checked)} />
                      <span>Enable DeepInfra Whisper STT for WA survey open-text voice notes</span>
                    </label>
                    <label className='label'>Integration name</label>
                    <input className='input' value={String(activeConfig.integration_name || 'DeepInfra API')} onChange={(e) => setProviderField('deepinfra', 'integration_name', e.target.value)} />
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>DeepInfra API key</label>
                      <input className='input' style={deepinfraStatus.errors.api_key ? invalidInputStyle : undefined} type='password' value={String(activeDraft.api_key_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, deepinfra: { ...(s.deepinfra || {}), api_key_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.api_key ? 'Leave blank to keep current key' : 'Paste DeepInfra API key'} />
                    </div>
                    <label className='label'>Base URL</label>
                    <input className='input' style={deepinfraStatus.errors.base_url ? invalidInputStyle : undefined} value={String(activeConfig.base_url || 'https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo')} onChange={(e) => setProviderField('deepinfra', 'base_url', e.target.value)} />
                    <label className='label'>Model name</label>
                    <input className='input' style={deepinfraStatus.errors.model_name ? invalidInputStyle : undefined} value={String(activeConfig.model_name || 'openai/whisper-large-v3-turbo')} onChange={(e) => setProviderField('deepinfra', 'model_name', e.target.value)} />
                    <div className='note' style={{ marginTop: 8 }}>Script content moderation (EU Mistral)</div>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input
                        type='checkbox'
                        checked={activeConfig.moderation_enabled !== false}
                        onChange={(e) => setProviderField('deepinfra', 'moderation_enabled', e.target.checked)}
                      />
                      <span>Scan interview and survey scripts before approval (DeepInfra chat API)</span>
                    </label>
                    <label className='label'>Moderation model</label>
                    <select
                      className='input'
                      value={String(activeConfig.moderation_model || 'mistralai/Mistral-Small-3.2-24B-Instruct-2506')}
                      onChange={(e) => setProviderField('deepinfra', 'moderation_model', e.target.value)}
                    >
                      {DEEPINFRA_MODERATION_MODELS.map((m) => (
                        <option key={m.id} value={m.id}>{m.label}</option>
                      ))}
                    </select>
                    <label className='label'>Moderation base URL</label>
                    <input
                      className='input'
                      value={String(activeConfig.moderation_base_url || 'https://api.deepinfra.com/v1/openai')}
                      onChange={(e) => setProviderField('deepinfra', 'moderation_base_url', e.target.value)}
                    />
                    {deepinfraModerationTestResult ? <div className='note'>{deepinfraModerationTestResult}</div> : null}
                    {activeConfig.last_tested_at ? (
                      <div className='muted' style={{ fontSize: 12 }}>
                        Last tested {String(activeConfig.last_tested_at)} · {String(activeConfig.last_test_status || '—')}
                        {activeConfig.last_test_response_time_ms ? ` · ${activeConfig.last_test_response_time_ms}ms` : ''}
                      </div>
                    ) : null}
                    {!deepinfraStatus.valid ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.35)' }}>Complete the required DeepInfra fields before saving.</div> : null}
                    {deepinfraTestResult ? <div className='note'>{deepinfraTestResult}</div> : null}
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('deepinfra')} disabled={providerSaving || !deepinfraStatus.valid}>
                        {providerSaving ? 'Saving…' : 'Save DeepInfra'}
                      </button>
                      <button className='btn soft' onClick={testDeepinfra} disabled={providerSaving || !activeSummary.configured}>
                        Test connection
                      </button>
                      <button className='btn soft' onClick={testDeepinfraModeration} disabled={providerSaving || !activeSummary.configured}>
                        Test moderation
                      </button>
                    </div>
                    <div className='note'>Used internally when respondents send voice notes on open-text WA survey questions. No customer billing is applied for DeepInfra usage.</div>
                  </div>
                </div>
              </div>

            ) : activeProvider === 'deepgram' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>Deepgram realtime STT setup</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('deepgram', e.target.checked)} />
                      <span>Enable Deepgram streaming speech-to-text</span>
                    </label>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Deepgram API key</label>
                      <input className='input' style={deepgramStatus.errors.api_key ? invalidInputStyle : undefined} type='password' value={String(activeDraft.api_key_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, deepgram: { ...(s.deepgram || {}), api_key_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.api_key ? 'Leave blank to keep current key' : 'Paste Deepgram API key'} />
                    </div>
                    <label className='label'>REST base URL</label>
                    <input className='input' style={deepgramStatus.errors.base_url ? invalidInputStyle : undefined} value={String(activeConfig.base_url || 'https://api.deepgram.com')} onChange={(e) => setProviderField('deepgram', 'base_url', e.target.value)} />
                    <label className='label'>WebSocket URL</label>
                    <input className='input' style={deepgramStatus.errors.ws_url ? invalidInputStyle : undefined} value={String(activeConfig.ws_url || 'wss://api.deepgram.com')} onChange={(e) => setProviderField('deepgram', 'ws_url', e.target.value)} />
                    <label className='label'>Model</label>
                    <input className='input' style={deepgramStatus.errors.model ? invalidInputStyle : undefined} value={String(activeConfig.model || 'nova-3')} onChange={(e) => setProviderField('deepgram', 'model', e.target.value)} />
                    <label className='label'>Language</label>
                    <input className='input' style={deepgramStatus.errors.language ? invalidInputStyle : undefined} value={String(activeConfig.language || 'en')} onChange={(e) => setProviderField('deepgram', 'language', e.target.value)} />
                    <label className='label'>Endpointing (ms)</label>
                    <input className='input' style={deepgramStatus.errors.endpointing ? invalidInputStyle : undefined} value={String(activeConfig.endpointing || '250')} onChange={(e) => setProviderField('deepgram', 'endpointing', e.target.value)} />
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeConfig.interim_results !== false} onChange={(e) => setProviderField('deepgram', 'interim_results', e.target.checked)} />
                      <span>Stream partial transcripts</span>
                    </label>
                    {!deepgramStatus.valid ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.35)' }}>Complete the required Deepgram fields before saving.</div> : null}
                    {deepgramTestResult ? <div className='note'>{deepgramTestResult}</div> : null}
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('deepgram')} disabled={providerSaving || !deepgramStatus.valid}>{providerSaving ? 'Saving...' : 'Save Deepgram'}</button>
                      <button className='btn soft' onClick={testDeepgram} disabled={providerSaving || !activeSummary.configured}>Test connection</button>
                    </div>
                    <div className='note'>The demo backend exposes a WebSocket proxy at `/admin/demo/stt/deepgram/stream` so API keys stay server-side while the browser receives partial/final transcript events.</div>
                  </div>
                </div>
              </div>
            ) : activeProvider === 'cartesia' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>Cartesia realtime TTS setup</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('cartesia', e.target.checked)} />
                      <span>Enable Cartesia streaming text-to-speech</span>
                    </label>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Cartesia API key</label>
                      <input className='input' style={cartesiaStatus.errors.api_key ? invalidInputStyle : undefined} type='password' value={String(activeDraft.api_key_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, cartesia: { ...(s.cartesia || {}), api_key_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.api_key ? 'Leave blank to keep current key' : 'Paste Cartesia API key'} />
                    </div>
                    <label className='label'>Base URL</label>
                    <input className='input' style={cartesiaStatus.errors.base_url ? invalidInputStyle : undefined} value={String(activeConfig.base_url || 'https://api.cartesia.ai')} onChange={(e) => setProviderField('cartesia', 'base_url', e.target.value)} />
                    <label className='label'>Model ID</label>
                    <input className='input' style={cartesiaStatus.errors.model_id ? invalidInputStyle : undefined} value={String(activeConfig.model_id || 'sonic-2')} onChange={(e) => setProviderField('cartesia', 'model_id', e.target.value)} />
                    <label className='label'>Voice ID</label>
                    <input className='input' style={cartesiaStatus.errors.voice_id ? invalidInputStyle : undefined} value={String(activeConfig.voice_id || 'a0e99841-438c-4a64-b679-ae501e7d6091')} onChange={(e) => setProviderField('cartesia', 'voice_id', e.target.value)} />
                    <label className='label'>Sample rate</label>
                    <input className='input' style={cartesiaStatus.errors.sample_rate ? invalidInputStyle : undefined} value={String(activeConfig.sample_rate || '44100')} onChange={(e) => setProviderField('cartesia', 'sample_rate', e.target.value)} />
                    {!cartesiaStatus.valid ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.35)' }}>Complete the required Cartesia fields before saving.</div> : null}
                    {cartesiaTestResult ? <div className='note'>{cartesiaTestResult}</div> : null}
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('cartesia')} disabled={providerSaving || !cartesiaStatus.valid}>{providerSaving ? 'Saving...' : 'Save Cartesia'}</button>
                      <button className='btn soft' onClick={testCartesia} disabled={providerSaving || !activeSummary.configured}>Test connection</button>
                    </div>
                    <div className='note'>Cartesia is used by the demo stream as soon as each Groq LLM sentence chunk is ready, minimizing time to first audio.</div>
                  </div>
                </div>
              </div>
            ) : activeProvider === 'vapi' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>Vapi browser-call setup</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('vapi', e.target.checked)} />
                      <span>Enable Vapi browser demo mode</span>
                    </label>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Public key</label>
                      <input className='input' style={vapiStatus.errors.public_key ? invalidInputStyle : undefined} value={String(activeConfig.public_key || '')} onChange={(e) => setProviderField('vapi', 'public_key', e.target.value)} placeholder='Public Key (for browser / Talk to us)' />
                      {vapiStatus.errors.public_key ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{vapiStatus.errors.public_key}</div> : null}
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Assistant ID</label>
                      <input className='input' style={vapiStatus.errors.assistant_id ? invalidInputStyle : undefined} value={String(activeConfig.assistant_id || '')} onChange={(e) => setProviderField('vapi', 'assistant_id', e.target.value)} placeholder='Vapi assistant ID for Vox Sales' />
                      {vapiStatus.errors.assistant_id ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{vapiStatus.errors.assistant_id}</div> : null}
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Private API key (required)</label>
                      <input className='input' style={vapiStatus.errors.api_key ? invalidInputStyle : undefined} type='password' value={String(activeDraft.api_key_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, vapi: { ...(s.vapi || {}), api_key_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.api_key ? 'Leave blank to keep current private key' : 'Paste Private API Key from Vapi dashboard'} />
                      {vapiStatus.errors.api_key ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{vapiStatus.errors.api_key}</div> : null}
                      <div className='muted' style={{ fontSize: 12 }}>Public key = Talk to us in the browser. Private API key = Lead sources transcript and recording from Vapi. Do not swap them.</div>
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Base URL</label>
                      <input className='input' value={String(activeConfig.base_url || 'https://api.vapi.ai')} onChange={(e) => setProviderField('vapi', 'base_url', e.target.value)} />
                    </div>
                    {!vapiStatus.valid ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.35)' }}>Complete Public key and Assistant ID before saving.</div> : null}
                    {vapiTestResult ? <div className='note'>{vapiTestResult}</div> : null}
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('vapi')} disabled={providerSaving || !vapiStatus.valid}>
                        {providerSaving ? 'Saving…' : 'Save Vapi'}
                      </button>
                      <button className='btn soft' onClick={testVapi} disabled={providerSaving || !activeSummary.configured}>
                        Test Vapi
                      </button>
                    </div>
                    <div className='note'>
                      From your Vapi dashboard → API Keys: paste <strong>Public Key</strong> in Public key (used by Talk to us on the website).
                      Optional <strong>Private API Key</strong> goes in Server API key (server checks only — never in the browser).
                      Click <strong>Save Vapi</strong>, then <strong>Test Vapi</strong>. Do not swap the two keys (401).
                      For website calls, also set the same assistant ID under Admin → Front page call leads.
                    </div>
                  </div>
                </div>
              </div>
            ) : activeProvider === 'elevenlabs' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>ElevenLabs text-to-speech setup</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('elevenlabs', e.target.checked)} />
                      <span>Enable ElevenLabs TTS</span>
                    </label>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>API key</label>
                      <input className='input' style={elevenLabsStatus.errors.api_key ? invalidInputStyle : undefined} type='password' value={String(activeDraft.api_key_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, elevenlabs: { ...(s.elevenlabs || {}), api_key_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.api_key ? 'Leave blank to keep current key' : 'Paste ElevenLabs API key'} />
                      {elevenLabsStatus.errors.api_key ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{elevenLabsStatus.errors.api_key}</div> : null}
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Default voice ID</label>
                      <input className='input' style={elevenLabsStatus.errors.default_voice_id ? invalidInputStyle : undefined} value={String(activeConfig.default_voice_id || activeConfig.voice_id || '')} onChange={(e) => { setProviderField('elevenlabs', 'default_voice_id', e.target.value); setProviderField('elevenlabs', 'voice_id', e.target.value) }} placeholder='Paste ElevenLabs voice_id' />
                      {elevenLabsStatus.errors.default_voice_id ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{elevenLabsStatus.errors.default_voice_id}</div> : null}
                      <div className='muted' style={{ fontSize: 12 }}>ElevenLabs uses this voice_id directly in `/v1/text-to-speech/:voice_id`.</div>
                    </div>
                    <details>
                      <summary style={{ cursor: 'pointer', fontWeight: 700 }}>Advanced voice settings</summary>
                      <div className='stack' style={{ gap: 12, marginTop: 12 }}>
                        <div style={{ display: 'grid', gap: 6 }}>
                          <label className='label'>Model ID</label>
                          <input className='input' value={String(activeConfig.model_id || 'eleven_multilingual_v2')} onChange={(e) => setProviderField('elevenlabs', 'model_id', e.target.value)} />
                        </div>
                        {[
                          ['stability', 'Stability (0-1)', '0.5'],
                          ['similarity_boost', 'Similarity boost (0-1)', '0.75'],
                          ['style', 'Style (0-1)', '0'],
                          ['speed', 'Speed (0.7-1.2)', '1.0'],
                        ].map(([field, label, placeholder]) => (
                          <div key={field} style={{ display: 'grid', gap: 6 }}>
                            <label className='label'>{label}</label>
                            <input className='input' style={elevenLabsStatus.errors[field] ? invalidInputStyle : undefined} value={String(activeConfig[field] ?? '')} onChange={(e) => setProviderField('elevenlabs', field, e.target.value)} placeholder={placeholder} />
                            {elevenLabsStatus.errors[field] ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{elevenLabsStatus.errors[field]}</div> : null}
                          </div>
                        ))}
                        <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <input type='checkbox' checked={activeConfig.speaker_boost !== false} onChange={(e) => setProviderField('elevenlabs', 'speaker_boost', e.target.checked)} />
                          <span>Use speaker boost</span>
                        </label>
                        <div style={{ display: 'grid', gap: 6 }}>
                          <label className='label'>Base URL</label>
                          <input className='input' value={String(activeConfig.base_url || 'https://api.elevenlabs.io')} onChange={(e) => setProviderField('elevenlabs', 'base_url', e.target.value)} />
                        </div>
                      </div>
                    </details>
                    {!elevenLabsStatus.valid ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.35)' }}>Complete the required ElevenLabs fields before saving.</div> : null}
                    {elevenLabsTestResult ? <div className='note'>{elevenLabsTestResult}</div> : null}
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('elevenlabs')} disabled={providerSaving || !elevenLabsStatus.valid}>
                        {providerSaving ? 'Saving…' : 'Save ElevenLabs'}
                      </button>
                      <button className='btn soft' onClick={testElevenLabs} disabled={providerSaving || !activeSummary.configured}>
                        Test ElevenLabs TTS
                      </button>
                    </div>
                    <div className='note'>Use this from `/ai/agent-demo` by choosing ElevenLabs in the Text-to-speech card. You can override the voice ID per test.</div>
                  </div>
                </div>
              </div>
            ) : activeProvider === 'zoom' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>Zoom Server-to-Server OAuth</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('zoom', e.target.checked)} />
                      <span>Enable Zoom for interview campaigns</span>
                    </label>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Account ID</label>
                      <input className='input' style={zoomStatus.errors.account_id ? invalidInputStyle : undefined} value={String(activeConfig.account_id || '')} onChange={(e) => setProviderField('zoom', 'account_id', e.target.value)} />
                      {zoomStatus.errors.account_id ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{zoomStatus.errors.account_id}</div> : null}
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Client ID</label>
                      <input className='input' style={zoomStatus.errors.client_id ? invalidInputStyle : undefined} value={String(activeConfig.client_id || '')} onChange={(e) => setProviderField('zoom', 'client_id', e.target.value)} />
                      {zoomStatus.errors.client_id ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{zoomStatus.errors.client_id}</div> : null}
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Client secret</label>
                      <input className='input' style={zoomStatus.errors.client_secret ? invalidInputStyle : undefined} type='password' value={String(activeDraft.client_secret_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, zoom: { ...(s.zoom || {}), client_secret_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.client_secret ? 'Leave blank to keep current secret' : 'Paste Zoom client secret'} />
                      {zoomStatus.errors.client_secret ? <div className='muted' style={{ fontSize: 12, color: '#dc2626' }}>{zoomStatus.errors.client_secret}</div> : null}
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>API base URL</label>
                      <input className='input' value={String(activeConfig.base_url || 'https://api.zoom.us/v2')} onChange={(e) => setProviderField('zoom', 'base_url', e.target.value)} />
                    </div>
                    {!zoomStatus.valid ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.35)' }}>Complete the required Zoom fields before saving.</div> : null}
                    {zoomTestResult ? <div className='note'>{zoomTestResult}</div> : null}
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('zoom')} disabled={providerSaving || !zoomStatus.valid}>
                        {providerSaving ? 'Saving…' : 'Save Zoom'}
                      </button>
                      <button className='btn soft' onClick={testZoom} disabled={providerSaving || !activeSummary.configured}>
                        Test Zoom
                      </button>
                    </div>
                    <div className='note'>Used when customers choose Zoom delivery on interview orders.</div>
                  </div>
                </div>
              </div>
            ) : activeProvider === 'calendly' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>Calendly OAuth (interview scheduling)</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('calendly', e.target.checked)} />
                      <span>Enable Calendly for interview shortlist booking links</span>
                    </label>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Client ID</label>
                      <input className='input' style={calendlyStatus.errors.client_id ? invalidInputStyle : undefined} value={String(activeConfig.client_id || '')} onChange={(e) => setProviderField('calendly', 'client_id', e.target.value)} />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Client secret</label>
                      <input className='input' style={calendlyStatus.errors.client_secret ? invalidInputStyle : undefined} type='password' value={String(activeDraft.client_secret_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, calendly: { ...(s.calendly || {}), client_secret_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.client_secret ? 'Leave blank to keep current secret' : 'Paste Calendly client secret'} />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Redirect URI</label>
                      <input className='input' style={calendlyStatus.errors.redirect_uri ? invalidInputStyle : undefined} value={String(activeConfig.redirect_uri || '')} onChange={(e) => setProviderField('calendly', 'redirect_uri', e.target.value)} placeholder='https://api.voxbulk.com/service-orders/scheduling/oauth/calendly/callback' />
                    </div>
                    {calendlyTestResult ? <div className='note'>{calendlyTestResult}</div> : null}
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('calendly')} disabled={providerSaving || !calendlyStatus.valid}>Save Calendly</button>
                      <button className='btn soft' onClick={testCalendly} disabled={providerSaving || !activeSummary.configured}>Test Calendly</button>
                    </div>
                    <div className='note'>Each organisation connects Calendly from Dashboard → Integrations. Register the redirect URI in your Calendly developer app.</div>
                    <div className='note' style={{ marginTop: 8 }}>
                      <strong>Setup (VoxBulk admin, one time)</strong>
                      <ol style={{ margin: '8px 0 0', paddingLeft: 20, lineHeight: 1.6 }}>
                        <li>Open <a href='https://developer.calendly.com/' target='_blank' rel='noreferrer'>developer.calendly.com</a> → create an OAuth application for VoxBulk.</li>
                        <li>Add redirect URI: <code>https://api.voxbulk.com/service-orders/scheduling/oauth/calendly/callback</code> (use your API host if different).</li>
                        <li>Paste Client ID and Client secret below → Enable → Save → Test.</li>
                        <li>Each customer org clicks <strong>Connect Calendly</strong> in Dashboard → Integrations (uses their Calendly account, not yours).</li>
                      </ol>
                    </div>
                  </div>
                </div>
              </div>
            ) : activeProvider === 'cal_com' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>Cal.com OAuth (interview scheduling)</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('cal_com', e.target.checked)} />
                      <span>Enable Cal.com for interview shortlist booking links</span>
                    </label>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Client ID</label>
                      <input className='input' style={calComStatus.errors.client_id ? invalidInputStyle : undefined} value={String(activeConfig.client_id || '')} onChange={(e) => setProviderField('cal_com', 'client_id', e.target.value)} />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Client secret</label>
                      <input className='input' style={calComStatus.errors.client_secret ? invalidInputStyle : undefined} type='password' value={String(activeDraft.client_secret_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, cal_com: { ...(s.cal_com || {}), client_secret_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.client_secret ? 'Leave blank to keep current secret' : 'Paste Cal.com client secret'} />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Redirect URI</label>
                      <input className='input' style={calComStatus.errors.redirect_uri ? invalidInputStyle : undefined} value={String(activeConfig.redirect_uri || '')} onChange={(e) => setProviderField('cal_com', 'redirect_uri', e.target.value)} placeholder='https://api.voxbulk.com/service-orders/scheduling/oauth/cal-com/callback' />
                    </div>
                    {calComTestResult ? <div className='note'>{calComTestResult}</div> : null}
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('cal_com')} disabled={providerSaving || !calComStatus.valid}>Save Cal.com</button>
                      <button className='btn soft' onClick={testCalCom} disabled={providerSaving || !activeSummary.configured}>Test Cal.com</button>
                    </div>
                    <div className='note'>Each organisation connects Cal.com from Dashboard → Integrations (one booking provider at a time).</div>
                  </div>
                </div>
              </div>
            ) : activeProvider === 'google_calendar' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>Google Calendar OAuth (interview scheduling)</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('google_calendar', e.target.checked)} />
                      <span>Enable Google Calendar appointment schedules for interview booking</span>
                    </label>
                    <div className='note'>Use a separate Google Cloud OAuth client from Social login. Enable Google Calendar API and add Calendar scopes.</div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Client ID</label>
                      <input className='input' style={googleCalendarStatus.errors.client_id ? invalidInputStyle : undefined} value={String(activeConfig.client_id || '')} onChange={(e) => setProviderField('google_calendar', 'client_id', e.target.value)} />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Client secret</label>
                      <input className='input' style={googleCalendarStatus.errors.client_secret ? invalidInputStyle : undefined} type='password' value={String(activeDraft.client_secret_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, google_calendar: { ...(s.google_calendar || {}), client_secret_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.client_secret ? 'Leave blank to keep current secret' : 'Paste Google client secret'} />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Redirect URI</label>
                      <input className='input' style={googleCalendarStatus.errors.redirect_uri ? invalidInputStyle : undefined} value={String(activeConfig.redirect_uri || '')} onChange={(e) => setProviderField('google_calendar', 'redirect_uri', e.target.value)} placeholder='https://api.voxbulk.com/service-orders/scheduling/oauth/google-calendar/callback' />
                    </div>
                    {googleCalendarTestResult ? <div className='note'>{googleCalendarTestResult}</div> : null}
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('google_calendar')} disabled={providerSaving || !googleCalendarStatus.valid}>Save Google Calendar</button>
                      <button className='btn soft' onClick={testGoogleCalendar} disabled={providerSaving || !activeSummary.configured}>Test Google Calendar</button>
                    </div>
                  </div>
                </div>
              </div>
            ) : activeProvider === 'microsoft_calendar' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>Microsoft 365 Calendar OAuth (interview scheduling)</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('microsoft_calendar', e.target.checked)} />
                      <span>Enable Microsoft 365 Calendar / Outlook Bookings for interview booking</span>
                    </label>
                    <div className='note'>
                      Register a <strong>multi-tenant</strong> app in <a href='https://entra.microsoft.com/' target='_blank' rel='noreferrer'>Microsoft Entra ID</a>. Add the delegated scopes <code>openid</code>, <code>profile</code>, <code>email</code>, <code>offline_access</code>, <code>User.Read</code>, <code>Calendars.ReadWrite</code> and the redirect URI below.
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Application (client) ID</label>
                      <input className='input' style={microsoftCalendarStatus.errors.client_id ? invalidInputStyle : undefined} value={String(activeConfig.client_id || '')} onChange={(e) => setProviderField('microsoft_calendar', 'client_id', e.target.value)} />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Client secret</label>
                      <input className='input' style={microsoftCalendarStatus.errors.client_secret ? invalidInputStyle : undefined} type='password' value={String(activeDraft.client_secret_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, microsoft_calendar: { ...(s.microsoft_calendar || {}), client_secret_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.client_secret ? 'Leave blank to keep current secret' : 'Paste Microsoft client secret'} />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Redirect URI</label>
                      <input className='input' style={microsoftCalendarStatus.errors.redirect_uri ? invalidInputStyle : undefined} value={String(activeConfig.redirect_uri || '')} onChange={(e) => setProviderField('microsoft_calendar', 'redirect_uri', e.target.value)} placeholder='https://api.voxbulk.com/service-orders/scheduling/oauth/microsoft-calendar/callback' />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Authority (tenant)</label>
                      <input
                        className='input'
                        value={String(activeConfig.tenant || 'common')}
                        onChange={(e) => setProviderField('microsoft_calendar', 'tenant', e.target.value)}
                        placeholder='common'
                      />
                      <div className='muted' style={{ fontSize: 12 }}>
                        Use <code>common</code> for multi-tenant (recommended), or <code>organizations</code> to allow only work/school accounts.
                      </div>
                    </div>
                    {microsoftCalendarTestResult ? <div className='note'>{microsoftCalendarTestResult}</div> : null}
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('microsoft_calendar')} disabled={providerSaving || !microsoftCalendarStatus.valid}>Save Microsoft Calendar</button>
                      <button className='btn soft' onClick={testMicrosoftCalendar} disabled={providerSaving || !activeSummary.configured}>Test Microsoft Calendar</button>
                    </div>
                    <div className='note'>
                      After saving and verifying, flip <strong>Visible to organisations</strong> on (top toolbar) so customers see Microsoft Calendar in Dashboard → Integrations. Keep it off during soft-launch testing.
                    </div>
                  </div>
                </div>
              </div>
            ) : activeProvider === 'hubspot' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>HubSpot CRM setup</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('hubspot', e.target.checked)} />
                      <span>Enable HubSpot integration</span>
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input
                        type='checkbox'
                        checked={Boolean(activeConfig.contact_sync_v1_enabled)}
                        onChange={(e) => setProviderField('hubspot', 'contact_sync_v1_enabled', e.target.checked)}
                      />
                      <span>Enable HubSpot contact sync (v1 beta)</span>
                    </label>
                    <div className='muted' style={{ fontSize: 12, marginTop: -4 }}>
                      When enabled, dashboard orgs see a separate Contact sync (beta) card for pulling HubSpot contacts into VoxBulk. Existing CRM connect and interview sync are unchanged.
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Connection type</label>
                      <select className='input' value={String(activeConfig.auth_mode || 'private_app')} onChange={(e) => setProviderField('hubspot', 'auth_mode', e.target.value)}>
                        <option value='private_app'>Service key / access token (recommended — no client secret)</option>
                        <option value='oauth'>OAuth app (legacy / CLI only — not for new HubSpot UI accounts)</option>
                      </select>
                      <div className='muted' style={{ fontSize: 12 }}>
                        <strong>New HubSpot accounts:</strong> legacy public OAuth apps are disabled in the HubSpot UI. Use <strong>Service key</strong> mode below — each company creates a Service Key and pastes it in Dashboard → Integrations. You do not need <code>hs project create</code> for this.
                      </div>
                    </div>
                    {String(activeConfig.auth_mode || 'private_app') === 'oauth' ? (
                      <>
                      <div className='note' style={{ borderColor: 'rgba(255,165,0,0.5)' }}>
                        Legacy public OAuth apps are <strong>disabled for new HubSpot accounts</strong>. OAuth here only works if you already have a legacy app or build a new app with the{' '}
                        <a href='https://developers.hubspot.com/docs/apps/developer-platform/build-apps/create-an-app' target='_blank' rel='noreferrer'>HubSpot CLI</a>{' '}
                        (<code>hs project create</code>). For most customers, switch connection type to <strong>Service key</strong> instead.
                      </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Client ID</label>
                      <input className='input' style={hubspotStatus.errors.client_id ? invalidInputStyle : undefined} value={String(activeConfig.client_id || '')} onChange={(e) => setProviderField('hubspot', 'client_id', e.target.value)} />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Client secret</label>
                      <input className='input' style={hubspotStatus.errors.client_secret ? invalidInputStyle : undefined} type='password' value={String(activeDraft.client_secret_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, hubspot: { ...(s.hubspot || {}), client_secret_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.client_secret ? 'Leave blank to keep current secret' : 'Paste HubSpot client secret'} />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Redirect URI</label>
                      <input className='input' style={hubspotStatus.errors.redirect_uri ? invalidInputStyle : undefined} value={String(activeConfig.redirect_uri || '')} onChange={(e) => setProviderField('hubspot', 'redirect_uri', e.target.value)} placeholder='https://api.voxbulk.com/service-orders/hubspot/oauth/callback' />
                    </div>
                      </>
                    ) : null}
                    {hubspotTestResult ? <div className='note'>{hubspotTestResult}</div> : null}
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('hubspot')} disabled={providerSaving || !hubspotStatus.valid}>Save HubSpot</button>
                      <button className='btn soft' onClick={testHubspot} disabled={providerSaving || !activeSummary.configured}>Test</button>
                    </div>
                    <div className='note'>
                      <strong>Setup steps</strong>
                      {String(activeConfig.auth_mode || 'private_app') === 'private_app' ? (
                        <ol style={{ margin: '8px 0 0', paddingLeft: 18 }}>
                          <li>Enable HubSpot above → Save → Test.</li>
                          <li>Each company: HubSpot → Settings → Integrations → <strong>Service Keys</strong> (or Development → Keys → Service Keys) → create key.</li>
                          <li>Scopes: <code>crm.objects.contacts.read</code> and <code>crm.objects.contacts.write</code>.</li>
                          <li>Copy the <strong>Service key</strong> — use as Bearer token; no client secret.</li>
                          <li>Paste token in <strong>Dashboard → Integrations → HubSpot</strong>.</li>
                        </ol>
                      ) : (
                        <ol style={{ margin: '8px 0 0', paddingLeft: 18 }}>
                          <li>Only for legacy OAuth apps or CLI-built apps (<code>hs project create</code>) — not available in HubSpot UI for new accounts.</li>
                          <li>Redirect URI: <code>https://api.voxbulk.com/service-orders/hubspot/oauth/callback</code></li>
                          <li>Scopes: <code>crm.objects.contacts.read</code>, <code>crm.objects.contacts.write</code>, <code>oauth</code></li>
                          <li>Paste Client ID and secret below → Save. Companies use <strong>Connect HubSpot</strong> in Dashboard → Integrations.</li>
                        </ol>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ) : activeProvider === 'gocardless' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>GoCardless sandbox setup</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('gocardless', e.target.checked)} />
                      <span>Enable GoCardless billing</span>
                    </label>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Environment</label>
                      <select className='input' value={String(activeConfig.environment || 'sandbox')} onChange={(e) => setProviderField('gocardless', 'environment', e.target.value)}>
                        <option value='sandbox'>Sandbox</option>
                        <option value='live'>Live</option>
                      </select>
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Access token</label>
                      <input className='input' type='password' value={String(activeDraft.access_token_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, gocardless: { ...(s.gocardless || {}), access_token_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.access_token ? 'Leave blank to keep current token' : 'Paste sandbox access token'} />
                      <div className='muted' style={{ fontSize: 12 }}>Token is encrypted in the backend and never returned to the browser.</div>
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Webhook endpoint URL</label>
                      <input className='input' value={String(activeConfig.webhook_url || 'http://localhost:8000/webhooks/gocardless')} onChange={(e) => setProviderField('gocardless', 'webhook_url', e.target.value)} />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Webhook secret</label>
                      <input className='input' type='password' value={String(activeDraft.webhook_secret_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, gocardless: { ...(s.gocardless || {}), webhook_secret_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.webhook_secret ? 'Leave blank to keep current secret' : 'Paste webhook secret'} />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Success redirect URL</label>
                      <input className='input' value={String(activeConfig.success_redirect_url || '')} placeholder='Leave blank — auto: dashboard via api.voxbulk.com hop' onChange={(e) => setProviderField('gocardless', 'success_redirect_url', e.target.value)} />
                      <div className='muted' style={{ fontSize: 12 }}>
                        Leave blank — GoCardless returns via api.voxbulk.com, then dashboard /account/packages. Do not set dashboard /packages (404).
                      </div>
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Cancel / retry URL</label>
                      <input className='input' value={String(activeConfig.cancel_redirect_url || '')} placeholder='Leave blank — auto: dashboard via api.voxbulk.com hop' onChange={(e) => setProviderField('gocardless', 'cancel_redirect_url', e.target.value)} />
                    </div>
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('gocardless')} disabled={providerSaving}>
                        {providerSaving ? 'Saving…' : 'Save GoCardless'}
                      </button>
                      <button className='btn soft' onClick={testGocardless} disabled={providerSaving || !activeSummary.configured}>
                        Test connection
                      </button>
                    </div>
                    {gocardlessTestResult ? <div className='note' style={{ marginTop: 8 }}>{gocardlessTestResult}</div> : null}
                  </div>
                </div>
              </div>
            ) : activeProvider === 'stripe' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>Stripe card payments</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('stripe', e.target.checked)} />
                      <span>Enable Stripe wallet top-ups</span>
                    </label>
                    <div className='note'>Used for customer wallet top-ups by card. Customers see Stripe at checkout only when this is enabled and configured.</div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Secret key</label>
                      <input className='input' type='password' value={String(activeDraft.secret_key_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, stripe: { ...(s.stripe || {}), secret_key_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.secret_key ? 'Leave blank to keep current key' : 'sk_test_… or sk_live_…'} />
                      <div className='muted' style={{ fontSize: 12 }}>Encrypted in the backend and never returned to the browser. Live/test mode is detected from the key.</div>
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Publishable key</label>
                      <input className='input' value={String(activeConfig.publishable_key || '')} onChange={(e) => setProviderField('stripe', 'publishable_key', e.target.value)} placeholder='pk_test_… or pk_live_…' />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Webhook signing secret</label>
                      <input className='input' type='password' value={String(activeDraft.webhook_secret_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, stripe: { ...(s.stripe || {}), webhook_secret_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.webhook_secret ? 'Leave blank to keep current secret' : 'whsec_…'} />
                      <div className='muted' style={{ fontSize: 12 }}>Endpoint: https://api.voxbulk.com/webhooks/stripe — subscribe to payment_intent.succeeded.</div>
                    </div>
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('stripe')} disabled={providerSaving}>
                        {providerSaving ? 'Saving…' : 'Save Stripe'}
                      </button>
                      <button className='btn soft' onClick={testStripe} disabled={providerSaving || !activeSummary.configured}>
                        Test connection
                      </button>
                    </div>
                    {stripeTestResult ? <div className='note' style={{ marginTop: 8 }}>{stripeTestResult}</div> : null}
                  </div>
                </div>
              </div>
            ) : activeProvider === 'airwallex' ? (
              <div className='card'>
                <div className='cardHead'>
                  <h3>Airwallex card payments</h3>
                  <span className={`pill ${statusPill(activeSummary).cls}`}>{statusPill(activeSummary).text}</span>
                </div>
                <div className='cardBody'>
                  {providerError ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)' }}>{providerError}</div> : null}
                  <div className='stack' style={{ gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('airwallex', e.target.checked)} />
                      <span>Enable Airwallex wallet top-ups</span>
                    </label>
                    <div className='note'>Used for customer wallet top-ups by card. Customers see Airwallex at checkout only when this is enabled and configured.</div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Environment</label>
                      <select className='input' value={String(activeConfig.environment || 'demo')} onChange={(e) => setProviderField('airwallex', 'environment', e.target.value)}>
                        <option value='demo'>Demo (sandbox)</option>
                        <option value='production'>Production</option>
                      </select>
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Client ID</label>
                      <input className='input' value={String(activeConfig.client_id || '')} onChange={(e) => setProviderField('airwallex', 'client_id', e.target.value)} placeholder='Airwallex client ID' />
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>API key</label>
                      <input className='input' type='password' value={String(activeDraft.api_key_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, airwallex: { ...(s.airwallex || {}), api_key_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.api_key ? 'Leave blank to keep current key' : 'Paste API key'} />
                      <div className='muted' style={{ fontSize: 12 }}>Encrypted in the backend and never returned to the browser.</div>
                    </div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      <label className='label'>Webhook secret</label>
                      <input className='input' type='password' value={String(activeDraft.webhook_secret_draft || '')} onChange={(e) => setProviderDrafts((s) => ({ ...s, airwallex: { ...(s.airwallex || {}), webhook_secret_draft: e.target.value } }))} placeholder={activeSummary?.secret_set?.webhook_secret ? 'Leave blank to keep current secret' : 'Paste webhook secret'} />
                      <div className='muted' style={{ fontSize: 12 }}>Endpoint: https://api.voxbulk.com/webhooks/airwallex — subscribe to payment_intent.succeeded.</div>
                    </div>
                    <div className='actions'>
                      <button className='btn primary' onClick={() => saveIntegrationProvider('airwallex')} disabled={providerSaving}>
                        {providerSaving ? 'Saving…' : 'Save Airwallex'}
                      </button>
                      <button className='btn soft' onClick={testAirwallex} disabled={providerSaving || !activeSummary.configured}>
                        Test connection
                      </button>
                    </div>
                    {airwallexTestResult ? <div className='note' style={{ marginTop: 8 }}>{airwallexTestResult}</div> : null}
                  </div>
                </div>
              </div>
            ) : activeProvider ? (
              <div className='card'>
                <div className='cardHead'><h3>{PROVIDERS.find((p) => p.key === activeProvider)?.label} settings</h3></div>
                <div className='cardBody'><div className='note'>Credential editor for this provider is not expanded in this phase.</div></div>
              </div>
            ) : null}
            </div>
          </IntegrationProviderShell>
        </div>
      ) : (
        <Navigate to='/integrations/kpi' replace />
      )}
    </>
  )
}
