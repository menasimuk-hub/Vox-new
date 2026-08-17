import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { money } from '../lib/billingAdminUtils'
import PlanPickerSelect from '../components/billing/PlanPickerSelect'
import { adminOrderViewPath, interviewFormatLabel, nextColumnSort, orderListSortTs, orderMatchesSearch, sortRowsByColumn } from '../lib/serviceOrderAdmin'
import { Button } from '@/components/ui/Button'
import { Panel, Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Pill } from '@/components/ui/Badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { Label } from '@/components/ui/Label'
import { Textarea } from '@/components/ui/Textarea'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableLoading,
  TableRow,
} from '@/components/ui/Table'

const TAB_IDS = ['overview', 'profile', 'branches', 'users', 'plan', 'suspend']

const CLINIC_ROLES = [
  { value: 'dental', label: 'Dental' },
  { value: 'receptionist', label: 'Receptionist' },
  { value: 'owner', label: 'Owner' },
  { value: 'manager', label: 'Manager' },
]

function tabFromSearchParams(searchParams) {
  const raw = String(searchParams.get('tab') || '').toLowerCase().trim()
  return TAB_IDS.includes(raw) ? raw : 'overview'
}

function publicAppBase() {
  return String(import.meta.env.VITE_PUBLIC_APP_URL || 'http://localhost:5173')
    .trim()
    .replace(/\/+$/, '')
}

function isProtectedUser(u) {
  if (u?.is_superuser) return true
  const em = String(u?.email || '').toLowerCase()
  return em.endsWith('@voxbulk.internal') || em === 'api-accounts@voxbulk.com'
}

