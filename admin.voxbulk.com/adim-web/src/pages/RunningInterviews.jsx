import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  Briefcase,
  ChevronRight,
  Download,
  Mail,
  MessageCircle,
  Pause,
  Phone,
  Play,
  RefreshCw,
  Search,
  Square,
  Users,
  X,
} from 'lucide-react'
import { apiFetch, apiFetchBlob } from '../lib/api'

const EMPTY_CANDIDATE = { name: '', phone: '', email: '', status: '' }

const LIST_TABS = [
  { id: 'active', label: 'Active' },
  { id: 'attention', label: 'Needs attention' },
  { id: 'failures', label: 'Failures' },
  { id: 'all', label: 'All orders' },
  { id: 'finished', label: 'Finished' },
]

function fmtWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

function fmtShort(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

function orderSortTs(o) {
  const raw = o.last_activity_at || o.updated_at || o.started_at || o.created_at
  if (!raw) return 0
  const t = new Date(raw).getTime()
  return Number.isNaN(t) ? 0 : t
}

function statusPill(status, paymentStatus) {
  if (status === 'running') return 'leadPill leadPillAdvance'
  if (status === 'paused') return 'leadPill leadPillHold'
  if (paymentStatus === 'rejected') return 'leadPill leadPillDecline'
  if (status === 'completed') return 'leadPill leadPillNeutral'
  return 'leadPill'
}

function channelPill(state) {
  const s = String(state || '').toLowerCase()
  if (s === 'complete' || s === 'healthy') return 'leadPill leadPillAdvance'
  if (s === 'failed') return 'leadPill leadPillDecline'
  if (s === 'partial' || s === 'active' || s === 'pending') return 'leadPill leadPillHold'
  return 'leadPill leadPillNeutral'
}

function healthPill(health) {
  const h = String(health || '').toLowerCase()
  if (h === 'healthy') return 'leadPill leadPillAdvance'
  if (h === 'failed') return 'leadPill leadPillDecline'
  if (h === 'stuck') return 'leadPill leadPillDecline'
  if (h === 'partial') return 'leadPill leadPillHold'
  return 'leadPill leadPillNeutral'
}

function healthLabel(health) {
  const map = { healthy: 'Healthy', partial: 'Partial', failed: 'Failed', stuck: 'Stuck' }
  return map[String(health || '').toLowerCase()] || health || '—'
}

function activityStatusLabel(code) {
  const map = {
    pending: 'Pending',
    booking_email_sent: 'Booking email sent',
    awaiting_booking: 'Awaiting booking',
    booked_waiting: 'Booked (upcoming)',
    booked: 'Booked',
    booking_cancelled: 'Booking cancelled',
    calling: 'Calling',
    interview_completed: 'Interview done',
    report_ready: 'Report ready',
    scheduling_sent: 'Scheduling sent',
    call_failed: 'Call failed',
  }
  return map[String(code || '').toLowerCase()] || code || 'Pending'
}

function activityPill(code) {
  const s = String(code || 'pending').toLowerCase()
  if (s === 'report_ready' || s === 'interview_completed') return 'leadPill leadPillAdvance'
  if (s === 'calling' || s === 'awaiting_booking' || s === 'booking_email_sent') return 'leadPill leadPillHold'
  if (s === 'call_failed' || s === 'booking_cancelled') return 'leadPill leadPillDecline'
  return 'leadPill leadPillNeutral'
}

function candidatePill(status) {
  const s = String(status || 'pending').toLowerCase()
  if (s === 'calling') return 'leadPill leadPillHold'
  if (s === 'completed') return 'leadPill leadPillAdvance'
  if (['failed', 'no_answer', 'busy', 'cancelled'].includes(s)) return 'leadPill leadPillDecline'
  return 'leadPill leadPillNeutral'
}

function cvQualityLabel(q) {
  const v = String(q || 'missing')
  if (v === 'good') return 'Good'
  if (v === 'low_quality') return 'Low quality'
  if (v === 'corrupt') return 'Error'
  return 'No CV'
}

function copyText(text) {
  if (!text) return
  navigator.clipboard?.writeText(String(text)).catch(() => {})
}

function StatCard({ label, value, hint, active, onClick }) {
  return (
    <button
      type="button"
      className={`card stat runningSurveyStat opsInterviewKpi${active ? ' isActive' : ''}`}
      onClick={onClick}
    >
      <div className="statValue">{value}</div>
      <div className="muted">{label}</div>
      {hint ? <div className="muted runningSurveyStatHint">{hint}</div> : null}
    </button>
  )
}

function DeliveryChip({ label, state }) {
  return (
    <span className={channelPill(state)} title={label}>
      {label}
    </span>
  )
}

export default function RunningInterviews() {
  const [orders, setOrders] = useState([])
  const [overview, setOverview] = useState(null)
  const [selected, setSelected] = useState(null)
  const [selectedSummary, setSelectedSummary] = useState(null)
  const [audit, setAudit] = useState([])
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [panelTab, setPanelTab] = useState('overview')
  const [listTab, setListTab] = useState('active')
  const [kpiFilter, setKpiFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState('activity_desc')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [paymentFilter, setPaymentFilter] = useState('')
  const [emailFilter, setEmailFilter] = useState('')
  const [callFilter, setCallFilter] = useState('')
  const [waFilter, setWaFilter] = useState('')
  const [launchFilter, setLaunchFilter] = useState('')
  const [orgFilter, setOrgFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyKey, setBusyKey] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState(EMPTY_CANDIDATE)
  const [activityRow, setActivityRow] = useState(null)
  const [activityData, setActivityData] = useState(null)
  const [activityLoading, setActivityLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback(async () => {
    setError('')
    const payload = await apiFetch('/admin/platform-services/interviews/operations')
    setOrders(Array.isArray(payload?.orders) ? payload.orders : [])
    setOverview(payload?.overview || null)
  }, [])

  const loadDetail = useCallback(async (orderId) => {
    if (!orderId) return
    const [row, auditRes] = await Promise.all([
      apiFetch(`/admin/platform-services/orders/${encodeURIComponent(orderId)}`),
      apiFetch(`/admin/platform-services/orders/${encodeURIComponent(orderId)}/audit`).catch(() => ({ timeline: [] })),
    ])
    setSelected(row)
    setAudit(auditRes?.timeline || [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load interview operations')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const orgOptions = useMemo(() => {
    const names = new Set()
    orders.forEach((o) => {
      if (o.org_name) names.add(o.org_name)
    })
    return Array.from(names).sort()
  }, [orders])

  const overviewCards = useMemo(
    () => [
      { key: 'active', label: 'Active interviews', value: overview?.active_interviews ?? '—', hint: `${overview?.running ?? 0} running · ${overview?.paused ?? 0} paused` },
      { key: 'waiting', label: 'Waiting to launch', value: overview?.waiting_to_launch ?? '—', hint: 'Approved but not live' },
      { key: 'progress', label: 'In progress', value: overview?.in_progress ?? '—', hint: 'Running or paused' },
      { key: 'attention', label: 'Needs attention', value: overview?.needs_attention ?? '—', hint: 'Delivery or data issues' },
      { key: 'completed_today', label: 'Completed today', value: overview?.completed_today ?? '—', hint: 'Finished today' },
      { key: 'failed', label: 'Failed deliveries', value: overview?.failed_deliveries ?? '—', hint: 'Email or launch failures' },
    ],
    [overview],
  )

  const filteredOrders = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    const fromTs = dateFrom ? new Date(`${dateFrom}T00:00:00`).getTime() : null
    const toTs = dateTo ? new Date(`${dateTo}T23:59:59`).getTime() : null

    const rows = orders.filter((o) => {
      if (listTab === 'active' && !o.is_live) return false
      if (listTab === 'attention' && !o.needs_attention) return false
      if (listTab === 'failures' && o.email_status !== 'failed' && o.launch_status !== 'launch_failed' && o.delivery_health !== 'failed') return false
      if (listTab === 'finished' && !o.is_finished) return false

      if (kpiFilter === 'active' && !o.is_live) return false
      if (kpiFilter === 'waiting' && !['waiting', 'launch_pending'].includes(o.launch_status)) return false
      if (kpiFilter === 'progress' && !['running', 'paused'].includes(o.status)) return false
      if (kpiFilter === 'attention' && !o.needs_attention) return false
      if (kpiFilter === 'completed_today') {
        const today = new Date().toDateString()
        const doneAt = o.completed_at || o.last_activity_at
        if (!doneAt || new Date(doneAt).toDateString() !== today) return false
      }
      if (kpiFilter === 'failed' && o.email_status !== 'failed' && o.launch_status !== 'launch_failed') return false

      const ts = orderSortTs(o)
      if (fromTs != null && ts < fromTs) return false
      if (toTs != null && ts > toTs) return false
      if (statusFilter && o.status !== statusFilter) return false
      if (paymentFilter && o.payment_status !== paymentFilter) return false
      if (emailFilter && o.email_status !== emailFilter) return false
      if (callFilter && o.call_status !== callFilter) return false
      if (waFilter && o.whatsapp_status !== waFilter) return false
      if (launchFilter === 'launched' && !['launched', 'invites_sent', 'completed'].includes(o.launch_status)) return false
      if (launchFilter === 'not_launched' && ['launched', 'invites_sent'].includes(o.launch_status)) return false
      if (orgFilter && o.org_name !== orgFilter) return false
      if (q && !(o.search_text || '').includes(q)) return false
      return true
    })

    rows.sort((a, b) => {
      if (sortBy === 'org_asc') return String(a.org_name || '').localeCompare(String(b.org_name || ''))
      if (sortBy === 'org_desc') return String(b.org_name || '').localeCompare(String(a.org_name || ''))
      if (sortBy === 'activity_asc') return orderSortTs(a) - orderSortTs(b)
      if (sortBy === 'attention') return Number(b.needs_attention) - Number(a.needs_attention) || orderSortTs(b) - orderSortTs(a)
      return orderSortTs(b) - orderSortTs(a)
    })
    return rows
  }, [orders, listTab, kpiFilter, searchQuery, sortBy, dateFrom, dateTo, statusFilter, paymentFilter, emailFilter, callFilter, waFilter, launchFilter, orgFilter])

  const tabCounts = useMemo(() => ({
    active: orders.filter((o) => o.is_live).length,
    attention: orders.filter((o) => o.needs_attention).length,
    failures: orders.filter((o) => o.email_status === 'failed' || o.launch_status === 'launch_failed' || o.delivery_health === 'failed').length,
    all: orders.length,
    finished: orders.filter((o) => o.is_finished).length,
  }), [orders])

  const drawerOrder = selected || selectedSummary
  const failureReasons = useMemo(() => {
    const reasons = [...(drawerOrder?.attention_reasons || [])]
    if (drawerOrder?.last_error) reasons.unshift(drawerOrder.last_error)
    const dispatch = drawerOrder?.last_invite_dispatch || selected?.config?.last_invite_dispatch
    if (dispatch?.errors?.length) reasons.push(...dispatch.errors.slice(0, 5))
    return [...new Set(reasons.filter(Boolean))]
  }, [drawerOrder, selected])

  const runAction = async (orderId, action, body, busy = orderId) => {
    setBusyKey(busy)
    setError('')
    try {
      await apiFetch(`/admin/platform-services/orders/${encodeURIComponent(orderId)}/${action}`, {
        method: 'POST',
        body: body ? JSON.stringify(body) : undefined,
      })
      await load()
      await loadDetail(orderId)
    } catch (e) {
      setError(e?.message || `${action} failed`)
    } finally {
      setBusyKey('')
    }
  }

  const openRow = async (order) => {
    setSelectedSummary(order)
    setPanelTab('overview')
    setEditingId(null)
    setActivityRow(null)
    setDrawerOpen(true)
    setDetailLoading(true)
    setError('')
    try {
      await loadDetail(order.id)
    } catch (e) {
      setError(e?.message || 'Could not load interview detail')
      setDrawerOpen(false)
    } finally {
      setDetailLoading(false)
    }
  }

  const closeDrawer = () => {
    setDrawerOpen(false)
    setSelected(null)
    setSelectedSummary(null)
    setEditingId(null)
    setActivityRow(null)
  }

  const exportCsv = () => {
    const headers = ['Order ID', 'Reference', 'Organisation', 'Role', 'Status', 'Launch', 'Email', 'WhatsApp', 'Call', 'Health', 'Payment', 'Recipients', 'Last activity', 'Needs attention']
    const lines = filteredOrders.map((o) => [
      o.id,
      o.reference_id || o.campaign_id || '',
      o.org_name || '',
      o.role_title || o.title || '',
      o.status_label || o.status || '',
      o.launch_label || '',
      o.email_label || '',
      o.whatsapp_label || '',
      o.call_label || '',
      healthLabel(o.delivery_health),
      o.payment_status || '',
      o.recipient_count || 0,
      o.last_activity_at || '',
      o.needs_attention ? 'yes' : 'no',
    ])
    const csv = [headers, ...lines]
      .map((row) => row.map((cell) => `"${String(cell ?? '').replace(/"/g, '""')}"`).join(','))
      .join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `interview-operations-${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  const startEditCandidate = (recipient) => {
    setEditingId(recipient.id)
    setEditForm({
      name: recipient.name || '',
      phone: recipient.phone || '',
      email: recipient.email || '',
      status: recipient.status || '',
    })
    setPanelTab('recipients')
  }

  const saveCandidate = async () => {
    if (!selected?.id || !editingId) return
    setBusyKey(`save-${editingId}`)
    setError('')
    try {
      await apiFetch(
        `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/recipients/${encodeURIComponent(editingId)}`,
        { method: 'PATCH', body: JSON.stringify(editForm) },
      )
      await loadDetail(selected.id)
      await load()
      setEditingId(null)
    } catch (e) {
      setError(e?.message || 'Could not save candidate')
    } finally {
      setBusyKey('')
    }
  }

  const downloadCv = async (recipient) => {
    if (!selected?.id || !recipient?.id) return
    setBusyKey(`cv-${recipient.id}`)
    setError('')
    try {
      const blob = await apiFetchBlob(
        `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/recipients/${encodeURIComponent(recipient.id)}/cv`,
      )
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = recipient.cv_filename || `cv-${recipient.id}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e?.message || 'Could not download CV')
    } finally {
      setBusyKey('')
    }
  }

  const openActivity = async (recipient) => {
    if (!selected?.id || !recipient?.id) return
    setActivityRow(recipient)
    setActivityData(null)
    setActivityLoading(true)
    setPanelTab('timeline')
    setError('')
    try {
      const data = await apiFetch(
        `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/recipients/${encodeURIComponent(recipient.id)}/activity`,
      )
      setActivityData(data)
    } catch (e) {
      setError(e?.message || 'Could not load activity')
      setActivityRow(null)
    } finally {
      setActivityLoading(false)
    }
  }

  const downloadReport = async (recipient, kind) => {
    if (!selected?.id || !recipient?.id) return
    setBusyKey(`report-${kind}-${recipient.id}`)
    setError('')
    try {
      const path =
        kind === 'pdf'
          ? `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/recipients/${encodeURIComponent(recipient.id)}/interview-candidate-report.pdf`
          : `/admin/platform-services/orders/${encodeURIComponent(selected.id)}/recipients/${encodeURIComponent(recipient.id)}/interview-candidate-report.html`
      const blob = await apiFetchBlob(path)
      const url = URL.createObjectURL(blob)
      if (kind === 'html') {
        window.open(url, '_blank', 'noopener,noreferrer')
      } else {
        const a = document.createElement('a')
        a.href = url
        a.download = `interview-report-${recipient.id}.pdf`
        document.body.appendChild(a)
        a.click()
        a.remove()
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (e) {
      setError(e?.message || 'Could not download report')
    } finally {
      setBusyKey('')
    }
  }

  const resendInvite = async (recipient, { emailOnly = false, waOnly = false } = {}) => {
    if (!selected?.id || !recipient?.id) return
    const locked =
      recipient.status === 'completed' ||
      ['report_ready', 'interview_completed', 'scheduling_sent'].includes(String(recipient.activity_status || ''))
    if (locked) {
      setError('This candidate has already completed screening — booking invites cannot be resent.')
      return
    }
    setBusyKey(`invite-${recipient.id}`)
    setError('')
    try {
      await apiFetch(`/admin/platform-services/orders/${encodeURIComponent(selected.id)}/send-invites`, {
        method: 'POST',
        body: JSON.stringify({
          recipient_ids: [recipient.id],
          force_resend: true,
          force_email: emailOnly || !waOnly,
        }),
      })
      await loadDetail(selected.id)
      await load()
    } catch (e) {
      setError(e?.message || 'Could not resend invite')
    } finally {
      setBusyKey('')
    }
  }

  const recipients = selected?.recipients || []
  const config = selected?.config || {}
  const report = selected?.report || {}
  const isRunning = selected?.status === 'running'
  const timeline = audit.length ? audit : selected?.audit_timeline || []

  return (
    <>
      <div className="pageTop opsInterviewPageTop">
        <div>
          <h1>Interview operations</h1>
          <p>Monitor launch status, delivery channels, call progress, and support actions across all interview campaigns.</p>
        </div>
        <div className="actions opsInterviewTopActions">
          <button type="button" className="btn soft" onClick={exportCsv} disabled={!filteredOrders.length}>
            <Download size={15} />
            Export CSV
          </button>
          <button type="button" className="btn soft" onClick={load} disabled={loading}>
            <RefreshCw size={15} />
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className="note runningSurveyError">{error}</div> : null}

      <div className="opsInterviewKpiGrid">
        {overviewCards.map((c) => (
          <StatCard
            key={c.key}
            label={c.label}
            value={c.value}
            hint={c.hint}
            active={kpiFilter === c.key}
            onClick={() => setKpiFilter((prev) => (prev === c.key ? '' : c.key))}
          />
        ))}
      </div>

      <div className="card opsInterviewFilterCard">
        <div className="cardBody opsInterviewFilterBody">
          <div className="opsInterviewFilterRow">
            <div className="opsInterviewSearchWrap">
              <Search size={15} />
              <input
                className="input opsInterviewSearch"
                type="search"
                placeholder="Search order ID, phone, email, company, reference…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <input className="input" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} title="From date" />
            <input className="input" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} title="To date" />
            <select className="input" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="activity_desc">Latest activity</option>
              <option value="activity_asc">Oldest activity</option>
              <option value="attention">Needs attention first</option>
              <option value="org_asc">Organisation A–Z</option>
              <option value="org_desc">Organisation Z–A</option>
            </select>
          </div>
          <div className="opsInterviewFilterRow">
            <select className="input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All statuses</option>
              <option value="running">Running</option>
              <option value="paused">Paused</option>
              <option value="scheduled">Scheduled</option>
              <option value="completed">Completed</option>
              <option value="draft">Draft</option>
              <option value="cancelled">Cancelled</option>
            </select>
            <select className="input" value={paymentFilter} onChange={(e) => setPaymentFilter(e.target.value)}>
              <option value="">All payments</option>
              <option value="approved">Approved</option>
              <option value="pending_approval">Pending approval</option>
              <option value="rejected">Rejected</option>
            </select>
            <select className="input" value={launchFilter} onChange={(e) => setLaunchFilter(e.target.value)}>
              <option value="">Launch: any</option>
              <option value="launched">Launched</option>
              <option value="not_launched">Not launched</option>
            </select>
            <select className="input" value={emailFilter} onChange={(e) => setEmailFilter(e.target.value)}>
              <option value="">Email: any</option>
              <option value="complete">Complete</option>
              <option value="partial">Partial</option>
              <option value="failed">Failed</option>
              <option value="pending">Pending</option>
            </select>
            <select className="input" value={waFilter} onChange={(e) => setWaFilter(e.target.value)}>
              <option value="">WhatsApp: any</option>
              <option value="complete">Complete</option>
              <option value="partial">Partial</option>
              <option value="pending">Pending</option>
            </select>
            <select className="input" value={callFilter} onChange={(e) => setCallFilter(e.target.value)}>
              <option value="">Call: any</option>
              <option value="complete">Complete</option>
              <option value="active">Active</option>
              <option value="failed">Failed</option>
              <option value="pending">Pending</option>
            </select>
            <select className="input" value={orgFilter} onChange={(e) => setOrgFilter(e.target.value)}>
              <option value="">All organisations</option>
              {orgOptions.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </div>
          <div className="opsInterviewLegend muted">
            <span><span className="leadPill leadPillAdvance">Healthy</span> all channels OK</span>
            <span><span className="leadPill leadPillHold">Partial</span> in progress</span>
            <span><span className="leadPill leadPillDecline">Failed / Stuck</span> needs action</span>
          </div>
        </div>
      </div>

      <div className="card runningSurveyListCard opsInterviewTableCard">
        <div className="cardHead runningSurveyListHead">
          <h3><Briefcase size={16} /> Interview orders</h3>
          <div className="runningSurveyTabs opsInterviewTabs">
            {LIST_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`runningSurveyTab${listTab === tab.id ? ' on' : ''}`}
                onClick={() => setListTab(tab.id)}
              >
                {tab.label}
                <span className="opsInterviewTabCount">{tabCounts[tab.id] ?? 0}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="cardBody">
          {loading ? (
            <div className="opsInterviewEmptyState">
              <RefreshCw size={18} className="opsInterviewSpin" />
              <div>Loading interview operations…</div>
            </div>
          ) : null}
          {!loading && !filteredOrders.length ? (
            <div className="opsInterviewEmptyState">
              <div>No interviews match the current filters.</div>
              <button type="button" className="btn soft bsm" onClick={() => { setListTab('all'); setKpiFilter(''); setSearchQuery(''); setStatusFilter(''); setPaymentFilter(''); setEmailFilter(''); setCallFilter(''); setWaFilter(''); setLaunchFilter(''); setOrgFilter('') }}>
                Clear filters
              </button>
            </div>
          ) : null}
          {!loading && filteredOrders.length ? (
            <div className="tableWrap opsInterviewTableWrap">
              <table className="table runningSurveyTable opsInterviewTable">
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Organisation</th>
                    <th>Role / campaign</th>
                    <th>Recipients</th>
                    <th>Launch</th>
                    <th>Email</th>
                    <th>WhatsApp</th>
                    <th>Call</th>
                    <th>Payment</th>
                    <th>Health</th>
                    <th>Last activity</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredOrders.map((o) => (
                    <tr
                      key={o.id}
                      className={`opsInterviewRow${selectedSummary?.id === o.id ? ' isSelected' : ''}${o.needs_attention ? ' needsAttention' : ''}`}
                      onClick={() => openRow(o)}
                    >
                      <td>
                        <code>{o.reference_id || o.campaign_id || o.id.slice(0, 8)}</code>
                        {o.needs_attention ? <AlertTriangle size={14} className="opsInterviewAlertIcon" title="Needs attention" /> : null}
                      </td>
                      <td>{o.org_name || '—'}</td>
                      <td>
                        <strong>{o.role_title || o.title}</strong>
                        <div className="muted opsInterviewSubCell">{o.status_label || o.status}</div>
                      </td>
                      <td>{o.recipient_count || o.delivery?.recipient_total || '—'}</td>
                      <td><DeliveryChip label={o.launch_label || '—'} state={o.launch_status === 'launch_failed' ? 'failed' : 'partial'} /></td>
                      <td><DeliveryChip label={o.email_label || '—'} state={o.email_status} /></td>
                      <td><DeliveryChip label={o.whatsapp_label || '—'} state={o.whatsapp_status} /></td>
                      <td><DeliveryChip label={o.call_label || '—'} state={o.call_status} /></td>
                      <td><span className={statusPill(o.status, o.payment_status)}>{o.payment_status || '—'}</span></td>
                      <td><span className={healthPill(o.delivery_health)}>{healthLabel(o.delivery_health)}</span></td>
                      <td className="muted opsInterviewWhen">{fmtShort(o.last_activity_at)}</td>
                      <td><ChevronRight size={16} className="opsInterviewChevron" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </div>

      {drawerOpen && drawerOrder ? (
        <div className="opsInterviewDrawerOverlay" role="presentation" onClick={closeDrawer}>
          <aside className="opsInterviewDrawer" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <div className="opsInterviewDrawerHead">
              <div>
                <div className="opsInterviewDrawerEyebrow">Interview order</div>
                <h3>{drawerOrder.title || selected?.title}</h3>
                <div className="muted runningSurveyDetailSub">
                  {drawerOrder.reference_id ? <><code>{drawerOrder.reference_id}</code> · </> : null}
                  {drawerOrder.org_name || selected?.org_name} · {drawerOrder.owner_email || selected?.owner_email}
                </div>
              </div>
              <button type="button" className="btn soft bsm" onClick={closeDrawer} aria-label="Close">
                <X size={16} />
              </button>
            </div>

            {detailLoading ? (
              <div className="opsInterviewDrawerLoading muted">Loading order detail…</div>
            ) : (
              <>
                {(drawerOrder.needs_attention || failureReasons.length) ? (
                  <div className="opsInterviewAttentionBanner">
                    <AlertTriangle size={16} />
                    <div>
                      <strong>Needs attention</strong>
                      <ul>
                        {failureReasons.slice(0, 4).map((reason) => (
                          <li key={reason}>{reason}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                ) : null}

                <div className="opsInterviewDrawerActions runningSurveyActionBar">
                  {selected?.payment_status === 'pending_approval' ? (
                    <>
                      <button type="button" className="btn primary bsm" disabled={busyKey === selected.id} onClick={() => runAction(selected.id, 'approve-payment')}>
                        Approve payment
                      </button>
                      <button type="button" className="btn soft bsm" disabled={busyKey === selected.id} onClick={() => runAction(selected.id, 'reject-payment', { note: 'Rejected by admin' })}>
                        Reject payment
                      </button>
                    </>
                  ) : null}
                  <button type="button" className="btn primary bsm" disabled={!selected || busyKey === selected?.id} onClick={() => runAction(selected.id, 'start')}>
                    <Play size={14} /> Start
                  </button>
                  <button type="button" className="btn soft bsm" disabled={!isRunning || busyKey === selected?.id} onClick={() => runAction(selected.id, 'pause')}>
                    <Pause size={14} /> Pause
                  </button>
                  <button type="button" className="btn soft bsm" disabled={!selected || busyKey === selected?.id} onClick={() => runAction(selected.id, 'resume')}>
                    <Play size={14} /> Resume
                  </button>
                  <button type="button" className="btn soft bsm" disabled={!selected || busyKey === selected?.id} onClick={() => {
                    if (!window.confirm(`Stop interview "${selected.title}"? Pending calls will not be placed.`)) return
                    runAction(selected.id, 'stop', { reason: 'Stopped by admin' })
                  }}>
                    <Square size={14} /> Stop
                  </button>
                  {selected?.owner_email ? (
                    <a className="btn soft bsm" href={`mailto:${selected.owner_email}`}><Mail size={14} /> Owner</a>
                  ) : null}
                </div>

                <div className="runningSurveyTabs opsInterviewDrawerTabs">
                  <button type="button" className={`runningSurveyTab${panelTab === 'overview' ? ' on' : ''}`} onClick={() => setPanelTab('overview')}>Overview</button>
                  <button type="button" className={`runningSurveyTab${panelTab === 'recipients' ? ' on' : ''}`} onClick={() => setPanelTab('recipients')}>
                    <Users size={14} /> Recipients ({recipients.length})
                  </button>
                  <button type="button" className={`runningSurveyTab${panelTab === 'timeline' ? ' on' : ''}`} onClick={() => setPanelTab('timeline')}>
                    <Activity size={14} /> Timeline
                  </button>
                  <button type="button" className={`runningSurveyTab${panelTab === 'failures' ? ' on' : ''}`} onClick={() => setPanelTab('failures')}>
                    Failures {failureReasons.length ? `(${failureReasons.length})` : ''}
                  </button>
                </div>

                <div className="opsInterviewDrawerBody">
                  {panelTab === 'overview' ? (
                    <div className="runningSurveyMetaGrid">
                      <div className="runningSurveyMetaBlock">
                        <div className="runningSurveyMetaLabel">Delivery health</div>
                        <span className={healthPill(drawerOrder.delivery_health)}>{healthLabel(drawerOrder.delivery_health)}</span>
                      </div>
                      <div className="runningSurveyMetaBlock">
                        <div className="runningSurveyMetaLabel">Launch status</div>
                        <div>{drawerOrder.launch_label || '—'}</div>
                      </div>
                      <div className="runningSurveyMetaBlock">
                        <div className="runningSurveyMetaLabel">Launch requested</div>
                        <div>{fmtWhen(drawerOrder.launch_requested_at || config.launch_requested_at)}</div>
                      </div>
                      <div className="runningSurveyMetaBlock">
                        <div className="runningSurveyMetaLabel">Invites sent</div>
                        <div>{fmtWhen(drawerOrder.booking_invites_sent_at || config.booking_invites_sent_at)}</div>
                      </div>
                      <div className="runningSurveyMetaBlock">
                        <div className="runningSurveyMetaLabel">Payment</div>
                        <div>{selected?.payment_status} · {selected?.payment_method || 'none'}</div>
                      </div>
                      <div className="runningSurveyMetaBlock">
                        <div className="runningSurveyMetaLabel">Schedule</div>
                        <div>{fmtWhen(selected?.scheduled_start_at)} → {fmtWhen(selected?.scheduled_end_at)}</div>
                      </div>
                      <div className="runningSurveyMetaBlock">
                        <div className="runningSurveyMetaLabel">Role</div>
                        <div>{config.role || '—'}</div>
                      </div>
                      <div className="runningSurveyMetaBlock">
                        <div className="runningSurveyMetaLabel">Call progress</div>
                        <div>{Number(report?.completed ?? report?.reached ?? 0)} screened · {Math.max(0, (selected?.recipient_count || 0) - Number(report?.completed ?? report?.reached ?? 0))} pending</div>
                      </div>
                      <div className="runningSurveyMetaBlock">
                        <div className="runningSurveyMetaLabel">Last error</div>
                        <div className="opsInterviewErrorText">{drawerOrder.last_error || '—'}</div>
                      </div>
                      <div className="runningSurveyMetaBlock">
                        <div className="runningSurveyMetaLabel">Last activity</div>
                        <div>{fmtWhen(drawerOrder.last_activity_at)}</div>
                      </div>
                    </div>
                  ) : null}

                  {panelTab === 'recipients' ? (
                    <div className="runningSurveyContactsPane">
                      {editingId ? (
                        <div className="runningSurveyEditPanel">
                          <div className="runningSurveyEditTitle">Edit candidate</div>
                          <div className="runningSurveyEditGrid">
                            <label>Name<input className="input" value={editForm.name} onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))} /></label>
                            <label>Phone<input className="input" value={editForm.phone} onChange={(e) => setEditForm((f) => ({ ...f, phone: e.target.value }))} /></label>
                            <label>Email<input className="input" value={editForm.email} onChange={(e) => setEditForm((f) => ({ ...f, email: e.target.value }))} /></label>
                            <label>Status<input className="input" value={editForm.status} onChange={(e) => setEditForm((f) => ({ ...f, status: e.target.value }))} /></label>
                          </div>
                          <div className="runningSurveyActionBar">
                            <button type="button" className="btn primary bsm" disabled={busyKey === `save-${editingId}`} onClick={saveCandidate}>Save</button>
                            <button type="button" className="btn soft bsm" onClick={() => setEditingId(null)}>Cancel</button>
                          </div>
                        </div>
                      ) : null}

                      <div className="tableWrap">
                        <table className="table runningSurveyContactsTable opsInterviewRecipientsTable">
                          <thead>
                            <tr>
                              <th>#</th>
                              <th>Candidate</th>
                              <th>Contact</th>
                              <th>Activity</th>
                              <th>Status</th>
                              <th>Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {recipients.map((r) => (
                              <tr key={r.id} className={activityRow?.id === r.id ? 'isSelected' : ''}>
                                <td>{r.row_number}</td>
                                <td>
                                  <strong>{r.name || '—'}</strong>
                                  <div className="muted opsInterviewSubCell">{cvQualityLabel(r.cv_quality)}{r.cv_filename ? ` · ${r.cv_filename}` : ''}</div>
                                </td>
                                <td>
                                  <div>{r.phone || '—'}</div>
                                  <div className="muted opsInterviewSubCell">{r.email || '—'}</div>
                                </td>
                                <td><span className={activityPill(r.activity_status)}>{activityStatusLabel(r.activity_status)}</span></td>
                                <td><span className={candidatePill(r.status)}>{r.status || 'pending'}</span></td>
                                <td>
                                  <div className="runningSurveyRowActions opsInterviewRecipientActions">
                                    <button type="button" className="btn soft bsm" onClick={() => openActivity(r)}>
                                      <Activity size={14} /> Timeline
                                    </button>
                                    <button type="button" className="btn soft bsm" disabled={busyKey === `invite-${r.id}`} onClick={() => resendInvite(r, { emailOnly: true })}>
                                      <Mail size={14} /> Email
                                    </button>
                                    <button type="button" className="btn soft bsm" disabled={busyKey === `invite-${r.id}`} onClick={() => resendInvite(r)}>
                                      <MessageCircle size={14} /> Invite
                                    </button>
                                    <button type="button" className="btn soft bsm" onClick={() => copyText(`${r.name || ''} · ${r.phone || ''} · ${r.email || ''}`)}>
                                      <Phone size={14} /> Copy
                                    </button>
                                    {r.activity_status === 'report_ready' || r.status === 'completed' ? (
                                      <>
                                        <button type="button" className="btn soft bsm" disabled={busyKey === `report-html-${r.id}`} onClick={() => downloadReport(r, 'html')}>Report</button>
                                        <button type="button" className="btn soft bsm" disabled={busyKey === `report-pdf-${r.id}`} onClick={() => downloadReport(r, 'pdf')}>PDF</button>
                                      </>
                                    ) : null}
                                    {r.has_cv_file ? (
                                      <button type="button" className="btn soft bsm" disabled={busyKey === `cv-${r.id}`} onClick={() => downloadCv(r)}>
                                        <Download size={14} /> CV
                                      </button>
                                    ) : null}
                                    <button type="button" className="btn soft bsm" onClick={() => startEditCandidate(r)}>Edit</button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                            {!recipients.length ? (
                              <tr><td colSpan={6} className="muted">No recipients on this order.</td></tr>
                            ) : null}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ) : null}

                  {panelTab === 'timeline' ? (
                    <div className="opsInterviewTimelinePane">
                      {activityRow && activityData ? (
                        <div className="opsInterviewRecipientTimeline">
                          <h4>{activityRow.name || activityRow.email || activityRow.id}</h4>
                          <span className={activityPill(activityData.activity_status)}>{activityStatusLabel(activityData.activity_status)}</span>
                          <ul className="activityTimeline">
                            {(activityData.events || []).map((ev, idx) => (
                              <li key={`${ev.at}-${idx}`} className="isDone">
                                <div className="activityTimelineLabel">{ev.label}</div>
                                <div className="muted">{fmtWhen(ev.at)}</div>
                                {ev.detail ? <div className="runningSurveyAuditDetail">{ev.detail}</div> : null}
                              </li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      <h4>Order audit</h4>
                      <ul className="runningSurveyAuditList">
                        {timeline.map((ev, idx) => (
                          <li key={`${ev.at}-${idx}`}>
                            <div className="runningSurveyAuditLabel">{ev.label}</div>
                            <div className="muted">{fmtWhen(ev.at)}</div>
                            {ev.detail ? <div className="runningSurveyAuditDetail">{ev.detail}</div> : null}
                          </li>
                        ))}
                        {!timeline.length ? <li className="muted">No audit events yet.</li> : null}
                      </ul>
                      {activityLoading ? <div className="muted">Loading recipient timeline…</div> : null}
                      {!activityRow ? <div className="muted opsInterviewHint">Open a recipient timeline from the Recipients tab.</div> : null}
                    </div>
                  ) : null}

                  {panelTab === 'failures' ? (
                    <div className="opsInterviewFailuresPane">
                      {failureReasons.length ? (
                        <ul className="opsInterviewFailureList">
                          {failureReasons.map((reason) => (
                            <li key={reason}>
                              <AlertTriangle size={14} />
                              <span>{reason}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <div className="muted">No recorded failures for this order.</div>
                      )}
                      {drawerOrder.last_invite_dispatch ? (
                        <div className="runningSurveyMetaBlock" style={{ marginTop: 16 }}>
                          <div className="runningSurveyMetaLabel">Last invite dispatch</div>
                          <pre className="opsInterviewRawLog">{JSON.stringify(drawerOrder.last_invite_dispatch, null, 2)}</pre>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </>
            )}
          </aside>
        </div>
      ) : null}
    </>
  )
}
