import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { apiFetch, apiFetchBlob, apiUpload } from '../lib/api'
import './ai-team.css'

const TABS = [
  { id: 'campaigns', label: 'Campaigns', icon: 'ti-send', group: 'Work' },
  { id: 'scrape', label: 'Scrape', icon: 'ti-world', group: 'Work' },
  { id: 'templates', label: 'Templates', icon: 'ti-template', group: 'Work' },
  { id: 'tracking', label: 'Tracking', icon: 'ti-chart-bar', group: 'Results' },
  { id: 'sending', label: 'Sending', icon: 'ti-mail', group: 'Setup' },
  { id: 'apify', label: 'Apify API', icon: 'ti-key', group: 'Setup' },
]

const WORKFLOW_STEPS = [
  { id: 'scrape', n: 1, label: 'Scrape contacts' },
  { id: 'templates', n: 2, label: 'Edit template' },
  { id: 'campaigns', n: 3, label: 'Create & send' },
  { id: 'tracking', n: 4, label: 'Track results' },
]

const HOME_KPIS = [
  { key: 'sent', label: 'Sent', filter: 'sent', tone: 'sent', hint: 'Emails delivered' },
  { key: 'opened', label: 'Opened', filter: 'opened', tone: 'opened', hint: 'Pixel opens' },
  { key: 'clicked', label: 'Clicked', filter: 'clicked', tone: 'clicked', hint: 'Link clicks' },
  { key: 'received', label: 'Received', filter: 'received', tone: 'received', hint: 'Matched replies' },
  { key: 'inbox', label: 'Inbox', filter: 'inbox', tone: 'inbox', hint: 'All IMAP mail' },
  { key: 'pending', label: 'Pending', filter: 'pending', tone: 'pending', hint: 'Still in queue' },
]

const CSV_MAP_FIELDS = [
  { key: 'email', label: 'Email', required: true },
  { key: 'first_name', label: 'First name' },
  { key: 'last_name', label: 'Last name' },
  { key: 'job_title', label: 'Job title' },
  { key: 'company_name', label: 'Company' },
  { key: 'event_name', label: 'Event name' },
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
  'first_name', 'last_name', 'company', 'company_name', 'event_name', 'event-name', 'job_title',
  'email', 'sector', 'country_code', 'promo_code', 'signup_url', 'trial_url',
  'tracked_trial_url', 'direct_signup_url', 'unsubscribe_url', 'unsubscribe_link', 'body',
]

const PREVIEW_DEVICES = [
  { id: 'desktop', label: 'Desktop', icon: 'ti-device-desktop', width: 800 },
  { id: 'tablet', label: 'Tablet', icon: 'ti-device-tablet', width: 600 },
  { id: 'mobile', label: 'Mobile', icon: 'ti-device-mobile', width: 375 },
]

const SAMPLE_MERGE = {
  first_name: 'Alex',
  last_name: 'Taylor',
  company: 'Example Ltd',
  company_name: 'Example Ltd',
  event_name: 'London Packaging Week',
  'event-name': 'London Packaging Week',
  job_title: 'Operations Director',
  email: 'alex@example.com',
  sector: 'expo',
  country_code: 'GB',
  promo_code: 'EXPO3DAYS',
  signup_url: 'https://voxbulk.com/signin?promo=EXPO3DAYS',
  trial_url: 'https://voxbulk.com/signin?promo=EXPO3DAYS',
  direct_signup_url: 'https://voxbulk.com/signin?promo=EXPO3DAYS',
  tracked_trial_url: 'https://voxbulk.com/signin?promo=EXPO3DAYS',
  unsubscribe_url: 'https://api.voxbulk.com/public/ai-team/unsubscribe/demo',
  unsubscribe_link: 'https://api.voxbulk.com/public/ai-team/unsubscribe/demo',
}

function applySampleMerge(template, bodyText, promoCode) {
  const vars = {
    ...SAMPLE_MERGE,
    promo_code: promoCode || SAMPLE_MERGE.promo_code,
    signup_url: `https://voxbulk.com/signin?promo=${promoCode || SAMPLE_MERGE.promo_code}`,
    trial_url: `https://voxbulk.com/signin?promo=${promoCode || SAMPLE_MERGE.promo_code}`,
    direct_signup_url: `https://voxbulk.com/signin?promo=${promoCode || SAMPLE_MERGE.promo_code}`,
    tracked_trial_url: `https://voxbulk.com/signin?promo=${promoCode || SAMPLE_MERGE.promo_code}`,
    unsubscribe_url: SAMPLE_MERGE.unsubscribe_url,
    unsubscribe_link: SAMPLE_MERGE.unsubscribe_link,
    body: bodyText || '',
  }
  let out = String(template || '')
  for (const [key, val] of Object.entries(vars)) {
    out = out.split(`{{${key}}}`).join(String(val ?? ''))
  }
  return out.replace(/\{\{[a-zA-Z0-9_-]+\}\}/g, '')
}

function guessCsvMapping(headers) {
  const norm = (h) => String(h || '').toLowerCase().replace(/[^a-z0-9]+/g, '_')
  const map = {}
  const rules = [
    ['email', ['email', 'e_mail', 'email_address']],
    ['first_name', ['first_name', 'firstname', 'first', 'given_name']],
    ['last_name', ['last_name', 'lastname', 'last', 'surname', 'family_name']],
    ['job_title', ['job_title', 'title', 'role', 'position']],
    ['company_name', ['company', 'company_name', 'organization', 'org', 'stand_name']],
    ['event_name', ['event_name', 'event', 'event_title', 'show_name', 'expo_name']],
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
    unsubscribed: 'b-rejected', skipped: 'b-pending',
    paused_daily_limit: 'b-dent', paused: 'b-dent', scheduled: 'b-prop',
    test: 'b-pending',
  }
  return map[status] || 'b-pending'
}

function contactDisplayName(r) {
  return [r.first_name, r.last_name].filter(Boolean).join(' ') || '—'
}

