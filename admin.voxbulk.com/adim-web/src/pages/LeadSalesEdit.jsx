import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiFetch, resolveApiUrl } from '../lib/api'
import { readAdminAccessToken, readSharedAccessToken } from '../lib/sessionStorage'
import TelnyxDualWaveform from '../components/TelnyxDualWaveform'
import TelnyxInsightsModal from '../components/TelnyxInsightsModal'
import TelnyxPromptPreview from '../components/TelnyxPromptPreview'
import LeadSalesPipelineStrip from '../components/LeadSalesPipelineStrip'
import {
  ArrowLeft,
  Save,
  CheckCircle2,
  XCircle,
  Phone,
  RefreshCw,
  Bot,
  Eye,
  EyeOff,
  Sparkles,
} from 'lucide-react'

async function resolveAdminBearerToken() {
  if (typeof window === 'undefined') return ''
  return readAdminAccessToken() || readSharedAccessToken()
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

function statusBadgeStyle(status) {
  const styles = {
    pending_approval: { bg: '#fef3c7', color: '#92400e', border: '#fde68a' },
    approved: { bg: '#dbeafe', color: '#1e4a7a', border: '#bfdbfe' },
    calling: { bg: '#e0e7ff', color: '#4338ca', border: '#c7d2fe' },
    completed: { bg: '#dcfce7', color: '#14532d', border: '#bbf7d0' },
    rejected: { bg: '#fee2e2', color: '#991b1b', border: '#fecaca' },
    no_answer: { bg: '#fee2e2', color: '#991b1b', border: '#fecaca' },
    failed: { bg: '#fee2e2', color: '#991b1b', border: '#fecaca' },
  }
  return styles[status] || { bg: 'var(--ds-surface-muted)', color: 'var(--ds-text-secondary)', border: 'var(--ds-border)' }
}

function Badge({ children, variant = 'default' }) {
  let style = {}
  if (variant === 'success') {
    style = { background: '#dcfce7', color: '#14532d', border: '1px solid #bbf7d0' }
  } else if (variant === 'danger') {
    style = { background: '#fee2e2', color: '#991b1b', border: '1px solid #fecaca' }
  } else {
    style = { background: 'var(--ds-surface-muted)', color: 'var(--ds-text-primary)', border: '1px solid var(--ds-border)' }
  }
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        borderRadius: '30px',
        padding: '0.15rem 0.7rem',
        fontSize: '0.7rem',
        fontWeight: 600,
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {children}
    </span>
  )
}

function Button({ children, onClick, disabled, variant = 'default', size = 'default', className = '', ...props }) {
  let baseStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.5rem',
    borderRadius: '8px',
    fontWeight: 500,
    fontSize: size === 'sm' ? '0.8rem' : '0.875rem',
    padding: size === 'sm' ? '0.4rem 0.8rem' : '0.5rem 1rem',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
    border: '1px solid transparent',
    transition: 'all 0.15s',
  }

  if (variant === 'primary') {
    baseStyle.background = 'var(--ds-primary)'
    baseStyle.color = 'var(--ds-primary-foreground)'
  } else if (variant === 'soft') {
    baseStyle.background = 'var(--ds-surface-muted)'
    baseStyle.color = 'var(--ds-text-primary)'
    baseStyle.border = '1px solid var(--ds-border)'
  } else if (variant === 'success') {
    baseStyle.background = '#dcfce7'
    baseStyle.color = '#14532d'
    baseStyle.border = '1px solid #bbf7d0'
  } else if (variant === 'danger') {
    baseStyle.background = '#fee2e2'
    baseStyle.color = '#991b1b'
    baseStyle.border = '1px solid #fecaca'
  } else {
    baseStyle.background = 'var(--ds-surface-muted)'
    baseStyle.color = 'var(--ds-text-primary)'
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={baseStyle}
      className={className}
      {...props}
    >
      {children}
    </button>
  )
}

