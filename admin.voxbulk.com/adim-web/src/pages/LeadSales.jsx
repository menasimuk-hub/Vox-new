import React, { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Modal } from '@/components/ui/Modal'
import {
  CheckCircle2,
  XCircle,
  Phone,
  Trash2,
  FileText,
  ChevronDown,
  RefreshCw,
  Search,
} from 'lucide-react'

function initials(name, company) {
  const source = String(name || company || '?').trim()
  const parts = source.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return source.slice(0, 2).toUpperCase()
}

function statusClass(status) {
  const map = {
    pending_approval: 'status-pending',
    approved: 'status-approved',
    calling: 'status-calling',
    completed: 'status-done',
    rejected: 'status-rejected',
  }
  return map[status] || 'status-pending'
}

function formatWhen(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString()
}

export default function LeadSales() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState('')
  const [tasks, setTasks] = useState([])
  const [busyId, setBusyId] = useState('')
  const [stats, setStats] = useState({ pending_approval: 0, waiting_to_dial: 0, needs_consent: 0, done_today: 0 })
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') || 'all')
  const [consentFilter, setConsentFilter] = useState('all')
  const [detailTask, setDetailTask] = useState(null)
  const [selectedIds, setSelectedIds] = useState([])

  const load = async () => {
    setLoading(true)
    setMsg('')
    try {
      const res = await apiFetch('/admin/frontpage/lead-sales/tasks')
      setTasks(res?.tasks || [])
      
      // Calculate stats
      const now = new Date()
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
      const pending = (res?.tasks || []).filter(t => t.status === 'pending_approval').length
      const approved = (res?.tasks || []).filter(t => t.status === 'approved' && t.callback_consent === true).length
      const needsConsent = (res?.tasks || []).filter(t => t.callback_consent !== true && t.status !== 'rejected').length
      const doneToday = (res?.tasks || []).filter(t => {
        const updated = new Date(t.updated_at)
        return t.status === 'completed' && updated >= todayStart
      }).length
      
      setStats({
        pending_approval: pending,
        waiting_to_dial: approved,
        needs_consent: needsConsent,
        done_today: doneToday,
      })
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
        if (detailTask?.id === data.task.id) {
          setDetailTask(data.task)
        }
      }
      await load()
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
      if (detailTask?.id === task.id) {
        setDetailTask(null)
      }
    } catch (e) {
      setMsg(e?.message || 'Delete failed')
    } finally {
      setBusyId('')
    }
  }

  const deleteSelected = async () => {
    if (!selectedIds.length) return
    if (!window.confirm(`Delete ${selectedIds.length} selected task(s)?`)) return
    setBusyId('bulk-delete')
    try {
      await Promise.all(selectedIds.map(id => apiFetch(`/admin/frontpage/lead-sales/tasks/${id}`, { method: 'DELETE' })))
      setTasks((rows) => rows.filter((r) => !selectedIds.includes(r.id)))
      setSelectedIds([])
      setMsg(`${selectedIds.length} task(s) deleted.`)
    } catch (e) {
      setMsg(e?.message || 'Bulk delete failed')
    } finally {
      setBusyId('')
    }
  }

  const toggleSelect = (id) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const toggleSelectAll = () => {
    if (selectedIds.length === filteredTasks.length) {
      setSelectedIds([])
    } else {
      setSelectedIds(filteredTasks.map((t) => t.id))
    }
  }

  const filteredTasks = tasks.filter((task) => {
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      const text = `${task.company_name || ''} ${task.contact_name || ''} ${task.phone || ''} ${task.email || ''}`.toLowerCase()
      if (!text.includes(q)) return false
    }
    if (statusFilter !== 'all' && task.status !== statusFilter) return false
    if (consentFilter !== 'all') {
      if (consentFilter === 'yes' && task.callback_consent !== true) return false
      if (consentFilter === 'no' && task.callback_consent === true) return false
    }
    return true
  })

  const canCall = (task) => {
    if (typeof task.can_call === 'boolean') return task.can_call
    return task.status === 'approved' && task.callback_consent === true
  }

  const canApprove = (task) => {
    if (typeof task.can_approve === 'boolean') return task.can_approve
    return task.status === 'pending_approval' && task.callback_consent === true
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Lead sales</h1>
          <p>
            Consent-gated outbound sales tasks. Approve, verify consent, then call. Configure the master script under{' '}
            <Link to='/marketing/lead-sales/settings'>Sales setup</Link>.
          </p>
        </div>
        <div className='actions'>
          <Button variant="soft" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
            {loading ? 'Loading…' : 'Refresh'}
          </Button>
          <Button variant="soft" size="sm" asChild>
            <Link to='/marketing/lead-sales/settings'>Sales setup</Link>
          </Button>
        </div>
      </div>

      {msg ? (
        <div className={`note ${/fail|error/i.test(msg) ? 'noteWarn' : ''}`} style={{ marginBottom: 16 }}>
          {msg}
        </div>
      ) : null}

      <section className='card'>
        <div className='cardBody' style={{ padding: 0 }}>
          {/* Top stats */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.5rem 2rem', padding: '1rem 1.5rem', borderBottom: '1px solid var(--ds-border)' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', fontSize: '0.9rem', color: 'var(--ds-text-primary)' }}>
              <span style={{ fontWeight: 600, fontSize: '1.1rem', marginRight: '0.35rem', background: '#fef3c7', padding: '0.15rem 0.6rem', borderRadius: '20px', color: '#92400e' }}>
                {stats.pending_approval}
              </span>
              <span>Pending approval</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', fontSize: '0.9rem', color: 'var(--ds-text-primary)' }}>
              <span style={{ fontWeight: 600, fontSize: '1.1rem', marginRight: '0.35rem', background: '#dbeafe', padding: '0.15rem 0.6rem', borderRadius: '20px', color: '#1e4a7a' }}>
                {stats.waiting_to_dial}
              </span>
              <span>Waiting to dial</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', fontSize: '0.9rem', color: 'var(--ds-text-primary)' }}>
              <span style={{ fontWeight: 600, fontSize: '1.1rem', marginRight: '0.35rem', background: '#fee2e2', padding: '0.15rem 0.6rem', borderRadius: '20px', color: '#991b1b' }}>
                {stats.needs_consent}
              </span>
              <span>Needs consent</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', fontSize: '0.9rem', color: 'var(--ds-text-primary)' }}>
              <span style={{ fontWeight: 600, fontSize: '1.1rem', marginRight: '0.35rem', background: '#dcfce7', padding: '0.15rem 0.6rem', borderRadius: '20px', color: '#14532d' }}>
                {stats.done_today}
              </span>
              <span>Done today</span>
            </div>
          </div>

          {/* Filter bar */}
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem 1.2rem', padding: '0.75rem 1.5rem', borderBottom: '1px solid var(--ds-border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', background: 'var(--ds-surface-secondary)', borderRadius: '40px', padding: '0.15rem 0.15rem 0.15rem 1rem', border: '1px solid var(--ds-border)' }}>
              <Search className="h-3.5 w-3.5 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search company, contact..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ border: 'none', background: 'transparent', padding: '0.4rem 0.6rem', fontSize: '0.85rem', width: '200px', outline: 'none' }}
              />
            </div>
            <span style={{ fontSize: '0.8rem', color: 'var(--ds-text-secondary)', fontWeight: 450 }}>Filter:</span>
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value)
                if (e.target.value !== 'all') {
                  searchParams.set('status', e.target.value)
                } else {
                  searchParams.delete('status')
                }
                setSearchParams(searchParams)
              }}
              style={{ background: 'var(--ds-surface-secondary)', border: '1px solid var(--ds-border)', borderRadius: '40px', padding: '0.3rem 1rem 0.3rem 1.2rem', fontSize: '0.8rem', outline: 'none' }}
            >
              <option value="all">All status</option>
              <option value="pending_approval">Pending</option>
              <option value="approved">Approved</option>
              <option value="calling">Calling</option>
              <option value="completed">Done</option>
              <option value="rejected">Rejected</option>
            </select>
            <select
              value={consentFilter}
              onChange={(e) => setConsentFilter(e.target.value)}
              style={{ background: 'var(--ds-surface-secondary)', border: '1px solid var(--ds-border)', borderRadius: '40px', padding: '0.3rem 1rem 0.3rem 1.2rem', fontSize: '0.8rem', outline: 'none' }}
            >
              <option value="all">All consent</option>
              <option value="yes">Consent Yes</option>
              <option value="no">Consent No</option>
            </select>
            <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.4rem' }}>
              <button
                type="button"
                onClick={toggleSelectAll}
                style={{ background: 'var(--ds-surface-secondary)', border: '1px solid var(--ds-border)', borderRadius: '30px', padding: '0.2rem 0.9rem', fontSize: '0.75rem', cursor: 'pointer' }}
              >
                {selectedIds.length === filteredTasks.length && filteredTasks.length > 0 ? 'Deselect all' : 'Select all'}
              </button>
              <button
                type="button"
                onClick={deleteSelected}
                disabled={!selectedIds.length || busyId === 'bulk-delete'}
                style={{ background: '#fde8e8', border: '1px solid #f5c2c2', borderRadius: '30px', padding: '0.2rem 0.9rem', fontSize: '0.75rem', color: '#a13030', cursor: 'pointer' }}
              >
                {busyId === 'bulk-delete' ? '…' : `Delete selected (${selectedIds.length})`}
              </button>
            </div>
          </div>

          {/* Table */}
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', minWidth: '1150px' }}>
              <thead>
                <tr style={{ background: 'var(--ds-surface-secondary)', borderBottom: '1px solid var(--ds-border)' }}>
                  <th style={{ width: '30px', padding: '0.6rem 0.4rem 0.6rem 0.6rem', textAlign: 'left', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 550 }}>
                    <input
                      type="checkbox"
                      checked={selectedIds.length === filteredTasks.length && filteredTasks.length > 0}
                      onChange={toggleSelectAll}
                      style={{ width: '18px', height: '18px', accentColor: 'var(--ds-primary)', cursor: 'pointer' }}
                    />
                  </th>
                  <th style={{ padding: '0.6rem 0.4rem', textAlign: 'left', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 550 }}>Company / contact</th>
                  <th style={{ padding: '0.6rem 0.4rem', textAlign: 'left', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 550 }}>Phone / email</th>
                  <th style={{ padding: '0.6rem 0.4rem', textAlign: 'left', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 550 }}>Services</th>
                  <th style={{ padding: '0.6rem 0.4rem', textAlign: 'left', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 550 }}>Consent</th>
                  <th style={{ padding: '0.6rem 0.4rem', textAlign: 'left', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 550 }}>Why call</th>
                  <th style={{ padding: '0.6rem 0.4rem', textAlign: 'left', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 550 }}>Status</th>
                  <th style={{ padding: '0.6rem 0.4rem', textAlign: 'left', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 550 }}>Preferred time</th>
                  <th style={{ padding: '0.6rem 0.4rem', textAlign: 'left', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 550, minWidth: '200px' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredTasks.map((task) => {
                  const busy = busyId.startsWith(`${task.id}-`)
                  const services = task.interested_services ? task.interested_services.split(',').map(s => s.trim()).filter(Boolean) : []
                  return (
                    <tr key={task.id} style={{ borderBottom: '1px solid var(--ds-border)', background: '#ffffff' }} onMouseEnter={(e) => e.currentTarget.style.background = 'var(--ds-surface-tertiary)'} onMouseLeave={(e) => e.currentTarget.style.background = '#ffffff'}>
                      <td style={{ padding: '0.5rem 0.4rem 0.5rem 0.6rem' }}>
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(task.id)}
                          onChange={() => toggleSelect(task.id)}
                          style={{ width: '18px', height: '18px', accentColor: 'var(--ds-primary)', cursor: 'pointer' }}
                        />
                      </td>
                      <td style={{ padding: '0.5rem 0.4rem' }}>
                        <div style={{ fontWeight: 500, color: 'var(--ds-text-primary)' }}>{task.company_name || '—'}</div>
                        <div style={{ fontSize: '0.85rem', color: 'var(--ds-text-secondary)' }}>{task.contact_name || '—'}</div>
                      </td>
                      <td style={{ padding: '0.5rem 0.4rem' }}>
                        <div style={{ color: 'var(--ds-text-primary)' }}>{task.phone || '—'}</div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--ds-text-secondary)' }}>{task.email || '—'}</div>
                      </td>
                      <td style={{ padding: '0.5rem 0.4rem' }}>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.2rem 0.35rem' }}>
                          {services.map((s, i) => (
                            <span key={i} style={{ background: 'var(--ds-surface-secondary)', padding: '0.05rem 0.5rem', borderRadius: '30px', fontSize: '0.7rem', fontWeight: 450, whiteSpace: 'nowrap' }}>
                              {s}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td style={{ padding: '0.5rem 0.4rem' }}>
                        {task.callback_consent === true ? (
                          <span style={{ color: '#1a7a3a', fontWeight: 500, background: '#e6f7ec', padding: '0.1rem 0.6rem', borderRadius: '30px', fontSize: '0.7rem', display: 'inline-block' }}>
                            Yes
                          </span>
                        ) : (
                          <span style={{ color: '#b91c1c', fontWeight: 600, background: '#fee9e7', padding: '0.1rem 0.6rem', borderRadius: '30px', fontSize: '0.7rem', display: 'inline-block', border: '1px solid #fecaca' }}>
                            No
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '0.5rem 0.4rem' }}>
                        <div style={{ maxWidth: '150px', fontSize: '0.8rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {task.why_call || task.interest_summary || '—'}
                        </div>
                      </td>
                      <td style={{ padding: '0.5rem 0.4rem' }}>
                        <span className={cn('leadPill', statusClass(task.status))} style={{ fontSize: '0.7rem', padding: '0.15rem 0.7rem', borderRadius: '30px', whiteSpace: 'nowrap' }}>
                          {task.status_label || task.status}
                        </span>
                      </td>
                      <td style={{ padding: '0.5rem 0.4rem', fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                        {formatWhen(task.scheduled_at)}
                      </td>
                      <td style={{ padding: '0.5rem 0.4rem' }}>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem 0.35rem', alignItems: 'center' }}>
                          {task.status === 'pending_approval' ? (
                            <>
                              <button
                                type="button"
                                onClick={() => runTaskAction(task, 'approve')}
                                disabled={busy || !canApprove(task)}
                                title={!canApprove(task) ? 'Consent required before approve' : undefined}
                                style={{ background: canApprove(task) ? '#e6f7ec' : 'var(--ds-surface-secondary)', border: '1px solid #b7dfc9', borderRadius: '30px', padding: '0.15rem 0.6rem', fontSize: '0.72rem', fontWeight: 500, color: canApprove(task) ? '#0f5c3a' : 'var(--ds-text-tertiary)', cursor: canApprove(task) ? 'pointer' : 'not-allowed', opacity: canApprove(task) ? 1 : 0.45 }}
                              >
                                <CheckCircle2 className="inline h-3 w-3 mr-1" />
                                {busyId === `${task.id}-approve` ? '…' : 'Approve'}
                              </button>
                              <button
                                type="button"
                                onClick={() => runTaskAction(task, 'reject')}
                                disabled={busy}
                                style={{ background: '#fde8e8', border: '1px solid #f5c2c2', borderRadius: '30px', padding: '0.15rem 0.6rem', fontSize: '0.72rem', fontWeight: 500, color: '#a13030', cursor: 'pointer' }}
                              >
                                <XCircle className="inline h-3 w-3 mr-1" />
                                {busyId === `${task.id}-reject` ? '…' : 'Reject'}
                              </button>
                            </>
                          ) : null}
                          <button
                            type="button"
                            onClick={() => setDetailTask(task)}
                            style={{ background: 'var(--ds-surface-secondary)', border: '1px solid var(--ds-border)', borderRadius: '30px', padding: '0.15rem 0.6rem', fontSize: '0.72rem', fontWeight: 500, cursor: 'pointer' }}
                          >
                            <FileText className="inline h-3 w-3 mr-1" />
                            Detail
                          </button>
                          <button
                            type="button"
                            onClick={() => runTaskAction(task, 'call-now')}
                            disabled={busy || !canCall(task)}
                            style={{ background: canCall(task) ? '#dbeafe' : 'var(--ds-surface-secondary)', border: '1px solid var(--ds-border)', borderRadius: '30px', padding: '0.15rem 0.6rem', fontSize: '0.72rem', fontWeight: 500, color: canCall(task) ? '#004187' : 'var(--ds-text-tertiary)', cursor: canCall(task) ? 'pointer' : 'not-allowed', opacity: canCall(task) ? 1 : 0.45 }}
                          >
                            <Phone className="inline h-3 w-3 mr-1" />
                            {busyId === `${task.id}-call-now` ? '…' : 'Call now'}
                          </button>
                          <button
                            type="button"
                            onClick={() => deleteTask(task)}
                            disabled={busy}
                            style={{ background: '#fde8e8', border: '1px solid #f5c2c2', borderRadius: '30px', padding: '0.15rem 0.5rem', fontSize: '0.72rem', fontWeight: 500, color: '#a13030', cursor: 'pointer' }}
                          >
                            <Trash2 className="inline h-3 w-3" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {!loading && !filteredTasks.length ? (
              <p className='muted' style={{ padding: 24, textAlign: 'center' }}>
                No sales leads match the current filters. They are created when a website lead requests a sales callback.
              </p>
            ) : null}
            {loading ? <p className='muted' style={{ padding: 24, textAlign: 'center' }}>Loading…</p> : null}
          </div>
        </div>
      </section>

      {/* Detail modal */}
      {detailTask ? (
        <Modal
          isOpen={!!detailTask}
          onClose={() => setDetailTask(null)}
          title={`${detailTask.company_name || 'Unknown'} · ${detailTask.contact_name || 'Unknown'}`}
          size="large"
        >
          <div style={{ padding: '1rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem 2rem', marginBottom: '1.5rem' }}>
              <div>
                <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.03em', color: 'var(--ds-text-tertiary)', fontWeight: 500, marginBottom: '0.2rem' }}>Contact</div>
                <div style={{ fontSize: '0.95rem', color: 'var(--ds-text-primary)', fontWeight: 450, background: 'var(--ds-surface-secondary)', padding: '0.3rem 0.6rem', borderRadius: '8px', borderLeft: '3px solid var(--ds-border)' }}>
                  {detailTask.contact_name || '—'}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.03em', color: 'var(--ds-text-tertiary)', fontWeight: 500, marginBottom: '0.2rem' }}>Phone</div>
                <div style={{ fontSize: '0.95rem', color: 'var(--ds-text-primary)', fontWeight: 450, background: 'var(--ds-surface-secondary)', padding: '0.3rem 0.6rem', borderRadius: '8px', borderLeft: '3px solid var(--ds-border)' }}>
                  {detailTask.phone || '—'}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.03em', color: 'var(--ds-text-tertiary)', fontWeight: 500, marginBottom: '0.2rem' }}>Email</div>
                <div style={{ fontSize: '0.95rem', color: 'var(--ds-text-primary)', fontWeight: 450, background: 'var(--ds-surface-secondary)', padding: '0.3rem 0.6rem', borderRadius: '8px', borderLeft: '3px solid var(--ds-border)' }}>
                  {detailTask.email || '—'}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.03em', color: 'var(--ds-text-tertiary)', fontWeight: 500, marginBottom: '0.2rem' }}>Source</div>
                <div style={{ fontSize: '0.95rem', color: 'var(--ds-text-primary)', fontWeight: 450, background: 'var(--ds-surface-secondary)', padding: '0.3rem 0.6rem', borderRadius: '8px', borderLeft: '3px solid var(--ds-border)' }}>
                  {detailTask.source_label || detailTask.source || '—'}
                </div>
              </div>
              <div style={{ gridColumn: '1 / -1' }}>
                <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.03em', color: 'var(--ds-text-tertiary)', fontWeight: 500, marginBottom: '0.2rem' }}>Why call / interest summary</div>
                <div style={{ fontSize: '0.95rem', color: 'var(--ds-text-primary)', fontWeight: 450, background: 'var(--ds-surface-secondary)', padding: '0.6rem 0.8rem', borderRadius: '8px', borderLeft: '3px solid var(--ds-border)' }}>
                  {detailTask.why_call || detailTask.interest_summary || '—'}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.03em', color: 'var(--ds-text-tertiary)', fontWeight: 500, marginBottom: '0.2rem' }}>Consent</div>
                <div style={{ fontSize: '0.95rem', color: 'var(--ds-text-primary)', fontWeight: 450, background: 'var(--ds-surface-secondary)', padding: '0.3rem 0.6rem', borderRadius: '8px', borderLeft: '3px solid var(--ds-border)' }}>
                  {detailTask.callback_consent === true ? (
                    <span style={{ color: '#1a7a3a', fontWeight: 500, background: '#e6f7ec', padding: '0.1rem 0.6rem', borderRadius: '30px', fontSize: '0.7rem', display: 'inline-block' }}>
                      Yes
                    </span>
                  ) : (
                    <span style={{ color: '#b91c1c', fontWeight: 600, background: '#fee9e7', padding: '0.1rem 0.6rem', borderRadius: '30px', fontSize: '0.7rem', display: 'inline-block', border: '1px solid #fecaca' }}>
                      No
                    </span>
                  )}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.03em', color: 'var(--ds-text-tertiary)', fontWeight: 500, marginBottom: '0.2rem' }}>Status</div>
                <div style={{ fontSize: '0.95rem', color: 'var(--ds-text-primary)', fontWeight: 450, background: 'var(--ds-surface-secondary)', padding: '0.3rem 0.6rem', borderRadius: '8px', borderLeft: '3px solid var(--ds-border)' }}>
                  {detailTask.status_label || detailTask.status}
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginTop: '1.5rem', paddingTop: '1rem', borderTop: '1px solid var(--ds-border)' }}>
              {detailTask.status === 'pending_approval' ? (
                <>
                  <Button
                    size="sm"
                    onClick={() => runTaskAction(detailTask, 'approve')}
                    disabled={busyId.startsWith(`${detailTask.id}-`) || !canApprove(detailTask)}
                    title={!canApprove(detailTask) ? 'Consent required before approve' : undefined}
                    style={{ background: canApprove(detailTask) ? '#e6f7ec' : undefined, color: canApprove(detailTask) ? '#0f5c3a' : undefined }}
                  >
                    <CheckCircle2 className="h-4 w-4 mr-1" />
                    {busyId === `${detailTask.id}-approve` ? 'Approving…' : 'Approve call'}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => runTaskAction(detailTask, 'reject')}
                    disabled={busyId.startsWith(`${detailTask.id}-`)}
                    style={{ background: '#fde8e8', color: '#a13030' }}
                  >
                    <XCircle className="h-4 w-4 mr-1" />
                    {busyId === `${detailTask.id}-reject` ? 'Rejecting…' : 'Reject'}
                  </Button>
                </>
              ) : null}
              <Button
                size="sm"
                variant={canCall(detailTask) ? 'default' : 'outline'}
                onClick={() => runTaskAction(detailTask, 'call-now')}
                disabled={busyId.startsWith(`${detailTask.id}-`) || !canCall(detailTask)}
              >
                <Phone className="h-4 w-4 mr-1" />
                {busyId === `${detailTask.id}-call-now` ? 'Calling…' : 'Call now'}
              </Button>
              <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--ds-text-tertiary)' }}>
                Consent editable via Edit
              </span>
            </div>
          </div>
        </Modal>
      ) : null}
    </>
  )
}
