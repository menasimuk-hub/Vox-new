import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch, apiFetchBlob, apiUpload } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import { Pill } from '@/components/ui/Badge'
import './ai-team.css'

const CSV_MAP_FIELDS = [
  { key: 'email', label: 'Email', required: true },
  { key: 'first_name', label: 'First name' },
  { key: 'last_name', label: 'Last name' },
  { key: 'job_title', label: 'Job title' },
  { key: 'company_name', label: 'Company' },
  { key: 'sector', label: 'Sector' },
  { key: 'country_code', label: 'Country' },
]

function guessCsvMapping(headers) {
  const norm = (h) => String(h || '').toLowerCase().replace(/[^a-z0-9]+/g, '_')
  const map = {}
  const rules = [
    ['email', ['email', 'e_mail', 'email_address']],
    ['first_name', ['first_name', 'firstname', 'first', 'given_name']],
    ['last_name', ['last_name', 'lastname', 'last', 'surname', 'family_name']],
    ['job_title', ['job_title', 'title', 'role', 'position']],
    ['company_name', ['company', 'company_name', 'organization', 'org', 'account_name']],
    ['sector', ['sector', 'industry', 'vertical']],
    ['country_code', ['country', 'country_code', 'location']],
  ]
  for (const h of headers) {
    const n = norm(h)
    for (const [field, keys] of rules) {
      if (keys.some((k) => n === k || n.includes(k))) {
        if (!map[field]) map[field] = h
      }
    }
  }
  return map
}

const TABS = [
  { id: 'queue', label: 'Approval queue', icon: 'ti-mail' },
  { id: 'tracking', label: 'Sent / Tracking', icon: 'ti-eye' },
  { id: 'prospects', label: 'Prospects', icon: 'ti-users' },
  { id: 'replies', label: 'Replies', icon: 'ti-messages' },
  { id: 'search', label: 'Search & email', icon: 'ti-adjustments-horizontal' },
  { id: 'promo', label: 'Promo codes', icon: 'ti-tag' },
  { id: 'analytics', label: 'Analytics', icon: 'ti-chart-bar' },
  { id: 'api', label: 'API settings', icon: 'ti-settings' },
]

function initials(name) {
  const parts = String(name || '?').trim().split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return String(name || '?').slice(0, 2).toUpperCase()
}

function sectorClass(sector) {
  const s = String(sector || '').toLowerCase()
  if (s.includes('auto')) return 'b-auto'
  if (s.includes('prop') || s.includes('estate')) return 'b-prop'
  if (s.includes('dent')) return 'b-dent'
  if (s.includes('rec')) return 'b-rec'
  return 'b-auto'
}

function statusBadge(status) {
  const map = {
    pending: 'b-pending',
    sent: 'b-sent',
    opened: 'b-opened',
    replied: 'b-replied',
    converted: 'b-converted',
    rejected: 'b-rejected',
    new: 'b-pending',
  }
  return map[status] || 'b-pending'
}