function Panel({ title, badge, actions, children }) {
  return (
    <section
      style={{
        background: 'var(--ds-surface)',
        border: '1px solid var(--ds-border)',
        borderRadius: '14px',
        marginTop: '16px',
        overflow: 'hidden',
      }}
    >
      {title && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            padding: '1rem 1.5rem',
            borderBottom: '1px solid var(--ds-border)',
            background: 'var(--ds-surface-muted)',
          }}
        >
          <h3 style={{ fontSize: '0.95rem', fontWeight: 600, margin: 0, color: 'var(--ds-text-primary)' }}>{title}</h3>
          {badge}
          {actions && <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.5rem' }}>{actions}</div>}
        </div>
      )}
      <div style={{ padding: '1.5rem' }}>{children}</div>
    </section>
  )
}

function Input({ label, type = 'text', value, onChange, placeholder, className = '' }) {
  return (
    <label style={{ display: 'block' }}>
      {label && (
        <span
          style={{
            display: 'block',
            fontSize: '0.8rem',
            fontWeight: 500,
            marginBottom: '0.4rem',
            color: 'var(--ds-text-primary)',
          }}
        >
          {label}
        </span>
      )}
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className={className}
        style={{
          width: '100%',
          padding: '0.5rem 0.75rem',
          fontSize: '0.875rem',
          borderRadius: '8px',
          border: '1px solid var(--ds-border)',
          background: 'transparent',
          color: 'var(--ds-text-primary)',
        }}
      />
    </label>
  )
}

