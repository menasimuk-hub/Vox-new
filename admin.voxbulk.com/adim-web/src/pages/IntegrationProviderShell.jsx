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
  visibleToOrgs,
  onVisibleToOrgsChange,
  showVisibilityToggle = true,
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
  const resolvedVisible = visibleToOrgs ?? summary?.visible_to_orgs ?? false

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
            {showVisibilityToggle && onVisibleToOrgsChange ? (
              <label className='integrationEnableRow' title='When off, this provider is fully configured but hidden from every organisation’s dashboard. Use this for soft launches.'>
                <input
                  type='checkbox'
                  checked={Boolean(resolvedVisible)}
                  onChange={(e) => onVisibleToOrgsChange?.(e.target.checked)}
                />
                <span>Visible to organisations</span>
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
