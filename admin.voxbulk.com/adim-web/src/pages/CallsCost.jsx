import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import TelnyxInsightsModal from '../components/TelnyxInsightsModal'

const DATE_RANGES = [
  ['today', 'Today'],
  ['yesterday', 'Yesterday'],
  ['last_7_days', 'Last 7 days'],
  ['last_30_days', 'Last 30 days'],
  ['this_month', 'This month'],
  ['last_month', 'Last month'],
]

function money(amount, currency = 'USD') {
  const value = Number(amount || 0)
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: currency || 'USD' }).format(value)
  } catch {
    return `$${value.toFixed(4)}`
  }
}

function formatWhen(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString()
}

function transportPill(transport) {
  return transport === 'web' ? 'callCostPill callCostPillWeb' : 'callCostPill callCostPillPhone'
}

function CallCostDetailModal({ sessionId, onClose }) {
  const [state, setState] = useState({ loading: true, error: '', data: null })

  useEffect(() => {
    let cancelled = false
    async function load() {
      setState({ loading: true, error: '', data: null })
      try {
        const data = await apiFetch(`/admin/billing/calls-cost/${encodeURIComponent(sessionId)}`)
        if (!cancelled) setState({ loading: false, error: '', data })
      } catch (e) {
        if (!cancelled) setState({ loading: false, error: e?.message || 'Could not load call details', data: null })
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [sessionId])

  const call = state.data?.call || {}
  const components = state.data?.components || []
  const conversation = state.data?.conversation || {}
  const metadata = conversation.metadata || {}

  return (
    <div className='modalOverlay' role='presentation' onClick={onClose}>
      <div className='callCostModal' role='dialog' aria-modal='true' onClick={(e) => e.stopPropagation()}>
        <div className='callCostModalHead'>
          <div>
            <h3>Call cost details</h3>
            <p className='muted'>{call.agent_name || 'Telnyx voice call'}</p>
          </div>
          <button type='button' className='btn soft' onClick={onClose}>
            Close
          </button>
        </div>

        {state.loading ? <div className='callCostModalBody note'>Loading Telnyx breakdown…</div> : null}
        {state.error ? <div className='callCostModalBody note'>{state.error}</div> : null}

        {!state.loading && !state.error && state.data ? (
          <div className='callCostModalBody'>
            <div className='callCostDetailGrid'>
              <div><span className='muted'>When</span><strong>{formatWhen(call.created_at)}</strong></div>
              <div><span className='muted'>Destination</span><strong>{call.destination || '—'}</strong></div>
              <div><span className='muted'>Duration</span><strong>{call.duration_label || '0:00'}</strong></div>
              <div><span className='muted'>Transport</span><strong><span className={transportPill(call.transport)}>{call.transport_label}</span></strong></div>
              <div><span className='muted'>Total cost</span><strong className='callCostTotal'>{money(call.total_cost, call.currency)}</strong></div>
              <div><span className='muted'>Source</span><strong>{call.source_label || 'Telnyx'}</strong></div>
            </div>

            {call.source_id ? (
              <div className='callCostSourceLink'>
                {call.source_type === 'intake' ? (
                  <Link to='/marketing/lead-sources'>Open intake leads</Link>
                ) : null}
                {call.source_type === 'sales' ? (
                  <Link to={`/marketing/lead-sales/${call.source_id}`}>Open sales task</Link>
                ) : null}
              </div>
            ) : null}

            <div className='callCostSection'>
              <h4>Cost breakdown</h4>
              <table className='table callCostTableCompact'>
                <thead>
                  <tr>
                    <th>Component</th>
                    <th>Duration</th>
                    <th>Rate</th>
                    <th>Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {components.length ? components.map((row) => (
                    <tr key={`${row.record_type}-${row.label}`}>
                      <td>{row.label}</td>
                      <td>{row.duration_sec ? `${Math.floor(row.duration_sec / 60)}:${String(row.duration_sec % 60).padStart(2, '0')}` : '—'}</td>
                      <td>{row.rate != null ? String(row.rate) : '—'}</td>
                      <td>{money(row.cost, row.currency || call.currency)}</td>
                    </tr>
                  )) : (
                    <tr><td colSpan={4}>No component rows returned.</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className='callCostSection callCostSectionSplit'>
              <div>
                <h4>AI models</h4>
                <div className='callCostMetaList'>
                  <div><span>LLM</span><strong>{call.llm_model || metadata.llm_model || '—'}</strong></div>
                  <div><span>STT</span><strong>{components.find((c) => c.record_type === 'ai-voice-assistant')?.details?.stt_model || '—'}</strong></div>
                  <div><span>TTS</span><strong>{components.find((c) => c.record_type === 'ai-voice-assistant')?.details?.tts_provider || '—'}</strong></div>
                </div>
              </div>
              <div>
                <h4>Identifiers</h4>
                <div className='callCostMetaList'>
                  <div><span>Session</span><strong className='mono'>{call.session_id || '—'}</strong></div>
                  <div><span>Conversation</span><strong className='mono'>{call.conversation_id || '—'}</strong></div>
                  <div><span>Call control</span><strong className='mono'>{call.call_control_id || metadata.call_control_id || '—'}</strong></div>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

export default function CallsCost() {
  const [dateRange, setDateRange] = useState('last_30_days')
  const [transport, setTransport] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [payload, setPayload] = useState(null)
  const [detailSessionId, setDetailSessionId] = useState('')
  const [insightsTarget, setInsightsTarget] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({
        date_range: dateRange,
        page: String(page),
        page_size: '25',
      })
      if (transport) params.set('transport', transport)
      if (search.trim()) params.set('search', search.trim())
      const data = await apiFetch(`/admin/billing/calls-cost?${params.toString()}`)
      setPayload(data)
    } catch (e) {
      setPayload(null)
      setError(e?.message || 'Could not load Telnyx call costs')
    } finally {
      setLoading(false)
    }
  }, [dateRange, page, search, transport])

  useEffect(() => {
    load()
  }, [load])

  const summary = payload?.summary || {}
  const items = payload?.items || []
  const pagination = payload?.pagination || {}
  const currency = summary.currency || 'USD'

  const totalPages = Math.max(1, Number(pagination.total_pages || 1))
  const canPrev = page > 1
  const canNext = page < totalPages

  const subtitle = useMemo(() => {
    const label = DATE_RANGES.find(([value]) => value === dateRange)?.[1] || dateRange
    return `Live Telnyx detail records · ${label}`
  }, [dateRange])

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Calls cost</h1>
          <p>{subtitle}. Agent, destination, duration, WebRTC vs phone, and per-component Telnyx billing.</p>
        </div>
        <div className='actions'>
          <button type='button' className='btn soft' onClick={load} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {error ? <div className='note' style={{ marginBottom: 16 }}>{error}</div> : null}

      <div className='grid-4 callCostStats' style={{ marginBottom: 16 }}>
        <div className='card stat' style={{ '--accent': '#0f766e' }}>
          <div className='muted'>Total calls</div>
          <div className='statValue'>{Number(summary.total_calls || 0).toLocaleString()}</div>
          <span className='pill p-green'>Telnyx AI calls</span>
        </div>
        <div className='card stat' style={{ '--accent': '#2563eb' }}>
          <div className='muted'>Total spend</div>
          <div className='statValue'>{money(summary.total_cost, currency)}</div>
          <span className='pill p-cyan'>All components</span>
        </div>
        <div className='card stat' style={{ '--accent': '#7c3aed' }}>
          <div className='muted'>WebRTC calls</div>
          <div className='statValue'>{Number(summary.web_calls || 0).toLocaleString()}</div>
          <span className='pill callCostPillWeb'>Browser</span>
        </div>
        <div className='card stat' style={{ '--accent': '#d97706' }}>
          <div className='muted'>Phone calls</div>
          <div className='statValue'>{Number(summary.phone_calls || 0).toLocaleString()}</div>
          <span className='pill callCostPillPhone'>PSTN</span>
        </div>
      </div>

      <div className='card callCostCard'>
        <div className='cardHead callCostFilters'>
          <div className='callCostFilterGroup'>
            <label>
              <span className='muted'>Period</span>
              <select value={dateRange} onChange={(e) => { setPage(1); setDateRange(e.target.value) }}>
                {DATE_RANGES.map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
            <label>
              <span className='muted'>Transport</span>
              <select value={transport} onChange={(e) => { setPage(1); setTransport(e.target.value) }}>
                <option value=''>All</option>
                <option value='web'>WebRTC</option>
                <option value='phone'>Phone</option>
              </select>
            </label>
            <label className='callCostSearchField'>
              <span className='muted'>Search</span>
              <input
                type='search'
                placeholder='Agent, destination, contact…'
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    setPage(1)
                    load()
                  }
                }}
              />
            </label>
            <button type='button' className='btn soft' onClick={() => { setPage(1); load() }} disabled={loading}>
              Apply
            </button>
          </div>
          <span className='pill p-cyan'>
            Avg {money(summary.avg_cost, currency)} / call
          </span>
        </div>

        <div className='cardBody callCostTableWrap'>
          <table className='table callCostTableCompact'>
            <thead>
              <tr>
                <th>When</th>
                <th>Agent</th>
                <th>Destination</th>
                <th>Duration</th>
                <th>Transport</th>
                <th>Cost</th>
                <th>Source</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8}>Loading Telnyx call costs…</td></tr>
              ) : items.length ? items.map((row) => (
                <tr key={row.id || row.session_id}>
                  <td>{formatWhen(row.created_at)}</td>
                  <td>
                    <div className='callCostAgentCell'>
                      <strong>{row.agent_name}</strong>
                      {row.contact_name ? <span className='muted'>{row.contact_name}</span> : null}
                    </div>
                  </td>
                  <td className='mono'>{row.destination}</td>
                  <td>{row.duration_label}</td>
                  <td><span className={transportPill(row.transport)}>{row.transport_label}</span></td>
                  <td>
                    <div className='callCostMoneyCell'>
                      <strong>{money(row.total_cost, row.currency)}</strong>
                      <span className='muted'>AI {money(row.ai_cost, row.currency)}</span>
                    </div>
                  </td>
                  <td>{row.source_label || '—'}</td>
                  <td className='callCostActions'>
                    <button
                      type='button'
                      className='btn soft'
                      disabled={!row.conversation_id && !row.session_id}
                      onClick={() => setInsightsTarget({
                        conversationId: row.conversation_id,
                        sessionId: row.session_id,
                        title: row.agent_name || row.destination || 'Call result',
                      })}
                    >
                      Result
                    </button>
                    <button type='button' className='btn soft' onClick={() => setDetailSessionId(row.session_id)}>
                      Details
                    </button>
                  </td>
                </tr>
              )) : (
                <tr><td colSpan={8}>No Telnyx AI calls found for this period.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className='callCostPager'>
          <button type='button' className='btn soft' disabled={!canPrev || loading} onClick={() => setPage((p) => Math.max(1, p - 1))}>
            Previous
          </button>
          <span className='muted'>
            Page {page} of {totalPages} · {Number(pagination.total_results || 0).toLocaleString()} calls
          </span>
          <button type='button' className='btn soft' disabled={!canNext || loading} onClick={() => setPage((p) => p + 1)}>
            Next
          </button>
        </div>
      </div>

      {detailSessionId ? (
        <CallCostDetailModal sessionId={detailSessionId} onClose={() => setDetailSessionId('')} />
      ) : null}

      {insightsTarget ? (
        <TelnyxInsightsModal
          sessionId={insightsTarget.sessionId}
          conversationId={insightsTarget.conversationId}
          title={insightsTarget.title}
          onClose={() => setInsightsTarget(null)}
        />
      ) : null}
    </>
  )
}
