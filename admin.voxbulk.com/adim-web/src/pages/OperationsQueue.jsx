import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import './operationsConsole.css'

const RETRYABLE_WEBHOOK_PROVIDERS = new Set(['vapi', 'gocardless'])
const RECOVERY_STATES = ['queued', 'calling', 'messaged', 'recovered', 'failed', 'skipped']

const MODE_META = {
  'failed-jobs': {
    title: 'Failed jobs',
    subtitle: 'Recovery jobs and webhooks that failed. Review the error, open the organisation, then retry.',
    showWebhooks: true,
    retryEmphasis: true,
  },
  'manual-retry': {
    title: 'Manual retry',
    subtitle: 'Retry workbench for failed recovery jobs and supported webhook providers (Vapi, GoCardless). Invalid signatures cannot be retried.',
    showWebhooks: true,
    retryEmphasis: true,
  },
  'recovery-events': {
    title: 'Recovery events',
    subtitle: 'Full recovery job history across all states. Filter by status to investigate the pipeline.',
    showWebhooks: false,
    retryEmphasis: false,
  },
  'call-queue': {
    title: 'Call queue',
    subtitle: 'Recovery jobs currently queued or in a voice call step.',
    showWebhooks: false,
    retryEmphasis: false,
  },
  'whatsapp-queue': {
    title: 'WhatsApp queue',
    subtitle: 'Recovery jobs that reached the WhatsApp / messaged step.',
    showWebhooks: false,
    retryEmphasis: false,
  },
}

const n = (value) => Number(value || 0).toLocaleString()
const dateText = (value) => (value ? new Date(value).toLocaleString() : '—')
const shortId = (value) => {
  const s = String(value || '')
  return s.length > 10 ? `${s.slice(0, 8)}…` : s || '—'
}
const truncate = (value, max = 120) => {
  const s = String(value || '').trim()
  if (!s) return ''
  return s.length > max ? `${s.slice(0, max)}…` : s
}

const badgeClass = (status) => {
  const s = String(status || '').toLowerCase()
  if (s === 'failed') return 'failed'
  if (['queued', 'received', 'processing'].includes(s)) return 'queued'
  if (['calling', 'messaged'].includes(s)) return 'calling'
  if (['recovered', 'processed'].includes(s)) return 'recovered'
  if (s === 'skipped') return 'skipped'
  return 'neutral'
}

function openOrgProfile(orgId, navigate) {
  if (!orgId) return
  localStorage.setItem('voxbulk_admin_selected_org_id', orgId)
  navigate(`/organisations/profile?org_id=${encodeURIComponent(orgId)}`)
}

function webhookCanRetry(w) {
  const provider = String(w?.provider || '').toLowerCase()
  return Boolean(w?.signature_valid) && RETRYABLE_WEBHOOK_PROVIDERS.has(provider)
}

function jobCanRetry(job, mode) {
  if (mode === 'manual-retry' || mode === 'failed-jobs') return String(job?.state || '').toLowerCase() === 'failed'
  return String(job?.state || '').toLowerCase() === 'failed'
}

async function fetchJobsForMode(mode, stateChip) {
  const limit = 75
  if (mode === 'failed-jobs' || mode === 'manual-retry') {
    return apiFetch(`/admin/operations/recovery-jobs?state_filter=failed&limit=${limit}`)
  }
  if (mode === 'whatsapp-queue') {
    return apiFetch(`/admin/operations/recovery-jobs?state_filter=messaged&limit=${limit}`)
  }
  if (mode === 'call-queue') {
    const [queued, calling] = await Promise.all([
      apiFetch(`/admin/operations/recovery-jobs?state_filter=queued&limit=${limit}`),
      apiFetch(`/admin/operations/recovery-jobs?state_filter=calling&limit=${limit}`),
    ])
    const map = new Map()
    for (const row of [...(Array.isArray(queued) ? queued : []), ...(Array.isArray(calling) ? calling : [])]) {
      map.set(row.id, row)
    }
    return Array.from(map.values()).sort((a, b) => {
      const ta = new Date(a.updated_at || a.created_at || 0).getTime()
      const tb = new Date(b.updated_at || b.created_at || 0).getTime()
      return tb - ta
    })
  }
  // recovery-events
  const filter = stateChip && stateChip !== 'all' ? `&state_filter=${encodeURIComponent(stateChip)}` : ''
  return apiFetch(`/admin/operations/recovery-jobs?limit=${limit}${filter}`)
}

