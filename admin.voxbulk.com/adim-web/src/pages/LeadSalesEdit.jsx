import React, { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiFetch, getApiBaseUrl } from '../lib/api'
import TelnyxDualWaveform from '../components/TelnyxDualWaveform'

async function resolveAdminBearerToken() {
  if (typeof window === 'undefined') return ''
  return localStorage.getItem('retover_admin_access_token') || localStorage.getItem('access_token') || ''
}

function formatWhen(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return d.toISOString().slice(0, 16)
}

function displayWhen(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString()
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

function OutcomeResults({ task, onSync, syncing }) {
  const outcome = task?.outcome
  const callDone = task?.call_done

  if (!callDone) {
    return (
      <section className='card' style={{ marginTop: 14 }}>
        <div className='cardHead'>
          <h3>Call results</h3>
          <span className='pill p-cyan'>Pending</span>
        </div>
        <div className='cardBody'>
          <p className='muted' style={{ margin: 0 }}>
            Results appear here after the outbound call completes. Use <strong>Run</strong> on the list or{' '}
            <strong>Call now</strong> below.
          </p>
        </div>
      </section>
    )
  }

  return (
    <section className='card salesResultsCard' style={{ marginTop: 18 }}>
      <div className='cardHead'>
        <h3>Call results</h3>
        <span className='salesDoneBadge'>Call done</span>
        <button type='button' className='btn soft' style={{ marginLeft: 'auto' }} onClick={onSync} disabled={syncing}>
          {syncing ? 'Syncing…' : 'Refresh from Telnyx'}
        </button>
      </div>
      <div className='cardBody'>
        {!outcome ? (
          <p className='muted'>
            Call finished — click <strong>Refresh from Telnyx</strong> to load transcript and analyse with DeepSeek.
          </p>
        ) : (
          <>
            <div className='salesOutcomeGrid'>
              <div className={`salesOutcomeTile${outcome.demo_agreed ? ' isPositive' : ''}`}>
                <span className='salesOutcomeTileLabel'>Demo</span>
                <strong>{outcome.demo_agreed ? 'Agreed' : 'No demo'}</strong>
                {outcome.demo_scheduled_at ? (
                  <span className='muted'>{displayWhen(outcome.demo_scheduled_at)}</span>
                ) : null}
              </div>
              <div className={`salesOutcomeTile${outcome.interested_to_buy ? ' isPositive' : ''}`}>
                <span className='salesOutcomeTileLabel'>Purchase intent</span>
                <strong>{outcome.interested_to_buy ? 'Interested to buy' : 'Not ready'}</strong>
              </div>
              <div className='salesOutcomeTile'>
                <span className='salesOutcomeTileLabel'>Stage</span>
                <strong>{String(outcome.deal_stage || '—').replace(/_/g, ' ')}</strong>
              </div>
              <div className='salesOutcomeTile'>
                <span className='salesOutcomeTileLabel'>Sentiment</span>
                <strong>{outcome.sentiment || '—'}</strong>
              </div>
            </div>
            <div className='note' style={{ marginTop: 16 }}>
              <strong>Summary</strong>
              <p style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap' }}>{outcome.outcome_summary || '—'}</p>
            </div>
            <div className='grid two' style={{ marginTop: 12, gap: 12 }}>
              <div className='note'>
                <strong>Next step</strong>
                <p style={{ margin: '8px 0 0' }}>{outcome.next_step || '—'}</p>
              </div>
              <div className='note'>
                <strong>Objections</strong>
                <p style={{ margin: '8px 0 0' }}>
                  {(outcome.objections || []).length ? outcome.objections.join(' · ') : 'None recorded'}
                </p>
              </div>
            </div>
          </>
        )}
        {task.sales_transcript_text ? (
          <details style={{ marginTop: 16 }}>
            <summary className='muted' style={{ cursor: 'pointer', fontWeight: 600 }}>
              Sales call transcript
            </summary>
            <pre className='frontpagePromptPreview' style={{ marginTop: 8 }}>
              {task.sales_transcript_text}
            </pre>
          </details>
        ) : null}
      </div>
    </section>
  )
}

function RecordingsPanel({ lead, taskId, callDone }) {
  const waveRef = useRef(null)
  const [authToken, setAuthToken] = useState('')
  const [intakeUrl, setIntakeUrl] = useState('')
  const [salesUrl, setSalesUrl] = useState('')
  const [tab, setTab] = useState('intake')
  const [mediaError, setMediaError] = useState('')

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      if (!lead?.id && !taskId) return
      const token = await resolveAdminBearerToken()
      const base = getApiBaseUrl()
      const origin = typeof window !== 'undefined' ? window.location.origin : ''
      const intakePath = lead?.recording_url || (lead?.id ? `/admin/frontpage/lead-sources/${lead.id}/recording` : '')
      const intakeFull = intakePath ? (base ? `${base}${intakePath}` : `${origin}${intakePath}`) : ''
      const salesPath = taskId ? `/admin/frontpage/lead-sales/tasks/${taskId}/recording` : ''
      const salesFull = salesPath ? (base ? `${base}${salesPath}` : `${origin}${salesPath}`) : ''
      if (!cancelled) {
        setAuthToken(token || '')
        setIntakeUrl(lead?.recording_available ? intakeFull : '')
        setSalesUrl(callDone ? salesFull : '')
        if (lead?.recording_available) setTab('intake')
        else if (callDone) setTab('sales')
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [lead?.id, lead?.recording_url, lead?.recording_available, taskId, callDone])

  const hasIntake = Boolean(intakeUrl)
  const hasSales = Boolean(salesUrl)
  const activeSrc = tab === 'sales' ? salesUrl : intakeUrl
  const transcript = [lead?.transcript_text, lead?.agent_response_text].filter(Boolean).join('\n\n')

  if (!lead && !hasSales) return null

  return (
    <section className='card salesRecordingsCard' style={{ marginTop: 14 }}>
      <div className='cardHead'>
        <h3>Recordings</h3>
        {lead?.lead_code ? <span className='pill p-cyan'>{lead.lead_code}</span> : null}
        <Link className='btn soft' style={{ marginLeft: 'auto' }} to='/marketing/lead-sources'>
          Lead sources
        </Link>
      </div>
      <div className='cardBody'>
        <div className='salesRecordingTabs' role='tablist'>
          <button
            type='button'
            role='tab'
            aria-selected={tab === 'intake'}
            className={`salesRecordingTab${tab === 'intake' ? ' isActive' : ''}`}
            disabled={!hasIntake}
            onClick={() => {
              setMediaError('')
              setTab('intake')
            }}
          >
            Website call
          </button>
          <button
            type='button'
            role='tab'
            aria-selected={tab === 'sales'}
            className={`salesRecordingTab${tab === 'sales' ? ' isActive' : ''}`}
            disabled={!hasSales}
            onClick={() => {
              setMediaError('')
              setTab('sales')
            }}
          >
            Outbound sales
          </button>
        </div>
        {!hasIntake && !hasSales ? (
          <p className='muted' style={{ margin: 0 }}>
            No recording yet. Intake appears after the website call; outbound audio after the sales call completes.
          </p>
        ) : null}
        {activeSrc ? (
          <TelnyxDualWaveform
            key={activeSrc}
            ref={waveRef}
            src={activeSrc}
            authToken={authToken}
            onError={(message) => setMediaError(message)}
          />
        ) : tab === 'sales' && !callDone ? (
          <p className='muted' style={{ marginTop: 8 }}>Run the outbound call first — recording appears when the call finishes.</p>
        ) : hasIntake || hasSales ? (
          <p className='muted' style={{ marginTop: 8 }}>Recording not available for this tab yet.</p>
        ) : null}
        {mediaError ? <div className='note noteWarn' style={{ marginTop: 10 }}>{mediaError}</div> : null}
        {tab === 'intake' && transcript ? (
          <details className='salesRecordingTranscript'>
            <summary className='muted'>Intake transcript</summary>
            <pre className='frontpagePromptPreview'>{transcript}</pre>
          </details>
        ) : null}
        {tab === 'sales' && callDone ? (
          <p className='muted' style={{ fontSize: 12, marginTop: 10, marginBottom: 0 }}>
            Sales transcript is in <strong>Call results</strong> below after you refresh from Telnyx.
          </p>
        ) : null}
      </div>
    </section>
  )
}

export default function LeadSalesEdit() {
  const { taskId } = useParams()
  const promptRef = useRef(null)
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState('')
  const [task, setTask] = useState(null)
  const [lead, setLead] = useState(null)
  const [form, setForm] = useState({})
  const [busy, setBusy] = useState('')
  const [generatingPrompt, setGeneratingPrompt] = useState(false)
  const [syncingOutcome, setSyncingOutcome] = useState(false)
  const [showPrompt, setShowPrompt] = useState(false)

  const load = async () => {
    setLoading(true)
    setMsg('')
    try {
      const data = await apiFetch(`/admin/frontpage/lead-sales/tasks/${taskId}`)
      const t = data?.task
      setTask(t)
      setLead(data?.lead || null)
      setForm({
        contact_name: t?.contact_name || '',
        company_name: t?.company_name || '',
        email: t?.email || '',
        phone: t?.phone || '',
        interest_summary: t?.interest_summary || '',
        sales_intent: t?.sales_intent || '',
        scheduled_at: formatWhen(t?.scheduled_at),
        callback_timezone: t?.callback_timezone || '',
        callback_consent: Boolean(t?.callback_consent),
      })
    } catch (e) {
      setMsg(e?.message || 'Could not load task')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [taskId])

  const saveDetails = async () => {
    setBusy('save')
    setMsg('')
    try {
      const data = await apiFetch(`/admin/frontpage/lead-sales/tasks/${taskId}`, {
        method: 'PUT',
        body: JSON.stringify({
          ...form,
          scheduled_at: form.scheduled_at ? new Date(form.scheduled_at).toISOString() : null,
        }),
      })
      setTask(data?.task)
      setMsg('Lead details saved.')
    } catch (e) {
      setMsg(e?.message || 'Save failed')
    } finally {
      setBusy('')
    }
  }

  const runAction = async (action) => {
    setBusy(action)
    try {
      const data = await apiFetch(`/admin/frontpage/lead-sales/tasks/${taskId}/${action}`, { method: 'POST' })
      if (data?.task) setTask(data.task)
      if (action === 'regenerate-prompt') setMsg('Prompt generated with DeepSeek.')
    } catch (e) {
      setMsg(e?.message || 'Action failed')
    } finally {
      setBusy('')
    }
  }

  const generatePrompt = async () => {
    setGeneratingPrompt(true)
    await runAction('regenerate-prompt')
    setGeneratingPrompt(false)
    setShowPrompt(true)
    promptRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const syncOutcome = async () => {
    setSyncingOutcome(true)
    try {
      const data = await apiFetch(`/admin/frontpage/lead-sales/tasks/${taskId}/sync-outcome`, { method: 'POST' })
      if (data?.task) setTask(data.task)
      setMsg('Results updated from Telnyx + DeepSeek.')
    } catch (e) {
      setMsg(e?.message || 'Could not sync results')
    } finally {
      setSyncingOutcome(false)
    }
  }

  if (loading) {
    return <p className='muted' style={{ padding: 24 }}>Loading…</p>
  }

  if (!task) {
    return (
      <div className='note noteWarn'>
        <p>{msg || 'Task not found'}</p>
        <Link to='/marketing/lead-sales'>Back to list</Link>
      </div>
    )
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <Link to='/marketing/lead-sales' className='muted' style={{ fontSize: 13 }}>
            ← Back to sales leads
          </Link>
          <h1 style={{ marginTop: 8 }}>{task.contact_name || 'Sales lead'}</h1>
          <p className='muted'>
            {task.lead_code ? `${task.lead_code} · ` : ''}
            {task.company_name || '—'} · <span className={statusClass(task.status)}>{task.status_label || task.status}</span>
            {task.callback_timezone ? ` · ${task.callback_timezone}` : ''}
            {task.call_done ? <span className='salesDoneBadge'>Call done</span> : null}
          </p>
        </div>
        <div className='actions'>
          <button type='button' className='btn primary' disabled={!!busy} onClick={() => runAction('call-now')}>
            {busy === 'call-now' ? 'Calling…' : 'Call now'}
          </button>
          {task.status === 'paused' ? (
            <button type='button' className='btn soft' disabled={!!busy} onClick={() => runAction('resume')}>
              Resume
            </button>
          ) : (
            <button type='button' className='btn soft' disabled={!!busy} onClick={() => runAction('pause')}>
              Stop
            </button>
          )}
        </div>
      </div>

      {msg ? <div className='note' style={{ marginBottom: 16 }}>{msg}</div> : null}

      <section className='card salesLeadDetailsCard'>
        <div className='cardHead salesLeadDetailsHead'>
          <h3>Lead details</h3>
          <button type='button' className='btn primary salesLeadSaveBtn' onClick={saveDetails} disabled={busy === 'save'}>
            {busy === 'save' ? 'Saving…' : 'Save'}
          </button>
        </div>
        <div className='cardBody salesLeadDetailsBody'>
          <div className='salesLeadDetailsGrid'>
            <label className='salesLeadField'>
              <span>Name</span>
              <input className='input inputCompact' value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} />
            </label>
            <label className='salesLeadField'>
              <span>Company</span>
              <input className='input inputCompact' value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} />
            </label>
            <label className='salesLeadField'>
              <span>Email</span>
              <input className='input inputCompact' type='email' value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </label>
            <label className='salesLeadField'>
              <span>Phone</span>
              <input className='input inputCompact' value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </label>
            <label className='salesLeadField'>
              <span>Callback</span>
              <input
                className='input inputCompact'
                type='datetime-local'
                value={form.scheduled_at}
                onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })}
              />
            </label>
            <label className='salesLeadField'>
              <span>Timezone</span>
              <input
                className='input inputCompact'
                value={form.callback_timezone}
                onChange={(e) => setForm({ ...form, callback_timezone: e.target.value })}
                placeholder='Europe/London'
              />
            </label>
            <label className='salesLeadField salesLeadFieldWide'>
              <span>Interest</span>
              <input
                className='input inputCompact'
                value={form.interest_summary}
                onChange={(e) => setForm({ ...form, interest_summary: e.target.value })}
              />
            </label>
            <label className='salesLeadField salesLeadFieldWide'>
              <span>Sales intent</span>
              <input
                className='input inputCompact'
                value={form.sales_intent}
                onChange={(e) => setForm({ ...form, sales_intent: e.target.value })}
              />
            </label>
            <label className='salesLeadConsent'>
              <input
                type='checkbox'
                checked={form.callback_consent}
                onChange={(e) => setForm({ ...form, callback_consent: e.target.checked })}
              />
              <span>Consent recorded</span>
            </label>
          </div>
        </div>
      </section>

      <RecordingsPanel lead={lead} taskId={taskId} callDone={task.call_done} />

      <OutcomeResults task={task} onSync={syncOutcome} syncing={syncingOutcome} />

      <section ref={promptRef} className='card frontpagePromptCard' style={{ marginTop: 18 }}>
        <div className='cardHead'>
          <h3>Sales call prompt</h3>
          <span className='pill p-cyan'>v{task.sales_prompt_version || 1} · DeepSeek</span>
        </div>
        <div className='cardBody frontpagePromptFull'>
          <p className='muted' style={{ marginTop: 0 }}>
            Generated from lead data + playbook. Synced to Telnyx before each call.
          </p>
          <div className='actions' style={{ gap: 8 }}>
            <button type='button' className='btn primary' onClick={generatePrompt} disabled={generatingPrompt}>
              {generatingPrompt ? 'Generating…' : 'Generate prompt with AI'}
            </button>
            <button type='button' className='btn soft' onClick={() => setShowPrompt((v) => !v)} disabled={!task.sales_prompt}>
              {showPrompt ? 'Hide' : 'View'} prompt
            </button>
          </div>
          {showPrompt && task.sales_prompt ? (
            <pre className='frontpagePromptPreview'>{task.sales_prompt}</pre>
          ) : (
            !task.sales_prompt && <p className='muted' style={{ marginBottom: 0 }}>No prompt yet — generate with AI before calling.</p>
          )}
        </div>
      </section>

    </>
  )
}
