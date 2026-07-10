import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Building2,
  ClipboardList,
  Megaphone,
  MessageSquareHeart,
  RefreshCw,
  ShoppingBag,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'
import WaIndustryBrowser from '../components/wa-templates/WaIndustryBrowser'
import WaTemplatesTable from '../components/wa-templates/WaTemplatesTable'
import WaEditSheet from '../components/wa-templates/WaEditSheet'
import WaRejectedDialog from '../components/wa-templates/WaRejectedDialog'
import WaJobProgressDialog from '../components/wa-templates/WaJobProgressDialog'
import WaSyncProfileSelect from '../components/wa-templates/WaSyncProfileSelect'
import WaSyncConfirmDialog from '../components/wa-templates/WaSyncConfirmDialog'
import WaSyncProfileMatrix from '../components/wa-templates/WaSyncProfileMatrix'
import { toHubRow } from '../components/wa-templates/waTemplatesUi'
import {
  EMPTY_PROFILE_SUMMARY_ROW,
  fetchProfileTemplateSummary,
  fetchWaSyncProfileOptions,
  getStoredSyncProfileId,
  resolveSelectedSyncProfile,
  resolvePrimarySyncProfile,
  resolveBackupSyncProfile,
  resolveDualSyncProfileIds,
  setStoredSyncProfileId,
  syncProfilePayload,
  syncProfileActionLabel,
} from '../lib/waSyncProfile'
import {
  buildIndustrySyncJobProgress,
  createHubPushAccumulator,
  flattenHubPushBatch,
  mergePushBatchIntoAcc,
  outcomeLabel,
} from '../lib/waIndustrySync'
import '../styles/wa-templates-hub.css'

const EMPTY_JOB = {
  open: false,
  title: '',
  dryRun: false,
  steps: [],
  phase: 'running',
  summaryRows: [],
  tables: {},
  message: '',
  error: '',
  reportPath: '',
}

const TAGS = [
  { id: 'ai', label: 'AI Interview', icon: Sparkles },
  { id: 'survey', label: 'Survey', icon: ClipboardList },
  { id: 'feedback', label: 'Customer Feedback', icon: MessageSquareHeart },
  { id: 'companies', label: 'Companies', icon: Building2 },
  { id: 'marketing', label: 'Marketing', icon: Megaphone },
  { id: 'sales', label: 'Sales', icon: ShoppingBag },
]

const SALES_TEMPLATE_KEYS = new Set([
  'sales_opt_in',
  'sales_offer',
  'sales_offer_followup',
  'sales_offer_keyword_confirm',
])

/** Lead-sales / marketing only — never interview keys. */
const MARKETING_TEMPLATE_KEYS = new Set([
  'sales_opt_in',
  'sales_offer',
  'sales_offer_followup',
  'sales_offer_keyword_confirm',
])

const INTERVIEW_TEMPLATE_KEYS = new Set([
  'interview_email_sent',
  'interview_booking_confirm',
  'interview_booking_cancel',
  'interview_job_closed',
  'interview_booking_invite',
])

function templateKey(t) {
  return String(t?.sales_template_key || t?.sales_key || '').toLowerCase().trim()
}

function templateName(t) {
  return String(t?.name || t?.telnyx_name || t?.display_name || '').toLowerCase().trim()
}

function isInterviewTemplate(t) {
  const key = templateKey(t)
  const name = templateName(t)
  if (INTERVIEW_TEMPLATE_KEYS.has(key)) return true
  if (key.startsWith('interview_')) return true
  if (name.startsWith('voxbulk_interview_')) return true
  if (name.includes('interview_') || name.includes('_interview')) return true
  return false
}

function isSalesTemplate(t) {
  if (isInterviewTemplate(t)) return false
  const key = templateKey(t)
  const name = templateName(t)
  if (SALES_TEMPLATE_KEYS.has(key)) return true
  if (key.startsWith('sales_')) return true
  if (name.startsWith('voxbulk_sales_')) return true
  return false
}

function isMarketingTemplate(t) {
  if (isInterviewTemplate(t)) return false
  if (isSalesTemplate(t)) return false
  const key = templateKey(t)
  const name = templateName(t)
  if (MARKETING_TEMPLATE_KEYS.has(key)) return true
  return false
}

const TAB_ALIASES = { interview: 'ai', appointment: 'ai' }

function syncServiceCodeForTab(tabId) {
  return tabId === 'feedback' ? 'customer_feedback' : 'survey'
}

