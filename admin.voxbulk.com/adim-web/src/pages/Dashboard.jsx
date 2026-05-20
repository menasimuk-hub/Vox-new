import React, { useEffect, useMemo, useState } from 'react'
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid, BarChart, Bar } from 'recharts'
import { DollarSign, Building2, BadgeCheck, BrainCircuit, PhoneCall, CalendarCheck2, AlertTriangle, Activity, Wallet, Mic2 } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { normalizeAdminRole } from '../lib/adminPaths'
import { useAdminProfile } from '../context/AdminProfileContext'

const n = (value) => Number(value || 0).toLocaleString()
const money = (amount, currency = 'USD') => {
  const value = Number(amount)
  if (!Number.isFinite(value)) return '—'
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: currency || 'USD' }).format(value)
  } catch {
    return `${currency || 'USD'} ${value.toFixed(2)}`
  }
}
const shortDate = (value) => {
  if (!value) return 'No records yet'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}
const S=({label,value,delta,accent,icon:Icon,cls})=><div className='card stat' style={{'--accent':accent}}><div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}><div style={{width:44,height:44,borderRadius:14,display:'grid',placeItems:'center',background:'var(--surface-2)'}}><Icon size={18}/></div><span className={`pill ${cls}`}>{delta}</span></div><div className='statValue'>{value}</div><div className='muted'>{label}</div></div>