async function fetchWebhooksForMode(mode) {
  if (mode !== 'failed-jobs' && mode !== 'manual-retry') return []
  return apiFetch('/admin/operations/webhooks?status_filter=failed&limit=75')
}

export default function OperationsQueue({ mode = 'recovery-events', title }) {
  const navigate = useNavigate()
  const meta = MODE_META[mode] || MODE_META['recovery-events']
  const pageTitle = title || meta.title

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [overview, setOverview] = useState(null)
  const [jobs, setJobs] = useState([])
  const [webhooks, setWebhooks] = useState([])
  const [busy, setBusy] = useState('')
  const [stateChip, setStateChip] = useState('all')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [data, jobRows, webhookRows] = await Promise.all([
        apiFetch('/admin/operations/overview'),
        fetchJobsForMode(mode, stateChip),
        fetchWebhooksForMode(mode),
      ])
      setOverview(data)
      setJobs(Array.isArray(jobRows) ? jobRows : [])
      setWebhooks(Array.isArray(webhookRows) ? webhookRows : [])
    } catch (e) {
      setError(e?.message || 'Could not load operations data')
      setOverview(null)
      setJobs([])
      setWebhooks([])
    } finally {
      setLoading(false)
    }
  }, [mode, stateChip])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const id = window.setInterval(() => {
      load().catch(() => {})
    }, 30000)
    return () => window.clearInterval(id)
  }, [load])

  useEffect(() => {
    setStateChip('all')
    setMessage('')
    setError('')
  }, [mode])

  const retryRecoveryJob = async (jobId) => {
    setBusy(`job-${jobId}`)
    setMessage('')
    setError('')
    try {
      const res = await apiFetch(`/admin/operations/recovery-jobs/${jobId}/retry`, { method: 'POST' })
      setMessage(res?.dispatch_error ? `Job reset, but worker dispatch failed: ${res.dispatch_error}` : 'Recovery job retry dispatched.')
      await load()
    } catch (e) {
      setError(e?.message || 'Could not retry recovery job')
    } finally {
      setBusy('')
    }
  }

  const retryWebhook = async (eventId) => {
    setBusy(`webhook-${eventId}`)
    setMessage('')
    setError('')
    try {
      const res = await apiFetch(`/admin/operations/webhooks/${eventId}/retry`, { method: 'POST' })
      setMessage(res?.dispatch_error ? `Webhook reset, but worker dispatch failed: ${res.dispatch_error}` : 'Webhook retry dispatched.')
      await load()
    } catch (e) {
      setError(e?.message || 'Could not retry webhook')
    } finally {
      setBusy('')
    }
  }

  const recovery = overview?.recovery_jobs || {}
  const hooks = overview?.webhooks || {}

  const emptyJobsLabel = useMemo(() => {
    if (mode === 'failed-jobs' || mode === 'manual-retry') return 'No failed recovery jobs right now.'
    if (mode === 'call-queue') return 'No jobs currently queued or calling.'
    if (mode === 'whatsapp-queue') return 'No jobs currently in the WhatsApp / messaged step.'
    if (stateChip !== 'all') return `No recovery jobs with status “${stateChip}”.`
    return 'No recovery jobs found yet.'
  }, [mode, stateChip])

  return (
    <div className='opsConsole'>
      <div className='opsConsole-header'>
        <div>
          <h1 className='opsConsole-title'>{pageTitle}</h1>
          <p className='opsConsole-sub'>{meta.subtitle}</p>
        </div>
        <div className='opsConsole-actions'>
          <button type='button' className='btn soft' onClick={load} disabled={loading || Boolean(busy)}>
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </div>

      {error ? <div className='opsConsole-note error'>{error}</div> : null}
      {message ? <div className='opsConsole-note ok'>{message}</div> : null}

      <div className='opsConsole-kpis'>
        <div className='opsConsole-kpi'>
          <div className='opsConsole-kpiLabel'>Recent recovery jobs</div>
          <div className='opsConsole-kpiValue'>{n(recovery.total_recent)}</div>
          <div className='opsConsole-kpiHint'>Last window</div>
        </div>
        <div className='opsConsole-kpi'>
          <div className='opsConsole-kpiLabel'>Failed recovery</div>
          <div className='opsConsole-kpiValue'>{n(recovery.failed)}</div>
          <div className='opsConsole-kpiHint'>Retryable</div>
        </div>
        <div className='opsConsole-kpi'>
          <div className='opsConsole-kpiLabel'>In call pipeline</div>
          <div className='opsConsole-kpiValue'>{n((recovery.queued || 0) + (recovery.calling || 0))}</div>
          <div className='opsConsole-kpiHint'>Queued + calling</div>
        </div>
        <div className='opsConsole-kpi'>
          <div className='opsConsole-kpiLabel'>Failed webhooks</div>
          <div className='opsConsole-kpiValue'>{n(hooks.failed)}</div>
          <div className='opsConsole-kpiHint'>Retry if Vapi / GoCardless</div>
        </div>
      </div>

      {mode === 'recovery-events' ? (
        <div className='opsConsole-filters'>
          <button type='button' className={`opsConsole-chip ${stateChip === 'all' ? 'active' : ''}`} onClick={() => setStateChip('all')}>
            All
          </button>
          {RECOVERY_STATES.map((s) => (
            <button
              key={s}
              type='button'
              className={`opsConsole-chip ${stateChip === s ? 'active' : ''}`}
              onClick={() => setStateChip(s)}
            >
              {s}
              {typeof recovery[s] === 'number' ? ` (${n(recovery[s])})` : ''}
            </button>
          ))}
        </div>
      ) : null}

      <div className='opsConsole-panel'>
        <div className='opsConsole-panelHead'>
          <h3>
            {mode === 'failed-jobs' || mode === 'manual-retry'
              ? 'Failed recovery jobs'
              : mode === 'call-queue'
                ? 'Call pipeline jobs'
                : mode === 'whatsapp-queue'
                  ? 'WhatsApp pipeline jobs'
                  : 'Recovery jobs'}
          </h3>
          <span className='opsConsole-panelHint'>
            {loading ? 'Refreshing…' : `${jobs.length} shown`}
            {meta.retryEmphasis ? ' · Retry resets the job and re-queues the worker' : ''}
          </span>
        </div>
        <div className='opsConsole-tableWrap'>
          {jobs.length ? (
            <table className='opsConsole-table'>
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Status</th>
                  <th>Organisation</th>
                  <th>Provider</th>
                  <th>Attempts</th>
                  <th>Updated</th>
                  <th>Error</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => {
                  const canRetry = jobCanRetry(j, mode)
                  return (
                    <tr key={j.id}>
                      <td>
                        <div className='opsConsole-mono' title={j.id}>{shortId(j.id)}</div>
                        {j.appointment_id ? (
                          <div className='opsConsole-muted' title={j.appointment_id}>Appt {shortId(j.appointment_id)}</div>
                        ) : null}
                      </td>
                      <td>
                        <span className={`opsConsole-badge ${badgeClass(j.state)}`}>{j.state || '—'}</span>
                      </td>
                      <td>
                        {j.org_id ? (
                          <button
                            type='button'
                            className='opsConsole-link'
                            style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer' }}
                            onClick={() => openOrgProfile(j.org_id, navigate)}
                          >
                            {shortId(j.org_id)}
                          </button>
                        ) : (
                          '—'
                        )}
                        {j.org_id ? (
                          <div>
                            <Link className='opsConsole-link' to={`/organisations/${encodeURIComponent(j.org_id)}`}>
                              Detail
                            </Link>
                          </div>
                        ) : null}
                      </td>
                      <td>
                        <div>{j.provider || '—'}</div>
                        {j.provider_status ? <div className='opsConsole-muted'>{j.provider_status}</div> : null}
                        {j.provider_ref ? <div className='opsConsole-muted opsConsole-mono' title={j.provider_ref}>{shortId(j.provider_ref)}</div> : null}
                      </td>
                      <td>{n(j.attempts)}</td>
                      <td>
                        <div>{dateText(j.updated_at || j.created_at)}</div>
                        {j.started_at ? <div className='opsConsole-muted'>Started {dateText(j.started_at)}</div> : null}
                      </td>
                      <td>
                        {j.last_error ? (
                          <div className='opsConsole-errorCell' title={j.last_error}>{truncate(j.last_error)}</div>
                        ) : (
                          <span className='opsConsole-muted'>—</span>
                        )}
                      </td>
                      <td>
                        <div className='opsConsole-rowActions'>
                          {canRetry ? (
                            <button
                              type='button'
                              className={meta.retryEmphasis ? 'btn primary' : 'btn soft'}
                              disabled={busy === `job-${j.id}`}
                              onClick={() => retryRecoveryJob(j.id)}
                            >
                              {busy === `job-${j.id}` ? 'Retrying…' : 'Retry'}
                            </button>
                          ) : (
                            <span className='opsConsole-muted'>{String(j.state) === 'failed' ? '—' : 'No retry'}</span>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          ) : (
            <div className='opsConsole-empty'>{loading ? 'Loading…' : emptyJobsLabel}</div>
          )}
        </div>
      </div>

      {meta.showWebhooks ? (
        <div className='opsConsole-panel'>
          <div className='opsConsole-panelHead'>
            <h3>Failed webhooks</h3>
            <span className='opsConsole-panelHint'>
              Only Vapi and GoCardless support retry. Signature must be valid.
            </span>
          </div>
          <div className='opsConsole-tableWrap'>
            {webhooks.length ? (
              <table className='opsConsole-table'>
                <thead>
                  <tr>
                    <th>Event</th>
                    <th>Status</th>
                    <th>Organisation</th>
                    <th>Provider</th>
                    <th>Signature</th>
                    <th>Attempts</th>
                    <th>Received</th>
                    <th>Error</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {webhooks.map((w) => {
                    const canRetry = webhookCanRetry(w)
                    return (
                      <tr key={w.id}>
                        <td>
                          <div className='opsConsole-mono'>#{w.id}</div>
                          {w.external_event_id ? (
                            <div className='opsConsole-muted' title={w.external_event_id}>{shortId(w.external_event_id)}</div>
                          ) : null}
                        </td>
                        <td>
                          <span className={`opsConsole-badge ${badgeClass(w.status)}`}>{w.status || '—'}</span>
                        </td>
                        <td>
                          {w.org_id ? (
                            <button
                              type='button'
                              className='opsConsole-link'
                              style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer' }}
                              onClick={() => openOrgProfile(w.org_id, navigate)}
                            >
                              {shortId(w.org_id)}
                            </button>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td>{w.provider || '—'}</td>
                        <td>
                          <span className={`opsConsole-badge ${w.signature_valid ? 'green' : 'red'}`}>
                            {w.signature_valid ? 'valid' : 'invalid'}
                          </span>
                        </td>
                        <td>{n(w.attempts)}</td>
                        <td>{dateText(w.received_at)}</td>
                        <td>
                          {w.last_error ? (
                            <div className='opsConsole-errorCell' title={w.last_error}>{truncate(w.last_error)}</div>
                          ) : (
                            <span className='opsConsole-muted'>—</span>
                          )}
                        </td>
                        <td>
                          {canRetry ? (
                            <button
                              type='button'
                              className={meta.retryEmphasis ? 'btn primary' : 'btn soft'}
                              disabled={busy === `webhook-${w.id}`}
                              onClick={() => retryWebhook(w.id)}
                            >
                              {busy === `webhook-${w.id}` ? 'Retrying…' : 'Retry'}
                            </button>
                          ) : (
                            <span className='opsConsole-muted' title={!w.signature_valid ? 'Invalid signature' : 'No retry handler for this provider'}>
                              Cannot retry
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            ) : (
              <div className='opsConsole-empty'>{loading ? 'Loading…' : 'No failed webhooks right now.'}</div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
