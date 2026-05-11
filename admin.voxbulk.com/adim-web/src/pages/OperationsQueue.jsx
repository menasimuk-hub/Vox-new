import React, { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'

const n = (value) => Number(value || 0).toLocaleString()
const dateText = (value) => value ? new Date(value).toLocaleString() : '—'
const shortId = (value) => String(value || '').slice(0, 8) || '—'
const pillClass = (status) => {
  const s = String(status || '').toLowerCase()
  if (['failed'].includes(s)) return 'p-red'
  if (['queued', 'received', 'processing'].includes(s)) return 'p-cyan'
  if (['calling', 'messaged'].includes(s)) return 'p-amber'
  if (['recovered', 'processed'].includes(s)) return 'p-green'
  return 'p-cyan'
}

export default function OperationsQueue({ title = 'Call queue' }) {
  const [state, setState] = useState({ loading: true, error: '', data: null, jobs: [], webhooks: [] })
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')

  const load = async () => {
    setState((s) => ({ ...s, loading: true, error: '' }))
    const [data, jobs, webhooks] = await Promise.all([
      apiFetch('/admin/operations/overview'),
      apiFetch('/admin/operations/recovery-jobs?limit=20'),
      apiFetch('/admin/operations/webhooks?limit=20'),
    ])
    setState({
      loading: false,
      error: '',
      data,
      jobs: Array.isArray(jobs) ? jobs : [],
      webhooks: Array.isArray(webhooks) ? webhooks : [],
    })
  }

  useEffect(() => {
    let cancelled = false
    load().catch((e) => {
      if (!cancelled) setState({ loading: false, error: e?.message || 'Could not load operations overview', data: null, jobs: [], webhooks: [] })
    })
    return () => { cancelled = true }
  }, [])

  const retryRecoveryJob = async (jobId) => {
    setBusy(`job-${jobId}`)
    setMessage('')
    try {
      const res = await apiFetch(`/admin/operations/recovery-jobs/${jobId}/retry`, { method: 'POST' })
      setMessage(res?.dispatch_error ? `Job reset, but worker dispatch failed: ${res.dispatch_error}` : 'Recovery job retry dispatched.')
      await load()
    } catch (e) {
      setState((s) => ({ ...s, error: e?.message || 'Could not retry recovery job' }))
    } finally {
      setBusy('')
    }
  }

  const retryWebhook = async (eventId) => {
    setBusy(`webhook-${eventId}`)
    setMessage('')
    try {
      const res = await apiFetch(`/admin/operations/webhooks/${eventId}/retry`, { method: 'POST' })
      setMessage(res?.dispatch_error ? `Webhook reset, but worker dispatch failed: ${res.dispatch_error}` : 'Webhook retry dispatched.')
      await load()
    } catch (e) {
      setState((s) => ({ ...s, error: e?.message || 'Could not retry webhook' }))
    } finally {
      setBusy('')
    }
  }

  const recovery = state.data?.recovery_jobs || {}
  const webhooks = state.data?.webhooks || {}
  const rows = useMemo(() => [
    { area: 'Recovery jobs', status: 'queued', count: recovery.queued, latest: recovery.latest_created_at },
    { area: 'Recovery jobs', status: 'calling', count: recovery.calling, latest: recovery.latest_created_at },
    { area: 'Recovery jobs', status: 'messaged', count: recovery.messaged, latest: recovery.latest_created_at },
    { area: 'Recovery jobs', status: 'recovered', count: recovery.recovered, latest: recovery.latest_created_at },
    { area: 'Recovery jobs', status: 'failed', count: recovery.failed, latest: recovery.latest_created_at },
    { area: 'Recovery jobs', status: 'skipped', count: recovery.skipped, latest: recovery.latest_created_at },
    { area: 'Webhooks', status: 'received', count: webhooks.received, latest: webhooks.latest_received_at },
    { area: 'Webhooks', status: 'processing', count: webhooks.processing, latest: webhooks.latest_received_at },
    { area: 'Webhooks', status: 'processed', count: webhooks.processed, latest: webhooks.latest_received_at },
    { area: 'Webhooks', status: 'failed', count: webhooks.failed, latest: webhooks.latest_received_at },
  ], [recovery, webhooks])

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>{title}</h1>
          <p>Live operations overview with real retry controls for recovery jobs and provider webhooks.</p>
        </div>
        <div className='actions'>
          <button className='btn soft' onClick={load} disabled={state.loading || Boolean(busy)}>{state.loading ? 'Loading…' : 'Refresh'}</button>
        </div>
      </div>

      {state.error ? <div className='note' style={{ marginBottom: 16 }}>{state.error}</div> : null}
      {message ? <div className='note' style={{ marginBottom: 16 }}>{message}</div> : null}

      <div className='grid-4' style={{ marginBottom: 16 }}>
        <div className='card stat' style={{ '--accent': '#0891b2' }}><div className='muted'>Recent recovery jobs</div><div className='statValue'>{n(recovery.total_recent)}</div><span className='pill p-cyan'>Last window</span></div>
        <div className='card stat' style={{ '--accent': '#dc2626' }}><div className='muted'>Failed recovery jobs</div><div className='statValue'>{n(recovery.failed)}</div><span className='pill p-red'>Retryable</span></div>
        <div className='card stat' style={{ '--accent': '#0f766e' }}><div className='muted'>Recent webhooks</div><div className='statValue'>{n(webhooks.total_recent)}</div><span className='pill p-green'>Received/processed</span></div>
        <div className='card stat' style={{ '--accent': '#d97706' }}><div className='muted'>Failed webhooks</div><div className='statValue'>{n(webhooks.failed)}</div><span className='pill p-amber'>Retryable</span></div>
      </div>

      <div className='grid-12'>
        <div className='span-6 card'>
          <div className='cardHead'><h3>Recent recovery jobs</h3><span className='pill p-cyan'>Retry wired</span></div>
          <div className='cardBody'>
            <table className='table'>
              <thead><tr><th>Job</th><th>Status</th><th>Attempts</th><th>Updated</th><th>Action</th></tr></thead>
              <tbody>
                {state.jobs.length ? state.jobs.map((j) => (
                  <tr key={j.id}>
                    <td title={j.id}>{shortId(j.id)}<br /><span className='muted'>{j.provider || '—'}</span></td>
                    <td><span className={`pill ${pillClass(j.state)}`}>{j.state}</span></td>
                    <td>{n(j.attempts)}</td>
                    <td>{dateText(j.updated_at || j.created_at)}</td>
                    <td><button className='btn soft' disabled={busy === `job-${j.id}`} onClick={() => retryRecoveryJob(j.id)}>{busy === `job-${j.id}` ? 'Retrying…' : 'Retry'}</button></td>
                  </tr>
                )) : <tr><td colSpan={5}>No recovery jobs found.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        <div className='span-6 card'>
          <div className='cardHead'><h3>Recent webhooks</h3><span className='pill p-cyan'>Replay wired</span></div>
          <div className='cardBody'>
            <table className='table'>
              <thead><tr><th>Event</th><th>Provider</th><th>Status</th><th>Attempts</th><th>Action</th></tr></thead>
              <tbody>
                {state.webhooks.length ? state.webhooks.map((w) => (
                  <tr key={w.id}>
                    <td>#{w.id}<br /><span className='muted'>{dateText(w.received_at)}</span></td>
                    <td>{w.provider}</td>
                    <td><span className={`pill ${pillClass(w.status)}`}>{w.status}</span></td>
                    <td>{n(w.attempts)}</td>
                    <td><button className='btn soft' disabled={busy === `webhook-${w.id}`} onClick={() => retryWebhook(w.id)}>{busy === `webhook-${w.id}` ? 'Retrying…' : 'Retry'}</button></td>
                  </tr>
                )) : <tr><td colSpan={5}>No webhook events found.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        <div className='span-12 card'>
          <div className='cardHead'><h3>Operations status counts</h3><span className='pill p-cyan'>DB-backed</span></div>
          <div className='cardBody'>
            <table className='table'>
              <thead><tr><th>Area</th><th>Status</th><th>Count</th><th>Latest record</th></tr></thead>
              <tbody>
                {rows.some((r) => Number(r.count || 0) > 0) ? rows.map((r) => (
                  <tr key={`${r.area}-${r.status}`}><td>{r.area}</td><td><span className={`pill ${pillClass(r.status)}`}>{r.status}</span></td><td>{n(r.count)}</td><td>{dateText(r.latest)}</td></tr>
                )) : <tr><td colSpan={4}>No recovery jobs or webhook events found yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  )
}
