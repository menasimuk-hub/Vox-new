import React, { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import {
  Send,
  RefreshCw,
  Search,
  AlertTriangle,
} from 'lucide-react'

function statusBadgeStyle(status) {
  const map = {
    ready_after_call: { background: '#dbeafe', color: '#004085' },
    pending: { background: '#fef3c7', color: '#8a6d1f' },
    sent: { background: '#d4edda', color: '#0b5e2e' },
    failed: { background: '#f8d7da', color: '#842029' },
  }
  return map[status] || { background: '#fef3c7', color: '#8a6d1f' }
}

function statusLabel(status) {
  const map = {
    ready_after_call: 'Ready',
    pending: 'Pending',
    sent: 'Sent',
    failed: 'Failed',
  }
  return map[status] || status
}

const SERVICE_LABELS = {
  recruitment: 'Recruitment',
  surveys: 'Surveys',
  feedback: 'Feedback',
  expo: 'Expo',
  smart_card: 'Smart Card',
}

export default function SendOffer() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState('')
  const [tasks, setTasks] = useState([])
  const [templates, setTemplates] = useState([])
  const [busyId, setBusyId] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') || 'all')
  const [serviceFilter, setServiceFilter] = useState('all')
  
  // Send modal state
  const [sendTask, setSendTask] = useState(null)
  const [selectedService, setSelectedService] = useState('')
  const [selectedTemplateId, setSelectedTemplateId] = useState('')
  const [sendEmail, setSendEmail] = useState(true)
  const [sendWhatsapp, setSendWhatsapp] = useState(true)
  const [force, setForce] = useState(false)
  const [cooldownError, setCooldownError] = useState('')

  const load = async () => {
    setLoading(true)
    setMsg('')
    try {
      const [queueRes, templatesRes] = await Promise.all([
        apiFetch('/admin/frontpage/lead-sales/offer-queue'),
        apiFetch('/admin/frontpage/lead-sales/offer-templates'),
      ])
      setTasks(queueRes?.tasks || [])
      setTemplates(templatesRes?.templates || [])
    } catch (e) {
      const hint =
        e?.status === 404
          ? ' Restart API from voxbulk.com/voxbulk-api.'
          : e?.status === 401 || e?.status === 403
            ? ' Sign in again as platform admin.'
            : ''
      setMsg(`${e?.message || 'Could not load offer queue'}${hint}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const openSendModal = (task) => {
    setSendTask(task)
    setCooldownError('')
    setForce(false)
    
    // Pre-select service if task has one recommended service
    const services = task.services || []
    if (services.length === 1) {
      setSelectedService(services[0])
    } else {
      setSelectedService('')
    }
    setSelectedTemplateId('')
    
    // Default channels based on availability
    setSendEmail(!!task.email)
    setSendWhatsapp(!!task.phone)
  }

  const sendOffer = async () => {
    if (!sendTask || !selectedService || !selectedTemplateId) return
    
    if (!sendEmail && !sendWhatsapp) {
      setMsg('Please select at least one channel (email or WhatsApp)')
      return
    }
    
    setBusyId(`${sendTask.id}-send`)
    setMsg('')
    setCooldownError('')
    
    try {
      const data = await apiFetch(`/admin/frontpage/lead-sales/tasks/${sendTask.id}/send-offer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template_id: selectedTemplateId,
          service_code: selectedService,
          send_email: sendEmail,
          send_whatsapp: sendWhatsapp,
          force: force,
        }),
      })
      
      if (data?.task) {
        setTasks((rows) => rows.map((r) => (r.id === data.task.id ? data.task : r)))
        setMsg('Offer sent successfully')
        setSendTask(null)
      }
      await load()
    } catch (e) {
      const errorMsg = e?.message || 'Send failed'
      if (errorMsg.toLowerCase().includes('cooldown') || errorMsg.toLowerCase().includes('recently sent')) {
        setCooldownError(errorMsg)
      } else {
        setMsg(errorMsg)
        setSendTask(null)
      }
    } finally {
      setBusyId('')
    }
  }

  const filteredTasks = tasks.filter((task) => {
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      const text = `${task.company_name || ''} ${task.contact_name || ''} ${task.phone || ''} ${task.email || ''}`.toLowerCase()
      if (!text.includes(q)) return false
    }
    
    if (statusFilter !== 'all' && task.offer_queue_status !== statusFilter) return false
    
    if (serviceFilter !== 'all') {
      const services = task.services || []
      if (!services.includes(serviceFilter)) return false
    }
    
    return true
  })

  // Count by status
  const statusCounts = {
    ready_after_call: tasks.filter(t => t.offer_queue_status === 'ready_after_call').length,
    pending: tasks.filter(t => t.offer_queue_status === 'pending').length,
    sent: tasks.filter(t => t.offer_queue_status === 'sent').length,
    failed: tasks.filter(t => t.offer_queue_status === 'failed').length,
  }

  // Filter templates by selected service
  const availableTemplates = selectedService
    ? templates.filter(t => t.service_code === selectedService)
    : templates

  const canSend = sendTask?.offer_queue_status === 'ready_after_call'

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Send offer</h1>
          <p>
            Send pricing offers to leads after successful sales calls. Configure templates under{' '}
            <Link to='/marketing/lead-sales/offer-templates'>Offer templates</Link>.
          </p>
        </div>
        <div className='actions'>
          <Button variant="soft" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
            {loading ? 'Loading…' : 'Refresh'}
          </Button>
          <Button variant="soft" size="sm" asChild>
            <Link to='/marketing/lead-sales'>Lead sales</Link>
          </Button>
          <Button variant="soft" size="sm" asChild>
            <Link to='/marketing/lead-sales/offer-templates'>Offer templates</Link>
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
          {/* Status tabs */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem 0.5rem', padding: '1rem 1.5rem', borderBottom: '1px solid var(--ds-border)', background: 'var(--ds-surface-secondary)' }}>
            <button
              type="button"
              onClick={() => setStatusFilter('ready_after_call')}
              className={cn('tab-pill', statusFilter === 'ready_after_call' && 'active')}
              style={{
                background: statusFilter === 'ready_after_call' ? '#dbeafe' : 'var(--ds-surface-tertiary)',
                border: `1px solid ${statusFilter === 'ready_after_call' ? '#6b8fc4' : 'var(--ds-border)'}`,
                borderRadius: '30px',
                padding: '0.3rem 1rem',
                fontSize: '0.8rem',
                fontWeight: 500,
                color: statusFilter === 'ready_after_call' ? '#004187' : 'var(--ds-text-secondary)',
                cursor: 'pointer',
              }}
            >
              Ready after call <span style={{ background: statusFilter === 'ready_after_call' ? '#b6d4f0' : 'var(--ds-border)', padding: '0.05rem 0.5rem', borderRadius: '30px', fontSize: '0.7rem', marginLeft: '0.3rem' }}>{statusCounts.ready_after_call}</span>
            </button>
            <button
              type="button"
              onClick={() => setStatusFilter('pending')}
              className={cn('tab-pill', statusFilter === 'pending' && 'active')}
              style={{
                background: statusFilter === 'pending' ? '#fef3c7' : 'var(--ds-surface-tertiary)',
                border: `1px solid ${statusFilter === 'pending' ? '#d4af37' : 'var(--ds-border)'}`,
                borderRadius: '30px',
                padding: '0.3rem 1rem',
                fontSize: '0.8rem',
                fontWeight: 500,
                color: statusFilter === 'pending' ? '#8a6d1f' : 'var(--ds-text-secondary)',
                cursor: 'pointer',
              }}
            >
              Pending send <span style={{ background: statusFilter === 'pending' ? '#e8d89f' : 'var(--ds-border)', padding: '0.05rem 0.5rem', borderRadius: '30px', fontSize: '0.7rem', marginLeft: '0.3rem' }}>{statusCounts.pending}</span>
            </button>
            <button
              type="button"
              onClick={() => setStatusFilter('sent')}
              className={cn('tab-pill', statusFilter === 'sent' && 'active')}
              style={{
                background: statusFilter === 'sent' ? '#d4edda' : 'var(--ds-surface-tertiary)',
                border: `1px solid ${statusFilter === 'sent' ? '#9bc9a8' : 'var(--ds-border)'}`,
                borderRadius: '30px',
                padding: '0.3rem 1rem',
                fontSize: '0.8rem',
                fontWeight: 500,
                color: statusFilter === 'sent' ? '#0b5e2e' : 'var(--ds-text-secondary)',
                cursor: 'pointer',
              }}
            >
              Sent <span style={{ background: statusFilter === 'sent' ? '#b3d9be' : 'var(--ds-border)', padding: '0.05rem 0.5rem', borderRadius: '30px', fontSize: '0.7rem', marginLeft: '0.3rem' }}>{statusCounts.sent}</span>
            </button>
            <button
              type="button"
              onClick={() => setStatusFilter('failed')}
              className={cn('tab-pill', statusFilter === 'failed' && 'active')}
              style={{
                background: statusFilter === 'failed' ? '#f8d7da' : 'var(--ds-surface-tertiary)',
                border: `1px solid ${statusFilter === 'failed' ? '#f5c2c2' : 'var(--ds-border)'}`,
                borderRadius: '30px',
                padding: '0.3rem 1rem',
                fontSize: '0.8rem',
                fontWeight: 500,
                color: statusFilter === 'failed' ? '#842029' : 'var(--ds-text-secondary)',
                cursor: 'pointer',
              }}
            >
              Failed <span style={{ background: statusFilter === 'failed' ? '#f5c2c2' : 'var(--ds-border)', padding: '0.05rem 0.5rem', borderRadius: '30px', fontSize: '0.7rem', marginLeft: '0.3rem' }}>{statusCounts.failed}</span>
            </button>
            <button
              type="button"
              onClick={() => setStatusFilter('all')}
              className={cn('tab-pill', statusFilter === 'all' && 'active')}
              style={{
                background: statusFilter === 'all' ? '#ffffff' : 'var(--ds-surface-tertiary)',
                border: `1px solid ${statusFilter === 'all' ? 'var(--ds-border-heavy)' : 'var(--ds-border)'}`,
                borderRadius: '30px',
                padding: '0.3rem 1rem',
                fontSize: '0.8rem',
                fontWeight: 500,
                color: statusFilter === 'all' ? 'var(--ds-text-primary)' : 'var(--ds-text-secondary)',
                cursor: 'pointer',
              }}
            >
              All
            </button>
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
            <span style={{ fontSize: '0.8rem', color: 'var(--ds-text-secondary)', fontWeight: 450 }}>Service:</span>
            <select
              value={serviceFilter}
              onChange={(e) => setServiceFilter(e.target.value)}
              style={{ background: 'var(--ds-surface-secondary)', border: '1px solid var(--ds-border)', borderRadius: '40px', padding: '0.3rem 1rem 0.3rem 1.2rem', fontSize: '0.8rem', outline: 'none' }}
            >
              <option value="all">All services</option>
              <option value="recruitment">Recruitment</option>
              <option value="surveys">Surveys</option>
              <option value="feedback">Feedback</option>
              <option value="expo">Expo</option>
              <option value="smart_card">Smart Card</option>
            </select>
          </div>

          {/* Table */}
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', minWidth: '1150px' }}>
              <thead>
                <tr style={{ background: 'var(--ds-surface-secondary)', borderBottom: '1px solid var(--ds-border)' }}>
                  <th style={{ padding: '0.6rem 0.4rem 0.6rem 1.5rem', textAlign: 'left', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 550 }}>Company / contact</th>
                  <th style={{ padding: '0.6rem 0.4rem', textAlign: 'left', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 550 }}>Phone / email</th>
                  <th style={{ padding: '0.6rem 0.4rem', textAlign: 'left', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 550 }}>Services</th>
                  <th style={{ padding: '0.6rem 0.4rem', textAlign: 'left', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 550 }}>Outcome</th>
                  <th style={{ padding: '0.6rem 0.4rem', textAlign: 'left', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 550 }}>Status</th>
                  <th style={{ padding: '0.6rem 0.4rem 0.6rem 1.5rem', textAlign: 'right', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 550 }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredTasks.map((task) => {
                  const busy = busyId === `${task.id}-send`
                  const services = task.services || []
                  return (
                    <tr key={task.id} style={{ borderBottom: '1px solid var(--ds-border)', background: '#ffffff' }} onMouseEnter={(e) => e.currentTarget.style.background = 'var(--ds-surface-tertiary)'} onMouseLeave={(e) => e.currentTarget.style.background = '#ffffff'}>
                      <td style={{ padding: '0.5rem 0.4rem 0.5rem 1.5rem' }}>
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
                              {SERVICE_LABELS[s] || s}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td style={{ padding: '0.5rem 0.4rem' }}>
                        <div style={{ maxWidth: '180px', fontSize: '0.8rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: 'var(--ds-text-secondary)' }}>
                          {task.call_outcome || '—'}
                        </div>
                      </td>
                      <td style={{ padding: '0.5rem 0.4rem' }}>
                        <span style={{ ...statusBadgeStyle(task.offer_queue_status), fontSize: '0.7rem', padding: '0.15rem 0.7rem', borderRadius: '30px', whiteSpace: 'nowrap', display: 'inline-block', fontWeight: 500 }}>
                          {statusLabel(task.offer_queue_status)}
                        </span>
                      </td>
                      <td style={{ padding: '0.5rem 0.4rem 0.5rem 1.5rem', textAlign: 'right' }}>
                        <button
                          type="button"
                          onClick={() => openSendModal(task)}
                          disabled={busy}
                          style={{ background: task.offer_queue_status === 'ready_after_call' ? '#dbeafe' : 'var(--ds-surface-secondary)', border: '1px solid var(--ds-border)', borderRadius: '30px', padding: '0.15rem 0.7rem', fontSize: '0.72rem', fontWeight: 500, color: task.offer_queue_status === 'ready_after_call' ? '#004187' : 'var(--ds-text-secondary)', cursor: task.offer_queue_status === 'ready_after_call' ? 'pointer' : 'default' }}
                        >
                          <Send className="inline h-3 w-3 mr-1" />
                          {busy ? '…' : 'Send'}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {!loading && !filteredTasks.length ? (
              <p className='muted' style={{ padding: 24, textAlign: 'center' }}>
                No offers waiting. Complete a call on <Link to='/marketing/lead-sales'>Lead sales</Link> to populate this queue.
              </p>
            ) : null}
            {loading ? <p className='muted' style={{ padding: 24, textAlign: 'center' }}>Loading…</p> : null}
          </div>
        </div>
      </section>

      {/* Send offer modal */}
      {sendTask ? (
        <Modal
          isOpen={!!sendTask}
          onClose={() => setSendTask(null)}
          title={`Send offer · ${sendTask.company_name || 'Unknown'}`}
          size="medium"
        >
          <div style={{ padding: '1rem' }}>
            <div style={{ marginBottom: '1.5rem', paddingBottom: '1rem', borderBottom: '1px solid var(--ds-border)' }}>
              <div style={{ fontSize: '0.9rem', color: 'var(--ds-text-secondary)', marginBottom: '0.4rem' }}>
                <strong>{sendTask.contact_name || 'Unknown'}</strong> · {sendTask.phone || 'no phone'} · {sendTask.email || 'no email'}
              </div>
              {sendTask.call_outcome ? (
                <div style={{ fontSize: '0.85rem', color: 'var(--ds-text-tertiary)', fontStyle: 'italic' }}>
                  Outcome: {sendTask.call_outcome}
                </div>
              ) : null}
            </div>

            {/* Service selection */}
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.02em', color: 'var(--ds-text-secondary)', fontWeight: 500, marginBottom: '0.4rem' }}>
                Service required *
              </label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                {['recruitment', 'surveys', 'feedback', 'expo', 'smart_card'].map((svc) => (
                  <button
                    key={svc}
                    type="button"
                    onClick={() => {
                      setSelectedService(svc)
                      setSelectedTemplateId('')
                    }}
                    style={{
                      background: selectedService === svc ? '#dbeafe' : 'var(--ds-surface-secondary)',
                      border: `1px solid ${selectedService === svc ? '#6b8fc4' : 'var(--ds-border)'}`,
                      borderRadius: '30px',
                      padding: '0.2rem 0.9rem',
                      fontSize: '0.8rem',
                      color: selectedService === svc ? '#004187' : 'var(--ds-text-primary)',
                      cursor: 'pointer',
                    }}
                  >
                    {SERVICE_LABELS[svc] || svc}
                  </button>
                ))}
              </div>
            </div>

            {/* Template selection */}
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.02em', color: 'var(--ds-text-secondary)', fontWeight: 500, marginBottom: '0.4rem' }}>
                Offer template *
              </label>
              <select
                value={selectedTemplateId}
                onChange={(e) => setSelectedTemplateId(e.target.value)}
                disabled={!selectedService}
                style={{ width: '100%', background: '#ffffff', border: '1px solid var(--ds-border)', borderRadius: '30px', padding: '0.4rem 1rem', fontSize: '0.85rem', outline: 'none' }}
              >
                <option value="">— Select template —</option>
                {availableTemplates.map((tpl) => (
                  <option key={tpl.id} value={tpl.id}>
                    {tpl.name} {tpl.trial_days ? `(${tpl.trial_days}-day trial)` : ''}
                  </option>
                ))}
              </select>
              {selectedService && availableTemplates.length === 0 ? (
                <div style={{ fontSize: '0.75rem', color: 'var(--ds-text-tertiary)', marginTop: '0.3rem' }}>
                  No templates for {SERVICE_LABELS[selectedService]}. Add one under{' '}
                  <Link to='/marketing/lead-sales/offer-templates' style={{ color: 'var(--ds-primary)' }}>Offer templates</Link>.
                </div>
              ) : null}
            </div>

            {/* Channels */}
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.02em', color: 'var(--ds-text-secondary)', fontWeight: 500, marginBottom: '0.4rem' }}>
                Channels
              </label>
              <div style={{ display: 'flex', gap: '1rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', fontSize: '0.85rem', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={sendEmail}
                    onChange={(e) => setSendEmail(e.target.checked)}
                    disabled={!sendTask.email}
                    style={{ marginRight: '0.5rem' }}
                  />
                  Email {!sendTask.email ? '(unavailable)' : ''}
                </label>
                <label style={{ display: 'flex', alignItems: 'center', fontSize: '0.85rem', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={sendWhatsapp}
                    onChange={(e) => setSendWhatsapp(e.target.checked)}
                    disabled={!sendTask.phone}
                    style={{ marginRight: '0.5rem' }}
                  />
                  WhatsApp {!sendTask.phone ? '(unavailable)' : ''}
                </label>
              </div>
            </div>

            {/* Cooldown warning or force checkbox */}
            {cooldownError ? (
              <div style={{ background: '#fee9e7', borderRadius: '30px', padding: '0.5rem 1rem', fontSize: '0.8rem', color: '#991b1b', display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', border: '1px solid #f5c2c2' }}>
                <AlertTriangle className="h-4 w-4" />
                <span style={{ flex: 1 }}>{cooldownError}</span>
                <label style={{ display: 'flex', alignItems: 'center', fontSize: '0.75rem', fontWeight: 500, cursor: 'pointer', whiteSpace: 'nowrap', marginLeft: 'auto' }}>
                  <input
                    type="checkbox"
                    checked={force}
                    onChange={(e) => setForce(e.target.checked)}
                    style={{ marginRight: '0.4rem' }}
                  />
                  Force send
                </label>
              </div>
            ) : (
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', fontSize: '0.8rem', color: 'var(--ds-text-secondary)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={force}
                    onChange={(e) => setForce(e.target.checked)}
                    style={{ marginRight: '0.5rem' }}
                  />
                  Force send (bypass 7-day phone cooldown)
                </label>
              </div>
            )}

            <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.5rem', paddingTop: '1rem', borderTop: '1px solid var(--ds-border)' }}>
              <Button
                size="sm"
                onClick={sendOffer}
                disabled={busyId === `${sendTask.id}-send` || !selectedService || !selectedTemplateId || !canSend || (!sendEmail && !sendWhatsapp)}
                style={{ background: canSend && selectedService && selectedTemplateId && (sendEmail || sendWhatsapp) ? 'var(--ds-primary)' : 'var(--ds-surface-secondary)', color: canSend && selectedService && selectedTemplateId && (sendEmail || sendWhatsapp) ? '#ffffff' : 'var(--ds-text-tertiary)' }}
              >
                <Send className="h-4 w-4 mr-1" />
                {busyId === `${sendTask.id}-send` ? 'Sending…' : 'Send offer'}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setSendTask(null)}>
                Cancel
              </Button>
              {!canSend ? (
                <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--ds-text-tertiary)', alignSelf: 'center' }}>
                  Only ready tasks can send
                </span>
              ) : null}
            </div>
          </div>
        </Modal>
      ) : null}
    </>
  )
}
