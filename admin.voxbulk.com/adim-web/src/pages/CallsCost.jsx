import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { leadSalesListUrl } from '../components/LeadSalesPipelineStrip'
import TelnyxInsightsModal from '../components/TelnyxInsightsModal'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Pill } from '@/components/ui/Badge'
import { KpiCard } from '@/components/ui/KpiCard'
import { Label } from '@/components/ui/Label'
import { TablePagination } from '@/components/ui/Table'

const DATE_RANGES = [
  ['today', 'Today'],
  ['yesterday', 'Yesterday'],
  ['last_7_days', 'Last 7 days'],
  ['last_30_days', 'Last 30 days'],
  ['this_month', 'This month'],
  ['last_month', 'Last month'],
]

const selectClass =
  'flex h-8 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring'

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

function transportTone(transport) {
  return transport === 'web' ? 'info' : 'neutral'
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
    <div className="modalOverlay" role="presentation" onClick={onClose}>
      <div className="callCostModal ds-scope" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div>
            <h3 className="text-[15px] font-semibold text-foreground">Call cost details</h3>
            <p className="text-[11px] text-muted-foreground">{call.agent_name || 'Telnyx voice call'}</p>
          </div>
          <Button type="button" variant="outline" size="sm" className="h-8" onClick={onClose}>
            Close
          </Button>
        </div>

        {state.loading ? (
          <div className="p-4 text-sm text-muted-foreground">Loading Telnyx breakdown…</div>
        ) : null}
        {state.error ? (
          <div className="m-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {state.error}
          </div>
        ) : null}

        {!state.loading && !state.error && state.data ? (
          <div className="callCostModalBody space-y-4 p-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <div>
                <span className="text-[11px] text-muted-foreground">When</span>
                <strong className="block text-[13px]">{formatWhen(call.created_at)}</strong>
              </div>
              <div>
                <span className="text-[11px] text-muted-foreground">Destination</span>
                <strong className="block text-[13px]">{call.destination || '—'}</strong>
              </div>
              <div>
                <span className="text-[11px] text-muted-foreground">Duration</span>
                <strong className="block text-[13px]">{call.duration_label || '0:00'}</strong>
              </div>
              <div>
                <span className="text-[11px] text-muted-foreground">Transport</span>
                <strong className="block text-[13px]">
                  <Pill tone={transportTone(call.transport)}>{call.transport_label}</Pill>
                </strong>
              </div>
              <div>
                <span className="text-[11px] text-muted-foreground">Total cost</span>
                <strong className="block text-[13px]">{money(call.total_cost, call.currency)}</strong>
              </div>
              <div>
                <span className="text-[11px] text-muted-foreground">Source</span>
                <strong className="block text-[13px]">{call.source_label || 'Telnyx'}</strong>
              </div>
            </div>

            {call.source_id ? (
              <div className="text-[12px]">
                {call.source_type === 'intake' ? (
                  <Link to="/marketing/leads/inbound" className="font-medium underline-offset-2 hover:underline">
                    Open intake leads
                  </Link>
                ) : null}
                {call.source_type === 'sales' ? (
                  <Link
                    to={leadSalesListUrl(call.source_id)}
                    className="font-medium underline-offset-2 hover:underline"
                  >
                    Open sales task
                  </Link>
                ) : null}
              </div>
            ) : null}

            <div>
              <h4 className="mb-2 text-[13px] font-semibold">Cost breakdown</h4>
              <table className="table callCostTableCompact">
                <thead>
                  <tr>
                    <th>Component</th>
                    <th>Duration</th>
                    <th>Rate</th>
                    <th>Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {components.length ? (
                    components.map((row) => (
                      <tr key={`${row.record_type}-${row.label}`}>
                        <td>{row.label}</td>
                        <td>
                          {row.duration_sec
                            ? `${Math.floor(row.duration_sec / 60)}:${String(row.duration_sec % 60).padStart(2, '0')}`
                            : '—'}
                        </td>
                        <td>{row.rate != null ? String(row.rate) : '—'}</td>
                        <td>{money(row.cost, row.currency || call.currency)}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={4}>No component rows returned.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <h4 className="mb-2 text-[13px] font-semibold">AI models</h4>
                <div className="space-y-1 text-[12.5px]">
                  <div className="flex justify-between gap-2">
                    <span className="text-muted-foreground">LLM</span>
                    <strong>{call.llm_model || metadata.llm_model || '—'}</strong>
                  </div>
                  <div className="flex justify-between gap-2">
                    <span className="text-muted-foreground">STT</span>
                    <strong>
                      {components.find((c) => c.record_type === 'ai-voice-assistant')?.details?.stt_model || '—'}
                    </strong>
                  </div>
                  <div className="flex justify-between gap-2">
                    <span className="text-muted-foreground">TTS</span>
                    <strong>
                      {components.find((c) => c.record_type === 'ai-voice-assistant')?.details?.tts_provider || '—'}
                    </strong>
                  </div>
                </div>
              </div>
              <div>
                <h4 className="mb-2 text-[13px] font-semibold">Identifiers</h4>
                <div className="space-y-1 text-[12.5px]">
                  <div className="flex justify-between gap-2">
                    <span className="text-muted-foreground">Session</span>
                    <strong className="font-mono text-[11px]">{call.session_id || '—'}</strong>
                  </div>
                  <div className="flex justify-between gap-2">
                    <span className="text-muted-foreground">Conversation</span>
                    <strong className="font-mono text-[11px]">{call.conversation_id || '—'}</strong>
                  </div>
                  <div className="flex justify-between gap-2">
                    <span className="text-muted-foreground">Call control</span>
                    <strong className="font-mono text-[11px]">
                      {call.call_control_id || metadata.call_control_id || '—'}
                    </strong>
                  </div>
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

  const subtitle = useMemo(() => {
    const label = DATE_RANGES.find(([value]) => value === dateRange)?.[1] || dateRange
    return `Live Telnyx detail records · ${label}`
  }, [dateRange])

  const totalCount = Number(pagination.total_results || 0)

  return (
    <div className="ds-scope space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0">
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">Calls cost</h1>
          <p className="text-[11px] leading-tight text-muted-foreground">{subtitle}</p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Pill tone="success">Live</Pill>
          <Button type="button" variant="outline" size="sm" className="h-8" onClick={load} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard label="Total calls" value={Number(summary.total_calls || 0)} tone="primary" index={0} />
        <KpiCard label="Total spend" value={money(summary.total_cost, currency)} tone="success" index={1} />
        <KpiCard label="WebRTC calls" value={Number(summary.web_calls || 0)} tone="info" index={2} />
        <KpiCard label="Phone calls" value={Number(summary.phone_calls || 0)} tone="warning" index={3} />
      </div>

      <Panel
        title="Telnyx AI calls"
        action={<Pill tone="info">Avg {money(summary.avg_cost, currency)} / call</Pill>}
        bodyClassName="space-y-3"
      >
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label className="text-[11px] text-muted-foreground">Period</Label>
            <select
              className={selectClass}
              value={dateRange}
              onChange={(e) => {
                setPage(1)
                setDateRange(e.target.value)
              }}
            >
              {DATE_RANGES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label className="text-[11px] text-muted-foreground">Transport</Label>
            <select
              className={selectClass}
              value={transport}
              onChange={(e) => {
                setPage(1)
                setTransport(e.target.value)
              }}
            >
              <option value="">All</option>
              <option value="web">WebRTC</option>
              <option value="phone">Phone</option>
            </select>
          </div>
          <div className="min-w-[200px] flex-1 space-y-1">
            <Label className="text-[11px] text-muted-foreground">Search</Label>
            <Input
              type="search"
              className="h-8"
              placeholder="Agent, destination, cost…"
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
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8"
            onClick={() => {
              setPage(1)
              load()
            }}
            disabled={loading}
          >
            Apply
          </Button>
        </div>

        <table className="table callCostTableCompact">
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
              <tr>
                <td colSpan={8}>Loading Telnyx call costs…</td>
              </tr>
            ) : items.length ? (
              items.map((row) => (
                <tr key={row.id || row.session_id}>
                  <td>{formatWhen(row.created_at)}</td>
                  <td>
                    <div className="flex flex-col leading-tight">
                      <strong className="font-medium">{row.agent_name}</strong>
                      {row.contact_name ? (
                        <span className="text-[11px] text-muted-foreground">{row.contact_name}</span>
                      ) : null}
                    </div>
                  </td>
                  <td className="font-mono text-[11px]">{row.destination}</td>
                  <td>{row.duration_label}</td>
                  <td>
                    <Pill tone={transportTone(row.transport)}>{row.transport_label}</Pill>
                  </td>
                  <td>
                    <div className="flex flex-col leading-tight">
                      <strong className="font-medium">{money(row.total_cost, row.currency)}</strong>
                      <span className="text-[11px] text-muted-foreground">
                        AI {money(row.ai_cost, row.currency)}
                      </span>
                    </div>
                  </td>
                  <td>{row.source_label || '—'}</td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7"
                        disabled={!row.conversation_id && !row.session_id}
                        onClick={() =>
                          setInsightsTarget({
                            conversationId: row.conversation_id,
                            sessionId: row.session_id,
                            title: row.agent_name || row.destination || 'Call result',
                          })
                        }
                      >
                        Result
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7"
                        onClick={() => setDetailSessionId(row.session_id)}
                      >
                        Details
                      </Button>
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={8}>No Telnyx AI calls found for this period.</td>
              </tr>
            )}
          </tbody>
        </table>

        <TablePagination
          page={page}
          pageCount={totalPages}
          total={totalCount}
          onPrev={() => setPage((p) => Math.max(1, p - 1))}
          onNext={() => setPage((p) => p + 1)}
        />
      </Panel>

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
    </div>
  )
}