export default function Dashboard(){
  const [health, setHealth] = useState(null)
  const [providerBalances, setProviderBalances] = useState({ loading: true, telnyx: null, elevenlabs: null })
  const [overview, setOverview] = useState({ loading: true, error: '', billing: null, operations: null, support: null, orgs: [], pending: [] })
  const { adminRole } = useAdminProfile()

  useEffect(() => {
    let cancelled = false
    async function runHealth(){
      if (normalizeAdminRole(adminRole) !== 'superadmin') {
        if (!cancelled) setHealth({})
        return
      }
      const providers = ['dentally','telnyx','azure_speech','openai','vapi','gocardless']
      const next = {}
      await Promise.all(providers.map(async (p) => {
        try {
          next[p] = await apiFetch(`/admin/integrations/${p}`)
        } catch {
          next[p] = { error: true }
        }
      }))
      if (!cancelled) setHealth(next)
    }
    runHealth()
    return () => { cancelled = true }
  }, [adminRole])

  useEffect(() => {
    let cancelled = false
    async function runOverview(){
      setOverview((s) => ({ ...s, loading: true, error: '' }))
      const [billing, operations, support, orgs, pending] = await Promise.all([
        apiFetch('/admin/billing/overview').catch((e) => ({ error: e?.message || 'Unavailable' })),
        apiFetch('/admin/operations/overview').catch((e) => ({ error: e?.message || 'Unavailable' })),
        apiFetch('/admin/support/kpis').catch((e) => ({ error: e?.message || 'Unavailable' })),
        apiFetch('/admin/organisations?limit=200').catch(() => []),
        apiFetch('/admin/onboarding/requests?status_filter=pending').catch(() => []),
      ])
      if (!cancelled) {
        setOverview({ loading: false, error: '', billing, operations, support, orgs: Array.isArray(orgs) ? orgs : [], pending: Array.isArray(pending) ? pending : [] })
      }
    }
    runOverview().catch((e) => {
      if (!cancelled) setOverview({ loading: false, error: e?.message || 'Could not load admin overview', billing: null, operations: null, support: null, orgs: [], pending: [] })
    })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function runBalances(){
      setProviderBalances((s) => ({ ...s, loading: true }))
      try {
        const data = await apiFetch('/admin/dashboard/provider-balances')
        if (!cancelled) {
          setProviderBalances({
            loading: false,
            telnyx: data?.telnyx || null,
            elevenlabs: data?.elevenlabs || null,
          })
        }
      } catch (e) {
        if (!cancelled) {
          setProviderBalances({
            loading: false,
            telnyx: { ok: false, message: e?.message || 'Could not load Telnyx balance' },
            elevenlabs: { ok: false, message: e?.message || 'Could not load ElevenLabs balance' },
          })
        }
      }
    }
    runBalances()
    return () => { cancelled = true }
  }, [])

  const healthRow = (label, key) => {
    const s = health?.[key]
    if (normalizeAdminRole(adminRole) !== 'superadmin') return [label, 'Hidden for your role']
    if (!s) return [label, 'Loading']
    if (s.error) return [label, 'Auth / error']
    if (!s.exists) return [label, 'Not set']
    if (!s.is_enabled) return [label, 'Disabled']
    return [label, s.configured ? 'Configured' : 'Incomplete']
  }

  const billing = overview.billing || {}
  const operations = overview.operations || {}
  const support = overview.support || {}
  const recovery = operations.recovery_jobs || {}
  const webhooks = operations.webhooks || {}
  const orgs = overview.orgs || []
  const pending = overview.pending || []
  const activeOrgs = orgs.filter((o) => !o.is_suspended).length
  const workflowRows = useMemo(() => [
    { n: 'Queued jobs', v: recovery.queued || 0 },
    { n: 'Calling', v: recovery.calling || 0 },
    { n: 'Messaged', v: recovery.messaged || 0 },
    { n: 'Recovered', v: recovery.recovered || 0 },
    { n: 'Failed', v: recovery.failed || 0 },
  ], [recovery.queued, recovery.calling, recovery.messaged, recovery.recovered, recovery.failed])
  const activityRows = useMemo(() => [
    { m: 'Organisations', v: orgs.length },
    { m: 'Subscriptions', v: billing.subscriptions_total || 0 },
    { m: 'Recovery jobs', v: recovery.total_recent || 0 },
    { m: 'Webhooks', v: webhooks.total_recent || 0 },
    { m: 'Tickets open', v: support.open || support.total_open || 0 },
  ], [orgs.length, billing.subscriptions_total, recovery.total_recent, webhooks.total_recent, support.open, support.total_open])
  const attention = [
    ['Failed recovery jobs', `${n(recovery.failed)} in recent window`],
    ['Failed webhooks', `${n(webhooks.failed)} in recent window`],
    ['Past-due subscriptions', `${n(billing.subscriptions_past_due)} subscriptions`],
    ['Pending signups', `${n(pending.length)} awaiting review`],
  ]

  const telnyxBalance = providerBalances.telnyx
  const elevenBalance = providerBalances.elevenlabs
  const telnyxValue = providerBalances.loading
    ? '…'
    : telnyxBalance?.ok
      ? money(telnyxBalance.amount, telnyxBalance.currency)
      : telnyxBalance?.configured === false
        ? 'Not configured'
        : 'Unavailable'
  const telnyxDelta = providerBalances.loading
    ? 'Loading'
    : telnyxBalance?.ok
      ? telnyxBalance.pending > 0
        ? `${money(telnyxBalance.pending, telnyxBalance.currency)} pending`
        : 'Available credit'
      : telnyxBalance?.message || 'Check Integrations'
  const elevenValue = providerBalances.loading
    ? '…'
    : elevenBalance?.ok
      ? n(elevenBalance.characters_remaining)
      : elevenBalance?.configured === false
        ? 'Not configured'
        : 'Unavailable'
  const elevenDelta = providerBalances.loading
    ? 'Loading'
    : elevenBalance?.ok
      ? `${n(elevenBalance.character_count)} / ${n(elevenBalance.character_limit)} used · ${elevenBalance.tier}`
      : (elevenBalance?.message || 'Check Integrations').includes('user_read')
        ? 'Enable user_read on API key'
        : elevenBalance?.message || 'Check Integrations'

  return <><div className='pageTop'><div><h1>Dashboard</h1><p>Live admin overview from VOXBULK backend data. Empty values mean no records exist yet.</p></div><div className='actions'><button className='btn soft' disabled>{overview.loading ? 'Loading…' : 'Live DB data'}</button><button className='btn primary' onClick={() => { window.location.href = '/organisations' }}>Create organisation</button></div></div>{overview.error ? <div className='note' style={{marginBottom:16}}>{overview.error}</div> : null}<div className='grid-4' style={{marginBottom:16}}><S label='Organisations loaded' value={n(orgs.length)} delta={`${n(activeOrgs)} active`} accent='#0891b2' icon={Building2} cls='p-cyan'/><S label='Active subscriptions' value={n(billing.subscriptions_active)} delta={`${n(billing.subscriptions_trial)} trial`} accent='#0f766e' icon={DollarSign} cls='p-green'/><S label='Open support tickets' value={n(support.open || support.total_open || 0)} delta={`${n(support.pending || support.total_pending || 0)} pending`} accent='#7c3aed' icon={BadgeCheck} cls='p-violet'/><S label='Failed operations' value={n((recovery.failed || 0) + (webhooks.failed || 0))} delta='Recent window' accent='#d97706' icon={BrainCircuit} cls='p-amber'/></div><div className='grid-4' style={{marginBottom:16}}><S label='Telnyx balance' value={telnyxValue} delta={telnyxDelta} accent='#14b8a6' icon={Wallet} cls='p-green'/><S label='ElevenLabs characters left' value={elevenValue} delta={elevenDelta} accent='#6366f1' icon={Mic2} cls='p-violet'/></div><div className='grid-12'><div className='span-8 stack'><div className='heroPanel'><div style={{display:'flex',justifyContent:'space-between',gap:14,alignItems:'start'}}><div><h2>Admin console now shows live backend totals</h2><p>These cards use organisation, billing, support, operations, and integration endpoints already present in FastAPI. No fake MRR or demo organisation names are shown.</p></div><div className='metricRing'><CalendarCheck2 size={24}/></div></div></div><div className='card'><div className='cardHead'><h3>Live activity snapshot</h3><span className='pill p-cyan'>DB-backed</span></div><div className='cardBody' style={{height:290}}><ResponsiveContainer width='100%' height='100%'><AreaChart data={activityRows}><defs><linearGradient id='mrr' x1='0' y1='0' x2='0' y2='1'><stop offset='5%' stopColor='#0f766e' stopOpacity='0.35'/><stop offset='95%' stopColor='#0f766e' stopOpacity='0.03'/></linearGradient></defs><CartesianGrid stroke='var(--line)' strokeDasharray='3 3'/><XAxis dataKey='m' tick={{fill:'var(--muted)',fontSize:12}}/><YAxis tick={{fill:'var(--muted)',fontSize:12}} allowDecimals={false}/><Tooltip/><Area type='monotone' dataKey='v' stroke='#0f766e' fill='url(#mrr)' strokeWidth={3}/></AreaChart></ResponsiveContainer></div></div></div><div className='span-4 stack'><div className='card'><div className='cardHead'><h3>System health</h3><span className='pill p-cyan'>Live</span></div><div className='cardBody'><div className='list'>{[
    healthRow('Dentally','dentally'),
    healthRow('Telnyx voice','telnyx'),
    healthRow('Azure Speech','azure_speech'),
    healthRow('OpenAI','openai'),
    healthRow('Vapi legacy','vapi'),
    healthRow('GoCardless','gocardless'),
    ['Social login', normalizeAdminRole(adminRole) === 'superadmin' ? 'Use Integrations → Social login' : 'Hidden for your role']
  ].map(([a,b],i)=><div className='listRow' key={i}><span>{a}</span><strong>{b}</strong></div>)}</div></div></div><div className='card'><div className='cardHead'><h3>Needs attention</h3><span className='pill p-red'>Live</span></div><div className='cardBody'><div className='timeline'>{attention.map(([t,d],i)=><div className='timelineItem' key={i}><div className='timelineIcon'>{i === 0 ? <PhoneCall size={16}/> : i === 1 ? <AlertTriangle size={16}/> : <Activity size={16}/>}</div><div><div style={{fontWeight:700,fontSize:14}}>{t}</div><div className='muted' style={{fontSize:13}}>{d}</div></div></div>)}</div></div></div></div><div className='card span-7'><div className='cardHead'><h3>Recovery workflow volume</h3><span className='pill p-cyan'>Recent jobs</span></div><div className='cardBody' style={{height:290}}><ResponsiveContainer width='100%' height='100%'><BarChart data={workflowRows}><CartesianGrid stroke='var(--line)' strokeDasharray='3 3'/><XAxis dataKey='n' tick={{fill:'var(--muted)',fontSize:12}}/><YAxis tick={{fill:'var(--muted)',fontSize:12}} allowDecimals={false}/><Tooltip/><Bar dataKey='v' fill='#0f766e' radius={[10,10,0,0]}/></BarChart></ResponsiveContainer></div></div><div className='card span-5'><div className='cardHead'><h3>Latest live records</h3><span className='pill p-amber'>No demo data</span></div><div className='cardBody'><div className='list'><div className='listRow'><span>Latest subscription</span><strong>{shortDate(billing.latest_subscription_created_at)}</strong></div><div className='listRow'><span>Latest recovery job</span><strong>{shortDate(recovery.latest_created_at)}</strong></div><div className='listRow'><span>Latest webhook</span><strong>{shortDate(webhooks.latest_received_at)}</strong></div><div className='listRow'><span>Pending onboarding</span><strong>{n(pending.length)}</strong></div></div></div></div></div></>}
