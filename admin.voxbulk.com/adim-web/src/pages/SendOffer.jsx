import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import {
  RefreshCw,
  Search,
  Send,
  AlertTriangle,
} from 'lucide-react'

const SERVICE_CODES = [
  { code: 'recruitment', label: 'Recruitment' },
  { code: 'surveys', label: 'Surveys' },
  { code: 'feedback', label: 'Feedback' },
  { code: 'expo', label: 'Expo' },
  { code: 'smart_card', label: 'Smart Card' },
]

const CHANNEL_OPTIONS = [
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'email', label: 'Email' },
  { value: 'both', label: 'Both' },
]

export default function SendOffer() {
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState('')
  const [activeTab, setActiveTab] = useState('ready')
  const [tasks, setTasks] = useState([])
  const [templates, setTemplates] = useState([])
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [serviceFilter, setServiceFilter] = useState('all')
  const [selectedTask, setSelectedTask] = useState(null)
  const [selectedService, setSelectedService] = useState('recruitment')
  const [selectedTemplate, setSelectedTemplate] = useState('')
  const [selectedChannel, setSelectedChannel] = useState('whatsapp')
  const [sending, setSending] = useState(false)
  const [tabCounts, setTabCounts] = useState({ ready: 0, pending: 0, sent: 0, failed: 0 })

  const load = async () => {
    setLoading(true)
    setMsg('')
    try {
      const [tasksRes, templatesRes] = await Promise.all([
        apiFetch('/admin/frontpage/lead-sales/offer-queue').catch(() => ({ tasks: [] })),
        apiFetch(`/admin/frontpage/lead-sales/offer-templates?service=${selectedService}`).catch(() => ({ templates: [] })),
      ])
      
      const allTasks = tasksRes?.tasks || []
      setTasks(allTasks)
      setTemplates(templatesRes?.templates || [])
      
      // Calculate tab counts
      setTabCounts({
        ready: allTasks.filter(t => t.offer_status === 'ready').length,
        pending: allTasks.filter(t => t.offer_status === 'pending').length,
        sent: allTasks.filter(t => t.offer_status === 'sent').length,
        failed: allTasks.filter(t => t.offer_status === 'failed').length,
      })

      // Auto-select first task if none selected
      if (!selectedTask && allTasks.length > 0) {
        const firstReady = allTasks.find(t => t.offer_status === 'ready')
        if (firstReady) {
          setSelectedTask(firstReady)
        }
      }
    } catch (e) {
      setMsg(e?.message || 'Could not load offer queue')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    // Reload templates when service changes
    const loadTemplates = async () => {
      try {
        const res = await apiFetch(`/admin/frontpage/lead-sales/offer-templates?service=${selectedService}`)
        setTemplates(res?.templates || [])
        if (res?.templates?.length > 0) {
          setSelectedTemplate(res.templates[0].id || '')
        }
      } catch (e) {
        setTemplates([])
      }
    }
    loadTemplates()
  }, [selectedService])

  const sendOffer = async (force = false) => {
    if (!selectedTask) {
      setMsg('No task selected')
      return
    }
    if (!selectedTemplate) {
      setMsg('No template selected')
      return
    }

    setSending(true)
    setMsg('')
    try {
      const data = await apiFetch(`/admin/frontpage/lead-sales/tasks/${selectedTask.id}/send-offer`, {
        method: 'POST',
        body: JSON.stringify({
          service_code: selectedService,
          template_id: selectedTemplate,
          channel: selectedChannel,
          force,
        }),
      })
      setMsg(data?.message || 'Offer sent successfully')
      await load()
    } catch (e) {
      setMsg(e?.message || 'Send failed')
    } finally {
      setSending(false)
    }
  }

  const filteredTasks = tasks.filter((task) => {
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      const text = `${task.company_name || ''} ${task.contact_name || ''} ${task.phone || ''} ${task.email || ''}`.toLowerCase()
      if (!text.includes(q)) return false
    }
    if (statusFilter !== 'all' && task.offer_status !== statusFilter) return false
    if (serviceFilter !== 'all' && task.recommended_service !== serviceFilter) return false
    
    // Tab filter
    if (activeTab !== 'all' && task.offer_status !== activeTab) return false
    
    return true
  })

  const getTemplateName = (tpl) => {
    return tpl?.name || tpl?.title || 'Untitled template'
  }

  const getTemplatePreview = (tpl) => {
    if (!tpl) return 'Select a template to see preview'
    return tpl?.preview || tpl?.body || 'No preview available'
  }

  const selectedTemplateObj = templates.find(t => t.id === selectedTemplate)
  const canSend = selectedTask && selectedTask.offer_status === 'ready' && selectedTemplate
  const showBlockMessage = selectedTask && (selectedTask.offer_recently_sent || selectedTask.offer_blocked_reason)

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Send offer</h1>
          <p>
            Service offer delivery after successful sales calls. Select a lead, choose template and channel, then send.
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
        </div>
      </div>

      {msg ? (
        <div className={`note ${/fail|error/i.test(msg) ? 'noteWarn' : ''}`} style={{ marginBottom: 16 }}>
          {msg}
        </div>
      ) : null}

      <section className='card'>
        <div className='cardBody' style={{ padding: 0 }}>
          {/* Header: Tabs */}
          <div style={{ padding: '1rem 1.5rem', borderBottom: '1px solid var(--ds-border)' }}>
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList>
                <TabsTrigger value="ready">
                  Ready after call <Badge variant="outline" className="ml-1.5">{tabCounts.ready}</Badge>
                </TabsTrigger>
                <TabsTrigger value="pending">
                  Pending send <Badge variant="outline" className="ml-1.5">{tabCounts.pending}</Badge>
                </TabsTrigger>
                <TabsTrigger value="sent">
                  Sent <Badge variant="outline" className="ml-1.5">{tabCounts.sent}</Badge>
                </TabsTrigger>
                <TabsTrigger value="failed">
                  Failed <Badge variant="outline" className="ml-1.5">{tabCounts.failed}</Badge>
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {/* Search + filter bar */}
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.6rem 1rem', padding: '0.75rem 1.5rem', borderBottom: '1px solid var(--ds-border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', background: 'var(--ds-surface-secondary)', borderRadius: '40px', padding: '0.1rem 0.1rem 0.1rem 1rem', border: '1px solid var(--ds-border)', flex: '0 1 240px' }}>
              <Search className="h-3.5 w-3.5 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search company, contact..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ border: 'none', background: 'transparent', padding: '0.4rem 0.6rem', fontSize: '0.82rem', width: '180px', outline: 'none' }}
              />
            </div>
            <span style={{ fontSize: '0.78rem', color: 'var(--ds-text-secondary)', fontWeight: 450 }}>Service:</span>
            <select
              value={serviceFilter}
              onChange={(e) => setServiceFilter(e.target.value)}
              style={{ background: 'var(--ds-surface-secondary)', border: '1px solid var(--ds-border)', borderRadius: '40px', padding: '0.3rem 1rem 0.3rem 1.2rem', fontSize: '0.78rem', outline: 'none' }}
            >
              <option value="all">All services</option>
              {SERVICE_CODES.map(s => (
                <option key={s.code} value={s.code}>{s.label}</option>
              ))}
            </select>
          </div>

          {/* Two-column layout: table + send panel */}
          <div style={{ display: 'flex', gap: '1.75rem', padding: '1.5rem', alignItems: 'stretch' }}>
            {/* Left: Table */}
            <div style={{ flex: '2.2', minWidth: 0, overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem', minWidth: '700px' }}>
                <thead>
                  <tr style={{ background: 'var(--ds-surface-secondary)', borderBottom: '1px solid var(--ds-border)' }}>
                    <th style={{ padding: '0.5rem 0.4rem', textAlign: 'left', fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: 550 }}>Company / contact</th>
                    <th style={{ padding: '0.5rem 0.4rem', textAlign: 'left', fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: 550 }}>Phone / email</th>
                    <th style={{ padding: '0.5rem 0.4rem', textAlign: 'left', fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: 550 }}>Linked lead task</th>
                    <th style={{ padding: '0.5rem 0.4rem', textAlign: 'left', fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: 550 }}>Recommended service</th>
                    <th style={{ padding: '0.5rem 0.4rem', textAlign: 'left', fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: 550 }}>Last call outcome</th>
                    <th style={{ padding: '0.5rem 0.4rem', textAlign: 'left', fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: 550 }}>Status</th>
                    <th style={{ padding: '0.5rem 0.4rem', textAlign: 'left', fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: 550, width: '80px' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTasks.map((task) => {
                    const isSelected = selectedTask?.id === task.id
                    return (
                      <tr
                        key={task.id}
                        style={{ borderBottom: '1px solid var(--ds-border)', background: isSelected ? 'var(--ds-surface-tertiary)' : '#ffffff', cursor: 'pointer' }}
                        onMouseEnter={(e) => !isSelected && (e.currentTarget.style.background = 'var(--ds-surface-tertiary)')}
                        onMouseLeave={(e) => !isSelected && (e.currentTarget.style.background = '#ffffff')}
                        onClick={() => setSelectedTask(task)}
                      >
                        <td style={{ padding: '0.45rem 0.4rem' }}>
                          <div style={{ fontWeight: 500, color: 'var(--ds-text-primary)' }}>{task.company_name || '—'}</div>
                          <div style={{ fontSize: '0.85rem', color: 'var(--ds-text-secondary)' }}>{task.contact_name || '—'}</div>
                        </td>
                        <td style={{ padding: '0.45rem 0.4rem' }}>
                          <div style={{ color: 'var(--ds-text-primary)' }}>{task.phone || '—'}</div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--ds-text-secondary)' }}>{task.email || '—'}</div>
                        </td>
                        <td style={{ padding: '0.45rem 0.4rem', fontSize: '0.75rem' }}>
                          Lead #{task.lead_code || task.id} · {task.source || 'Unknown'}
                        </td>
                        <td style={{ padding: '0.45rem 0.4rem' }}>
                          <span style={{ background: 'var(--ds-surface-secondary)', padding: '0.05rem 0.6rem', borderRadius: '30px', fontSize: '0.7rem', whiteSpace: 'nowrap' }}>
                            {task.recommended_service || '—'}
                          </span>
                        </td>
                        <td style={{ padding: '0.45rem 0.4rem', fontSize: '0.75rem', maxWidth: '120px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {task.last_call_outcome || '—'}
                        </td>
                        <td style={{ padding: '0.45rem 0.4rem' }}>
                          <Badge
                            variant="outline"
                            className={cn(
                              'text-[10px] px-2',
                              task.offer_status === 'ready' && 'bg-blue-50 text-blue-700 border-blue-200',
                              task.offer_status === 'pending' && 'bg-yellow-50 text-yellow-700 border-yellow-200',
                              task.offer_status === 'sent' && 'bg-green-50 text-green-700 border-green-200',
                              task.offer_status === 'failed' && 'bg-red-50 text-red-700 border-red-200',
                            )}
                          >
                            {task.offer_status || 'Ready'}
                          </Badge>
                        </td>
                        <td style={{ padding: '0.45rem 0.4rem' }}>
                          <button
                            type="button"
                            onClick={() => setSelectedTask(task)}
                            className={cn(
                              'px-3 py-1 text-[11px] rounded-full border transition-colors',
                              isSelected
                                ? 'bg-blue-100 text-blue-700 border-blue-300'
                                : 'bg-gray-100 text-gray-700 border-gray-300 hover:bg-gray-200'
                            )}
                          >
                            {isSelected ? 'Selected' : 'Select'}
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              {!loading && !filteredTasks.length ? (
                <div style={{ textAlign: 'center', padding: '2.5rem 0.5rem', color: 'var(--ds-text-tertiary)', fontSize: '0.9rem' }}>
                  No offers waiting? Approve and complete a call on Lead Sales, or add a contact.
                </div>
              ) : null}
              {loading ? <div style={{ textAlign: 'center', padding: '2.5rem 0.5rem', color: 'var(--ds-text-tertiary)', fontSize: '0.9rem' }}>Loading…</div> : null}
            </div>

            {/* Right: Send panel (sticky) */}
            <div style={{ flex: '1.3', minWidth: '320px', background: 'var(--ds-surface-secondary)', borderRadius: '16px', padding: '1.25rem', border: '1px solid var(--ds-border)', height: 'fit-content', position: 'sticky', top: '1rem' }}>
              <div style={{ fontWeight: 600, fontSize: '1rem', color: 'var(--ds-text-primary)', marginBottom: '0.1rem' }}>
                Send offer
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--ds-text-tertiary)', marginBottom: '1.25rem', borderBottom: '1px solid var(--ds-border)', paddingBottom: '0.6rem' }}>
                Selected: <strong>{selectedTask ? `${selectedTask.company_name} · ${selectedTask.contact_name}` : 'none'}</strong>
              </div>

              {/* Service required (radios/chips) */}
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.02em', color: 'var(--ds-text-secondary)', fontWeight: 500, marginBottom: '0.2rem' }}>
                  Service required
                </label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem 0.5rem' }}>
                  {SERVICE_CODES.map((s) => (
                    <button
                      key={s.code}
                      type="button"
                      onClick={() => setSelectedService(s.code)}
                      className={cn(
                        'px-3 py-1 text-[13px] rounded-full border transition-colors',
                        selectedService === s.code
                          ? 'bg-blue-100 text-blue-700 border-blue-400'
                          : 'bg-gray-100 text-gray-700 border-gray-300 hover:bg-gray-200'
                      )}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Template dropdown */}
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.02em', color: 'var(--ds-text-secondary)', fontWeight: 500, marginBottom: '0.2rem' }}>
                  Offer template
                </label>
                <select
                  value={selectedTemplate}
                  onChange={(e) => setSelectedTemplate(e.target.value)}
                  style={{ width: '100%', background: '#ffffff', border: '1px solid var(--ds-border)', borderRadius: '30px', padding: '0.35rem 1rem', fontSize: '0.82rem', outline: 'none' }}
                >
                  <option value="">Select a template</option>
                  {templates.map((tpl) => (
                    <option key={tpl.id} value={tpl.id}>
                      {getTemplateName(tpl)}
                    </option>
                  ))}
                </select>
              </div>

              {/* Channel */}
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.02em', color: 'var(--ds-text-secondary)', fontWeight: 500, marginBottom: '0.2rem' }}>
                  Channel
                </label>
                <select
                  value={selectedChannel}
                  onChange={(e) => setSelectedChannel(e.target.value)}
                  style={{ width: '100%', background: '#ffffff', border: '1px solid var(--ds-border)', borderRadius: '30px', padding: '0.35rem 1rem', fontSize: '0.82rem', outline: 'none' }}
                >
                  {CHANNEL_OPTIONS.map((ch) => (
                    <option key={ch.value} value={ch.value}>
                      {ch.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Preview */}
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.02em', color: 'var(--ds-text-secondary)', fontWeight: 500, marginBottom: '0.2rem' }}>
                  Preview
                </label>
                <div style={{ background: 'var(--ds-surface-tertiary)', borderRadius: '12px', padding: '0.6rem 0.9rem', fontSize: '0.82rem', color: 'var(--ds-text-primary)', borderLeft: '3px solid var(--ds-border)', minHeight: '50px', lineHeight: 1.5 }}>
                  {getTemplatePreview(selectedTemplateObj)}
                </div>
              </div>

              {/* Block message */}
              {showBlockMessage ? (
                <div style={{ background: '#fee9e7', borderRadius: '30px', padding: '0.3rem 1rem', fontSize: '0.75rem', color: '#991b1b', display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.3rem', border: '1px solid #f5c2c2' }}>
                  <AlertTriangle className="h-3.5 w-3.5" />
                  {selectedTask.offer_blocked_reason || 'Already sent to this phone recently'}
                  <button
                    type="button"
                    onClick={() => sendOffer(true)}
                    disabled={sending}
                    style={{ color: '#1e4a7a', fontWeight: 500, textDecoration: 'underline', cursor: 'pointer', marginLeft: 'auto', background: 'none', border: 'none' }}
                  >
                    Force send (admin)
                  </button>
                </div>
              ) : null}

              {/* Send button */}
              <Button
                className="w-full mt-2"
                onClick={() => sendOffer(false)}
                disabled={!canSend || sending}
              >
                <Send className="h-4 w-4 mr-2" />
                {sending ? 'Sending…' : 'Send offer'}
              </Button>
              {!canSend && !sending ? (
                <div style={{ fontSize: '0.7rem', color: 'var(--ds-text-tertiary)', marginTop: '0.3rem', textAlign: 'center' }}>
                  Enable by selecting a ready lead
                </div>
              ) : null}

              {/* Small note */}
              <div style={{ marginTop: '1rem', fontSize: '0.65rem', color: 'var(--ds-text-tertiary)', borderTop: '1px solid var(--ds-border)', paddingTop: '0.6rem' }}>
                <AlertTriangle className="inline h-3 w-3 mr-1" />
                No auto-send. Templates filtered by service.
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
