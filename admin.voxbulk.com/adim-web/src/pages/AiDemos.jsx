import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bot,
  Check,
  CheckCircle2,
  Eye,
  Globe,
  Info,
  Inbox,
  Languages,
  Link2,
  ListTodo,
  Mail,
  MessageSquare,
  Mic,
  MousePointer2,
  Phone,
  Redo2,
  RefreshCw,
  Save,
  Search,
  Send,
  Settings,
  TriangleAlert,
  UserCircle2,
  UserPlus,
  Users,
  X,
} from 'lucide-react'
import { apiFetch } from '../lib/api'
import LeadSalesPipelineStrip, { leadSalesListUrl } from '../components/LeadSalesPipelineStrip'
import { TablePagination } from '@/components/ui/Table'
import './ai-demos.css'

const PAGE_SIZE = 20

const LANGS = [
  { id: 'en', label: 'English' },
  { id: 'ar', label: 'Arabic' },
]

const STATUS_FILTERS = [
  { label: 'All', value: '' },
  { label: 'Pending', value: 'pending' },
  { label: 'Approved', value: 'approved' },
  { label: 'Active', value: 'active' },
  { label: 'Completed', value: 'completed' },
  { label: 'Rejected', value: 'rejected' },
]

const emptyManual = {
  contact_name: '',
  email: '',
  company_name: '',
  whatsapp: '',
  website: 'https://voxbulk.com',
  preferred_language: 'en',
  voice_region: '',
  message: '',
}

function fmt(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString()
}

function statusBadgeClass(status) {
  const map = {
    pending: 'aid-badge-pending',
    approved: 'aid-badge-approved',
    active: 'aid-badge-active',
    completed: 'aid-badge-completed',
    rejected: 'aid-badge-rejected',
  }
  return map[status] || ''
}