export default function OrganisationProfile() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = useMemo(() => tabFromSearchParams(searchParams), [searchParams])
  const selectedUserId = String(searchParams.get('user_id') || '').trim()
  const orgIdFromQuery = String(searchParams.get('org_id') || '').trim()

  const [orgId, setOrgId] = useState(() => orgIdFromQuery || localStorage.getItem('voxbulk_admin_selected_org_id') || '')
  const [statusNote, setStatusNote] = useState({ type: '', text: '' })

  const signupUrl = orgId ? `${publicAppBase()}/signin?org_id=${encodeURIComponent(orgId)}` : ''

  useEffect(() => {
    const fromQuery = orgIdFromQuery
    const fromStore = localStorage.getItem('voxbulk_admin_selected_org_id') || ''
    if (fromQuery) {
      if (fromQuery !== fromStore) localStorage.setItem('voxbulk_admin_selected_org_id', fromQuery)
      if (fromQuery !== orgId) setOrgId(fromQuery)
      return
    }
    if (fromStore) {
      if (fromStore !== orgId) setOrgId(fromStore)
      const next = new URLSearchParams(searchParams)
      next.set('org_id', fromStore)
      setSearchParams(next, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sync org_id into URL once when missing
  }, [orgIdFromQuery])

  const buildParams = useCallback(
    (overrides = {}) => {
      const params = {}
      const id = overrides.org_id !== undefined ? overrides.org_id : orgId
      if (id) params.org_id = id
      const nextTab = overrides.tab !== undefined ? overrides.tab : tab
      if (nextTab && nextTab !== 'overview') params.tab = nextTab
      const uid = overrides.user_id !== undefined ? overrides.user_id : selectedUserId
      if (uid && (params.tab === 'users' || nextTab === 'users')) params.user_id = uid
      return params
    },
    [orgId, tab, selectedUserId],
  )

  const selectTab = useCallback(
    (id) => {
      const next = TAB_IDS.includes(id) ? id : 'overview'
      setSearchParams(buildParams({ tab: next, user_id: next === 'users' ? selectedUserId : '' }), { replace: true })
    },
    [setSearchParams, buildParams, selectedUserId],
  )

  const selectUserActivity = useCallback(
    (userId) => {
      setSearchParams(buildParams({ tab: 'users', user_id: userId }), { replace: true })
    },
    [setSearchParams, buildParams],
  )

  const flash = useCallback((type, text) => {
    setStatusNote({ type, text })
  }, [])

  const [org, setOrg] = useState(null)
  const [branches, setBranches] = useState(null)
  const [users, setUsers] = useState(null)
  const [plans, setPlans] = useState(null)
  const [feedbackPlans, setFeedbackPlans] = useState(null)
  const [categories, setCategories] = useState(null)
  const [loadError, setLoadError] = useState('')

  const [profileName, setProfileName] = useState('')
  const [profileNotes, setProfileNotes] = useState('')
  const [profileCategoryId, setProfileCategoryId] = useState('')
  const [profileAddress1, setProfileAddress1] = useState('')
  const [profileAddress2, setProfileAddress2] = useState('')
  const [profileCity, setProfileCity] = useState('')
  const [profileCountyState, setProfileCountyState] = useState('')
  const [profilePostcode, setProfilePostcode] = useState('')
  const [profileCountry, setProfileCountry] = useState('')
  const [profileContactName, setProfileContactName] = useState('')
  const [profileContactEmail, setProfileContactEmail] = useState('')
  const [profileContactPhone, setProfileContactPhone] = useState('')
  const [profileWebsite, setProfileWebsite] = useState('')
  const [profileSaving, setProfileSaving] = useState(false)

  const [planCode, setPlanCode] = useState('')
  const [subStatus, setSubStatus] = useState('active')
  const [planSaving, setPlanSaving] = useState(false)
  const [feedbackPlanCode, setFeedbackPlanCode] = useState('')
  const [feedbackSubStatus, setFeedbackSubStatus] = useState('active')
  const [feedbackPlanSaving, setFeedbackPlanSaving] = useState(false)
  const [walletCreditGbp, setWalletCreditGbp] = useState('50')
  const [walletBusy, setWalletBusy] = useState(false)
  const [financePreview, setFinancePreview] = useState(null)
  const [upgradePreview, setUpgradePreview] = useState(null)
  const [financeNote, setFinanceNote] = useState('')
  const [financeBusy, setFinanceBusy] = useState(false)

  const [suspendSaving, setSuspendSaving] = useState(false)
  const [hardDeleteBusy, setHardDeleteBusy] = useState('')

  const [newUserEmail, setNewUserEmail] = useState('')
  const [newUserPassword, setNewUserPassword] = useState('')
  const [newUserRole, setNewUserRole] = useState('dental')
  const [userCreateBusy, setUserCreateBusy] = useState(false)

  const [inviteEmailField, setInviteEmailField] = useState('')
  const [inviteRole, setInviteRole] = useState('dental')
  const [inviteBusy, setInviteBusy] = useState(false)
  const [lastInviteUrl, setLastInviteUrl] = useState('')
  const [pendingInvites, setPendingInvites] = useState(null)
  const [userActivity, setUserActivity] = useState(null)
  const [userActivityLoading, setUserActivityLoading] = useState(false)
  const [userOrdersSearch, setUserOrdersSearch] = useState('')
  const [userOrdersSortField, setUserOrdersSortField] = useState('updated')
  const [userOrdersSortAsc, setUserOrdersSortAsc] = useState(false)

  const refreshFinancePreview = useCallback(async () => {
    if (!orgId) {
      setFinancePreview(null)
      return
    }
    try {
      const preview = await apiFetch(`/admin/organisations/${encodeURIComponent(orgId)}/billing/cancellation-preview`)
      setFinancePreview(preview)
    } catch {
      setFinancePreview(null)
    }
  }, [orgId])

  const refreshOrg = useCallback(async () => {
    if (!orgId) {
      setOrg(null)
      return
    }
    const o = await apiFetch(`/admin/organisations/${orgId}`)
    setOrg(o)
    setProfileName(o?.name || '')
    setProfileNotes(o?.profile_notes || '')
    setProfileCategoryId(o?.category_id || '')
    setProfileAddress1(o?.address_line1 || '')
    setProfileAddress2(o?.address_line2 || '')
    setProfileCity(o?.city || '')
    setProfileCountyState(o?.county_state || '')
    setProfilePostcode(o?.postcode || '')
    setProfileCountry(o?.country || '')
    setProfileContactName(o?.contact_name || '')
    setProfileContactEmail(o?.contact_email || '')
    setProfileContactPhone(o?.contact_phone || '')
    setProfileWebsite(o?.website || '')
    setPlanCode(o?.core_plan_code || o?.plan_code || '')
    setSubStatus(o?.core_subscription_status || o?.subscription_status ? String(o.core_subscription_status || o.subscription_status) : 'active')
    setFeedbackPlanCode(o?.feedback_plan_code || '')
    setFeedbackSubStatus(o?.feedback_subscription_status ? String(o.feedback_subscription_status) : 'active')
    setFinanceNote(o?.finance_notes || o?.profile_notes || '')
  }, [orgId])

  useEffect(() => {
    if (!orgId) return
    refreshFinancePreview().catch(() => setFinancePreview(null))
  }, [orgId, refreshFinancePreview, org?.updated_at])

  useEffect(() => {
    if (!orgId || !planCode.trim() || planCode.trim() === String(org?.core_plan_code || org?.plan_code || '').trim()) {
      setUpgradePreview(null)
      return undefined
    }
    let cancelled = false
    const timer = window.setTimeout(() => {
      apiFetch(
        `/admin/organisations/${encodeURIComponent(orgId)}/billing/upgrade-preview?plan_code=${encodeURIComponent(planCode.trim())}`,
      )
        .then((res) => {
          if (!cancelled) setUpgradePreview(res)
        })
        .catch(() => {
          if (!cancelled) setUpgradePreview(null)
        })
    }, 300)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [orgId, planCode, org?.core_plan_code, org?.plan_code])

  const refreshFeedbackPlans = useCallback(async () => {
    const zone = org?.market_zone || 'gb'
    try {
      const data = await apiFetch(`/admin/customer-feedback/plans?market_zone=${encodeURIComponent(zone)}`)
      const items = Array.isArray(data?.items) ? data.items : []
      setFeedbackPlans(items)
    } catch {
      setFeedbackPlans([])
    }
  }, [org?.market_zone])

  const refreshBranches = useCallback(async () => {
    if (!orgId) {
      setBranches([])
      return
    }
    const list = await apiFetch(`/admin/organisations/${orgId}/branches`)
    setBranches(Array.isArray(list) ? list : [])
  }, [orgId])

  const refreshUsers = useCallback(async () => {
    if (!orgId) {
      setUsers([])
      return
    }
    const list = await apiFetch(`/admin/organisations/${orgId}/users`)
    setUsers(Array.isArray(list) ? list : [])
  }, [orgId])

  const refreshPlans = useCallback(async () => {
    const list = await apiFetch('/admin/billing/plans')
    setPlans(Array.isArray(list) ? list : [])
  }, [])

  useEffect(() => {
    if (tab === 'plan' && org?.market_zone) {
      refreshFeedbackPlans().catch(() => setFeedbackPlans([]))
    }
  }, [tab, org?.market_zone, refreshFeedbackPlans])

  const refreshCategories = useCallback(async () => {
    const list = await apiFetch('/admin/categories')
    setCategories(Array.isArray(list) ? list : [])
  }, [])

  const refreshInvites = useCallback(async () => {
    if (!orgId) {
      setPendingInvites([])
      return
    }
    const list = await apiFetch(`/admin/organisations/${orgId}/invites`)
    setPendingInvites(Array.isArray(list) ? list : [])
  }, [orgId])

  const refreshUserActivity = useCallback(async () => {
    if (!orgId || !selectedUserId) {
      setUserActivity(null)
      return
    }
    setUserActivityLoading(true)
    try {
      const data = await apiFetch(`/admin/organisations/${orgId}/users/${selectedUserId}/activity`)
      setUserActivity(data)
    } catch {
      setUserActivity(null)
    } finally {
      setUserActivityLoading(false)
    }
  }, [orgId, selectedUserId])

  const userOrderSortAccessors = useMemo(
    () => ({
      reference: (o) => o.reference_id || o.campaign_id || o.id || '',
      title: (o) => o.title || '',
      service: (o) => o.service_code || '',
      format: (o) => (o.service_code === 'interview' ? interviewFormatLabel(o) : o.service_code || ''),
      status: (o) => o.status || '',
      quote: (o) => Number(o.quote_total_pence) || 0,
      updated: (o) => orderListSortTs(o),
    }),
    [],
  )

  const filteredUserOrders = useMemo(() => {
    const rows = userActivity?.service_orders || []
    const q = userOrdersSearch.trim()
    const filtered = q ? rows.filter((o) => orderMatchesSearch(o, q)) : rows
    return sortRowsByColumn(filtered, userOrdersSortField, userOrdersSortAsc, userOrderSortAccessors)
  }, [userActivity, userOrdersSearch, userOrdersSortField, userOrdersSortAsc, userOrderSortAccessors])

  const sortUserOrdersColumn = (field) => {
    const next = nextColumnSort(userOrdersSortField, userOrdersSortAsc, field)
    setUserOrdersSortField(next.field)
    setUserOrdersSortAsc(next.asc)
  }

  useEffect(() => {
    let cancelled = false
    setLoadError('')
    ;(async () => {
      if (!orgId) {
        setOrg(null)
        setBranches([])
        setUsers([])
        return
      }
      try {
        await refreshOrg()
        if (cancelled) return
      } catch (e) {
        if (!cancelled) {
          setLoadError(e?.message || 'Could not load organisation')
          setOrg(null)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [orgId, refreshOrg])

  useEffect(() => {
    if (!orgId) return
    if (tab === 'branches') {
      refreshBranches().catch(() => setBranches([]))
    }
    if (tab === 'users') {
      refreshUsers().catch(() => setUsers([]))
      refreshInvites().catch(() => setPendingInvites([]))
    }
    if (tab === 'users' && selectedUserId) {
      refreshUserActivity().catch(() => setUserActivity(null))
    }
    if (tab === 'plan') {
      refreshPlans().catch(() => setPlans([]))
    }
    if (tab === 'profile') {
      refreshCategories().catch(() => setCategories([]))
    }
  }, [tab, orgId, refreshBranches, refreshUsers, refreshPlans, refreshCategories, refreshInvites, selectedUserId, refreshUserActivity])

  useEffect(() => {
    if (!orgId || tab !== 'users') return
    const refresh = () => {
      if (document.visibilityState !== 'visible') return
      refreshUsers().catch(() => {})
      refreshInvites().catch(() => {})
    }
    document.addEventListener('visibilitychange', refresh)
    window.addEventListener('focus', refresh)
    return () => {
      document.removeEventListener('visibilitychange', refresh)
      window.removeEventListener('focus', refresh)
    }
  }, [tab, orgId, refreshUsers, refreshInvites])

  const createOrgUserDirect = async () => {
    if (!orgId) return
    const email = newUserEmail.trim().toLowerCase()
    if (!email || !email.includes('@')) {
      window.alert('Enter a valid email.')
      return
    }
    if (!newUserPassword.trim() || newUserPassword.trim().length < 6) {
      window.alert('Password is required (minimum 6 characters) for new users.')
      return
    }
    setUserCreateBusy(true)
    try {
      const res = await apiFetch(`/admin/organisations/${orgId}/users`, {
        method: 'POST',
        body: JSON.stringify({
          email,
          password: newUserPassword.trim(),
          role: newUserRole,
        }),
      })
      window.alert('User created or linked.')
      setNewUserEmail('')
      setNewUserPassword('')
      await refreshUsers()
      await refreshInvites()
      if (res?.user_id) selectUserActivity(res.user_id)
    } catch (e) {
      window.alert(e?.message || 'Could not create user')
    } finally {
      setUserCreateBusy(false)
    }
  }

  const createOrgInviteFlow = async () => {
    if (!orgId) return
    const email = inviteEmailField.trim().toLowerCase()
    if (!email) {
      window.alert('Enter an email.')
      return
    }
    setInviteBusy(true)
    try {
      const res = await apiFetch(`/admin/organisations/${orgId}/invites`, {
        method: 'POST',
        body: JSON.stringify({ email, role: inviteRole }),
      })
      const built =
        res?.signup_url ||
        (res?.token ? `${publicAppBase()}/signin?invite_token=${encodeURIComponent(res.token)}` : '')
      setLastInviteUrl(built)
      await refreshInvites()
    } catch (e) {
      window.alert(e?.message || 'Could not create invite')
    } finally {
      setInviteBusy(false)
    }
  }

  const revokeInviteRow = async (inviteId) => {
    if (!orgId || !inviteId) return
    try {
      await apiFetch(`/admin/organisations/${orgId}/invites/${inviteId}`, { method: 'DELETE' })
      await refreshInvites()
    } catch (e) {
      window.alert(e?.message || 'Could not revoke invite')
    }
  }

  const saveProfile = async () => {
    if (!orgId) return
    setProfileSaving(true)
    setStatusNote({ type: '', text: '' })
    try {
      await apiFetch(`/admin/organisations/${orgId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          name: profileName.trim(),
          profile_notes: profileNotes.trim() ? profileNotes.trim() : null,
          category_id: profileCategoryId.trim() ? profileCategoryId.trim() : null,
          address_line1: profileAddress1.trim() ? profileAddress1.trim() : null,
          address_line2: profileAddress2.trim() ? profileAddress2.trim() : null,
          city: profileCity.trim() ? profileCity.trim() : null,
          county_state: profileCountyState.trim() ? profileCountyState.trim() : null,
          postcode: profilePostcode.trim() ? profilePostcode.trim() : null,
          country: profileCountry.trim() ? profileCountry.trim() : null,
          contact_name: profileContactName.trim() ? profileContactName.trim() : null,
          contact_email: profileContactEmail.trim() ? profileContactEmail.trim() : null,
          contact_phone: profileContactPhone.trim() ? profileContactPhone.trim() : null,
          website: profileWebsite.trim() ? profileWebsite.trim() : null,
        }),
      })
      await refreshOrg()
      flash('ok', 'Profile saved.')
    } catch (e) {
      flash('error', e?.message || 'Save failed')
    } finally {
      setProfileSaving(false)
    }
  }

  const savePlan = async () => {
    if (!orgId || !planCode.trim()) {
      flash('error', 'Choose a Core Platform plan.')
      return
    }
    setPlanSaving(true)
    setStatusNote({ type: '', text: '' })
    try {
      await apiFetch(`/admin/organisations/${orgId}/subscription`, {
        method: 'PUT',
        body: JSON.stringify({ plan_code: planCode.trim(), status: subStatus.trim() || 'active' }),
      })
      await refreshOrg()
      flash('ok', 'Core Platform plan updated.')
    } catch (e) {
      flash('error', e?.message || 'Could not update Core Platform plan')
    } finally {
      setPlanSaving(false)
    }
  }

  const saveFeedbackPlan = async () => {
    if (!orgId || !feedbackPlanCode.trim()) {
      flash('error', 'Choose a Customer Feedback plan.')
      return
    }
    setFeedbackPlanSaving(true)
    setStatusNote({ type: '', text: '' })
    try {
      await apiFetch(`/admin/organisations/${orgId}/feedback-subscription`, {
        method: 'PUT',
        body: JSON.stringify({ plan_code: feedbackPlanCode.trim(), status: feedbackSubStatus.trim() || 'active' }),
      })
      await refreshOrg()
      await refreshFeedbackPlans()
      flash('ok', 'Customer Feedback plan updated.')
    } catch (e) {
      flash('error', e?.message || 'Could not update Customer Feedback plan')
    } finally {
      setFeedbackPlanSaving(false)
    }
  }

  const creditWallet = async () => {
    if (!orgId) return
    const pounds = Number(walletCreditGbp || 0)
    if (!Number.isFinite(pounds) || pounds <= 0) {
      flash('error', 'Enter a positive amount in GBP.')
      return
    }
    const amountPence = Math.round(pounds * 100)
    setWalletBusy(true)
    setStatusNote({ type: '', text: '' })
    try {
      const res = await apiFetch(`/admin/organisations/${orgId}/wallet/credit`, {
        method: 'POST',
        body: JSON.stringify({ amount_pence: amountPence, note: 'Admin test credit' }),
      })
      await refreshOrg()
      flash('ok', `Wallet credited. New balance: ${res.wallet_balance_display || res.wallet_balance_gbp || ''}`)
    } catch (e) {
      flash('error', e?.message || 'Could not credit wallet')
    } finally {
      setWalletBusy(false)
    }
  }

  const saveSuspended = async (next) => {
    if (!orgId) return
    setSuspendSaving(true)
    setStatusNote({ type: '', text: '' })
    try {
      await apiFetch(`/admin/organisations/${orgId}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_suspended: next }),
      })
      await refreshOrg()
      flash('ok', next ? 'Organisation suspended.' : 'Organisation unsuspended.')
    } catch (e) {
      flash('error', e?.message || 'Could not update suspension')
    } finally {
      setSuspendSaving(false)
    }
  }

  const setUserBlocked = async (userId, blocked) => {
    if (!orgId) return
    try {
      await apiFetch(`/admin/organisations/${orgId}/users/${userId}/block`, {
        method: 'POST',
        body: JSON.stringify({ blocked }),
      })
      await refreshUsers()
    } catch (e) {
      window.alert(e?.message || 'Could not update user')
    }
  }

  const removeUser = async (userId, email) => {
    if (!orgId) return
    if (!window.confirm(`Remove membership for ${email}? They will lose access to this organisation.`)) return
    try {
      await apiFetch(`/admin/organisations/${orgId}/users/${userId}`, { method: 'DELETE' })
      await refreshUsers()
    } catch (e) {
      window.alert(e?.message || 'Could not remove user')
    }
  }

  const hardDeleteUser = async (userId, email) => {
    if (!orgId) {
      window.alert('No organisation selected. Open an org from Organisations list first.')
      return
    }
    const typed = window.prompt(
      `TEST ONLY — permanently delete ${email}.\n` +
        `• Sole member of an org → wipe that org + billing/subscription\n` +
        `• Shared org → remove this user only (org kept)\n` +
        `Note: signing up again with a promo (e.g. UKMAN15) will create a NEW Starter plan + wallet credit.\n\n` +
        `Type exactly: HARD_DELETE`,
    )
    if (typed === null) return
    if (String(typed).trim() !== 'HARD_DELETE') {
      window.alert('Cancelled. You must type exactly: HARD_DELETE')
      return
    }
    setHardDeleteBusy(userId)
    try {
      const res = await apiFetch(`/admin/organisations/${orgId}/users/${userId}/hard-delete-test`, {
        method: 'POST',
        body: JSON.stringify({
          confirm: 'HARD_DELETE',
          delete_solo_org: true,
          delete_service_orders: true,
        }),
      })
      window.alert(`Hard deleted ${email}${res?.report?.solo_orgs?.length ? '\n\nOrg cleanup: see server report.' : ''}`)
      await refreshUsers()
      await refreshOrg()
    } catch (e) {
      window.alert(`Hard delete failed:\n\n${e?.message || 'Unknown error'}`)
    } finally {
      setHardDeleteBusy('')
    }
  }

  const pillTone = (status) => {
    const s = String(status || 'active').toLowerCase()
    if (s === 'pending') return 'warning'
    if (s === 'archived') return 'danger'
    if (s === 'cancelled') return 'info'
    return 'neutral'
  }

  return (
    <div className='ds-scope mx-auto max-w-[1440px] space-y-4 px-1 pb-12'>
      <div className='flex flex-wrap items-start justify-between gap-4 border-b border-border pb-4 pt-5'>
        <div>
          <h1 className='text-xl font-semibold tracking-tight text-foreground'>{org?.name || 'Organisation profile'}</h1>
          <p className='mt-1 max-w-2xl text-[13px] text-muted-foreground'>
            Tenant identity, branches, members, plans, and suspension. Billing ledger actions live in the Finance console.
          </p>
          {orgId ? (
            <div className='mt-2.5 flex flex-wrap items-center gap-2'>
              <code className='rounded-md border border-border bg-muted px-2 py-0.5 text-xs font-mono text-muted-foreground' title={orgId}>{orgId}</code>
              {org?.is_suspended ? <Pill tone='warning'>Suspended</Pill> : org ? <Pill tone='success'>Active</Pill> : null}
              {org?.category_name ? <Pill tone='info'>{org.category_name}</Pill> : null}
              {org?.deletion_status && org.deletion_status !== 'active' ? (
                <Pill tone={pillTone(org.deletion_status)}>{org.deletion_status}</Pill>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className='flex flex-wrap items-center gap-2'>
          <Button variant='outline' size='sm' asChild>
            <Link to='/organisations'>Organisations</Link>
          </Button>
          {orgId ? (
            <>
              <Button variant='outline' size='sm' asChild>
                <Link to={`/organisations/${encodeURIComponent(orgId)}`}>Ops detail</Link>
              </Button>
              <Button variant='outline' size='sm' asChild>
                <Link to={`/organisations/all-users/${encodeURIComponent(orgId)}`}>Finance console</Link>
              </Button>
              <Button
                variant='outline'
                size='sm'
                onClick={async () => {
                  if (!signupUrl) return
                  try {
                    await navigator.clipboard.writeText(signupUrl)
                    flash('ok', 'Signup link copied.')
                  } catch {
                    window.prompt('Copy signup link:', signupUrl)
                  }
                }}
              >
                Copy signup link
              </Button>
              <Button
                variant='outline'
                size='sm'
                onClick={() => signupUrl && window.open(signupUrl, '_blank', 'noopener,noreferrer')}
              >
                Open signup
              </Button>
            </>
          ) : null}
        </div>
      </div>

      {statusNote.text ? (
        <div className={statusNote.type === 'error' ? 'rounded-lg border border-destructive/35 bg-destructive/10 px-3 py-2.5 text-sm text-destructive' : 'rounded-lg border border-success/35 bg-success-soft px-3 py-2.5 text-sm text-success'}>
          {statusNote.text}
        </div>
      ) : null}

      {!orgId && (
        <Panel bodyClassName='space-y-3'>
          <p className='m-0 text-sm text-muted-foreground'>Select an organisation from the list, then open Profile — or pass <code className='rounded bg-muted px-1.5 py-0.5 text-xs'>?org_id=…</code> in the URL.</p>
          <div>
            <Button asChild>
              <Link to='/organisations'>Browse organisations</Link>
            </Button>
          </div>
        </Panel>
      )}

      {loadError && orgId && (
        <Panel bodyClassName='rounded-lg border-destructive/40 bg-destructive/10'>
          <p className='m-0 text-sm text-destructive'>{loadError}</p>
        </Panel>
      )}

      {org?.deletion_status && org.deletion_status !== 'active' ? (
        <Panel bodyClassName={org.deletion_status === 'pending' ? 'border-warning/40 bg-warning/10' : 'border-destructive/35 bg-destructive/10'}>
          <div className='flex flex-wrap items-center gap-3'>
            <Pill tone={pillTone(org.deletion_status)}>
              {org.deletion_status === 'pending' ? 'Pending deletion' : org.deletion_status === 'archived' ? 'Deleted' : org.deletion_status}
            </Pill>
            {org.deletion_requested_at ? (
              <span className='text-[13px] text-muted-foreground'>
                Requested {new Date(org.deletion_requested_at).toLocaleString()}
              </span>
            ) : null}
            {org.deletion_status === 'pending' ? (
              <Button variant='outline' size='sm' className='ml-auto' asChild>
                <Link to='/compliance/account-deletions'>Open deletion queue</Link>
              </Button>
            ) : null}
          </div>
        </Panel>
      ) : null}

      <div className='inline-flex h-9 items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground'>
        {TAB_IDS.map((id) => (
          <div
            key={id}
            className={`inline-flex cursor-pointer items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium transition-all ${tab === id ? 'bg-background text-foreground shadow' : ''}`}
            role='button'
            tabIndex={0}
            onClick={() => selectTab(id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                selectTab(id)
              }
            }}
          >
            {id === 'suspend' ? 'Suspension' : id.charAt(0).toUpperCase() + id.slice(1)}
          </div>
        ))}
      </div>

      {tab === 'overview' && (
        <div className='grid grid-cols-1 gap-4 lg:grid-cols-12'>
          <div className='space-y-4 lg:col-span-8'>
            <Panel bodyClassName='space-y-3'>
              <h2 className='text-lg font-semibold'>{org ? org.name : orgId ? 'Loading…' : 'No organisation selected'}</h2>
              <p className='text-sm text-muted-foreground'>
                {org
                  ? `${org.user_count} users · ${org.branch_count} branches · ${org.patient_count} patients · Core Platform ${org.core_plan_name || org.core_plan_code || org.plan_name || org.plan_code || '—'} · Customer Feedback ${org.feedback_plan_name || org.feedback_plan_code || '—'}`
                  : 'Select an org from the Organisations page.'}
              </p>
              <div className='flex flex-wrap items-center gap-2'>
                {org?.category_name ? <Pill tone='info'>Category: {org.category_name}</Pill> : null}
                {org?.is_suspended ? <Pill tone='warning'>Suspended — organisation login blocked</Pill> : org ? <Pill tone='success'>Active</Pill> : null}
                {typeof org?.recovery_job_count === 'number' ? (
                  <Pill tone='info'>Recovery jobs: {org.recovery_job_count}</Pill>
                ) : null}
              </div>
              <div className='flex flex-wrap gap-2'>
                <Button variant='outline' size='sm' onClick={() => selectTab('profile')}>Edit profile</Button>
                <Button variant='outline' size='sm' onClick={() => selectTab('users')}>Manage users</Button>
                <Button variant='outline' size='sm' onClick={() => selectTab('plan')}>Manage plans</Button>
                {orgId ? (
                  <Button variant='outline' size='sm' asChild>
                    <Link to={`/organisations/all-users/${encodeURIComponent(orgId)}`}>Finance console</Link>
                  </Button>
                ) : null}
              </div>
            </Panel>
            <div className='grid grid-cols-2 gap-3 sm:grid-cols-4'>
              <Card className='relative overflow-hidden p-4 before:absolute before:inset-0 before:border-l-2 before:content-[""] before:border-l-[oklch(0.47_0.13_175)]'>
                <div className='text-xs text-muted-foreground'>Users</div>
                <div className='mt-1 text-2xl font-bold'>{org ? org.user_count : '—'}</div>
              </Card>
              <Card className='relative overflow-hidden p-4 before:absolute before:inset-0 before:border-l-2 before:content-[""] before:border-l-[oklch(0.52_0.1_195)]'>
                <div className='text-xs text-muted-foreground'>Patients</div>
                <div className='mt-1 text-2xl font-bold'>{org ? org.patient_count : '—'}</div>
              </Card>
              <Card className='relative overflow-hidden p-4 before:absolute before:inset-0 before:border-l-2 before:content-[""] before:border-l-[oklch(0.58_0.16_290)]'>
                <div className='text-xs text-muted-foreground'>Appointments</div>
                <div className='mt-1 text-2xl font-bold'>{org ? org.appointment_count : '—'}</div>
              </Card>
              <Card className='relative overflow-hidden p-4 before:absolute before:inset-0 before:border-l-2 before:content-[""] before:border-l-[oklch(0.57_0.15_45)]'>
                <div className='text-xs text-muted-foreground'>Branches</div>
                <div className='mt-1 text-2xl font-bold'>{org ? org.branch_count : '—'}</div>
              </Card>
            </div>
          </div>
          <div className='space-y-4 lg:col-span-4'>
            <Panel title='Billing snapshot' bodyClassName='space-y-3'>
              <div className='space-y-2 text-sm'>
                <div className='flex justify-between'><span className='text-muted-foreground'>Core Platform plan</span><strong>{org?.core_plan_name || org?.core_plan_code || org?.plan_name || org?.plan_code || '—'}</strong></div>
                <div className='flex justify-between'><span className='text-muted-foreground'>Core Platform status</span><strong>{org?.core_subscription_status || org?.subscription_status || '—'}</strong></div>
                <div className='flex justify-between'><span className='text-muted-foreground'>Customer Feedback plan</span><strong>{org?.feedback_plan_name || org?.feedback_plan_code || '—'}</strong></div>
                <div className='flex justify-between'><span className='text-muted-foreground'>Customer Feedback status</span><strong>{org?.feedback_subscription_status || '—'}</strong></div>
                <div className='flex justify-between'><span className='text-muted-foreground'>Next billing (Core)</span><strong>{financePreview?.subscription_finance?.next_billing_date ? new Date(financePreview.subscription_finance.next_billing_date).toLocaleDateString() : '—'}</strong></div>
                <div className='flex justify-between'><span className='text-muted-foreground'>Next charge (Core)</span><strong>{financePreview?.subscription_finance?.amount_next_payment_display || '—'}</strong></div>
                <div className='flex justify-between'><span className='text-muted-foreground'>Cancellation</span><strong>{financePreview?.status || 'none'}</strong></div>
                <div className='flex justify-between'><span className='text-muted-foreground'>Wallet</span><strong>{org?.wallet_balance_display || org?.wallet_balance_gbp || '—'}</strong></div>
              </div>
              <div className='flex flex-wrap gap-2'>
                <Button variant='outline' size='sm' onClick={() => selectTab('plan')}>Manage plan</Button>
                {orgId ? (
                  <Button variant='outline' size='sm' asChild>
                    <Link to={`/organisations/all-users/${encodeURIComponent(orgId)}`}>Finance console</Link>
                  </Button>
                ) : null}
                <Button variant='outline' size='sm' asChild>
                  <Link to='/onboarding/services'>Product services</Link>
                </Button>
              </div>
            </Panel>
          </div>
        </div>
      )}

      {tab === 'profile' && (
        <Panel title='Profile details' action={<Pill tone='info'>Saved fields</Pill>} bodyClassName='space-y-6'>
          <div className='space-y-4'>
            <div className='grid gap-4 md:grid-cols-2'>
              <div className='space-y-2'>
                <Label htmlFor='org-profile-name'>Organisation name</Label>
                <Input
                  id='org-profile-name'
                  value={profileName}
                  onChange={(e) => setProfileName(e.target.value)}
                  disabled={!orgId}
                />
              </div>
              <div className='space-y-2'>
                <Label htmlFor='org-profile-category'>Category</Label>
                <select
                  id='org-profile-category'
                  className='flex h-9 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50'
                  value={profileCategoryId}
                  onChange={(e) => setProfileCategoryId(e.target.value)}
                  disabled={!orgId}
                >
                  <option value=''>No category</option>
                  {(categories || []).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.slug})
                    </option>
                  ))}
                </select>
                <p className='text-xs leading-tight text-muted-foreground'>
                  Manage categories under Organisations → Categories.
                </p>
              </div>
            </div>
          </div>

          <div className='space-y-4'>
            <div className='text-sm font-semibold text-foreground'>Address</div>
            <div className='space-y-4'>
              <div className='space-y-2'>
                <Label htmlFor='org-profile-address1'>Address line 1</Label>
                <Input id='org-profile-address1' value={profileAddress1} onChange={(e) => setProfileAddress1(e.target.value)} />
              </div>
              <div className='space-y-2'>
                <Label htmlFor='org-profile-address2'>Address line 2</Label>
                <Input id='org-profile-address2' value={profileAddress2} onChange={(e) => setProfileAddress2(e.target.value)} />
              </div>
              <div className='grid gap-4 md:grid-cols-2'>
                <div className='space-y-2'>
                  <Label htmlFor='org-profile-city'>City</Label>
                  <Input id='org-profile-city' value={profileCity} onChange={(e) => setProfileCity(e.target.value)} />
                </div>
                <div className='space-y-2'>
                  <Label htmlFor='org-profile-county'>County / state</Label>
                  <Input id='org-profile-county' value={profileCountyState} onChange={(e) => setProfileCountyState(e.target.value)} />
                </div>
                <div className='space-y-2'>
                  <Label htmlFor='org-profile-postcode'>Postcode</Label>
                  <Input id='org-profile-postcode' value={profilePostcode} onChange={(e) => setProfilePostcode(e.target.value)} />
                </div>
                <div className='space-y-2'>
                  <Label htmlFor='org-profile-country'>Country</Label>
                  <Input id='org-profile-country' value={profileCountry} onChange={(e) => setProfileCountry(e.target.value)} />
                </div>
              </div>
            </div>
          </div>

          <div className='space-y-4'>
            <div className='text-sm font-semibold text-foreground'>Primary contact</div>
            <div className='grid gap-4 md:grid-cols-2'>
              <div className='space-y-2'>
                <Label htmlFor='org-profile-contact-name'>Contact name</Label>
                <Input id='org-profile-contact-name' value={profileContactName} onChange={(e) => setProfileContactName(e.target.value)} />
              </div>
              <div className='space-y-2'>
                <Label htmlFor='org-profile-contact-email'>Contact email</Label>
                <Input id='org-profile-contact-email' type='email' autoComplete='off' value={profileContactEmail} onChange={(e) => setProfileContactEmail(e.target.value)} />
              </div>
              <div className='space-y-2'>
                <Label htmlFor='org-profile-phone'>Contact phone</Label>
                <Input id='org-profile-phone' value={profileContactPhone} onChange={(e) => setProfileContactPhone(e.target.value)} />
              </div>
              <div className='space-y-2'>
                <Label htmlFor='org-profile-website'>Website</Label>
                <Input id='org-profile-website' placeholder='https://…' value={profileWebsite} onChange={(e) => setProfileWebsite(e.target.value)} />
              </div>
            </div>
          </div>

          <div className='space-y-2'>
            <Label htmlFor='org-profile-notes'>Notes</Label>
            <Textarea
              id='org-profile-notes'
              rows={5}
              value={profileNotes}
              onChange={(e) => setProfileNotes(e.target.value)}
              disabled={!orgId}
              placeholder='Internal notes…'
            />
          </div>

          <div>
            <Button disabled={!orgId || profileSaving} onClick={saveProfile}>
              {profileSaving ? 'Saving…' : 'Save profile'}
            </Button>
          </div>
        </Panel>
      )}

      {tab === 'branches' && (
        <Panel title='Branches'>
          <StripeTable>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>City</TableHead>
                <TableHead>Postcode</TableHead>
                <TableHead>Address</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(branches || []).map((b) => (
                <TableRow key={b.id}>
                  <TableCell>{b.name}</TableCell>
                  <TableCell>{b.city || '—'}</TableCell>
                  <TableCell>{b.postcode || '—'}</TableCell>
                  <TableCell>{b.address_line1 || '—'}</TableCell>
                  <TableCell>{b.created_at ? new Date(b.created_at).toLocaleString() : '—'}</TableCell>
                </TableRow>
              ))}
              {!branches && <TableLoading colSpan={5} />}
              {branches && branches.length === 0 && <TableEmpty colSpan={5}>No branches recorded.</TableEmpty>}
            </TableBody>
          </StripeTable>
        </Panel>
      )}

      {tab === 'users' && (
        <div className='space-y-3.5'>
          <Panel title='Add user (direct)' bodyClassName='space-y-2.5'>
            <p className='m-0 text-[13px] text-muted-foreground'>
              Creates an active login for a new email, or links an existing account to this organisation. Password is required only for brand-new emails.
            </p>
            <div className='space-y-1.5'>
              <Label className='text-xs text-muted-foreground'>Email</Label>
              <Input value={newUserEmail} onChange={(e) => setNewUserEmail(e.target.value)} disabled={!orgId} placeholder='name@company.com' />
            </div>
            <div className='space-y-1.5'>
              <Label className='text-xs text-muted-foreground'>
                Temporary password <span className='text-destructive'>*</span>
              </Label>
              <Input type='password' autoComplete='new-password' required minLength={6} value={newUserPassword} onChange={(e) => setNewUserPassword(e.target.value)} disabled={!orgId} placeholder='Min 6 characters' />
            </div>
            <div className='space-y-1.5'>
              <Label className='text-xs text-muted-foreground'>Role</Label>
              <select className='flex h-9 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50' value={newUserRole} onChange={(e) => setNewUserRole(e.target.value)} disabled={!orgId}>
                {CLINIC_ROLES.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>
            <Button disabled={!orgId || userCreateBusy} onClick={createOrgUserDirect}>
              {userCreateBusy ? 'Saving…' : 'Create / link user'}
            </Button>
          </Panel>

          <Panel title='Invite user (link)' bodyClassName='space-y-2.5'>
            <p className='m-0 text-[13px] text-muted-foreground'>
              Sends no email from the server — copy the invite URL and share it. The user sets their password on the public sign-in page.
            </p>
            <div className='space-y-1.5'>
              <Label className='text-xs text-muted-foreground'>Email</Label>
              <Input value={inviteEmailField} onChange={(e) => setInviteEmailField(e.target.value)} disabled={!orgId} placeholder='name@company.com' />
            </div>
            <div className='space-y-1.5'>
              <Label className='text-xs text-muted-foreground'>Role (applied when they accept)</Label>
              <select className='flex h-9 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50' value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} disabled={!orgId}>
                {CLINIC_ROLES.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>
            <Button disabled={!orgId || inviteBusy} onClick={createOrgInviteFlow}>
              {inviteBusy ? 'Creating…' : 'Generate invite link'}
            </Button>
            {lastInviteUrl && (
              <div className='space-y-1.5'>
                <Label className='text-xs text-muted-foreground'>Latest invite URL</Label>
                <code className='block break-all rounded-lg bg-muted p-2 text-xs'>{lastInviteUrl}</code>
                <div className='flex flex-wrap gap-2'>
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(lastInviteUrl)
                        window.alert('Copied.')
                      } catch {
                        window.prompt('Copy:', lastInviteUrl)
                      }
                    }}
                  >
                    Copy link
                  </Button>
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => window.open(lastInviteUrl, '_blank', 'noopener,noreferrer')}
                  >
                    Open link
                  </Button>
                </div>
              </div>
            )}
          </Panel>

          <Panel title='Pending invites'>
            <StripeTable>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Expires</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(pendingInvites || []).map((inv) => (
                  <TableRow key={inv.id}>
                    <TableCell>{inv.email}</TableCell>
                    <TableCell>{inv.role || '—'}</TableCell>
                    <TableCell>{inv.created_at ? new Date(inv.created_at).toLocaleString() : '—'}</TableCell>
                    <TableCell>{inv.expires_at ? new Date(inv.expires_at).toLocaleString() : '—'}</TableCell>
                    <TableCell>
                      {inv.is_expired ? <Pill tone='warning'>Expired</Pill> : <Pill tone='info'>Pending</Pill>}
                    </TableCell>
                    <TableCell>
                      <Button variant='outline' size='sm' className='h-7 text-xs' onClick={() => revokeInviteRow(inv.id)}>Revoke</Button>
                    </TableCell>
                  </TableRow>
                ))}
                {!pendingInvites && <TableLoading colSpan={6} />}
                {pendingInvites && pendingInvites.length === 0 && <TableEmpty colSpan={6}>No pending invites.</TableEmpty>}
              </TableBody>
            </StripeTable>
          </Panel>

          <Panel title='Members' bodyClassName='space-y-3 overflow-x-auto'>
            <p className='m-0 text-xs text-muted-foreground'>
              <strong className='text-destructive'>Hard delete (TEST)</strong> — last button in each row’s Actions column.
              Works for any member (not only sole owners). Solo org is wiped; shared orgs keep other members. Type{' '}
              <code>HARD_DELETE</code> to confirm.
            </p>
            <StripeTable>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Flags</TableHead>
                  <TableHead>Linked</TableHead>
                  <TableHead className='w-[260px]'>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(users || []).map((u) => (
                  <TableRow key={u.user_id} className={selectedUserId === u.user_id ? 'bg-muted/40' : undefined}>
                    <TableCell>
                      <button type='button' className='text-primary hover:underline' onClick={() => selectUserActivity(u.user_id)}>
                        {u.email}
                      </button>
                    </TableCell>
                    <TableCell>{u.role || '—'}</TableCell>
                    <TableCell>
                      <div className='flex flex-wrap gap-1.5'>
                        {u.is_active ? <Pill tone='success'>Active</Pill> : <Pill tone='warning'>Blocked</Pill>}
                        {u.deletion_status && u.deletion_status !== 'active' ? (
                          <Pill tone={pillTone(u.deletion_status)}>
                            {u.deletion_label || u.deletion_status}
                          </Pill>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell>{u.is_superuser ? <Pill tone='neutral'>Platform admin</Pill> : '—'}</TableCell>
                    <TableCell>{u.linked_at ? new Date(u.linked_at).toLocaleString() : '—'}</TableCell>
                    <TableCell>
                      <div className='flex flex-wrap gap-1.5'>
                        <Button
                          variant='outline'
                          size='sm'
                          className='h-7 text-xs'
                          onClick={() => selectUserActivity(u.user_id)}
                        >
                          Activity
                        </Button>
                        {isProtectedUser(u) ? (
                          <span className='text-[11px] text-muted-foreground'>Protected</span>
                        ) : (
                          <>
                            <Button
                              variant='outline'
                              size='sm'
                              className='h-7 text-xs'
                              onClick={() => setUserBlocked(u.user_id, u.is_active)}
                            >
                              {u.is_active ? 'Block' : 'Unblock'}
                            </Button>
                            <Button
                              variant='outline'
                              size='sm'
                              className='h-7 text-xs'
                              onClick={() => removeUser(u.user_id, u.email)}
                            >
                              Remove
                            </Button>
                            <Button
                              variant='destructive'
                              size='sm'
                              className='h-7 text-xs'
                              disabled={hardDeleteBusy === u.user_id}
                              onClick={() => void hardDeleteUser(u.user_id, u.email)}
                            >
                              {hardDeleteBusy === u.user_id ? 'Deleting…' : 'Hard delete (TEST)'}
                            </Button>
                          </>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {!users && <TableLoading colSpan={6} />}
                {users && users.length === 0 && <TableEmpty colSpan={6}>No members yet.</TableEmpty>}
              </TableBody>
            </StripeTable>
            <p className='m-0 text-xs text-muted-foreground'>
              Generic organisation invite (no preset role):{' '}
              {signupUrl ? <code className='text-[11px]'>{signupUrl}</code> : '—'}
            </p>
          </Panel>

          {selectedUserId ? (
            <Panel
              title='User activity'
              action={
                <Button type='button' variant='outline' size='sm' className='h-8' onClick={() => refreshUserActivity()} disabled={userActivityLoading}>
                  {userActivityLoading ? 'Loading…' : 'Refresh'}
                </Button>
              }
              bodyClassName='space-y-3.5'
            >
              {userActivityLoading && !userActivity ? (
                <p className='m-0 text-sm text-muted-foreground'>Loading activity…</p>
              ) : userActivity ? (
                <>
                  <div className='space-y-1.5 text-sm'>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Email</span><strong>{userActivity.user?.email}</strong></div>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Role</span><strong>{userActivity.user?.role || '—'}</strong></div>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Linked</span><strong>{userActivity.user?.linked_at ? new Date(userActivity.user.linked_at).toLocaleString() : '—'}</strong></div>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Account created</span><strong>{userActivity.user?.account_created_at ? new Date(userActivity.user.account_created_at).toLocaleString() : '—'}</strong></div>
                  </div>

                  <div>
                    <h4 className='mb-2 mt-0 text-sm font-semibold'>Audit log ({userActivity.counts?.audit_events ?? 0})</h4>
                    {(userActivity.audit_events || []).length ? (
                      <div className='overflow-x-auto'>
                        <StripeTable>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Time</TableHead>
                              <TableHead>Action</TableHead>
                              <TableHead>Detail</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {userActivity.audit_events.map((ev) => (
                              <TableRow key={ev.id}>
                                <TableCell className='text-muted-foreground'>{ev.created_at ? new Date(ev.created_at).toLocaleString() : '—'}</TableCell>
                                <TableCell>{ev.action}</TableCell>
                                <TableCell>{ev.detail || '—'}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </StripeTable>
                      </div>
                    ) : (
                      <p className='m-0 text-[13px] text-muted-foreground'>No audit events recorded for this user yet.</p>
                    )}
                  </div>

                  <div>
                    <div className='mb-2 flex flex-wrap items-center gap-2'>
                      <h4 className='m-0 flex-1 text-sm font-semibold'>Service orders ({userActivity.counts?.service_orders ?? 0})</h4>
                      <Input
                        type='search'
                        className='h-8 min-w-[220px] max-w-sm'
                        placeholder='Search order ID, VB-CMP, reference, title…'
                        value={userOrdersSearch}
                        onChange={(e) => setUserOrdersSearch(e.target.value)}
                      />
                    </div>
                    {filteredUserOrders.length ? (
                      <div className='overflow-x-auto'>
                        <StripeTable>
                          <TableHeader>
                            <TableRow>
                              <TableHead className='cursor-pointer' onClick={() => sortUserOrdersColumn('reference')}>Order ID</TableHead>
                              <TableHead className='cursor-pointer' onClick={() => sortUserOrdersColumn('title')}>Title</TableHead>
                              <TableHead className='cursor-pointer' onClick={() => sortUserOrdersColumn('service')}>Service</TableHead>
                              <TableHead className='cursor-pointer' onClick={() => sortUserOrdersColumn('format')}>Format</TableHead>
                              <TableHead className='cursor-pointer' onClick={() => sortUserOrdersColumn('status')}>Status</TableHead>
                              <TableHead className='cursor-pointer' onClick={() => sortUserOrdersColumn('quote')}>Quote</TableHead>
                              <TableHead className='cursor-pointer' onClick={() => sortUserOrdersColumn('updated')}>Updated</TableHead>
                              <TableHead>View</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {filteredUserOrders.map((o) => (
                              <TableRow key={o.id}>
                                <TableCell className='text-muted-foreground'><code>{o.reference_id || o.campaign_id || o.id?.slice(0, 8)}</code></TableCell>
                                <TableCell>{o.title || '—'}</TableCell>
                                <TableCell>{o.service_code}</TableCell>
                                <TableCell>{o.service_code === 'interview' ? interviewFormatLabel(o) : '—'}</TableCell>
                                <TableCell><Pill tone='info'>{o.status}</Pill></TableCell>
                                <TableCell>{o.quote_total_gbp || money(Number(o.quote_total_pence || 0))}</TableCell>
                                <TableCell className='text-muted-foreground'>{o.updated_at ? new Date(o.updated_at).toLocaleString() : '—'}</TableCell>
                                <TableCell>
                                  <Button asChild variant='outline' size='sm' className='h-7 text-xs'>
                                    <Link to={adminOrderViewPath(o)}>Open</Link>
                                  </Button>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </StripeTable>
                      </div>
                    ) : (
                      <p className='m-0 text-[13px] text-muted-foreground'>{userOrdersSearch.trim() ? 'No orders match your search.' : 'No surveys or interviews created by this user.'}</p>
                    )}
                  </div>

                  <div>
                    <h4 className='mb-2 mt-0 text-sm font-semibold'>Support tickets ({userActivity.counts?.support_tickets ?? 0})</h4>
                    {(userActivity.support_tickets || []).length ? (
                      <div className='overflow-x-auto'>
                        <StripeTable>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Subject</TableHead>
                              <TableHead>Category</TableHead>
                              <TableHead>Status</TableHead>
                              <TableHead>Updated</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {userActivity.support_tickets.map((t) => (
                              <TableRow key={t.id}>
                                <TableCell>{t.subject}</TableCell>
                                <TableCell>{t.category}</TableCell>
                                <TableCell><Pill tone='info'>{t.status}</Pill></TableCell>
                                <TableCell className='text-muted-foreground'>{t.updated_at ? new Date(t.updated_at).toLocaleString() : '—'}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </StripeTable>
                      </div>
                    ) : (
                      <p className='m-0 text-[13px] text-muted-foreground'>No support tickets opened by this user.</p>
                    )}
                  </div>
                </>
              ) : (
                <p className='m-0 text-sm text-muted-foreground'>Could not load activity for this user.</p>
              )}
            </Panel>
          ) : null}
        </div>
      )}

      {tab === 'plan' && (
        <div className='grid gap-4 lg:grid-cols-2'>
          <Panel title='Core Platform plan' action={<Pill tone='info'>Subscription</Pill>} bodyClassName='space-y-3.5'>
            <p className='m-0 text-[13px] text-muted-foreground'>
              Current: <strong className='text-foreground'>{org?.core_plan_name || org?.core_plan_code || org?.plan_name || org?.plan_code || '—'}</strong> ({org?.core_subscription_status || org?.subscription_status || '—'})
            </p>
            {financePreview?.subscription_finance ? (
              <div className='space-y-1.5 text-[13px]'>
                <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Next billing</span><strong>{financePreview.subscription_finance.next_billing_date ? new Date(financePreview.subscription_finance.next_billing_date).toLocaleDateString() : '—'}</strong></div>
                <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Next charge</span><strong>{financePreview.subscription_finance.amount_next_payment_display || '—'}</strong></div>
                <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Cancel at period end</span><strong>{financePreview.subscription_finance.cancel_at_period_end ? 'Yes' : 'No'}</strong></div>
                <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Unused value (est.)</span><strong>{financePreview.calculated_unused_value_display || '—'}</strong></div>
              </div>
            ) : null}
            <label className='grid gap-1.5'>
              <span className='text-xs text-muted-foreground'>Core Platform plan</span>
              <PlanPickerSelect
                value={planCode}
                onChange={setPlanCode}
                productLine='core'
                placeholder='Choose Core platform plan…'
                disabled={!orgId}
                className='select'
              />
            </label>
            <label className='grid gap-1.5'>
              <span className='text-xs text-muted-foreground'>Subscription status</span>
              <Input className='h-8' value={subStatus} onChange={(e) => setSubStatus(e.target.value)} placeholder='active, trial…' disabled={!orgId} />
            </label>
            {upgradePreview ? (
              <div className='space-y-1.5 rounded-md bg-muted/50 p-2.5 text-[13px]'>
                <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Upgrade preview</span><strong>{upgradePreview.new_plan_name || upgradePreview.new_plan_code}</strong></div>
                <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Pro-rata charge</span><strong>{upgradePreview.pro_rata_display || money(upgradePreview.pro_rata_minor, upgradePreview.currency)}</strong></div>
                <div className='flex justify-between gap-3'><span className='text-muted-foreground'>New monthly</span><strong>{upgradePreview.new_monthly_display || money(upgradePreview.new_monthly_minor, upgradePreview.currency)}</strong></div>
              </div>
            ) : null}
            <Button size='sm' className='h-8' disabled={!orgId || planSaving || !planCode.trim()} onClick={savePlan}>
              {planSaving ? 'Applying…' : 'Apply Core Platform plan'}
            </Button>
            <p className='m-0 text-xs text-muted-foreground'>
              Assigns the Core Platform subscription only. Private packages (from Pricing → Private packages) appear in the picker as “Private · …”.
            </p>
          </Panel>

          <Panel title='Customer Feedback plan' action={<Pill tone='warning'>Separate billing</Pill>} bodyClassName='space-y-3.5'>
            <p className='m-0 text-[13px] text-muted-foreground'>
              Current: <strong className='text-foreground'>{org?.feedback_plan_name || org?.feedback_plan_code || 'None — assign below'}</strong>
              {org?.feedback_subscription_status ? ` (${org.feedback_subscription_status})` : ''}
            </p>
            {(org?.feedback_wa_units_included || org?.feedback_wa_units_used || org?.feedback_survey_units_remaining) ? (
              <div className='space-y-1.5 text-[13px]'>
                {String(org?.feedback_web_mode || '').toLowerCase() === 'shared' ? (
                  <>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Surveys included</span><strong>{org?.feedback_wa_units_included ?? 0}</strong></div>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Surveys used (WA + web)</span><strong>{(Number(org?.feedback_wa_units_used ?? 0) + Number(org?.feedback_web_units_used ?? 0))}</strong></div>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Surveys remaining</span><strong>{org?.feedback_survey_units_remaining ?? org?.feedback_wa_units_remaining ?? 0}</strong></div>
                  </>
                ) : String(org?.feedback_web_mode || '').toLowerCase() === 'separate' ? (
                  <>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>WA included</span><strong>{org?.feedback_wa_units_included ?? 0}</strong></div>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>WA used</span><strong>{org?.feedback_wa_units_used ?? 0}</strong></div>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>WA remaining</span><strong>{org?.feedback_wa_units_remaining ?? 0}</strong></div>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Web included</span><strong>{org?.feedback_web_units_included ?? 0}</strong></div>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Web used</span><strong>{org?.feedback_web_units_used ?? 0}</strong></div>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Web remaining</span><strong>{org?.feedback_web_units_remaining ?? 0}</strong></div>
                  </>
                ) : (
                  <>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>WA included</span><strong>{org?.feedback_wa_units_included ?? 0}</strong></div>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>WA used</span><strong>{org?.feedback_wa_units_used ?? 0}</strong></div>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>WA remaining</span><strong>{org?.feedback_wa_units_remaining ?? 0}</strong></div>
                    <div className='flex justify-between gap-3'><span className='text-muted-foreground'>Web surveys</span><strong>Not included</strong></div>
                  </>
                )}
              </div>
            ) : null}
            <label className='grid gap-1.5'>
              <span className='text-xs text-muted-foreground'>Customer Feedback plan</span>
              <PlanPickerSelect
                value={feedbackPlanCode}
                onChange={setFeedbackPlanCode}
                productLine='feedback'
                marketZone={org?.market_zone || 'gb'}
                placeholder='Choose Customer feedback plan…'
                disabled={!orgId}
                className='select'
              />
            </label>
            <label className='grid gap-1.5'>
              <span className='text-xs text-muted-foreground'>Subscription status</span>
              <Input className='h-8' value={feedbackSubStatus} onChange={(e) => setFeedbackSubStatus(e.target.value)} placeholder='active, trial…' disabled={!orgId} />
            </label>
            <Button size='sm' className='h-8' disabled={!orgId || feedbackPlanSaving || !feedbackPlanCode.trim()} onClick={saveFeedbackPlan}>
              {feedbackPlanSaving ? 'Applying…' : 'Apply Customer Feedback plan'}
            </Button>
            <p className='m-0 text-xs text-muted-foreground'>
              Customer Feedback billing is separate from Core Platform. An org can have both plans at once.
            </p>
          </Panel>

          <Panel title='Wallet & finance' bodyClassName='space-y-3.5'>
            <p className='m-0 text-[13px] text-muted-foreground'>
              Balance: <strong className='text-foreground'>{org?.wallet_balance_display || org?.wallet_balance_gbp || money(0, org?.billing_currency)}</strong> — ledger-backed credits only.
            </p>
            <label className='grid gap-1.5'>
              <span className='text-xs text-muted-foreground'>Add credit ({org?.billing_currency || 'GBP'})</span>
              <Input
                className='h-8'
                type='number'
                min='1'
                step='1'
                value={walletCreditGbp}
                onChange={(e) => setWalletCreditGbp(e.target.value)}
                disabled={!orgId || walletBusy}
              />
            </label>
            <Button variant='outline' size='sm' className='h-8' disabled={!orgId || walletBusy} onClick={creditWallet}>
              {walletBusy ? 'Crediting…' : 'Add wallet credit'}
            </Button>
            <Button asChild variant='outline' size='sm' className='h-8'>
              <Link to='/billing/wallet-ledger'>Global wallet ledger</Link>
            </Button>
            {orgId ? (
              <Button asChild variant='outline' size='sm' className='h-8'>
                <Link to={`/organisations/all-users/${encodeURIComponent(orgId)}`}>Open finance console</Link>
              </Button>
            ) : null}
          </Panel>

          <Panel title='Finance notes' bodyClassName='space-y-2.5'>
            <Textarea rows={4} value={financeNote} onChange={(e) => setFinanceNote(e.target.value)} disabled={!orgId} placeholder='Internal finance/admin notes…' />
            <Button
              variant='outline'
              size='sm'
              className='h-8'
              disabled={!orgId || financeBusy}
              onClick={async () => {
                setFinanceBusy(true)
                setStatusNote({ type: '', text: '' })
                try {
                  await apiFetch(`/admin/organisations/${orgId}`, { method: 'PATCH', body: JSON.stringify({ finance_notes: financeNote.trim() || null }) })
                  await refreshOrg()
                  flash('ok', 'Finance notes saved.')
                } catch (e) {
                  flash('error', e?.message || 'Could not save notes')
                } finally {
                  setFinanceBusy(false)
                }
              }}
            >
              {financeBusy ? 'Saving…' : 'Save notes'}
            </Button>
          </Panel>
        </div>
      )}

      {tab === 'suspend' && (
        <Panel title='Organisation suspension' bodyClassName='space-y-3.5'>
          <p className='m-0 text-[13px] text-muted-foreground'>
            When suspended, non–platform users cannot obtain a bearer token for this tenant. Superusers retain access for support.
          </p>
          <label className='flex cursor-pointer items-center gap-2.5'>
            <input
              type='checkbox'
              checked={Boolean(org?.is_suspended)}
              disabled={!org || suspendSaving}
              onChange={(e) => saveSuspended(e.target.checked)}
            />
            <span className='text-sm'>Suspended</span>
          </label>
          {suspendSaving && <span className='text-sm text-muted-foreground'>Updating…</span>}
        </Panel>
      )}
    </div>
  )
}
