import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import './ai-team.css'

const TABS = [
  { id: 'queue', label: 'Approval queue', icon: 'ti-mail' },
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

  const loadProspects = useCallback(async () => {
    try {
      const data = await apiFetch('/admin/ai-team/prospects')
      setProspects(data.prospects || [])
    } catch (e) {
      showBanner('err', e?.message || 'Could not load prospects')
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
    if (tab === 'prospects') loadProspects()
    if (tab === 'replies') loadReplies()
    if (tab === 'promo') loadPromo()
    if (tab === 'analytics') loadAnalytics()
  }, [tab, loadProspects, loadReplies, loadPromo, loadAnalytics])

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
      if (tab === 'prospects') await loadProspects()
      if (tab === 'replies') await loadReplies()
    } catch (e) {
      showBanner('err', e?.message || 'Action failed')
    } finally {
      setBusy('')
    }
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

  const ProspectCard = ({ p, showActions = true }) => (
    <div className="ait-pcard" key={p.id}>
      <div className="ait-pcard-top">
        <div className="ait-avatar b-prop">{initials(p.full_name)}</div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
            <strong>{p.full_name}</strong>
            <span className={`ait-badge ${sectorClass(p.sector)}`}>{p.sector || 'General'}</span>
            <span className={`ait-badge ${statusBadge(p.status)}`}>{p.status}</span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--ait-text3)', marginTop: 2 }}>
            {p.job_title} — {p.company_name} · {p.email} · {p.country_code}
          </div>
          <div style={{ fontSize: 11, marginTop: 6 }}>
            Match <strong style={{ color: p.match_score >= 80 ? 'var(--ait-green)' : 'var(--ait-amber)' }}>{p.match_score}</strong>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          {p.promo_code && <div className="ait-promo-pill">{p.promo_code}</div>}
          <div style={{ fontSize: 10, color: 'var(--ait-text3)', marginTop: 4 }}>{p.source || 'apollo'}</div>
        </div>
      </div>
      {(p.draft_subject || p.draft_body) && (
        <div className="ait-pcard-body">
          <div style={{ fontWeight: 600, marginBottom: 6 }}>{p.draft_subject}</div>
          <div className="ait-email-preview">{p.draft_body}</div>
          {showActions && (
            <div className="ait-btn-row">
              <button type="button" className="ait-btn success sm" disabled={busy === p.id}
                onClick={() => act(p.id, () => apiFetch(`/admin/ai-team/prospects/${p.id}/approve`, { method: 'POST' }))}>
                Approve & send
              </button>
              <button type="button" className="ait-btn sm" onClick={() => setEditDraft({ id: p.id, subject: p.draft_subject, body: p.draft_body })}>Edit</button>
              <button type="button" className="ait-btn sm" disabled={busy === p.id}
                onClick={() => act(`reg-${p.id}`, () => apiFetch(`/admin/ai-team/prospects/${p.id}/regenerate`, { method: 'POST' }))}>
                Regenerate
              </button>
              <button type="button" className="ait-btn danger sm" disabled={busy === p.id}
                onClick={() => act(`rej-${p.id}`, () => apiFetch(`/admin/ai-team/prospects/${p.id}/reject`, { method: 'POST' }))}>
                Reject
              </button>
              <span style={{ fontSize: 10, color: 'var(--ait-text3)', marginLeft: 'auto' }}>
                {timeAgo(p.drafted_at)} · <button type="button" className="ait-btn ghost xs" onClick={() => openDrawer(p)}>Profile →</button>
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
          <div>
            <div className="ait-page-title">AI Team — Sales Agent</div>
            <div className="ait-page-sub">Semi-automatic outreach · Apollo + Resend + DeepSeek</div>
          </div>
          <div className="ait-agent-pill">
            <span className="ait-pulse" />
            {settings.agent_paused ? 'Paused' : 'Active'}
          </div>
        </div>
        <div className="ait-topbar-right">
          <button type="button" className="ait-btn ghost sm" disabled={!!busy}
            onClick={() => act('run', () => apiFetch('/admin/ai-team/agent/run', { method: 'POST' }))}>
            Run agent
          </button>
          <button type="button" className="ait-btn primary sm" disabled={!!busy}
            onClick={() => act('search', () => apiFetch('/admin/ai-team/search', { method: 'POST', body: JSON.stringify({ preview: false }) }))}>
            New search
          </button>
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
            {t.id === 'queue' && stats.pending_approval > 0 && <span className="ait-tab-badge">{stats.pending_approval}</span>}
            {t.id === 'replies' && stats.replied_count > 0 && <span className="ait-tab-badge">{stats.replied_count}</span>}
          </button>
        ))}
      </div>

      <div className="ait-content">
        {tab === 'queue' && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
              <span style={{ color: 'var(--ait-text3)', fontSize: 12 }}>{queue.length} awaiting approval</span>
              <button type="button" className="ait-btn primary sm" disabled={!queue.length || !!busy}
                onClick={() => act('approve-all', () => apiFetch('/admin/ai-team/prospects/approve-all', { method: 'POST' }))}>
                Approve all {queue.length}
              </button>
            </div>
            {queue.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 48, color: 'var(--ait-text3)' }}>
                No drafts in queue. Run a search or configure Apollo in API settings.
              </div>
            ) : queue.map((p) => <ProspectCard key={p.id} p={p} />)}
          </>
        )}

        {tab === 'prospects' && (
          <div className="ait-card">
            <div className="ait-card-hdr"><span className="ait-card-title">Prospect pipeline</span></div>
            <div className="ait-card-body" style={{ overflowX: 'auto' }}>
              <table className="ait-tbl">
                <thead>
                  <tr><th>Prospect</th><th>Company</th><th>Sector</th><th>Score</th><th>Status</th><th>Promo</th><th>Last</th><th /></tr>
                </thead>
                <tbody>
                  {(prospects.length ? prospects : queue).map((p) => (
                    <tr key={p.id} style={{ cursor: 'pointer' }} onClick={() => openDrawer(p)}>
                      <td><strong>{p.full_name}</strong><div style={{ fontSize: 10, color: 'var(--ait-text3)' }}>{p.email}</div></td>
                      <td>{p.company_name}</td>
                      <td><span className={`ait-badge ${sectorClass(p.sector)}`}>{p.sector}</span></td>
                      <td>{p.match_score}</td>
                      <td><span className={`ait-badge ${statusBadge(p.status)}`}>{p.status}</span></td>
                      <td>{p.promo_code && <span className="ait-promo-pill">{p.promo_code}</span>}</td>
                      <td style={{ fontSize: 11, color: 'var(--ait-text3)' }}>{timeAgo(p.updated_at)}</td>
                      <td><button type="button" className="ait-btn xs" onClick={(e) => { e.stopPropagation(); openDrawer(p) }}>View</button></td>
                    </tr>
                  ))}
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
                    <button type="button" className="ait-btn xs success" onClick={() => act('convert', () => apiFetch(`/admin/ai-team/prospects/${selectedThread.id}/convert`, { method: 'POST' }))}>Mark converted</button>
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
                    <textarea className="ait-compose" value={replyText} onChange={(e) => setReplyText(e.target.value)} placeholder="Write your reply…" />
                    <div className="ait-btn-row" style={{ marginTop: 8 }}>
                      <button type="button" className="ait-btn primary sm" disabled={!replyText.trim() || !!busy}
                        onClick={() => act('reply', async () => {
                          await apiFetch(`/admin/ai-team/replies/${selectedThread.id}/send`, { method: 'POST', body: JSON.stringify({ body: replyText }) })
                          setReplyText('')
                          await selectThread(selectedThread)
                        })}>Send reply</button>
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
              <div className="ait-card-hdr"><span className="ait-card-title">Apollo.io — target profile</span></div>
              <div className="ait-card-body">
                <div className="ait-fg-3">
                  <div className="ait-field"><label>Sector</label><input value={settings.search_sector || ''} onChange={(e) => setSettings({ ...settings, search_sector: e.target.value })} /></div>
                  <div className="ait-field"><label>Country</label><input value={settings.search_country || ''} onChange={(e) => setSettings({ ...settings, search_country: e.target.value })} /></div>
                  <div className="ait-field"><label>Company size</label><input value={settings.search_company_size || ''} onChange={(e) => setSettings({ ...settings, search_company_size: e.target.value })} /></div>
                </div>
                <div className="ait-fg-2">
                  <div className="ait-field"><label>Job title keywords</label><input value={settings.search_title_keywords || ''} onChange={(e) => setSettings({ ...settings, search_title_keywords: e.target.value })} /></div>
                  <div className="ait-field"><label>City / region</label><input value={settings.search_city_region || ''} onChange={(e) => setSettings({ ...settings, search_city_region: e.target.value })} /></div>
                </div>
                <div className="ait-fg-4">
                  <div className="ait-field"><label>Max per run</label><input type="number" value={settings.search_max_per_run || 20} onChange={(e) => setSettings({ ...settings, search_max_per_run: +e.target.value })} /></div>
                  <div className="ait-field"><label>Min match score</label><input type="number" value={settings.search_min_score || 60} onChange={(e) => setSettings({ ...settings, search_min_score: +e.target.value })} /></div>
                  <div className="ait-field"><label>Follow-up after (days)</label><input type="number" value={settings.followup_after_days || 3} onChange={(e) => setSettings({ ...settings, followup_after_days: +e.target.value })} /></div>
                  <div className="ait-field"><label>Max follow-ups</label><input type="number" value={settings.max_followups || 2} onChange={(e) => setSettings({ ...settings, max_followups: +e.target.value })} /></div>
                </div>
                <div className="ait-btn-row">
                  <button type="button" className="ait-btn primary" onClick={() => saveSettings()}>Save search profile</button>
                  <button type="button" className="ait-btn" disabled={!!busy}
                    onClick={() => act('preview', () => apiFetch('/admin/ai-team/search', { method: 'POST', body: JSON.stringify({ preview: true, limit: 5 }) }))}>
                    Preview — fetch 5 prospects
                  </button>
                </div>
              </div>
            </div>
            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Email content — DeepSeek instructions</span></div>
              <div className="ait-card-body">
                <div className="ait-fg-2">
                  <div className="ait-field"><label>Sender name</label><input value={settings.sender_name || ''} onChange={(e) => setSettings({ ...settings, sender_name: e.target.value })} /></div>
                  <div className="ait-field"><label>Reply-to</label><input value={settings.reply_to_email || ''} onChange={(e) => setSettings({ ...settings, reply_to_email: e.target.value })} /></div>
                </div>
                <div className="ait-field"><label>Writing instruction</label>
                  <textarea style={{ height: 100 }} value={settings.writing_instruction || ''} onChange={(e) => setSettings({ ...settings, writing_instruction: e.target.value })} />
                </div>
                <div className="ait-field"><label>Email signature</label>
                  <textarea value={settings.email_signature || ''} onChange={(e) => setSettings({ ...settings, email_signature: e.target.value })} />
                </div>
                <div className="ait-btn-row">
                  <button type="button" className="ait-btn primary" onClick={() => saveSettings()}>Save email settings</button>
                  <button type="button" className="ait-btn" disabled={!!busy}
                    onClick={() => act('sample', async () => {
                      const r = await apiFetch('/admin/ai-team/test/deepseek-sample', { method: 'POST' })
                      showBanner('ok', `Sample: ${r.subject}`)
                    })}>Generate sample</button>
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
                  <div className="ait-field"><label>Code prefix</label><input value={settings.promo_code_prefix || 'TRIAL'} onChange={(e) => setSettings({ ...settings, promo_code_prefix: e.target.value })} /></div>
                  <div className="ait-field"><label>Offer type</label>
                    <select value={settings.promo_offer_type || 'survey_credits'} onChange={(e) => setSettings({ ...settings, promo_offer_type: e.target.value })}>
                      <option value="survey_credits">Free survey contacts</option>
                      <option value="interview_credits">Free interviews</option>
                      <option value="dental_trial">Subscription trial</option>
                    </select>
                  </div>
                </div>
                <div className="ait-fg-4">
                  <div className="ait-field"><label>Value</label><input type="number" value={settings.promo_value || 50} onChange={(e) => setSettings({ ...settings, promo_value: +e.target.value })} /></div>
                  <div className="ait-field"><label>Expiry (days)</label><input type="number" value={settings.promo_expiry_days || 14} onChange={(e) => setSettings({ ...settings, promo_expiry_days: +e.target.value })} /></div>
                  <div className="ait-field"><label>Max uses</label><input type="number" value={settings.promo_max_uses || 1} onChange={(e) => setSettings({ ...settings, promo_max_uses: +e.target.value })} /></div>
                </div>
                <div className="ait-btn-row">
                  <button type="button" className="ait-btn primary" onClick={() => saveSettings()}>Save offer defaults</button>
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
              <div className="ait-card-hdr"><span className="ait-card-title">Apollo.io</span></div>
              <div className="ait-card-body">
                <div className="ait-conn-block">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span className={`ait-dot ${settings.apollo_connected ? 'on' : 'off'}`} />
                    <div><strong>{settings.apollo_api_key_configured ? 'API key saved' : 'Not connected'}</strong></div>
                  </div>
                  <button type="button" className="ait-btn sm" disabled={!!busy}
                    onClick={() => act('test-apollo', () => apiFetch('/admin/ai-team/test/apollo', { method: 'POST', body: JSON.stringify({ api_key: apolloKey || undefined }) }))}>
                    Test connection
                  </button>
                </div>
                <div className="ait-fg-2">
                  <div className="ait-field"><label>API key</label><input type="password" placeholder={settings.apollo_api_key_configured ? '••••••••' : 'apollo_api_…'} value={apolloKey} onChange={(e) => setApolloKey(e.target.value)} /></div>
                  <div className="ait-field"><label>Credit alert at</label><input type="number" value={settings.apollo_credit_alert_at || 800} onChange={(e) => setSettings({ ...settings, apollo_credit_alert_at: +e.target.value })} /></div>
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
                  <button type="button" className="ait-btn sm" disabled={!!busy}
                    onClick={() => act('test-resend', () => apiFetch('/admin/ai-team/test/resend', { method: 'POST', body: JSON.stringify({ api_key: resendKey || undefined }) }))}>
                    Send test email
                  </button>
                </div>
                <div className="ait-fg-2">
                  <div className="ait-field"><label>API key</label><input type="password" placeholder={settings.resend_api_key_configured ? '••••••••' : 're_…'} value={resendKey} onChange={(e) => setResendKey(e.target.value)} /></div>
                  <div className="ait-field"><label>Sending domain</label><input value={settings.resend_sending_domain || ''} onChange={(e) => setSettings({ ...settings, resend_sending_domain: e.target.value })} placeholder="outreach.voxbulk.com" /></div>
                </div>
              </div>
            </div>
            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Outreach email account</span></div>
              <div className="ait-card-body">
                <div className="ait-fg-2">
                  <div className="ait-field"><label>From name</label><input value={settings.sender_name || ''} onChange={(e) => setSettings({ ...settings, sender_name: e.target.value })} /></div>
                  <div className="ait-field"><label>From email</label><input value={settings.from_email || ''} onChange={(e) => setSettings({ ...settings, from_email: e.target.value })} /></div>
                </div>
                <div className="ait-fg-2">
                  <div className="ait-field"><label>Reply-to / inbox email</label><input value={settings.reply_to_email || ''} onChange={(e) => setSettings({ ...settings, reply_to_email: e.target.value })} /></div>
                  <div className="ait-field"><label>Inbox email (replies)</label><input value={settings.inbox_email || ''} onChange={(e) => setSettings({ ...settings, inbox_email: e.target.value })} /></div>
                </div>
                <div className="ait-fg-3">
                  <div className="ait-field"><label>SMTP host</label><input value={settings.smtp_host || ''} onChange={(e) => setSettings({ ...settings, smtp_host: e.target.value })} /></div>
                  <div className="ait-field"><label>SMTP port</label><input type="number" value={settings.smtp_port || 587} onChange={(e) => setSettings({ ...settings, smtp_port: +e.target.value })} /></div>
                  <div className="ait-field"><label>SMTP username</label><input value={settings.smtp_username || ''} onChange={(e) => setSettings({ ...settings, smtp_username: e.target.value })} /></div>
                </div>
                <div className="ait-field"><label>SMTP password</label><input type="password" placeholder={settings.smtp_password_configured ? '••••••••' : ''} value={smtpPassword} onChange={(e) => setSmtpPassword(e.target.value)} /></div>
                <div className="ait-btn-row">
                  <button type="button" className="ait-btn primary" onClick={() => saveSettings()}>Save email account</button>
                  <button type="button" className="ait-btn" disabled={!!busy}
                    onClick={() => act('test-email', () => apiFetch('/admin/ai-team/test/email-account', { method: 'POST', body: JSON.stringify({ ...settings, smtp_password: smtpPassword || undefined }) }))}>
                    Send test email
                  </button>
                  <button type="button" className="ait-btn" disabled={!!busy}
                    onClick={() => act('test-smtp', () => apiFetch('/admin/ai-team/test/smtp', { method: 'POST', body: JSON.stringify({ ...settings, smtp_password: smtpPassword || undefined }) }))}>
                    Test SMTP
                  </button>
                </div>
                <p style={{ fontSize: 11, color: 'var(--ait-text3)', marginTop: 8 }}>
                  DeepSeek uses existing <Link to="/integrations/deepseek">Integrations → DeepSeek</Link> platform key.
                </p>
              </div>
            </div>
            <div className="ait-card">
              <div className="ait-card-hdr"><span className="ait-card-title">Agent behaviour</span></div>
              <div className="ait-card-body">
                <div className="ait-fg-3">
                  <div className="ait-field"><label>Max emails per day</label><input type="number" value={settings.max_emails_per_day || 10} onChange={(e) => setSettings({ ...settings, max_emails_per_day: +e.target.value })} /></div>
                  <div className="ait-field"><label>Run schedule</label>
                    <select value={settings.run_schedule || 'daily_08'} onChange={(e) => setSettings({ ...settings, run_schedule: e.target.value })}>
                      <option value="daily_08">Daily at 08:00</option>
                      <option value="manual">Manual only</option>
                    </select>
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
                <div className="ait-btn-row"><button type="button" className="ait-btn primary" onClick={() => saveSettings()}>Save settings</button></div>
              </div>
            </div>
          </>
        )}
      </div>

      {editDraft && (
        <div className="ait-drawer-overlay" onClick={() => setEditDraft(null)}>
          <div className="ait-drawer" onClick={(e) => e.stopPropagation()}>
            <h3>Edit draft</h3>
            <div className="ait-field"><label>Subject</label><input value={editDraft.subject || ''} onChange={(e) => setEditDraft({ ...editDraft, subject: e.target.value })} /></div>
            <div className="ait-field"><label>Body</label><textarea style={{ height: 200 }} value={editDraft.body || ''} onChange={(e) => setEditDraft({ ...editDraft, body: e.target.value })} /></div>
            <div className="ait-btn-row">
              <button type="button" className="ait-btn primary" onClick={() => act('edit', async () => {
                await apiFetch(`/admin/ai-team/prospects/${editDraft.id}/draft`, { method: 'PUT', body: JSON.stringify({ subject: editDraft.subject, body: editDraft.body }) })
                setEditDraft(null)
              })}>Save</button>
              <button type="button" className="ait-btn" onClick={() => setEditDraft(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {drawer && (
        <div className="ait-drawer-overlay" onClick={() => setDrawer(null)}>
          <div className="ait-drawer" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="ait-btn ghost sm" onClick={() => setDrawer(null)}>Close</button>
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
    </div>
  )
}
