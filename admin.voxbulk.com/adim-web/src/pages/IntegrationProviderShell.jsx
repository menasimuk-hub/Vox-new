import React from 'react'
import { Link } from 'react-router-dom'
import { integrationCardStatus } from '../lib/integrationsCatalog'

function joinMissingFields(x) {
  const arr = Array.isArray(x) ? x : []
  return arr.length ? arr.join(', ') : ''
}

export default function IntegrationProviderShell({
  title,
  enableLabel,
  enabled,
  onEnabledChange,
  summary,
  saving,
  onSave,
  saveLabel = 'Save',
  saveDisabled,
  providerError,
  toolbarActions,
  children,
}) {
  const status = integrationCardStatus(summary)

  return (
    <div className='integrationProviderPage'>
      <div className='card integrationToolbar'>
        <div className='cardBody integrationToolbarBody'>
          <div className='integrationToolbarLeft'>
            <Link to='/integrations/kpi' className='integrationBackLink'>
              <i className='ti ti-arrow-left' /> Integration KPI
            </Link>
            {enableLabel ? (
              <label className='integrationEnableRow'>
                <input type='checkbox' checked={Boolean(enabled)} onChange={(e) => onEnabledChange?.(e.target.checked)} />
                <span>{enableLabel}</span>
              </label>
            ) : null}
            {summary ? <span className={`pill ${status.pillClass}`}>{status.label}</span> : null}
            {summary?.missing_fields?.length ? (
              <span className='muted integrationMissing'>Missing: {joinMissingFields(summary.missing_fields)}</span>
            ) : null}
          </div>
          <div className='actions'>
            {toolbarActions}
            {onSave ? (
              <button type='button' className='btn primary' onClick={onSave} disabled={saving || saveDisabled}>
                {saving ? 'Saving…' : saveLabel}
              </button>
            ) : null}
          </div>
        </div>
      </div>

      {providerError ? <div className='note integrationErrorNote'>{providerError}</div> : null}

      <div className='integrationProviderBody'>{children}</div>
    </div>
  )
}