export default function AiDemos({ embedded = false }) {
  const [tab, setTab] = useState('inbox')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState('created')
  const [manual, setManual] = useState(emptyManual)
  const [batchText, setBatchText] = useState('')
  const [batchLang, setBatchLang] = useState('en')
  const [batchRegion, setBatchRegion] = useState('')
  const [batchMsg, setBatchMsg] = useState('You are invited to a live VoxBulk AI demo.')
  const [compose, setCompose] = useState(null)
  const [detail, setDetail] = useState(null)
  const [settings, setSettings] = useState({
    provider_agent_id: '',
    from_email: '',
    soft_cap_minutes: 7,
    agent_by_region: {},
    regions: [],
    notes: '',
  })
  const [agents, setAgents] = useState([])
  const [busy, setBusy] = useState(false)
  const [batchResult, setBatchResult] = useState(null)
  const [page, setPage] = useState(1)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const q = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : ''
      const [list, st, preview, agentList] = await Promise.all([
        apiFetch(`/admin/ai-demo/requests${q}`),
        apiFetch('/admin/ai-demo/settings'),
        apiFetch('/admin/ai-demo/invite-preview').catch(() => null),
        apiFetch('/admin/ai-demo/agents').catch(() => ({ items: [] })),
      ])
      setItems(list.items || [])
      setAgents(Array.isArray(agentList?.items) ? agentList.items : [])
      setSettings({
        provider_agent_id: st.provider_agent_id || '',
        from_email: st.from_email || '',
        soft_cap_minutes: st.soft_cap_minutes || 7,
        notes: st.notes || '',
        agent_by_region: st.agent_by_region && typeof st.agent_by_region === 'object' ? st.agent_by_region : {},
        regions: Array.isArray(st.regions) ? st.regions : [],
        _previewSubject: preview?.subject || '',
        _previewBody: preview?.body || '',
      })
    } catch (e) {
      setError(e?.message || 'Failed to load AI demos')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    refresh()
  }, [refresh])

  const stats = useMemo(() => {
    const total = items.length
    const opened = items.filter((r) => r.opened_at).length
    const clicked = items.filter((r) => r.link_clicked_at).length
    const completed = items.filter((r) => r.demo_completed_at || r.status === 'completed').length
    return { total, opened, clicked, completed }
  }, [items])

  const sortedFilteredItems = useMemo(() => {
    let list = [...items]
    const q = searchQuery.trim().toLowerCase()
    if (q) {
      list = list.filter((r) => {
        const name = String(r.contact_name || '').toLowerCase()
        const company = String(r.company_name || '').toLowerCase()
        const email = String(r.email || '').toLowerCase()
        return name.includes(q) || company.includes(q) || email.includes(q)
      })
    }
    if (sortBy === 'created') {
      list.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
    } else if (sortBy === 'created_old') {
      list.sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0))
    } else if (sortBy === 'name') {
      list.sort((a, b) => String(a.contact_name || '').localeCompare(String(b.contact_name || '')))
    } else if (sortBy === 'status') {
      list.sort((a, b) => String(a.status || '').localeCompare(String(b.status || '')))
    }
    return list
  }, [items, searchQuery, sortBy])

  useEffect(() => {
    setPage(1)
  }, [statusFilter, searchQuery, sortBy])

  const pageCount = Math.max(1, Math.ceil(sortedFilteredItems.length / PAGE_SIZE))
  const pagedItems = sortedFilteredItems.slice(
    (Math.min(page, pageCount) - 1) * PAGE_SIZE,
    Math.min(page, pageCount) * PAGE_SIZE,
  )

  const openApprove = (row) => {
    setCompose({
      id: row.id,
      subject_override: settings._previewSubject || '',
      body_override: settings._previewBody || '',
      skip_wa: !row.whatsapp_e164,
      voice_region: row.voice_region || '',
    })
  }

  const openDetail = async (id) => {
    setBusy(true)
    try {
      const data = await apiFetch(`/admin/ai-demo/requests/${id}`)
      setDetail(data)
    } catch (e) {
      alert(e?.message || 'Failed to load detail')
    } finally {
      setBusy(false)
    }
  }

  const sendApprove = async ({ useEdited } = { useEdited: true }) => {
    if (!compose?.id) return
    setBusy(true)
    try {
      const body = {
        skip_wa: Boolean(compose.skip_wa),
        voice_region: compose.voice_region || null,
      }
      if (useEdited) {
        body.subject_override = compose.subject_override || null
        body.body_override = compose.body_override || null
      }
      await apiFetch(`/admin/ai-demo/requests/${compose.id}/approve`, {
        method: 'POST',
        body: JSON.stringify(body),
      })
      setCompose(null)
      setDetail(null)
      await refresh()
    } catch (e) {
      alert(e?.message || 'Approve failed')
    } finally {
      setBusy(false)
    }
  }

  const reject = async (id) => {
    const reason = window.prompt('Reject reason (optional)') || ''
    setBusy(true)
    try {
      await apiFetch(`/admin/ai-demo/requests/${id}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      })
      setDetail(null)
      await refresh()
    } catch (e) {
      alert(e?.message || 'Reject failed')
    } finally {
      setBusy(false)
    }
  }

  const resend = async (id) => {
    setBusy(true)
    try {
      await apiFetch(`/admin/ai-demo/requests/${id}/resend`, { method: 'POST' })
      await refresh()
    } catch (e) {
      alert(e?.message || 'Resend failed')
    } finally {
      setBusy(false)
    }
  }

  const sendManual = async () => {
    if (!manual.email?.trim()) {
      alert('Email is required.')
      return
    }
    setBusy(true)
    try {
      await apiFetch('/admin/ai-demo/requests/manual', {
        method: 'POST',
        body: JSON.stringify({
          ...manual,
          whatsapp: manual.whatsapp || null,
          skip_wa: !manual.whatsapp,
          voice_region: manual.voice_region || null,
        }),
      })
      setManual(emptyManual)
      setTab('inbox')
      await refresh()
    } catch (e) {
      alert(e?.message || 'Send failed')
    } finally {
      setBusy(false)
    }
  }

  const sendBatch = async () => {
    setBusy(true)
    setBatchResult(null)
    try {
      const data = await apiFetch('/admin/ai-demo/requests/batch', {
        method: 'POST',
        body: JSON.stringify({
          emails_text: batchText,
          preferred_language: batchLang,
          message: batchMsg,
          skip_wa: true,
          voice_region: batchRegion || null,
        }),
      })
      setBatchResult(data)
      setBatchText('')
      setTab('inbox')
      await refresh()
    } catch (e) {
      alert(e?.message || 'Batch send failed')
    } finally {
      setBusy(false)
    }
  }

  const saveSettings = async () => {
    setBusy(true)
    try {
      await apiFetch('/admin/ai-demo/settings', {
        method: 'PUT',
        body: JSON.stringify({
          from_email: settings.from_email,
          soft_cap_minutes: Number(settings.soft_cap_minutes) || 7,
          notes: settings.notes || '',
          agent_by_region: settings.agent_by_region || {},
        }),
      })
      await refresh()
    } catch (e) {
      alert(e?.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const provisionDemoAgents = async () => {
    if (
      !window.confirm(
        'Clone interview voice agents into dedicated AI Demo agents (new Telnyx assistants). Interview agents are not changed. Continue?',
      )
    ) {
      return
    }
    setBusy(true)
    try {
      const out = await apiFetch('/admin/ai-demo/agents/duplicate-for-demo', { method: 'POST' })
      const ok = (out?.results || []).filter((r) => r.ok).length
      alert(`AI Demo agents ready: ${ok} market(s) mapped.`)
      await refresh()
    } catch (e) {
      alert(e?.message || 'Could not provision AI Demo agents')
    } finally {
      setBusy(false)
    }
  }

  const setRegionAgent = (code, agentId) => {
    setSettings((s) => {
      const next = { ...(s.agent_by_region || {}) }
      if (!agentId) delete next[code]
      else next[code] = agentId
      return { ...s, agent_by_region: next }
    })
  }

  const agentsForRegion = (code) => {
    if (!agents.length) return []
    if (code === 'DEFAULT') return agents
    const preferred = agents.filter((a) => String(a.accent_region || '').toUpperCase() === code)
    const rest = agents.filter((a) => String(a.accent_region || '').toUpperCase() !== code)
    return [...preferred, ...rest]
  }

  const voiceRegionOptions = useMemo(() => {
    const regions = Array.isArray(settings.regions) ? settings.regions : []
    const map = settings.agent_by_region || {}
    return regions
      .filter((r) => r.code !== 'DEFAULT')
      .map((r) => {
        const agentId = map[r.code]
        const agent = agents.find((a) => a.id === agentId)
        const configured = Boolean(agentId && agent)
        return {
          code: r.code,
          label: configured ? `${r.label} — ${agent.name}` : `${r.label} (not mapped)`,
          configured,
        }
      })
  }, [settings.regions, settings.agent_by_region, agents])

  const VoiceRegionSelect = ({ value, onChange, id, className = 'aid-form-control' }) => (
    <div className="aid-form-group">
      <label className="aid-form-label" htmlFor={id}>
        Voice market
      </label>
      <select id={id} className={className} value={value || ''} onChange={(e) => onChange(e.target.value)}>
        <option value="">Auto from WhatsApp</option>
        {voiceRegionOptions.map((r) => (
          <option key={r.code} value={r.code} disabled={!r.configured}>
            {r.label}
          </option>
        ))}
      </select>
      <span className="aid-form-hint">Uses the agent mapped in Settings for that market.</span>
    </div>
  )

  return (
    <div className="ai-demos-page">
      {!embedded ? (
        <>
          <div className="aid-page-header">
            <div className="aid-header-left">
              <h1 className="aid-page-title">
                <Bot /> AI Demos
              </h1>
              <p className="aid-page-desc">
                Approve requests and send magic-link invites. When a demo completes, a Lead sales task is created in this
                same pipeline.
              </p>
            </div>
            <div className="aid-header-actions">
              <button type="button" className="aid-btn aid-btn-outline aid-btn-sm" onClick={() => refresh()} disabled={loading || busy}>
                <RefreshCw /> Refresh
              </button>
              <button type="button" className="aid-btn aid-btn-primary aid-btn-sm" onClick={() => setTab('send')}>
                <Send /> Send invites
              </button>
            </div>
          </div>
          <LeadSalesPipelineStrip active="demo" />
        </>
      ) : (
        <div className="aid-header-actions" style={{ marginBottom: 12, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="aid-btn aid-btn-outline aid-btn-sm" onClick={() => refresh()} disabled={loading || busy}>
            <RefreshCw /> Refresh
          </button>
          <button type="button" className="aid-btn aid-btn-primary aid-btn-sm" onClick={() => setTab('send')}>
            <Send /> Send invites
          </button>
        </div>
      )}

      {error ? <div className="aid-error">{error}</div> : null}

      <div className="aid-kpi-grid">
        <div className="aid-kpi-card">
          <div className="aid-kpi-icon total">
            <Inbox />
          </div>
          <div className="aid-kpi-content">
            <span className="aid-kpi-number">{stats.total}</span>
            <span className="aid-kpi-label">Total</span>
          </div>
        </div>
        <div className="aid-kpi-card">
          <div className="aid-kpi-icon opened">
            <Mail />
          </div>
          <div className="aid-kpi-content">
            <span className="aid-kpi-number">{stats.opened}</span>
            <span className="aid-kpi-label">Opened</span>
          </div>
        </div>
        <div className="aid-kpi-card">
          <div className="aid-kpi-icon clicked">
            <MousePointer2 />
          </div>
          <div className="aid-kpi-content">
            <span className="aid-kpi-number">{stats.clicked}</span>
            <span className="aid-kpi-label">Clicked</span>
          </div>
        </div>
        <div className="aid-kpi-card">
          <div className="aid-kpi-icon completed">
            <CheckCircle2 />
          </div>
          <div className="aid-kpi-content">
            <span className="aid-kpi-number">{stats.completed}</span>
            <span className="aid-kpi-label">Completed</span>
          </div>
        </div>
      </div>

      <div className="aid-tabs">
        <button type="button" className={`aid-tab${tab === 'inbox' ? ' active' : ''}`} onClick={() => setTab('inbox')}>
          <Inbox /> Inbox
        </button>
        <button type="button" className={`aid-tab${tab === 'send' ? ' active' : ''}`} onClick={() => setTab('send')}>
          <Send /> Send
        </button>
        <button type="button" className={`aid-tab${tab === 'settings' ? ' active' : ''}`} onClick={() => setTab('settings')}>
          <Settings /> Settings
        </button>
      </div>

      {tab === 'settings' && (
        <div className="aid-panel aid-settings-panel">
          <h4>
            <Mic /> Voice agents by market
          </h4>
          <p className="aid-text-muted" style={{ marginBottom: 16 }}>
            Only dedicated AI Demo agents appear here (not interview or survey). Visitors match from WhatsApp country
            (+44 → GB, +61 → AU, +1 → US, +353 → IE, +966 → SA, +20 → EG, +971 → AE). Unmapped markets use Default.
          </p>
          {!agents.length ? (
            <div className="aid-warn-box">
              <TriangleAlert />
              <span>
                No dedicated AI Demo agents yet. Clone them from the interview roster (new Telnyx assistants — interview
                agents stay untouched).
              </span>
            </div>
          ) : null}
          <div style={{ marginBottom: 16 }}>
            <button type="button" className="aid-btn aid-btn-outline" onClick={provisionDemoAgents} disabled={busy}>
              <Bot /> {agents.length ? 'Refresh / re-clone AI Demo agents' : 'Create dedicated AI Demo agents'}
            </button>
          </div>
          {(settings.regions || []).map((r) => (
            <div key={r.code} className="aid-setting-row">
              <label htmlFor={`region-${r.code}`}>{r.label}</label>
              <select
                id={`region-${r.code}`}
                className="aid-form-control"
                value={settings.agent_by_region?.[r.code] || ''}
                onChange={(e) => setRegionAgent(r.code, e.target.value)}
                disabled={!agents.length}
              >
                <option value="">Not set</option>
                {agentsForRegion(r.code).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label || a.name}
                  </option>
                ))}
              </select>
            </div>
          ))}
          <hr className="aid-hr" />
          <div className="aid-setting-row">
            <label htmlFor="from-email">From / reply email</label>
            <input
              id="from-email"
              className="aid-form-control"
              value={settings.from_email}
              onChange={(e) => setSettings((s) => ({ ...s, from_email: e.target.value }))}
              placeholder="hello@voxbulk.com"
            />
          </div>
          <div className="aid-setting-row">
            <label htmlFor="soft-cap">Soft cap (minutes)</label>
            <input
              id="soft-cap"
              className="aid-form-control"
              type="number"
              min={3}
              max={30}
              style={{ maxWidth: 120 }}
              value={settings.soft_cap_minutes}
              onChange={(e) => setSettings((s) => ({ ...s, soft_cap_minutes: e.target.value }))}
            />
          </div>
          <button type="button" className="aid-btn aid-btn-primary" onClick={saveSettings} disabled={busy}>
            <Save /> Save settings
          </button>
        </div>
      )}

      {tab === 'send' && (
        <div className="aid-grid-2col">
          <div className="aid-panel">
            <h4>
              <UserPlus /> Single invite
            </h4>
            <div className="aid-form-group">
              <label className="aid-form-label">Contact name</label>
              <input
                className="aid-form-control"
                value={manual.contact_name}
                onChange={(e) => setManual((m) => ({ ...m, contact_name: e.target.value }))}
                placeholder="John Doe"
              />
            </div>
            <div className="aid-form-group">
              <label className="aid-form-label">Email *</label>
              <input
                className="aid-form-control"
                value={manual.email}
                onChange={(e) => setManual((m) => ({ ...m, email: e.target.value }))}
                placeholder="john@company.com"
              />
            </div>
            <div className="aid-form-group">
              <label className="aid-form-label">Company</label>
              <input
                className="aid-form-control"
                value={manual.company_name}
                onChange={(e) => setManual((m) => ({ ...m, company_name: e.target.value }))}
                placeholder="Acme Inc"
              />
            </div>
            <div className="aid-form-group">
              <label className="aid-form-label">WhatsApp</label>
              <input
                className="aid-form-control"
                value={manual.whatsapp}
                onChange={(e) => setManual((m) => ({ ...m, whatsapp: e.target.value }))}
                placeholder="+44..."
              />
            </div>
            <div className="aid-form-group">
              <label className="aid-form-label">Website</label>
              <input
                className="aid-form-control"
                value={manual.website}
                onChange={(e) => setManual((m) => ({ ...m, website: e.target.value }))}
                placeholder="https://voxbulk.com"
              />
            </div>
            <div className="aid-form-group">
              <label className="aid-form-label">Language</label>
              <select
                className="aid-form-control"
                value={manual.preferred_language}
                onChange={(e) => setManual((m) => ({ ...m, preferred_language: e.target.value }))}
              >
                {LANGS.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.label}
                  </option>
                ))}
              </select>
            </div>
            <VoiceRegionSelect
              id="manual-voice-region"
              value={manual.voice_region}
              onChange={(v) => setManual((m) => ({ ...m, voice_region: v }))}
            />
            <div className="aid-form-group">
              <label className="aid-form-label">Optional message</label>
              <textarea
                className="aid-form-control"
                rows={2}
                value={manual.message}
                onChange={(e) => setManual((m) => ({ ...m, message: e.target.value }))}
              />
            </div>
            <button type="button" className="aid-btn aid-btn-primary" disabled={busy || !manual.email} onClick={sendManual}>
              <Send /> Send invite
            </button>
          </div>

          <div className="aid-panel">
            <h4>
              <Users /> Multi-email batch (max 50)
            </h4>
            <div className="aid-form-group">
              <label className="aid-form-label">Email list</label>
              <textarea
                className="aid-form-control"
                rows={4}
                style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12 }}
                placeholder={'one@company.com\ntwo@company.com\nor comma-separated'}
                value={batchText}
                onChange={(e) => setBatchText(e.target.value)}
              />
            </div>
            <div className="aid-form-group">
              <label className="aid-form-label">Language</label>
              <select className="aid-form-control" value={batchLang} onChange={(e) => setBatchLang(e.target.value)}>
                {LANGS.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.label}
                  </option>
                ))}
              </select>
            </div>
            <VoiceRegionSelect id="batch-voice-region" value={batchRegion} onChange={setBatchRegion} />
            <div className="aid-form-group">
              <label className="aid-form-label">Optional note</label>
              <input className="aid-form-control" value={batchMsg} onChange={(e) => setBatchMsg(e.target.value)} placeholder="context" />
            </div>
            <button type="button" className="aid-btn aid-btn-primary" disabled={busy || !batchText.trim()} onClick={sendBatch}>
              <Send /> Send batch
            </button>
            {batchResult ? (
              <div className="aid-batch-result">
                Sent {batchResult.sent}, failed {batchResult.failed}
                {batchResult.errors?.length ? (
                  <ul>
                    {batchResult.errors.map((e) => (
                      <li key={e.email}>
                        {e.email}: {e.error}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      )}

      {tab === 'inbox' && (
        <>
          <div className="aid-toolbar">
            <div className="aid-filters">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.value || 'all'}
                  type="button"
                  className={`aid-filter-chip${statusFilter === f.value ? ' active' : ''}`}
                  onClick={() => setStatusFilter(f.value)}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <div className="aid-search-box">
              <Search />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search name or company..."
              />
            </div>
            <select className="aid-sort-select" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="created">Sort by date (newest)</option>
              <option value="created_old">Sort by date (oldest)</option>
              <option value="name">Sort by name</option>
              <option value="status">Sort by status</option>
            </select>
          </div>

          <div className="aid-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Contact</th>
                  <th>Tracking</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td colSpan={6} className="aid-empty-state">
                      Loading…
                    </td>
                  </tr>
                )}
                {!loading && pagedItems.length === 0 && sortedFilteredItems.length === 0 && (
                  <tr>
                    <td colSpan={6} className="aid-empty-state">
                      <Inbox style={{ display: 'inline', marginRight: 8, verticalAlign: 'middle' }} size={16} />
                      No demos match
                    </td>
                  </tr>
                )}
                {!loading &&
                  pagedItems.map((row) => (
                    <tr key={row.id}>
                      <td style={{ whiteSpace: 'nowrap' }}>{fmt(row.created_at)}</td>
                      <td>
                        <div className="aid-contact-cell">
                          <span className="aid-contact-name">{row.contact_name}</span>
                          <span className="aid-contact-email">{row.email}</span>
                          <span className="aid-contact-company">{row.company_name}</span>
                        </div>
                      </td>
                      <td>
                        <div className="aid-tracking-badges">
                          {row.email_sent_at ? (
                            <span className="aid-tracking-badge sent">
                              <Mail /> sent
                            </span>
                          ) : (
                            <span className="aid-tracking-badge muted">sent —</span>
                          )}
                          {(row.open_count || 0) > 0 ? (
                            <span className="aid-tracking-badge opened">
                              <Eye /> {row.open_count}
                            </span>
                          ) : null}
                          {(row.click_count || 0) > 0 ? (
                            <span className="aid-tracking-badge clicked">
                              <MousePointer2 /> {row.click_count}
                            </span>
                          ) : null}
                          {row.demo_completed_at || row.status === 'completed' ? (
                            <span className="aid-tracking-badge done">
                              <CheckCircle2 /> done
                            </span>
                          ) : null}
                        </div>
                      </td>
                      <td>
                        <span className="aid-badge">{row.source || '—'}</span>
                      </td>
                      <td>
                        <span className={`aid-badge ${statusBadgeClass(row.status)}`}>{row.status}</span>
                      </td>
                      <td>
                        <div className="aid-actions-cell">
                          <span className="aid-action-group">
                            <button
                              type="button"
                              className="aid-action-icon detail"
                              title="Detail"
                              disabled={busy}
                              onClick={() => openDetail(row.id)}
                            >
                              <Info />
                            </button>
                          </span>
                          {row.status === 'pending' ? (
                            <span className="aid-action-group">
                              <button
                                type="button"
                                className="aid-action-icon approve"
                                title="Approve"
                                disabled={busy}
                                onClick={() => openApprove(row)}
                              >
                                <Check />
                              </button>
                              <button
                                type="button"
                                className="aid-action-icon reject"
                                title="Reject"
                                disabled={busy}
                                onClick={() => reject(row.id)}
                              >
                                <X />
                              </button>
                            </span>
                          ) : null}
                          {['approved', 'active'].includes(row.status) && !row.demo_completed_at ? (
                            <span className="aid-action-group">
                              <button
                                type="button"
                                className="aid-action-icon resend"
                                title="Resend"
                                disabled={busy}
                                onClick={() => resend(row.id)}
                              >
                                <Redo2 />
                              </button>
                            </span>
                          ) : null}
                          {row.frontpage_lead_call_id || row.lead_sales_task_id ? (
                            <span className="aid-action-group">
                              {row.frontpage_lead_call_id ? (
                                <Link className="aid-action-icon link" to="/marketing/leads/inbound" title="Inbound calls">
                                  <Link2 />
                                </Link>
                              ) : null}
                              {row.lead_sales_task_id ? (
                                <Link
                                  className="aid-action-icon link"
                                  to={leadSalesListUrl(row.lead_sales_task_id)}
                                  title="Open sales task"
                                >
                                  <ListTodo />
                                </Link>
                              ) : null}
                            </span>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
            {!loading && sortedFilteredItems.length ? (
              <TablePagination
                page={Math.min(page, pageCount)}
                pageCount={pageCount}
                total={sortedFilteredItems.length}
                onPrev={() => setPage((p) => Math.max(1, p - 1))}
                onNext={() => setPage((p) => Math.min(pageCount, p + 1))}
              />
            ) : null}
          </div>
        </>
      )}

      {compose ? (
        <div className="aid-modal-overlay" role="dialog" aria-modal="true">
          <div className="aid-modal">
            <div className="aid-modal-header">
              <h2 className="aid-modal-title">
                <CheckCircle2 style={{ color: '#0b1a2f' }} /> Approve & send
              </h2>
              <button type="button" className="aid-modal-close" onClick={() => setCompose(null)} aria-label="Close">
                ×
              </button>
            </div>
            <div className="aid-form-group">
              <label className="aid-form-label">Subject</label>
              <input
                className="aid-form-control"
                value={compose.subject_override}
                onChange={(e) => setCompose((c) => ({ ...c, subject_override: e.target.value }))}
              />
            </div>
            <div className="aid-form-group">
              <label className="aid-form-label">Body</label>
              <textarea
                className="aid-form-control"
                rows={8}
                style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12, minHeight: 200 }}
                value={compose.body_override}
                onChange={(e) => setCompose((c) => ({ ...c, body_override: e.target.value }))}
              />
            </div>
            <div className="aid-form-group aid-inline-check">
              <input
                type="checkbox"
                id="skip-wa"
                checked={Boolean(compose.skip_wa)}
                onChange={(e) => setCompose((c) => ({ ...c, skip_wa: e.target.checked }))}
              />
              <label htmlFor="skip-wa">Skip WhatsApp notice</label>
            </div>
            <VoiceRegionSelect
              id="approve-voice-region"
              value={compose.voice_region}
              onChange={(v) => setCompose((c) => ({ ...c, voice_region: v }))}
            />
            <div className="aid-modal-footer">
              <button type="button" className="aid-btn aid-btn-outline" onClick={() => setCompose(null)}>
                Cancel
              </button>
              <button type="button" className="aid-btn aid-btn-outline" disabled={busy} onClick={() => sendApprove({ useEdited: false })}>
                Send directly
              </button>
              <button type="button" className="aid-btn aid-btn-primary" disabled={busy} onClick={() => sendApprove({ useEdited: true })}>
                Send edited
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {detail ? (
        <div className="aid-modal-overlay" role="dialog" aria-modal="true">
          <div className="aid-modal aid-modal-lg">
            <div className="aid-modal-header">
              <h2 className="aid-modal-title">
                <UserCircle2 style={{ color: '#0b1a2f' }} /> {detail.contact_name}
              </h2>
              <button type="button" className="aid-modal-close" onClick={() => setDetail(null)} aria-label="Close">
                ×
              </button>
            </div>

            <div className="aid-detail-grid">
              <div>
                <span className="aid-detail-label">
                  <Mail /> Email
                </span>
                <div className="aid-detail-value">{detail.email}</div>
              </div>
              <div>
                <span className="aid-detail-label">
                  <Phone /> WhatsApp
                </span>
                <div className="aid-detail-value">{detail.whatsapp_e164 || '—'}</div>
              </div>
              <div>
                <span className="aid-detail-label">
                  <Globe /> Website
                </span>
                <div className="aid-detail-value">{detail.website || '—'}</div>
              </div>
              <div>
                <span className="aid-detail-label">
                  <Languages /> Language
                </span>
                <div className="aid-detail-value">{detail.preferred_language || 'en'}</div>
              </div>
              <div className="aid-detail-span">
                <span className="aid-detail-label">
                  <MessageSquare /> Message / note
                </span>
                <div className="aid-detail-value">{detail.message || '—'}</div>
              </div>
              <div>
                <span className="aid-detail-label">Status</span>
                <div className="aid-detail-value">
                  <span className={`aid-badge ${statusBadgeClass(detail.status)}`}>{detail.status}</span>
                </div>
              </div>
              <div>
                <span className="aid-detail-label">Sent</span>
                <div className="aid-detail-value">{fmt(detail.email_sent_at)}</div>
              </div>
              <div>
                <span className="aid-detail-label">Opened (count)</span>
                <div className="aid-detail-value">
                  {detail.open_count || 0}
                  {detail.opened_at ? ` · ${fmt(detail.opened_at)}` : ''}
                </div>
              </div>
              <div>
                <span className="aid-detail-label">Clicked (count)</span>
                <div className="aid-detail-value">
                  {detail.click_count || 0}
                  {detail.link_clicked_at ? ` · ${fmt(detail.link_clicked_at)}` : ''}
                </div>
              </div>
              <div>
                <span className="aid-detail-label">Completed</span>
                <div className="aid-detail-value">{fmt(detail.demo_completed_at)}</div>
              </div>

              {detail.lead ? (
                <div className="aid-detail-span">
                  <span className="aid-detail-label">Lead outcome</span>
                  <div className="aid-detail-value" style={{ marginTop: 6 }}>
                    <div>
                      Recommendation: <strong>{detail.lead.recommendation || '—'}</strong> · Sentiment:{' '}
                      {detail.lead.sentiment || '—'}
                    </div>
                    <div style={{ marginTop: 4 }}>Interest: {detail.lead.interest_summary || '—'}</div>
                    <div style={{ marginTop: 4 }}>
                      Services: {(detail.lead.services_explored || []).join(', ') || '—'}
                    </div>
                    {detail.lead.transcript_text ? (
                      <>
                        <div className="aid-detail-label" style={{ marginTop: 10 }}>
                          Transcript
                        </div>
                        <div className="aid-transcript-box">{detail.lead.transcript_text}</div>
                      </>
                    ) : null}
                  </div>
                </div>
              ) : (
                <div className="aid-detail-span">
                  <span className="aid-detail-label">Lead outcome</span>
                  <div className="aid-detail-value">—</div>
                </div>
              )}

              <div className="aid-detail-span">
                <span className="aid-detail-label">Sessions</span>
                {(detail.sessions || []).length === 0 ? (
                  <div className="aid-text-muted" style={{ marginTop: 8 }}>
                    No sessions yet
                  </div>
                ) : (
                  <div style={{ marginTop: 8 }}>
                    {(detail.sessions || []).map((s) => (
                      <div key={s.id} className="aid-session-item">
                        <div className="aid-flex-between">
                          <span>
                            <strong>{s.status}</strong> · {s.active_service_code || 'no KB yet'}
                          </span>
                          <span className="aid-text-muted">
                            {fmt(s.started_at)} – {fmt(s.ended_at)}
                          </span>
                        </div>
                        <div className="aid-text-muted">Duration: {s.duration_seconds || 0}s</div>
                        <div className="aid-transcript-box" style={{ maxHeight: 80 }}>
                          {s.transcript_log || 'No transcript'}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="aid-detail-actions">
              {detail.status === 'pending' ? (
                <>
                  <button
                    type="button"
                    className="aid-btn aid-btn-outline aid-btn-sm"
                    disabled={busy}
                    onClick={() => {
                      openApprove(detail)
                      setDetail(null)
                    }}
                  >
                    <Check /> Approve
                  </button>
                  <button
                    type="button"
                    className="aid-btn aid-btn-outline aid-btn-sm"
                    disabled={busy}
                    onClick={() => reject(detail.id)}
                  >
                    <X /> Reject
                  </button>
                </>
              ) : null}
              {detail.frontpage_lead_call_id ? (
                <Link className="aid-btn aid-btn-outline aid-btn-sm" to="/marketing/leads/inbound">
                  <Link2 /> Inbound calls
                </Link>
              ) : null}
              {detail.lead_sales_task_id ? (
                <Link className="aid-btn aid-btn-outline aid-btn-sm" to={leadSalesListUrl(detail.lead_sales_task_id)}>
                  <ListTodo /> Sales task
                </Link>
              ) : null}
              <button type="button" className="aid-btn aid-btn-primary aid-btn-sm" onClick={() => setDetail(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
