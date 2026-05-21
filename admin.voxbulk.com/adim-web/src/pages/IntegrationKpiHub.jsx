import React, { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { INTEGRATION_EXTRAS, INTEGRATION_PROVIDERS, integrationCardStatus, isIntegrationConnected } from '../lib/integrationsCatalog'

function IntegrationCard({ item, summary, onOpen }) {
  const status = integrationCardStatus(summary, { kind: item.kind })
  return (
    <button type='button' className={`integrationKpiCard ${status.cardClass}`} onClick={onOpen}>
      <div className='integrationKpiCardTop'>
        <span className='integrationKpiIcon'>
          <i className={`ti ${item.icon}`} />
        </span>
        <span className={`integrationKpiDot ${status.connected === true ? 'isOn' : status.connected === false ? 'isOff' : 'isNeutral'}`} title={status.label} />
      </div>
      <strong className='integrationKpiTitle'>{item.label}</strong>
      <p className='integrationKpiBlurb'>{item.blurb}</p>
      <div className='integrationKpiFoot'>
        <span className={`pill ${status.pillClass}`}>{status.label}</span>
        <span className='integrationKpiOpen'>
          Open <i className='ti ti-chevron-right' />
        </span>
      </div>
    </button>
  )
}

export default function IntegrationKpiHub({ summaries, loading, onRefresh }) {
  const navigate = useNavigate()

  const stats = useMemo(() => {
    let connected = 0
    let total = INTEGRATION_PROVIDERS.length
    INTEGRATION_PROVIDERS.forEach((p) => {
      if (isIntegrationConnected(summaries[p.key])) connected += 1
    })
    return { connected, total, extras: INTEGRATION_EXTRAS.length }
  }, [summaries])

  return (
    <div className='integrationKpiHub'>
      <div className='integrationKpiStats'>
        <div className='integrationKpiStat'>
          <label>Connected</label>
          <strong>{stats.connected}</strong>
          <span>of {stats.total} API integrations</span>
        </div>
        <div className='integrationKpiStat'>
          <label>Needs attention</label>
          <strong>{Math.max(0, stats.total - stats.connected)}</strong>
          <span>disabled or missing credentials</span>
        </div>
        <div className='integrationKpiStat'>
          <label>Also configure</label>
          <strong>{stats.extras}</strong>
          <span>webhooks & social login</span>
        </div>
      </div>

      <div className='integrationKpiSectionHead'>
        <h2>Platform integrations</h2>
        <button type='button' className='btn soft' onClick={onRefresh} disabled={loading}>
          <i className='ti ti-refresh' /> {loading ? 'Refreshing…' : 'Refresh status'}
        </button>
      </div>

      <div className='integrationKpiGrid'>
        {INTEGRATION_PROVIDERS.map((item) => (
          <IntegrationCard
            key={item.key}
            item={item}
            summary={summaries[item.key]}
            onOpen={() => navigate(`/integrations/${item.key}`)}
          />
        ))}
      </div>

      <div className='integrationKpiSectionHead'>
        <h2>Auth & webhooks</h2>
      </div>

      <div className='integrationKpiGrid integrationKpiGridCompact'>
        {INTEGRATION_EXTRAS.map((item) => (
          <IntegrationCard
            key={item.key}
            item={item}
            summary={null}
            onOpen={() => navigate(item.route)}
          />
        ))}
      </div>
    </div>
  )
}
