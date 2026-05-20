import React, { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { downloadAdminCsv } from '../lib/csvDownload'
import TelnyxInsightsModal from '../components/TelnyxInsightsModal'

function initials(name, company) {
  const source = String(name || company || '?').trim()
  const parts = source.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return source.slice(0, 2).toUpperCase()
}

function statusClass(status) {
  const map = {
    scheduled: 'leadPill leadPillHold',
    calling: 'leadPill leadPillAdvance',
    paused: 'leadPill leadPillNeutral',
    completed: 'leadPill leadPillAdvance',
    failed: 'leadPill leadPillDecline',
    cancelled: 'leadPill',
    no_answer: 'leadPill leadPillDecline',
  }
  return map[status] || 'leadPill'
}

function outcomeClass(outcome) {
  if (!outcome) return 'salesOutcomePill salesOutcomePillMuted'
  if (outcome.demo_agreed) return 'salesOutcomePill salesOutcomePillDemo'
  if (outcome.interested_to_buy) return 'salesOutcomePill salesOutcomePillBuy'
  if (outcome.deal_stage === 'not_interested') return 'salesOutcomePill salesOutcomePillDecline'
  return 'salesOutcomePill salesOutcomePillNeutral'
}

function formatWhen(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString()
}

export default function LeadSales() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState('')
  const [tasks, setTasks] = useState([])
  const [busyId, setBusyId] = useState('')
  const [masterPromptReady, setMasterPromptReady] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [assistantConfigured, setAssistantConfigured] = useState(true)
  const [insightsTarget, setInsightsTarget] = useState(null)

  const load = async () => {
    setLoading(true)
    setMsg('')
    try {
      const [settingsRes, tasksRes] = await Promise.all([
        apiFetch('/admin/frontpage/lead-sales/settings'),
        apiFetch('/admin/frontpage/lead-sales/tasks'),
      ])
      const s = settingsRes?.settings || {}
      setAssistantConfigured(s.assistant_configured !== false)
      setMasterPromptReady(s.master_prompt_configured === true)
      setTasks(tasksRes?.tasks || [])
    } catch (e) {
      const hint =
        e?.status === 404
          ? ' Restart API from voxbulk.com/voxbulk-api.'
          : e?.status === 401 || e?.status === 403
            ? ' Sign in again as platform admin.'
            : ''
      setMsg(`${e?.message || 'Could not load lead sales'}${hint}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const runTaskAction = async (task, action) => {
    setBusyId(`${task.id}-${action}`)
    setMsg('')
    try {
      const data = await apiFetch(`/admin/frontpage/lead-sales/tasks/${task.id}/${action}`, { method: 'POST' })
      if (data?.task) {
        setTasks((rows) => rows.map((r) => (r.id === data.task.id ? data.task : r)))
      }
    } catch (e) {
      setMsg(e?.message || 'Action failed')
    } finally {
      setBusyId('')
    }
  }

  const deleteTask = async (task) => {
    if (!window.confirm(`Delete sales task for ${task.contact_name || 'this lead'}?`)) return
    setBusyId(`${task.id}-delete`)
    try {
      await apiFetch(`/admin/frontpage/lead-sales/tasks/${task.id}`, { method: 'DELETE' })
      setTasks((rows) => rows.filter((r) => r.id !== task.id))
      setMsg('Task deleted.')
    } catch (e) {
      setMsg(e?.message || 'Delete failed')
    } finally {
      setBusyId('')
    }
  }

  const runCall = async (task) => {
    if (task.status === 'paused') {
      await runTaskAction(task, 'resume')
      return
    }
    await runTaskAction(task, 'call-now')
  }

  const stopCall = async (task) => {
    await runTaskAction(task, 'pause')
  }

  const exportCsv = async () => {
    setExporting(true)
    setMsg('')
    try {
      await downloadAdminCsv('/admin/frontpage/lead-sales/tasks/export', 'lead-sales.csv')
      setMsg('CSV exported.')
    } catch (e) {
      setMsg(e?.message || 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Lead sales</h1>
          <p>
            Outbound sales tasks from website leads. Configure the master script under{' '}
            <Link to='/marketing/lead-sales/settings'>Sales setup</Link>, then use <strong>Edit</strong> per lead.
          </p>
        </div>
        <div className='actions'>
          <button type='button' className='btn soft' onClick={exportCsv} disabled={exporting || loading}>
            {exporting ? 'Exporting…' : 'Export CSV'}
          </button>
          <Link className='btn soft' to='/marketing/lead-sales/settings'>
            Sales setup
          </Link>
          <button type='button' className='btn soft' onClick={load} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </button>
          <Link className='btn soft' to='/marketing/lead-sources'>
            Lead sources
          </Link>
        </div>
      </div>

      {!assistantConfigured || !masterPromptReady ? (
        <div className='note noteWarn' style={{ marginBottom: 16 }}>
          Complete <Link to='/marketing/lead-sales/settings'>Sales setup</Link>: Telnyx assistant ID, knowledge base, and
          master sales script (Generate with AI). Without these, tasks will not auto-create or call.
        </div>
      ) : null}

      {msg ? (
        <div className={`note ${/fail|error|enter/i.test(msg) ? 'noteWarn' : ''}`} style={{ marginBottom: 16 }}>
          {msg}
        </div>
      ) : null}

      <section className='card leadSourcesCard'>
        <div className='cardHead'>
          <h3>Sales leads</h3>
          <span className='pill p-cyan'>{tasks.length} leads</span>
        </div>
        <div className='cardBody' style={{ padding: 0 }}>
          <div className='leadSourcesTableWrap'>
            <table className='leadSourcesTable'>
              <thead>
                <tr>
                  <th>Contact</th>
                  <th>Company</th>
                  <th>Lead</th>
                  <th>Scheduled</th>
                  <th>Status</th>
                  <th>Result</th>
                  <th style={{ width: 200 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => {
                  const busy = busyId.startsWith(`${task.id}-`)
                  const finished = ['completed', 'cancelled', 'failed', 'no_answer'].includes(task.status)
                  const canRun = !finished && (task.status === 'paused' || task.status === 'scheduled')
                  const canStop = !finished && (task.status === 'calling' || task.status === 'scheduled')
                  return (
                    <tr key={task.id}>
                      <td>
                        <div className='leadIdentity'>
                          <span className='leadAvatar'>{initials(task.contact_name, task.company_name)}</span>
                          <div>
                            <strong>{task.contact_name || 'Unknown'}</strong>
                            <span className='leadSub muted'>{task.phone || task.email || '—'}</span>
                          </div>
                        </div>
                      </td>
                      <td>{task.company_name || '—'}</td>
                      <td>
                        <span className='leadCode'>{task.lead_code || '—'}</span>
                      </td>
                      <td className='leadDuration'>
                        {formatWhen(task.scheduled_at)}
                        {task.callback_timezone ? (
                          <span className='leadSub muted' style={{ display: 'block' }}>
                            {task.callback_timezone}
                          </span>
                        ) : null}
                      </td>
                      <td>
                        <span className={statusClass(task.status)} title={task.status}>
                          {task.status_label || task.status}
                        </span>
                      </td>
                      <td>
                        {task.call_done ? (
                          <button
                            type='button'
                            className={`salesOutcomeLink ${outcomeClass(task.outcome)}`}
                            onClick={() => setInsightsTarget({
                              taskId: task.id,
                              title: task.contact_name || task.company_name || 'Sales call result',
                            })}
                          >
                            {task.outcome_label || 'View result'}
                          </button>
                        ) : task.last_error ? (
                          <span className='muted' title={task.last_error}>
                            {task.last_error.slice(0, 40)}
                          </span>
                        ) : (
                          <span className='muted'>—</span>
                        )}
                      </td>
                      <td>
                        <div className='leadCallActions' onClick={(e) => e.stopPropagation()}>
                          <button
                            type='button'
                            className='leadPlayBtn'
                            onClick={() => navigate(`/marketing/lead-sales/${task.id}`)}
                          >
                            Edit
                          </button>
                          <button
                            type='button'
                            className='leadPlayBtn'
                            disabled={busy || !canRun}
                            onClick={() => runCall(task)}
                          >
                            {busyId === `${task.id}-call-now` || busyId === `${task.id}-resume` ? '…' : 'Run'}
                          </button>
                          <button
                            type='button'
                            className='leadPlayBtn'
                            disabled={busy || !canStop}
                            onClick={() => stopCall(task)}
                          >
                            {busyId === `${task.id}-pause` ? '…' : 'Stop'}
                          </button>
                          <button
                            type='button'
                            className='leadPlayBtn leadPlayBtnDanger'
                            disabled={busy}
                            onClick={() => deleteTask(task)}
                          >
                            {busyId === `${task.id}-delete` ? '…' : 'Delete'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {!loading && !tasks.length ? (
              <p className='muted' style={{ padding: 24 }}>
                No sales leads yet. They are created when a website lead requests a sales callback — or use{' '}
                <Link to='/marketing/lead-sources'>Lead sources</Link> → Create sales task.
              </p>
            ) : null}
            {loading ? <p className='muted' style={{ padding: 24 }}>Loading…</p> : null}
          </div>
        </div>
      </section>

      {insightsTarget ? (
        <TelnyxInsightsModal
          taskId={insightsTarget.taskId}
          conversationId={insightsTarget.conversationId}
          sessionId={insightsTarget.sessionId}
          title={insightsTarget.title}
          onClose={() => setInsightsTarget(null)}
        />
      ) : null}
    </>
  )
}