function OutcomeResults({ task, onSync, syncing, onViewInsight }) {
  const outcome = task?.outcome
  const callDone = task?.call_done

  if (!callDone) {
    return (
      <Panel
        title="Call results"
        badge={<Badge>Pending</Badge>}
      >
        <p style={{ margin: 0, color: 'var(--ds-text-secondary)', fontSize: '0.875rem' }}>
          Results appear here after the outbound call completes. Use <strong>Call now</strong> to start the call.
        </p>
      </Panel>
    )
  }

  return (
    <Panel
      title="Call results"
      badge={<Badge variant="success">Call done</Badge>}
      actions={
        <>
          <Button variant="soft" size="sm" onClick={onViewInsight}>
            <Bot className="h-4 w-4" />
            Assistant result
          </Button>
          <Button variant="soft" size="sm" onClick={onSync} disabled={syncing}>
            <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
            {syncing ? 'Syncing…' : 'Refresh from Telnyx'}
          </Button>
        </>
      }
    >
      {!outcome ? (
        <p style={{ color: 'var(--ds-text-secondary)', fontSize: '0.875rem' }}>
          Call finished — click <strong>Refresh from Telnyx</strong> to load transcript and analyse with DeepSeek.
        </p>
      ) : (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '1rem',
            }}
          >
            <div
              style={{
                background: outcome.demo_agreed ? '#dcfce7' : 'var(--ds-surface-muted)',
                padding: '1rem',
                borderRadius: '10px',
                border: outcome.demo_agreed ? '1px solid #bbf7d0' : '1px solid var(--ds-border)',
              }}
            >
              <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: 600, color: 'var(--ds-text-secondary)', marginBottom: '0.4rem' }}>
                Demo
              </div>
              <div style={{ fontWeight: 600, fontSize: '0.95rem', color: outcome.demo_agreed ? '#14532d' : 'var(--ds-text-primary)' }}>
                {outcome.demo_agreed ? 'Agreed' : 'No demo'}
              </div>
              {outcome.demo_scheduled_at && (
                <div style={{ fontSize: '0.75rem', color: 'var(--ds-text-secondary)', marginTop: '0.3rem' }}>
                  {displayWhen(outcome.demo_scheduled_at)}
                </div>
              )}
            </div>

            <div
              style={{
                background: outcome.interested_to_buy ? '#dcfce7' : 'var(--ds-surface-muted)',
                padding: '1rem',
                borderRadius: '10px',
                border: outcome.interested_to_buy ? '1px solid #bbf7d0' : '1px solid var(--ds-border)',
              }}
            >
              <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: 600, color: 'var(--ds-text-secondary)', marginBottom: '0.4rem' }}>
                Purchase intent
              </div>
              <div style={{ fontWeight: 600, fontSize: '0.95rem', color: outcome.interested_to_buy ? '#14532d' : 'var(--ds-text-primary)' }}>
                {outcome.interested_to_buy ? 'Interested to buy' : 'Not ready'}
              </div>
            </div>

            <div style={{ background: 'var(--ds-surface-muted)', padding: '1rem', borderRadius: '10px', border: '1px solid var(--ds-border)' }}>
              <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: 600, color: 'var(--ds-text-secondary)', marginBottom: '0.4rem' }}>
                Stage
              </div>
              <div style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--ds-text-primary)' }}>
                {String(outcome.deal_stage || '—').replace(/_/g, ' ')}
              </div>
            </div>

            <div style={{ background: 'var(--ds-surface-muted)', padding: '1rem', borderRadius: '10px', border: '1px solid var(--ds-border)' }}>
              <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: 600, color: 'var(--ds-text-secondary)', marginBottom: '0.4rem' }}>
                Sentiment
              </div>
              <div style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--ds-text-primary)' }}>
                {outcome.sentiment || '—'}
              </div>
            </div>
          </div>

          <div
            style={{
              marginTop: '1rem',
              padding: '1rem',
              background: 'var(--ds-surface-muted)',
              borderRadius: '8px',
              border: '1px solid var(--ds-border)',
            }}
          >
            <strong style={{ fontSize: '0.875rem', color: 'var(--ds-text-primary)' }}>Summary</strong>
            <p style={{ margin: '0.5rem 0 0', whiteSpace: 'pre-wrap', fontSize: '0.875rem', lineHeight: 1.6, color: 'var(--ds-text-primary)' }}>
              {outcome.outcome_summary || '—'}
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
            <div
              style={{
                padding: '1rem',
                background: 'var(--ds-surface-muted)',
                borderRadius: '8px',
                border: '1px solid var(--ds-border)',
              }}
            >
              <strong style={{ fontSize: '0.875rem', color: 'var(--ds-text-primary)' }}>Next step</strong>
              <p style={{ margin: '0.5rem 0 0', fontSize: '0.875rem', color: 'var(--ds-text-primary)' }}>{outcome.next_step || '—'}</p>
            </div>
            <div
              style={{
                padding: '1rem',
                background: 'var(--ds-surface-muted)',
                borderRadius: '8px',
                border: '1px solid var(--ds-border)',
              }}
            >
              <strong style={{ fontSize: '0.875rem', color: 'var(--ds-text-primary)' }}>Objections</strong>
              <p style={{ margin: '0.5rem 0 0', fontSize: '0.875rem', color: 'var(--ds-text-primary)' }}>
                {(outcome.objections || []).length ? outcome.objections.join(' · ') : 'None recorded'}
              </p>
            </div>
          </div>
        </>
      )}

      {task.sales_transcript_text && (
        <details style={{ marginTop: '1rem' }}>
          <summary
            style={{
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.875rem',
              color: 'var(--ds-text-secondary)',
              paddingBottom: '0.5rem',
            }}
          >
            Sales call transcript
          </summary>
          <pre
            style={{
              marginTop: '0.5rem',
              padding: '1rem',
              background: 'var(--ds-surface-muted)',
              borderRadius: '8px',
              fontSize: '0.8rem',
              whiteSpace: 'pre-wrap',
              border: '1px solid var(--ds-border)',
              color: 'var(--ds-text-primary)',
            }}
          >
            {task.sales_transcript_text}
          </pre>
        </details>
      )}
    </Panel>
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
      const intakePath = lead?.recording_url || (lead?.id ? `/admin/frontpage/lead-sources/${lead.id}/recording` : '')
      const intakeFull = intakePath ? resolveApiUrl(intakePath) : ''
      const salesPath = taskId ? `/admin/frontpage/lead-sales/tasks/${taskId}/recording` : ''
      const salesFull = salesPath ? resolveApiUrl(salesPath) : ''
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
    <Panel
      title="Recordings"
      badge={lead?.lead_code && <Badge>{lead.lead_code}</Badge>}
      actions={
        <Button variant="soft" size="sm" asChild>
          <Link to="/marketing/leads/inbound">Inbound calls</Link>
        </Button>
      }
    >
      <div
        style={{
          display: 'flex',
          gap: '0.5rem',
          marginBottom: '1rem',
          borderBottom: '1px solid var(--ds-border)',
        }}
      >
        <button
          type="button"
          onClick={() => {
            setMediaError('')
            setTab('intake')
          }}
          disabled={!hasIntake}
          style={{
            padding: '0.5rem 1rem',
            fontSize: '0.85rem',
            fontWeight: 500,
            background: tab === 'intake' ? 'var(--ds-surface)' : 'transparent',
            color: tab === 'intake' ? 'var(--ds-text-primary)' : 'var(--ds-text-secondary)',
            border: 'none',
            borderBottom: tab === 'intake' ? '2px solid var(--ds-primary)' : '2px solid transparent',
            cursor: hasIntake ? 'pointer' : 'not-allowed',
            opacity: hasIntake ? 1 : 0.5,
          }}
        >
          Website call
        </button>
        <button
          type="button"
          onClick={() => {
            setMediaError('')
            setTab('sales')
          }}
          disabled={!hasSales}
          style={{
            padding: '0.5rem 1rem',
            fontSize: '0.85rem',
            fontWeight: 500,
            background: tab === 'sales' ? 'var(--ds-surface)' : 'transparent',
            color: tab === 'sales' ? 'var(--ds-text-primary)' : 'var(--ds-text-secondary)',
            border: 'none',
            borderBottom: tab === 'sales' ? '2px solid var(--ds-primary)' : '2px solid transparent',
            cursor: hasSales ? 'pointer' : 'not-allowed',
            opacity: hasSales ? 1 : 0.5,
          }}
        >
          Outbound sales
        </button>
      </div>

      {!hasIntake && !hasSales ? (
        <p style={{ margin: 0, color: 'var(--ds-text-secondary)', fontSize: '0.875rem' }}>
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
        <p style={{ marginTop: '0.5rem', color: 'var(--ds-text-secondary)', fontSize: '0.875rem' }}>
          Run the outbound call first — recording appears when the call finishes.
        </p>
      ) : hasIntake || hasSales ? (
        <p style={{ marginTop: '0.5rem', color: 'var(--ds-text-secondary)', fontSize: '0.875rem' }}>
          Recording not available for this tab yet.
        </p>
      ) : null}

      {mediaError && (
        <div
          style={{
            marginTop: '0.75rem',
            padding: '0.75rem',
            background: '#fee2e2',
            border: '1px solid #fecaca',
            borderRadius: '8px',
            color: '#991b1b',
            fontSize: '0.875rem',
          }}
        >
          {mediaError}
        </div>
      )}

      {tab === 'intake' && transcript && (
        <details style={{ marginTop: '1rem' }}>
          <summary
            style={{
              cursor: 'pointer',
              color: 'var(--ds-text-secondary)',
              fontSize: '0.875rem',
              fontWeight: 600,
            }}
          >
            Intake transcript
          </summary>
          <pre
            style={{
              marginTop: '0.5rem',
              padding: '1rem',
              background: 'var(--ds-surface-muted)',
              borderRadius: '8px',
              fontSize: '0.8rem',
              whiteSpace: 'pre-wrap',
              border: '1px solid var(--ds-border)',
              color: 'var(--ds-text-primary)',
            }}
          >
            {transcript}
          </pre>
        </details>
      )}

      {tab === 'sales' && callDone && (
        <p style={{ fontSize: '0.75rem', marginTop: '0.75rem', marginBottom: 0, color: 'var(--ds-text-secondary)' }}>
          Sales transcript is in <strong>Call results</strong> below after you refresh from Telnyx.
        </p>
      )}
    </Panel>
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
  const [showInsights, setShowInsights] = useState(false)

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

  const sendDemoInvite = async () => {
    setBusy('demo-invite')
    setMsg('')
    try {
      await apiFetch('/admin/ai-demo/requests/manual', {
        method: 'POST',
        body: JSON.stringify({
          contact_name: task.contact_name || 'Guest',
          email: task.email || '',
          company_name: task.company_name || 'Company',
          whatsapp: task.phone || task.whatsapp || '',
          website: task.website || 'https://voxbulk.com',
          preferred_language: 'en',
          message: 'Manual invite from Lead Sales',
          lead_sales_task_id: taskId,
        }),
      })
      setMsg('AI demo invite emailed (and WhatsApp notice sent if number valid).')
    } catch (e) {
      setMsg(e?.message || 'Failed to send demo invite')
    } finally {
      setBusy('')
    }
  }

  const canCall = (t) => {
    if (typeof t?.can_call === 'boolean') return t.can_call
    return t?.callback_consent === true && t?.status === 'approved'
  }

  const canApprove = (t) => {
    if (typeof t?.can_approve === 'boolean') return t.can_approve
    return t?.callback_consent === true && t?.status === 'pending_approval'
  }

  if (loading) {
    return (
      <p style={{ padding: '1.5rem', color: 'var(--ds-text-secondary)' }}>Loading…</p>
    )
  }

  if (!task) {
    return (
      <div
        style={{
          padding: '1rem',
          background: '#fee2e2',
          border: '1px solid #fecaca',
          borderRadius: '8px',
          color: '#991b1b',
        }}
      >
        <p>{msg || 'Task not found'}</p>
          <Link to="/marketing/leads/tasks" style={{ color: '#991b1b', textDecoration: 'underline' }}>
          Back to list
        </Link>
      </div>
    )
  }

  const badgeStyle = statusBadgeStyle(task.status)
  const consentBadgeStyle = task.callback_consent === true
    ? { bg: '#dcfce7', color: '#14532d', border: '#bbf7d0' }
    : { bg: '#fee2e2', color: '#991b1b', border: '#fecaca' }

  return (
    <>
      <LeadSalesPipelineStrip active="sales" />
      <div style={{ marginBottom: '1.5rem' }}>
        <Link
          to="/marketing/leads/tasks"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.3rem',
            fontSize: '0.85rem',
            color: 'var(--ds-text-secondary)',
            textDecoration: 'none',
            marginBottom: '0.75rem',
          }}
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Sales tasks
        </Link>

        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <p style={{ margin: '0 0 0.35rem', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ds-text-secondary)' }}>
              Full editor · same pipeline as Sales tasks list
            </p>
            <h1 style={{ fontSize: '1.5rem', fontWeight: 600, margin: '0 0 0.5rem', color: 'var(--ds-text-primary)' }}>
              {task.contact_name || 'Sales lead'}
            </h1>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap', fontSize: '0.875rem', color: 'var(--ds-text-secondary)' }}>
              <span>{task.company_name || '—'}</span>
              <span
                style={{
                  background: badgeStyle.bg,
                  color: badgeStyle.color,
                  border: `1px solid ${badgeStyle.border}`,
                  padding: '0.15rem 0.7rem',
                  borderRadius: '30px',
                  fontSize: '0.7rem',
                  fontWeight: 600,
                }}
              >
                {task.status_label || task.status}
              </span>
              <span
                style={{
                  background: consentBadgeStyle.bg,
                  color: consentBadgeStyle.color,
                  border: `1px solid ${consentBadgeStyle.border}`,
                  padding: '0.15rem 0.7rem',
                  borderRadius: '30px',
                  fontSize: '0.7rem',
                  fontWeight: 600,
                }}
              >
                Consent: {task.callback_consent ? 'Yes' : 'No'}
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {task.status === 'pending_approval' && (
              <>
                <Button
                  variant="success"
                  onClick={() => runAction('approve')}
                  disabled={!!busy || !canApprove(task)}
                  title={!canApprove(task) ? 'Consent required before approve' : undefined}
                >
                  <CheckCircle2 className="h-4 w-4" />
                  {busy === 'approve' ? 'Approving…' : 'Approve'}
                </Button>
                <Button
                  variant="danger"
                  onClick={() => runAction('reject')}
                  disabled={!!busy}
                >
                  <XCircle className="h-4 w-4" />
                  {busy === 'reject' ? 'Rejecting…' : 'Reject'}
                </Button>
              </>
            )}
            <Button
              variant="primary"
              onClick={() => runAction(task.call_done ? 'call-again' : 'call-now')}
              disabled={!!busy || !canCall(task) || task.status === 'calling'}
              title={!canCall(task) ? 'Consent + approval required to call' : undefined}
            >
              <Phone className="h-4 w-4" />
              {busy === 'call-now' || busy === 'call-again'
                ? 'Calling…'
                : task.call_done
                  ? 'Call again'
                  : 'Call now'}
            </Button>
            <Button variant="soft" onClick={sendDemoInvite} disabled={!!busy}>
              <Bot className="h-4 w-4" />
              {busy === 'demo-invite' ? 'Sending…' : 'Send AI demo'}
            </Button>
            {task.status === 'paused' ? (
              <Button variant="soft" onClick={() => runAction('resume')} disabled={!!busy}>
                Resume
              </Button>
            ) : (
              <Button variant="soft" onClick={() => runAction('pause')} disabled={!!busy}>
                Pause
              </Button>
            )}
            <Button variant="primary" onClick={saveDetails} disabled={busy === 'save'}>
              <Save className="h-4 w-4" />
              {busy === 'save' ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </div>
      </div>

      {msg && (
        <div
          style={{
            padding: '0.75rem 1rem',
            marginBottom: '1rem',
            background: /fail|error/i.test(msg) ? '#fee2e2' : '#dcfce7',
            border: /fail|error/i.test(msg) ? '1px solid #fecaca' : '1px solid #bbf7d0',
            borderRadius: '8px',
            color: /fail|error/i.test(msg) ? '#991b1b' : '#14532d',
            fontSize: '0.875rem',
          }}
        >
          {msg}
        </div>
      )}

      <Panel title="Lead details">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem' }}>
          <Input
            label="Name"
            value={form.contact_name}
            onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
          />
          <Input
            label="Company"
            value={form.company_name}
            onChange={(e) => setForm({ ...form, company_name: e.target.value })}
          />
          <Input
            label="Email"
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <Input
            label="Phone"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
          />
          <Input
            label="Callback time"
            type="datetime-local"
            value={form.scheduled_at}
            onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })}
          />
          <Input
            label="Timezone"
            value={form.callback_timezone}
            onChange={(e) => setForm({ ...form, callback_timezone: e.target.value })}
            placeholder="Europe/London"
          />
          <div style={{ gridColumn: '1 / -1' }}>
            <Input
              label="Interest summary"
              value={form.interest_summary}
              onChange={(e) => setForm({ ...form, interest_summary: e.target.value })}
            />
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <Input
              label="Sales intent"
              value={form.sales_intent}
              onChange={(e) => setForm({ ...form, sales_intent: e.target.value })}
            />
          </div>
          <label
            style={{
              gridColumn: '1 / -1',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              fontSize: '0.875rem',
              color: 'var(--ds-text-primary)',
              cursor: 'pointer',
            }}
          >
            <input
              type="checkbox"
              checked={form.callback_consent}
              onChange={(e) => setForm({ ...form, callback_consent: e.target.checked })}
              style={{ width: '18px', height: '18px', cursor: 'pointer' }}
            />
            <span>Consent recorded</span>
          </label>
        </div>
      </Panel>

      <RecordingsPanel lead={lead} taskId={taskId} callDone={task.call_done} />

      <OutcomeResults
        task={task}
        onSync={syncOutcome}
        syncing={syncingOutcome}
        onViewInsight={() => setShowInsights(true)}
      />

      <Panel title="Send offer">
        <p style={{ margin: '0 0 0.75rem', fontSize: '0.875rem', color: 'var(--ds-text-secondary)' }}>
          Offers are sent manually. Use the <strong>Marketing → Send offer</strong> page to send promo offers to this lead.
        </p>
        {task.offer_promo_code && (
          <div style={{ marginBottom: '0.75rem' }}>
            <Badge variant="success">Offer sent: {task.offer_promo_code}</Badge>
            {task.offer_sent_at && (
              <span style={{ marginLeft: '0.5rem', fontSize: '0.8rem', color: 'var(--ds-text-secondary)' }}>
                {displayWhen(task.offer_sent_at)}
              </span>
            )}
          </div>
        )}
        <Link to={`/marketing/leads/offers`} style={{ textDecoration: 'none' }}>
          <Button variant="soft">Go to Send offer page</Button>
        </Link>
      </Panel>

      <div ref={promptRef}>
      <Panel
        title="Sales call prompt"
        badge={<Badge>v{task.sales_prompt_version || 1} · DeepSeek</Badge>}
      >
        <p style={{ marginTop: 0, marginBottom: '1rem', fontSize: '0.875rem', color: 'var(--ds-text-secondary)' }}>
          Saved prompt includes master script + lead section + sales KB. Before each call the full text is pushed to Telnyx{' '}
          <strong>instructions</strong>; the opening line goes to Telnyx <strong>greeting</strong> (separate field).
        </p>
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
          <Button variant="primary" onClick={generatePrompt} disabled={generatingPrompt}>
            <Sparkles className="h-4 w-4" />
            {generatingPrompt ? 'Generating…' : 'Generate prompt with AI'}
          </Button>
          <Button
            variant="soft"
            onClick={() => setShowPrompt((v) => !v)}
            disabled={!task.sales_prompt}
          >
            {showPrompt ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            {showPrompt ? 'Hide' : 'View'} saved prompt
          </Button>
        </div>

        {showPrompt && task.sales_prompt ? (
          <pre
            style={{
              padding: '1rem',
              background: 'var(--ds-surface-muted)',
              borderRadius: '8px',
              fontSize: '0.8rem',
              whiteSpace: 'pre-wrap',
              border: '1px solid var(--ds-border)',
              color: 'var(--ds-text-primary)',
              marginBottom: '1rem',
            }}
          >
            {task.sales_prompt}
          </pre>
        ) : (
          !task.sales_prompt && (
            <p style={{ marginBottom: '1rem', fontSize: '0.875rem', color: 'var(--ds-text-secondary)' }}>
              No prompt yet — generate with AI before calling.
            </p>
          )
        )}

        <TelnyxPromptPreview
          previewUrl={`/admin/frontpage/lead-sales/tasks/${taskId}/telnyx-preview`}
          resyncUrl={`/admin/frontpage/lead-sales/tasks/${taskId}/resync-telnyx`}
          onResyncDone={() => setMsg('Full prompt + greeting pushed to Telnyx for this lead.')}
        />
      </Panel>
      </div>

      {showInsights && (
        <TelnyxInsightsModal
          taskId={taskId}
          title={task.contact_name || task.company_name || 'Sales call result'}
          onClose={() => setShowInsights(false)}
        />
      )}
    </>
  )
}