function timeAgo(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const mins = Math.floor((Date.now() - d.getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 48) return `${hrs}h ago`
  return d.toLocaleDateString()
}

export default function AiTeam() {
  const [tab, setTab] = useState('queue')
  const [howtoOpen, setHowtoOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [banner, setBanner] = useState(null)
  const [stats, setStats] = useState({})
  const [settings, setSettings] = useState({})
  const [queue, setQueue] = useState([])
  const [prospects, setProspects] = useState([])
  const [threads, setThreads] = useState([])
  const [promoCodes, setPromoCodes] = useState([])
  const [analytics, setAnalytics] = useState(null)
  const [drawer, setDrawer] = useState(null)
  const [drawerMessages, setDrawerMessages] = useState([])
  const [selectedThread, setSelectedThread] = useState(null)
  const [threadDetail, setThreadDetail] = useState(null)
  const [replyText, setReplyText] = useState('')
  const [editDraft, setEditDraft] = useState(null)
  const [apolloKey, setApolloKey] = useState('')
  const [resendKey, setResendKey] = useState('')
  const [smtpPassword, setSmtpPassword] = useState('')
  const [resendTestEmail, setResendTestEmail] = useState('')
  const [searchTestEmail, setSearchTestEmail] = useState('')
  const [pasteEmails, setPasteEmails] = useState('')
  const [pasteCompany, setPasteCompany] = useState('')
  const [pasteSector, setPasteSector] = useState('expo')
  const [prospectSource, setProspectSource] = useState('')
  const [connectionChecks, setConnectionChecks] = useState(null)
  const [csvFile, setCsvFile] = useState(null)
  const [csvDrag, setCsvDrag] = useState(false)
  const [csvHeaders, setCsvHeaders] = useState([])
  const [csvPreviewRows, setCsvPreviewRows] = useState([])
  const [csvTotal, setCsvTotal] = useState(0)
  const [csvMapping, setCsvMapping] = useState({})
  const [emailPreview, setEmailPreview] = useState(null)
  const [templatePreview, setTemplatePreview] = useState(null)
  const [queueView, setQueueView] = useState('cards') // cards | list
  const [trackingFilter, setTrackingFilter] = useState('engagement') // engagement | sent | opened | replied
  const [trackingRows, setTrackingRows] = useState([])

  const showBanner = (type, text) => {
    setBanner({ type, text })
    window.setTimeout(() => setBanner(null), 5000)
  }

  const loadDashboard = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiFetch('/admin/ai-team/dashboard')
      setStats(data.stats || {})
      setSettings(data.settings || {})
      setQueue(data.queue || [])
    } catch (e) {
      showBanner('err', e?.message || 'Could not load AI Team dashboard')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadProspects = useCallback(async (sourceFilter) => {
    try {
      const qs = sourceFilter ? `?source=${encodeURIComponent(sourceFilter)}` : ''
      const data = await apiFetch(`/admin/ai-team/prospects${qs}`)
      setProspects(data.prospects || [])
    } catch (e) {
      showBanner('err', e?.message || 'Could not load prospects')
    }
  }, [])

  const loadTracking = useCallback(async (filter) => {
    try {
      const status = filter || 'engagement'
      const data = await apiFetch(`/admin/ai-team/prospects?status=${encodeURIComponent(status)}`)
      setTrackingRows(data.prospects || [])
    } catch (e) {
      showBanner('err', e?.message || 'Could not load tracking')
    }
  }, [])


  const loadReplies = useCallback(async () => {
    try {
      const data = await apiFetch('/admin/ai-team/replies')
      setThreads(data.threads || [])
    } catch (e) {
      showBanner('err', e?.message || 'Could not load replies')
    }
  }, [])

  const loadPromo = useCallback(async () => {
    try {
      const data = await apiFetch('/admin/ai-team/promo-codes')
      setPromoCodes(data.promo_codes || [])
    } catch (e) {
      showBanner('err', e?.message || 'Could not load promo codes')
    }
  }, [])

  const loadAnalytics = useCallback(async () => {
    try {
      const data = await apiFetch('/admin/ai-team/analytics')
      setAnalytics(data)
    } catch (e) {
      showBanner('err', e?.message || 'Could not load analytics')
    }
  }, [])

  useEffect(() => {
    loadDashboard()
  }, [loadDashboard])

  useEffect(() => {
    if (tab === 'prospects') loadProspects(prospectSource)
    if (tab === 'tracking') loadTracking(trackingFilter)
    if (tab === 'replies') loadReplies()
    if (tab === 'promo') loadPromo()
    if (tab === 'analytics') loadAnalytics()
  }, [tab, prospectSource, trackingFilter, loadProspects, loadTracking, loadReplies, loadPromo, loadAnalytics])

  const openDrawer = async (prospect) => {
    setDrawer(prospect)
    try {
      const data = await apiFetch(`/admin/ai-team/prospects/${prospect.id}`)
      setDrawerMessages(data.messages || [])
    } catch {
      setDrawerMessages([])
    }
  }

  const selectThread = async (thread) => {
    setSelectedThread(thread)
    try {
      const data = await apiFetch(`/admin/ai-team/prospects/${thread.id}`)
      setThreadDetail(data)
    } catch (e) {
      showBanner('err', e?.message || 'Could not load thread')
    }
  }

  const act = async (key, fn) => {
    setBusy(key)
    try {
      await fn()
      await loadDashboard()
      if (tab === 'prospects') await loadProspects(prospectSource)
      if (tab === 'tracking') await loadTracking(trackingFilter)
      if (tab === 'replies') await loadReplies()
    } catch (e) {
      showBanner('err', e?.message || 'Action failed')
    } finally {
      setBusy('')
    }
  }

  const exportProspects = async (status, filename) => {
    await act(`export-${status}`, async () => {
      const blob = await apiFetchBlob(`/admin/ai-team/prospects/export.csv?status=${encodeURIComponent(status)}`)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename || `ai-team-${status}.csv`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      showBanner('ok', 'Excel/CSV download started')
    })
  }

  const deleteProspect = async (prospectId) => {
    if (!window.confirm('Permanently delete this prospect and their messages?')) return
    await act(`del-${prospectId}`, async () => {
      await apiFetch(`/admin/ai-team/prospects/${prospectId}`, { method: 'DELETE' })
      setEmailPreview((prev) => (prev?.prospect?.id === prospectId ? null : prev))
      setDrawer((prev) => (prev?.id === prospectId ? null : prev))
      showBanner('ok', 'Prospect deleted')
    })
  }

  const purgeQueue = async () => {
    if (!queue.length) {
      showBanner('err', 'Approval queue is empty')
      return
    }
    if (!window.confirm(`Permanently delete all ${queue.length} draft(s) in the approval queue? This cannot be undone.`)) return
    await act('purge-queue', async () => {
      const data = await apiFetch('/admin/ai-team/prospects', {
        method: 'DELETE',
        body: JSON.stringify({ status: 'queue' }),
      })
      showBanner('ok', data.message || `Deleted ${data.deleted || 0} prospect(s)`)
    })
  }

  const saveSettings = async (partial = {}) => {
    await act('save-settings', async () => {
      const body = {
        ...settings,
        ...partial,
        apollo_api_key: apolloKey || undefined,
        resend_api_key: resendKey || undefined,
        smtp_password: smtpPassword || undefined,
      }
      const data = await apiFetch('/admin/ai-team/settings', { method: 'PUT', body: JSON.stringify(body) })
      setSettings(data.settings || {})
      setApolloKey('')
      setResendKey('')
      setSmtpPassword('')
      showBanner('ok', 'Settings saved')
    })
  }

  const parseCsvFile = async (file) => {
    if (!file) return
    setCsvFile(file)
    const fd = new FormData()
    fd.append('file', file)
    const data = await apiUpload('/admin/ai-team/import/csv/preview', fd)
    setCsvHeaders(data.headers || [])
    setCsvPreviewRows(data.preview_rows || [])
    setCsvTotal(data.total_rows || 0)
    setCsvMapping(guessCsvMapping(data.headers || []))
  }

  const importCsv = async () => {
    if (!csvFile) {
      showBanner('err', 'Choose a CSV file first')
      return
    }
    if (!csvMapping.email) {
      showBanner('err', 'Map the email column before importing')
      return
    }
    await act('csv-import', async () => {
      const fd = new FormData()
      fd.append('file', csvFile)
      fd.append('mapping', JSON.stringify(csvMapping))
      const data = await apiUpload('/admin/ai-team/import/csv', fd)
      showBanner('ok', `Imported ${data.created || 0} prospects (${data.skipped || 0} skipped)`)
      setCsvFile(null)
      setCsvHeaders([])
      setCsvPreviewRows([])
      await loadDashboard()
    })
  }

  const importPasteEmails = async () => {
    if (!pasteEmails.trim()) {
      showBanner('err', 'Paste at least one email address')
      return
    }
    await act('paste-import', async () => {
      const data = await apiFetch('/admin/ai-team/import/emails', {
        method: 'POST',
        body: JSON.stringify({
          emails: pasteEmails,
          company_name: pasteCompany || undefined,
          sector: pasteSector || undefined,
        }),
      })
      showBanner('ok', `Imported ${data.created || 0} emails (${data.skipped || 0} skipped) — drafts in approval queue`)
      setPasteEmails('')
      setTab('queue')
    })
  }

  const runTestAll = async () => {
    await act('test-all', async () => {
      const data = await apiFetch('/admin/ai-team/test/all', {
        method: 'POST',
        body: JSON.stringify({
          ...settings,
          smtp_password: smtpPassword || undefined,
          to_email: resendTestEmail || searchTestEmail || undefined,
        }),
      })
      setConnectionChecks(data.checks || [])
      showBanner(data.ok ? 'ok' : 'err', data.ok ? 'All critical connections OK' : 'Some connections failed — see checklist')
    })
  }

  const openProspectPreview = async (prospect) => {
    try {
      const data = await apiFetch(`/admin/ai-team/prospects/${prospect.id}/email-preview`)
      setEmailPreview({ prospect, ...data })
    } catch (e) {
      showBanner('err', e?.message || 'Could not load email preview')
    }
  }

  const openTemplatePreview = async () => {
    try {
      const data = await apiFetch('/admin/ai-team/template/preview', {
        method: 'POST',
        body: JSON.stringify({ template: settings.email_html_template, use_sample: true }),
      })
      setTemplatePreview(data)
    } catch (e) {
      showBanner('err', e?.message || 'Could not render template preview')
    }
  }

  const sendTestTemplate = async (toEmail, prospectId) => {
    if (!toEmail?.trim()) {
      showBanner('err', 'Enter your email address for the test')
      return
    }
    await act('test-template', async () => {
      await apiFetch('/admin/ai-team/test/template-email', {
        method: 'POST',
        body: JSON.stringify({ to_email: toEmail.trim(), prospect_id: prospectId || undefined }),
      })
      showBanner('ok', `Test email sent to ${toEmail.trim()}`)
    })
  }

  const ProspectCard = ({ p, showActions = true }) => (
    <div className="ait-pcard" key={p.id}>
      <div className="ait-pcard-top">
        <div className="ait-avatar b-prop">{initials(p.full_name || p.email)}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
            <strong>{p.full_name || p.email}</strong>
            <span className={`ait-badge ${sectorClass(p.sector)}`}>{p.sector || 'General'}</span>
            <span className={`ait-badge ${statusBadge(p.status)}`}>{p.status}</span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--ait-text3)', marginTop: 2 }}>
            {[p.job_title, p.company_name, p.email, p.country_code].filter(Boolean).join(' · ')}
          </div>
          <div style={{ fontSize: 12, marginTop: 6 }}>
            Match <strong style={{ color: p.match_score >= 80 ? 'var(--ait-green)' : 'var(--ait-amber)' }}>{p.match_score ?? '—'}</strong>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          {p.promo_code && <div className="ait-promo-pill">{p.promo_code}</div>}
          <div style={{ fontSize: 11, color: 'var(--ait-text3)', marginTop: 4 }}>{p.source || '—'}</div>
        </div>
      </div>
          {(p.draft_subject || p.draft_body) && (
        <div className="ait-pcard-body">
          <div style={{ fontWeight: 600, marginBottom: 4 }}>{p.draft_subject || '(no subject)'}</div>
          {p.draft_body && <div className="ait-email-snippet">{p.draft_body}</div>}
          {showActions && (
            <div className="ait-btn-row">
              <Button size="sm" variant="outline" onClick={() => openProspectPreview(p)}>
                View email
              </Button>
              <Button size="sm" variant="success" disabled={busy === p.id}
                onClick={() => act(p.id, () => apiFetch(`/admin/ai-team/prospects/${p.id}/approve`, { method: 'POST' }))}>
                Approve & send
              </Button>
              <Button size="sm" variant="outline" onClick={() => setEditDraft({ id: p.id, subject: p.draft_subject, body: p.draft_body })}>Edit</Button>
              <Button size="sm" variant="outline" disabled={busy === `reg-${p.id}`}
                onClick={() => act(`reg-${p.id}`, () => apiFetch(`/admin/ai-team/prospects/${p.id}/regenerate`, { method: 'POST' }))}>
                Regenerate
              </Button>
              <Button size="sm" variant="outline" disabled={busy === `rej-${p.id}`}
                onClick={() => act(`rej-${p.id}`, () => apiFetch(`/admin/ai-team/prospects/${p.id}/reject`, { method: 'POST' }))}>
                Reject
              </Button>
              <Button size="sm" variant="destructive" disabled={busy === `del-${p.id}`}
                onClick={() => deleteProspect(p.id)}>
                Delete
              </Button>
              <span style={{ fontSize: 11, color: 'var(--ait-text3)', marginLeft: 'auto' }}>
                {timeAgo(p.drafted_at)} · <Button size="sm" variant="ghost" onClick={() => openDrawer(p)}>Profile →</Button>
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )

  if (loading && !settings.search_sector && !settings.from_email) {
    return (
      <div className="ai-team-page" style={{ padding: 24 }}>
        <div className="muted">Loading AI Team…</div>
      </div>
    )
  }

  return (
    <div className="ai-team-page">
      <div className="ait-topbar">
        <div className="ait-topbar-left">
          <div className="ait-logo-mark">AI</div>
          <div>
            <div className="ait-page-title">AI Team</div>
            <div className="ait-page-sub">Scrape → draft → approve → send → track opens & replies</div>
          </div>
          <div className="ait-sep" />
          <div className="ait-agent-pill">
            <span className="ait-pulse" />
            {settings.agent_paused ? 'Paused' : 'Live'}
          </div>
        </div>
        <div className="ait-topbar-right">
          <Button variant="ghost" size="sm" onClick={() => setHowtoOpen(true)}>
            How to use
          </Button>
          <Button variant="ghost" size="sm" disabled={!!busy}
            onClick={() => act('run', () => apiFetch('/admin/ai-team/agent/run', { method: 'POST' }))}>
            Run agent
          </Button>
          <Button size="sm" disabled={!!busy}
            onClick={() => act('search', () => apiFetch('/admin/ai-team/search', { method: 'POST', body: JSON.stringify({ preview: false }) }))}>
            New search
          </Button>
        </div>
      </div>

      {banner && (
        <div className={`ait-msg-banner ${banner.type}`} style={{ marginTop: 8 }}>{banner.text}</div>
      )}

      <div className="ait-stats">
        <div className="ait-stat"><div className="ait-stat-lbl">Pending approval</div><div className="ait-stat-val" style={{ color: 'var(--ait-amber)' }}>{stats.pending_approval || 0}</div></div>
        <div className="ait-stat"><div className="ait-stat-lbl">Sent this week</div><div className="ait-stat-val">{stats.sent_this_week || 0}</div></div>
        <div className="ait-stat"><div className="ait-stat-lbl">Open rate</div><div className="ait-stat-val" style={{ color: 'var(--ait-green)' }}>{stats.open_rate || 0}%</div></div>
        <div className="ait-stat"><div className="ait-stat-lbl">Reply rate</div><div className="ait-stat-val" style={{ color: 'var(--ait-blue)' }}>{stats.reply_rate || 0}%</div></div>
        <div className="ait-stat"><div className="ait-stat-lbl">Promo used</div><div className="ait-stat-val" style={{ color: 'var(--ait-amber)' }}>{stats.promo_used || 0}</div></div>
        <div className="ait-stat"><div className="ait-stat-lbl">Converted</div><div className="ait-stat-val" style={{ color: 'var(--ait-green)' }}>{stats.converted || 0}</div></div>
      </div>

      <div className="ait-tabs">
        {TABS.map((t) => (
          <button key={t.id} type="button" className={`ait-tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
            <i className={`ti ${t.icon}`} style={{ fontSize: 12 }} />
            {t.label}
            {t.id === 'queue' && (stats.pending_approval > 0 || queue.length > 0) && (
              <span className="ait-tab-badge">{stats.pending_approval || queue.length}</span>
            )}
            {t.id === 'replies' && stats.replied_count > 0 && <span className="ait-tab-badge">{stats.replied_count}</span>}
          </button>
        ))}
      </div>

      <div className="ait-content">
        {tab === 'queue' && (
          <>
            <div className="ait-toolbar">
              <div className="ait-toolbar-left">
                <span className="ait-toolbar-meta">{queue.length} awaiting approval</span>
                <div className="ait-seg" role="group" aria-label="Queue view">
                  <button type="button" className={queueView === 'cards' ? 'active' : ''} onClick={() => setQueueView('cards')}>Cards</button>
                  <button type="button" className={queueView === 'list' ? 'active' : ''} onClick={() => setQueueView('list')}>List</button>
                </div>
              </div>
              <div className="ait-toolbar-right">
                <Button size="sm" variant="outline" disabled={!queue.length || !!busy}
                  onClick={() => exportProspects('queue', 'ai-team-approval-queue.csv')}>
                  Export Excel
                </Button>
                <Button size="sm" variant="destructive" disabled={!queue.length || busy === 'purge-queue'}
                  onClick={purgeQueue}>
                  Delete all
                </Button>
                <Button size="sm" disabled={!queue.length || !!busy}
                  onClick={() => act('approve-all', () => apiFetch('/admin/ai-team/prospects/approve-all', { method: 'POST' }))}>
                  Approve & send all ({queue.length})
                </Button>
              </div>
            </div>
            {queue.length === 0 ? (
              <div className="ait-empty">
                <strong>No drafts in the queue</strong>
                Scrape an expo directory (Apify tab), import emails, or run Apollo search — drafts land here for approval before send.
              </div>
            ) : queueView === 'list' ? (
              <div className="ait-card">
                <div className="ait-table-wrap">
                  <table className="ait-tbl">
                    <thead>
                      <tr>
                        <th>Prospect</th>
                        <th>Company</th>
                        <th>Subject</th>
                        <th>Promo</th>
                        <th>Drafted</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {queue.map((p) => (
                        <tr key={p.id}>
                          <td>
                            <strong>{p.full_name || p.email}</strong>
                            <div style={{ fontSize: 11, color: 'var(--ait-text3)' }}>{p.email}</div>
                          </td>
                          <td>{p.company_name || '—'}</td>
                          <td className="ait-ellipsis" title={p.draft_subject || ''}>{p.draft_subject || '—'}</td>
                          <td>{p.promo_code ? <span className="ait-promo-pill">{p.promo_code}</span> : '—'}</td>
                          <td style={{ fontSize: 12, color: 'var(--ait-text3)' }}>{timeAgo(p.drafted_at)}</td>
                          <td>
                            <div className="ait-btn-row" style={{ marginTop: 0, justifyContent: 'flex-end' }}>
                              <Button size="sm" variant="ghost" onClick={() => openProspectPreview(p)}>View</Button>
                              <Button size="sm" variant="success" disabled={busy === p.id}
                                onClick={() => act(p.id, () => apiFetch(`/admin/ai-team/prospects/${p.id}/approve`, { method: 'POST' }))}>
                                Send
                              </Button>
                              <Button size="sm" variant="destructive" disabled={busy === `del-${p.id}`}
                                onClick={() => deleteProspect(p.id)}>×</Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              queue.map((p) => <ProspectCard key={p.id} p={p} />)
            )}
          </>
        )}

        {tab === 'tracking' && (
          <>
            <div className="ait-toolbar">
              <div className="ait-toolbar-left">
                <span className="ait-toolbar-meta">Who opened · who replied</span>
                <div className="ait-seg" role="group" aria-label="Tracking filter">
                  {[
                    { id: 'engagement', label: 'All sent' },
                    { id: 'opened', label: 'Opened' },
                    { id: 'replied', label: 'Replied' },
                    { id: 'sent', label: 'Sent only' },
                  ].map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      className={trackingFilter === f.id ? 'active' : ''}
                      onClick={() => setTrackingFilter(f.id)}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="ait-toolbar-right">
                <Button size="sm" variant="outline" disabled={!trackingRows.length || !!busy}
                  onClick={() => exportProspects(trackingFilter, `ai-team-${trackingFilter}.csv`)}>
                  Export Excel
                </Button>
                <Button size="sm" variant="outline" onClick={() => loadTracking(trackingFilter)}>
                  Refresh
                </Button>
              </div>
            </div>
            <div className="ait-card">
              <div className="ait-table-wrap">
                <table className="ait-tbl">
                  <thead>
                    <tr>
                      <th>Prospect</th>
                      <th>Company</th>
                      <th>Status</th>
                      <th>Sent</th>
                      <th>Opened</th>
                      <th>Replied</th>
                      <th>Subject</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {trackingRows.map((p) => (
                      <tr key={p.id}>
                        <td>
                          <strong>{p.full_name || p.email}</strong>
                          <div style={{ fontSize: 11, color: 'var(--ait-text3)' }}>{p.email}</div>
                        </td>
                        <td>{p.company_name || '—'}</td>
                        <td><span className={`ait-badge ${statusBadge(p.status)}`}>{p.status}</span></td>
                        <td style={{ fontSize: 12, color: 'var(--ait-text3)' }}>{timeAgo(p.sent_at)}</td>
                        <td style={{ fontSize: 12, color: p.opened_at ? 'var(--ait-purple)' : 'var(--ait-text3)' }}>
                          {p.opened_at ? timeAgo(p.opened_at) : '—'}
                        </td>
                        <td style={{ fontSize: 12, color: p.replied_at ? 'var(--ait-green)' : 'var(--ait-text3)' }}>
                          {p.replied_at ? timeAgo(p.replied_at) : '—'}
                        </td>
                        <td className="ait-ellipsis" title={p.draft_subject || ''}>{p.draft_subject || '—'}</td>
                          <td>
                            <div className="ait-btn-row" style={{ marginTop: 0, justifyContent: 'flex-end' }}>
                              <Button size="sm" variant="ghost" onClick={() => openProspectPreview(p)}>Email</Button>
                              <Button size="sm" variant="ghost" onClick={() => openDrawer(p)}>Profile</Button>
                              {(p.replied_at || p.status === 'replied') && (
                                <Button size="sm" variant="ghost" onClick={() => { setTab('replies'); selectThread(p) }}>Thread</Button>
                              )}
                            </div>
                          </td>
                      </tr>
                    ))}
                    {!trackingRows.length && (
                      <tr>
                        <td colSpan={8} style={{ textAlign: 'center', color: 'var(--ait-text3)', padding: 32 }}>
                          No tracked emails yet — approve drafts from the queue to start sending.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}


        {tab === 'prospects' && (
          <div className="ait-card">
            <div className="ait-card-hdr">
              <span className="ait-card-title">Prospect pipeline</span>
              <select value={prospectSource} onChange={(e) => setProspectSource(e.target.value)} style={{ maxWidth: 160 }}>
                <option value="">All sources</option>
                <option value="apify">Apify</option>
                <option value="paste">Paste</option>
                <option value="csv">CSV</option>
                <option value="apollo">Apollo</option>
              </select>
            </div>
            <div className="ait-card-body" style={{ overflowX: 'auto' }}>
              <table className="ait-tbl">
                <thead>
                  <tr><th>Prospect</th><th>Company</th><th>Source</th><th>Sector</th><th>Score</th><th>Status</th><th>Promo</th><th>Last</th><th /></tr>
                </thead>
                <tbody>
                  {(prospects.length ? prospects : []).map((p) => (
                    <tr key={p.id} style={{ cursor: 'pointer' }} onClick={() => openDrawer(p)}>
                      <td><strong>{p.full_name || p.email}</strong><div style={{ fontSize: 10, color: 'var(--ait-text3)' }}>{p.email}</div></td>
                      <td>{p.company_name || '—'}</td>
                      <td><span className="ait-badge b-pending">{p.source || '—'}</span></td>
                      <td><span className={`ait-badge ${sectorClass(p.sector)}`}>{p.sector}</span></td>
                      <td>{p.match_score}</td>
                      <td><span className={`ait-badge ${statusBadge(p.status)}`}>{p.status}</span></td>
                      <td>{p.promo_code && <span className="ait-promo-pill">{p.promo_code}</span>}</td>
                      <td style={{ fontSize: 11, color: 'var(--ait-text3)' }}>{timeAgo(p.updated_at)}</td>
                      <td><Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); openDrawer(p) }}>View</Button></td>
                    </tr>
                  ))}
                  {!prospects.length && (
                    <tr><td colSpan={9} style={{ textAlign: 'center', color: 'var(--ait-text3)', padding: 24 }}>No prospects yet — paste emails, CSV, or run Apify</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === 'replies' && (
          <div className="ait-replies">
            <div className="ait-inbox-panel">
              <div className="ait-card-hdr"><span className="ait-card-title">Inbox</span></div>
              <div style={{ overflowY: 'auto', flex: 1 }}>
                {threads.map((t) => (
                  <div key={t.id} className={`ait-inbox-item ${selectedThread?.id === t.id ? 'active' : ''}`} onClick={() => selectThread(t)}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}><strong style={{ fontSize: 12 }}>{t.full_name}</strong><span style={{ fontSize: 10, color: 'var(--ait-text3)' }}>{timeAgo(t.replied_at || t.updated_at)}</span></div>
                    <div style={{ fontSize: 11, color: 'var(--ait-text3)' }}>{t.company_name}</div>
                    <span className={`ait-badge ${statusBadge(t.status)}`} style={{ marginTop: 6 }}>{t.status}</span>
                  </div>
                ))}
                {!threads.length && <div style={{ padding: 24, color: 'var(--ait-text3)', textAlign: 'center' }}>No reply threads yet</div>}
              </div>
            </div>
            <div className="ait-thread-panel">
              {selectedThread && threadDetail ? (
                <>
                  <div className="ait-card-hdr">
                    <div><strong>{selectedThread.full_name}</strong><div style={{ fontSize: 11, color: 'var(--ait-text3)' }}>{selectedThread.email}</div></div>
                    <Button size="sm" variant="success" onClick={() => act('convert', () => apiFetch(`/admin/ai-team/prospects/${selectedThread.id}/convert`, { method: 'POST' }))}>Mark converted</Button>
                  </div>
                  <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
                    {(threadDetail.messages || []).map((m) => (
                      <div key={m.id} className={`ait-msg-bubble ${m.direction === 'inbound' ? 'incoming' : ''}`}>
                        <div style={{ fontSize: 10, color: 'var(--ait-text3)', marginBottom: 6 }}>{m.from_email} · {timeAgo(m.created_at)}</div>
                        {m.body_text}
                      </div>
                    ))}
                  </div>
                  <div style={{ padding: 12, borderTop: '1px solid var(--ait-border)' }}>
                    <Textarea className="ait-compose" value={replyText} onChange={(e) => setReplyText(e.target.value)} placeholder="Write your reply…" />
                    <div className="ait-btn-row" style={{ marginTop: 8 }}>
                      <Button size="sm" disabled={!replyText.trim() || !!busy}
                        onClick={() => act('reply', async () => {
                          await apiFetch(`/admin/ai-team/replies/${selectedThread.id}/send`, { method: 'POST', body: JSON.stringify({ body: replyText }) })
                          setReplyText('')
                          await selectThread(selectedThread)
                        })}>Send reply</Button>
                    </div>
                  </div>
                </>
              ) : (
                <div style={{ padding: 48, textAlign: 'center', color: 'var(--ait-text3)' }}>Select a thread</div>
              )}
            </div>
          </div>
        )}

        {tab === 'search' && (
          <>
            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Import any emails</span></div>
              <div className="ait-card-body">
                <p style={{ fontSize: 12, color: 'var(--ait-text3)', marginBottom: 10 }}>
                  Paste one email per line. Also accepts <code>Name &lt;email@x.com&gt;</code> or <code>email, first, last, company</code>.
                  Imports go to the approval queue with AI draft + promo, then follow-ups after send.
                </p>
                <div className="space-y-3">
                  <div>
                    <Label htmlFor="paste-emails">Emails</Label>
                    <Textarea
                      id="paste-emails"
                      className="min-h-[120px]"
                      value={pasteEmails}
                      onChange={(e) => setPasteEmails(e.target.value)}
                      placeholder={'ops@exhibitor.com\nJane Doe <jane@brand.co.uk>\nhello@stand.io, Jane, Doe, Brand Ltd'}
                    />
                  </div>
                  <div className="ait-fg-2">
                    <div>
                      <Label htmlFor="paste-company">Default company (optional)</Label>
                      <Input id="paste-company" value={pasteCompany} onChange={(e) => setPasteCompany(e.target.value)} />
                    </div>
                    <div>
                      <Label htmlFor="paste-sector">Sector</Label>
                      <Input id="paste-sector" value={pasteSector} onChange={(e) => setPasteSector(e.target.value)} placeholder="expo" />
                    </div>
                  </div>
                </div>
                <div className="ait-btn-row">
                  <Button disabled={!!busy || !pasteEmails.trim()} onClick={importPasteEmails}>
                    Import &amp; draft follow-ups
                  </Button>
                </div>
              </div>
            </div>

            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Import prospects from CSV</span></div>
              <div className="ait-card-body">
                <div
                  className={`ait-dropzone ${csvDrag ? 'active' : ''}`}
                  onDragOver={(e) => { e.preventDefault(); setCsvDrag(true) }}
                  onDragLeave={() => setCsvDrag(false)}
                  onDrop={(e) => {
                    e.preventDefault()
                    setCsvDrag(false)
                    const f = e.dataTransfer.files?.[0]
                    if (f) parseCsvFile(f).catch((err) => showBanner('err', err?.message || 'CSV parse failed'))
                  }}
                  onClick={() => document.getElementById('ait-csv-input')?.click()}
                >
                  <input
                    id="ait-csv-input"
                    type="file"
                    accept=".csv,text/csv"
                    style={{ display: 'none' }}
                    onChange={(e) => {
                      const f = e.target.files?.[0]
                      if (f) parseCsvFile(f).catch((err) => showBanner('err', err?.message || 'CSV parse failed'))
                    }}
                  />
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{csvFile ? csvFile.name : 'Drop CSV here or click to upload'}</div>
                  <div style={{ fontSize: 11, color: 'var(--ait-text3)', marginTop: 6 }}>
                    Manual Apollo alternative — import leads without API credits
                  </div>
                </div>

                {csvHeaders.length > 0 && (
                  <>
                    <div className="section-lbl" style={{ marginTop: 16, fontSize: 10, fontWeight: 700, color: 'var(--ait-text3)', textTransform: 'uppercase' }}>Field mapping</div>
                    <div className="ait-fg-3">
                      {CSV_MAP_FIELDS.map((f) => (
                        <div key={f.key} className="space-y-1.5">
                          <Label htmlFor={`csv-map-${f.key}`}>{f.label}{f.required ? ' *' : ''}</Label>
                          <Select
                            id={`csv-map-${f.key}`}
                            value={csvMapping[f.key] || ''}
                            onChange={(e) => setCsvMapping({ ...csvMapping, [f.key]: e.target.value })}
                          >
                            <option value="">— skip —</option>
                            {csvHeaders.map((h) => <option key={h} value={h}>{h}</option>)}
                          </Select>
                        </div>
                      ))}
                    </div>

                    <div style={{ marginTop: 12, fontSize: 11, color: 'var(--ait-text3)' }}>
                      Preview ({Math.min(5, csvPreviewRows.length)} of {csvTotal} rows)
                    </div>
                    <div style={{ overflowX: 'auto', marginTop: 8 }}>
                      <table className="ait-tbl">
                        <thead>
                          <tr>{csvHeaders.map((h) => <th key={h}>{h}</th>)}</tr>
                        </thead>
                        <tbody>
                          {csvPreviewRows.map((row, i) => (
                            <tr key={i}>{csvHeaders.map((h) => <td key={h}>{row[h] || '—'}</td>)}</tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <div className="ait-btn-row" style={{ marginTop: 12 }}>
                      <Button disabled={!!busy || !csvMapping.email} onClick={importCsv}>
                        Import {csvTotal} prospects
                      </Button>
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Apollo.io — target profile</span></div>
              <div className="ait-card-body">
                <div className="ait-fg-3">
                  <div><Label htmlFor="search-sector">Sector</Label><Input id="search-sector" value={settings.search_sector || ''} onChange={(e) => setSettings({ ...settings, search_sector: e.target.value })} /></div>
                  <div><Label htmlFor="search-country">Country</Label><Input id="search-country" value={settings.search_country || ''} onChange={(e) => setSettings({ ...settings, search_country: e.target.value })} /></div>
                  <div><Label htmlFor="search-company-size">Company size</Label><Input id="search-company-size" value={settings.search_company_size || ''} onChange={(e) => setSettings({ ...settings, search_company_size: e.target.value })} /></div>
                </div>
                <div className="ait-fg-2">
                  <div><Label htmlFor="search-title-keywords">Job title keywords</Label><Input id="search-title-keywords" value={settings.search_title_keywords || ''} onChange={(e) => setSettings({ ...settings, search_title_keywords: e.target.value })} /></div>
                  <div><Label htmlFor="search-city-region">City / region</Label><Input id="search-city-region" value={settings.search_city_region || ''} onChange={(e) => setSettings({ ...settings, search_city_region: e.target.value })} /></div>
                </div>
                <div className="ait-fg-4">
                  <div><Label htmlFor="search-max-per-run">Max per run</Label><Input id="search-max-per-run" type="number" value={settings.search_max_per_run || 20} onChange={(e) => setSettings({ ...settings, search_max_per_run: +e.target.value })} /></div>
                  <div><Label htmlFor="search-min-score">Min match score</Label><Input id="search-min-score" type="number" value={settings.search_min_score || 60} onChange={(e) => setSettings({ ...settings, search_min_score: +e.target.value })} /></div>
                  <div><Label htmlFor="followup-after-days">Follow-up after (days)</Label><Input id="followup-after-days" type="number" value={settings.followup_after_days || 3} onChange={(e) => setSettings({ ...settings, followup_after_days: +e.target.value })} /></div>
                  <div><Label htmlFor="max-followups">Max follow-ups</Label><Input id="max-followups" type="number" value={settings.max_followups || 2} onChange={(e) => setSettings({ ...settings, max_followups: +e.target.value })} /></div>
                </div>
                <div className="ait-btn-row">
                  <Button onClick={() => saveSettings()}>Save search profile</Button>
                  <Button variant="outline" disabled={!!busy}
                    onClick={() => act('preview', () => apiFetch('/admin/ai-team/search', { method: 'POST', body: JSON.stringify({ preview: true, limit: 5 }) }))}>
                    Preview — fetch 5 prospects
                  </Button>
                </div>
              </div>
            </div>
            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Email content — DeepSeek instructions</span></div>
              <div className="ait-card-body">
                <div className="ait-fg-2">
                  <div><Label htmlFor="sender-name">Sender name</Label><Input id="sender-name" value={settings.sender_name || ''} onChange={(e) => setSettings({ ...settings, sender_name: e.target.value })} /></div>
                  <div><Label htmlFor="reply-to-email">Reply-to</Label><Input id="reply-to-email" value={settings.reply_to_email || ''} onChange={(e) => setSettings({ ...settings, reply_to_email: e.target.value })} /></div>
                </div>
                <div>
                  <Label htmlFor="writing-instruction">Writing instruction</Label>
                  <Textarea id="writing-instruction" className="min-h-[100px]" value={settings.writing_instruction || ''} onChange={(e) => setSettings({ ...settings, writing_instruction: e.target.value })} />
                </div>
                <div>
                  <Label htmlFor="email-signature">Email signature</Label>
                  <Textarea id="email-signature" value={settings.email_signature || ''} onChange={(e) => setSettings({ ...settings, email_signature: e.target.value })} />
                </div>
                <div className="ait-btn-row">
                  <Button onClick={() => saveSettings()}>Save email settings</Button>
                  <Button variant="outline" disabled={!!busy}
                    onClick={() => act('sample', async () => {
                      const r = await apiFetch('/admin/ai-team/test/deepseek-sample', { method: 'POST' })
                      showBanner('ok', `Sample: ${r.subject}`)
                    })}>Generate sample</Button>
                </div>
              </div>
            </div>

            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Email template</span></div>
              <div className="ait-card-body">
                <p style={{ fontSize: 11, color: 'var(--ait-text3)', marginBottom: 10 }}>
                  Placeholders: {'{{body}}'}, {'{{first_name}}'}, {'{{last_name}}'}, {'{{company}}'}, {'{{promo_code}}'}, {'{{job_title}}'}, {'{{email}}'}
                </p>
                <div>
                  <Label htmlFor="email-html-template">HTML wrapper</Label>
                  <Textarea
                    id="email-html-template"
                    className="ait-code-editor"
                    value={settings.email_html_template || settings.default_email_html_template || ''}
                    onChange={(e) => setSettings({ ...settings, email_html_template: e.target.value })}
                  />
                </div>
                <div className="ait-fg-2" style={{ marginTop: 12 }}>
                  <div>
                    <Label htmlFor="search-test-email">Send test to your inbox</Label>
                    <Input
                      id="search-test-email"
                      type="email"
                      placeholder="you@company.com"
                      value={searchTestEmail}
                      onChange={(e) => setSearchTestEmail(e.target.value)}
                    />
                  </div>
                  <div style={{ justifyContent: 'flex-end', display: 'flex', alignItems: 'end' }}>
                    <Button variant="outline" disabled={!!busy} onClick={() => sendTestTemplate(searchTestEmail)}>
                      Send test with sample data
                    </Button>
                  </div>
                </div>
                <div className="ait-btn-row">
                  <Button onClick={() => saveSettings()}>Save template</Button>
                  <Button variant="outline" disabled={!!busy} onClick={openTemplatePreview}>Live preview</Button>
                  <Button
                    variant="outline"
                    onClick={() => setSettings({
                      ...settings,
                      email_html_template: settings.default_email_html_template || '',
                    })}
                  >
                    Reset to default
                  </Button>
                </div>
              </div>
            </div>
          </>
        )}


        {tab === 'promo' && (
          <>
            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Default promo offer</span></div>
              <div className="ait-card-body">
                <div className="ait-fg-2">
                  <div><Label htmlFor="promo-code-prefix">Code prefix</Label><Input id="promo-code-prefix" value={settings.promo_code_prefix || 'TRIAL'} onChange={(e) => setSettings({ ...settings, promo_code_prefix: e.target.value })} /></div>
                  <div>
                    <Label htmlFor="promo-offer-type">Offer type</Label>
                    <Select id="promo-offer-type" value={settings.promo_offer_type || 'survey_credits'} onChange={(e) => setSettings({ ...settings, promo_offer_type: e.target.value })}>
                      <option value="survey_credits">Free survey contacts</option>
                      <option value="interview_credits">Free interviews</option>
                      <option value="expo">Expo free usage</option>
                      <option value="dental_trial">Subscription trial</option>
                    </Select>
                  </div>
                </div>
                <div className="ait-fg-4">
                  <div><Label htmlFor="promo-value">Value</Label><Input id="promo-value" type="number" value={settings.promo_value || 50} onChange={(e) => setSettings({ ...settings, promo_value: +e.target.value })} /></div>
                  <div><Label htmlFor="promo-expiry-days">Expiry (days)</Label><Input id="promo-expiry-days" type="number" value={settings.promo_expiry_days || 14} onChange={(e) => setSettings({ ...settings, promo_expiry_days: +e.target.value })} /></div>
                  <div><Label htmlFor="promo-max-uses">Max uses</Label><Input id="promo-max-uses" type="number" value={settings.promo_max_uses || 1} onChange={(e) => setSettings({ ...settings, promo_max_uses: +e.target.value })} /></div>
                </div>
                <div className="ait-btn-row">
                  <Button onClick={() => saveSettings()}>Save offer defaults</Button>
                  <Link to="/marketing/promo-offers" className="ait-btn">All promo offers →</Link>
                </div>
              </div>
            </div>
            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Issued codes (auto-created per prospect)</span></div>
              <div className="ait-card-body">
                <table className="ait-tbl">
                  <thead><tr><th>Code</th><th>Prospect</th><th>Offer</th><th>Expires</th><th>Status</th></tr></thead>
                  <tbody>
                    {promoCodes.map((row) => (
                      <tr key={row.id}>
                        <td><span className="ait-promo-pill">{row.code}</span></td>
                        <td>{row.prospect_email || row.prospect_name || '—'}</td>
                        <td>{row.name}</td>
                        <td>{row.expires_at ? new Date(row.expires_at).toLocaleDateString() : '—'}</td>
                        <td><span className={`ait-badge ${row.usage_status === 'used' ? 'b-replied' : row.usage_status === 'expired' ? 'b-rejected' : 'b-pending'}`}>{row.usage_status}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {tab === 'analytics' && analytics && (
          <div className="ait-fg-2" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Outreach funnel</span></div>
              <div className="ait-card-body">
                {Object.entries(analytics.funnel || {}).map(([label, val]) => (
                  <div key={label} className="ait-funnel-bar">
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                      <span style={{ textTransform: 'capitalize' }}>{label}</span><strong>{val}</strong>
                    </div>
                    <div className="ait-funnel-track"><div className="ait-funnel-fill" style={{ width: `${Math.min(100, (val / (analytics.funnel?.found || 1)) * 100)}%`, background: 'var(--ait-accent)' }} /></div>
                  </div>
                ))}
              </div>
            </div>
            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Performance by sector</span></div>
              <div className="ait-card-body">
                <table className="ait-tbl">
                  <thead><tr><th>Sector</th><th>Sent</th><th>Open %</th><th>Reply %</th><th>Converted</th></tr></thead>
                  <tbody>
                    {(analytics.sectors || []).map((s) => (
                      <tr key={s.sector}><td>{s.sector}</td><td>{s.sent}</td><td>{s.open_pct}%</td><td>{s.reply_pct}%</td><td>{s.converted}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {tab === 'api' && (
          <>
            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Test all connections</span></div>
              <div className="ait-card-body">
                <p style={{ fontSize: 12, color: 'var(--ait-text3)', marginBottom: 10 }}>
                  Checks Apify, email delivery (SMTP or Resend), From address, promo defaults, and DeepSeek.
                </p>
                <div className="ait-btn-row">
                  <Button disabled={!!busy} onClick={runTestAll}>
                    Test all connections
                  </Button>
                  <Button
                    variant="outline"
                    disabled={!!busy}
                    onClick={() => act('followups', () => apiFetch('/admin/ai-team/followups/run', { method: 'POST' }).then((d) => showBanner('ok', `Follow-ups sent: ${d.sent || 0}`)))}
                  >
                    Run due follow-ups now
                  </Button>
                </div>
                {connectionChecks && (
                  <div style={{ marginTop: 12 }}>
                    {connectionChecks.map((c) => (
                      <div key={c.id} className="ait-toggle-row" style={{ gap: 10 }}>
                        <span className={`ait-dot ${c.ok ? 'on' : 'off'}`} />
                        <span style={{ flex: 1 }}><strong>{c.id}</strong> — {c.message}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Apollo.io</span></div>
              <div className="ait-card-body">
                <div className="ait-conn-block">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span className={`ait-dot ${settings.apollo_connected ? 'on' : 'off'}`} />
                    <div><strong>{settings.apollo_api_key_configured ? 'API key saved' : 'Not connected'}</strong></div>
                  </div>
                  <Button size="sm" variant="outline" disabled={!!busy}
                    onClick={() => act('test-apollo', () => apiFetch('/admin/ai-team/test/apollo', { method: 'POST', body: JSON.stringify({ api_key: apolloKey || undefined }) }))}>
                    Test connection
                  </Button>
                </div>
                <div className="ait-fg-2">
                  <div><Label htmlFor="apollo-api-key">API key</Label><Input id="apollo-api-key" type="password" placeholder={settings.apollo_api_key_configured ? '••••••••' : 'apollo_api_…'} value={apolloKey} onChange={(e) => setApolloKey(e.target.value)} /></div>
                  <div><Label htmlFor="apollo-credit-alert">Credit alert at</Label><Input id="apollo-credit-alert" type="number" value={settings.apollo_credit_alert_at || 800} onChange={(e) => setSettings({ ...settings, apollo_credit_alert_at: +e.target.value })} /></div>
                </div>
              </div>
            </div>
            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Resend.com</span></div>
              <div className="ait-card-body">
                <div className="ait-conn-block">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span className={`ait-dot ${settings.resend_connected ? 'on' : 'off'}`} />
                    <div><strong>{settings.resend_api_key_configured ? 'API key saved' : 'Not connected'}</strong></div>
                  </div>
                  <Button size="sm" variant="outline" disabled={!!busy}
                    onClick={() => act('test-resend', () => apiFetch('/admin/ai-team/test/resend', { method: 'POST', body: JSON.stringify({ api_key: resendKey || undefined }) }))}>
                    Test connection
                  </Button>
                </div>
                <div className="ait-fg-2">
                  <div><Label htmlFor="resend-api-key">API key</Label><Input id="resend-api-key" type="password" placeholder={settings.resend_api_key_configured ? '••••••••' : 're_…'} value={resendKey} onChange={(e) => setResendKey(e.target.value)} /></div>
                  <div><Label htmlFor="resend-sending-domain">Sending domain</Label><Input id="resend-sending-domain" value={settings.resend_sending_domain || ''} onChange={(e) => setSettings({ ...settings, resend_sending_domain: e.target.value })} placeholder="outreach.voxbulk.com" /></div>
                </div>
                <div className="ait-fg-2" style={{ marginTop: 4 }}>
                  <div>
                    <Label htmlFor="resend-test-email">Send test email to</Label>
                    <Input
                      id="resend-test-email"
                      type="email"
                      placeholder="you@company.com"
                      value={resendTestEmail}
                      onChange={(e) => setResendTestEmail(e.target.value)}
                    />
                  </div>
                  <div style={{ justifyContent: 'flex-end', display: 'flex', alignItems: 'end' }}>
                    <Button disabled={!!busy} onClick={() => sendTestTemplate(resendTestEmail)}>
                      Send rendered template
                    </Button>
                  </div>
                </div>
                <p style={{ fontSize: 11, color: 'var(--ait-text3)', marginTop: 8 }}>
                  Sends the full HTML template with sample data to your inbox before going live.
                </p>
              </div>
            </div>
            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Outreach email account</span></div>
              <div className="ait-card-body">
                <p className="ait-hint" style={{ marginTop: 0, marginBottom: 10 }}>
                  SMTP for campaigns also lives under the <strong>Apify</strong> sidebar page → Sending.
                </p>
                <div className="ait-fg-2">
                  <div>
                    <Label htmlFor="email-delivery-provider">Delivery provider</Label>
                    <Select
                      id="email-delivery-provider"
                      value={settings.email_delivery_provider || 'smtp'}
                      onChange={(e) => setSettings({ ...settings, email_delivery_provider: e.target.value })}
                    >
                      <option value="smtp">SMTP (your mailbox)</option>
                      <option value="resend">Resend</option>
                    </Select>
                  </div>
                  <div style={{ justifyContent: 'flex-end', display: 'flex', alignItems: 'end' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span className={`ait-dot ${(settings.email_delivery_provider || 'smtp') === 'smtp' ? (settings.smtp_configured ? 'on' : 'off') : (settings.resend_connected ? 'on' : 'off')}`} />
                      <span style={{ fontSize: 12 }}>{(settings.email_delivery_provider || 'smtp') === 'smtp' ? 'SMTP' : 'Resend'}</span>
                    </div>
                  </div>
                </div>
                <div className="ait-fg-2">
                  <div><Label htmlFor="smtp-sender-name">From name</Label><Input id="smtp-sender-name" value={settings.sender_name || ''} onChange={(e) => setSettings({ ...settings, sender_name: e.target.value })} /></div>
                  <div><Label htmlFor="smtp-from-email">From email (new outreach mailbox)</Label><Input id="smtp-from-email" value={settings.from_email || ''} onChange={(e) => setSettings({ ...settings, from_email: e.target.value })} /></div>
                </div>
                <div className="ait-fg-2">
                  <div><Label htmlFor="smtp-reply-to-email">Reply-to / inbox email</Label><Input id="smtp-reply-to-email" value={settings.reply_to_email || ''} onChange={(e) => setSettings({ ...settings, reply_to_email: e.target.value })} /></div>
                  <div><Label htmlFor="smtp-inbox-email">Inbox email (replies)</Label><Input id="smtp-inbox-email" value={settings.inbox_email || ''} onChange={(e) => setSettings({ ...settings, inbox_email: e.target.value })} /></div>
                </div>
                <div className="ait-fg-3">
                  <div><Label htmlFor="smtp-host">SMTP host</Label><Input id="smtp-host" value={settings.smtp_host || ''} onChange={(e) => setSettings({ ...settings, smtp_host: e.target.value })} /></div>
                  <div><Label htmlFor="smtp-port">SMTP port</Label><Input id="smtp-port" type="number" value={settings.smtp_port || 587} onChange={(e) => setSettings({ ...settings, smtp_port: +e.target.value })} /></div>
                  <div><Label htmlFor="smtp-username">SMTP username</Label><Input id="smtp-username" value={settings.smtp_username || ''} onChange={(e) => setSettings({ ...settings, smtp_username: e.target.value })} /></div>
                </div>
                <div><Label htmlFor="smtp-password">SMTP password</Label><Input id="smtp-password" type="password" placeholder={settings.smtp_password_configured ? '••••••••' : ''} value={smtpPassword} onChange={(e) => setSmtpPassword(e.target.value)} /></div>
                <div className="ait-btn-row">
                  <Button onClick={() => saveSettings()}>Save email account</Button>
                  <Button variant="outline" disabled={!!busy}
                    onClick={() => act('test-email', () => apiFetch('/admin/ai-team/test/email-account', { method: 'POST', body: JSON.stringify({ ...settings, smtp_password: smtpPassword || undefined, to_email: resendTestEmail || undefined }) }).then((d) => showBanner('ok', d.message || 'Test sent')))}>
                    Send test email
                  </Button>
                  <Button variant="outline" disabled={!!busy}
                    onClick={() => act('test-smtp', () => apiFetch('/admin/ai-team/test/smtp', { method: 'POST', body: JSON.stringify({ ...settings, smtp_password: smtpPassword || undefined, to_email: resendTestEmail || undefined }) }).then((d) => showBanner('ok', d.message || 'SMTP OK')))}>
                    Test SMTP
                  </Button>
                </div>
                <p style={{ fontSize: 11, color: 'var(--ait-text3)', marginTop: 8 }}>
                  Use your new dedicated outreach mailbox here. DeepSeek uses existing <Link to="/integrations/deepseek">Integrations → DeepSeek</Link>.
                </p>
              </div>
            </div>
            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Agent behaviour</span></div>
              <div className="ait-card-body">
                <div className="ait-fg-3">
                  <div><Label htmlFor="max-emails-per-day">Max emails per day</Label><Input id="max-emails-per-day" type="number" value={settings.max_emails_per_day || 10} onChange={(e) => setSettings({ ...settings, max_emails_per_day: +e.target.value })} /></div>
                  <div>
                    <Label htmlFor="run-schedule">Run schedule</Label>
                    <Select id="run-schedule" value={settings.run_schedule || 'daily_08'} onChange={(e) => setSettings({ ...settings, run_schedule: e.target.value })}>
                      <option value="daily_08">Daily at 08:00</option>
                      <option value="manual">Manual only</option>
                    </Select>
                  </div>
                </div>
                {[
                  ['auto_fetch_prospects', 'Auto-fetch prospects on schedule'],
                  ['auto_draft_emails', 'Auto-draft emails for qualified prospects'],
                  ['auto_followup', 'Auto follow-up if no reply'],
                  ['track_opens', 'Email open tracking'],
                  ['notify_on_reply', 'Notify on reply'],
                  ['notify_on_promo_used', 'Notify on promo code used'],
                  ['auto_send_without_approval', 'Auto-send without approval (keep off)'],
                  ['agent_paused', 'Pause agent'],
                ].map(([key, label]) => (
                  <div key={key} className="ait-toggle-row">
                    <span>{label}</span>
                    <input type="checkbox" checked={!!settings[key]} onChange={(e) => setSettings({ ...settings, [key]: e.target.checked })} />
                  </div>
                ))}
                <div className="ait-btn-row"><Button onClick={() => saveSettings()}>Save settings</Button></div>
              </div>
            </div>
          </>
        )}
      </div>

      {editDraft && (
        <div className="ait-drawer-overlay" onClick={() => setEditDraft(null)}>
          <div className="ait-drawer" onClick={(e) => e.stopPropagation()}>
            <h3>Edit draft</h3>
            <div className="space-y-3">
              <div><Label htmlFor="edit-subject">Subject</Label><Input id="edit-subject" value={editDraft.subject || ''} onChange={(e) => setEditDraft({ ...editDraft, subject: e.target.value })} /></div>
              <div><Label htmlFor="edit-body">Body</Label><Textarea id="edit-body" className="min-h-[200px]" value={editDraft.body || ''} onChange={(e) => setEditDraft({ ...editDraft, body: e.target.value })} /></div>
            </div>
            <div className="ait-btn-row">
              <Button onClick={() => act('edit', async () => {
                await apiFetch(`/admin/ai-team/prospects/${editDraft.id}/draft`, { method: 'PUT', body: JSON.stringify({ subject: editDraft.subject, body: editDraft.body }) })
                setEditDraft(null)
              })}>Save</Button>
              <Button variant="outline" onClick={() => setEditDraft(null)}>Cancel</Button>
            </div>
          </div>
        </div>
      )}

      {drawer && (
        <div className="ait-drawer-overlay" onClick={() => setDrawer(null)}>
          <div className="ait-drawer" onClick={(e) => e.stopPropagation()}>
            <Button variant="ghost" size="sm" onClick={() => setDrawer(null)}>Close</Button>
            <h3 style={{ marginTop: 12 }}>{drawer.full_name}</h3>
            <p style={{ fontSize: 11, color: 'var(--ait-text3)' }}>{drawer.job_title} · {drawer.company_name}</p>
            <p style={{ fontSize: 12, marginTop: 12 }}>{drawer.email}</p>
            {drawer.promo_code && <p className="ait-promo-pill" style={{ display: 'inline-block', marginTop: 8 }}>{drawer.promo_code}</p>}
            <h4 style={{ marginTop: 16, fontSize: 12 }}>Timeline</h4>
            {drawerMessages.map((m) => (
              <div key={m.id} style={{ fontSize: 12, marginBottom: 8 }}>
                <span style={{ color: 'var(--ait-text3)' }}>{m.direction} · {timeAgo(m.created_at)}</span>
                <div>{m.subject}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {emailPreview && (
        <div className="ait-modal-backdrop" onClick={() => setEmailPreview(null)}>
          <div className="ait-modal ait-modal-wide" onClick={(e) => e.stopPropagation()}>
            <div className="ait-modal-hdr">
              <div>
                <h3>{emailPreview.subject}</h3>
                <div style={{ fontSize: 11, color: 'var(--ait-text3)', marginTop: 4 }}>
                  To {emailPreview.prospect?.email} · {emailPreview.prospect?.full_name}
                </div>
              </div>
              <button type="button" className="ait-btn ghost sm" onClick={() => setEmailPreview(null)}>Close</button>
            </div>
            <iframe
              title="Email preview"
              className="ait-html-preview"
              sandbox=""
              srcDoc={emailPreview.html || ''}
            />
            <div className="ait-btn-row" style={{ marginTop: 14 }}>
              <Button
                variant="success"
                disabled={busy === emailPreview.prospect?.id}
                onClick={() => act(emailPreview.prospect.id, async () => {
                  await apiFetch(`/admin/ai-team/prospects/${emailPreview.prospect.id}/approve`, { method: 'POST' })
                  setEmailPreview(null)
                  showBanner('ok', 'Email approved and sent')
                })}
              >
                Approve & send
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  const p = emailPreview.prospect
                  setEditDraft({ id: p.id, subject: p.draft_subject, body: p.draft_body })
                  setEmailPreview(null)
                }}
              >
                Edit
              </Button>
              <Button
                variant="outline"
                disabled={busy === `rej-${emailPreview.prospect?.id}`}
                onClick={() => act(`rej-${emailPreview.prospect.id}`, async () => {
                  await apiFetch(`/admin/ai-team/prospects/${emailPreview.prospect.id}/reject`, { method: 'POST' })
                  setEmailPreview(null)
                  showBanner('ok', 'Prospect rejected')
                })}
              >
                Reject
              </Button>
              <Button
                variant="destructive"
                disabled={busy === `del-${emailPreview.prospect?.id}`}
                onClick={() => deleteProspect(emailPreview.prospect.id)}
              >
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}


      {howtoOpen && (
        <div className="ait-modal-backdrop" onClick={() => setHowtoOpen(false)}>
          <div className="ait-modal ait-modal-wide" onClick={(e) => e.stopPropagation()}>
            <div className="ait-modal-hdr">
              <h3>How to use AI Team</h3>
              <button type="button" className="ait-btn ghost sm" onClick={() => setHowtoOpen(false)}>Close</button>
            </div>
            <div style={{ maxHeight: '70vh', overflow: 'auto', paddingRight: 4 }}>
          <div className="ait-howto">
            <div className="ait-howto-step">
              <h3><span className="ait-howto-num">1</span> Connect sending</h3>
              <ol>
                <li>Open <strong>API settings</strong> (or the Apify menu → Sending) and save SMTP / Resend.</li>
                <li>Send a test email to yourself.</li>
                <li>Optional: set writing tone under <strong>API settings → Agent behaviour</strong>.</li>
              </ol>
            </div>
            <div className="ait-howto-step">
              <h3><span className="ait-howto-num">2</span> Scrape expo emails</h3>
              <ol>
                <li>Go to the sidebar <strong>Apify</strong> page → <strong>Scrape</strong>.</li>
                <li>Paste the exhibitor directory URL (e.g. London Packaging Week).</li>
                <li>Tick <strong>Also scrape company websites</strong> for more emails.</li>
                <li>Click <strong>Scrape</strong> and wait for SUCCEEDED (live progress updates).</li>
                <li>Use <strong>View</strong> / <strong>Export Excel</strong>, then <strong>Import</strong>.</li>
              </ol>
            </div>
            <div className="ait-howto-step">
              <h3><span className="ait-howto-num">3</span> Approve & send</h3>
              <ol>
                <li>Imported rows become drafts in <strong>Approval queue</strong>.</li>
                <li><strong>View email</strong> shows the full HTML; Edit / Regenerate as needed.</li>
                <li><strong>Approve & send</strong> one row, or <strong>Approve & send all</strong>.</li>
                <li><strong>Delete</strong> removes one; <strong>Delete all</strong> clears the whole queue.</li>
                <li><strong>Export Excel</strong> downloads the queue as CSV (opens in Excel).</li>
              </ol>
            </div>
            <div className="ait-howto-step">
              <h3><span className="ait-howto-num">4</span> Track engagement</h3>
              <ol>
                <li><strong>Sent / Tracking</strong> lists who was emailed, opened, or replied.</li>
                <li>Filter: All sent · Opened · Replied · Sent only.</li>
                <li><strong>Replies</strong> is the inbox for conversation threads.</li>
                <li>Stats strip at the top shows open rate, reply rate, and conversions.</li>
              </ol>
            </div>
            <div className="ait-howto-step">
              <h3><span className="ait-howto-num">5</span> Other intake</h3>
              <ul>
                <li><strong>Search & email</strong> — paste emails / CSV / Apollo search.</li>
                <li><strong>Prospects</strong> — full pipeline table (all statuses).</li>
                <li><strong>Promo codes</strong> — codes attached to outreach.</li>
                <li>Nothing sends until you approve (unless auto-send is enabled in settings).</li>
              </ul>
            </div>
            <div className="ait-howto-step">
              <h3><span className="ait-howto-num">!</span> Tips</h3>
              <ul>
                <li>Scrape jobs run on Celery — if status sticks on RUNNING with no heartbeat, check workers on the VPS.</li>
                <li>Reject keeps a rejected status; Delete removes the row permanently.</li>
                <li>Open tracking needs pixel / provider open events configured on your mail path.</li>
              </ul>
              <p style={{ marginTop: 12 }}>
                Need scrape / templates / bulk send?{' '}
                <Link to="/marketing/apify" className="ait-btn primary sm" onClick={() => setHowtoOpen(false)}>
                  Open Apify
                </Link>
              </p>
            </div>
          </div>
            </div>
          </div>
        </div>
      )}

      {templatePreview && (
        <div className="ait-modal-backdrop" onClick={() => setTemplatePreview(null)}>
          <div className="ait-modal ait-modal-wide" onClick={(e) => e.stopPropagation()}>
            <div className="ait-modal-hdr">
              <div>
                <h3>Template preview (sample data)</h3>
                <div style={{ fontSize: 11, color: 'var(--ait-text3)', marginTop: 4 }}>{templatePreview.subject}</div>
              </div>
              <button type="button" className="ait-btn ghost sm" onClick={() => setTemplatePreview(null)}>Close</button>
            </div>
            <iframe
              title="Template preview"
              className="ait-html-preview"
              sandbox=""
              srcDoc={templatePreview.html || ''}
            />
            <div className="ait-btn-row" style={{ marginTop: 14 }}>
              <Button variant="outline" onClick={() => setTemplatePreview(null)}>Close</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