function toLocalInputValue(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function insertAtEnd(value, setValue, tag) {
  setValue(`${value || ''}{{${tag}}}`)
}

export default function ApifyOutreach() {
  const navigate = useNavigate()
  const { campaignId: routeCampaignId } = useParams()
  const [searchParams] = useSearchParams()
  const isCampaignPage = Boolean(routeCampaignId)
  const [tab, setTab] = useState(() => searchParams.get('tab') || 'campaigns')
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
  const [tplPreviewDevice, setTplPreviewDevice] = useState('desktop')
  const [tplLiveHtml, setTplLiveHtml] = useState('')

  const [tracking, setTracking] = useState(null)
  const [kpis, setKpis] = useState(null)
  const [trackingFilter, setTrackingFilter] = useState(() => searchParams.get('filter') || 'all')
  const [trackingQ, setTrackingQ] = useState('')
  const [trackingCampaignId, setTrackingCampaignId] = useState('')

  const [csvFile, setCsvFile] = useState(null)
  const [csvDrag, setCsvDrag] = useState(false)
  const [csvHeaders, setCsvHeaders] = useState([])
  const [csvContacts, setCsvContacts] = useState([])
  const [csvTotal, setCsvTotal] = useState(0)
  const [csvMapping, setCsvMapping] = useState({})
  const [csvDetected, setCsvDetected] = useState({})
  const [csvEmailOk, setCsvEmailOk] = useState(false)
  const [csvMapOpen, setCsvMapOpen] = useState(false)
  const [contactsModal, setContactsModal] = useState(null) // { title, rows, source }
  const [suppressions, setSuppressions] = useState([])

  const [apifyExpoUrl, setApifyExpoUrl] = useState('')
  const [scrapeEngine, setScrapeEngine] = useState('auto')
  const [apifyActorOverride, setApifyActorOverride] = useState('')
  const [scrapeAdvancedOpen, setScrapeAdvancedOpen] = useState(false)
  const [scrapeFollowWebsites, setScrapeFollowWebsites] = useState(true)
  const [apifyRuns, setApifyRuns] = useState([])
  const [apifyPreview, setApifyPreview] = useState(null)
  const [exhibitionDirs, setExhibitionDirs] = useState([])
  const [bulkUrls, setBulkUrls] = useState('')
  const [bulkOpen, setBulkOpen] = useState(false)

  const [smtpPassword, setSmtpPassword] = useState('')
  const [imapPassword, setImapPassword] = useState('')
  const [resendKey, setResendKey] = useState('')
  const [apifyToken, setApifyToken] = useState('')
  const [smtpTestResult, setSmtpTestResult] = useState(null)
  const [imapTestResult, setImapTestResult] = useState(null)
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

  const loadExhibitionDirs = useCallback(async () => {
    try {
      const data = await apiFetch('/admin/ai-team/scrape/exhibition-directories')
      setExhibitionDirs(data.exhibitions || [])
      return data.exhibitions || []
    } catch {
      setExhibitionDirs([])
      return []
    }
  }, [])

  const loadTracking = useCallback(async () => {
    const params = new URLSearchParams()
    if (trackingFilter && trackingFilter !== 'all' && trackingFilter !== 'unsub_list') {
      params.set('status', trackingFilter)
    }
    if (trackingCampaignId) params.set('campaign_id', trackingCampaignId)
    if (trackingQ.trim()) params.set('q', trackingQ.trim())
    const qs = params.toString()
    const data = await apiFetch(`/admin/ai-team/tracking${qs ? `?${qs}` : ''}`)
    setTracking(data)
    if (data?.summary) setKpis(data.summary)
    if (trackingFilter === 'unsub_list' || trackingFilter === 'unsubscribed') {
      try {
        const s = await apiFetch('/admin/ai-team/suppressions')
        setSuppressions(s.suppressions || [])
      } catch {
        setSuppressions([])
      }
    }
    return data
  }, [trackingFilter, trackingCampaignId, trackingQ])

  const loadKpis = useCallback(async () => {
    const data = await apiFetch('/admin/ai-team/tracking?limit=1')
    if (data?.summary) setKpis(data.summary)
    return data
  }, [])

  const openKpi = useCallback((filter) => {
    setTrackingFilter(filter)
    setTrackingCampaignId('')
    setTab('tracking')
    navigate(`/marketing/apify?tab=tracking&filter=${encodeURIComponent(filter)}`)
  }, [navigate])

  const goTab = useCallback((id) => {
    setTab(id)
    if (id === 'tracking') {
      navigate(`/marketing/apify?tab=tracking&filter=${encodeURIComponent(trackingFilter || 'all')}`)
    } else {
      navigate(`/marketing/apify?tab=${encodeURIComponent(id)}`)
    }
  }, [navigate, trackingFilter])

  const loadBoot = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiFetch('/admin/ai-team/dashboard')
      setSettings(data.settings || {})
      const list = data.campaigns || []
      setCampaigns(list)
      setActiveId((prev) => prev || list[0]?.id || null)
      await Promise.all([loadTemplates(), loadKpis().catch(() => null)])
    } catch (e) {
      showBanner('err', e?.message || 'Could not load Apify hub')
    } finally {
      setLoading(false)
    }
  }, [loadTemplates, loadKpis])

  useEffect(() => { loadBoot() }, [loadBoot])
  useEffect(() => {
    if (isCampaignPage) return undefined
    const id = window.setInterval(() => loadKpis().catch(() => {}), 20000)
    return () => window.clearInterval(id)
  }, [isCampaignPage, loadKpis])
  useEffect(() => {
    if (routeCampaignId) {
      setActiveId(routeCampaignId)
      setTab('campaigns')
    }
  }, [routeCampaignId])
  useEffect(() => {
    if (activeId) loadCampaign(activeId).catch((e) => showBanner('err', e?.message || 'Load failed'))
  }, [activeId, loadCampaign])
  useEffect(() => {
    if (tab === 'scrape') {
      loadApifyRuns().catch(() => {})
      loadExhibitionDirs().catch(() => {})
    }
    if (tab === 'templates') loadTemplates().catch(() => {})
    if (tab === 'tracking') loadTracking().catch((e) => showBanner('err', e?.message || 'Tracking load failed'))
  }, [tab, loadApifyRuns, loadTemplates, loadTracking, loadExhibitionDirs])

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
    const active = apifyRuns.some((r) => {
      const s = String(r.status || '').toUpperCase()
      return s === 'RUNNING' || s === 'READY' || s === 'CREATED' || s === 'ABORTING'
    })
    if (!active) return undefined
    const id = window.setInterval(() => loadApifyRuns().catch(() => {}), 2500)
    return () => window.clearInterval(id)
  }, [tab, apifyRuns, loadApifyRuns])

  useEffect(() => {
    if (!activeTplId) {
      setTplDraft(null)
      setTplLiveHtml('')
      return
    }
    const t = templates.find((x) => x.id === activeTplId)
    if (t) setTplDraft({ ...t })
  }, [activeTplId, templates])

  useEffect(() => {
    if (!tplDraft) {
      setTplLiveHtml('')
      return undefined
    }
    const id = window.setTimeout(() => {
      setTplLiveHtml(applySampleMerge(tplDraft.html_template, tplDraft.body_text, defaultPromoCode))
    }, 200)
    return () => window.clearTimeout(id)
  }, [tplDraft, defaultPromoCode])

  const liveScrapeRun = apifyRuns.find((r) => {
    const s = String(r.status || '').toUpperCase()
    return s === 'RUNNING' || s === 'READY' || s === 'CREATED' || s === 'ABORTING'
  }) || null
  const liveProgress = liveScrapeRun?.progress || null
  const liveStandsTotal = Number(liveProgress?.stands_total || liveScrapeRun?.stands_found || 0)
  const liveStandsDone = Number(liveProgress?.stands_done || 0)
  const liveEmails = Number(liveProgress?.emails_found || liveScrapeRun?.emails_found || 0)
  const livePct = liveStandsTotal > 0 ? Math.min(100, Math.round((liveStandsDone / liveStandsTotal) * 100)) : (
    String(liveScrapeRun?.status || '').toUpperCase() === 'RUNNING' ? 15 : 5
  )
  const liveStatusUp = String(liveScrapeRun?.status || '').toUpperCase()
  const liveStatusLabel = ({
    READY: 'Queued on Apify',
    CREATED: 'Created on Apify',
    RUNNING: 'Running',
    ABORTING: 'Stopping…',
  })[liveStatusUp] || liveStatusUp || 'Working'

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
    const path = String(apifyExpoUrl || '').toLowerCase()
    const looksDirectory = ['/exhibitor', '/directory', '/stands', '/participants'].some((t) => path.includes(t))
    if (scrapeEngine === 'builtin') {
      return { engine: 'builtin', label: 'Built-in scraper (forced)' }
    }
    if (scrapeEngine === 'apify') {
      if (!tokenOk) return { engine: 'need-token', label: 'Apify (save token under Apify API first)' }
      return { engine: 'apify', label: `Apify · ${actor} (${actorSource})` }
    }
    if (looksDirectory) {
      return { engine: 'builtin', label: 'Built-in first (Easyfairs / SPA / ASP / Reed / HTML)' }
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
      const id = data.campaign?.id
      if (id) {
        setActiveId(id)
        navigate(`/marketing/apify/campaigns/${id}`)
      }
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
      const local = campaign._scheduleLocal
      let scheduled_at = campaign.scheduled_at || null
      if (local !== undefined) {
        if (!local) scheduled_at = null
        else {
          const when = new Date(local)
          scheduled_at = Number.isNaN(when.getTime()) ? null : when.toISOString()
        }
      }
      const data = await apiFetch(`/admin/ai-team/campaigns/${activeId}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: campaign.name,
          event_name: campaign.event_name || '',
          scheduled_at,
        }),
      })
      setCampaign(data.campaign)
      await loadCampaigns()
      showBanner('ok', 'Campaign saved')
    })
  }

  const deleteCampaignById = async (id) => {
    if (!id) return
    if (!window.confirm('Delete this campaign and all its contacts?')) return
    await act('del-c', async () => {
      await apiFetch(`/admin/ai-team/campaigns/${id}`, { method: 'DELETE' })
      if (activeId === id) {
        setActiveId(null)
        setCampaign(null)
        setRecipients([])
      }
      await loadCampaigns()
      if (isCampaignPage && routeCampaignId === id) {
        navigate('/marketing/apify')
      }
      showBanner('ok', 'Campaign deleted')
    })
  }

  const deleteCampaign = async () => {
    await deleteCampaignById(activeId)
  }

  const resetCsvUpload = () => {
    setCsvFile(null)
    setCsvHeaders([])
    setCsvContacts([])
    setCsvTotal(0)
    setCsvMapping({})
    setCsvDetected({})
    setCsvEmailOk(false)
    setCsvMapOpen(false)
  }

  const parseCsvFile = async (file) => {
    if (!file) return
    setCsvFile(file)
    const fd = new FormData()
    fd.append('file', file)
    const data = await apiUpload('/admin/ai-team/import/csv/preview', fd)
    const detected = data.detected_fields || data.suggested_mapping || {}
    const mapping = Object.keys(detected).length ? detected : guessCsvMapping(data.headers || [])
    setCsvHeaders(data.headers || [])
    setCsvContacts(data.contacts || [])
    setCsvTotal(data.contacts_count ?? data.total_rows ?? 0)
    setCsvMapping(mapping)
    setCsvDetected(detected)
    setCsvEmailOk(Boolean(data.email_detected || mapping.email))
    setCsvMapOpen(!data.email_detected && !mapping.email)
    if (!data.email_detected && !mapping.email) {
      showBanner('err', 'Could not auto-detect email column — pick it under Fix columns')
    }
  }

  const importCsvToCampaign = async () => {
    if (!activeId || !csvFile) {
      showBanner('err', 'Select a campaign and upload a sheet')
      return
    }
    if (!csvMapping.email && !csvEmailOk) {
      showBanner('err', 'No email column detected — open Fix columns and map Email')
      return
    }
    await act('csv', async () => {
      const fd = new FormData()
      fd.append('file', csvFile)
      if (csvMapping && Object.keys(csvMapping).length) {
        fd.append('mapping', JSON.stringify(csvMapping))
      }
      const data = await apiUpload(`/admin/ai-team/campaigns/${activeId}/import/csv`, fd)
      showBanner('ok', `Added ${data.created || 0} (${data.skipped || 0} skipped)`)
      resetCsvUpload()
      await loadCampaign(activeId)
      await loadCampaigns()
    })
  }

  const openSheetContactsPreview = () => {
    if (!csvContacts.length) {
      showBanner('err', 'No contacts with valid emails in this file yet')
      return
    }
    setContactsModal({
      title: `Sheet preview · ${csvContacts.length} contact${csvContacts.length === 1 ? '' : 's'}`,
      rows: csvContacts,
      source: 'sheet',
    })
  }

  const openAudiencePreview = () => {
    if (!recipients.length) {
      showBanner('err', 'Audience is empty — import a sheet first')
      return
    }
    setContactsModal({
      title: `Audience · ${recipients.length} contact${recipients.length === 1 ? '' : 's'}`,
      rows: recipients.map((r) => ({
        id: r.id,
        email: r.email,
        first_name: r.first_name,
        last_name: r.last_name,
        company_name: r.company_name,
        job_title: r.job_title,
        event_name: r.event_name,
        status: r.status,
      })),
      source: 'audience',
    })
  }

  const deleteContactFromPreview = async (row, index) => {
    if (contactsModal?.source === 'audience' && row.id && activeId) {
      if (!window.confirm(`Remove ${row.email} from this campaign?`)) return
      await act('del-contact', async () => {
        await apiFetch(`/admin/ai-team/campaigns/${activeId}/recipients/${row.id}`, { method: 'DELETE' })
        await loadCampaign(activeId)
        await loadCampaigns()
        setContactsModal((prev) => {
          if (!prev) return null
          const rows = prev.rows.filter((r) => r.id !== row.id)
          return rows.length ? { ...prev, rows, title: `Audience · ${rows.length} contacts` } : null
        })
        showBanner('ok', `Removed ${row.email}`)
      })
      return
    }
    setCsvContacts((prev) => {
      const next = prev.filter((r, i) => (row.email ? r.email !== row.email : i !== index))
      setCsvTotal(next.length)
      setContactsModal((modal) => {
        if (!modal || modal.source !== 'sheet') return modal
        return next.length
          ? { ...modal, rows: next, title: `Sheet preview · ${next.length} contacts` }
          : null
      })
      return next
    })
  }

  const pauseCampaign = async (id = activeId) => {
    if (!id) return
    await act('pause', async () => {
      const data = await apiFetch(`/admin/ai-team/campaigns/${id}/pause`, { method: 'POST' })
      if (data.campaign && id === activeId) setCampaign(data.campaign)
      showBanner('ok', data.message || 'Paused')
      await loadCampaigns()
      if (id === activeId) await loadCampaign(id)
    })
  }

  const resumeCampaign = async (id = activeId) => {
    if (!id) return
    await act('resume', async () => {
      const data = await apiFetch(`/admin/ai-team/campaigns/${id}/resume`, { method: 'POST' })
      if (data.campaign && id === activeId) setCampaign(data.campaign)
      showBanner('ok', data.message || 'Resumed')
      await loadCampaigns()
      if (id === activeId) await loadCampaign(id)
    })
  }

  const scheduleCampaign = async () => {
    if (!activeId || !campaign) return
    const local = campaign._scheduleLocal || toLocalInputValue(campaign.scheduled_at)
    if (!local) {
      showBanner('err', 'Pick a date and time first')
      return
    }
    const when = new Date(local)
    if (Number.isNaN(when.getTime())) {
      showBanner('err', 'Invalid schedule time')
      return
    }
    await act('schedule', async () => {
      const data = await apiFetch(`/admin/ai-team/campaigns/${activeId}/schedule`, {
        method: 'POST',
        body: JSON.stringify({ scheduled_at: when.toISOString() }),
      })
      if (data.campaign) setCampaign({ ...data.campaign, _scheduleLocal: undefined })
      showBanner('ok', data.message || 'Scheduled')
      await loadCampaigns()
    })
  }

  const clearSchedule = async () => {
    if (!activeId || !campaign) return
    await act('clear-sched', async () => {
      const data = await apiFetch(`/admin/ai-team/campaigns/${activeId}`, {
        method: 'PUT',
        body: JSON.stringify({ scheduled_at: null }),
      })
      setCampaign({ ...data.campaign, _scheduleLocal: '' })
      showBanner('ok', 'Schedule cleared')
      await loadCampaigns()
    })
  }

  const viewCampaignSent = (c) => {
    setTrackingFilter('sent')
    setTrackingCampaignId(c.id)
    navigate(`/marketing/apify?tab=tracking&filter=sent`)
    setTab('tracking')
  }

  const editCampaign = (c) => {
    navigate(`/marketing/apify/campaigns/${c.id}`)
  }

  const pauseScrape = async (runId) => {
    if (!runId) return
    if (!window.confirm('Force pause this scrape? It will stop as soon as possible.')) return
    await act('scrape-pause', async () => {
      const data = await apiFetch(`/admin/ai-team/apify/runs/${runId}/abort`, { method: 'POST' })
      showBanner('ok', data.message || 'Scrape paused')
      await loadApifyRuns()
    })
  }

  const updateScrapeRun = async (run) => {
    if (!run?.id) return
    const url = run.expo_url || 'this directory'
    if (!window.confirm(`Update scrape for this URL?\n\n${url}\n\nExisting emails stay. Only new emails are added.`)) return
    await act(`update-${run.id}`, async () => {
      const data = await apiFetch(`/admin/ai-team/apify/runs/${run.id}/update`, {
        method: 'POST',
        body: JSON.stringify({
          follow_websites: scrapeFollowWebsites,
          engine: scrapeEngine || 'auto',
        }),
      })
      const added = data.emails_added
      const skipped = data.emails_skipped
      const found = data.emails_found
      const msg = data.message
        || (added != null
          ? `Update · ${found ?? '—'} found · ${skipped ?? 0} already had · ${added} new`
          : 'Update started')
      showBanner('ok', msg)
      await loadApifyRuns()
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

  const sendIntervalSec = Math.max(1, Number(settings.send_interval_seconds) || 20)
  const sendAll = async (resend = false) => {
    if (!activeId) return
    const n = recipients.filter((r) => r.status === 'pending' || r.status === 'failed').length
    const sentN = recipients.filter((r) => r.status === 'sent').length
    const queueN = resend ? (n + sentN) : (n || 0)
    if (!queueN && !resend) {
      if (sentN > 0) {
        if (!window.confirm(
          `All ${sentN} contact(s) were already sent.\n\nResend the campaign to them again?`,
        )) return
        return sendAll(true)
      }
      showBanner('err', 'No pending contacts. Drop Excel/CSV and click Add to audience first.')
      return
    }
    const eta = Math.max(1, Math.ceil((queueN || 0) * sendIntervalSec / 60))
    if (!window.confirm(
      `Queue ${queueN || campaign?.total_count || 0} email(s) · 1 every ${sendIntervalSec}s (~${eta} min)?\n\n`
      + 'Send a Test first if you have not. Watch the progress bar on this page.',
    )) return
    await act('send', async () => {
      const data = await apiFetch(`/admin/ai-team/campaigns/${activeId}/send`, {
        method: 'POST',
        body: JSON.stringify({ resend: !!resend }),
      })
      if (data.campaign) setCampaign(data.campaign)
      showBanner('ok', data.message || 'Sending queued…')
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

  const deleteTemplate = async (id) => {
    const tid = id || tplDraft?.id
    if (!tid || !window.confirm('Delete this template?')) return
    await act('tpl-del', async () => {
      await apiFetch(`/admin/ai-team/templates/${tid}`, { method: 'DELETE' })
      if (activeTplId === tid) setActiveTplId(null)
      await loadTemplates()
      showBanner('ok', 'Template deleted')
    })
  }

  const openReply = (row) => {
    if (!row?.id) return
    navigate(`/marketing/apify/recipients/${row.id}/reply`)
  }

  const openSentEmail = (row) => {
    if (!row?.id) return
    navigate(`/marketing/apify/recipients/${row.id}`)
  }

  const openInboxMessage = (msg) => {
    if (!msg?.id) return
    const isUnread = msg.unread !== false && !msg.read_at
    if (isUnread) {
      const dec = (n) => Math.max(0, Number(n ?? 0) - 1)
      setTracking((prev) => {
        if (!prev) return prev
        const base = prev.summary?.inbox_unread ?? prev.summary?.inbox ?? 0
        return {
          ...prev,
          inbox: (prev.inbox || []).map((m) => (
            m.id === msg.id ? { ...m, read_at: new Date().toISOString(), unread: false } : m
          )),
          summary: { ...(prev.summary || {}), inbox_unread: dec(base) },
        }
      })
      setKpis((prev) => (prev ? { ...prev, inbox_unread: dec(prev.inbox_unread ?? prev.inbox) } : prev))
    }
    navigate(`/marketing/apify/inbox/${msg.id}`)
  }

  const deleteInboxMessage = async (msg) => {
    const mid = msg?.id
    const from = msg?.from_email || msg?.email || 'unknown'
    if (!mid || !window.confirm(`Delete inbox message from ${from}?`)) return
    await act('inbox-del', async () => {
      const data = await apiFetch(`/admin/ai-team/tracking/inbox/${mid}`, { method: 'DELETE' })
      const left = data?.inbox != null ? Number(data.inbox) : null
      const unreadLeft = data?.inbox_unread != null ? Number(data.inbox_unread) : null
      setTracking((prev) => {
        if (!prev) return prev
        const wasUnread = (prev.inbox || []).find((m) => m.id === mid)?.unread !== false
          && !(prev.inbox || []).find((m) => m.id === mid)?.read_at
        const nextInbox = left != null ? left : Math.max(0, Number(prev.summary?.inbox ?? 1) - 1)
        const nextUnread = unreadLeft != null
          ? unreadLeft
          : Math.max(0, Number(prev.summary?.inbox_unread ?? prev.summary?.inbox ?? 0) - (wasUnread ? 1 : 0))
        return {
          ...prev,
          inbox: (prev.inbox || []).filter((m) => m.id !== mid),
          summary: { ...(prev.summary || {}), inbox: nextInbox, inbox_unread: nextUnread },
        }
      })
      setKpis((prev) => {
        const nextInbox = left != null ? left : Math.max(0, Number(prev?.inbox ?? 1) - 1)
        const nextUnread = unreadLeft != null
          ? unreadLeft
          : Math.max(0, Number(prev?.inbox_unread ?? 0) - (msg.unread !== false && !msg.read_at ? 1 : 0))
        return prev ? { ...prev, inbox: nextInbox, inbox_unread: nextUnread } : { inbox: nextInbox, inbox_unread: nextUnread }
      })
      showBanner('ok', 'Inbox message deleted')
      await Promise.all([loadTracking(), loadKpis().catch(() => null)])
    })
  }

  const startBulkScrapes = async () => {
    const lines = bulkUrls.split(/\r?\n/).map((l) => l.trim()).filter((l) => l.startsWith('http'))
    if (!lines.length) {
      showBanner('err', 'Paste one https:// directory URL per line')
      return
    }
    if (lines.length > 15) {
      showBanner('err', 'Bulk scrape is limited to 15 URLs — run in batches')
      return
    }
    await act('bulk-scrape', async () => {
      let ok = 0
      let fail = 0
      let emails = 0
      for (let i = 0; i < lines.length; i += 1) {
        const url = lines[i]
        showBanner('ok', `Scraping ${i + 1}/${lines.length}…`)
        try {
          const data = await apiFetch('/admin/ai-team/scrape', {
            method: 'POST',
            body: JSON.stringify({
              expo_url: url,
              follow_websites: scrapeFollowWebsites,
              engine: scrapeEngine || 'auto',
            }),
          })
          ok += 1
          emails += Number(data.emails_found || data.run?.emails_found || data.run?.item_count || 0)
        } catch {
          fail += 1
        }
        await loadApifyRuns().catch(() => {})
      }
      showBanner(fail ? 'err' : 'ok', `Bulk done · ${ok} ok · ${fail} failed · ${emails} email(s)`)
      await loadApifyRuns()
    })
  }

  const fillBulkFromCurated = async () => {
    let rows = exhibitionDirs
    if (!rows.length) rows = await loadExhibitionDirs()
    const urls = (rows || []).map((e) => e.url).filter(Boolean)
    if (!urls.length) {
      showBanner('err', 'Curated exhibition list empty — check API')
      return
    }
    setBulkUrls(urls.join('\n'))
    setBulkOpen(true)
    showBanner('ok', `${urls.length} exhibition directory URLs filled`)
  }

  const deleteScrapeRun = async (run) => {
    const rid = run?.id
    if (!rid) return
    const label = (run.expo_url || rid).slice(0, 60)
    if (!window.confirm(`Delete this scrape run?\n${label}`)) return
    await act('scrape-del', async () => {
      await apiFetch(`/admin/ai-team/apify/runs/${rid}`, { method: 'DELETE' })
      showBanner('ok', 'Scrape run deleted')
      await Promise.all([loadApifyRuns(), loadKpis().catch(() => null)])
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
      if (cid) navigate(`/marketing/apify/campaigns/${cid}`)
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
          imap_password: imapPassword || undefined,
          resend_api_key: resendKey || undefined,
          apify_token: apifyToken || undefined,
        }),
      })
      setSettings(data.settings || {})
      setSmtpPassword('')
      setImapPassword('')
      setResendKey('')
      setApifyToken('')
      showBanner('ok', 'Settings saved')
    })
  }

  const refreshInbox = async () => {
    await act('imap-refresh', async () => {
      const data = await apiFetch('/admin/ai-team/tracking/imap/refresh', { method: 'POST' })
      const samples = Array.isArray(data.unmatched_samples) ? data.unmatched_samples : []
      const extra = samples.length
        ? ` Unmatched From: ${samples.map((s) => s.from).join(', ')}`
        : ''
      showBanner(
        data.matched > 0 ? 'ok' : (data.scanned > 0 ? 'err' : 'ok'),
        `${data.message || 'Inbox refreshed'}${extra && !(data.message || '').includes('Unmatched From') ? extra : ''}`,
      )
      setSettings((prev) => ({
        ...prev,
        imap_last_sync_at: data.imap_last_sync_at || prev.imap_last_sync_at,
        imap_last_sync_message: data.imap_last_sync_message || prev.imap_last_sync_message,
      }))
      setTrackingFilter('inbox')
      await loadTracking()
    })
  }

  const runTestImap = async () => {
    await act('imap-test', async () => {
      try {
        const data = await apiFetch('/admin/ai-team/test/imap', { method: 'POST' })
        setImapTestResult(data)
        showBanner(data.ok ? 'ok' : 'err', data.message || 'IMAP test done')
      } catch (e) {
        setImapTestResult({ ok: false, message: e?.message || 'IMAP test failed' })
        throw e
      }
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
  const pendingCount = recipients.filter((r) => r.status === 'pending').length
  const sendEtaMin = pendingCount > 0 ? Math.max(1, Math.ceil(pendingCount * sendIntervalSec / 60)) : 0

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
            <div className="ait-page-sub">Scrape → template → campaign → track</div>
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

      {/* Keep workflow + KPIs + tabs on every Apify page so the tab bar does not jump */}
      <div className="ait-hub-chrome">
        <div className="ait-workflow" aria-label="Suggested workflow">
          {WORKFLOW_STEPS.map((s, i) => (
            <React.Fragment key={s.id}>
              {i > 0 && <span className="ait-workflow-arrow" aria-hidden>→</span>}
              <button
                type="button"
                className={`ait-workflow-step ${!isCampaignPage && tab === s.id ? 'active' : ''}`}
                onClick={() => goTab(s.id)}
              >
                <span className="ait-workflow-n">{s.n}</span>
                {s.label}
              </button>
            </React.Fragment>
          ))}
          <span className="ait-workflow-hint">Setup: Sending · Apify API</span>
        </div>

        <div className="ait-stats ait-stats-home" aria-label="Outreach KPIs">
          {HOME_KPIS.map((k) => {
            const val = kpis?.[k.key]
            return (
              <button
                key={k.key}
                type="button"
                className={`ait-stat ait-stat-click tone-${k.tone}`}
                onClick={() => openKpi(k.filter)}
                title={`Open ${k.label.toLowerCase()} list`}
              >
                <div className="ait-stat-lbl">{k.label}</div>
                <div className="ait-stat-val">{val == null ? '—' : val}</div>
                <div className="ait-stat-sub">{k.hint} · click to open</div>
              </button>
            )
          })}
        </div>

        <div className="ait-tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`ait-tab ${!isCampaignPage && tab === t.id ? 'active' : ''}`}
              onClick={() => goTab(t.id)}
            >
              <i className={`ti ${t.icon}`} style={{ fontSize: 12 }} />
              {t.label}
                {t.id === 'tracking' && (() => {
                  const unreadN = Number(
                    tracking?.summary?.inbox_unread
                    ?? kpis?.inbox_unread
                    ?? 0,
                  )
                  return unreadN > 0 ? <span className="ait-tab-badge">{unreadN}</span> : null
                })()}
            </button>
          ))}
        </div>
      </div>

      <div className="ait-content">
        {(tab === 'campaigns' && !isCampaignPage) && (
          <div className="ait-campaigns-page">
            <div className="ait-card ait-campaigns-table-card ait-sec ait-sec-list">
              <div className="ait-card-hdr">
                <div className="ait-sec-title-wrap">
                  <span className="ait-sec-step ait-sec-step-list"><i className="ti ti-list" /></span>
                  <div>
                    <span className="ait-card-title">Campaigns</span>
                    <span className="ait-sec-sub">Open Edit to configure & send</span>
                  </div>
                </div>
                <div className="ait-btn-row" style={{ margin: 0, gap: 8 }}>
                  <input
                    className="ait-inline-input"
                    placeholder="New campaign name"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') createCampaign() }}
                  />
                  <button type="button" className="ait-btn primary sm" disabled={!!busy} onClick={createCampaign}>Create</button>
                </div>
              </div>
              <div className="ait-table-wrap" style={{ marginTop: 0 }}>
                <table className="ait-tbl ait-tbl-campaigns">
                  <thead>
                    <tr>
                      <th>Campaign</th>
                      <th>Status</th>
                      <th>Audience</th>
                      <th>Sent</th>
                      <th>Opened</th>
                      <th>Schedule</th>
                      <th>Updated</th>
                      <th style={{ width: 220 }} />
                    </tr>
                  </thead>
                  <tbody>
                    {campaigns.map((c) => (
                      <tr key={c.id} className={activeId === c.id ? 'ait-row-active' : ''}>
                        <td>
                          <button type="button" className="ait-link-btn" onClick={() => editCampaign(c)}>
                            <strong>{c.name}</strong>
                          </button>
                          {c.event_name ? <div className="ait-contact-email">{c.event_name}</div> : null}
                        </td>
                        <td><span className={`ait-badge ${statusBadge(c.status)}`}>{c.status}</span></td>
                        <td className="ait-muted-num">{c.total_count || 0}</td>
                        <td className="ait-muted-num">{c.sent_count || 0}</td>
                        <td className="ait-muted-num">{c.opened_count || 0}</td>
                        <td style={{ fontSize: 12, color: 'var(--ait-text3)' }}>
                          {c.scheduled_at ? new Date(c.scheduled_at).toLocaleString() : '—'}
                        </td>
                        <td style={{ fontSize: 12, color: 'var(--ait-text3)' }}>{timeAgo(c.updated_at)}</td>
                        <td>
                          <div className="ait-btn-row" style={{ margin: 0, gap: 4, flexWrap: 'wrap' }}>
                            <button type="button" className="ait-btn xs" onClick={() => editCampaign(c)}>Edit</button>
                            <button type="button" className="ait-btn xs" onClick={() => viewCampaignSent(c)}>Sent</button>
                            {c.status === 'sending' || c.status === 'scheduled' ? (
                              <button type="button" className="ait-btn xs" disabled={!!busy} onClick={() => pauseCampaign(c.id)}>Pause</button>
                            ) : null}
                            {c.status === 'paused' || c.status === 'paused_daily_limit' ? (
                              <button type="button" className="ait-btn xs primary" disabled={!!busy} onClick={() => resumeCampaign(c.id)}>Resume</button>
                            ) : null}
                            <button type="button" className="ait-btn xs danger" disabled={!!busy || c.status === 'sending'} onClick={() => deleteCampaignById(c.id)}>Delete</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {!campaigns.length && (
                      <tr>
                        <td colSpan={8} style={{ textAlign: 'center', color: 'var(--ait-text3)', padding: 24 }}>
                          No campaigns yet — create one, pick a template, upload Excel.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {isCampaignPage && (
          <div className="ait-campaigns-page">
            <div className="ait-campaign-main">
              <div className="ait-btn-row" style={{ marginBottom: 10, marginTop: 0 }}>
                <button type="button" className="ait-btn sm" onClick={() => navigate('/marketing/apify')}>
                  ← Campaigns
                </button>
                <span className="ait-toolbar-meta" style={{ marginLeft: 4 }}>
                  {campaign?.name || 'Campaign settings'}
                </span>
              </div>
              {!campaign ? (
                <div className="ait-empty"><strong>Loading campaign…</strong></div>
              ) : (
                <>
                  <div className="ait-toolbar">
                    <div className="ait-toolbar-left">
                      <span className={`ait-badge ${statusBadge(campaign.status)}`}>{campaign.status}</span>
                      <span className="ait-toolbar-meta">{campaign.sent_count}/{campaign.total_count} sent</span>
                      {campaign.scheduled_at ? (
                        <span className="ait-toolbar-meta">Scheduled {new Date(campaign.scheduled_at).toLocaleString()}</span>
                      ) : null}
                    </div>
                    <div className="ait-toolbar-right">
                      {(campaign.status === 'sending' || campaign.status === 'scheduled') && (
                        <button type="button" className="ait-btn sm" disabled={!!busy} onClick={() => pauseCampaign()}>Pause</button>
                      )}
                      {(campaign.status === 'paused' || campaign.status === 'paused_daily_limit') && (
                        <button type="button" className="ait-btn sm primary" disabled={!!busy} onClick={() => resumeCampaign()}>Resume</button>
                      )}
                      <button type="button" className="ait-btn sm" disabled={!!busy || campaign.status === 'sending'} onClick={saveCampaignMeta}>Save</button>
                      <button type="button" className="ait-btn danger sm" disabled={!!busy || campaign.status === 'sending'} onClick={deleteCampaign}>Delete</button>
                    </div>
                  </div>

                  {(campaign.status === 'sending' || campaign.status === 'paused' || campaign.status === 'paused_daily_limit' || campaign.status === 'scheduled') && (
                    <div className="ait-send-progress">
                      <div className="ait-send-progress-top">
                        <div>
                          <div className="ait-send-progress-title">
                            {campaign.status === 'sending' && 'Sending queue'}
                            {campaign.status === 'paused' && 'Paused'}
                            {campaign.status === 'paused_daily_limit' && 'Paused — daily limit'}
                            {campaign.status === 'scheduled' && 'Scheduled'}
                          </div>
                          <div className="ait-send-progress-sub">
                            {campaign.status === 'sending' && `1 email every ${sendIntervalSec}s · ~${sendEtaMin || '…'} min left for ${pendingCount} queued`}
                            {campaign.status === 'paused' && 'Sending stopped — click Resume to continue the queue'}
                            {campaign.status === 'paused_daily_limit' && (campaign.last_error || 'Raise Max/day under Sending, then Resume')}
                            {campaign.status === 'scheduled' && `Starts ${campaign.scheduled_at ? new Date(campaign.scheduled_at).toLocaleString() : '—'} · Pause to cancel schedule`}
                          </div>
                        </div>
                        <div className="ait-btn-row" style={{ margin: 0, gap: 6 }}>
                          {campaign.status === 'sending' && (
                            <>
                              <button type="button" className="ait-btn xs" disabled={!!busy} onClick={() => pauseCampaign()}>Pause</button>
                              <button type="button" className="ait-btn danger xs" disabled={!!busy} onClick={cancelSend}>Cancel</button>
                            </>
                          )}
                          {(campaign.status === 'paused' || campaign.status === 'paused_daily_limit') && (
                            <button type="button" className="ait-btn xs primary" disabled={!!busy} onClick={() => resumeCampaign()}>Resume</button>
                          )}
                        </div>
                      </div>
                      {(campaign.status === 'sending' || campaign.status === 'paused') && (
                        <>
                          <div className="ait-send-progress-bar">
                            <div className="ait-send-progress-fill" style={{ width: `${sendPct}%` }} />
                          </div>
                          <div className="ait-send-progress-stats">
                            <span><strong>{campaign.sent_count || 0}</strong> sent</span>
                            <span><strong>{campaign.failed_count || 0}</strong> failed</span>
                            <span><strong>{pendingCount}</strong> queued</span>
                            <span><strong>{sendPct}%</strong> done</span>
                          </div>
                        </>
                      )}
                    </div>
                  )}

                  <div className="ait-card ait-sec ait-sec-campaign">
                    <div className="ait-card-hdr">
                      <div className="ait-sec-title-wrap">
                        <span className="ait-sec-step">1</span>
                        <div>
                          <span className="ait-card-title">Campaign</span>
                          <span className="ait-sec-sub">Name, event & schedule</span>
                        </div>
                      </div>
                    </div>
                    <div className="ait-card-body">
                      <div className="ait-fg-2" style={{ marginBottom: 0 }}>
                        <div className="ait-field">
                          <label>Campaign name</label>
                          <input
                            className="ait-campaign-name-input"
                            value={campaign.name || ''}
                            disabled={campaign.status === 'sending'}
                            placeholder="e.g. London Packaging Week — outreach"
                            onChange={(e) => setCampaign({ ...campaign, name: e.target.value })}
                          />
                        </div>
                        <div className="ait-field">
                          <label>Event name · {'{{event-name}}'}</label>
                          <input
                            value={campaign.event_name || ''}
                            disabled={campaign.status === 'sending'}
                            placeholder="e.g. London Packaging Week"
                            onChange={(e) => setCampaign({ ...campaign, event_name: e.target.value })}
                          />
                          <span className="ait-hint" style={{ display: 'block', marginTop: 4 }}>
                            Used for all emails unless Excel has an Event name column.
                          </span>
                        </div>
                      </div>
                      <div className="ait-fg-2" style={{ marginTop: 12 }}>
                        <div className="ait-field">
                          <label>Schedule send</label>
                          <input
                            type="datetime-local"
                            disabled={campaign.status === 'sending'}
                            value={campaign._scheduleLocal ?? toLocalInputValue(campaign.scheduled_at)}
                            onChange={(e) => setCampaign({ ...campaign, _scheduleLocal: e.target.value })}
                          />
                        </div>
                        <div className="ait-field">
                          <label>&nbsp;</label>
                          <div className="ait-btn-row" style={{ margin: 0 }}>
                            <button type="button" className="ait-btn sm" disabled={!!busy || campaign.status === 'sending'} onClick={scheduleCampaign}>Schedule</button>
                            <button
                              type="button"
                              className="ait-btn ghost sm"
                              disabled={!!busy || campaign.status === 'sending'}
                              onClick={clearSchedule}
                            >
                              Clear
                            </button>
                            <button type="button" className="ait-btn ghost sm" disabled={!!busy || campaign.status === 'sending'} onClick={saveCampaignMeta}>Save</button>
                          </div>
                          <span className="ait-hint" style={{ display: 'block', marginTop: 4 }}>
                            Celery starts the queue at this time. Pause stops until Resume.
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="ait-card ait-sec ait-sec-template">
                    <div className="ait-card-hdr">
                      <div className="ait-sec-title-wrap">
                        <span className="ait-sec-step">2</span>
                        <div>
                          <span className="ait-card-title">Template</span>
                          <span className="ait-sec-sub">Email subject & HTML</span>
                        </div>
                      </div>
                      <button type="button" className="ait-btn xs" onClick={() => { navigate('/marketing/apify'); setTab('templates') }}>Edit templates</button>
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

                  <div className="ait-card ait-sec ait-sec-audience">
                    <div className="ait-card-hdr">
                      <div className="ait-sec-title-wrap">
                        <span className="ait-sec-step">3</span>
                        <div>
                          <span className="ait-card-title">Audience</span>
                          <span className="ait-sec-sub">{campaign.total_count || 0} contact{(campaign.total_count || 0) === 1 ? '' : 's'}</span>
                        </div>
                      </div>
                      <div className="ait-btn-row" style={{ margin: 0, gap: 6 }}>
                        <button type="button" className="ait-btn xs" disabled={!recipients.length} onClick={openAudiencePreview}>
                          Preview contacts
                        </button>
                        <button type="button" className="ait-btn danger xs" disabled={!recipients.length || campaign.status === 'sending'} onClick={clearAudience}>Clear</button>
                      </div>
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
                        <input
                          id="apify-campaign-csv"
                          type="file"
                          accept=".csv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                          style={{ display: 'none' }}
                          onChange={(e) => {
                            const f = e.target.files?.[0]
                            if (f) parseCsvFile(f).catch((err) => showBanner('err', err?.message || 'Parse failed'))
                          }}
                        />
                        <div style={{ fontWeight: 600 }}>{csvFile ? csvFile.name : 'Drop Excel or CSV'}</div>
                        <div style={{ fontSize: 12, color: 'var(--ait-text3)', marginTop: 6 }}>
                          Columns auto-detected (name, email, company…) — no mapping needed
                        </div>
                      </div>
                      {csvHeaders.length > 0 && (
                        <div style={{ marginTop: 14 }}>
                          <div style={{ fontSize: 13, color: 'var(--ait-text2)', marginBottom: 8 }}>
                            {csvEmailOk
                              ? `Detected ${csvTotal} contact${csvTotal === 1 ? '' : 's'} with email`
                              : 'Email column not found — use Fix columns'}
                          </div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
                            {CSV_MAP_FIELDS.filter((f) => csvDetected[f.key] || csvMapping[f.key]).map((f) => (
                              <span
                                key={f.key}
                                style={{
                                  fontSize: 11,
                                  padding: '3px 8px',
                                  borderRadius: 6,
                                  background: 'var(--ait-surface2, #f1f3f5)',
                                  color: 'var(--ait-text2)',
                                }}
                              >
                                {f.label}: <strong>{csvDetected[f.key] || csvMapping[f.key]}</strong>
                              </span>
                            ))}
                            {!csvDetected.email && !csvMapping.email && (
                              <span style={{ fontSize: 11, color: '#b42318' }}>Email not detected</span>
                            )}
                          </div>
                          <div className="ait-btn-row">
                            <button type="button" className="ait-btn sm" disabled={!csvContacts.length} onClick={openSheetContactsPreview}>
                              Preview contacts
                            </button>
                            <button
                              type="button"
                              className="ait-btn primary sm"
                              disabled={!!busy || (!csvMapping.email && !csvEmailOk)}
                              onClick={importCsvToCampaign}
                            >
                              Add to audience ({csvTotal})
                            </button>
                            <button type="button" className="ait-btn ghost sm" onClick={() => setCsvMapOpen((v) => !v)}>
                              {csvMapOpen ? 'Hide columns' : 'Fix columns'}
                            </button>
                            <button type="button" className="ait-btn ghost sm" onClick={resetCsvUpload}>Cancel</button>
                          </div>
                          {csvMapOpen && (
                            <div className="ait-fg-3" style={{ marginTop: 14 }}>
                              <p className="ait-hint" style={{ marginTop: 0 }}>Only needed if auto-detect got a column wrong.</p>
                              {CSV_MAP_FIELDS.map((f) => (
                                <div className="ait-field" key={f.key}>
                                  <label>{f.label}{f.required ? ' *' : ''}</label>
                                  <select
                                    value={csvMapping[f.key] || ''}
                                    onChange={(e) => {
                                      const next = { ...csvMapping, [f.key]: e.target.value }
                                      setCsvMapping(next)
                                      setCsvEmailOk(Boolean(next.email))
                                    }}
                                  >
                                    <option value="">— skip —</option>
                                    {csvHeaders.map((h) => <option key={h} value={h}>{h}</option>)}
                                  </select>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                      {recipients.length > 0 && (
                        <div className="ait-table-wrap" style={{ marginTop: 16 }}>
                          <table className="ait-tbl ait-tbl-contacts">
                            <thead>
                              <tr>
                                <th>Contact</th>
                                <th>Company</th>
                                <th>Status</th>
                              </tr>
                            </thead>
                            <tbody>
                              {recipients.slice(0, 8).map((r) => (
                                <tr key={r.id}>
                                  <td>
                                    <div className="ait-contact-name">{contactDisplayName(r)}</div>
                                    <div className="ait-contact-email">{r.email}</div>
                                  </td>
                                  <td>{r.company_name || '—'}</td>
                                  <td><span className={`ait-badge ${statusBadge(r.status)}`}>{r.status || '—'}</span></td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {recipients.length > 8 && (
                            <button type="button" className="ait-btn ghost xs" style={{ marginTop: 8 }} onClick={openAudiencePreview}>
                              View all {recipients.length} contacts
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="ait-card ait-sec ait-sec-send">
                    <div className="ait-card-hdr">
                      <div className="ait-sec-title-wrap">
                        <span className="ait-sec-step">4</span>
                        <div>
                          <span className="ait-card-title">Preview & send</span>
                          <span className="ait-sec-sub">Test mail, then send all</span>
                        </div>
                      </div>
                    </div>
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
                        <button
                          type="button"
                          className="ait-btn primary"
                          disabled={!!busy || campaign.status === 'sending' || !campaign.total_count}
                          onClick={() => sendAll(false)}
                        >
                          {campaign.status === 'paused_daily_limit' ? 'Resume send' : 'Send all'} ({pendingCount || 0} pending)
                        </button>
                        {(campaign.sent_count > 0 || recipients.some((r) => r.status === 'sent')) && (
                          <button
                            type="button"
                            className="ait-btn sm"
                            disabled={!!busy || campaign.status === 'sending'}
                            onClick={() => sendAll(true)}
                          >
                            Resend
                          </button>
                        )}
                        <button
                          type="button"
                          className="ait-btn ghost sm"
                          disabled={!campaign.sent_count}
                          onClick={() => viewCampaignSent(campaign)}
                        >
                          View sent
                        </button>
                      </div>
                      <p className="ait-hint" style={{ marginTop: 10 }}>
                        <strong>Send test</strong> always prefixes the subject with <code>[TEST]</code> — that is not the live campaign.
                        <strong> Send all</strong> uses the real subject only. Queue: 1 email every <strong>{sendIntervalSec}s</strong>.
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
            <div className="ait-card ait-sec ait-sec-tracking">
              <div className="ait-card-hdr">
                <div className="ait-sec-title-wrap">
                  <span className="ait-sec-step"><i className="ti ti-chart-bar" /></span>
                  <div>
                    <span className="ait-card-title">Campaigns</span>
                    <span className="ait-sec-sub">Filter tracking by campaign</span>
                  </div>
                </div>
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
                            <button type="button" className="ait-btn xs primary" onClick={() => editCampaign(c)}>Open</button>
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

            <div className="ait-card ait-sec ait-sec-activity">
              <div className="ait-card-hdr">
                <div className="ait-sec-title-wrap">
                  <span className="ait-sec-step"><i className="ti ti-activity" /></span>
                  <div>
                    <span className="ait-card-title">Activity</span>
                    <span className="ait-sec-sub">Sent, opens, inbox &amp; unsubs</span>
                  </div>
                </div>
                <div className="ait-seg ait-seg-right">
                  {[['all', 'All'], ['sent', 'Sent'], ['opened', 'Opened'], ['clicked', 'Clicked'], ['received', 'Received'], ['inbox', 'Inbox'], ['unsubscribed', 'Unsubscribed'], ['unsub_list', 'Unsub list'], ['failed', 'Failed'], ['pending', 'Pending']].map(([id, label]) => (
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
                <div className="ait-btn-row" style={{ marginTop: 8 }}>
                  <button type="button" className="ait-btn sm" disabled={!!busy} onClick={() => act('tracking', loadTracking)}>Apply filters</button>
                  <button type="button" className="ait-btn sm primary" disabled={!!busy} onClick={refreshInbox} title="Fetch mail from IMAP inbox">
                    <i className="ti ti-refresh" style={{ marginRight: 6 }} />Refresh inbox
                  </button>
                </div>
                {settings.imap_last_sync_message && (
                  <p className="ait-hint" style={{ marginTop: 8 }}>
                    Last IMAP: {settings.imap_last_sync_message}
                    {settings.imap_last_sync_at ? ` · ${timeAgo(settings.imap_last_sync_at)}` : ''}
                  </p>
                )}
                {trackingFilter === 'inbox' && (
                  <p className="ait-hint" style={{ marginTop: 8 }}>
                    Inbox lists every message pulled from IMAP (matched or not). Use Refresh inbox to fetch.
                    The number on the Tracking tab is <strong>unread</strong> only — it clears when you open a message.
                  </p>
                )}
                {trackingFilter === 'opened' && (
                  <p className="ait-hint" style={{ marginTop: 8 }}>
                    Opened = tracking pixel loaded. Some email apps block images (opens stay blank even if read).
                  </p>
                )}
                {trackingFilter === 'clicked' && (
                  <p className="ait-hint" style={{ marginTop: 8 }}>
                    Clicked = any button/link in the sent HTML (links are wrapped through our tracker on send).
                  </p>
                )}
              </div>
              {trackingFilter === 'unsub_list' ? (
              <div className="ait-table-wrap">
                <p className="ait-hint" style={{ marginTop: 0 }}>
                  Stored in DB table <code>ai_team_email_suppressions</code> — global opt-out from unsubscribe links.
                  These emails are skipped on every future campaign import/send.
                </p>
                <table className="ait-tbl ait-tbl-contacts">
                  <thead>
                    <tr>
                      <th>Email</th>
                      <th>Unsubscribed</th>
                      <th>Campaign</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {suppressions.map((s) => (
                      <tr key={s.id}>
                        <td>{s.email}</td>
                        <td style={{ fontSize: 12, color: 'var(--ait-text3)' }}>{s.unsubscribed_at ? new Date(s.unsubscribed_at).toLocaleString() : '—'}</td>
                        <td style={{ fontSize: 12 }}>{s.source_campaign_id ? String(s.source_campaign_id).slice(0, 8) : '—'}</td>
                        <td>
                          <button
                            type="button"
                            className="ait-btn xs danger"
                            disabled={!!busy}
                            onClick={() => act('unsub-del', async () => {
                              if (!window.confirm(`Remove ${s.email} from unsubscribe list?`)) return
                              await apiFetch(`/admin/ai-team/suppressions/${s.id}`, { method: 'DELETE' })
                              showBanner('ok', 'Removed from unsub list')
                              await loadTracking()
                            })}
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                    {!suppressions.length && (
                      <tr>
                        <td colSpan={4} style={{ textAlign: 'center', color: 'var(--ait-text3)', padding: 20 }}>
                          No global unsubscribes yet
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              ) : trackingFilter === 'inbox' ? (
              <div className="ait-table-wrap">
                <table className="ait-tbl">
                  <thead>
                    <tr>
                      <th>From</th>
                      <th>Subject</th>
                      <th>Matched</th>
                      <th>When</th>
                      <th>Preview</th>
                      <th style={{ width: 100 }} />
                    </tr>
                  </thead>
                  <tbody>
                    {(tracking?.inbox || []).map((m) => {
                      const unread = m.unread !== false && !m.read_at
                      return (
                      <tr key={m.id} className={unread ? 'ait-inbox-unread' : ''}>
                        <td style={{ fontSize: 12 }}>{m.from_email || '—'}</td>
                        <td><strong style={{ fontSize: 13, fontWeight: unread ? 700 : 500 }}>{m.subject || '(no subject)'}</strong></td>
                        <td>
                          {m.matched
                            ? <span className="ait-badge b-opened">yes</span>
                            : <span className="ait-badge b-pending">no</span>}
                        </td>
                        <td style={{ fontSize: 12, color: 'var(--ait-text3)' }}>{timeAgo(m.received_at)}</td>
                        <td className="ait-ellipsis" title={m.body_text || ''}>{(m.body_text || '').slice(0, 80) || '—'}</td>
                        <td>
                          <div className="ait-btn-row" style={{ margin: 0, gap: 4 }}>
                            <button type="button" className="ait-icon-btn" title="Open reply page" onClick={() => openInboxMessage(m)}>
                              <i className="ti ti-mail-opened" />
                            </button>
                            <button type="button" className="ait-icon-btn danger" title="Delete" disabled={!!busy} onClick={() => deleteInboxMessage(m)}>
                              <i className="ti ti-trash" />
                            </button>
                          </div>
                        </td>
                      </tr>
                      )
                    })}
                    {!(tracking?.inbox || []).length && (
                      <tr>
                        <td colSpan={6} style={{ textAlign: 'center', color: 'var(--ait-text3)', padding: 20 }}>
                          No inbox messages yet — click Refresh inbox
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              ) : (
              <div className="ait-table-wrap">
                <table className="ait-tbl">
                  <thead>
                    <tr>
                      <th>Email</th>
                      <th>Company</th>
                      <th>Campaign</th>
                      <th>Status</th>
                      <th>Opened</th>
                      <th>Clicks</th>
                      <th>Sent</th>
                      <th>Error</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {(tracking?.activity || []).map((r) => (
                      <tr key={r.id} style={{ cursor: 'pointer' }} onClick={() => openSentEmail(r)}>
                        <td>
                          <strong>{r.full_name || r.email}</strong>
                          <div style={{ fontSize: 11, color: 'var(--ait-text3)' }}>{r.email}</div>
                        </td>
                        <td>{r.company_name || '—'}</td>
                        <td style={{ fontSize: 12 }}>{r.campaign_name || '—'}</td>
                        <td>
                          <span className={`ait-badge ${statusBadge(r.status)}`}>{r.status}</span>
                          {r.replied_at || r.last_inbound_body ? <span className="ait-badge b-opened" style={{ marginLeft: 4 }}>inbox</span> : null}
                          {r.unsubscribed_at ? <span className="ait-badge b-rejected" style={{ marginLeft: 4 }}>unsub</span> : null}
                        </td>
                        <td style={{ fontSize: 12, color: 'var(--ait-text3)' }}>
                          {r.opened_at ? <span className="ait-badge b-opened" title={r.opened_at}>yes</span> : '—'}
                        </td>
                        <td style={{ fontSize: 12 }}>
                          {(r.click_count || 0) > 0 ? (
                            <span className="ait-badge b-opened" title={r.clicked_at || ''}>{r.click_count}</span>
                          ) : '—'}
                        </td>
                        <td style={{ fontSize: 12, color: 'var(--ait-text3)' }}>{timeAgo(r.sent_at)}</td>
                        <td className="ait-ellipsis" title={r.last_error || ''}>{r.last_error || '—'}</td>
                        <td onClick={(e) => e.stopPropagation()}>
                          <div className="ait-btn-row" style={{ margin: 0, gap: 4 }}>
                            <button type="button" className="ait-icon-btn" title="Open sent email" onClick={() => openSentEmail(r)}>
                              <i className="ti ti-mail" />
                            </button>
                            {(r.status === 'sent' || r.replied_at || r.last_inbound_body || r.status === 'unsubscribed') && (
                              <button type="button" className="ait-icon-btn" title="Reply" onClick={() => openReply(r)}>
                                <i className="ti ti-mail-opened" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                    {!(tracking?.activity || []).length && (
                      <tr><td colSpan={9} style={{ textAlign: 'center', color: 'var(--ait-text3)', padding: 20 }}>No activity</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              )}
            </div>
          </div>
        )}

        {tab === 'templates' && (
          <div>
            {!tplDraft ? (
              <div className="ait-card ait-sec ait-sec-templates">
                <div className="ait-card-hdr">
                  <div className="ait-sec-title-wrap">
                    <span className="ait-sec-step"><i className="ti ti-template" /></span>
                    <div>
                      <span className="ait-card-title">Email templates</span>
                      <span className="ait-sec-sub">Library · create &amp; edit</span>
                    </div>
                  </div>
                  <button type="button" className="ait-btn sm primary" disabled={!!busy} onClick={createTemplate}>
                    <i className="ti ti-plus" style={{ marginRight: 6 }} />Create new template
                  </button>
                </div>
                <div className="ait-table-wrap">
                  <table className="ait-tbl">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Subject</th>
                        <th>Updated</th>
                        <th style={{ width: 120 }}>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {templates.map((t) => (
                        <tr key={t.id}>
                          <td><strong>{t.name}</strong></td>
                          <td className="ait-ellipsis" title={t.subject || ''}>{t.subject || '—'}</td>
                          <td style={{ fontSize: 12, color: 'var(--ait-text3)' }}>{timeAgo(t.updated_at)}</td>
                          <td>
                            <div className="ait-btn-row" style={{ margin: 0, gap: 4 }}>
                              <button type="button" className="ait-icon-btn" title="Edit" onClick={() => setActiveTplId(t.id)}>
                                <i className="ti ti-edit" />
                              </button>
                              <button type="button" className="ait-icon-btn danger" title="Delete" disabled={!!busy} onClick={() => deleteTemplate(t.id)}>
                                <i className="ti ti-trash" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                      {!templates.length && (
                        <tr>
                          <td colSpan={4} style={{ textAlign: 'center', color: 'var(--ait-text3)', padding: 28 }}>
                            No templates yet — create one and paste your full HTML
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="ait-card ait-sec ait-sec-tpl-edit" style={{ marginBottom: 0 }}>
                <div className="ait-card-hdr">
                  <div className="ait-btn-row" style={{ margin: 0 }}>
                    <button type="button" className="ait-btn ghost sm" onClick={() => { setActiveTplId(null); setTplDraft(null) }}>
                      <i className="ti ti-arrow-left" style={{ marginRight: 4 }} />Templates
                    </button>
                    <div className="ait-sec-title-wrap">
                      <span className="ait-sec-step"><i className="ti ti-code" /></span>
                      <div>
                        <span className="ait-card-title">{tplDraft.name || 'Edit template'}</span>
                        <span className="ait-sec-sub">HTML left · live preview right</span>
                      </div>
                    </div>
                  </div>
                  <div className="ait-btn-row" style={{ margin: 0 }}>
                    <button type="button" className="ait-btn primary sm" disabled={!!busy} onClick={saveTemplate}>Save</button>
                    <button type="button" className="ait-btn danger sm" disabled={!!busy || !tplDraft.id} onClick={() => deleteTemplate(tplDraft.id)}>Delete</button>
                  </div>
                </div>
                <div className="ait-card-body" style={{ paddingBottom: 10 }}>
                  <div className="ait-fg-2">
                    <div className="ait-field"><label>Name</label>
                      <input value={tplDraft.name || ''} onChange={(e) => setTplDraft({ ...tplDraft, name: e.target.value })} />
                    </div>
                    <div className="ait-field"><label>Subject</label>
                      <input value={tplDraft.subject || ''} onChange={(e) => setTplDraft({ ...tplDraft, subject: e.target.value })} />
                    </div>
                  </div>
                  <div className="ait-chip-row" style={{ marginBottom: 8 }}>
                    {mergeTags.filter((t) => t !== 'body').map((t) => (
                      <button
                        key={t}
                        type="button"
                        className="ait-chip"
                        title={`Insert {{${t}}} into HTML`}
                        onClick={() => insertAtEnd(tplDraft.html_template, (v) => setTplDraft({ ...tplDraft, html_template: v }), t)}
                      >{`{{${t}}}`}</button>
                    ))}
                    <button
                      type="button"
                      className="ait-chip"
                      onClick={() => insertAtEnd(tplDraft.html_template, (v) => setTplDraft({ ...tplDraft, html_template: v }), 'body')}
                    >{`{{body}}`}</button>
                  </div>
                  <details className="ait-tpl-body-details">
                    <summary>Optional body text (only if HTML contains {'{{body}}'})</summary>
                    <textarea
                      style={{ minHeight: 90, marginTop: 8 }}
                      value={tplDraft.body_text || ''}
                      onChange={(e) => setTplDraft({ ...tplDraft, body_text: e.target.value })}
                    />
                  </details>
                </div>
                <div className="ait-tpl-split">
                  <div className="ait-tpl-pane">
                    <div className="ait-tpl-pane-hdr">
                      <span>HTML (CSS inlined on save &amp; send for email clients)</span>
                    </div>
                    <textarea
                      className="ait-code-editor ait-tpl-code"
                      value={tplDraft.html_template || ''}
                      onChange={(e) => setTplDraft({ ...tplDraft, html_template: e.target.value })}
                      spellCheck={false}
                    />
                  </div>
                  <div className="ait-tpl-pane">
                    <div className="ait-tpl-pane-hdr">
                      <span>Live preview</span>
                      <div className="ait-device-seg" role="group" aria-label="Preview width">
                        {PREVIEW_DEVICES.map((d) => (
                          <button
                            key={d.id}
                            type="button"
                            className={tplPreviewDevice === d.id ? 'active' : ''}
                            title={d.label}
                            onClick={() => setTplPreviewDevice(d.id)}
                          >
                            <i className={`ti ${d.icon}`} />
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="ait-tpl-preview-frame">
                      <iframe
                        className="ait-html-preview ait-tpl-preview-iframe"
                        title="Template preview"
                        sandbox=""
                        srcDoc={tplLiveHtml || '<p style="padding:16px;color:#888;font-family:sans-serif;">Paste HTML to preview</p>'}
                        style={{
                          width: '100%',
                          maxWidth: PREVIEW_DEVICES.find((d) => d.id === tplPreviewDevice)?.width || 640,
                        }}
                      />
                    </div>
                  </div>
                </div>
                <p className="ait-hint" style={{ padding: '0 18px 14px' }}>
                  Links and styles in your HTML are sent exactly as written. Only {'{{merge}}'} tags are replaced.
                  Use <code>{'{{trial_url}}'}</code> for signup, <code>{'{{tracked_trial_url}}'}</code> for click tracking,
                  and <code>{'{{unsubscribe_url}}'}</code> in the footer for opt-out.
                  For Gmail white button text, put <code>color:#ffffff !important</code> on the <code>&lt;a&gt;</code> and a nested <code>&lt;span&gt;</code>.
                </p>
              </div>
            )}
          </div>
        )}

        {tab === 'scrape' && (
          <div className="ait-card ait-sec ait-sec-scrape">
            <div className="ait-card-hdr">
              <div className="ait-sec-title-wrap">
                <span className="ait-sec-step"><i className="ti ti-world" /></span>
                <div>
                  <span className="ait-card-title">Scrape exhibitor emails</span>
                  <span className="ait-sec-sub">Auto uses built-in for /exhibitors (SPA + HTML)</span>
                </div>
              </div>
              <button type="button" className="ait-btn sm" disabled={!!busy} onClick={() => loadApifyRuns()}>Refresh</button>
            </div>
            <div className="ait-card-body">
              <div className={`ait-msg-banner ${scrapePlan.engine === 'need-token' ? 'err' : 'ok'}`} style={{ margin: '0 0 12px' }}>
                <strong>Will use:</strong> {scrapePlan.label}
                <span className="ait-hint" style={{ display: 'block', marginTop: 6, marginBottom: 0 }}>
                  Built-in covers Easyfairs, SPA/Supabase, ASP Events (A–Z), Reed/WTM Algolia, and HTML + company websites. Keep “Also scrape company websites” on for ASP lists.
                </span>
              </div>
              <div className="ait-field">
                <label>Expo / directory URL</label>
                <div className="ait-input-with-action">
                  <input
                    value={apifyExpoUrl}
                    onChange={(e) => setApifyExpoUrl(e.target.value)}
                    placeholder="https://…/exhibitors/ (any show directory)"
                  />
                  {apifyExpoUrl.trim() ? (
                    <button
                      type="button"
                      className="ait-icon-btn danger"
                      title="Clear URL"
                      onClick={() => setApifyExpoUrl('')}
                    >
                      <i className="ti ti-trash" />
                    </button>
                  ) : null}
                </div>
              </div>
              <label className="ait-check" style={{ marginBottom: 12 }}>
                <input type="checkbox" checked={scrapeFollowWebsites} onChange={(e) => setScrapeFollowWebsites(e.target.checked)} />
                Also scrape company websites (built-in path)
              </label>
              <div className="ait-btn-row">
                <button type="button" className="ait-btn primary sm" disabled={!!busy || !apifyExpoUrl.trim()} onClick={startScrape}>
                  Scrape
                </button>
                <button type="button" className="ait-btn ghost sm" onClick={() => setBulkOpen((v) => !v)}>
                  {bulkOpen ? 'Hide bulk list' : 'Bulk / Book1 list'}
                </button>
                <button type="button" className="ait-btn ghost sm" onClick={() => setScrapeAdvancedOpen((v) => !v)}>
                  {scrapeAdvancedOpen ? 'Hide advanced' : 'Advanced'}
                </button>
              </div>
              {bulkOpen && (
                <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--ait-border)' }}>
                  <div className="ait-field">
                    <label>Directory URLs (one per line) — Book1 + found exhibitor lists</label>
                    <textarea
                      value={bulkUrls}
                      onChange={(e) => setBulkUrls(e.target.value)}
                      rows={8}
                      placeholder="https://…/exhibitors&#10;https://…/exhibitor-list"
                      style={{ width: '100%', fontFamily: 'ui-monospace, monospace', fontSize: 12 }}
                    />
                  </div>
                  <div className="ait-btn-row">
                    <button type="button" className="ait-btn sm" disabled={!!busy} onClick={fillBulkFromCurated}>
                      Fill curated ({exhibitionDirs.length || '…'})
                    </button>
                    <button
                      type="button"
                      className="ait-btn primary sm"
                      disabled={!!busy || !bulkUrls.trim()}
                      onClick={startBulkScrapes}
                    >
                      {busy === 'bulk-scrape' ? 'Scraping…' : 'Scrape all (max 15)'}
                    </button>
                  </div>
                  {exhibitionDirs.length > 0 && (
                    <p className="ait-hint" style={{ marginBottom: 0 }}>
                      Curated: {exhibitionDirs.map((e) => e.name).join(' · ')}
                    </p>
                  )}
                </div>
              )}
              {scrapeAdvancedOpen && (
                <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--ait-border)' }}>
                  <div className="ait-fg-2">
                    <div className="ait-field">
                      <label>Engine</label>
                      <select value={scrapeEngine} onChange={(e) => setScrapeEngine(e.target.value)}>
                        <option value="auto">Auto (built-in for /exhibitors, else Apify)</option>
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
                Auto / Built-in for /exhibitors uses the SPA API when available (e.g. takeawayexpo). Scrape may take 10–60s — wait for the banner, then click Add to campaign.
                Manual alternative: <button type="button" className="ait-btn ghost xs" onClick={() => setTab('campaigns')}>Campaigns → upload Excel</button>
              </p>
              {liveScrapeRun && (
                <div className="ait-send-progress" style={{ margin: '12px 0' }}>
                  <div className="ait-send-progress-top">
                    <div>
                      <div className="ait-send-progress-title">
                        Scrape · {liveStatusLabel}
                        {liveProgress?.phase ? ` · ${liveProgress.phase}` : ''}
                      </div>
                      <div className="ait-send-progress-sub">
                        {liveProgress?.message
                          || (liveStatusUp === 'READY'
                            ? 'Queued on Apify — waiting to start. Counters refresh every few seconds.'
                            : 'Working… leave this tab open to watch progress.')}
                      </div>
                    </div>
                    <div className="ait-btn-row" style={{ margin: 0, gap: 6 }}>
                      <span className="ait-badge b-opened">{livePct}%</span>
                      <button
                        type="button"
                        className="ait-btn danger xs"
                        disabled={!!busy || liveStatusUp === 'ABORTING'}
                        onClick={() => pauseScrape(liveScrapeRun.id)}
                      >
                        Force pause
                      </button>
                    </div>
                  </div>
                  <div className="ait-send-progress-bar">
                    <div className="ait-send-progress-fill" style={{ width: `${livePct || 5}%` }} />
                  </div>
                  <div className="ait-send-progress-stats">
                    <span><strong>{liveStandsDone}</strong> / {liveStandsTotal || '—'} stands</span>
                    <span><strong>{liveEmails}</strong> emails</span>
                    <span><strong>{Number(liveProgress?.stands_with_email || 0)}</strong> with email</span>
                    <span><strong>{Number(liveProgress?.errors || 0)}</strong> errors</span>
                    <span style={{ color: 'var(--ait-text3)' }}>
                      {liveProgress?.heartbeat_at ? `updated ${timeAgo(liveProgress.heartbeat_at)}` : ''}
                    </span>
                  </div>
                  {Number(liveProgress?.errors || 0) > 0 && (
                    <p className="ait-hint" style={{ marginTop: 8, marginBottom: 0, color: 'var(--ait-amber)' }}>
                      Some pages failed — scrape still continues. Check the run row when finished.
                    </p>
                  )}
                  {liveStatusUp === 'READY' && (
                    <p className="ait-hint" style={{ marginTop: 8, marginBottom: 0 }}>
                      <strong>READY</strong> means Apify accepted the job but has not started the actor yet — not stuck unless it stays READY with no heartbeat for 5+ minutes.
                    </p>
                  )}
                </div>
              )}
              {(apifyRuns[0] && ['FAILED', 'ABORTED', 'TIMED-OUT'].includes(String(apifyRuns[0].status || '').toUpperCase())) && (
                <div className="ait-msg-banner err" style={{ margin: '12px 0' }}>
                  Last scrape {apifyRuns[0].status}: {apifyRuns[0].error || apifyRuns[0].progress?.message || 'see Celery / Apify console'}
                </div>
              )}
              <div className="ait-table-wrap" style={{ marginTop: 12 }}>
                <table className="ait-tbl ait-tbl-compact">
                  <thead><tr><th>Status</th><th>Engine</th><th>URL</th><th>Emails</th><th>Progress</th><th /></tr></thead>
                  <tbody>
                    {apifyRuns.map((run) => {
                      const isBuiltin = String(run.actor_id || '').startsWith('builtin:') || run.provider === 'builtin' || run.engine === 'builtin'
                      const prog = run.progress || {}
                      const st = String(run.status || '').toUpperCase()
                      const active = st === 'RUNNING' || st === 'READY' || st === 'CREATED' || st === 'ABORTING'
                      return (
                        <tr key={run.id}>
                          <td>
                            <span className={`ait-badge ${
                              st === 'SUCCEEDED' ? 'b-sent'
                                : (st === 'FAILED' || st === 'ABORTED' || st === 'TIMED-OUT') ? 'b-rejected'
                                  : active ? 'b-opened' : 'b-pending'
                            }`}>{run.status}</span>
                          </td>
                          <td style={{ fontSize: 11 }}>{isBuiltin ? 'built-in' : (run.actor_id || 'apify')}</td>
                          <td className="ait-ellipsis" title={run.expo_url}>{run.expo_url}</td>
                          <td>
                            {run.emails_found ?? prog.emails_found ?? 0}
                            {run.emails_added != null && Number(run.emails_added) > 0 ? (
                              <div style={{ fontSize: 10, color: 'var(--ait-text3)' }}>+{run.emails_added} new</div>
                            ) : null}
                          </td>
                          <td style={{ fontSize: 11, color: 'var(--ait-text3)', maxWidth: 220 }}>
                            {prog.message || (active ? 'Waiting…' : '—')}
                            {active && (prog.stands_total || prog.stands_done) ? (
                              <div>{prog.stands_done || 0}/{prog.stands_total || '—'} stands</div>
                            ) : null}
                          </td>
                          <td>
                            <div className="ait-btn-row" style={{ margin: 0, gap: 4, flexWrap: 'wrap' }}>
                              {active ? (
                                <button type="button" className="ait-btn xs danger" disabled={!!busy} onClick={() => pauseScrape(run.id)}>
                                  Force pause
                                </button>
                              ) : null}
                              {!active ? (
                                <button
                                  type="button"
                                  className="ait-btn xs"
                                  disabled={!!busy}
                                  title="Re-scrape this URL; keep existing emails, add only new ones"
                                  onClick={() => updateScrapeRun(run)}
                                >
                                  Update
                                </button>
                              ) : null}
                              <button type="button" className="ait-btn xs" disabled={run.status !== 'SUCCEEDED'} onClick={() => exportApifyRun(run.id)}>Excel</button>
                              <button type="button" className="ait-btn xs primary" disabled={!!busy || run.status !== 'SUCCEEDED'} onClick={() => addScrapeToCampaign(run.id)}>Add to campaign</button>
                              {!active ? (
                                <button
                                  type="button"
                                  className="ait-icon-btn danger"
                                  title="Delete scrape run"
                                  disabled={!!busy}
                                  onClick={() => deleteScrapeRun(run)}
                                >
                                  <i className="ti ti-trash" />
                                </button>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                    {!apifyRuns.length && <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--ait-text3)', padding: 20 }}>No scrapes yet</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {tab === 'apify' && (
          <div className="ait-card ait-sec ait-sec-apify">
            <div className="ait-card-hdr">
              <div className="ait-sec-title-wrap">
                <span className="ait-sec-step"><i className="ti ti-key" /></span>
                <div>
                  <span className="ait-card-title">Apify API</span>
                  <span className="ait-sec-sub">Token &amp; actor settings</span>
                </div>
              </div>
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
          <div className="ait-card ait-sec ait-sec-sending">
            <div className="ait-card-hdr">
              <div className="ait-sec-title-wrap">
                <span className="ait-sec-step"><i className="ti ti-mail" /></span>
                <div>
                  <span className="ait-card-title">Sending</span>
                  <span className="ait-sec-sub">SMTP · IMAP · pace</span>
                </div>
              </div>
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
                <div className="ait-field">
                  <label>Max / day</label>
                  <input type="number" min={1} value={settings.max_emails_per_day || 50} onChange={(e) => setSettings({ ...settings, max_emails_per_day: +e.target.value })} />
                </div>
              </div>
              <div className="ait-fg-2">
                <div className="ait-field">
                  <label>Send 1 email every (seconds)</label>
                  <input
                    type="number"
                    min={1}
                    max={600}
                    value={settings.send_interval_seconds ?? 20}
                    onChange={(e) => setSettings({ ...settings, send_interval_seconds: Math.max(1, Math.min(600, +e.target.value || 1)) })}
                  />
                </div>
                <div className="ait-field">
                  <label>Approx. rate</label>
                  <input
                    disabled
                    value={`${Math.max(1, Math.round(60 / Math.max(1, Number(settings.send_interval_seconds) || 20)))} / minute`}
                  />
                </div>
              </div>
              <p className="ait-hint" style={{ marginTop: 0 }}>
                Example: <strong>4</strong> = one email every 4 seconds. Click <strong>Save</strong>, then Campaign → <strong>Send test</strong> before Send all.
                Opens/clicks are tracked automatically on sent mail (pixel + wrapped links). Some clients block images so opens can under-count.
              </p>
              <div className="ait-toggle-row" style={{ marginTop: 8 }}>
                <div>
                  <strong>Track opens</strong>
                  <div className="ait-hint" style={{ margin: 0 }}>Invisible pixel in each email</div>
                </div>
                <label className="ait-check">
                  <input
                    type="checkbox"
                    checked={settings.track_opens !== false}
                    onChange={(e) => setSettings({ ...settings, track_opens: e.target.checked })}
                  />
                  On
                </label>
              </div>

              <hr style={{ border: 0, borderTop: '1px solid var(--ait-border)', margin: '18px 0 14px' }} />
              <div className="ait-conn-block ait-conn-compact">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className={`ait-dot ${imapTestResult?.ok || settings.imap_configured ? 'on' : 'off'}`} />
                  <strong>{imapTestResult ? (imapTestResult.ok ? 'IMAP OK' : 'Failed') : (settings.imap_configured ? 'IMAP ready' : 'IMAP not set')}</strong>
                </div>
                <button type="button" className="ait-btn xs" disabled={!!busy} onClick={runTestImap}>Test IMAP</button>
              </div>
              <p className="ait-hint" style={{ marginTop: 0 }}>
                Inbound replies for Tracking → Received. <strong>SMTP is send-only</strong> — replies need IMAP
                (often the same host as SMTP, port 993 SSL). Leave host blank to reuse SMTP host; leave IMAP password
                blank to reuse SMTP password. Then click <strong>Test IMAP</strong> before Refresh inbox.
              </p>
              <div className="ait-fg-3">
                <div className="ait-field"><label>IMAP host</label><input value={settings.imap_host || ''} placeholder={settings.smtp_host || 'mail.example.com'} onChange={(e) => setSettings({ ...settings, imap_host: e.target.value })} /></div>
                <div className="ait-field"><label>Port</label><input type="number" value={settings.imap_port || 993} onChange={(e) => setSettings({ ...settings, imap_port: +e.target.value })} /></div>
                <div className="ait-field"><label>Username</label><input value={settings.imap_username || ''} placeholder={settings.smtp_username || ''} onChange={(e) => setSettings({ ...settings, imap_username: e.target.value })} /></div>
              </div>
              <div className="ait-fg-3">
                <div className="ait-field"><label>IMAP password</label><input type="password" value={imapPassword} onChange={(e) => setImapPassword(e.target.value)} placeholder={settings.imap_password_configured || settings.smtp_password_configured ? '••••••••' : ''} /></div>
                <div className="ait-field"><label>SSL</label>
                  <select value={settings.imap_use_ssl ? '1' : '0'} onChange={(e) => setSettings({ ...settings, imap_use_ssl: e.target.value === '1' })}>
                    <option value="1">SSL (993)</option>
                    <option value="0">No SSL</option>
                  </select>
                </div>
                <div className="ait-field"><label>STARTTLS</label>
                  <select value={settings.imap_use_tls ? '1' : '0'} onChange={(e) => setSettings({ ...settings, imap_use_tls: e.target.value === '1' })}>
                    <option value="0">Off</option>
                    <option value="1">On</option>
                  </select>
                </div>
              </div>
              {settings.imap_last_sync_message && (
                <p className="ait-hint">Last sync: {settings.imap_last_sync_message}</p>
              )}
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

      {contactsModal && (
        <div className="ait-modal-backdrop" onClick={() => setContactsModal(null)}>
          <div className="ait-modal ait-contacts-modal" onClick={(e) => e.stopPropagation()}>
            <div className="ait-modal-hdr">
              <div>
                <h3>{contactsModal.title}</h3>
                <div className="ait-contacts-modal-sub">{contactsModal.rows.length} row{contactsModal.rows.length === 1 ? '' : 's'}</div>
              </div>
              <button type="button" className="ait-btn ghost sm" onClick={() => setContactsModal(null)}>Close</button>
            </div>
            <div className="ait-contacts-modal-body">
              <table className="ait-tbl ait-tbl-contacts">
                <thead>
                  <tr>
                    <th style={{ width: 44 }}>#</th>
                    <th>Contact</th>
                    <th>Company</th>
                    <th>Job title</th>
                    <th>Event</th>
                    {contactsModal.rows.some((r) => r.status) ? <th>Status</th> : null}
                    <th style={{ width: 72 }} />
                  </tr>
                </thead>
                <tbody>
                  {contactsModal.rows.map((r, i) => (
                    <tr key={r.id || r.email || i}>
                      <td className="ait-muted-num">{i + 1}</td>
                      <td>
                        <div className="ait-contact-name">{contactDisplayName(r)}</div>
                        <div className="ait-contact-email">{r.email || '—'}</div>
                      </td>
                      <td>{r.company_name || '—'}</td>
                      <td>{r.job_title || '—'}</td>
                      <td>{r.event_name || '—'}</td>
                      {contactsModal.rows.some((x) => x.status) ? (
                        <td><span className={`ait-badge ${statusBadge(r.status)}`}>{r.status || '—'}</span></td>
                      ) : null}
                      <td>
                        <button
                          type="button"
                          className="ait-btn xs danger"
                          disabled={!!busy}
                          title="Remove from list"
                          onClick={() => deleteContactFromPreview(r, i)}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
              <li><strong>Top KPIs</strong> — Sent / Opened / Clicked / Received / Inbox. Click any tile to open that email list in Tracking.</li>
              <li><strong>Workflow</strong> — Scrape contacts → Templates → Campaigns (Edit → send) → Tracking. Sending + Apify API are setup tabs.</li>
              <li><strong>Sending</strong> — save From + SMTP to send, and IMAP to receive replies (SMTP alone cannot inbox).</li>
              <li><strong>Templates</strong> — paste HTML; on Save we inline CSS for Gmail/Outlook. Use {'{{trial_url}}'}, {'{{event-name}}'}, {'{{unsubscribe_url}}'}.</li>
              <li><strong>Scrape</strong> — Auto picks the best engine: Easyfairs API, SPA+Supabase directories, HTML exhibitor crawl, or Apify actors. Not every website has public emails.</li>
              <li><strong>Tracking</strong> — filter by status or campaign. <strong>Unsub list</strong> = DB suppressions.</li>
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
