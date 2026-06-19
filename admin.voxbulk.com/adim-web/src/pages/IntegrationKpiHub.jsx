import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import {
  INTEGRATION_EXTRAS,
  INTEGRATION_PROVIDERS,
  integrationCardStatus,
  isIntegrationConnected,
} from '../lib/integrationsCatalog'

const money = (amount, currency = 'USD') => {
  const value = Number(amount)
  if (!Number.isFinite(value)) return '—'
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: currency || 'USD' }).format(value)
  } catch {
    return `${currency || 'USD'} ${value.toFixed(2)}`
  }
}

const n = (value) => Number(value || 0).toLocaleString()

function fmtWhen(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

function isEnabledProvider(summary) {
  if (!summary || summary.error) return false
  return Boolean(summary.is_enabled && summary.configured)
}

function pickConfigModel(config) {
  if (!config || typeof config !== 'object') return ''
  return String(
    config.default_model || config.model || config.realtime_model || config.base_model || '',
  ).trim()
}

function buildIntegrationMetrics(key, summary, balances, callSummary) {
  const lines = []
  const config = summary?.config || {}

  if (key === 'telnyx') {
    const row = balances?.telnyx
    if (row?.ok) {
      lines.push({ label: 'Credit', value: money(row.amount, row.currency) })
      if (Number(row.pending) > 0) {
        lines.push({ label: 'Pending', value: money(row.pending, row.currency) })
      }
    } else if (row?.message) {
      lines.push({ label: 'Balance', value: row.message })
    }
    const cs = callSummary?.summary
    if (cs) {
      lines.push({
        label: '30d voice spend',
        value: money(cs.total_cost, cs.currency || 'USD'),
      })
      lines.push({ label: '30d AI calls', value: n(cs.total_calls) })
    }
  } else if (key === 'elevenlabs') {
    const row = balances?.elevenlabs
    if (row?.ok) {
      lines.push({ label: 'Chars left', value: n(row.characters_remaining) })
      lines.push({ label: 'Used (period)', value: n(row.character_count) })
      lines.push({ label: 'Tier', value: row.tier || '—' })
    } else if (row?.message) {
      lines.push({ label: 'Quota', value: row.message })
    }
  } else if (key === 'openai' || key === 'deepseek' || key === 'groq') {
    const model = pickConfigModel(config)
    if (model) lines.push({ label: 'Model', value: model })
    if (config.base_url) lines.push({ label: 'Base URL', value: String(config.base_url).replace(/^https?:\/\//, '') })
  } else if (key === 'azure_speech') {
    if (config.region) lines.push({ label: 'Region', value: config.region })
    if (config.default_voice_id) lines.push({ label: 'Voice', value: config.default_voice_id })
  } else if (key === 'vapi') {
    if (config.public_key_set || summary?.secret_set?.public_key) {
      lines.push({ label: 'Public key', value: 'Configured' })
    }
  } else if (key === 'stripe' || key === 'gocardless' || key === 'airwallex') {
    if (config.mode) lines.push({ label: 'Mode', value: config.mode })
    if (config.webhook_base_url) lines.push({ label: 'Webhook base', value: config.webhook_base_url })
  } else if (key === 'hubspot' || key === 'calendly' || key === 'cal_com' || key === 'google_calendar') {
    lines.push({ label: 'OAuth', value: 'Platform app configured' })
  } else if (key === 'dentally') {
    if (config.base_url) lines.push({ label: 'API base', value: config.base_url })
  }

  if (summary?.updated_at) {
    lines.push({ label: 'Updated', value: fmtWhen(summary.updated_at) })
  }

  if (!lines.length) {
    lines.push({ label: 'Status', value: 'Running · credentials OK' })
  }

  return lines.slice(0, 5)
}

function IntegrationCard({ item, summary, metrics, onOpen }) {
  const status = integrationCardStatus(summary, { kind: item.kind })
  return (
    <button type='button' className={`integrationKpiCard integrationKpiCardRich ${status.cardClass}`} onClick={onOpen}>
      <div className='integrationKpiCardTop'>
        <span className='integrationKpiIcon'>
          <i className={`ti ${item.icon}`} />
        </span>
        <span
          className={`integrationKpiDot ${status.connected === true ? 'isOn' : status.connected === false ? 'isOff' : 'isNeutral'}`}
          title={status.label}
        />
      </div>
      <strong className='integrationKpiTitle'>{item.label}</strong>
      <p className='integrationKpiBlurb'>{item.blurb}</p>
      <ul className='integrationKpiMetrics'>
        {metrics.map((row) => (
          <li key={`${item.key}-${row.label}`}>
            <span>{row.label}</span>
            <strong>{row.value}</strong>
          </li>
        ))}
      </ul>
      <div className='integrationKpiFoot'>
        <span className={`pill ${status.pillClass}`}>{status.label}</span>
        <span className='integrationKpiOpen'>
          Settings <i className='ti ti-chevron-right' />
        </span>
      </div>
    </button>
  )
}

export default function IntegrationKpiHub({ summaries, loading, onRefresh }) {
  const navigate = useNavigate()
  const [balances, setBalances] = useState(null)
  const [callSummary, setCallSummary] = useState(null)
  const [extrasLoading, setExtrasLoading] = useState(false)

  const loadExtras = useCallback(async () => {
    setExtrasLoading(true)
    try {
      const [balancesRes, costsRes] = await Promise.all([
        apiFetch('/admin/dashboard/provider-balances').catch(() => null),
        apiFetch('/admin/billing/calls-cost?date_range=last_30_days&page_size=1').catch(() => null),
      ])
      setBalances(balancesRes)
      setCallSummary(costsRes)
    } finally {
      setExtrasLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadExtras()
  }, [loadExtras])

  const enabledProviders = useMemo(
    () => INTEGRATION_PROVIDERS.filter((p) => isEnabledProvider(summaries[p.key])),
    [summaries],
  )

  const stats = useMemo(() => {
    let connected = 0
    INTEGRATION_PROVIDERS.forEach((p) => {
      if (isIntegrationConnected(summaries[p.key])) connected += 1
    })
    return {
      enabled: enabledProviders.length,
      connected,
      total: INTEGRATION_PROVIDERS.length,
    }
  }, [summaries, enabledProviders.length])

  const refreshAll = async () => {
    await Promise.all([onRefresh?.(), loadExtras()])
  }

  const busy = loading || extrasLoading

  return (
    <div className='integrationKpiHub'>
      <div className='integrationKpiStats'>
        <div className='integrationKpiStat'>
          <label>Enabled & running</label>
          <strong>{stats.enabled}</strong>
          <span>configured integrations shown below</span>
        </div>
        <div className='integrationKpiStat'>
          <label>Telnyx 30d spend</label>
          <strong>
            {callSummary?.summary?.total_cost != null
              ? money(callSummary.summary.total_cost, callSummary.summary.currency)
              : '—'}
          </strong>
          <span>{n(callSummary?.summary?.total_calls)} AI voice calls</span>
        </div>
        <div className='integrationKpiStat'>
          <label>Platform total</label>
          <strong>{stats.connected}</strong>
          <span>of {stats.total} connected · disabled hidden</span>
        </div>
      </div>

      <div className='integrationKpiSectionHead'>
        <div>
          <h2>Enabled integrations</h2>
          <p className='muted integrationKpiSectionSub'>
            Balance, quota, and last-30-days usage where available. Click a card for API settings.
          </p>
        </div>
        <div className='integrationKpiSectionActions'>
          <Link to='/integrations/telnyx' className='btn soft'>
            Telnyx
          </Link>
          <button type='button' className='btn soft' onClick={refreshAll} disabled={busy}>
            <i className='ti ti-refresh' /> {busy ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {enabledProviders.length === 0 ? (
        <div className='integrationKpiEmpty'>
          <p>No enabled integrations yet. Turn providers on and save credentials in Integrations.</p>
          <Link to='/integrations/openai' className='btn primary'>
            Configure integrations
          </Link>
        </div>
      ) : (
        <div className='integrationKpiGrid integrationKpiGridEnabled'>
          {enabledProviders.map((item) => (
            <IntegrationCard
              key={item.key}
              item={item}
              summary={summaries[item.key]}
              metrics={buildIntegrationMetrics(item.key, summaries[item.key], balances, callSummary)}
              onOpen={() => navigate(`/integrations/${item.key}`)}
            />
          ))}
        </div>
      )}

      <div className='integrationKpiSectionHead'>
        <h2>Auth & webhooks</h2>
      </div>

      <div className='integrationKpiGrid integrationKpiGridCompact'>
        {INTEGRATION_EXTRAS.map((item) => (
          <IntegrationCard
            key={item.key}
            item={item}
            summary={null}
            metrics={[{ label: 'Type', value: item.kind === 'config' ? 'Platform config' : '—' }]}
            onOpen={() => navigate(item.route)}
          />
        ))}
      </div>
    </div>
  )
}
