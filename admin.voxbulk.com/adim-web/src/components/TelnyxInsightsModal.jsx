import React, { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'

function formatWhen(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString()
}

function humanizeKey(key) {
  return String(key || '')
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatValue(value) {
  if (value == null || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') return String(value)
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    return value.map((item) => (typeof item === 'object' ? JSON.stringify(item) : String(item))).join(' · ')
  }
  return JSON.stringify(value, null, 2)
}

function statusPillClass(status) {
  const clean = String(status || '').toLowerCase()
  if (clean === 'completed') return 'telnyxInsightStatus telnyxInsightStatusDone'
  if (clean === 'pending' || clean === 'processing' || clean === 'in_progress') {
    return 'telnyxInsightStatus telnyxInsightStatusPending'
  }
  if (clean === 'failed' || clean === 'error') return 'telnyxInsightStatus telnyxInsightStatusFailed'
  return 'telnyxInsightStatus telnyxInsightStatusNeutral'
}

function InsightResultBody({ item }) {
  const parsed = item?.result_json
  const entries = useMemo(() => {
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return Object.entries(parsed)
    }
    return null
  }, [parsed])

  if (entries?.length) {
    return (
      <dl className='telnyxInsightFields'>
        {entries.map(([key, value]) => (
          <div key={key} className='telnyxInsightField'>
            <dt>{humanizeKey(key)}</dt>
            <dd>{formatValue(value)}</dd>
          </div>
        ))}
      </dl>
    )
  }

  if (Array.isArray(parsed) && parsed.length) {
    return (
      <ul className='telnyxInsightList'>
        {parsed.map((row, index) => (
          <li key={index}>{typeof row === 'object' ? JSON.stringify(row) : String(row)}</li>
        ))}
      </ul>
    )
  }

  const text = String(item?.result || '').trim()
  if (!text) return <p className='muted'>No insight output yet.</p>
  return <pre className='frontpagePromptPreview telnyxInsightRaw'>{text}</pre>
}

function formatLoadError(error) {
  const message = String(error?.message || error || 'Could not load Telnyx insights')
  if (error?.status === 404 && /not found/i.test(message)) {
    return `${message}. The API on this server may need updating — pull latest code and restart the FastAPI service.`
  }
  return message
}

export default function TelnyxInsightsModal({ taskId, sessionId, conversationId, title, onClose }) {
  const [state, setState] = useState({ loading: true, error: '', data: null })

  const fetchPath = useMemo(() => {
    if (taskId) {
      return `/admin/frontpage/lead-sales/tasks/${encodeURIComponent(taskId)}/telnyx-insights`
    }
    if (conversationId) {
      return `/admin/billing/conversations/${encodeURIComponent(conversationId)}/insights`
    }
    if (sessionId) {
      return `/admin/billing/calls-cost/${encodeURIComponent(sessionId)}/insights`
    }
    return ''
  }, [conversationId, sessionId, taskId])

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (!fetchPath) {
        setState({ loading: false, error: 'Missing call identifier', data: null })
        return
      }
      setState({ loading: true, error: '', data: null })
      try {
        const data = await apiFetch(fetchPath)
        if (!cancelled) setState({ loading: false, error: '', data })
      } catch (e) {
        if (!cancelled) {
          setState({ loading: false, error: formatLoadError(e), data: null })
        }
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [fetchPath])

  const items = state.data?.items || []
  const overallStatus = state.data?.status || 'unknown'
  const helperMessage = state.data?.message || ''

  return (
    <div className='modalOverlay' role='presentation' onClick={onClose}>
      <div className='callCostModal telnyxInsightsModal' role='dialog' aria-modal='true' onClick={(e) => e.stopPropagation()}>
        <div className='callCostModalHead'>
          <div>
            <h3>Assistant call result</h3>
            <p className='muted'>{title || 'Telnyx conversation insight output'}</p>
          </div>
          <button type='button' className='btn soft' onClick={onClose}>
            Close
          </button>
        </div>

        {state.loading ? <div className='callCostModalBody note'>Loading Telnyx assistant insights…</div> : null}
        {state.error ? <div className='callCostModalBody note'>{state.error}</div> : null}

        {!state.loading && !state.error && state.data ? (
          <div className='callCostModalBody'>
            <div className='telnyxInsightMeta'>
              <div>
                <span className='muted'>Status</span>
                <strong><span className={statusPillClass(overallStatus)}>{overallStatus}</span></strong>
              </div>
              {state.data.conversation_id ? (
                <div>
                  <span className='muted'>Conversation</span>
                  <strong className='mono'>{state.data.conversation_id}</strong>
                </div>
              ) : null}
              {state.data.session_id ? (
                <div>
                  <span className='muted'>Session</span>
                  <strong className='mono'>{state.data.session_id}</strong>
                </div>
              ) : null}
            </div>

            {helperMessage ? (
              <div className='note' style={{ marginTop: 16 }}>
                <p style={{ margin: 0 }}>{helperMessage}</p>
              </div>
            ) : null}

            {!items.length && !helperMessage ? (
              <div className='note' style={{ marginTop: 16 }}>
                {overallStatus === 'pending' || overallStatus === 'processing' || overallStatus === 'in_progress' ? (
                  <p style={{ margin: 0 }}>Telnyx is still generating assistant insights for this call. Try again in a minute.</p>
                ) : (
                  <p style={{ margin: 0 }}>No assistant insight output was returned for this conversation.</p>
                )}
              </div>
            ) : null}

            {items.map((item, index) => (
              <section key={`${item.insight_id || 'insight'}-${index}`} className='telnyxInsightBlock'>
                <div className='telnyxInsightBlockHead'>
                  <h4>{item.insight_name || (item.insight_id ? `Insight ${item.insight_id.slice(0, 8)}…` : `Insight ${index + 1}`)}</h4>
                  <span className={statusPillClass(item.batch_status)}>{item.batch_status || 'unknown'}</span>
                </div>
                {item.created_at ? <p className='muted telnyxInsightWhen'>{formatWhen(item.created_at)}</p> : null}
                <InsightResultBody item={item} />
              </section>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}
