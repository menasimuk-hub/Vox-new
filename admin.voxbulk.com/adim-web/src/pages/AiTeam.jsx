import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch, apiFetchBlob, apiUpload } from '../lib/api'
import './ai-team.css'

const TABS = [
  { id: 'campaigns', label: 'Campaigns', icon: 'ti-send' },
  { id: 'scrape', label: 'Scrape', icon: 'ti-world' },
  { id: 'settings', label: 'Settings', icon: 'ti-settings' },
]

const SETTINGS_SUB_TABS = [
  { id: 'sending', label: 'Sending' },
  { id: 'apify', label: 'Apify' },
  { id: 'apollo', label: 'Apollo' },
  { id: 'ai', label: 'AI' },
  { id: 'promo', label: 'Promo' },
]

const SUGGESTED_ACTORS = [
  { id: 'vdrmota~contact-info-scraper', label: 'Contact info', note: 'Emails/phones from websites' },
  { id: 'foo121~website-contact-scraper', label: 'Website email', note: 'Bulk website emails' },
  { id: 'goat255~website-contact-scraper', label: 'Contact pages', note: 'Homepage + contact pages' },
]

const CSV_MAP_FIELDS = [
  { key: 'email', label: 'Email', required: true },
  { key: 'first_name', label: 'First name' },
  { key: 'last_name', label: 'Last name' },
  { key: 'job_title', label: 'Job title' },
  { key: 'company_name', label: 'Company' },
  { key: 'sector', label: 'Sector' },
  { key: 'country_code', label: 'Country' },
  { key: 'promo_code', label: 'Promo' },
]

const MERGE_TAGS = ['first_name', 'company', 'job_title', 'email', 'promo_code']