export default function WaTemplatesHub() {
  const [searchParams, setSearchParams] = useSearchParams()
  const rawTab = searchParams.get('tab') || 'survey'
  const tab = TAB_ALIASES[rawTab] || (TAGS.some((t) => t.id === rawTab) ? rawTab : 'survey')
  const syncServiceCode = syncServiceCodeForTab(tab)
  const hubScopeLabel = tab === 'feedback' ? 'customer feedback templates' : 'survey templates'

  const [syncing, setSyncing] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [syncProgress, setSyncProgress] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [interviewTemplates, setInterviewTemplates] = useState([])
  const [marketingTemplates, setMarketingTemplates] = useState([])
  const [salesTemplates, setSalesTemplates] = useState([])
  const [flatLoading, setFlatLoading] = useState(false)
  const [cleaning, setCleaning] = useState(false)
  const [job, setJob] = useState(EMPTY_JOB)
  const hubJobAbortRef = useRef(null)

  const stopHubJob = () => {
    hubJobAbortRef.current?.abort()
  }

  const beginHubJobAbort = () => {
    hubJobAbortRef.current?.abort()
    const controller = new AbortController()
    hubJobAbortRef.current = controller
    return controller
  }

  const [surveyIndustries, setSurveyIndustries] = useState([])
  const [surveyIndustriesLoading, setSurveyIndustriesLoading] = useState(true)
  const [surveyIndustriesError, setSurveyIndustriesError] = useState('')
  const [feedbackIndustries, setFeedbackIndustries] = useState([])
  const [feedbackIndustriesLoading, setFeedbackIndustriesLoading] = useState(false)
  const [feedbackIndustriesError, setFeedbackIndustriesError] = useState('')

  const [editTarget, setEditTarget] = useState(null)
  const [syncingId, setSyncingId] = useState(null)
  const [rejectRow, setRejectRow] = useState(null)
  const [syncProfileItems, setSyncProfileItems] = useState([])
  const [syncProfileId, setSyncProfileIdState] = useState(() => getStoredSyncProfileId())
  const [syncProfilesLoading, setSyncProfilesLoading] = useState(true)
  const [syncConfirm, setSyncConfirm] = useState(null)
  const [profileSummaries, setProfileSummaries] = useState({})
  const [refreshingAllProfiles, setRefreshingAllProfiles] = useState(false)
  const profileSummariesRef = useRef({})
  const profileLoadInFlightRef = useRef(new Set())
  const staggerTimersRef = useRef([])
  const syncServiceCodeRef = useRef(syncServiceCode)

  useEffect(() => {
    syncServiceCodeRef.current = syncServiceCode
  }, [syncServiceCode])

  const syncProfile = useMemo(
    () => resolveSelectedSyncProfile(syncProfileItems, syncProfileId, null),
    [syncProfileItems, syncProfileId],
  )
  const primarySyncProfile = useMemo(
    () => resolvePrimarySyncProfile(syncProfileItems),
    [syncProfileItems],
  )
  const backupSyncProfile = useMemo(
    () => resolveBackupSyncProfile(syncProfileItems, primarySyncProfile),
    [syncProfileItems, primarySyncProfile],
  )

  const setSyncProfileId = useCallback((id) => {
    setSyncProfileIdState(id)
    setStoredSyncProfileId(id)
  }, [])

  const syncBodyExtra = useCallback(
    () => ({ ...syncProfilePayload(syncProfile), service_code: syncServiceCode }),
    [syncProfile, syncServiceCode],
  )

  const requestSyncConfirm = useCallback(
    ({ title, action, detail, profile: confirmProfile = null }) =>
      new Promise((resolve, reject) => {
        const profile = confirmProfile || syncProfile
        if (!profile?.id) {
          reject(new Error('Select a WhatsApp connection profile first'))
          return
        }
        setSyncConfirm({
          title,
          action,
          detail,
          profile,
          onConfirm: () => {
            setSyncConfirm(null)
            resolve(true)
          },
          onCancel: () => {
            setSyncConfirm(null)
            reject(new Error('cancelled'))
          },
        })
      }),
    [syncProfile],
  )

  const patchProfileSummary = useCallback((profileId, patch) => {
    const id = String(profileId || '').trim()
    if (!id) return
    setProfileSummaries((prev) => ({
      ...prev,
      [id]: { ...EMPTY_PROFILE_SUMMARY_ROW, ...prev[id], ...patch },
    }))
  }, [])

  const loadProfileSummary = useCallback(async (profileId, { force = false } = {}) => {
    const id = String(profileId || '').trim()
    if (!id) return
    const requestServiceCode = syncServiceCodeRef.current
    const inFlightKey = `${id}:${requestServiceCode}`
    if (profileLoadInFlightRef.current.has(inFlightKey)) return
    if (!force) {
      const cur = profileSummariesRef.current[id]
      if (cur?.summary && cur?.fetchedAt && cur?.serviceCode === requestServiceCode) return
    }
    profileLoadInFlightRef.current.add(inFlightKey)
    patchProfileSummary(id, {
      loading: true,
      error: null,
      summary: null,
      serviceCode: requestServiceCode,
    })
    try {
      const data = await fetchProfileTemplateSummary(apiFetch, id, { serviceCode: requestServiceCode })
      if (syncServiceCodeRef.current !== requestServiceCode) return
      patchProfileSummary(id, {
        loading: false,
        error: null,
        summary: data?.summary || null,
        fetchedAt: Date.now(),
        serviceCode: requestServiceCode,
      })
    } catch (e) {
      if (syncServiceCodeRef.current !== requestServiceCode) return
      patchProfileSummary(id, {
        loading: false,
        error: formatWaSurveyError(e, 'Could not load profile stats').message || e?.message || 'Load failed',
        summary: null,
        serviceCode: requestServiceCode,
      })
    } finally {
      profileLoadInFlightRef.current.delete(inFlightKey)
    }
  }, [patchProfileSummary])

  const refreshSelectedProfileSummary = useCallback(() => {
    if (syncProfile?.id) void loadProfileSummary(syncProfile.id, { force: true })
  }, [syncProfile?.id, loadProfileSummary])

  const queueBackgroundProfileLoads = useCallback(
    (profiles, selectedId) => {
      staggerTimersRef.current.forEach(clearTimeout)
      staggerTimersRef.current = []
      const others = (Array.isArray(profiles) ? profiles : [])
        .filter((p) => String(p.id) !== String(selectedId))
        .map((p) => p.id)
      let delay = 2000
      for (const pid of others) {
        const timer = setTimeout(() => {
          void loadProfileSummary(pid)
        }, delay)
        staggerTimersRef.current.push(timer)
        delay += 2000
      }
    },
    [loadProfileSummary],
  )

  const refreshAllProfileSummaries = useCallback(async () => {
    if (!syncProfileItems.length) return
    setRefreshingAllProfiles(true)
    try {
      for (const profile of syncProfileItems) {
        await loadProfileSummary(profile.id, { force: true })
      }
    } finally {
      setRefreshingAllProfiles(false)
    }
  }, [syncProfileItems, loadProfileSummary])

  useEffect(() => {
    profileSummariesRef.current = profileSummaries
  }, [profileSummaries])

  const setTab = (next) => {
    const params = new URLSearchParams(searchParams)
    params.set('tab', next)
    setSearchParams(params, { replace: true })
  }

  const loadInterview = useCallback(async () => {
    setFlatLoading(true)
    try {
      const data = await apiFetch('/admin/wa-interview/templates')
      const rows = (Array.isArray(data?.templates) ? data.templates : []).filter(isInterviewTemplate)
      setInterviewTemplates(rows.map((t) => toHubRow(t, { rowKind: 'interview' })))
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load interview templates').message)
    } finally {
      setFlatLoading(false)
    }
  }, [])

  const loadMarketing = useCallback(async () => {
    setFlatLoading(true)
    try {
      const stored = await apiFetch('/admin/integrations/telnyx/whatsapp-templates?approved_only=false')
      const rows = (Array.isArray(stored?.templates) ? stored.templates : []).filter(isMarketingTemplate)
      setMarketingTemplates(rows.map((t) => toHubRow(t, { rowKind: 'marketing' })))
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load marketing templates').message)
    } finally {
      setFlatLoading(false)
    }
  }, [])

  const loadSales = useCallback(async () => {
    setFlatLoading(true)
    try {
      await apiFetch('/admin/wa-templates/ensure-sales', { method: 'POST', quietNetworkHint: true })
      const stored = await apiFetch('/admin/integrations/telnyx/whatsapp-templates?approved_only=false')
      const rows = (Array.isArray(stored?.templates) ? stored.templates : []).filter(isSalesTemplate)
      setSalesTemplates(rows.map((t) => toHubRow(t, { rowKind: 'sales' })))
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load sales templates').message)
    } finally {
      setFlatLoading(false)
    }
  }, [])

  const loadSurveyIndustries = useCallback(async () => {
    setSurveyIndustriesLoading(true)
    setSurveyIndustriesError('')
    let listed = false
    try {
      const fast = await apiFetch('/admin/wa-survey/overview?fast=1', { quietNetworkHint: true })
      const rows = Array.isArray(fast?.industries) ? fast.industries : []
      setSurveyIndustries(rows)
      listed = rows.length > 0
    } catch (e) {
      try {
        const fallback = await apiFetch(
          '/admin/wa-survey/industries?include_hidden=true&include_inactive=true',
          { quietNetworkHint: true },
        )
        const rows = Array.isArray(fallback?.industries) ? fallback.industries : []
        setSurveyIndustries(rows)
        listed = rows.length > 0
        if (!rows.length) {
          setSurveyIndustriesError(formatWaSurveyError(e, 'Could not load survey industries').message)
        }
      } catch (fallbackErr) {
        setSurveyIndustries([])
        setSurveyIndustriesError(
          formatWaSurveyError(fallbackErr, 'Could not load survey industries').message,
        )
      }
    } finally {
      setSurveyIndustriesLoading(false)
    }

    if (!listed) return
    try {
      const full = await apiFetch('/admin/wa-survey/overview', { quietNetworkHint: true })
      if (Array.isArray(full?.industries) && full.industries.length) {
        setSurveyIndustries(full.industries)
      }
    } catch {
      // Keep fast list when full template-count enrichment fails.
    }
  }, [])

  const loadFeedbackIndustries = useCallback(async () => {
    setFeedbackIndustriesLoading(true)
    setFeedbackIndustriesError('')
    try {
      const data = await apiFetch('/admin/customer-feedback/industries', { quietNetworkHint: true })
      setFeedbackIndustries(Array.isArray(data?.items) ? data.items : [])
    } catch (e) {
      setFeedbackIndustries([])
      setFeedbackIndustriesError(formatWaSurveyError(e, 'Could not load feedback industries').message)
    } finally {
      setFeedbackIndustriesLoading(false)
    }
  }, [])

  const refreshTabData = useCallback(() => {
    if (tab === 'ai') void loadInterview()
    else if (tab === 'marketing') void loadMarketing()
    else if (tab === 'sales') void loadSales()
    else if (tab === 'survey') void loadSurveyIndustries()
    else if (tab === 'feedback') void loadFeedbackIndustries()
  }, [tab, loadInterview, loadMarketing, loadSales, loadSurveyIndustries, loadFeedbackIndustries])

  useEffect(() => {
    profileSummariesRef.current = {}
    profileLoadInFlightRef.current.clear()
    staggerTimersRef.current.forEach(clearTimeout)
    staggerTimersRef.current = []
    setProfileSummaries({})
    let cancelled = false
    ;(async () => {
      setSyncProfilesLoading(true)
      try {
        const { items, defaultId } = await fetchWaSyncProfileOptions(apiFetch, {
          serviceCode: syncServiceCode,
        })
        if (cancelled) return
        setSyncProfileItems(items)
        const resolved = resolveSelectedSyncProfile(items, getStoredSyncProfileId(), defaultId)
        if (resolved?.id) setSyncProfileIdState(resolved.id)
      } catch {
        if (!cancelled) setSyncProfileItems([])
      } finally {
        if (!cancelled) setSyncProfilesLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [syncServiceCode])

  useEffect(() => {
    if (!syncProfileItems.length) return
    const selected = syncProfile?.id
    if (selected) void loadProfileSummary(selected, { force: true })
    queueBackgroundProfileLoads(syncProfileItems, selected)
    return () => {
      staggerTimersRef.current.forEach(clearTimeout)
    }
  }, [syncProfileItems, queueBackgroundProfileLoads, loadProfileSummary, syncProfile?.id, syncServiceCode])

  useEffect(() => {
    setError('')
    refreshTabData()
  }, [refreshTabData])

  const patchJobStep = (stepId, patch) => {
    setJob((prev) => ({
      ...prev,
      steps: prev.steps.map((s) => (s.id === stepId ? { ...s, ...patch } : s)),
    }))
  }

  const pullFromMeta = async () => {
    try {
      await requestSyncConfirm({
        title: 'Refresh status from Meta',
        action: 'Pull',
        detail: 'Pull approval status and category from Meta (does not push local changes).',
      })
    } catch (e) {
      if (e?.message !== 'cancelled') setError(e?.message || 'Sync cancelled')
      return
    }
    setRefreshing(true)
    setError('')
    setMsg('')
    try {
      const pullPath =
        tab === 'feedback'
          ? '/admin/customer-feedback/templates/pull-status'
          : '/admin/integrations/meta_whatsapp/whatsapp-templates/sync-step/pull'
      const pullBody =
        tab === 'feedback'
          ? syncBodyExtra()
          : { status_only: true, ...syncBodyExtra() }
      const last = await apiFetch(pullPath, {
        method: 'POST',
        body: JSON.stringify(pullBody),
        timeoutMs: 300000,
        quietNetworkHint: true,
      })
      const updated = last?.status_pull?.updated
      const text =
        updated != null
          ? `Status refreshed from Meta (${updated} template(s) updated)`
          : formatActionSuccess(last, 'Status refreshed from Meta').message
      setMsg(text)
      refreshSelectedProfileSummary()
      refreshTabData()
    } catch (e) {
      const raw = e?.message || String(e)
      const aborted = e?.name === 'AbortError' || /aborted|abort/i.test(raw)
      setError(
        aborted
          ? 'Refresh timed out — wait 1–2 minutes and try again.'
          : formatWaSurveyError(e, 'Refresh from Meta failed').detailText || raw || 'Refresh from Meta failed',
      )
    } finally {
      setRefreshing(false)
    }
  }

  const runProfilePushBatch = async ({
    path,
    profile,
    title,
    detail,
    forcePush = true,
    extraBody = {},
    scopeLabel = 'templates',
  }) => {
    if (!profile?.id) {
      setError('Connection profile is not configured.')
      return
    }
    try {
      await requestSyncConfirm({ title, action: 'Push', detail, profile })
    } catch (e) {
      if (e?.message !== 'cancelled') setError(e?.message || 'Sync cancelled')
      return
    }
    const controller = beginHubJobAbort()
    setSyncing(true)
    setSyncProgress('')
    setError('')
    setMsg('')
    const acc = createHubPushAccumulator()
    setJob({
      ...EMPTY_JOB,
      open: true,
      title,
      phase: 'running',
      steps: [{ id: 'push', label: 'Push templates', status: 'running', detail: 'Starting…' }],
      tables: { sync_log: [], pushed: [], refreshed: [], push_failed: [] },
      progressPct: 0,
    })
    const PUSH_BATCH = 10
    let offset = 0
    let pushTotal = 0
    let last = null
    try {
      for (let batchNum = 1; ; batchNum += 1) {
        last = await apiFetch(path, {
          method: 'POST',
          body: JSON.stringify({
            offset,
            limit: PUSH_BATCH,
            force_push: forcePush,
            ...extraBody,
            connection_profile_id: profile.id,
          }),
          timeoutMs: 300000,
          quietNetworkHint: true,
          signal: controller.signal,
        })
        const flat = flattenHubPushBatch(last)
        mergePushBatchIntoAcc(acc, flat)
        pushTotal = acc.content_updated
        const progress = buildIndustrySyncJobProgress(acc, {
          running: Boolean(last?.has_more),
          industryName: scopeLabel,
        })
        const lastResult = acc.results[acc.results.length - 1]
        const lastName = lastResult?.template_name || lastResult?.label || ''
        setSyncProgress(acc.total ? `${acc.results.length}/${acc.total}` : '')
        setJob((prev) => ({
          ...prev,
          ...progress,
          phase: 'running',
          open: true,
          steps: prev.steps.map((s) =>
            s.id === 'push'
              ? {
                  ...s,
                  status: last?.has_more ? 'running' : 'done',
                  detail: lastName
                    ? `Last: ${lastName} — ${outcomeLabel(lastResult?.outcome)}`
                    : last?.message || `Batch ${batchNum}`,
                }
              : s,
          ),
        }))
        if (!last?.has_more) break
        offset = Number(last?.next_offset ?? offset + PUSH_BATCH)
      }
      const branchNote = last?.results?.[0]?.sync_branch ? ` (${last.results[0].sync_branch})` : ''
      const finalProgress = buildIndustrySyncJobProgress(acc, { running: false, industryName: hubScopeLabel })
      const finalMsg = formatActionSuccess(last || {}, last?.message || `Pushed ${pushTotal} template(s)${branchNote}`).message
      setMsg(finalMsg)
      setJob((prev) => ({
        ...prev,
        phase: 'done',
        message: finalMsg,
        progressPct: 100,
        summaryRows: finalProgress.summaryRows?.length
          ? finalProgress.summaryRows
          : [
              ...(pushTotal ? [{ metric: 'Templates pushed', count: pushTotal }] : []),
              ...(Number(last?.skipped) > 0 ? [{ metric: 'Skipped (already in sync)', count: last.skipped }] : []),
              ...(Number(last?.total) > 0 ? [{ metric: 'Total in batch scope', count: last.total }] : []),
            ],
        tables: finalProgress.tables,
      }))
      refreshSelectedProfileSummary()
      refreshAllProfileSummaries()
      refreshTabData()
    } catch (e) {
      if (controller.signal.aborted || /cancelled/i.test(e?.message || '')) {
        const partial = buildIndustrySyncJobProgress(acc, { running: false, industryName: hubScopeLabel })
        setJob((prev) => ({
          ...prev,
          ...partial,
          phase: 'cancelled',
          message: 'Stopped — push cancelled',
        }))
        return
      }
      const errText = formatWaSurveyError(e, 'Push failed').detailText || e?.message || 'Push failed'
      setError(errText)
      setJob((prev) => ({ ...prev, phase: 'error', error: errText }))
    } finally {
      if (hubJobAbortRef.current === controller) hubJobAbortRef.current = null
      setSyncing(false)
      setSyncProgress('')
    }
  }

  const pushToPrimary = () => {
    if (tab === 'feedback') {
      void runProfilePushBatch({
        path: '/admin/customer-feedback/templates/push-changed',
        profile: primarySyncProfile,
        title: 'Push changed customer feedback templates to primary',
        detail:
          'Pushes only customer feedback templates that need syncing (local edits, not yet on Meta, or out of sync). Skips templates already in sync on the selected profile.',
        forcePush: false,
        scopeLabel: hubScopeLabel,
      })
      return
    }
    void runProfilePushBatch({
      path: '/admin/integrations/meta_whatsapp/whatsapp-templates/sync-step/push',
      profile: primarySyncProfile,
      title: 'Push changed survey templates to primary',
      detail:
        'Pushes only survey templates that need syncing (local edits, not yet on Meta, or out of sync). Includes industry topics and system templates (Welcome, Thank you, etc.). Skips templates already in sync. Opens a progress window. Does not push Custom Org service-only templates.',
      forcePush: false,
      extraBody: { service_code: syncServiceCode },
      scopeLabel: hubScopeLabel,
    })
  }

  const mirrorToBackup = () => {
    if (tab !== 'survey' && tab !== 'feedback') return
    const isFeedback = tab === 'feedback'
    void runProfilePushBatch({
      path: isFeedback
        ? '/admin/customer-feedback/templates/mirror-backup'
        : '/admin/wa-survey/templates/mirror-backup',
      profile: backupSyncProfile,
      title: isFeedback
        ? 'Mirror all customer feedback templates to Telnyx backup'
        : 'Mirror all survey templates to Telnyx backup',
      detail: isFeedback
        ? 'Force-pushes every customer feedback industry template to the Telnyx backup profile — same names and bodies as the database. Opens a progress window.'
        : 'Force-pushes every survey industry topic and system template (Welcome, Thank you, Tell us more, Closing) to the Telnyx backup profile — same names and bodies as the database. Opens a progress window. Skips empty/local-only rows with no body.',
      forcePush: true,
      extraBody: isFeedback ? {} : { service_code: syncServiceCode },
      scopeLabel: hubScopeLabel,
    })
  }

  const syncFromMeta = async () => {
    try {
      await requestSyncConfirm({
        title: 'Sync with Meta',
        action: 'Sync',
        detail: 'Pull catalog and status from Meta, then push locally changed templates.',
      })
    } catch (e) {
      if (e?.message !== 'cancelled') setError(e?.message || 'Sync cancelled')
      return
    }
    const stepDefs = [
      { id: 'pull', label: '1. Refresh status from Meta (DB is source of truth)' },
      { id: 'push', label: '2. Push changed templates from DB' },
    ]
    const controller = beginHubJobAbort()
    setSyncing(true)
    setSyncProgress('')
    setError('')
    setMsg('')
    setJob({
      ...EMPTY_JOB,
      open: true,
      title: 'Sync with Meta',
      phase: 'running',
      steps: stepDefs.map((s) => ({ ...s, status: 'pending', detail: '' })),
      tables: { sync_log: [], pushed: [], refreshed: [], push_failed: [] },
      progressPct: 0,
    })
    const messages = []
    const summaryRows = []
    const acc = createHubPushAccumulator()
    const isFeedback = tab === 'feedback'
    const pullPath = isFeedback
      ? '/admin/customer-feedback/templates/pull-status'
      : '/admin/integrations/meta_whatsapp/whatsapp-templates/sync-step/pull'
    const pushPath = isFeedback
      ? '/admin/customer-feedback/templates/push-changed'
      : '/admin/integrations/meta_whatsapp/whatsapp-templates/sync-step/push'
    try {
      let last = null
      patchJobStep('pull', { status: 'running', detail: 'Refreshing approval status from Meta…' })
      last = await apiFetch(pullPath, {
        method: 'POST',
        body: JSON.stringify(
          isFeedback ? syncBodyExtra() : { status_only: true, ...syncBodyExtra() },
        ),
        timeoutMs: 300000,
        quietNetworkHint: true,
        signal: controller.signal,
      })
      messages.push(last?.message || 'Pull complete')
      patchJobStep('pull', { status: 'done', detail: last?.message || 'Done' })
      if (last?.status_pull?.updated != null) {
        summaryRows.push({ metric: 'Status refreshed', count: last.status_pull.updated })
      }

      const PUSH_BATCH = 10
      let offset = 0
      let pushTotal = 0
      patchJobStep('push', { status: 'running', detail: 'Pushing changed templates…' })
      for (let batchNum = 1; ; batchNum += 1) {
        last = await apiFetch(pushPath, {
          method: 'POST',
          body: JSON.stringify({
            offset,
            limit: PUSH_BATCH,
            force_push: false,
            ...(isFeedback ? {} : { force_utility_category: false }),
            ...syncBodyExtra(),
          }),
          timeoutMs: 300000,
          quietNetworkHint: true,
          signal: controller.signal,
        })
        const flat = flattenHubPushBatch(last)
        mergePushBatchIntoAcc(acc, flat)
        pushTotal = acc.content_updated
        const progress = buildIndustrySyncJobProgress(acc, {
          running: Boolean(last?.has_more),
          industryName: hubScopeLabel,
        })
        const lastResult = acc.results[acc.results.length - 1]
        const lastName = lastResult?.template_name || lastResult?.label || ''
        setSyncProgress(acc.total ? `${acc.results.length}/${acc.total}` : '')
        patchJobStep('push', {
          status: last?.has_more ? 'running' : 'done',
          detail: lastName
            ? `Last: ${lastName} — ${outcomeLabel(lastResult?.outcome)}`
            : last?.message || `Batch ${batchNum}`,
        })
        setJob((prev) => ({
          ...prev,
          ...progress,
          phase: 'running',
          open: true,
        }))
        if (!last?.has_more) break
        offset = Number(last?.next_offset ?? offset + PUSH_BATCH)
      }
      messages.push(last?.message || 'Push complete')
      if (pushTotal) summaryRows.push({ metric: 'Templates pushed', count: pushTotal })
      const finalProgress = buildIndustrySyncJobProgress(acc, { running: false, industryName: hubScopeLabel })

      const finalMsg = formatActionSuccess(last || {}, messages.join(' · ')).message
      setMsg(finalMsg)
      setJob((prev) => ({
        ...prev,
        phase: 'done',
        message: finalMsg,
        progressPct: 100,
        summaryRows: summaryRows.length ? summaryRows : finalProgress.summaryRows,
        tables: finalProgress.tables,
      }))
      refreshSelectedProfileSummary()
      refreshTabData()
    } catch (e) {
      if (controller.signal.aborted || /cancelled/i.test(e?.message || '')) {
        const partial = buildIndustrySyncJobProgress(acc, { running: false, industryName: hubScopeLabel })
        setJob((prev) => ({
          ...prev,
          ...partial,
          phase: 'cancelled',
          message: 'Stopped — sync cancelled',
          summaryRows,
        }))
        return
      }
      const raw = e?.message || String(e)
      const aborted = e?.name === 'AbortError' || /aborted|abort/i.test(raw)
      const errText = aborted
        ? 'Meta sync timed out in the browser. The server may still be finishing — wait 1–2 minutes, refresh this page, and check template statuses.'
        : formatWaSurveyError(e, 'Meta sync failed').detailText || raw || 'Meta sync failed'
      setError(errText)
      if (messages.length) setMsg(messages.join(' · '))
      setJob((prev) => ({
        ...prev,
        phase: 'error',
        error: errText,
        message: messages.join(' · '),
        summaryRows,
      }))
    } finally {
      if (hubJobAbortRef.current === controller) hubJobAbortRef.current = null
      setSyncing(false)
      setSyncProgress('')
    }
  }

  const openSurveyTypeEditor = async (row) => {
    setError('')
    try {
      if (row.rowKind === 'survey_template') {
        setEditTarget({
          product: 'survey',
          templateId: row.id,
          surveyTypeId: row.surveyTypeId,
        })
        return
      }
      if (row.rowKind === 'feedback_template') {
        setEditTarget({
          product: 'feedback',
          templateId: row.id,
          surveyTypeId: row.surveyTypeId,
        })
        return
      }
      // Empty survey types are no longer listed as fake template rows.
      setError('Select a real WhatsApp template row (not a survey type name).')
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not open editor').message)
    }
  }

  const pushSurveyType = async (row) => {
    const isFeedbackRow = row.rowKind === 'feedback_template' || row.rowKind === 'feedback_type'
    try {
      await requestSyncConfirm({
        title: `Sync ${row.name || 'template'}`,
        action: 'Push',
        detail: isFeedbackRow
          ? 'Push all language variants to Meta (primary), mirror to Telnyx backup, then refresh status.'
          : 'Push this template (or topic) to Meta.',
      })
    } catch (e) {
      if (e?.message !== 'cancelled') setError(e?.message || 'Sync cancelled')
      return
    }
    setError('')
    setSyncingId(row.id)
    const profileBody = syncBodyExtra()
    try {
      if (row.rowKind === 'survey_template') {
        const dual = resolveDualSyncProfileIds(syncProfileItems, {
          primaryProfile: primarySyncProfile,
          backupProfile: backupSyncProfile,
        })
        for (const profileId of dual.ids) {
          const result = await apiFetch(`/admin/wa-survey/templates/${row.id}/push`, {
            method: 'POST',
            body: JSON.stringify({
              force_push: true,
              connection_profile_id: profileId,
            }),
            timeoutMs: 180000,
            quietNetworkHint: true,
          })
          if (profileId === dual.ids[dual.ids.length - 1]) {
            setMsg(formatActionSuccess(result, 'Synced with Meta').message)
          }
        }
        refreshSelectedProfileSummary()
        return
      }
      if (isFeedbackRow) {
        const dual = resolveDualSyncProfileIds(syncProfileItems, {
          primaryProfile: primarySyncProfile,
          backupProfile: backupSyncProfile,
        })
        if (!dual.backup?.id) {
          throw new Error('Telnyx backup profile not found — add Telnyx 55 in Integrations before syncing Customer Feedback.')
        }
        const variantCount =
          (row.languageCount || 0) > 1
            ? row.languageCount
            : Array.isArray(row.raw?.variants)
              ? row.raw.variants.length
              : 1
        const pushAllLangs = Boolean(row.surveyTypeId && variantCount > 1)
        const typeId = row.surveyTypeId || row.id
        let lastResult = null

        for (const profileId of dual.ids) {
          const isBackup = dual.backup?.id && String(profileId) === String(dual.backup.id)
          if (pushAllLangs) {
            lastResult = await apiFetch(
              `/admin/customer-feedback/survey-types/${encodeURIComponent(typeId)}/sync-telnyx`,
              {
                method: 'POST',
                body: JSON.stringify({
                  service_code: syncServiceCode,
                  connection_profile_id: profileId,
                  force_push: Boolean(isBackup),
                }),
                timeoutMs: 300000,
                quietNetworkHint: true,
              },
            )
          } else {
            const variants =
              Array.isArray(row.raw?.variants) && row.raw.variants.length ? row.raw.variants : [{ id: row.id }]
            for (const variant of variants) {
              const templateId = variant?.id || row.id
              lastResult = await apiFetch(`/admin/customer-feedback/wa-templates/${templateId}/push`, {
                method: 'POST',
                body: JSON.stringify({
                  service_code: syncServiceCode,
                  connection_profile_id: profileId,
                  force_push: Boolean(isBackup),
                }),
                timeoutMs: 180000,
                quietNetworkHint: true,
              })
            }
          }
        }

        setMsg(
          formatActionSuccess(
            lastResult,
            pushAllLangs ? 'Synced all languages to Meta + Telnyx' : 'Pushed to Meta + Telnyx',
          ).message,
        )
        refreshTabData()
        refreshSelectedProfileSummary()
        return
      }
      // Sync only this survey type / topic (not the whole industry).
      const typeId = row.surveyTypeId || row.id
      const path =
        row.rowKind === 'feedback_type'
          ? `/admin/customer-feedback/survey-types/${typeId}/sync-telnyx`
          : `/admin/wa-survey/types/${typeId}/templates/push-all`
      const result = await apiFetch(path, {
        method: 'POST',
        body: JSON.stringify(profileBody),
        timeoutMs: 300000,
        quietNetworkHint: true,
      })
      setMsg(formatActionSuccess(result, 'Synced survey type with Meta').message)
      refreshSelectedProfileSummary()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Sync failed').detailText)
    } finally {
      setSyncingId(null)
    }
  }

  const toggleSurveyType = async (row) => {
    setError('')
    try {
      if (row.rowKind === 'survey_template') {
        const active = row.raw?.active_for_survey !== false
        await apiFetch(`/admin/wa-survey/templates/${row.id}/set-active`, {
          method: 'POST',
          body: JSON.stringify({ active_for_survey: !active }),
        })
        setMsg(active ? 'Template disabled for surveys' : 'Template enabled for surveys')
        return
      }
      if (row.rowKind === 'feedback_template') {
        const enable = row.hiddenFromSurvey
        const variants = Array.isArray(row.raw?.variants) ? row.raw.variants : [{ id: row.id }]
        await Promise.all(
          variants.map((v) =>
            apiFetch('/admin/customer-feedback/wa-templates', {
              method: 'POST',
              body: JSON.stringify({ id: v.id, is_active: enable }),
            }),
          ),
        )
        setMsg(enable ? 'Topic enabled for surveys' : 'Topic hidden from surveys')
        return
      }
      if (row.rowKind === 'feedback_type') {
        await apiFetch(`/admin/customer-feedback/survey-types/${row.id}`, {
          method: 'PUT',
          body: JSON.stringify({ is_active: row.raw?.is_active === false }),
        })
        void loadFeedbackIndustries()
        return
      }
      await apiFetch(`/admin/wa-survey/types/${row.id}`, {
        method: 'PUT',
        body: JSON.stringify({ is_active: row.raw?.is_active === false }),
      })
      void loadSurveyIndustries()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not update status').message)
      throw e
    }
  }

  const deleteSurveyType = async (row) => {
    if (!window.confirm(`Delete “${row.name}”? This removes it from the database and Meta.`)) return
    setError('')
    try {
      if (row.rowKind === 'survey_template' || row.rowKind === 'system_template') {
        const typeId = row.surveyTypeId
        if (row.rowKind === 'system_template') {
          await apiFetch(`/admin/wa-survey/system-templates/${row.id}`, { method: 'DELETE' })
        } else if (typeId) {
          await apiFetch(`/admin/wa-survey/types/${typeId}/templates/${row.id}`, { method: 'DELETE' })
        } else {
          await apiFetch(`/admin/wa-survey/templates/${row.id}`, { method: 'DELETE' })
        }
        setMsg('Template deleted from database and Meta')
        refreshSelectedProfileSummary()
        refreshTabData()
        return
      }
      if (row.rowKind === 'feedback_template') {
        await apiFetch(`/admin/customer-feedback/wa-templates/${row.id}`, { method: 'DELETE' })
        setMsg('Template deleted from database and Meta')
        refreshSelectedProfileSummary()
        refreshTabData()
        return
      }
      if (row.rowKind === 'feedback_type') {
        await apiFetch(`/admin/customer-feedback/survey-types/${row.id}`, { method: 'DELETE' })
        setMsg('Survey type deleted')
        refreshTabData()
        return
      }
      await apiFetch(`/admin/wa-survey/types/${row.id}`, { method: 'DELETE' })
      setMsg('Survey type deleted')
      refreshTabData()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Delete failed').message)
    }
  }

  const pushInterview = async (row) => {
    setError('')
    setSyncingId(row.id)
    try {
      const result = await apiFetch(`/admin/wa-interview/templates/${row.id}/push`, {
        method: 'POST',
        body: '{}',
        timeoutMs: 180000,
        quietNetworkHint: true,
      })
      setMsg(formatActionSuccess(result, 'Synced with Meta').message)
      await loadInterview()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Sync failed').detailText || e?.message)
    } finally {
      setSyncingId(null)
    }
  }

  const toggleInterview = async (row) => {
    try {
      const active = row.raw?.active_for_interview !== false
      await apiFetch(`/admin/wa-interview/templates/${row.id}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ active_for_interview: !active }),
      })
      await loadInterview()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not update status').message)
    }
  }

  const deleteInterview = async (row) => {
    if (!window.confirm(`Delete “${row.name}”?`)) return
    try {
      await apiFetch(`/admin/wa-interview/templates/${row.id}`, { method: 'DELETE' })
      setMsg('Template deleted')
      await loadInterview()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Delete failed').message)
    }
  }

  const marketingAction = async (row, action) => {
    if (action === 'edit') {
      setError('Marketing templates are managed in Lead sales settings.')
      return
    }
    if (action === 'sync') {
      await syncFromMeta()
      return
    }
    setError(`Cannot ${action} marketing templates from this list. Use Lead sales settings.`)
  }

  const salesAction = async (row, action) => {
    if (action === 'edit') {
      setEditTarget({ product: 'survey', templateId: row.id })
      return
    }
    if (action === 'sync') {
      setSyncingId(row.id)
      setError('')
      try {
        await apiFetch(`/admin/wa-survey/templates/${row.id}/push`, {
          method: 'POST',
          timeoutMs: 120000,
          quietNetworkHint: true,
        })
        setMsg(formatActionSuccess(null, 'Sales template submitted to Meta').message)
        await loadSales()
        refreshSelectedProfileSummary()
      } catch (e) {
        setError(formatWaSurveyError(e, 'Sales sync failed').detailText || e?.message)
      } finally {
        setSyncingId(null)
      }
      return
    }
    setError(`Cannot ${action} sales templates from this list yet. Review and sync when ready.`)
  }

  const runCleanupAndSync = async ({ dryRun = false } = {}) => {
    const label = dryRun ? 'Dry-run cleanup' : 'Cleanup + push buttoned'
    if (
      !dryRun &&
      !window.confirm(
        'Delete unused survey/feedback templates from local DB and Meta, then push buttoned keepers only? Interview and Sales are not touched. Local DB is source of truth.',
      )
    ) {
      return
    }
    const stepDefs = [
      { id: 'meta_cleanup', label: '1. Delete unused survey/CF from Meta' },
      { id: 'local_cleanup', label: '2. Delete unused survey/CF from local DB' },
      { id: 'push_buttoned', label: '3. Push buttoned keepers to Meta' },
      { id: 'finalize', label: '4. Build report (local = source of truth)' },
    ]
    setCleaning(true)
    setError('')
    setMsg('')
    const controller = beginHubJobAbort()
    setJob({
      ...EMPTY_JOB,
      open: true,
      title: label,
      dryRun,
      phase: 'running',
      steps: stepDefs.map((s) => ({ ...s, status: 'pending', detail: '' })),
    })

    let meta = null
    let local = null
    let push = null
    const PUSH_BATCH = 10
    try {
      for (const step of stepDefs) {
        patchJobStep(step.id, { status: 'running', detail: 'Running…' })

        if (step.id === 'push_buttoned') {
          // Batch pushes — nginx proxy_read_timeout is 300s; one big push always 504s.
          const acc = {
            ok: true,
            dry_run: dryRun,
            pushed_buttoned: [],
            failed: [],
            skipped_buttonless: [],
            skipped_buttonless_total: 0,
            keepers_count: 0,
            buttoned_total: 0,
          }
          let offset = 0
          let batchNum = 0
          for (;;) {
            batchNum += 1
            patchJobStep(step.id, {
              status: 'running',
              detail: `Pushing batch ${batchNum} (offset ${offset})…`,
            })
            const batch = await apiFetch('/admin/wa-templates/cleanup-and-sync', {
              method: 'POST',
              body: JSON.stringify({
                dry_run: dryRun,
                step: 'push_buttoned',
                offset,
                limit: PUSH_BATCH,
              }),
              timeoutMs: 280000,
              quietNetworkHint: true,
              signal: controller.signal,
            })
            acc.pushed_buttoned.push(...(batch?.pushed_buttoned || []))
            acc.failed.push(...(batch?.failed || []))
            if (offset === 0) {
              acc.skipped_buttonless = batch?.skipped_buttonless || []
              acc.skipped_buttonless_total = batch?.skipped_buttonless_total ?? acc.skipped_buttonless.length
              acc.keepers_count = batch?.keepers_count ?? 0
              acc.buttoned_total = batch?.buttoned_total ?? 0
            }
            const done = acc.pushed_buttoned.length + acc.failed.length
            const total = acc.buttoned_total || done
            patchJobStep(step.id, {
              status: 'running',
              detail: `Pushed ${done} / ${total} buttoned…`,
            })
            if (!batch?.has_more) break
            offset = Number(batch?.next_offset ?? offset + PUSH_BATCH)
          }
          acc.pushed_buttoned_count = acc.pushed_buttoned.length
          acc.failed_count = acc.failed.length
          acc.skipped_buttonless_count = acc.skipped_buttonless.length
          push = acc
          patchJobStep(step.id, {
            status: 'done',
            detail: `Pushed ${acc.pushed_buttoned_count}, failed ${acc.failed_count}, buttonless ${acc.skipped_buttonless_total}`,
          })
          continue
        }

        const body = { dry_run: dryRun, step: step.id }
        if (step.id === 'finalize') {
          body.meta = meta
          body.local = local
          body.push = push
        }
        const result = await apiFetch('/admin/wa-templates/cleanup-and-sync', {
          method: 'POST',
          body: JSON.stringify(body),
          timeoutMs: 280000,
          quietNetworkHint: true,
          signal: controller.signal,
        })
        if (step.id === 'meta_cleanup') meta = result
        if (step.id === 'local_cleanup') local = result

        const detail =
          result?.message ||
          (step.id === 'meta_cleanup'
            ? `Deleted ${result?.deleted_meta_count ?? 0} from Meta`
            : step.id === 'local_cleanup'
              ? `Deleted ${result?.deleted_local_count ?? 0} from local`
              : 'Report ready')
        patchJobStep(step.id, { status: 'done', detail })

        if (step.id === 'finalize') {
          const parts = [result?.message || label, result?.report_path ? `Report: ${result.report_path}` : null].filter(
            Boolean,
          )
          setMsg(parts.join(' · '))
          setJob((prev) => ({
            ...prev,
            phase: 'done',
            message: parts.join(' · '),
            summaryRows: Array.isArray(result?.summary_rows) ? result.summary_rows : [],
            tables: result?.tables || {},
            reportPath: result?.report_path || '',
          }))
        }
      }
      refreshSelectedProfileSummary()
      refreshTabData()
    } catch (e) {
      if (controller.signal.aborted || /cancelled/i.test(e?.message || '')) {
        setJob((prev) => ({
          ...prev,
          phase: 'cancelled',
          message: 'Stopped — job cancelled',
        }))
        return
      }
      const errText = formatWaSurveyError(e, `${label} failed`).detailText || e?.message
      setError(errText)
      setJob((prev) => ({
        ...prev,
        phase: 'error',
        error: errText,
      }))
    } finally {
      if (hubJobAbortRef.current === controller) hubJobAbortRef.current = null
      setCleaning(false)
    }
  }

  const flatTemplates = useMemo(() => {
    if (tab === 'ai') return interviewTemplates
    if (tab === 'marketing') return marketingTemplates
    if (tab === 'sales') return salesTemplates
    return []
  }, [tab, interviewTemplates, marketingTemplates, salesTemplates])

  const showCleanupActions = false

  return (
    <div className="waTemplatesHub ds-scope min-h-full bg-background">
      <header className="sticky top-0 z-30 border-b bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
        <div className="mx-auto max-w-[1400px] px-4 py-2">
          <div className="flex min-h-10 flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[#25D366]/15 text-[#128C7E]">
                <MessageSquareHeart className="h-4 w-4" />
              </div>
              <div>
                <div className="text-sm font-semibold leading-none">WA Templates</div>
                <div className="mt-0.5 text-[10px] text-muted-foreground">Internal · WhatsApp Business Templates</div>
              </div>
            </div>

            <div className="ml-auto flex flex-wrap items-center gap-2">
              <Link
                to="/ai/wa-messages"
                className="inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                Inbound messages
              </Link>
              {showCleanupActions ? (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 gap-1.5 text-xs"
                    onClick={() => void runCleanupAndSync({ dryRun: true })}
                    disabled={cleaning || syncing}
                  >
                    <Trash2 className={cn('h-3.5 w-3.5', cleaning && 'animate-pulse')} />
                    Dry-run cleanup
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 gap-1.5 text-xs"
                    onClick={() => void runCleanupAndSync({ dryRun: false })}
                    disabled={cleaning || syncing}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    {cleaning ? 'Cleaning…' : 'Cleanup + push buttoned'}
                  </Button>
                </>
              ) : null}
              <WaSyncProfileSelect
                items={syncProfileItems}
                value={syncProfile?.id}
                onChange={setSyncProfileId}
                loading={syncProfilesLoading}
                disabled={syncing || refreshing || cleaning}
              />
              <Button
                size="sm"
                variant="outline"
                className="h-8 gap-1.5 text-xs"
                onClick={() => pushToPrimary()}
                disabled={syncing || refreshing || cleaning || !primarySyncProfile?.id}
                title="Push changed survey + system templates to the default Meta profile (skips already in-sync). Shows progress."
              >
                {syncProfileActionLabel(primarySyncProfile, 'Push changed')}
              </Button>
              {(tab === 'survey' || tab === 'feedback') && backupSyncProfile?.id ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 gap-1.5 text-xs"
                  onClick={() => mirrorToBackup()}
                  disabled={syncing || refreshing || cleaning}
                  title={
                    tab === 'feedback'
                      ? 'Force-push all customer feedback templates to Telnyx backup. Shows progress.'
                      : 'Force-push all survey industry + system templates to Telnyx backup. Shows progress.'
                  }
                >
                  {syncProfileActionLabel(backupSyncProfile, 'Mirror all')}
                </Button>
              ) : null}
              <Button
                size="sm"
                variant="outline"
                className="h-8 gap-1.5 text-xs"
                onClick={() => void pullFromMeta()}
                disabled={refreshing || syncing || cleaning || !syncProfile?.id}
                title="Pull approval status and category from Meta (does not push local changes)"
              >
                <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
                {refreshing ? 'Refreshing…' : 'Refresh status'}
              </Button>
              <Button
                size="sm"
                className="wa-hub-primary-btn h-8 gap-1.5 text-xs"
                onClick={() => void syncFromMeta()}
                disabled={syncing || refreshing || cleaning || !syncProfile?.id}
              >
                <RefreshCw className={cn('h-3.5 w-3.5', syncing && 'animate-spin')} />
                {syncing
                  ? syncProgress
                    ? `Syncing ${syncProgress}`
                    : 'Syncing…'
                  : syncProfileActionLabel(syncProfile, 'Sync')}
              </Button>
            </div>
          </div>

          <div className="mt-2 border-t border-border/60 pt-2">
            <WaSyncProfileMatrix
              profiles={syncProfileItems}
              selectedProfileId={syncProfile?.id}
              rowState={profileSummaries}
              activeServiceCode={syncServiceCode}
              onSelectProfile={setSyncProfileId}
              onRefreshProfile={(id) => void loadProfileSummary(id, { force: true })}
              onRefreshAll={() => void refreshAllProfileSummaries()}
              refreshingAll={refreshingAllProfiles}
              scopeLabel={hubScopeLabel}
            />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] p-4">
        {syncing && !job.open ? (
          <button
            type="button"
            className="mb-3 w-full rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-left text-xs text-primary hover:bg-primary/15"
            onClick={() => setJob((prev) => ({ ...prev, open: true }))}
          >
            Sync in progress{syncProgress ? ` (${syncProgress})` : ''} — click here to show progress window
          </button>
        ) : null}
        {error ? (
          <div className="mb-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </div>
        ) : null}
        {msg ? (
          <div className="mb-3 rounded-md border border-success/30 bg-success-soft px-3 py-2 text-xs text-success">
            {msg}
          </div>
        ) : null}

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="h-9 gap-1 rounded-lg border bg-surface-muted p-1">
            {TAGS.map((tg) => {
              const Icon = tg.icon
              return (
                <TabsTrigger
                  key={tg.id}
                  value={tg.id}
                  className="h-7 gap-1.5 rounded-md px-3 text-xs data-[state=active]:bg-background data-[state=active]:shadow-sm"
                >
                  <Icon className="h-3.5 w-3.5" />
                  {tg.label}
                </TabsTrigger>
              )
            })}
          </TabsList>

          {TAGS.map((tg) => (
            <TabsContent key={tg.id} value={tg.id} className="mt-3">
              <div className="overflow-hidden rounded-xl border bg-surface shadow-sm">
                {tg.id === 'survey' ? (
                  <WaIndustryBrowser
                    product="survey"
                    industries={surveyIndustries}
                    loadingIndustries={surveyIndustriesLoading}
                    industriesError={surveyIndustriesError}
                    onReloadIndustries={loadSurveyIndustries}
                    onEditRow={(row) => void openSurveyTypeEditor(row)}
                    onSyncRow={(row) => void pushSurveyType(row)}
                    onToggleRow={(row) => void toggleSurveyType(row)}
                    onDeleteRow={(row) => void deleteSurveyType(row)}
                    onRejectRow={setRejectRow}
                    syncingId={syncingId}
                    onOpenSystemTemplate={setEditTarget}
                    onError={setError}
                    onMessage={setMsg}
                    syncProfileId={syncProfile?.id}
                    syncProfile={syncProfile}
                    syncProfileItems={syncProfileItems}
                    primarySyncProfile={primarySyncProfile}
                    backupSyncProfile={backupSyncProfile}
                    backupSyncProfileId={backupSyncProfile?.id}
                    onRequestSyncConfirm={requestSyncConfirm}
                  />
                ) : null}

                {tg.id === 'feedback' ? (
                  <WaIndustryBrowser
                    product="feedback"
                    industries={feedbackIndustries}
                    loadingIndustries={feedbackIndustriesLoading}
                    industriesError={feedbackIndustriesError}
                    onReloadIndustries={loadFeedbackIndustries}
                    onEditRow={(row) => void openSurveyTypeEditor(row)}
                    onSyncRow={(row) => void pushSurveyType(row)}
                    onToggleRow={(row) => void toggleSurveyType(row)}
                    onDeleteRow={(row) => void deleteSurveyType(row)}
                    onRejectRow={setRejectRow}
                    syncingId={syncingId}
                    onOpenSystemTemplate={setEditTarget}
                    onError={setError}
                    onMessage={setMsg}
                    syncProfileId={syncProfile?.id}
                    syncProfile={syncProfile}
                    syncProfileItems={syncProfileItems}
                    primarySyncProfile={primarySyncProfile}
                    backupSyncProfile={backupSyncProfile}
                    backupSyncProfileId={backupSyncProfile?.id}
                    onRequestSyncConfirm={requestSyncConfirm}
                  />
                ) : null}

                {tg.id === 'ai' ? (
                  <WaTemplatesTable
                    templates={flatTemplates}
                    loading={flatLoading}
                    onEdit={(row) => setEditTarget({ product: 'interview', templateId: row.id })}
                    onSync={(row) => void pushInterview(row)}
                    onToggle={(row) => void toggleInterview(row)}
                    onDelete={(row) => void deleteInterview(row)}
                    onReject={setRejectRow}
                    syncingId={syncingId}
                    plainNames
                    showNew={false}
                    emptyLabel="No templates yet."
                  />
                ) : null}

                {tg.id === 'marketing' ? (
                  <WaTemplatesTable
                    templates={flatTemplates}
                    loading={flatLoading}
                    onEdit={(row) => void marketingAction(row, 'edit')}
                    onSync={(row) => void marketingAction(row, 'sync')}
                    onToggle={(row) => void marketingAction(row, 'disable')}
                    onDelete={(row) => void marketingAction(row, 'delete')}
                    showNew={false}
                    emptyLabel="No templates yet."
                  />
                ) : null}

                {tg.id === 'sales' ? (
                  <WaTemplatesTable
                    templates={flatTemplates}
                    loading={flatLoading}
                    onEdit={(row) => void salesAction(row, 'edit')}
                    onSync={(row) => void salesAction(row, 'sync')}
                    onToggle={(row) => void salesAction(row, 'disable')}
                    onDelete={(row) => void salesAction(row, 'delete')}
                    syncingId={syncingId}
                    showNew={false}
                    emptyLabel="No sales templates yet — open this tab to seed the four lead-sales templates."
                  />
                ) : null}

                {tg.id === 'companies' ? (
                  <div className="flex flex-col items-center gap-3 px-4 py-12 text-center">
                    <Building2 className="h-9 w-9 text-muted-foreground/60" />
                    <p className="max-w-md text-xs text-muted-foreground">
                      Customer Feedback Companies service — WhatsApp templates are not configured yet.
                    </p>
                  </div>
                ) : null}
              </div>
            </TabsContent>
          ))}
        </Tabs>
      </main>

      <WaEditSheet
        editTarget={editTarget}
        onClose={() => {
          setSyncConfirm(null)
          setEditTarget(null)
        }}
        syncProfile={syncProfile}
        syncProfileItems={syncProfileItems}
        primarySyncProfile={primarySyncProfile}
        backupSyncProfile={backupSyncProfile}
        syncConfirm={editTarget ? syncConfirm : null}
        onRequestSyncConfirm={requestSyncConfirm}
        onSaved={() => {
          if (editTarget?.product === 'interview') void loadInterview()
          setEditTarget(null)
        }}
      />

      <WaRejectedDialog
        open={Boolean(rejectRow)}
        row={rejectRow}
        onClose={() => setRejectRow(null)}
        onDone={(message) => {
          setMsg(message)
          void refreshSelectedProfileSummary()
          if (tab === 'ai') void loadInterview()
          if (tab === 'survey') void loadSurveyIndustries()
          if (tab === 'feedback') void loadFeedbackIndustries()
        }}
        onError={setError}
      />

      <WaJobProgressDialog
        open={job.open}
        title={job.title}
        dryRun={job.dryRun}
        steps={job.steps}
        phase={job.phase}
        summaryRows={job.summaryRows}
        tables={job.tables}
        message={job.message}
        error={job.error}
        reportPath={job.reportPath}
        progressPct={job.progressPct}
        onStop={stopHubJob}
        onClose={() => setJob(EMPTY_JOB)}
      />

      {!editTarget ? (
        <WaSyncConfirmDialog
          open={Boolean(syncConfirm)}
          title={syncConfirm?.title}
          action={syncConfirm?.action}
          detail={syncConfirm?.detail}
          profile={syncConfirm?.profile || syncProfile}
          onConfirm={syncConfirm?.onConfirm}
          onCancel={syncConfirm?.onCancel}
        />
      ) : null}
    </div>
  )
}
