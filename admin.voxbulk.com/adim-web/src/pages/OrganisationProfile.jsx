import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { money } from '../lib/billingAdminUtils'
import { adminOrderViewPath, interviewFormatLabel, nextColumnSort, orderListSortTs, orderMatchesSearch, sortRowsByColumn } from '../lib/serviceOrderAdmin'

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

function deletionPillClass(status) {
  const s = String(status || 'active').toLowerCase()
  if (s === 'pending') return 'p-amber'
  if (s === 'archived') return 'p-red'
  if (s === 'cancelled') return 'p-cyan'
  return ''
}

export default function OrganisationProfile() {
  const orgId = localStorage.getItem('voxbulk_admin_selected_org_id') || ''
  const signupUrl = orgId ? `${publicAppBase()}/signin?org_id=${encodeURIComponent(orgId)}` : ''

  const [searchParams, setSearchParams] = useSearchParams()
  const tab = useMemo(() => tabFromSearchParams(searchParams), [searchParams])
  const selectedUserId = String(searchParams.get('user_id') || '').trim()

  const selectTab = useCallback(
    (id) => {
      const next = TAB_IDS.includes(id) ? id : 'overview'
      if (next === 'overview') {
        setSearchParams({}, { replace: true })
      } else {
        const params = { tab: next }
        if (selectedUserId && next === 'users') params.user_id = selectedUserId
        setSearchParams(params, { replace: true })
      }
    },
    [setSearchParams, selectedUserId],
  )

  const selectUserActivity = useCallback(
    (userId) => {
      setSearchParams({ tab: 'users', user_id: userId }, { replace: true })
    },
    [setSearchParams],
  )

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
      window.alert('Profile saved.')
    } catch (e) {
      window.alert(e?.message || 'Save failed')
    } finally {
      setProfileSaving(false)
    }
  }

  const savePlan = async () => {
    if (!orgId || !planCode.trim()) {
      window.alert('Choose a C.P plan code.')
      return
    }
    setPlanSaving(true)
    try {
      await apiFetch(`/admin/organisations/${orgId}/subscription`, {
        method: 'PUT',
        body: JSON.stringify({ plan_code: planCode.trim(), status: subStatus.trim() || 'active' }),
      })
      await refreshOrg()
      window.alert('C.P plan updated.')
    } catch (e) {
      window.alert(e?.message || 'Could not update C.P plan')
    } finally {
      setPlanSaving(false)
    }
  }

  const saveFeedbackPlan = async () => {
    if (!orgId || !feedbackPlanCode.trim()) {
      window.alert('Choose an F.B plan code.')
      return
    }
    setFeedbackPlanSaving(true)
    try {
      await apiFetch(`/admin/organisations/${orgId}/feedback-subscription`, {
        method: 'PUT',
        body: JSON.stringify({ plan_code: feedbackPlanCode.trim(), status: feedbackSubStatus.trim() || 'active' }),
      })
      await refreshOrg()
      await refreshFeedbackPlans()
      window.alert('F.B plan updated.')
    } catch (e) {
      window.alert(e?.message || 'Could not update F.B plan')
    } finally {
      setFeedbackPlanSaving(false)
    }
  }

  const creditWallet = async () => {
    if (!orgId) return
    const pounds = Number(walletCreditGbp || 0)
    if (!Number.isFinite(pounds) || pounds <= 0) {
      window.alert('Enter a positive amount in GBP.')
      return
    }
    const amountPence = Math.round(pounds * 100)
    setWalletBusy(true)
    try {
      const res = await apiFetch(`/admin/organisations/${orgId}/wallet/credit`, {
        method: 'POST',
        body: JSON.stringify({ amount_pence: amountPence, note: 'Admin test credit' }),
      })
      await refreshOrg()
      window.alert(`Wallet credited. New balance: ${res.wallet_balance_display || res.wallet_balance_gbp || ''}`)
    } catch (e) {
      window.alert(e?.message || 'Could not credit wallet')
    } finally {
      setWalletBusy(false)
    }
  }

  const saveSuspended = async (next) => {
    if (!orgId) return
    setSuspendSaving(true)
    try {
      await apiFetch(`/admin/organisations/${orgId}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_suspended: next }),
      })
      await refreshOrg()
    } catch (e) {
      window.alert(e?.message || 'Could not update suspension')
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
      `TEST ONLY — permanently delete ${email}, billing records, and this org if they are the sole member.\n\nType exactly: HARD_DELETE`,
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

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Organisation profile</h1>
          <p>
            Manage tenant profile, branches, members, plan, and suspension. New registrations appear under Users once they complete sign-up and are linked to this org.
          </p>
        </div>
        <div className='actions'>
          <button
            className='btn soft'
            disabled={!orgId}
            onClick={async () => {
              if (!signupUrl) return
              try {
                await navigator.clipboard.writeText(signupUrl)
                window.alert('Signup link copied.')
              } catch {
                window.prompt('Copy signup link:', signupUrl)
              }
            }}
          >
            Copy signup link
          </button>
          <button
            className='btn soft'
            disabled={!orgId}
            onClick={() => signupUrl && window.open(signupUrl, '_blank', 'noopener,noreferrer')}
          >
            Open signup page
          </button>
        </div>
      </div>

      {!orgId && (
        <div className='card' style={{ marginBottom: 16 }}>
          <div className='cardBody'>
            <p className='muted'>Select an organisation from the list, or create one, then open this page again.</p>
          </div>
        </div>
      )}

      {loadError && orgId && (
        <div className='card' style={{ marginBottom: 16, borderColor: '#fecaca' }}>
          <div className='cardBody'>{loadError}</div>
        </div>
      )}

      {org?.deletion_status && org.deletion_status !== 'active' ? (
        <div className='card' style={{ marginBottom: 16, borderColor: org.deletion_status === 'pending' ? 'rgba(245,158,11,0.45)' : 'rgba(220,38,38,0.35)' }}>
          <div className='cardBody' style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <span className={`pill ${deletionPillClass(org.deletion_status)}`}>
              {org.deletion_status === 'pending' ? 'Pending deletion' : org.deletion_status === 'archived' ? 'Deleted' : org.deletion_status}
            </span>
            {org.deletion_requested_at ? (
              <span className='muted' style={{ fontSize: 13 }}>
                Requested {new Date(org.deletion_requested_at).toLocaleString()}
              </span>
            ) : null}
            {org.deletion_status === 'pending' ? (
              <Link className='btn soft' to='/compliance/account-deletions' style={{ marginLeft: 'auto' }}>
                Open deletion queue
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className='tabs' style={{ marginBottom: 16, flexWrap: 'wrap' }}>
        {TAB_IDS.map((id) => (
          <div
            key={id}
            className={`tab ${tab === id ? 'active' : ''}`}
            role='button'
            tabIndex={0}
            onClick={() => selectTab(id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                selectTab(id)
              }
            }}
            style={{ cursor: 'pointer' }}
          >
            {id === 'suspend' ? 'Suspension' : id.charAt(0).toUpperCase() + id.slice(1)}
          </div>
        ))}
      </div>

      {tab === 'overview' && (
        <div className='grid-12'>
          <div className='span-8 stack'>
            <div className='heroPanel'>
              <h2>{org ? org.name : orgId ? 'Loading…' : 'No organisation selected'}</h2>
              <p>
                {org
                  ? `${org.user_count} users · ${org.branch_count} branches · ${org.patient_count} patients · C.P ${org.core_plan_name || org.core_plan_code || org.plan_name || org.plan_code || '—'} · F.B ${org.feedback_plan_name || org.feedback_plan_code || '—'}`
                  : 'Select an org from the Organisations page.'}
              </p>
              {org?.category_name ? <span className='pill p-cyan'>Category: {org.category_name}</span> : null}
              {org?.is_suspended ? <span className='pill p-amber'>Suspended — clinic login blocked</span> : <span className='pill p-green'>Active</span>}
            </div>
            <div className='grid-4'>
              <div className='card stat' style={{ '--accent': '#0f766e' }}>
                <div className='muted'>Users</div>
                <div className='statValue'>{org ? org.user_count : '—'}</div>
              </div>
              <div className='card stat' style={{ '--accent': '#0891b2' }}>
                <div className='muted'>Patients</div>
                <div className='statValue'>{org ? org.patient_count : '—'}</div>
              </div>
              <div className='card stat' style={{ '--accent': '#7c3aed' }}>
                <div className='muted'>Appointments</div>
                <div className='statValue'>{org ? org.appointment_count : '—'}</div>
              </div>
              <div className='card stat' style={{ '--accent': '#d97706' }}>
                <div className='muted'>Branches</div>
                <div className='statValue'>{org ? org.branch_count : '—'}</div>
              </div>
            </div>
          </div>
          <div className='span-4 stack'>
            <div className='card'>
              <div className='cardHead'><h3>Billing snapshot</h3></div>
              <div className='cardBody'>
                <div className='list'>
                  <div className='listRow'><span>C.P plan</span><strong>{org?.core_plan_name || org?.core_plan_code || org?.plan_name || org?.plan_code || '—'}</strong></div>
                  <div className='listRow'><span>C.P status</span><strong>{org?.core_subscription_status || org?.subscription_status || '—'}</strong></div>
                  <div className='listRow'><span>F.B plan</span><strong>{org?.feedback_plan_name || org?.feedback_plan_code || '—'}</strong></div>
                  <div className='listRow'><span>F.B status</span><strong>{org?.feedback_subscription_status || '—'}</strong></div>
                  <div className='listRow'><span>Next billing (C.P)</span><strong>{financePreview?.subscription_finance?.next_billing_date ? new Date(financePreview.subscription_finance.next_billing_date).toLocaleDateString() : '—'}</strong></div>
                  <div className='listRow'><span>Next charge (C.P)</span><strong>{financePreview?.subscription_finance?.amount_next_payment_display || '—'}</strong></div>
                  <div className='listRow'><span>Cancellation</span><strong>{financePreview?.status || 'none'}</strong></div>
                </div>
                <div className='actions' style={{ marginTop: 12, flexWrap: 'wrap' }}>
                  <button type='button' className='btn soft' onClick={() => selectTab('plan')}>Manage plan</button>
                  <Link to='/organisations/all-users' className='btn soft' onClick={() => localStorage.setItem('voxbulk_admin_selected_org_id', orgId)}>Finance console</Link>
                  <Link to='/onboarding/services' className='btn soft'>Product services</Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === 'profile' && (
        <div className='card' style={{ maxWidth: 920, width: '100%', minWidth: 0 }}>
          <div className='cardHead'>
            <h3>Organisation profile</h3>
            <span className='pill p-cyan'>Saved fields</span>
          </div>
          <div className='cardBody'>
            <div className='orgProfileForm'>
              <section className='orgProfileSection'>
                <div className='formField'>
                  <label className='label' htmlFor='org-profile-name'>
                    Organisation name
                  </label>
                  <input
                    id='org-profile-name'
                    className='input'
                    value={profileName}
                    onChange={(e) => setProfileName(e.target.value)}
                    disabled={!orgId}
                  />
                </div>
                <div className='formField'>
                  <label className='label' htmlFor='org-profile-category'>
                    Category
                  </label>
                  <select
                    id='org-profile-category'
                    className='select'
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
                  <div className='muted' style={{ fontSize: 12, lineHeight: 1.45 }}>
                    Manage categories under Organisations → Categories.
                  </div>
                </div>
              </section>

              <section className='orgProfileSection'>
                <div className='formSectionTitle'>Address</div>
                <div className='formField'>
                  <label className='label' htmlFor='org-profile-address1'>
                    Address line 1
                  </label>
                  <input id='org-profile-address1' className='input' value={profileAddress1} onChange={(e) => setProfileAddress1(e.target.value)} />
                </div>
                <div className='formField'>
                  <label className='label' htmlFor='org-profile-address2'>
                    Address line 2
                  </label>
                  <input id='org-profile-address2' className='input' value={profileAddress2} onChange={(e) => setProfileAddress2(e.target.value)} />
                </div>
                <div className='orgProfileGrid2'>
                  <div className='formField'>
                    <label className='label' htmlFor='org-profile-city'>
                      City
                    </label>
                    <input id='org-profile-city' className='input' value={profileCity} onChange={(e) => setProfileCity(e.target.value)} />
                  </div>
                  <div className='formField'>
                    <label className='label' htmlFor='org-profile-county'>
                      County / state
                    </label>
                    <input id='org-profile-county' className='input' value={profileCountyState} onChange={(e) => setProfileCountyState(e.target.value)} />
                  </div>
                  <div className='formField'>
                    <label className='label' htmlFor='org-profile-postcode'>
                      Postcode
                    </label>
                    <input id='org-profile-postcode' className='input' value={profilePostcode} onChange={(e) => setProfilePostcode(e.target.value)} />
                  </div>
                  <div className='formField'>
                    <label className='label' htmlFor='org-profile-country'>
                      Country
                    </label>
                    <input id='org-profile-country' className='input' value={profileCountry} onChange={(e) => setProfileCountry(e.target.value)} />
                  </div>
                </div>
              </section>

              <section className='orgProfileSection'>
                <div className='formSectionTitle'>Primary contact</div>
                <div className='orgProfileGrid2'>
                  <div className='formField'>
                    <label className='label' htmlFor='org-profile-contact-name'>
                      Contact name
                    </label>
                    <input id='org-profile-contact-name' className='input' value={profileContactName} onChange={(e) => setProfileContactName(e.target.value)} />
                  </div>
                  <div className='formField'>
                    <label className='label' htmlFor='org-profile-contact-email'>
                      Contact email
                    </label>
                    <input id='org-profile-contact-email' className='input' type='email' autoComplete='off' value={profileContactEmail} onChange={(e) => setProfileContactEmail(e.target.value)} />
                  </div>
                  <div className='formField'>
                    <label className='label' htmlFor='org-profile-phone'>
                      Contact phone
                    </label>
                    <input id='org-profile-phone' className='input' value={profileContactPhone} onChange={(e) => setProfileContactPhone(e.target.value)} />
                  </div>
                  <div className='formField'>
                    <label className='label' htmlFor='org-profile-website'>
                      Website
                    </label>
                    <input id='org-profile-website' className='input' placeholder='https://…' value={profileWebsite} onChange={(e) => setProfileWebsite(e.target.value)} />
                  </div>
                </div>
              </section>

              <div className='formField'>
                <label className='label' htmlFor='org-profile-notes'>
                  Notes
                </label>
                <textarea
                  id='org-profile-notes'
                  className='input'
                  rows={5}
                  value={profileNotes}
                  onChange={(e) => setProfileNotes(e.target.value)}
                  disabled={!orgId}
                  placeholder='Internal notes…'
                />
              </div>

              <div className='actions' style={{ marginTop: 4 }}>
                <button type='button' className='btn primary' disabled={!orgId || profileSaving} onClick={saveProfile}>
                  {profileSaving ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === 'branches' && (
        <div className='card'>
          <div className='cardHead'><h3>Branches</h3></div>
          <div className='cardBody'>
            <div className='tableWrap'>
              <table className='table'>
                <thead>
                  <tr><th>Name</th><th>City</th><th>Postcode</th><th>Address</th><th>Created</th></tr>
                </thead>
                <tbody>
                  {(branches || []).map((b) => (
                    <tr key={b.id}>
                      <td>{b.name}</td>
                      <td>{b.city || '—'}</td>
                      <td>{b.postcode || '—'}</td>
                      <td>{b.address_line1 || '—'}</td>
                      <td>{b.created_at ? new Date(b.created_at).toLocaleString() : '—'}</td>
                    </tr>
                  ))}
                  {!branches && <tr><td colSpan={5}>Loading…</td></tr>}
                  {branches && branches.length === 0 && <tr><td colSpan={5}>No branches recorded.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {tab === 'users' && (
        <div className='stack' style={{ display: 'grid', gap: 14 }}>
          <div className='card'>
            <div className='cardHead'><h3>Add user (direct)</h3></div>
            <div className='cardBody stack' style={{ display: 'grid', gap: 10, maxWidth: 520 }}>
              <p className='muted' style={{ fontSize: 13, margin: 0 }}>
                Creates an active login for a new email, or links an existing account to this organisation. Password is required only for brand-new emails.
              </p>
              <label style={{ display: 'grid', gap: 6 }}>
                <span className='muted' style={{ fontSize: 12 }}>Email</span>
                <input className='input' value={newUserEmail} onChange={(e) => setNewUserEmail(e.target.value)} disabled={!orgId} placeholder='name@clinic.com' />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span className='muted' style={{ fontSize: 12 }}>
                  Temporary password <span style={{ color: '#dc2626' }}>*</span>
                </span>
                <input className='input' type='password' autoComplete='new-password' required minLength={6} value={newUserPassword} onChange={(e) => setNewUserPassword(e.target.value)} disabled={!orgId} placeholder='Min 6 characters' />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span className='muted' style={{ fontSize: 12 }}>Role</span>
                <select className='select' value={newUserRole} onChange={(e) => setNewUserRole(e.target.value)} disabled={!orgId}>
                  {CLINIC_ROLES.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </label>
              <button type='button' className='btn primary' disabled={!orgId || userCreateBusy} onClick={createOrgUserDirect}>
                {userCreateBusy ? 'Saving…' : 'Create / link user'}
              </button>
            </div>
          </div>

          <div className='card'>
            <div className='cardHead'><h3>Invite user (link)</h3></div>
            <div className='cardBody stack' style={{ display: 'grid', gap: 10, maxWidth: 520 }}>
              <p className='muted' style={{ fontSize: 13, margin: 0 }}>
                Sends no email from the server — copy the invite URL and share it. The user sets their password on the public sign-in page.
              </p>
              <label style={{ display: 'grid', gap: 6 }}>
                <span className='muted' style={{ fontSize: 12 }}>Email</span>
                <input className='input' value={inviteEmailField} onChange={(e) => setInviteEmailField(e.target.value)} disabled={!orgId} placeholder='name@clinic.com' />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span className='muted' style={{ fontSize: 12 }}>Role (applied when they accept)</span>
                <select className='select' value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} disabled={!orgId}>
                  {CLINIC_ROLES.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </label>
              <button type='button' className='btn primary' disabled={!orgId || inviteBusy} onClick={createOrgInviteFlow}>
                {inviteBusy ? 'Creating…' : 'Generate invite link'}
              </button>
              {lastInviteUrl && (
                <div style={{ display: 'grid', gap: 6 }}>
                  <span className='muted' style={{ fontSize: 12 }}>Latest invite URL</span>
                  <code style={{ fontSize: 12, wordBreak: 'break-all', background: 'var(--surface, #f8fafc)', padding: 8, borderRadius: 8 }}>{lastInviteUrl}</code>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <button
                      type='button'
                      className='btn soft'
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
                    </button>
                    <button
                      type='button'
                      className='btn soft'
                      onClick={() => window.open(lastInviteUrl, '_blank', 'noopener,noreferrer')}
                    >
                      Open link
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className='card'>
            <div className='cardHead'><h3>Pending invites</h3></div>
            <div className='cardBody'>
              <div className='tableWrap'>
                <table className='table'>
                  <thead>
                    <tr><th>Email</th><th>Role</th><th>Created</th><th>Expires</th><th>Status</th><th /></tr>
                  </thead>
                  <tbody>
                    {(pendingInvites || []).map((inv) => (
                      <tr key={inv.id}>
                        <td>{inv.email}</td>
                        <td>{inv.role || '—'}</td>
                        <td>{inv.created_at ? new Date(inv.created_at).toLocaleString() : '—'}</td>
                        <td>{inv.expires_at ? new Date(inv.expires_at).toLocaleString() : '—'}</td>
                        <td>
                          {inv.is_expired ? <span className='pill p-amber'>Expired</span> : <span className='pill p-cyan'>Pending</span>}
                        </td>
                        <td>
                          <button type='button' className='btn soft' style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => revokeInviteRow(inv.id)}>Revoke</button>
                        </td>
                      </tr>
                    ))}
                    {!pendingInvites && <tr><td colSpan={6}>Loading…</td></tr>}
                    {pendingInvites && pendingInvites.length === 0 && <tr><td colSpan={6}>No pending invites.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className='card'>
            <div className='cardHead'><h3>Members</h3></div>
            <div className='cardBody'>
              <p className='muted' style={{ fontSize: 12, marginBottom: 12 }}>
                <strong style={{ color: 'var(--red)' }}>Hard delete (TEST)</strong> — last button in each row’s Actions column.
                Wipes billing and permanently deletes the user (and solo org). Type <code>HARD_DELETE</code> to confirm.
              </p>
              <div className='tableWrap'>
                <table className='table'>
                  <thead>
                    <tr>
                      <th>Email</th>
                      <th>Role</th>
                      <th>Status</th>
                      <th>Flags</th>
                      <th>Linked</th>
                      <th style={{ width: 260 }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(users || []).map((u) => (
                      <tr key={u.user_id} className={selectedUserId === u.user_id ? 'rowSelected' : ''}>
                        <td>
                          <button type='button' className='linkish' onClick={() => selectUserActivity(u.user_id)}>
                            {u.email}
                          </button>
                        </td>
                        <td>{u.role || '—'}</td>
                        <td>
                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                            {u.is_active ? <span className='pill p-green'>Active</span> : <span className='pill p-amber'>Blocked</span>}
                            {u.deletion_status && u.deletion_status !== 'active' ? (
                              <span className={`pill ${deletionPillClass(u.deletion_status)}`}>
                                {u.deletion_label || u.deletion_status}
                              </span>
                            ) : null}
                          </div>
                        </td>
                        <td>{u.is_superuser ? <span className='pill'>Platform admin</span> : '—'}</td>
                        <td>{u.linked_at ? new Date(u.linked_at).toLocaleString() : '—'}</td>
                        <td>
                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                            <button
                              type='button'
                              className='btn soft'
                              style={{ padding: '4px 10px', fontSize: 12 }}
                              onClick={() => selectUserActivity(u.user_id)}
                            >
                              Activity
                            </button>
                            {isProtectedUser(u) ? (
                              <span className='muted' style={{ fontSize: 11 }}>Protected</span>
                            ) : (
                              <>
                                <button
                                  type='button'
                                  className='btn soft'
                                  style={{ padding: '4px 10px', fontSize: 12 }}
                                  onClick={() => setUserBlocked(u.user_id, u.is_active)}
                                >
                                  {u.is_active ? 'Block' : 'Unblock'}
                                </button>
                                <button
                                  type='button'
                                  className='btn soft'
                                  style={{ padding: '4px 10px', fontSize: 12 }}
                                  onClick={() => removeUser(u.user_id, u.email)}
                                >
                                  Remove
                                </button>
                                <button
                                  type='button'
                                  className='btn soft'
                                  style={{ padding: '4px 10px', fontSize: 12, color: 'var(--red)' }}
                                  disabled={hardDeleteBusy === u.user_id}
                                  onClick={() => void hardDeleteUser(u.user_id, u.email)}
                                >
                                  {hardDeleteBusy === u.user_id ? 'Deleting…' : 'Hard delete (TEST)'}
                                </button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                    {!users && <tr><td colSpan={6}>Loading…</td></tr>}
                    {users && users.length === 0 && <tr><td colSpan={6}>No members yet.</td></tr>}
                  </tbody>
                </table>
              </div>
              <p className='muted' style={{ fontSize: 12, marginTop: 12 }}>
                Generic clinic invite (no preset role):{' '}
                {signupUrl ? <code style={{ fontSize: 11 }}>{signupUrl}</code> : '—'}
              </p>
            </div>
          </div>

          {selectedUserId ? (
            <div className='card'>
              <div className='cardHead'>
                <h3>User activity</h3>
                <button type='button' className='btn soft' onClick={() => refreshUserActivity()} disabled={userActivityLoading}>
                  {userActivityLoading ? 'Loading…' : 'Refresh'}
                </button>
              </div>
              <div className='cardBody stack' style={{ gap: 14 }}>
                {userActivityLoading && !userActivity ? (
                  <p className='muted'>Loading activity…</p>
                ) : userActivity ? (
                  <>
                    <div className='list'>
                      <div className='listRow'><span>Email</span><strong>{userActivity.user?.email}</strong></div>
                      <div className='listRow'><span>Role</span><strong>{userActivity.user?.role || '—'}</strong></div>
                      <div className='listRow'><span>Linked</span><strong>{userActivity.user?.linked_at ? new Date(userActivity.user.linked_at).toLocaleString() : '—'}</strong></div>
                      <div className='listRow'><span>Account created</span><strong>{userActivity.user?.account_created_at ? new Date(userActivity.user.account_created_at).toLocaleString() : '—'}</strong></div>
                    </div>

                    <div>
                      <h4 style={{ margin: '0 0 8px', fontSize: 14 }}>Audit log ({userActivity.counts?.audit_events ?? 0})</h4>
                      {(userActivity.audit_events || []).length ? (
                        <div className='tableWrap'>
                          <table className='table'>
                            <thead><tr><th>Time</th><th>Action</th><th>Detail</th></tr></thead>
                            <tbody>
                              {userActivity.audit_events.map((ev) => (
                                <tr key={ev.id}>
                                  <td className='muted'>{ev.created_at ? new Date(ev.created_at).toLocaleString() : '—'}</td>
                                  <td>{ev.action}</td>
                                  <td>{ev.detail || '—'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className='muted' style={{ fontSize: 13 }}>No audit events recorded for this user yet.</p>
                      )}
                    </div>

                    <div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                        <h4 style={{ margin: 0, fontSize: 14, flex: '1 1 auto' }}>Service orders ({userActivity.counts?.service_orders ?? 0})</h4>
                        <input
                          type='search'
                          className='input'
                          placeholder='Search order ID, VB-CMP, reference, title…'
                          value={userOrdersSearch}
                          onChange={(e) => setUserOrdersSearch(e.target.value)}
                          style={{ minWidth: 220, maxWidth: 360 }}
                        />
                      </div>
                      {filteredUserOrders.length ? (
                        <div className='tableWrap'>
                          <table className='table'>
                            <thead>
                              <tr>
                                <th style={{ cursor: 'pointer' }} onClick={() => sortUserOrdersColumn('reference')}>Order ID</th>
                                <th style={{ cursor: 'pointer' }} onClick={() => sortUserOrdersColumn('title')}>Title</th>
                                <th style={{ cursor: 'pointer' }} onClick={() => sortUserOrdersColumn('service')}>Service</th>
                                <th style={{ cursor: 'pointer' }} onClick={() => sortUserOrdersColumn('format')}>Format</th>
                                <th style={{ cursor: 'pointer' }} onClick={() => sortUserOrdersColumn('status')}>Status</th>
                                <th style={{ cursor: 'pointer' }} onClick={() => sortUserOrdersColumn('quote')}>Quote</th>
                                <th style={{ cursor: 'pointer' }} onClick={() => sortUserOrdersColumn('updated')}>Updated</th>
                                <th>View</th>
                              </tr>
                            </thead>
                            <tbody>
                              {filteredUserOrders.map((o) => (
                                <tr key={o.id}>
                                  <td className='muted'><code>{o.reference_id || o.campaign_id || o.id?.slice(0, 8)}</code></td>
                                  <td>{o.title || '—'}</td>
                                  <td>{o.service_code}</td>
                                  <td>{o.service_code === 'interview' ? interviewFormatLabel(o) : '—'}</td>
                                  <td><span className='pill p-cyan'>{o.status}</span></td>
                                  <td>{o.quote_total_gbp || money(Number(o.quote_total_pence || 0))}</td>
                                  <td className='muted'>{o.updated_at ? new Date(o.updated_at).toLocaleString() : '—'}</td>
                                  <td><Link className='btn soft bsm' to={adminOrderViewPath(o)}>Open</Link></td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className='muted' style={{ fontSize: 13 }}>{userOrdersSearch.trim() ? 'No orders match your search.' : 'No surveys or interviews created by this user.'}</p>
                      )}
                    </div>

                    <div>
                      <h4 style={{ margin: '0 0 8px', fontSize: 14 }}>Support tickets ({userActivity.counts?.support_tickets ?? 0})</h4>
                      {(userActivity.support_tickets || []).length ? (
                        <div className='tableWrap'>
                          <table className='table'>
                            <thead><tr><th>Subject</th><th>Category</th><th>Status</th><th>Updated</th></tr></thead>
                            <tbody>
                              {userActivity.support_tickets.map((t) => (
                                <tr key={t.id}>
                                  <td>{t.subject}</td>
                                  <td>{t.category}</td>
                                  <td><span className='pill p-cyan'>{t.status}</span></td>
                                  <td className='muted'>{t.updated_at ? new Date(t.updated_at).toLocaleString() : '—'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className='muted' style={{ fontSize: 13 }}>No support tickets opened by this user.</p>
                      )}
                    </div>
                  </>
                ) : (
                  <p className='muted'>Could not load activity for this user.</p>
                )}
              </div>
            </div>
          ) : null}
        </div>
      )}

      {tab === 'plan' && (
        <div className='stack' style={{ display: 'grid', gap: 14, maxWidth: 560 }}>
          <div className='card'>
            <div className='cardHead'><h3>C.P plan</h3><span className='pill p-cyan'>Core Platform</span></div>
            <div className='cardBody stack' style={{ display: 'grid', gap: 14 }}>
              <p className='muted' style={{ fontSize: 13, margin: 0 }}>
                Current: <strong>{org?.core_plan_name || org?.core_plan_code || org?.plan_name || org?.plan_code || '—'}</strong> ({org?.core_subscription_status || org?.subscription_status || '—'})
              </p>
              {financePreview?.subscription_finance ? (
                <div className='list' style={{ fontSize: 13 }}>
                  <div className='listRow'><span>Next billing</span><strong>{financePreview.subscription_finance.next_billing_date ? new Date(financePreview.subscription_finance.next_billing_date).toLocaleDateString() : '—'}</strong></div>
                  <div className='listRow'><span>Next charge</span><strong>{financePreview.subscription_finance.amount_next_payment_display || '—'}</strong></div>
                  <div className='listRow'><span>Cancel at period end</span><strong>{financePreview.subscription_finance.cancel_at_period_end ? 'Yes' : 'No'}</strong></div>
                  <div className='listRow'><span>Unused value (est.)</span><strong>{financePreview.calculated_unused_value_display || '—'}</strong></div>
                </div>
              ) : null}
              <label style={{ display: 'grid', gap: 6 }}>
                <span className='muted' style={{ fontSize: 12 }}>C.P plan</span>
                <select className='select' value={planCode} onChange={(e) => setPlanCode(e.target.value)} disabled={!orgId}>
                  <option value=''>Choose plan…</option>
                  {(plans || []).map((p) => (
                    <option key={p.code} value={p.code}>{p.name} ({p.code})</option>
                  ))}
                </select>
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span className='muted' style={{ fontSize: 12 }}>Subscription status</span>
                <input className='input' value={subStatus} onChange={(e) => setSubStatus(e.target.value)} placeholder='active, trial…' disabled={!orgId} />
              </label>
              {upgradePreview ? (
                <div className='list' style={{ fontSize: 13, padding: 10, background: 'var(--surface2, #f8fafc)', borderRadius: 8 }}>
                  <div className='listRow'><span>Upgrade preview</span><strong>{upgradePreview.new_plan_name || upgradePreview.new_plan_code}</strong></div>
                  <div className='listRow'><span>Pro-rata charge</span><strong>{upgradePreview.pro_rata_display || money(upgradePreview.pro_rata_minor, upgradePreview.currency)}</strong></div>
                  <div className='listRow'><span>New monthly</span><strong>{upgradePreview.new_monthly_display || money(upgradePreview.new_monthly_minor, upgradePreview.currency)}</strong></div>
                </div>
              ) : null}
              <button className='btn primary' disabled={!orgId || planSaving || !planCode.trim()} onClick={savePlan}>
                {planSaving ? 'Applying…' : 'Apply C.P plan'}
              </button>
              <p className='muted' style={{ fontSize: 12, margin: 0 }}>
                Assigns the Core Platform subscription only. Does not change the F.B plan.
              </p>
            </div>
          </div>

          <div className='card'>
            <div className='cardHead'><h3>F.B plan</h3><span className='pill p-amber'>Customer Feedback</span></div>
            <div className='cardBody stack' style={{ display: 'grid', gap: 14 }}>
              <p className='muted' style={{ fontSize: 13, margin: 0 }}>
                Current: <strong>{org?.feedback_plan_name || org?.feedback_plan_code || 'None — assign below'}</strong>
                {org?.feedback_subscription_status ? ` (${org.feedback_subscription_status})` : ''}
              </p>
              {(org?.feedback_wa_units_included || org?.feedback_wa_units_used) ? (
                <div className='list' style={{ fontSize: 13 }}>
                  <div className='listRow'><span>WA included</span><strong>{org?.feedback_wa_units_included ?? 0}</strong></div>
                  <div className='listRow'><span>WA used</span><strong>{org?.feedback_wa_units_used ?? 0}</strong></div>
                  <div className='listRow'><span>WA remaining</span><strong>{org?.feedback_wa_units_remaining ?? 0}</strong></div>
                </div>
              ) : null}
              <label style={{ display: 'grid', gap: 6 }}>
                <span className='muted' style={{ fontSize: 12 }}>F.B plan</span>
                <select className='select' value={feedbackPlanCode} onChange={(e) => setFeedbackPlanCode(e.target.value)} disabled={!orgId}>
                  <option value=''>Choose plan…</option>
                  {(feedbackPlans || []).map((p) => (
                    <option key={p.id || p.code} value={p.code}>{p.name} ({p.code})</option>
                  ))}
                </select>
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span className='muted' style={{ fontSize: 12 }}>Subscription status</span>
                <input className='input' value={feedbackSubStatus} onChange={(e) => setFeedbackSubStatus(e.target.value)} placeholder='active, trial…' disabled={!orgId} />
              </label>
              <button className='btn primary' disabled={!orgId || feedbackPlanSaving || !feedbackPlanCode.trim()} onClick={saveFeedbackPlan}>
                {feedbackPlanSaving ? 'Applying…' : 'Apply F.B plan'}
              </button>
              <p className='muted' style={{ fontSize: 12, margin: 0 }}>
                Customer Feedback billing is separate from C.P. An org can have both plans at once.
              </p>
            </div>
          </div>

          <div className='card'>
            <div className='cardHead'><h3>Wallet & finance</h3></div>
            <div className='cardBody stack' style={{ display: 'grid', gap: 14 }}>
              <p className='muted' style={{ fontSize: 13, margin: 0 }}>
                Balance: <strong>{org?.wallet_balance_display || org?.wallet_balance_gbp || money(0, org?.billing_currency)}</strong> — ledger-backed credits only.
              </p>
              <label style={{ display: 'grid', gap: 6 }}>
                <span className='muted' style={{ fontSize: 12 }}>Add credit ({org?.billing_currency || 'GBP'})</span>
                <input
                  className='input'
                  type='number'
                  min='1'
                  step='1'
                  value={walletCreditGbp}
                  onChange={(e) => setWalletCreditGbp(e.target.value)}
                  disabled={!orgId || walletBusy}
                />
              </label>
              <button className='btn soft' disabled={!orgId || walletBusy} onClick={creditWallet}>
                {walletBusy ? 'Crediting…' : 'Add wallet credit'}
              </button>
              <Link className='btn soft' to='/billing/wallet-ledger'>Global wallet ledger</Link>
              <Link className='btn soft' to='/organisations/all-users' onClick={() => localStorage.setItem('voxbulk_admin_selected_org_id', orgId)}>Open finance console</Link>
            </div>
          </div>

          <div className='card'>
            <div className='cardHead'><h3>Finance notes</h3></div>
            <div className='cardBody stack' style={{ display: 'grid', gap: 10 }}>
              <textarea className='input' rows={4} value={financeNote} onChange={(e) => setFinanceNote(e.target.value)} disabled={!orgId} placeholder='Internal finance/admin notes…' />
              <button className='btn soft' disabled={!orgId || financeBusy} onClick={async () => {
                setFinanceBusy(true)
                try {
                  await apiFetch(`/admin/organisations/${orgId}`, { method: 'PATCH', body: JSON.stringify({ finance_notes: financeNote.trim() || null }) })
                  await refreshOrg()
                } catch (e) {
                  window.alert(e?.message || 'Could not save notes')
                } finally {
                  setFinanceBusy(false)
                }
              }}>{financeBusy ? 'Saving…' : 'Save notes'}</button>
            </div>
          </div>
        </div>
      )}

      {tab === 'suspend' && (
        <div className='card' style={{ maxWidth: 560 }}>
          <div className='cardHead'><h3>Organisation suspension</h3></div>
          <div className='cardBody stack' style={{ display: 'grid', gap: 14 }}>
            <p className='muted' style={{ fontSize: 13, margin: 0 }}>
              When suspended, non–platform users cannot obtain a bearer token for this tenant. Superusers retain access for support.
            </p>
            <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
              <input
                type='checkbox'
                checked={Boolean(org?.is_suspended)}
                disabled={!org || suspendSaving}
                onChange={(e) => saveSuspended(e.target.checked)}
              />
              <span>Suspended</span>
            </label>
            {suspendSaving && <span className='muted'>Updating…</span>}
          </div>
        </div>
      )}
    </>
  )
}
