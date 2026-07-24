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
  releaseMode,
  onReleaseModeChange,
  showReleaseToggle = true,
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
  const resolvedMode = releaseMode || summary?.release_mode || (summary?.visible_to_orgs ? 'live' : 'testing')

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
            {showReleaseToggle && onReleaseModeChange ? (
              <label
                className='integrationEnableRow'
                title='Testing: only Admin Test group emails see this on the dashboard and in linked FAQs. Live: visible to all organisations.'
                style={{ gap: 8 }}
              >
                <span>Release</span>
                <select
                  className='input'
                  style={{ width: 'auto', minWidth: 120, height: 32 }}
                  value={resolvedMode === 'live' ? 'live' : 'testing'}
                  onChange={(e) => onReleaseModeChange?.(e.target.value)}
                >
                  <option value='testing'>Testing</option>
                  <option value='live'>Live</option>
                </select>
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
