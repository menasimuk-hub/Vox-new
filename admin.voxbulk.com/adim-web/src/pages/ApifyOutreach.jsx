import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch, apiFetchBlob, apiUpload } from '../lib/api'
import './ai-team.css'

const TABS = [
  { id: 'campaigns', label: 'Campaigns', icon: 'ti-send' },
  { id: 'tracking', label: 'Tracking', icon: 'ti-chart-bar' },
  { id: 'templates', label: 'Templates', icon: 'ti-template' },
  { id: 'scrape', label: 'Scrape', icon: 'ti-world' },
  { id: 'apify', label: 'Apify API', icon: 'ti-key' },
  { id: 'sending', label: 'Sending', icon: 'ti-mail' },
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

const SUGGESTED_ACTORS = [
  { id: 'vdrmota~contact-info-scraper', label: 'Contact info', note: 'Emails/phones from websites' },
  { id: 'foo121~website-contact-scraper', label: 'Website email', note: 'Bulk website emails' },
  { id: 'goat255~website-contact-scraper', label: 'Contact pages', note: 'Homepage + contact pages' },
]

const DEFAULT_MERGE = [
  'first_name', 'last_name', 'company', 'company_name', 'job_title',
  'email', 'sector', 'country_code', 'promo_code', 'signup_url', 'trial_url', 'body',
]

function guessCsvMapping(headers) {
  const norm = (h) => String(h || '').toLowerCase().replace(/[^a-z0-9]+/g, '_')
  const map = {}
  const rules = [
    ['email', ['email', 'e_mail', 'email_address']],
    ['first_name', ['first_name', 'firstname', 'first', 'given_name']],
    ['last_name', ['last_name', 'lastname', 'last', 'surname', 'family_name']],
    ['job_title', ['job_title', 'title', 'role', 'position']],
    ['company_name', ['company', 'company_name', 'organization', 'org', 'stand_name']],
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
    draft: 'b-pending', sending: 'b-opened', sent: 'b-sent',
    cancelled: 'b-rejected', failed: 'b-rejected', pending: 'b-pending',
  }
  return map[status] || 'b-pending'
}

function insertAtEnd(value, setValue, tag) {
  setValue(`${value || ''}{{${tag}}}`)
}

export default function ApifyOutreach() {
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

  const [templates, setTemplates] = useState([])
  const [mergeTags, setMergeTags] = useState(DEFAULT_MERGE)
  const [defaultPromoCode, setDefaultPromoCode] = useState('EXPO3DAYS')
  const [activeTplId, setActiveTplId] = useState(null)
  const [tplDraft, setTplDraft] = useState(null)

  const [tracking, setTracking] = useState(null)
  const [trackingFilter, setTrackingFilter] = useState('all')
  const [trackingQ, setTrackingQ] = useState('')
  const [trackingCampaignId, setTrackingCampaignId] = useState('')

  const [csvFile, setCsvFile] = useState(null)
  const [csvDrag, setCsvDrag] = useState(false)
  const [csvHeaders, setCsvHeaders] = useState([])
  const [csvPreviewRows, setCsvPreviewRows] = useState([])
  const [csvTotal, setCsvTotal] = useState(0)
  const [csvMapping, setCsvMapping] = useState({})

  const [apifyExpoUrl, setApifyExpoUrl] = useState('')
  const [scrapeEngine, setScrapeEngine] = useState('auto')
  const [apifyActorOverride, setApifyActorOverride] = useState('')
  const [scrapeAdvancedOpen, setScrapeAdvancedOpen] = useState(false)
  const [scrapeFollowWebsites, setScrapeFollowWebsites] = useState(true)
  const [apifyRuns, setApifyRuns] = useState([])
  const [apifyPreview, setApifyPreview] = useState(null)

  const [smtpPassword, setSmtpPassword] = useState('')
  const [resendKey, setResendKey] = useState('')
  const [apifyToken, setApifyToken] = useState('')
  const [smtpTestResult, setSmtpTestResult] = useState(null)
  const [apifyTestResult, setApifyTestResult] = useState(null)
  const [settingsTestEmail, setSettingsTestEmail] = useState('')

  const showBanner = (type, text) => {
    setBanner({ type, text })
    window.setTimeout(() => setBanner(null), 5000)
  }

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

  const loadTemplates = useCallback(async () => {
    const data = await apiFetch('/admin/ai-team/templates')
    setTemplates(data.templates || [])
    setMergeTags(data.merge_tags?.length ? data.merge_tags : DEFAULT_MERGE)
    if (data.default_promo_code) setDefaultPromoCode(data.default_promo_code)
    return data.templates || []
  }, [])

  const loadApifyRuns = useCallback(async () => {
    const data = await apiFetch('/admin/ai-team/apify/runs')
    setApifyRuns(data.runs || [])
  }, [])

  const loadTracking = useCallback(async () => {
    const params = new URLSearchParams()
    if (trackingFilter && trackingFilter !== 'all') params.set('status', trackingFilter)
    if (trackingCampaignId) params.set('campaign_id', trackingCampaignId)
    if (trackingQ.trim()) params.set('q', trackingQ.trim())
    const qs = params.toString()
    const data = await apiFetch(`/admin/ai-team/tracking${qs ? `?${qs}` : ''}`)
    setTracking(data)
    return data
  }, [trackingFilter, trackingCampaignId, trackingQ])

  const loadBoot = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiFetch('/admin/ai-team/dashboard')
      setSettings(data.settings || {})
      const list = data.campaigns || []
      setCampaigns(list)
      setActiveId((prev) => prev || list[0]?.id || null)
      await loadTemplates()
    } catch (e) {
      showBanner('err', e?.message || 'Could not load Apify hub')
    } finally {
      setLoading(false)
    }
  }, [loadTemplates])

  useEffect(() => { loadBoot() }, [loadBoot])
  useEffect(() => {
    if (activeId) loadCampaign(activeId).catch((e) => showBanner('err', e?.message || 'Load failed'))
  }, [activeId, loadCampaign])
  useEffect(() => {
    if (tab === 'scrape') loadApifyRuns().catch(() => {})
    if (tab === 'templates') loadTemplates().catch(() => {})
    if (tab === 'tracking') loadTracking().catch((e) => showBanner('err', e?.message || 'Tracking load failed'))
  }, [tab, loadApifyRuns, loadTemplates, loadTracking])

  useEffect(() => {
    if (tab !== 'tracking') return undefined
    const sending = (tracking?.campaigns || campaigns).some((c) => c.status === 'sending')
    if (!sending) return undefined
    const id = window.setInterval(() => loadTracking().catch(() => {}), 3000)
    return () => window.clearInterval(id)
  }, [tab, tracking, campaigns, loadTracking])

  useEffect(() => {
    if (!activeId || campaign?.status !== 'sending') return undefined
    const id = window.setInterval(() => {
      loadCampaign(activeId).catch(() => {})
      loadCampaigns().catch(() => {})
    }, 2500)
    return () => window.clearInterval(id)
  }, [activeId, campaign?.status, loadCampaign, loadCampaigns])

  useEffect(() => {
    if (tab !== 'scrape') return undefined
    const running = apifyRuns.some((r) => String(r.status || '').toUpperCase() === 'RUNNING')
    if (!running) return undefined
    const id = window.setInterval(() => loadApifyRuns().catch(() => {}), 2000)
    return () => window.clearInterval(id)
  }, [tab, apifyRuns, loadApifyRuns])

  useEffect(() => {
    if (!activeTplId) {
      setTplDraft(null)
      return
    }
    const t = templates.find((x) => x.id === activeTplId)
    if (t) setTplDraft({ ...t })
  }, [activeTplId, templates])

  const liveScrapeRun = apifyRuns.find((r) => String(r.status || '').toUpperCase() === 'RUNNING') || null
  const liveProgress = liveScrapeRun?.progress || null
  const liveStandsTotal = Number(liveProgress?.stands_total || liveScrapeRun?.stands_found || 0)
  const liveStandsDone = Number(liveProgress?.stands_done || 0)
  const liveEmails = Number(liveProgress?.emails_found || liveScrapeRun?.emails_found || 0)
  const livePct = liveStandsTotal > 0 ? Math.min(100, Math.round((liveStandsDone / liveStandsTotal) * 100)) : 0

  const scrapePlan = (() => {
    const tokenOk = !!(settings.apify_token_configured || apifyToken.trim())
    const actor = (
      apifyActorOverride.trim()
      || settings.apify_exhibitor_actor_id
      || settings.default_free_actor
      || 'vdrmota~contact-info-scraper'
    )
    const actorSource = apifyActorOverride.trim()
      ? 'override'
      : (settings.apify_exhibitor_actor_id ? 'saved' : 'auto free')
    if (scrapeEngine === 'builtin') {
      return { engine: 'builtin', label: 'Built-in scraper (forced)' }
    }
    if (scrapeEngine === 'apify') {
      if (!tokenOk) return { engine: 'need-token', label: 'Apify (save token under Apify API first)' }
      return { engine: 'apify', label: `Apify · ${actor} (${actorSource})` }
    }
    if (tokenOk) return { engine: 'apify', label: `Apify · ${actor} (${actorSource})` }
    return { engine: 'builtin', label: 'Built-in (save Apify token for better results on any site)' }
  })()

  const createCampaign = async () => {
    const name = newName.trim() || `Campaign ${new Date().toLocaleDateString()}`
    await act('create', async () => {
      const data = await apiFetch('/admin/ai-team/campaigns', { method: 'POST', body: JSON.stringify({ name }) })
      setNewName('')
      await loadCampaigns()
      setActiveId(data.campaign?.id)
      showBanner('ok', `Created “${data.campaign?.name}”`)
    })
  }

  const applyTemplate = async (templateId) => {
    if (!activeId || !templateId) return
    await act('apply-tpl', async () => {
      const data = await apiFetch(`/admin/ai-team/campaigns/${activeId}/apply-template`, {
        method: 'POST',
        body: JSON.stringify({ template_id: templateId }),
      })
      setCampaign(data.campaign)
      await loadCampaigns()
      showBanner('ok', 'Template applied to campaign')
    })
  }

  const saveCampaignMeta = async () => {
    if (!activeId || !campaign) return
    await act('save-c', async () => {
      const data = await apiFetch(`/admin/ai-team/campaigns/${activeId}`, {
        method: 'PUT',
        body: JSON.stringify({ name: campaign.name }),
      })
      setCampaign(data.campaign)
      await loadCampaigns()
      showBanner('ok', 'Campaign saved')
    })
  }

  const deleteCampaign = async () => {
    if (!activeId || !window.confirm('Delete this campaign and its audience?')) return
    await act('del-c', async () => {
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
    if (!activeId || !csvFile || !csvMapping.email) {
      showBanner('err', 'Select a campaign, upload a sheet, and map email')
      return
    }
    await act('csv', async () => {
      const fd = new FormData()
      fd.append('file', csvFile)
      fd.append('mapping', JSON.stringify(csvMapping))
      const data = await apiUpload(`/admin/ai-team/campaigns/${activeId}/import/csv`, fd)
      showBanner('ok', `Added ${data.created || 0} (${data.skipped || 0} skipped)`)
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
      showBanner('err', 'Enter a test email')
      return
    }
    await act('test', async () => {
      const data = await apiFetch(`/admin/ai-team/campaigns/${activeId}/test`, {
        method: 'POST',
        body: JSON.stringify({ to_email: to }),
      })
      showBanner('ok', data.message || 'Test sent')
    })
  }

  const sendAll = async () => {
    if (!activeId) return
    const n = recipients.filter((r) => r.status === 'pending' || r.status === 'failed').length
    if (!window.confirm(`Send this campaign to ${n || campaign?.total_count || 0} recipient(s)?`)) return
    await act('send', async () => {
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
    if (!activeId || !window.confirm('Remove all recipients?')) return
    await act('clear', async () => {
      const data = await apiFetch(`/admin/ai-team/campaigns/${activeId}/recipients`, { method: 'DELETE' })
      showBanner('ok', `Removed ${data.deleted || 0}`)
      await loadCampaign(activeId)
      await loadCampaigns()
    })
  }

  const createTemplate = async () => {
    const name = window.prompt('Template name', 'Expo outreach')
    if (name === null) return
    await act('tpl-create', async () => {
      const data = await apiFetch('/admin/ai-team/templates', {
        method: 'POST',
        body: JSON.stringify({ name: name.trim() || 'Untitled template' }),
      })
      const list = await loadTemplates()
      setActiveTplId(data.template?.id || list[0]?.id)
      showBanner('ok', 'Template created')
    })
  }

  const saveTemplate = async () => {
    if (!tplDraft?.id) return
    await act('tpl-save', async () => {
      await apiFetch(`/admin/ai-team/templates/${tplDraft.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: tplDraft.name,
          subject: tplDraft.subject,
          body_text: tplDraft.body_text,
          html_template: tplDraft.html_template,
        }),
      })
      await loadTemplates()
      showBanner('ok', 'Template saved')
    })
  }

  const previewTemplate = async () => {
    if (!tplDraft) return
    await act('tpl-preview', async () => {
      const data = await apiFetch('/admin/ai-team/templates/preview', {
        method: 'POST',
        body: JSON.stringify({
          subject: tplDraft.subject,
          body_text: tplDraft.body_text,
          html_template: tplDraft.html_template,
        }),
      })
      setPreview({ ...data, sample: true })
    })
  }

  const deleteTemplate = async () => {
    if (!tplDraft?.id || !window.confirm('Delete this template?')) return
    await act('tpl-del', async () => {
      await apiFetch(`/admin/ai-team/templates/${tplDraft.id}`, { method: 'DELETE' })
      setActiveTplId(null)
      await loadTemplates()
      showBanner('ok', 'Template deleted')
    })
  }

  const startScrape = async () => {
    if (!apifyExpoUrl.trim()) {
      showBanner('err', 'Paste an exhibitor directory URL')
      return
    }
    if (scrapeEngine === 'apify' && !settings.apify_token_configured && !apifyToken.trim()) {
      showBanner('err', 'Save Apify token under Apify API first (or use Auto / Built-in)')
      setTab('apify')
      return
    }
    await act('scrape', async () => {
      const data = await apiFetch('/admin/ai-team/scrape', {
        method: 'POST',
        body: JSON.stringify({
          expo_url: apifyExpoUrl.trim(),
          follow_websites: scrapeFollowWebsites,
          engine: scrapeEngine || 'auto',
          actor_id: apifyActorOverride.trim() || undefined,
        }),
      })
      showBanner('ok', data.message || 'Scrape started')
      await loadApifyRuns()
    })
  }

  const addScrapeToCampaign = async (runId) => {
    let cid = activeId
    if (!cid) {
      const name = window.prompt('Campaign name', `Expo scrape ${new Date().toLocaleDateString()}`)
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
      showBanner('ok', `Added ${data.created || 0} emails`)
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
      const data = await apiFetch('/admin/ai-team/settings', {
        method: 'PUT',
        body: JSON.stringify({
          ...settings,
          ...partial,
          smtp_password: smtpPassword || undefined,
          resend_api_key: resendKey || undefined,
          apify_token: apifyToken || undefined,
        }),
      })
      setSettings(data.settings || {})
      setSmtpPassword('')
      setResendKey('')
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
        setSmtpTestResult({ ok: false, message: e?.message || 'SMTP failed' })
        throw e
      }
    })
  }

  const runTestApify = async () => {
    setApifyTestResult(null)
    if (!apifyToken.trim() && !settings.apify_token_configured) {
      const msg = 'Paste Personal API token (apify_api_…), then Test'
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
        const msg = data.message || 'Apify OK'
        const ok = !!(data.ok && data.token_saved && data.apify_token_configured)
        setApifyTestResult({ ok, message: msg })
        if (!ok) {
          showBanner('err', msg)
          return
        }
        setApifyToken('')
        const refreshed = await apiFetch('/admin/ai-team/settings')
        setSettings(refreshed.settings || {})
        showBanner('ok', msg)
      } catch (e) {
        setApifyTestResult({ ok: false, message: e?.message || 'Apify failed' })
        throw e
      }
    })
  }

  const sendPct = campaign?.total_count
    ? Math.min(100, Math.round(((campaign.sent_count + campaign.failed_count) / campaign.total_count) * 100))
    : 0

  if (loading && !settings.from_email && !campaigns.length) {
    return <div className="ai-team-page" style={{ padding: 24 }}><div className="muted">Loading Apify…</div></div>
  }

  return (
    <div className="ai-team-page">
      <div className="ait-topbar">
        <div className="ait-topbar-left">
          <div className="ait-logo-mark">AP</div>
          <div>
            <div className="ait-page-title">Apify</div>
            <div className="ait-page-sub">Templates · campaigns · scrape · send all</div>
          </div>
        </div>
        <div className="ait-topbar-right">
          <button type="button" className="ait-btn ghost sm" onClick={() => setHowtoOpen(true)}>How to use</button>
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
          </button>
        ))}
      </div>

      <div className="ait-content">
        {tab === 'campaigns' && (
          <div className="ait-campaign-layout">
            <aside className="ait-campaign-rail">
              <div className="ait-card" style={{ marginBottom: 0 }}>
                <div className="ait-card-hdr"><span className="ait-card-title">Campaigns</span></div>
                <div className="ait-card-body" style={{ padding: 12 }}>
                  <div className="ait-field" style={{ marginBottom: 8 }}>
                    <input placeholder="New campaign name" value={newName} onChange={(e) => setNewName(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') createCampaign() }} />
                  </div>
                  <button type="button" className="ait-btn primary sm" style={{ width: '100%', marginBottom: 12 }} disabled={!!busy} onClick={createCampaign}>Create</button>
                  <div className="ait-campaign-list">
                    {campaigns.map((c) => (
                      <button key={c.id} type="button" className={`ait-campaign-item ${activeId === c.id ? 'active' : ''}`} onClick={() => setActiveId(c.id)}>
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
                        <strong>No campaigns</strong>
                        Create one, pick a template, upload Excel.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </aside>

            <div className="ait-campaign-main">
              {!campaign ? (
                <div className="ait-empty"><strong>Select or create a campaign</strong>Template → Excel → Preview → Send all</div>
              ) : (
                <>
                  <div className="ait-toolbar">
                    <div className="ait-toolbar-left">
                      <span className={`ait-badge ${statusBadge(campaign.status)}`}>{campaign.status}</span>
                      <span className="ait-toolbar-meta">{campaign.sent_count}/{campaign.total_count} sent</span>
                    </div>
                    <div className="ait-toolbar-right">
                      <button type="button" className="ait-btn sm" disabled={!!busy || campaign.status === 'sending'} onClick={saveCampaignMeta}>Save</button>
                      <button type="button" className="ait-btn danger sm" disabled={!!busy || campaign.status === 'sending'} onClick={deleteCampaign}>Delete</button>
                    </div>
                  </div>

                  {campaign.status === 'sending' && (
                    <div className="ait-msg-banner ok" style={{ margin: '0 0 14px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <strong>Sending… {campaign.sent_count + campaign.failed_count}/{campaign.total_count}</strong>
                        <button type="button" className="ait-btn danger xs" onClick={cancelSend}>Cancel</button>
                      </div>
                      <div style={{ marginTop: 8, height: 8, background: 'rgba(0,0,0,0.08)', borderRadius: 999, overflow: 'hidden' }}>
                        <div style={{ width: `${sendPct}%`, height: '100%', background: 'var(--ait-accent)' }} />
                      </div>
                    </div>
                  )}

                  <div className="ait-card">
                    <div className="ait-card-hdr"><span className="ait-card-title">1 · Campaign</span></div>
                    <div className="ait-card-body">
                      <div className="ait-field" style={{ marginBottom: 0 }}>
                        <label>Campaign name</label>
                        <input
                          className="ait-campaign-name-input"
                          value={campaign.name || ''}
                          disabled={campaign.status === 'sending'}
                          placeholder="e.g. London Packaging Week — outreach"
                          onChange={(e) => setCampaign({ ...campaign, name: e.target.value })}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="ait-card">
                    <div className="ait-card-hdr">
                      <span className="ait-card-title">2 · Template</span>
                      <button type="button" className="ait-btn xs" onClick={() => setTab('templates')}>Edit templates</button>
                    </div>
                    <div className="ait-card-body">
                      <div className="ait-fg-2">
                        <div className="ait-field">
                          <label>Select template</label>
                          <select
                            value={campaign.template_id || ''}
                            disabled={campaign.status === 'sending'}
                            onChange={(e) => applyTemplate(e.target.value)}
                          >
                            <option value="">— choose —</option>
                            {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                          </select>
                        </div>
                        <div className="ait-field">
                          <label>Subject (from template)</label>
                          <input disabled value={campaign.subject || ''} />
                        </div>
                      </div>
                      <div className="ait-email-snippet" style={{ whiteSpace: 'pre-wrap', maxHeight: 120, overflow: 'auto' }}>
                        {campaign.body_text || 'No body — pick a template'}
                      </div>
                    </div>
                  </div>

                  <div className="ait-card">
                    <div className="ait-card-hdr">
                      <span className="ait-card-title">3 · Audience · {campaign.total_count}</span>
                      <button type="button" className="ait-btn danger xs" disabled={!recipients.length || campaign.status === 'sending'} onClick={clearAudience}>Clear</button>
                    </div>
                    <div className="ait-card-body">
                      <div
                        className={`ait-dropzone ${csvDrag ? 'active' : ''}`}
                        onDragOver={(e) => { e.preventDefault(); setCsvDrag(true) }}
                        onDragLeave={() => setCsvDrag(false)}
                        onDrop={(e) => {
                          e.preventDefault(); setCsvDrag(false)
                          const f = e.dataTransfer.files?.[0]
                          if (f) parseCsvFile(f).catch((err) => showBanner('err', err?.message || 'Parse failed'))
                        }}
                        onClick={() => document.getElementById('apify-campaign-csv')?.click()}
                      >
                        <input id="apify-campaign-csv" type="file" accept=".csv,text/csv" style={{ display: 'none' }}
                          onChange={(e) => {
                            const f = e.target.files?.[0]
                            if (f) parseCsvFile(f).catch((err) => showBanner('err', err?.message || 'Parse failed'))
                          }}
                        />
                        <div style={{ fontWeight: 600 }}>{csvFile ? csvFile.name : 'Drop Excel/CSV or click'}</div>
                        <div style={{ fontSize: 12, color: 'var(--ait-text3)', marginTop: 6 }}>Save as CSV from Excel if needed</div>
                      </div>
                      {csvHeaders.length > 0 && (
                        <>
                          <div className="ait-fg-3" style={{ marginTop: 14 }}>
                            {CSV_MAP_FIELDS.map((f) => (
                              <div className="ait-field" key={f.key}>
                                <label>{f.label}{f.required ? ' *' : ''}</label>
                                <select value={csvMapping[f.key] || ''} onChange={(e) => setCsvMapping({ ...csvMapping, [f.key]: e.target.value })}>
                                  <option value="">— skip —</option>
                                  {csvHeaders.map((h) => <option key={h} value={h}>{h}</option>)}
                                </select>
                              </div>
                            ))}
                          </div>
                          <button type="button" className="ait-btn primary sm" disabled={!!busy || !csvMapping.email} onClick={importCsvToCampaign}>
                            Add {csvTotal} rows
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  <div className="ait-card">
                    <div className="ait-card-hdr"><span className="ait-card-title">4 · Preview & send</span></div>
                    <div className="ait-card-body">
                      <div className="ait-fg-2">
                        <div className="ait-field">
                          <label>Send test to</label>
                          <input type="email" value={testEmail} onChange={(e) => setTestEmail(e.target.value)} placeholder={settings.from_email || 'you@company.com'} />
                        </div>
                        <div className="ait-field">
                          <label>From</label>
                          <input disabled value={settings.from_email || '— set in Sending —'} />
                        </div>
                      </div>
                      <div className="ait-btn-row">
                        <button type="button" className="ait-btn sm" disabled={!!busy} onClick={runPreview}>Preview</button>
                        <button type="button" className="ait-btn sm" disabled={!!busy} onClick={sendTest}>Send test</button>
                        <button type="button" className="ait-btn primary" disabled={!!busy || campaign.status === 'sending' || !campaign.total_count} onClick={sendAll}>
                          Send all ({campaign.total_count || 0})
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="ait-card">
                    <div className="ait-card-hdr">
                      <span className="ait-card-title">5 · Results</span>
                      <button type="button" className="ait-btn xs primary" onClick={() => {
                        setTrackingCampaignId(activeId || '')
                        setTab('tracking')
                      }}>
                        Open Tracking
                      </button>
                    </div>
                    <div className="ait-card-body">
                      <p className="ait-hint" style={{ margin: 0 }}>
                        Sent {campaign.sent_count || 0}/{campaign.total_count || 0}
                        {' · '}failed {campaign.failed_count || 0}
                        {' · '}opened {campaign.opened_count || 0}.
                        Full send/click history is on the <strong>Tracking</strong> tab.
                      </p>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {tab === 'tracking' && (
          <div>
            <div className="ait-stats" style={{ marginBottom: 14 }}>
              {[
                ['Sent', tracking?.summary?.sent ?? '—'],
                ['Failed', tracking?.summary?.failed ?? '—'],
                ['Pending', tracking?.summary?.pending ?? '—'],
                ['Clicked', tracking?.summary?.clicked ?? '—'],
                ['Campaigns', tracking?.summary?.campaigns ?? '—'],
              ].map(([label, val]) => (
                <div className="ait-stat" key={label}>
                  <div className="ait-stat-lbl">{label}</div>
                  <div className="ait-stat-val">{val}</div>
                </div>
              ))}
            </div>

            <div className="ait-card">
              <div className="ait-card-hdr">
                <span className="ait-card-title">Campaigns</span>
                <button type="button" className="ait-btn xs" disabled={!!busy} onClick={() => act('tracking', loadTracking)}>Refresh</button>
              </div>
              <div className="ait-table-wrap">
                <table className="ait-tbl ait-tbl-compact">
                  <thead>
                    <tr>
                      <th>Campaign</th>
                      <th>Status</th>
                      <th>Sent</th>
                      <th>Clicks</th>
                      <th>Updated</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {(tracking?.campaigns || []).map((c) => (
                      <tr key={c.id}>
                        <td><strong>{c.name}</strong></td>
                        <td><span className={`ait-badge ${statusBadge(c.status)}`}>{c.status}</span></td>
                        <td>{c.sent_count}/{c.total_count}</td>
                        <td>{c.clicked_count || 0}</td>
                        <td style={{ fontSize: 12, color: 'var(--ait-text3)' }}>{timeAgo(c.updated_at)}</td>
                        <td>
                          <div className="ait-btn-row" style={{ margin: 0 }}>
                            <button type="button" className="ait-btn xs" onClick={() => setTrackingCampaignId(c.id)}>Filter</button>
                            <button type="button" className="ait-btn xs primary" onClick={() => { setActiveId(c.id); setTab('campaigns') }}>Open</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {!(tracking?.campaigns || []).length && (
                      <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--ait-text3)', padding: 20 }}>No campaigns yet</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="ait-card">
              <div className="ait-card-hdr">
                <span className="ait-card-title">Activity</span>
                <div className="ait-seg">
                  {[['all', 'All'], ['sent', 'Sent'], ['clicked', 'Clicked'], ['failed', 'Failed'], ['pending', 'Pending']].map(([id, label]) => (
                    <button key={id} type="button" className={trackingFilter === id ? 'active' : ''} onClick={() => setTrackingFilter(id)}>{label}</button>
                  ))}
                </div>
              </div>
              <div className="ait-card-body" style={{ paddingBottom: 8 }}>
                <div className="ait-fg-2">
                  <div className="ait-field">
                    <label>Search</label>
                    <input
                      value={trackingQ}
                      placeholder="Email or company"
                      onChange={(e) => setTrackingQ(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') loadTracking().catch((err) => showBanner('err', err?.message || 'Failed')) }}
                    />
                  </div>
                  <div className="ait-field">
                    <label>Campaign</label>
                    <select value={trackingCampaignId} onChange={(e) => setTrackingCampaignId(e.target.value)}>
                      <option value="">All campaigns</option>
                      {(tracking?.campaigns || campaigns).map((c) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <button type="button" className="ait-btn sm" disabled={!!busy} onClick={() => act('tracking', loadTracking)}>Apply filters</button>
              </div>
              <div className="ait-table-wrap">
                <table className="ait-tbl">
                  <thead>
                    <tr>
                      <th>Email</th>
                      <th>Company</th>
                      <th>Campaign</th>
                      <th>Promo</th>
                      <th>Status</th>
                      <th>Clicks</th>
                      <th>Sent</th>
                      <th>Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(tracking?.activity || []).map((r) => (
                      <tr key={r.id}>
                        <td>
                          <strong>{r.full_name || r.email}</strong>
                          <div style={{ fontSize: 11, color: 'var(--ait-text3)' }}>{r.email}</div>
                        </td>
                        <td>{r.company_name || '—'}</td>
                        <td style={{ fontSize: 12 }}>{r.campaign_name || '—'}</td>
                        <td style={{ fontSize: 12, fontFamily: 'monospace' }}>{r.promo_code || defaultPromoCode}</td>
                        <td><span className={`ait-badge ${statusBadge(r.status)}`}>{r.status}</span></td>
                        <td style={{ fontSize: 12 }}>
                          {(r.click_count || 0) > 0 ? (
                            <span className="ait-badge b-opened" title={r.clicked_at || ''}>{r.click_count}</span>
                          ) : '—'}
                        </td>
                        <td style={{ fontSize: 12, color: 'var(--ait-text3)' }}>{timeAgo(r.sent_at)}</td>
                        <td className="ait-ellipsis" title={r.last_error || ''}>{r.last_error || '—'}</td>
                      </tr>
                    ))}
                    {!(tracking?.activity || []).length && (
                      <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--ait-text3)', padding: 28 }}>No activity yet — send a campaign first</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {tab === 'templates' && (
          <div className="ait-campaign-layout">
            <aside className="ait-campaign-rail">
              <div className="ait-card" style={{ marginBottom: 0 }}>
                <div className="ait-card-hdr">
                  <span className="ait-card-title">Templates</span>
                  <button type="button" className="ait-btn xs primary" disabled={!!busy} onClick={createTemplate}>New</button>
                </div>
                <div className="ait-card-body" style={{ padding: 12 }}>
                  <div className="ait-campaign-list">
                    {templates.map((t) => (
                      <button key={t.id} type="button" className={`ait-campaign-item ${activeTplId === t.id ? 'active' : ''}`} onClick={() => setActiveTplId(t.id)}>
                        <strong style={{ fontSize: 13 }}>{t.name}</strong>
                        <div style={{ fontSize: 11, color: 'var(--ait-text3)', marginTop: 4 }} className="ait-ellipsis">{t.subject}</div>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </aside>
            <div className="ait-campaign-main">
              {!tplDraft ? (
                <div className="ait-empty"><strong>Select or create a template</strong>Add merge codes with the chips below.</div>
              ) : (
                <div className="ait-card">
                  <div className="ait-card-hdr">
                    <span className="ait-card-title">Edit template</span>
                    <div className="ait-btn-row" style={{ margin: 0 }}>
                      <button type="button" className="ait-btn sm" disabled={!!busy} onClick={previewTemplate}>Preview</button>
                      <button type="button" className="ait-btn primary sm" disabled={!!busy} onClick={saveTemplate}>Save</button>
                      <button type="button" className="ait-btn danger sm" disabled={!!busy} onClick={deleteTemplate}>Delete</button>
                    </div>
                  </div>
                  <div className="ait-card-body">
                    <div className="ait-field"><label>Name</label>
                      <input value={tplDraft.name || ''} onChange={(e) => setTplDraft({ ...tplDraft, name: e.target.value })} />
                    </div>
                    <div className="ait-field"><label>Subject</label>
                      <input value={tplDraft.subject || ''} onChange={(e) => setTplDraft({ ...tplDraft, subject: e.target.value })} />
                    </div>
                    <div className="ait-chip-row" style={{ marginBottom: 10 }}>
                      {mergeTags.filter((t) => t !== 'body').map((t) => (
                        <button key={t} type="button" className="ait-chip"
                          onClick={() => insertAtEnd(tplDraft.body_text, (v) => setTplDraft({ ...tplDraft, body_text: v }), t)}
                        >{`{{${t}}}`}</button>
                      ))}
                    </div>
                    <div className="ait-field"><label>Body text</label>
                      <textarea style={{ minHeight: 140 }} value={tplDraft.body_text || ''} onChange={(e) => setTplDraft({ ...tplDraft, body_text: e.target.value })} />
                    </div>
                    <div className="ait-chip-row" style={{ marginBottom: 8 }}>
                      <button type="button" className="ait-chip"
                        onClick={() => insertAtEnd(tplDraft.html_template, (v) => setTplDraft({ ...tplDraft, html_template: v }), 'body')}
                      >{`{{body}}`}</button>
                      <span className="ait-hint" style={{ margin: 0 }}>Use in HTML wrapper for the text block</span>
                    </div>
                    <div className="ait-field" style={{ marginBottom: 0 }}><label>HTML (paste full email — sent exactly as pasted)</label>
                      <textarea className="ait-code-editor" style={{ minHeight: 220 }} value={tplDraft.html_template || ''} onChange={(e) => setTplDraft({ ...tplDraft, html_template: e.target.value })} />
                    </div>
                    <p className="ait-hint">
                      HTML is sent <strong>as-is</strong>. Only merge codes are replaced:
                      {' '}{mergeTags.filter((t) => t !== 'body').map((t) => `{{${t}}}`).join(' ')}.
                      Put <code>href=&quot;{'{{trial_url}}'}&quot;</code> on your Start free trial button
                      (tracks clicks → signup with <strong>{defaultPromoCode}</strong>).
                    </p>
                    <p className="ait-hint" style={{ marginTop: 4 }}>
                      Use Body text only if your HTML contains <code>{'{{body}}'}</code>. Otherwise paste the full design in HTML and leave Body short or empty.
                    </p>
                  </div>
                </div>
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
              <div className={`ait-msg-banner ${scrapePlan.engine === 'need-token' ? 'err' : 'ok'}`} style={{ margin: '0 0 12px' }}>
                <strong>Will use:</strong> {scrapePlan.label}
              </div>
              <div className="ait-field">
                <label>Expo / directory URL</label>
                <input
                  value={apifyExpoUrl}
                  onChange={(e) => setApifyExpoUrl(e.target.value)}
                  placeholder="https://…/exhibitors/ (any show directory)"
                />
              </div>
              <label className="ait-check" style={{ marginBottom: 12 }}>
                <input type="checkbox" checked={scrapeFollowWebsites} onChange={(e) => setScrapeFollowWebsites(e.target.checked)} />
                Also scrape company websites (built-in path)
              </label>
              <div className="ait-btn-row">
                <button type="button" className="ait-btn primary sm" disabled={!!busy || !apifyExpoUrl.trim()} onClick={startScrape}>
                  Scrape
                </button>
                <button type="button" className="ait-btn ghost sm" onClick={() => setScrapeAdvancedOpen((v) => !v)}>
                  {scrapeAdvancedOpen ? 'Hide advanced' : 'Advanced'}
                </button>
              </div>
              {scrapeAdvancedOpen && (
                <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--ait-border)' }}>
                  <div className="ait-fg-2">
                    <div className="ait-field">
                      <label>Engine</label>
                      <select value={scrapeEngine} onChange={(e) => setScrapeEngine(e.target.value)}>
                        <option value="auto">Auto (Apify if ready, else built-in)</option>
                        <option value="apify">Force Apify</option>
                        <option value="builtin">Force built-in</option>
                      </select>
                    </div>
                    <div className="ait-field">
                      <label>Actor override</label>
                      <input
                        value={apifyActorOverride}
                        onChange={(e) => setApifyActorOverride(e.target.value)}
                        placeholder={settings.apify_exhibitor_actor_id || settings.default_free_actor || 'username~actor'}
                      />
                    </div>
                  </div>
                  <div className="ait-chip-row">
                    {(settings.curated_free_actors || SUGGESTED_ACTORS.map((a) => a.id)).map((id) => {
                      const label = SUGGESTED_ACTORS.find((a) => a.id === id)?.label || id
                      return (
                        <button
                          key={id}
                          type="button"
                          className="ait-chip"
                          onClick={() => setApifyActorOverride(id)}
                        >
                          {label}
                        </button>
                      )
                    })}
                  </div>
                  <p className="ait-hint" style={{ marginBottom: 0 }}>
                    Auto picks a free/community actor when none is saved. If Apify fails to start, built-in runs automatically.
                  </p>
                </div>
              )}
              <p className="ait-hint">
                Manual alternative: <button type="button" className="ait-btn ghost xs" onClick={() => setTab('campaigns')}>Campaigns → upload Excel</button>
              </p>
              {liveScrapeRun && (
                <div className="ait-msg-banner ok" style={{ margin: '12px 0' }}>
                  <strong>Live:</strong> {liveProgress?.message || 'Running…'} · {liveStandsDone}/{liveStandsTotal || '—'} · emails {liveEmails} · {livePct}%
                </div>
              )}
              <div className="ait-table-wrap" style={{ marginTop: 12 }}>
                <table className="ait-tbl ait-tbl-compact">
                  <thead><tr><th>Status</th><th>Engine</th><th>URL</th><th>Emails</th><th /></tr></thead>
                  <tbody>
                    {apifyRuns.map((run) => {
                      const isBuiltin = String(run.actor_id || '').startsWith('builtin:') || run.provider === 'builtin' || run.engine === 'builtin'
                      return (
                        <tr key={run.id}>
                          <td><span className={`ait-badge ${run.status === 'SUCCEEDED' ? 'b-sent' : 'b-pending'}`}>{run.status}</span></td>
                          <td style={{ fontSize: 11 }}>{isBuiltin ? 'built-in' : (run.actor_id || 'apify')}</td>
                          <td className="ait-ellipsis" title={run.expo_url}>{run.expo_url}</td>
                          <td>{run.emails_found ?? 0}</td>
                          <td>
                            <div className="ait-btn-row" style={{ margin: 0 }}>
                              <button type="button" className="ait-btn xs" disabled={run.status !== 'SUCCEEDED'} onClick={() => exportApifyRun(run.id)}>Excel</button>
                              <button type="button" className="ait-btn xs primary" disabled={!!busy || run.status !== 'SUCCEEDED'} onClick={() => addScrapeToCampaign(run.id)}>Add to campaign</button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                    {!apifyRuns.length && <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--ait-text3)', padding: 20 }}>No scrapes yet</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {tab === 'apify' && (
          <div className="ait-card">
            <div className="ait-card-hdr">
              <span className="ait-card-title">Apify API</span>
              <button type="button" className="ait-btn primary sm" disabled={!!busy} onClick={() => saveSettings()}>Save</button>
            </div>
            <div className="ait-card-body ait-compact">
              <div className="ait-conn-block ait-conn-compact">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className={`ait-dot ${apifyTestResult?.ok || settings.apify_token_configured ? 'on' : 'off'}`} />
                  <strong>{apifyTestResult ? (apifyTestResult.ok ? 'Connected' : 'Failed') : (settings.apify_token_configured ? 'Token saved' : 'Not connected')}</strong>
                </div>
                <button type="button" className="ait-btn xs" disabled={!!busy} onClick={runTestApify}>Test</button>
              </div>
              {apifyTestResult && (
                <div className={`ait-msg-banner ${apifyTestResult.ok ? 'ok' : 'err'}`} style={{ margin: '0 0 10px' }}>{apifyTestResult.message}</div>
              )}
              <div className="ait-fg-2">
                <div className="ait-field"><label>User ID</label>
                  <input value={settings.apify_user_id || ''} onChange={(e) => setSettings({ ...settings, apify_user_id: e.target.value })} />
                </div>
                <div className="ait-field"><label>Personal API token</label>
                  <input type="password" placeholder={settings.apify_token_configured ? '••••••••' : 'apify_api_…'} value={apifyToken} onChange={(e) => setApifyToken(e.target.value)} />
                </div>
                <div className="ait-field" style={{ gridColumn: '1 / -1' }}><label>Exhibitor actor ID</label>
                  <input value={settings.apify_exhibitor_actor_id || ''} onChange={(e) => setSettings({ ...settings, apify_exhibitor_actor_id: e.target.value })} />
                </div>
              </div>
              <div className="ait-chip-row">
                {SUGGESTED_ACTORS.map((a) => (
                  <button key={a.id} type="button" className="ait-chip" title={a.note} onClick={() => setSettings({ ...settings, apify_exhibitor_actor_id: a.id })}>{a.label}</button>
                ))}
              </div>
              <div className="ait-field"><label>Second actor (optional)</label>
                <input value={settings.apify_contact_actor_id || ''} onChange={(e) => setSettings({ ...settings, apify_contact_actor_id: e.target.value })} />
              </div>
            </div>
          </div>
        )}

        {tab === 'sending' && (
          <div className="ait-card">
            <div className="ait-card-hdr">
              <span className="ait-card-title">Sending</span>
              <button type="button" className="ait-btn primary sm" disabled={!!busy} onClick={() => saveSettings()}>Save</button>
            </div>
            <div className="ait-card-body ait-compact">
              <div className="ait-conn-block ait-conn-compact">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className={`ait-dot ${smtpTestResult?.ok || settings.smtp_configured ? 'on' : 'off'}`} />
                  <strong>{smtpTestResult ? (smtpTestResult.ok ? 'SMTP OK' : 'Failed') : (settings.smtp_configured ? 'Configured' : 'Not set')}</strong>
                </div>
                <button type="button" className="ait-btn xs" disabled={!!busy} onClick={runTestSmtp}>Test SMTP</button>
              </div>
              <div className="ait-fg-3">
                <div className="ait-field"><label>Provider</label>
                  <select value={settings.email_delivery_provider || 'smtp'} onChange={(e) => setSettings({ ...settings, email_delivery_provider: e.target.value })}>
                    <option value="smtp">SMTP</option>
                    <option value="resend">Resend</option>
                  </select>
                </div>
                <div className="ait-field"><label>From name</label><input value={settings.sender_name || ''} onChange={(e) => setSettings({ ...settings, sender_name: e.target.value })} /></div>
                <div className="ait-field"><label>From email</label><input value={settings.from_email || ''} onChange={(e) => setSettings({ ...settings, from_email: e.target.value })} /></div>
              </div>
              <div className="ait-fg-3">
                <div className="ait-field"><label>SMTP host</label><input value={settings.smtp_host || ''} onChange={(e) => setSettings({ ...settings, smtp_host: e.target.value })} /></div>
                <div className="ait-field"><label>Port</label><input type="number" value={settings.smtp_port || 587} onChange={(e) => setSettings({ ...settings, smtp_port: +e.target.value })} /></div>
                <div className="ait-field"><label>Username</label><input value={settings.smtp_username || ''} onChange={(e) => setSettings({ ...settings, smtp_username: e.target.value })} /></div>
              </div>
              <div className="ait-fg-2">
                <div className="ait-field"><label>Password</label><input type="password" value={smtpPassword} onChange={(e) => setSmtpPassword(e.target.value)} placeholder={settings.smtp_password_configured ? '••••••••' : ''} /></div>
                <div className="ait-field"><label>Resend key</label><input type="password" value={resendKey} onChange={(e) => setResendKey(e.target.value)} /></div>
              </div>
              <div className="ait-fg-2">
                <div className="ait-field"><label>Test email</label><input type="email" value={settingsTestEmail} onChange={(e) => setSettingsTestEmail(e.target.value)} /></div>
                <div className="ait-field"><label>Max / day</label><input type="number" value={settings.max_emails_per_day || 200} onChange={(e) => setSettings({ ...settings, max_emails_per_day: +e.target.value })} /></div>
              </div>
            </div>
          </div>
        )}
      </div>

      {preview && (
        <div className="ait-modal-backdrop" onClick={() => setPreview(null)}>
          <div className="ait-modal ait-modal-wide ait-modal-fullscreen" onClick={(e) => e.stopPropagation()}>
            <div className="ait-modal-hdr">
              <div>
                <h3>{preview.subject}</h3>
                <div style={{ fontSize: 12, color: 'var(--ait-text3)' }}>
                  {preview.sample ? 'Sample preview · full screen' : `To ${preview.recipient?.email}`}
                  {' · '}promo {defaultPromoCode}
                </div>
              </div>
              <button type="button" className="ait-btn ghost sm" onClick={() => setPreview(null)}>Close</button>
            </div>
            <div className="ait-email-client-frame">
              <iframe title="preview" className="ait-html-preview" srcDoc={preview.html || ''} />
            </div>
            {preview.body_text ? (
              <details style={{ marginTop: 10, flexShrink: 0 }}>
                <summary style={{ cursor: 'pointer', fontSize: 12, color: 'var(--ait-text3)' }}>Plain text</summary>
                <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, marginTop: 8 }}>{preview.body_text || preview.text}</pre>
              </details>
            ) : null}
          </div>
        </div>
      )}

      {howtoOpen && (
        <div className="ait-modal-backdrop" onClick={() => setHowtoOpen(false)}>
          <div className="ait-modal" onClick={(e) => e.stopPropagation()}>
            <div className="ait-modal-hdr">
              <h3>How to use Apify hub</h3>
              <button type="button" className="ait-btn ghost sm" onClick={() => setHowtoOpen(false)}>Close</button>
            </div>
            <ol style={{ margin: 0, paddingLeft: 18, color: 'var(--ait-text2)', lineHeight: 1.6, fontSize: 13 }}>
              <li><strong>Sending</strong> — save From + SMTP and test.</li>
              <li><strong>Templates</strong> — paste HTML as-is; only {'{{…}}'} codes are replaced. Use {'{{trial_url}}'} on the CTA.</li>
              <li><strong>Campaigns</strong> — name → select template → Excel → Preview → Send all.</li>
              <li><strong>Tracking</strong> — all sends, failures, and trial-link clicks across campaigns.</li>
              <li><strong>Scrape</strong> — paste any exhibitor URL; uses Apify + free actor when token is set, otherwise built-in → Add to campaign.</li>
            </ol>
            <p className="ait-hint" style={{ marginTop: 12 }}>
              AI Team (sidebar) is the older approval-queue tool. This Apify page is template + bulk send.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