function guessCsvMapping(headers) {
  const norm = (h) => String(h || '').toLowerCase().replace(/[^a-z0-9]+/g, '_')
  const map = {}
  const rules = [
    ['email', ['email', 'e_mail', 'email_address']],
    ['first_name', ['first_name', 'firstname', 'first', 'given_name']],
    ['last_name', ['last_name', 'lastname', 'last', 'surname', 'family_name']],
    ['job_title', ['job_title', 'title', 'role', 'position']],
    ['company_name', ['company', 'company_name', 'organization', 'org', 'account_name', 'stand_name']],
    ['sector', ['sector', 'industry', 'vertical']],
    ['country_code', ['country', 'country_code', 'location']],
    ['promo_code', ['promo', 'promo_code', 'code']],
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

function statusBadge(status) {
  const map = {
    draft: 'b-pending',
    sending: 'b-opened',
    sent: 'b-sent',
    cancelled: 'b-rejected',
    failed: 'b-rejected',
    pending: 'b-pending',
  }
  return map[status] || 'b-pending'
}

function insertTag(value, setValue, tag) {
  const token = `{{${tag}}}`
  setValue(`${value || ''}${token}`)
}

export default function AiTeam() {
  const [tab, setTab] = useState('campaigns')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [banner, setBanner] = useState(null)
  const [settings, setSettings] = useState({})
  const [howtoOpen, setHowtoOpen] = useState(false)

  const [campaigns, setCampaigns] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [campaign, setCampaign] = useState(null)
  const [recipients, setRecipients] = useState([])
  const [newName, setNewName] = useState('')
  const [preview, setPreview] = useState(null)
  const [testEmail, setTestEmail] = useState('')
  const [recipientFilter, setRecipientFilter] = useState('all')

  const [csvFile, setCsvFile] = useState(null)
  const [csvDrag, setCsvDrag] = useState(false)
  const [csvHeaders, setCsvHeaders] = useState([])
  const [csvPreviewRows, setCsvPreviewRows] = useState([])
  const [csvTotal, setCsvTotal] = useState(0)
  const [csvMapping, setCsvMapping] = useState({})

  const [apifyExpoUrl, setApifyExpoUrl] = useState('')
  const [apifyActorUrl, setApifyActorUrl] = useState('')
  const [apifyActorOverride, setApifyActorOverride] = useState('')
  const [scrapeFollowWebsites, setScrapeFollowWebsites] = useState(true)
  const [apifyRuns, setApifyRuns] = useState([])
  const [apifyPreview, setApifyPreview] = useState(null)

  const [settingsSubTab, setSettingsSubTab] = useState('sending')
  const [smtpPassword, setSmtpPassword] = useState('')
  const [resendKey, setResendKey] = useState('')
  const [apolloKey, setApolloKey] = useState('')
  const [apifyToken, setApifyToken] = useState('')
  const [smtpTestResult, setSmtpTestResult] = useState(null)
  const [apifyTestResult, setApifyTestResult] = useState(null)
  const [apolloTestResult, setApolloTestResult] = useState(null)
  const [settingsTestEmail, setSettingsTestEmail] = useState('')
  const [promoCodes, setPromoCodes] = useState([])

  const showBanner = (type, text) => {
    setBanner({ type, text })
    window.setTimeout(() => setBanner(null), 5000)
  }

  const loadCampaigns = useCallback(async () => {
    const data = await apiFetch('/admin/ai-team/campaigns')
    setCampaigns(data.campaigns || [])
    return data.campaigns || []
  }, [])

  const loadCampaign = useCallback(async (id) => {
    if (!id) {
      setCampaign(null)
      setRecipients([])
      return null
    }
    const data = await apiFetch(`/admin/ai-team/campaigns/${id}`)
    setCampaign(data.campaign || null)
    setRecipients(data.recipients || [])
    return data.campaign
  }, [])

  const loadDashboard = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiFetch('/admin/ai-team/dashboard')
      setSettings(data.settings || {})
      const list = data.campaigns || []
      setCampaigns(list)
      setActiveId((prev) => prev || list[0]?.id || null)
    } catch (e) {
      showBanner('err', e?.message || 'Could not load AI Team')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadApifyRuns = useCallback(async () => {
    try {
      const data = await apiFetch('/admin/ai-team/apify/runs')
      setApifyRuns(data.runs || [])
    } catch (e) {
      showBanner('err', e?.message || 'Could not load scrape runs')
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

  useEffect(() => {
    loadDashboard()
  }, [loadDashboard])

  useEffect(() => {
    if (activeId) loadCampaign(activeId).catch((e) => showBanner('err', e?.message || 'Load failed'))
  }, [activeId, loadCampaign])

  useEffect(() => {
    if (tab === 'scrape') loadApifyRuns()
    if (tab === 'settings' && settingsSubTab === 'promo') loadPromo()
  }, [tab, settingsSubTab, loadApifyRuns, loadPromo])

  // Poll while campaign is sending
  useEffect(() => {
    if (!activeId || campaign?.status !== 'sending') return undefined
    const id = window.setInterval(() => {
      loadCampaign(activeId).catch(() => {})
      loadCampaigns().catch(() => {})
    }, 2500)
    return () => window.clearInterval(id)
  }, [activeId, campaign?.status, loadCampaign, loadCampaigns])

  // Poll scrape runs
  useEffect(() => {
    if (tab !== 'scrape') return undefined
    const running = apifyRuns.some((r) => String(r.status || '').toUpperCase() === 'RUNNING')
    if (!running) return undefined
    const id = window.setInterval(() => loadApifyRuns(), 2000)
    return () => window.clearInterval(id)
  }, [tab, apifyRuns, loadApifyRuns])

  const liveScrapeRun = apifyRuns.find((r) => String(r.status || '').toUpperCase() === 'RUNNING') || null
  const liveProgress = liveScrapeRun?.progress || null
  const liveStandsTotal = Number(liveProgress?.stands_total || liveScrapeRun?.stands_found || 0)
  const liveStandsDone = Number(liveProgress?.stands_done || 0)
  const liveEmails = Number(liveProgress?.emails_found || liveScrapeRun?.emails_found || 0)
  const livePct = liveStandsTotal > 0 ? Math.min(100, Math.round((liveStandsDone / liveStandsTotal) * 100)) : 0

  const act = async (key, fn) => {
    setBusy(key)
    try {
      await fn()
    } catch (e) {
      showBanner('err', e?.message || 'Action failed')
    } finally {
      setBusy('')
    }
  }

  const createCampaign = async () => {
    const name = newName.trim() || `Campaign ${new Date().toLocaleDateString()}`
    await act('create', async () => {
      const data = await apiFetch('/admin/ai-team/campaigns', {
        method: 'POST',
        body: JSON.stringify({ name }),
      })
      setNewName('')
      await loadCampaigns()
      setActiveId(data.campaign?.id)
      showBanner('ok', `Created “${data.campaign?.name}”`)
    })
  }

  const saveCampaign = async (partial = {}) => {
    if (!activeId || !campaign) return
    await act('save', async () => {
      const body = {
        name: campaign.name,
        subject: campaign.subject,
        body_text: campaign.body_text,
        html_template: campaign.html_template,
        ...partial,
      }
      const data = await apiFetch(`/admin/ai-team/campaigns/${activeId}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      })
      setCampaign(data.campaign)
      await loadCampaigns()
      showBanner('ok', 'Campaign saved')
    })
  }

  const deleteCampaign = async () => {
    if (!activeId) return
    if (!window.confirm('Delete this campaign and its audience?')) return
    await act('del', async () => {
      await apiFetch(`/admin/ai-team/campaigns/${activeId}`, { method: 'DELETE' })
      setActiveId(null)
      setCampaign(null)
      setRecipients([])
      const list = await loadCampaigns()
      if (list[0]?.id) setActiveId(list[0].id)
      showBanner('ok', 'Campaign deleted')
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

  const importCsvToCampaign = async () => {
    if (!activeId) {
      showBanner('err', 'Create or select a campaign first')
      return
    }
    if (!csvFile || !csvMapping.email) {
      showBanner('err', 'Upload a sheet and map the email column')
      return
    }
    await act('csv', async () => {
      const fd = new FormData()
      fd.append('file', csvFile)
      fd.append('mapping', JSON.stringify(csvMapping))
      const data = await apiUpload(`/admin/ai-team/campaigns/${activeId}/import/csv`, fd)
      showBanner('ok', `Added ${data.created || 0} (${data.skipped || 0} skipped) · ${data.total || 0} total`)
      setCsvFile(null)
      setCsvHeaders([])
      setCsvPreviewRows([])
      await loadCampaign(activeId)
      await loadCampaigns()
    })
  }

  const runPreview = async () => {
    if (!activeId) return
    await act('preview', async () => {
      // Save first so preview matches editor
      await apiFetch(`/admin/ai-team/campaigns/${activeId}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: campaign.name,
          subject: campaign.subject,
          body_text: campaign.body_text,
          html_template: campaign.html_template,
        }),
      })
      const data = await apiFetch(`/admin/ai-team/campaigns/${activeId}/preview`, {
        method: 'POST',
        body: JSON.stringify({}),
      })
      setPreview(data)
    })
  }

  const sendTest = async () => {
    if (!activeId) return
    const to = (testEmail || settings.from_email || '').trim()
    if (!to) {
      showBanner('err', 'Enter a test email address')
      return
    }
    await act('test', async () => {
      await apiFetch(`/admin/ai-team/campaigns/${activeId}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: campaign.name,
          subject: campaign.subject,
          body_text: campaign.body_text,
          html_template: campaign.html_template,
        }),
      })
      const data = await apiFetch(`/admin/ai-team/campaigns/${activeId}/test`, {
        method: 'POST',
        body: JSON.stringify({ to_email: to }),
      })
      showBanner('ok', data.message || 'Test sent')
    })
  }

  const sendAll = async () => {
    if (!activeId) return
    const pending = recipients.filter((r) => r.status === 'pending' || r.status === 'failed').length
    if (!window.confirm(`Send this campaign to ${pending || campaign?.total_count || 0} recipient(s)?`)) return
    await act('send', async () => {
      await apiFetch(`/admin/ai-team/campaigns/${activeId}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: campaign.name,
          subject: campaign.subject,
          body_text: campaign.body_text,
          html_template: campaign.html_template,
        }),
      })
      const data = await apiFetch(`/admin/ai-team/campaigns/${activeId}/send`, { method: 'POST' })
      showBanner('ok', data.message || 'Sending…')
      await loadCampaign(activeId)
      await loadCampaigns()
    })
  }

  const cancelSend = async () => {
    if (!activeId) return
    await act('cancel', async () => {
      const data = await apiFetch(`/admin/ai-team/campaigns/${activeId}/cancel`, { method: 'POST' })
      showBanner('ok', data.message || 'Cancelled')
      await loadCampaign(activeId)
      await loadCampaigns()
    })
  }

  const clearAudience = async () => {
    if (!activeId) return
    if (!window.confirm('Remove all recipients from this campaign?')) return
    await act('clear', async () => {
      const data = await apiFetch(`/admin/ai-team/campaigns/${activeId}/recipients`, { method: 'DELETE' })
      showBanner('ok', `Removed ${data.deleted || 0}`)
      await loadCampaign(activeId)
      await loadCampaigns()
    })
  }

  const startScrape = async () => {
    if (!apifyExpoUrl.trim()) {
      showBanner('err', 'Paste an expo exhibitor directory URL')
      return
    }
    await act('scrape', async () => {
      const data = await apiFetch('/admin/ai-team/scrape/directory', {
        method: 'POST',
        body: JSON.stringify({
          expo_url: apifyExpoUrl.trim(),
          follow_websites: scrapeFollowWebsites,
        }),
      })
      showBanner('ok', data.message || 'Scrape started')
      await loadApifyRuns()
    })
  }

  const startApifyActorRun = async () => {
    if (!apifyActorUrl.trim()) {
      showBanner('err', 'Paste a URL for the Apify actor run')
      return
    }
    if (!settings.apify_token_configured && !apifyToken.trim()) {
      showBanner('err', 'Save an Apify Personal API token under Settings → Apify first')
      setTab('settings')
      setSettingsSubTab('apify')
      return
    }
    await act('apify-actor', async () => {
      const data = await apiFetch('/admin/ai-team/apify/runs', {
        method: 'POST',
        body: JSON.stringify({
          expo_url: apifyActorUrl.trim(),
          actor_id: apifyActorOverride.trim() || settings.apify_exhibitor_actor_id || undefined,
        }),
      })
      showBanner('ok', data.message || `Apify run started (${data.run?.status || 'RUNNING'})`)
      await loadApifyRuns()
    })
  }

  const addScrapeToCampaign = async (runId) => {
    let cid = activeId
    if (!cid) {
      const name = window.prompt('Campaign name for these emails', `Expo scrape ${new Date().toLocaleDateString()}`)
      if (name === null) return
      const created = await apiFetch('/admin/ai-team/campaigns', {
        method: 'POST',
        body: JSON.stringify({ name: name.trim() || 'Expo scrape' }),
      })
      cid = created.campaign?.id
      setActiveId(cid)
      await loadCampaigns()
    }
    await act(`add-${runId}`, async () => {
      const data = await apiFetch(`/admin/ai-team/campaigns/${cid}/import/scrape`, {
        method: 'POST',
        body: JSON.stringify({ run_id: runId }),
      })
      showBanner('ok', `Added ${data.created || 0} emails to campaign (${data.skipped || 0} skipped)`)
      setTab('campaigns')
      await loadCampaign(cid)
      await loadCampaigns()
    })
  }

  const exportApifyRun = async (runId) => {
    await act(`export-${runId}`, async () => {
      const blob = await apiFetchBlob(`/admin/ai-team/apify/runs/${runId}/export.csv`)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `expo-emails-${String(runId).slice(0, 8)}.csv`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    })
  }

  const saveSettings = async (partial = {}) => {
    await act('settings', async () => {
      const body = {
        ...settings,
        ...partial,
        smtp_password: smtpPassword || undefined,
        resend_api_key: resendKey || undefined,
        apollo_api_key: apolloKey || undefined,
        apify_token: apifyToken || undefined,
      }
      const data = await apiFetch('/admin/ai-team/settings', { method: 'PUT', body: JSON.stringify(body) })
      setSettings(data.settings || {})
      setSmtpPassword('')
      setResendKey('')
      setApolloKey('')
      setApifyToken('')
      showBanner('ok', 'Settings saved')
    })
  }

  const runTestSmtp = async () => {
    await act('smtp-test', async () => {
      try {
        const data = await apiFetch('/admin/ai-team/test/smtp', {
          method: 'POST',
          body: JSON.stringify({
            ...settings,
            smtp_password: smtpPassword || undefined,
            to_email: settingsTestEmail || undefined,
          }),
        })
        const msg = data.message || 'SMTP OK'
        setSmtpTestResult({ ok: true, message: msg })
        showBanner('ok', msg)
      } catch (e) {
        const msg = e?.message || 'SMTP failed'
        setSmtpTestResult({ ok: false, message: msg })
        throw e
      }
    })
  }

  const runTestApify = async () => {
    setApifyTestResult(null)
    const hasUserId = !!(settings.apify_user_id || '').trim()
    if (!apifyToken.trim() && !settings.apify_token_configured) {
      const msg = hasUserId
        ? 'User ID is set, but you still need the Personal API token (starts with apify_api_).'
        : 'Paste Personal API token (apify_api_…), then click Test'
      setApifyTestResult({ ok: false, message: msg })
      showBanner('err', msg)
      return
    }
    await act('test-apify', async () => {
      try {
        const data = await apiFetch('/admin/ai-team/test/apify', {
          method: 'POST',
          body: JSON.stringify({
            apify_token: apifyToken.trim() || undefined,
            apify_user_id: (settings.apify_user_id || '').trim() || undefined,
            check_actor: false,
          }),
        })
        const saved = !!(data.token_saved && data.apify_token_configured)
        const msg = data.message || (data.username ? `Apify OK — ${data.username}` : 'Apify OK')
        if (!data.ok || !saved) {
          setApifyTestResult({ ok: false, message: msg || 'Token was not saved' })
          showBanner('err', msg || 'Apify test failed')
          return
        }
        setApifyTestResult({ ok: true, message: msg })
        setApifyToken('')
        const refreshed = await apiFetch('/admin/ai-team/settings')
        setSettings(refreshed.settings || {})
        showBanner('ok', msg)
      } catch (e) {
        const msg = e?.message || 'Apify test failed'
        setApifyTestResult({ ok: false, message: msg })
        throw e
      }
    })
  }

  const runTestApollo = async () => {
    setApolloTestResult(null)
    await act('test-apollo', async () => {
      try {
        const data = await apiFetch('/admin/ai-team/test/apollo', {
          method: 'POST',
          body: JSON.stringify({ api_key: apolloKey || undefined }),
        })
        const msg = data.message || 'Apollo OK'
        setApolloTestResult({ ok: true, message: msg })
        showBanner('ok', msg)
      } catch (e) {
        const msg = e?.message || 'Apollo test failed'
        setApolloTestResult({ ok: false, message: msg })
        throw e
      }
    })
  }

  const filteredRecipients = recipients.filter((r) => {
    if (recipientFilter === 'all') return true
    if (recipientFilter === 'opened') return !!r.opened_at
    if (recipientFilter === 'replied') return !!r.replied_at
    return r.status === recipientFilter
  })

  const sendPct = campaign?.total_count
    ? Math.min(100, Math.round(((campaign.sent_count + campaign.failed_count) / campaign.total_count) * 100))
    : 0

  if (loading && !campaigns.length && !settings.from_email) {
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
            <div className="ait-page-sub">Campaigns · scrape · send all · track</div>
          </div>
        </div>
        <div className="ait-topbar-right">
          <button type="button" className="ait-btn ghost sm" onClick={() => setHowtoOpen(true)}>
            How to use
          </button>
          <button type="button" className="ait-btn primary sm" disabled={!!busy} onClick={() => { setTab('campaigns'); createCampaign() }}>
            New campaign
          </button>
        </div>
      </div>

      {banner && <div className={`ait-msg-banner ${banner.type}`}>{banner.text}</div>}

      <div className="ait-tabs">
        {TABS.map((t) => (
          <button key={t.id} type="button" className={`ait-tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
            <i className={`ti ${t.icon}`} style={{ fontSize: 12 }} />
            {t.label}
            {t.id === 'campaigns' && campaigns.length > 0 && (
              <span className="ait-tab-badge" style={{ background: 'var(--ait-accent-dim)', color: 'var(--ait-accent)' }}>
                {campaigns.length}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="ait-content">
        {tab === 'campaigns' && (
          <div className="ait-campaign-layout">
            <aside className="ait-campaign-rail">
              <div className="ait-card" style={{ marginBottom: 0 }}>
                <div className="ait-card-hdr">
                  <span className="ait-card-title">Campaigns</span>
                </div>
                <div className="ait-card-body" style={{ padding: 12 }}>
                  <div className="ait-field" style={{ marginBottom: 8 }}>
                    <input
                      placeholder="New campaign name"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') createCampaign() }}
                    />
                  </div>
                  <button type="button" className="ait-btn primary sm" style={{ width: '100%', marginBottom: 12 }} disabled={!!busy} onClick={createCampaign}>
                    Create
                  </button>
                  <div className="ait-campaign-list">
                    {campaigns.map((c) => (
                      <button
                        key={c.id}
                        type="button"
                        className={`ait-campaign-item ${activeId === c.id ? 'active' : ''}`}
                        onClick={() => setActiveId(c.id)}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                          <strong style={{ fontSize: 13 }}>{c.name}</strong>
                          <span className={`ait-badge ${statusBadge(c.status)}`}>{c.status}</span>
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--ait-text3)', marginTop: 4 }}>
                          {c.sent_count}/{c.total_count} sent · {timeAgo(c.updated_at)}
                        </div>
                      </button>
                    ))}
                    {!campaigns.length && (
                      <div className="ait-empty" style={{ padding: 20 }}>
                        <strong>No campaigns yet</strong>
                        Create one, then edit template + upload Excel.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </aside>

            <div className="ait-campaign-main">
              {!campaign ? (
                <div className="ait-empty">
                  <strong>Select or create a campaign</strong>
                  Name → template → Excel → preview → Send all
                </div>
              ) : (
                <>
                  <div className="ait-toolbar">
                    <div className="ait-toolbar-left">
                      <span className={`ait-badge ${statusBadge(campaign.status)}`}>{campaign.status}</span>
                      <span className="ait-toolbar-meta">
                        {campaign.sent_count}/{campaign.total_count} sent
                        {campaign.failed_count ? ` · ${campaign.failed_count} failed` : ''}
                        {campaign.opened_count ? ` · ${campaign.opened_count} opened` : ''}
                      </span>
                    </div>
                    <div className="ait-toolbar-right">
                      <button type="button" className="ait-btn sm" disabled={!!busy || campaign.status === 'sending'} onClick={() => saveCampaign()}>
                        Save
                      </button>
                      <button type="button" className="ait-btn danger sm" disabled={!!busy || campaign.status === 'sending'} onClick={deleteCampaign}>
                        Delete
                      </button>
                    </div>
                  </div>

                  {campaign.status === 'sending' && (
                    <div className="ait-msg-banner ok" style={{ margin: '0 0 14px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                        <strong>Sending… {campaign.sent_count + campaign.failed_count}/{campaign.total_count}</strong>
                        <button type="button" className="ait-btn danger xs" disabled={!!busy} onClick={cancelSend}>Cancel</button>
                      </div>
                      <div style={{ marginTop: 8, height: 8, background: 'rgba(0,0,0,0.08)', borderRadius: 999, overflow: 'hidden' }}>
                        <div style={{ width: `${sendPct}%`, height: '100%', background: 'var(--ait-accent)', transition: 'width .3s' }} />
                      </div>
                    </div>
                  )}

                  {/* 1 Name */}
                  <div className="ait-card">
                    <div className="ait-card-hdr"><span className="ait-card-title">1 · Campaign name</span></div>
                    <div className="ait-card-body">
                      <div className="ait-field" style={{ marginBottom: 0 }}>
                        <input
                          value={campaign.name || ''}
                          disabled={campaign.status === 'sending'}
                          onChange={(e) => setCampaign({ ...campaign, name: e.target.value })}
                        />
                      </div>
                    </div>
                  </div>

                  {/* 2 Template */}
                  <div className="ait-card">
                    <div className="ait-card-hdr">
                      <span className="ait-card-title">2 · Email template</span>
                      <div className="ait-chip-row" style={{ margin: 0 }}>
                        {MERGE_TAGS.map((t) => (
                          <button
                            key={t}
                            type="button"
                            className="ait-chip"
                            disabled={campaign.status === 'sending'}
                            onClick={() => insertTag(campaign.body_text, (v) => setCampaign({ ...campaign, body_text: v }), t)}
                          >
                            {`{{${t}}}`}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="ait-card-body">
                      <div className="ait-field">
                        <label>Subject</label>
                        <input
                          value={campaign.subject || ''}
                          disabled={campaign.status === 'sending'}
                          onChange={(e) => setCampaign({ ...campaign, subject: e.target.value })}
                          placeholder="Quick idea for {{company}}"
                        />
                      </div>
                      <div className="ait-field">
                        <label>Body text (plain — merge tags work)</label>
                        <textarea
                          style={{ minHeight: 140 }}
                          value={campaign.body_text || ''}
                          disabled={campaign.status === 'sending'}
                          onChange={(e) => setCampaign({ ...campaign, body_text: e.target.value })}
                        />
                      </div>
                      <div className="ait-field" style={{ marginBottom: 0 }}>
                        <label>HTML wrapper (optional — use {'{{body}}'} for text block)</label>
                        <textarea
                          className="ait-code-editor"
                          style={{ minHeight: 160 }}
                          value={campaign.html_template || ''}
                          disabled={campaign.status === 'sending'}
                          onChange={(e) => setCampaign({ ...campaign, html_template: e.target.value })}
                        />
                      </div>
                    </div>
                  </div>

                  {/* 3 Audience */}
                  <div className="ait-card">
                    <div className="ait-card-hdr">
                      <span className="ait-card-title">3 · Audience · {campaign.total_count} emails</span>
                      <div className="ait-btn-row" style={{ margin: 0 }}>
                        <button type="button" className="ait-btn xs" onClick={() => setTab('scrape')}>From scrape</button>
                        <button type="button" className="ait-btn danger xs" disabled={!recipients.length || campaign.status === 'sending'} onClick={clearAudience}>
                          Clear
                        </button>
                      </div>
                    </div>
                    <div className="ait-card-body">
                      <div
                        className={`ait-dropzone ${csvDrag ? 'active' : ''}`}
                        onDragOver={(e) => { e.preventDefault(); setCsvDrag(true) }}
                        onDragLeave={() => setCsvDrag(false)}
                        onDrop={(e) => {
                          e.preventDefault()
                          setCsvDrag(false)
                          const f = e.dataTransfer.files?.[0]
                          if (f) parseCsvFile(f).catch((err) => showBanner('err', err?.message || 'Parse failed'))
                        }}
                        onClick={() => document.getElementById('ait-campaign-csv')?.click()}
                      >
                        <input
                          id="ait-campaign-csv"
                          type="file"
                          accept=".csv,.xlsx,text/csv"
                          style={{ display: 'none' }}
                          onChange={(e) => {
                            const f = e.target.files?.[0]
                            if (f) parseCsvFile(f).catch((err) => showBanner('err', err?.message || 'Parse failed'))
                          }}
                        />
                        <div style={{ fontWeight: 600 }}>{csvFile ? csvFile.name : 'Drop Excel/CSV here or click to upload'}</div>
                        <div style={{ fontSize: 12, color: 'var(--ait-text3)', marginTop: 6 }}>
                          Needs an email column. Save as CSV from Excel if .xlsx upload fails.
                        </div>
                      </div>

                      {csvHeaders.length > 0 && (
                        <>
                          <div className="ait-fg-3" style={{ marginTop: 14 }}>
                            {CSV_MAP_FIELDS.map((f) => (
                              <div className="ait-field" key={f.key}>
                                <label>{f.label}{f.required ? ' *' : ''}</label>
                                <select
                                  value={csvMapping[f.key] || ''}
                                  onChange={(e) => setCsvMapping({ ...csvMapping, [f.key]: e.target.value })}
                                >
                                  <option value="">— skip —</option>
                                  {csvHeaders.map((h) => <option key={h} value={h}>{h}</option>)}
                                </select>
                              </div>
                            ))}
                          </div>
                          <div className="ait-btn-row">
                            <button type="button" className="ait-btn primary sm" disabled={!!busy || !csvMapping.email} onClick={importCsvToCampaign}>
                              Add {csvTotal} rows to campaign
                            </button>
                          </div>
                          <div className="ait-table-wrap">
                            <table className="ait-tbl ait-tbl-compact">
                              <thead><tr>{csvHeaders.map((h) => <th key={h}>{h}</th>)}</tr></thead>
                              <tbody>
                                {csvPreviewRows.map((row, i) => (
                                  <tr key={i}>{csvHeaders.map((h) => <td key={h}>{row[h] || '—'}</td>)}</tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </>
                      )}
                    </div>
                  </div>

                  {/* 4 Preview + send */}
                  <div className="ait-card">
                    <div className="ait-card-hdr"><span className="ait-card-title">4 · Preview & send</span></div>
                    <div className="ait-card-body">
                      <div className="ait-fg-2">
                        <div className="ait-field">
                          <label>Send test to</label>
                          <input
                            type="email"
                            placeholder={settings.from_email || 'you@company.com'}
                            value={testEmail}
                            onChange={(e) => setTestEmail(e.target.value)}
                          />
                        </div>
                        <div className="ait-field">
                          <label>From</label>
                          <input disabled value={settings.from_email || '— set in Settings —'} />
                        </div>
                      </div>
                      <div className="ait-btn-row">
                        <button type="button" className="ait-btn sm" disabled={!!busy} onClick={runPreview}>Preview</button>
                        <button type="button" className="ait-btn sm" disabled={!!busy} onClick={sendTest}>Send test</button>
                        <button
                          type="button"
                          className="ait-btn primary"
                          disabled={!!busy || campaign.status === 'sending' || !campaign.total_count}
                          onClick={sendAll}
                        >
                          Send all ({campaign.total_count || 0})
                        </button>
                      </div>
                      <p className="ait-hint">
                        One template × every row. Merge tags like {'{{first_name}}'} personalise each message. Sending runs in the background.
                      </p>
                    </div>
                  </div>

                  {/* 5 Results */}
                  <div className="ait-card">
                    <div className="ait-card-hdr">
                      <span className="ait-card-title">5 · Results</span>
                      <div className="ait-seg">
                        {[
                          ['all', 'All'],
                          ['pending', 'Pending'],
                          ['sent', 'Sent'],
                          ['opened', 'Opened'],
                          ['failed', 'Failed'],
                        ].map(([id, label]) => (
                          <button key={id} type="button" className={recipientFilter === id ? 'active' : ''} onClick={() => setRecipientFilter(id)}>
                            {label}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="ait-table-wrap">
                      <table className="ait-tbl">
                        <thead>
                          <tr>
                            <th>Email</th>
                            <th>Company</th>
                            <th>Status</th>
                            <th>Sent</th>
                            <th>Opened</th>
                            <th>Error</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredRecipients.map((r) => (
                            <tr key={r.id}>
                              <td>
                                <strong>{r.full_name || r.email}</strong>
                                <div style={{ fontSize: 11, color: 'var(--ait-text3)' }}>{r.email}</div>
                              </td>
                              <td>{r.company_name || '—'}</td>
                              <td><span className={`ait-badge ${statusBadge(r.status)}`}>{r.status}</span></td>
                              <td style={{ fontSize: 12, color: 'var(--ait-text3)' }}>{timeAgo(r.sent_at)}</td>
                              <td style={{ fontSize: 12, color: 'var(--ait-text3)' }}>{timeAgo(r.opened_at)}</td>
                              <td className="ait-ellipsis" title={r.last_error || ''}>{r.last_error || '—'}</td>
                            </tr>
                          ))}
                          {!filteredRecipients.length && (
                            <tr>
                              <td colSpan={6} style={{ textAlign: 'center', color: 'var(--ait-text3)', padding: 28 }}>
                                No recipients yet — upload Excel or add from Scrape.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {tab === 'scrape' && (
          <div className="ait-card">
            <div className="ait-card-hdr">
              <span className="ait-card-title">Scrape exhibitor emails</span>
              <button type="button" className="ait-btn sm" disabled={!!busy} onClick={() => loadApifyRuns()}>Refresh</button>
            </div>
            <div className="ait-card-body">
              <div className="ait-msg-banner ok" style={{ margin: '0 0 12px' }}>
                Built-in scrape — no Apify token needed for Easyfairs (e.g. London Packaging Week).
                When done, click <strong>Add to campaign</strong>.
              </div>
              <div className="ait-field">
                <label>Expo exhibitor URL</label>
                <input value={apifyExpoUrl} onChange={(e) => setApifyExpoUrl(e.target.value)} placeholder="https://www.londonpackagingweek.com/exhibitors/" />
              </div>
              <label className="ait-check" style={{ marginBottom: 12 }}>
                <input type="checkbox" checked={scrapeFollowWebsites} onChange={(e) => setScrapeFollowWebsites(e.target.checked)} />
                Also scrape company websites (recommended)
              </label>
              <div className="ait-btn-row">
                <button type="button" className="ait-btn primary sm" disabled={!!busy || !apifyExpoUrl.trim()} onClick={startScrape}>
                  Scrape exhibitors
                </button>
                <button type="button" className="ait-btn danger sm" disabled={!!busy || !apifyRuns.length}
                  onClick={() => act('purge', async () => {
                    if (!window.confirm(`Remove all ${apifyRuns.length} scrape run(s)?`)) return
                    await apiFetch('/admin/ai-team/apify/runs', { method: 'DELETE' })
                    setApifyPreview(null)
                    await loadApifyRuns()
                  })}
                >
                  Remove all
                </button>
              </div>

              {liveScrapeRun && (
                <div className="ait-msg-banner ok" style={{ margin: '12px 0' }}>
                  <strong>Live:</strong> {liveProgress?.message || 'Running…'} · stands {liveStandsDone}/{liveStandsTotal || '—'} · emails {liveEmails} · {livePct}%
                  <div style={{ marginTop: 8, height: 8, background: 'rgba(0,0,0,0.08)', borderRadius: 999, overflow: 'hidden' }}>
                    <div style={{ width: `${livePct}%`, height: '100%', background: 'var(--ait-green)' }} />
                  </div>
                </div>
              )}

              <div className="ait-table-wrap" style={{ marginTop: 12 }}>
                <table className="ait-tbl ait-tbl-compact">
                  <thead>
                    <tr><th>Status</th><th>URL</th><th>Stands</th><th>Emails</th><th /></tr>
                  </thead>
                  <tbody>
                    {apifyRuns.map((run) => (
                      <tr key={run.id}>
                        <td><span className={`ait-badge ${run.status === 'SUCCEEDED' ? 'b-sent' : 'b-pending'}`}>{run.status}</span></td>
                        <td className="ait-ellipsis" title={run.expo_url}>{run.expo_url}</td>
                        <td>{run.stands_found ?? run.item_count ?? 0}</td>
                        <td>{run.emails_found ?? 0}</td>
                        <td>
                          <div className="ait-btn-row" style={{ margin: 0 }}>
                            <button type="button" className="ait-btn xs" disabled={!!busy || run.status !== 'SUCCEEDED'}
                              onClick={() => act(`view-${run.id}`, async () => {
                                const data = await apiFetch(`/admin/ai-team/apify/runs/${run.id}/preview?limit=5000`)
                                setApifyPreview(data)
                              })}
                            >View</button>
                            <button type="button" className="ait-btn xs" disabled={!!busy || run.status !== 'SUCCEEDED'} onClick={() => exportApifyRun(run.id)}>Excel</button>
                            <button type="button" className="ait-btn xs primary" disabled={!!busy || run.status !== 'SUCCEEDED'} onClick={() => addScrapeToCampaign(run.id)}>
                              Add to campaign
                            </button>
                            <button type="button" className="ait-btn xs danger" disabled={!!busy || String(run.status).toUpperCase() === 'RUNNING'}
                              onClick={() => act(`del-${run.id}`, async () => {
                                if (!window.confirm('Remove this scrape run?')) return
                                await apiFetch(`/admin/ai-team/apify/runs/${run.id}`, { method: 'DELETE' })
                                await loadApifyRuns()
                              })}
                            >×</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {!apifyRuns.length && (
                      <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--ait-text3)', padding: 20 }}>No scrapes yet</td></tr>
                    )}
                  </tbody>
                </table>
              </div>

              {apifyPreview && (
                <div style={{ marginTop: 12 }}>
                  <div className="ait-toolbar">
                    <span className="ait-toolbar-meta">{apifyPreview.contacts_with_email || 0} emails</span>
                    <button type="button" className="ait-btn xs" onClick={() => setApifyPreview(null)}>Close</button>
                  </div>
                  <div className="ait-table-wrap" style={{ maxHeight: 320, overflow: 'auto' }}>
                    <table className="ait-tbl ait-tbl-compact">
                      <thead><tr><th>#</th><th>Email</th><th>Company</th></tr></thead>
                      <tbody>
                        {(apifyPreview.preview || []).map((c, i) => (
                          <tr key={`${c.email}-${i}`}>
                            <td>{i + 1}</td>
                            <td>{c.email}</td>
                            <td>{c.company_name || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--ait-border)' }}>
                <div className="ait-card-title" style={{ marginBottom: 8 }}>Apify actor run (other sites)</div>
                <p className="ait-hint" style={{ marginTop: 0 }}>
                  Uses the token from <strong>Settings → Apify</strong>. For non-Easyfairs directories that need a Store actor.
                </p>
                <div className="ait-field">
                  <label>Target URL</label>
                  <input value={apifyActorUrl} onChange={(e) => setApifyActorUrl(e.target.value)} placeholder="https://example.com/exhibitors/" />
                </div>
                <div className="ait-field">
                  <label>Actor ID (optional override)</label>
                  <input
                    value={apifyActorOverride}
                    onChange={(e) => setApifyActorOverride(e.target.value)}
                    placeholder={settings.apify_exhibitor_actor_id || 'username~actor-name'}
                  />
                </div>
                <div className="ait-btn-row">
                  <button type="button" className="ait-btn primary sm" disabled={!!busy || !apifyActorUrl.trim()} onClick={startApifyActorRun}>
                    Start Apify run
                  </button>
                  <button type="button" className="ait-btn sm" onClick={() => { setTab('settings'); setSettingsSubTab('apify') }}>
                    Apify settings
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {tab === 'settings' && (
          <div className="ait-card ait-apify-panel">
            <div className="ait-card-hdr ait-apify-hdr">
              <span className="ait-card-title">Settings</span>
              <div className="ait-subtabs">
                {SETTINGS_SUB_TABS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`ait-subtab ${settingsSubTab === t.id ? 'active' : ''}`}
                    onClick={() => setSettingsSubTab(t.id)}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <button type="button" className="ait-btn primary sm" disabled={!!busy} onClick={() => saveSettings()}>Save</button>
            </div>
            <div className="ait-card-body ait-apify-body ait-compact">
              {settingsSubTab === 'sending' && (
                <>
                  <div className="ait-conn-block ait-conn-compact">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span className={`ait-dot ${smtpTestResult?.ok || settings.smtp_configured ? 'on' : 'off'}`} />
                      <strong style={{ fontSize: 13 }}>
                        {smtpTestResult ? (smtpTestResult.ok ? 'SMTP OK' : 'SMTP failed') : (settings.smtp_configured ? 'SMTP configured' : 'Not configured')}
                      </strong>
                    </div>
                    <button type="button" className="ait-btn xs" disabled={!!busy} onClick={runTestSmtp}>Test SMTP</button>
                  </div>
                  {smtpTestResult && (
                    <div className={`ait-msg-banner ${smtpTestResult.ok ? 'ok' : 'err'}`} style={{ margin: '0 0 12px' }}>
                      {smtpTestResult.message}
                    </div>
                  )}
                  <div className="ait-fg-3">
                    <div className="ait-field">
                      <label>Provider</label>
                      <select value={settings.email_delivery_provider || 'smtp'} onChange={(e) => setSettings({ ...settings, email_delivery_provider: e.target.value })}>
                        <option value="smtp">SMTP</option>
                        <option value="resend">Resend</option>
                      </select>
                    </div>
                    <div className="ait-field"><label>From name</label><input value={settings.sender_name || ''} onChange={(e) => setSettings({ ...settings, sender_name: e.target.value })} /></div>
                    <div className="ait-field"><label>From email</label><input value={settings.from_email || ''} onChange={(e) => setSettings({ ...settings, from_email: e.target.value })} /></div>
                  </div>
                  <div className="ait-fg-2">
                    <div className="ait-field"><label>Reply-to</label><input value={settings.reply_to_email || ''} onChange={(e) => setSettings({ ...settings, reply_to_email: e.target.value })} /></div>
                    <div className="ait-field"><label>Test email</label><input type="email" value={settingsTestEmail} onChange={(e) => setSettingsTestEmail(e.target.value)} placeholder="you@company.com" /></div>
                  </div>
                  <div className="ait-fg-3">
                    <div className="ait-field"><label>SMTP host</label><input value={settings.smtp_host || ''} onChange={(e) => setSettings({ ...settings, smtp_host: e.target.value })} /></div>
                    <div className="ait-field"><label>Port</label><input type="number" value={settings.smtp_port || 587} onChange={(e) => setSettings({ ...settings, smtp_port: +e.target.value })} /></div>
                    <div className="ait-field"><label>Username</label><input value={settings.smtp_username || ''} onChange={(e) => setSettings({ ...settings, smtp_username: e.target.value })} /></div>
                  </div>
                  <div className="ait-fg-2">
                    <div className="ait-field"><label>Password</label><input type="password" placeholder={settings.smtp_password_configured ? '••••••••' : ''} value={smtpPassword} onChange={(e) => setSmtpPassword(e.target.value)} /></div>
                    <div className="ait-field"><label>Resend API key</label><input type="password" placeholder={settings.resend_api_key_configured || settings.resend_configured ? '••••••••' : 're_…'} value={resendKey} onChange={(e) => setResendKey(e.target.value)} /></div>
                  </div>
                  <div className="ait-fg-2">
                    <div className="ait-field"><label>Resend sending domain</label><input value={settings.resend_sending_domain || ''} onChange={(e) => setSettings({ ...settings, resend_sending_domain: e.target.value })} placeholder="outreach.voxbulk.com" /></div>
                    <div className="ait-field"><label>Max emails / day</label><input type="number" value={settings.max_emails_per_day || 200} onChange={(e) => setSettings({ ...settings, max_emails_per_day: +e.target.value })} /></div>
                  </div>
                  <p className="ait-hint">Campaigns use this From address. Raise the daily cap before large Send all runs.</p>
                </>
              )}

              {settingsSubTab === 'apify' && (
                <>
                  <div className="ait-conn-block ait-conn-compact">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span className={`ait-dot ${apifyTestResult?.ok || settings.apify_token_configured ? 'on' : 'off'}`} />
                      <strong style={{ fontSize: 13 }}>
                        {apifyTestResult ? (apifyTestResult.ok ? 'Connected' : 'Failed') : (settings.apify_token_configured ? 'Token saved' : 'Not connected')}
                      </strong>
                    </div>
                    <div className="ait-btn-row" style={{ margin: 0 }}>
                      <button type="button" className="ait-btn xs" disabled={!!busy} onClick={runTestApify}>Test</button>
                      <button type="button" className="ait-btn xs primary" disabled={!!busy} onClick={() => saveSettings()}>Save</button>
                    </div>
                  </div>
                  {apifyTestResult && (
                    <div className={`ait-msg-banner ${apifyTestResult.ok ? 'ok' : 'err'}`} style={{ margin: '0 0 10px' }}>
                      {apifyTestResult.ok ? 'OK — ' : 'FAIL — '}{apifyTestResult.message}
                    </div>
                  )}
                  <div className="ait-fg-2">
                    <div className="ait-field">
                      <label>User ID</label>
                      <input
                        value={settings.apify_user_id || ''}
                        onChange={(e) => setSettings({ ...settings, apify_user_id: e.target.value })}
                        placeholder="from Apify account (e.g. 346ec9…)"
                      />
                    </div>
                    <div className="ait-field">
                      <label>Personal API token</label>
                      <input type="password" placeholder={settings.apify_token_configured ? '••••••••' : 'apify_api_…'} value={apifyToken} onChange={(e) => setApifyToken(e.target.value)} />
                    </div>
                    <div className="ait-field" style={{ gridColumn: '1 / -1' }}>
                      <label>Exhibitor actor ID</label>
                      <input value={settings.apify_exhibitor_actor_id || ''} onChange={(e) => setSettings({ ...settings, apify_exhibitor_actor_id: e.target.value })} placeholder="username~actor-name" />
                    </div>
                  </div>
                  <div className="ait-chip-row">
                    {SUGGESTED_ACTORS.map((a) => (
                      <button key={a.id} type="button" className="ait-chip" title={a.note} onClick={() => setSettings({ ...settings, apify_exhibitor_actor_id: a.id })}>
                        {a.label}
                      </button>
                    ))}
                  </div>
                  <div className="ait-field" style={{ marginTop: 8 }}>
                    <label>Second actor (optional)</label>
                    <input value={settings.apify_contact_actor_id || ''} onChange={(e) => setSettings({ ...settings, apify_contact_actor_id: e.target.value })} placeholder="optional" />
                  </div>
                  <div className="ait-msg-banner ok" style={{ margin: '0 0 10px' }}>
                    <strong>User ID</strong> = account id. <strong>Personal API token</strong> = secret starting with <code>apify_api_</code>. Only the token connects the API.
                  </div>
                  <p className="ait-hint">
                    Token: <a href="https://console.apify.com/settings/integrations" target="_blank" rel="noreferrer">console.apify.com/settings/integrations</a>
                    {' '}→ Personal API tokens.
                  </p>
                </>
              )}

              {settingsSubTab === 'apollo' && (
                <>
                  <div className="ait-conn-block ait-conn-compact">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span className={`ait-dot ${apolloTestResult?.ok || settings.apollo_connected || settings.apollo_api_key_configured ? 'on' : 'off'}`} />
                      <strong style={{ fontSize: 13 }}>
                        {apolloTestResult ? (apolloTestResult.ok ? 'Connected' : 'Failed') : (settings.apollo_api_key_configured ? 'API key saved' : 'Not connected')}
                      </strong>
                    </div>
                    <button type="button" className="ait-btn xs" disabled={!!busy} onClick={runTestApollo}>Test</button>
                  </div>
                  {apolloTestResult && (
                    <div className={`ait-msg-banner ${apolloTestResult.ok ? 'ok' : 'err'}`} style={{ margin: '0 0 10px' }}>
                      {apolloTestResult.message}
                    </div>
                  )}
                  <div className="ait-fg-2">
                    <div className="ait-field">
                      <label>API key</label>
                      <input type="password" placeholder={settings.apollo_api_key_configured ? '••••••••' : 'apollo_api_…'} value={apolloKey} onChange={(e) => setApolloKey(e.target.value)} />
                    </div>
                    <div className="ait-field">
                      <label>Credit alert at</label>
                      <input type="number" value={settings.apollo_credit_alert_at || 800} onChange={(e) => setSettings({ ...settings, apollo_credit_alert_at: +e.target.value })} />
                    </div>
                  </div>
                  <div className="section-lbl" style={{ margin: '12px 0 8px', fontSize: 11, fontWeight: 700, color: 'var(--ait-text3)', textTransform: 'uppercase' }}>Search profile</div>
                  <div className="ait-fg-3">
                    <div className="ait-field"><label>Sector</label><input value={settings.search_sector || ''} onChange={(e) => setSettings({ ...settings, search_sector: e.target.value })} /></div>
                    <div className="ait-field"><label>Country</label><input value={settings.search_country || ''} onChange={(e) => setSettings({ ...settings, search_country: e.target.value })} /></div>
                    <div className="ait-field"><label>Company size</label><input value={settings.search_company_size || ''} onChange={(e) => setSettings({ ...settings, search_company_size: e.target.value })} /></div>
                  </div>
                  <div className="ait-fg-2">
                    <div className="ait-field"><label>Job title keywords</label><input value={settings.search_title_keywords || ''} onChange={(e) => setSettings({ ...settings, search_title_keywords: e.target.value })} /></div>
                    <div className="ait-field"><label>City / region</label><input value={settings.search_city_region || ''} onChange={(e) => setSettings({ ...settings, search_city_region: e.target.value })} /></div>
                  </div>
                  <div className="ait-fg-2">
                    <div className="ait-field"><label>Max per run</label><input type="number" value={settings.search_max_per_run || 20} onChange={(e) => setSettings({ ...settings, search_max_per_run: +e.target.value })} /></div>
                    <div className="ait-field"><label>Min match score</label><input type="number" value={settings.search_min_score || 60} onChange={(e) => setSettings({ ...settings, search_min_score: +e.target.value })} /></div>
                  </div>
                  <p className="ait-hint">Apollo is optional. Campaigns mainly use Excel / scrape audiences.</p>
                </>
              )}

              {settingsSubTab === 'ai' && (
                <>
                  <div className="ait-fg-3">
                    <div className="ait-field"><label>Tone</label>
                      <select value={settings.email_tone || 'direct'} onChange={(e) => setSettings({ ...settings, email_tone: e.target.value })}>
                        <option value="direct">Direct</option>
                        <option value="friendly">Friendly</option>
                        <option value="formal">Formal</option>
                      </select>
                    </div>
                    <div className="ait-field"><label>Max words</label><input type="number" value={settings.email_max_words || 120} onChange={(e) => setSettings({ ...settings, email_max_words: +e.target.value })} /></div>
                    <div className="ait-field"><label>Language</label><input value={settings.email_language || 'en'} onChange={(e) => setSettings({ ...settings, email_language: e.target.value })} /></div>
                  </div>
                  <div className="ait-fg-2">
                    <div className="ait-field"><label>Follow-up after (days)</label><input type="number" value={settings.followup_after_days || 3} onChange={(e) => setSettings({ ...settings, followup_after_days: +e.target.value })} /></div>
                    <div className="ait-field"><label>Max follow-ups</label><input type="number" value={settings.max_followups || 2} onChange={(e) => setSettings({ ...settings, max_followups: +e.target.value })} /></div>
                  </div>
                  <div className="ait-field">
                    <label>Writing instruction</label>
                    <textarea style={{ minHeight: 88 }} value={settings.writing_instruction || ''} onChange={(e) => setSettings({ ...settings, writing_instruction: e.target.value })} placeholder="Short cold email for expo exhibitors…" />
                  </div>
                  <div className="ait-field">
                    <label>Signature</label>
                    <textarea style={{ minHeight: 56 }} value={settings.email_signature || ''} onChange={(e) => setSettings({ ...settings, email_signature: e.target.value })} />
                  </div>
                  <div className="ait-field">
                    <label>Default HTML template (new campaigns copy this)</label>
                    <textarea className="ait-code-editor" style={{ minHeight: 160 }} value={settings.email_html_template || ''} onChange={(e) => setSettings({ ...settings, email_html_template: e.target.value })} />
                  </div>
                  <div className="ait-toggle-grid">
                    {[
                      ['auto_draft_emails', 'Auto-draft'],
                      ['auto_followup', 'Auto follow-up'],
                      ['auto_send_without_approval', 'Auto-send (legacy)'],
                      ['agent_paused', 'Pause agent'],
                    ].map(([key, label]) => (
                      <label key={key} className="ait-check">
                        <input type="checkbox" checked={!!settings[key]} onChange={(e) => setSettings({ ...settings, [key]: e.target.checked })} />
                        {label}
                      </label>
                    ))}
                  </div>
                  <div className="ait-btn-row">
                    <button type="button" className="ait-btn sm" disabled={!!busy}
                      onClick={() => act('followups', () => apiFetch('/admin/ai-team/followups/run', { method: 'POST' }).then((d) => showBanner('ok', `Follow-ups sent: ${d.sent || 0}`)))}
                    >
                      Run follow-ups
                    </button>
                  </div>
                </>
              )}

              {settingsSubTab === 'promo' && (
                <>
                  <div className="ait-fg-2">
                    <div className="ait-field"><label>Code prefix</label><input value={settings.promo_code_prefix || 'TRIAL'} onChange={(e) => setSettings({ ...settings, promo_code_prefix: e.target.value })} /></div>
                    <div className="ait-field"><label>Offer type</label>
                      <select value={settings.promo_offer_type || 'expo'} onChange={(e) => setSettings({ ...settings, promo_offer_type: e.target.value })}>
                        <option value="expo">Expo free usage</option>
                        <option value="survey_credits">Free survey contacts</option>
                        <option value="interview_credits">Free interviews</option>
                        <option value="dental_trial">Subscription trial</option>
                      </select>
                    </div>
                  </div>
                  <div className="ait-fg-3">
                    <div className="ait-field"><label>Value</label><input type="number" value={settings.promo_value || 50} onChange={(e) => setSettings({ ...settings, promo_value: +e.target.value })} /></div>
                    <div className="ait-field"><label>Expiry (days)</label><input type="number" value={settings.promo_expiry_days || 14} onChange={(e) => setSettings({ ...settings, promo_expiry_days: +e.target.value })} /></div>
                    <div className="ait-field"><label>Max uses</label><input type="number" value={settings.promo_max_uses || 1} onChange={(e) => setSettings({ ...settings, promo_max_uses: +e.target.value })} /></div>
                  </div>
                  <div className="ait-btn-row">
                    <button type="button" className="ait-btn primary sm" disabled={!!busy} onClick={() => saveSettings()}>Save promo defaults</button>
                    <Link to="/marketing/promo-offers" className="ait-btn sm">All promo offers →</Link>
                  </div>
                  <div className="section-lbl" style={{ margin: '16px 0 8px', fontSize: 11, fontWeight: 700, color: 'var(--ait-text3)', textTransform: 'uppercase' }}>Recent codes</div>
                  <div className="ait-table-wrap">
                    <table className="ait-tbl ait-tbl-compact">
                      <thead><tr><th>Code</th><th>Prospect</th><th>Offer</th><th>Expires</th><th>Status</th></tr></thead>
                      <tbody>
                        {(promoCodes || []).slice(0, 40).map((p) => (
                          <tr key={p.id || p.code}>
                            <td><span className="ait-promo-pill">{p.code}</span></td>
                            <td>{p.prospect_email || p.prospect_name || '—'}</td>
                            <td>{p.offer_type || p.name || '—'}</td>
                            <td style={{ fontSize: 11, color: 'var(--ait-text3)' }}>{p.expires_at ? timeAgo(p.expires_at) : '—'}</td>
                            <td><span className={`ait-badge ${p.is_active === false ? 'b-rejected' : 'b-sent'}`}>{p.is_active === false ? 'off' : 'active'}</span></td>
                          </tr>
                        ))}
                        {!promoCodes.length && (
                          <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--ait-text3)', padding: 16 }}>No promo codes yet</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {preview && (
        <div className="ait-modal-backdrop" onClick={() => setPreview(null)}>
          <div className="ait-modal ait-modal-wide" onClick={(e) => e.stopPropagation()}>
            <div className="ait-modal-hdr">
              <div>
                <h3>{preview.subject}</h3>
                <div style={{ fontSize: 12, color: 'var(--ait-text3)', marginTop: 4 }}>
                  {preview.sample ? 'Sample data' : `To ${preview.recipient?.email}`}
                </div>
              </div>
              <button type="button" className="ait-btn ghost sm" onClick={() => setPreview(null)}>Close</button>
            </div>
            <iframe title="preview" className="ait-html-preview" srcDoc={preview.html || ''} />
            <div className="ait-email-preview" style={{ marginTop: 12 }}>{preview.body_text || preview.text}</div>
          </div>
        </div>
      )}

      {howtoOpen && (
        <div className="ait-modal-backdrop" onClick={() => setHowtoOpen(false)}>
          <div className="ait-modal" onClick={(e) => e.stopPropagation()}>
            <div className="ait-modal-hdr">
              <h3>How to use</h3>
              <button type="button" className="ait-btn ghost sm" onClick={() => setHowtoOpen(false)}>Close</button>
            </div>
            <ol style={{ margin: 0, paddingLeft: 18, color: 'var(--ait-text2)', lineHeight: 1.6, fontSize: 13 }}>
              <li><strong>Settings</strong> — Sending (SMTP), Apify, Apollo, AI, Promo — all under one tab.</li>
              <li><strong>Campaigns</strong> — name → template → Excel → preview → Send all.</li>
              <li><strong>Scrape</strong> — Easyfairs built-in, or Apify actor for other sites → Add to campaign.</li>
              <li><strong>Preview</strong> / send a test, then <strong>Send all</strong>.</li>
            </ol>
            <p className="ait-hint" style={{ marginTop: 14 }}>
              Merge tags: {'{{first_name}}'}, {'{{company}}'}. Results stay on the campaign page.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
