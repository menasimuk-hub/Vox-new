import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  Activity,
  Building2,
  CheckCircle2,
  CreditCard,
  Gauge,
  Layers,
  MapPin,
  MessageCircle,
  MessageSquare,
  Package,
  QrCode,
  RefreshCw,
} from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { cn } from '@/lib/utils'
import { Panel } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Label } from '@/components/ui/Label'
import { Pill } from '@/components/ui/Badge'
import { Switch } from '@/components/ui/Switch'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'industries', label: 'Industries' },
  { key: 'survey-types', label: 'Survey types' },
  { key: 'packages', label: 'Packages' },
  { key: 'subscriptions', label: 'Subscriptions' },
  { key: 'locations', label: 'Locations' },
  { key: 'results', label: 'Results' },
  { key: 'wa-templates', label: 'WhatsApp templates' },
]

// Overview pinned first; the rest sorted alphabetically.
const SORTED_TABS = [
  TABS[0],
  ...TABS.slice(1).sort((a, b) => a.label.localeCompare(b.label)),
]

const PACKAGE_ZONES = ['gb', 'eu', 'us', 'ca', 'au']

const ZONE_LABELS = { gb: 'GB', eu: 'EU', us: 'US', ca: 'CA', au: 'AU' }

const NATIVE_SELECT_CLS =
  'flex h-8 w-full items-center rounded-md border border-input bg-transparent px-2 text-[12px] shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50'

function fmtWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

function moneyMinor(minor, currency = 'GBP') {
  const amount = Number(minor || 0) / 100
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(amount)
  } catch {
    return `${currency} ${amount.toFixed(2)}`
  }
}

// Kept for the (untouched) Packages tab.
function statusPill(active) {
  return active ? 'leadPill leadPillAdvance' : 'leadPill leadPillNeutral'
}

// Kept for the (untouched) Packages tab.
function EditPanel({ title, onClose, onSave, saving, children }) {
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="cardHead">
        <h3>{title}</h3>
        <button type="button" className="btn soft bsm" onClick={onClose}>Close</button>
      </div>
      <div className="cardBody">
        {children}
        <div className="runningSurveyActionBar" style={{ marginTop: 14 }}>
          <button type="button" className="btn primary bsm" disabled={saving} onClick={onSave}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="btn soft bsm" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

// Kept for the (untouched) Packages tab.
function Field({ label, children }) {
  return (
    <label style={{ display: 'grid', gap: 6 }}>
      <span className="muted" style={{ fontSize: 12 }}>{label}</span>
      {children}
    </label>
  )
}

function DsField({ label, children, className }) {
  return (
    <div className={cn('space-y-1', className)}>
      <Label className="text-[12px]">{label}</Label>
      {children}
    </div>
  )
}

function ActiveCheck({ checked, onChange }) {
  return (
    <div className="flex items-center gap-2 text-[12px]">
      <Switch checked={checked} onCheckedChange={(v) => onChange({ target: { checked: v } })} />
      <span className="text-muted-foreground">{checked ? 'Active' : 'Inactive'}</span>
    </div>
  )
}

function DsEditPanel({ title, onClose, onSave, saving, children }) {
  return (
    <div className="mb-3 rounded-md border border-border bg-surface-muted/50 p-2.5">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</h4>
        <Button type="button" variant="ghost" size="sm" className="h-6 px-2 text-[11px]" onClick={onClose}>
          Close
        </Button>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
      <div className="mt-2.5 flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" className="h-7 px-3 text-[11px]" onClick={onClose}>
          Cancel
        </Button>
        <Button type="button" size="sm" className="h-7 px-3 text-[11px]" disabled={saving} onClick={onSave}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </div>
  )
}

const KPI_TONES = {
  primary: 'bg-primary/10 text-primary',
  info: 'bg-info-soft text-info',
  success: 'bg-success-soft text-success',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-destructive/10 text-destructive',
}

function useCountUp(target, duration = 900) {
  const [value, setValue] = useState(0)
  useEffect(() => {
    const to = Number(target) || 0
    let raf
    const start = performance.now()
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      setValue(Math.round(to * eased))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])
  return value
}

function KpiCard({ icon: Icon, label, value, tone = 'primary', index = 0 }) {
  const numeric = value !== null && value !== undefined && value !== '—' && Number.isFinite(Number(value))
  const counted = useCountUp(numeric ? Number(value) : 0)
  const display = numeric ? counted.toLocaleString() : value ?? '—'
  return (
    <div
      className="animate-in fade-in slide-in-from-bottom-2 rounded-lg border border-border bg-card p-4 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md"
      style={{ animationDuration: '500ms', animationDelay: `${index * 60}ms`, animationFillMode: 'both' }}
    >
      <span className={cn('flex size-9 items-center justify-center rounded-md', KPI_TONES[tone])}>
        <Icon size={18} />
      </span>
      <div className="mt-3 text-2xl font-semibold leading-none tabular-nums">{display}</div>
      <div className="mt-1 text-[12px] text-muted-foreground">{label}</div>
    </div>
  )
}

export default function CustomerFeedbackHub() {
  const { tab: tabParam } = useParams()
  const navigate = useNavigate()
  const tab = TABS.some((t) => t.key === tabParam) ? tabParam : 'industries'

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [overview, setOverview] = useState(null)

  const [industries, setIndustries] = useState([])
  const [surveyTypes, setSurveyTypes] = useState([])
  const [packages, setPackages] = useState([])
  const [feedbackPlans, setFeedbackPlans] = useState([])
  const [packageZone, setPackageZone] = useState('gb')
  const [subscriptions, setSubscriptions] = useState([])
  const [locations, setLocations] = useState([])
  const [results, setResults] = useState([])
  const [waTemplates, setWaTemplates] = useState([])

  const [industryEdit, setIndustryEdit] = useState(null)
  const [surveyTypeEdit, setSurveyTypeEdit] = useState(null)
  const [packageEdit, setPackageEdit] = useState(null)
  const [waTemplateEdit, setWaTemplateEdit] = useState(null)

  const setTab = (next) => {
    navigate(`/customer-feedback/${next}`)
  }

  const loadOverview = useCallback(async () => {
    const data = await apiFetch('/admin/customer-feedback/overview')
    setOverview(data || null)
  }, [])

  const loadTab = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      if (tab === 'overview') {
        const [subs, locs, res, types, tpls] = await Promise.all([
          apiFetch('/admin/customer-feedback/subscriptions'),
          apiFetch('/admin/customer-feedback/locations'),
          apiFetch('/admin/customer-feedback/results'),
          apiFetch('/admin/customer-feedback/survey-types'),
          apiFetch('/admin/customer-feedback/wa-templates'),
        ])
        setSubscriptions(subs?.items || [])
        setLocations(locs?.items || [])
        setResults(res?.rows || [])
        setSurveyTypes(types?.items || [])
        setWaTemplates(tpls?.items || [])
      } else if (tab === 'industries') {
        const data = await apiFetch('/admin/customer-feedback/industries')
        setIndustries(data?.items || [])
      } else if (tab === 'survey-types') {
        const data = await apiFetch('/admin/customer-feedback/survey-types')
        setSurveyTypes(data?.items || [])
        const ind = await apiFetch('/admin/customer-feedback/industries')
        setIndustries(ind?.items || [])
      } else if (tab === 'packages') {
        const [data, plans] = await Promise.all([
          apiFetch(`/admin/customer-feedback/packages?market_zone=${encodeURIComponent(packageZone)}`),
          apiFetch(`/admin/customer-feedback/plans?market_zone=${encodeURIComponent(packageZone)}`),
        ])
        setPackages(data?.items || [])
        setFeedbackPlans(plans?.items || [])
      } else if (tab === 'subscriptions') {
        const data = await apiFetch('/admin/customer-feedback/subscriptions')
        setSubscriptions(data?.items || [])
      } else if (tab === 'locations') {
        const data = await apiFetch('/admin/customer-feedback/locations')
        setLocations(data?.items || [])
      } else if (tab === 'results') {
        const data = await apiFetch('/admin/customer-feedback/results')
        setResults(data?.rows || [])
      } else if (tab === 'wa-templates') {
        const [tpl, ind, types] = await Promise.all([
          apiFetch('/admin/customer-feedback/wa-templates'),
          apiFetch('/admin/customer-feedback/industries'),
          apiFetch('/admin/customer-feedback/survey-types'),
        ])
        setWaTemplates(tpl?.items || [])
        setIndustries(ind?.items || [])
        setSurveyTypes(types?.items || [])
      }
    } catch (e) {
      setError(e?.message || 'Could not load data')
    } finally {
      setLoading(false)
    }
  }, [tab, packageZone])

  const refreshAll = useCallback(async () => {
    setError('')
    try {
      await loadOverview()
      await loadTab()
    } catch (e) {
      setError(e?.message || 'Refresh failed')
    }
  }, [loadOverview, loadTab])

  useEffect(() => {
    loadOverview().catch(() => {})
  }, [loadOverview])

  useEffect(() => {
    loadTab()
  }, [loadTab])

  const industryName = useMemo(() => {
    const map = Object.fromEntries(industries.map((i) => [i.id, i.name]))
    return (id) => map[id] || id || '—'
  }, [industries])

  const saveIndustry = async () => {
    if (!industryEdit) return
    setBusy(true)
    setError('')
    try {
      await apiFetch('/admin/customer-feedback/industries', {
        method: 'POST',
        body: JSON.stringify(industryEdit),
      })
      setIndustryEdit(null)
      await loadTab()
      await loadOverview()
    } catch (e) {
      setError(e?.message || 'Could not save industry')
    } finally {
      setBusy(false)
    }
  }

  const saveSurveyType = async () => {
    if (!surveyTypeEdit) return
    setBusy(true)
    setError('')
    try {
      await apiFetch('/admin/customer-feedback/survey-types', {
        method: 'POST',
        body: JSON.stringify(surveyTypeEdit),
      })
      setSurveyTypeEdit(null)
      await loadTab()
    } catch (e) {
      setError(e?.message || 'Could not save survey type')
    } finally {
      setBusy(false)
    }
  }

  const savePackage = async () => {
    if (!packageEdit) return
    setBusy(true)
    setError('')
    try {
      await apiFetch('/admin/customer-feedback/packages', {
        method: 'POST',
        body: JSON.stringify({ ...packageEdit, market_zone: packageZone }),
      })
      setPackageEdit(null)
      await loadTab()
      await loadOverview()
    } catch (e) {
      setError(e?.message || 'Could not save package')
    } finally {
      setBusy(false)
    }
  }

  const saveWaTemplate = async () => {
    if (!waTemplateEdit) return
    setBusy(true)
    setError('')
    try {
      await apiFetch('/admin/customer-feedback/wa-templates', {
        method: 'POST',
        body: JSON.stringify(waTemplateEdit),
      })
      setWaTemplateEdit(null)
      await loadTab()
    } catch (e) {
      setError(e?.message || 'Could not save template')
    } finally {
      setBusy(false)
    }
  }

  const overviewCards = [
    { label: 'Industries', value: overview?.industries ?? '—' },
    { label: 'Packages', value: overview?.packages ?? '—' },
    { label: 'Active tab', value: TABS.find((t) => t.key === tab)?.label || tab },
  ]

  const activeLabel = TABS.find((t) => t.key === tab)?.label || tab

  const kpis = useMemo(() => {
    const sum = (rows, key) => rows.reduce((acc, r) => acc + (Number(r?.[key]) || 0), 0)
    const activeSubs = subscriptions.filter((s) => String(s.status || '').toLowerCase() === 'active').length
    return [
      { label: 'Industries', value: overview?.industries ?? 0, icon: Building2, tone: 'primary' },
      { label: 'Survey types', value: surveyTypes.length, icon: Layers, tone: 'info' },
      { label: 'Packages', value: overview?.packages ?? 0, icon: Package, tone: 'warning' },
      { label: 'Subscriptions', value: subscriptions.length, icon: CreditCard, tone: 'success' },
      { label: 'Active subscriptions', value: activeSubs, icon: CheckCircle2, tone: 'success' },
      { label: 'Locations', value: locations.length, icon: MapPin, tone: 'info' },
      { label: 'Total scans', value: sum(locations, 'scan_count'), icon: QrCode, tone: 'primary' },
      { label: 'WA units used', value: sum(subscriptions, 'wa_units_used'), icon: Activity, tone: 'warning' },
      { label: 'WA units remaining', value: sum(subscriptions, 'wa_units_remaining'), icon: Gauge, tone: 'success' },
      { label: 'Responses', value: results.length, icon: MessageSquare, tone: 'info' },
    ]
  }, [overview, surveyTypes, subscriptions, locations, results])

  return (
    <div className="ds-scope space-y-4">
      <div className="pageTop">
        <div>
          <h1>Customer feedback</h1>
          <p>
            Manage feedback industries, survey types, zone packages, subscriptions, locations, results, and WhatsApp
            templates. Enable the module per org under{' '}
            <Link to="/onboarding/services" style={{ color: 'var(--grn)' }}>Onboarding → Customer services</Link>.
          </p>
        </div>
        <div className="actions">
          <Button type="button" variant="outline" size="sm" className="h-8" onClick={refreshAll} disabled={loading}>
            <RefreshCw size={14} />
            Refresh
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {tab !== 'overview' ? (
        <div className="grid gap-3 sm:grid-cols-3">
          {overviewCards.map((c) => (
            <Panel key={c.label} bodyClassName="py-3">
              <div className="text-2xl font-semibold leading-none">{c.value}</div>
              <div className="mt-1 text-[12px] text-muted-foreground">{c.label}</div>
            </Panel>
          ))}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5 text-[12px] font-semibold text-muted-foreground">
          <MessageCircle size={15} /> Customer feedback admin
        </span>
        <div className="flex flex-wrap gap-0.5 rounded-lg border border-border bg-card p-1">
          {SORTED_TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                'h-7 rounded-md px-3 text-[12px] font-medium transition-colors',
                tab === t.key
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? <div className="text-[12px] text-muted-foreground">Loading…</div> : null}

      {!loading && tab === 'overview' ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {kpis.map((k, i) => (
            <KpiCard key={k.label} icon={k.icon} label={k.label} value={k.value} tone={k.tone} index={i} />
          ))}
        </div>
      ) : null}

      {!loading && tab === 'industries' ? (
        <Panel
          title="Industries"
          subtitle="Feedback industries shown to customers."
          action={
            <Button
              type="button"
              size="sm"
              className="h-8"
              onClick={() => setIndustryEdit({ name: '', slug: '', description: '', is_active: true, sort_order: 100 })}
            >
              Add industry
            </Button>
          }
        >
          {industryEdit ? (
            <DsEditPanel title={industryEdit.id ? 'Edit industry' : 'New industry'} onClose={() => setIndustryEdit(null)} onSave={saveIndustry} saving={busy}>
              <DsField label="Name">
                <Input className="h-8" value={industryEdit.name || ''} onChange={(e) => setIndustryEdit((f) => ({ ...f, name: e.target.value }))} />
              </DsField>
              <DsField label="Slug">
                <Input className="h-8" value={industryEdit.slug || ''} onChange={(e) => setIndustryEdit((f) => ({ ...f, slug: e.target.value }))} />
              </DsField>
              <DsField label="Sort order">
                <Input className="h-8" type="number" value={industryEdit.sort_order ?? 100} onChange={(e) => setIndustryEdit((f) => ({ ...f, sort_order: Number(e.target.value) }))} />
              </DsField>
              <DsField label="Description" className="sm:col-span-2">
                <Input className="h-8" value={industryEdit.description || ''} onChange={(e) => setIndustryEdit((f) => ({ ...f, description: e.target.value }))} />
              </DsField>
              <DsField label="Active">
                <ActiveCheck checked={Boolean(industryEdit.is_active)} onChange={(e) => setIndustryEdit((f) => ({ ...f, is_active: e.target.checked }))} />
              </DsField>
            </DsEditPanel>
          ) : null}
          <StripeTable>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Slug</TableHead>
                <TableHead>Order</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {industries.map((row) => (
                <TableRow key={row.id}>
                  <TableCell><strong className="font-medium">{row.name}</strong></TableCell>
                  <TableCell><code className="text-[11px]">{row.slug}</code></TableCell>
                  <TableCell>{row.sort_order}</TableCell>
                  <TableCell><Pill tone={row.is_active ? 'success' : 'neutral'}>{row.is_active ? 'Active' : 'Inactive'}</Pill></TableCell>
                  <TableCell className="text-right">
                    <Button type="button" variant="outline" size="sm" className="h-7" onClick={() => setIndustryEdit({ ...row })}>Edit</Button>
                  </TableCell>
                </TableRow>
              ))}
              {!industries.length ? <TableEmpty colSpan={5}>No industries yet.</TableEmpty> : null}
            </TableBody>
          </StripeTable>
        </Panel>
      ) : null}

      {!loading && tab === 'survey-types' ? (
        <Panel
          title="Survey types"
          subtitle="Survey types grouped under each industry."
          action={
            <Button
              type="button"
              size="sm"
              className="h-8"
              disabled={!industries.length}
              onClick={() =>
                setSurveyTypeEdit({
                  industry_id: industries[0]?.id || '',
                  name: '',
                  slug: '',
                  description: '',
                  is_active: true,
                  sort_order: 100,
                })
              }
            >
              Add survey type
            </Button>
          }
        >
          {surveyTypeEdit ? (
            <DsEditPanel title={surveyTypeEdit.id ? 'Edit survey type' : 'New survey type'} onClose={() => setSurveyTypeEdit(null)} onSave={saveSurveyType} saving={busy}>
              <DsField label="Industry">
                <select className={NATIVE_SELECT_CLS} value={surveyTypeEdit.industry_id || ''} onChange={(e) => setSurveyTypeEdit((f) => ({ ...f, industry_id: e.target.value }))}>
                  {industries.map((i) => (
                    <option key={i.id} value={i.id}>{i.name}</option>
                  ))}
                </select>
              </DsField>
              <DsField label="Name">
                <Input className="h-8" value={surveyTypeEdit.name || ''} onChange={(e) => setSurveyTypeEdit((f) => ({ ...f, name: e.target.value }))} />
              </DsField>
              <DsField label="Slug">
                <Input className="h-8" value={surveyTypeEdit.slug || ''} onChange={(e) => setSurveyTypeEdit((f) => ({ ...f, slug: e.target.value }))} />
              </DsField>
              <DsField label="Sort order">
                <Input className="h-8" type="number" value={surveyTypeEdit.sort_order ?? 100} onChange={(e) => setSurveyTypeEdit((f) => ({ ...f, sort_order: Number(e.target.value) }))} />
              </DsField>
              <DsField label="Description" className="sm:col-span-2">
                <Input className="h-8" value={surveyTypeEdit.description || ''} onChange={(e) => setSurveyTypeEdit((f) => ({ ...f, description: e.target.value }))} />
              </DsField>
              <DsField label="Active">
                <ActiveCheck checked={Boolean(surveyTypeEdit.is_active)} onChange={(e) => setSurveyTypeEdit((f) => ({ ...f, is_active: e.target.checked }))} />
              </DsField>
            </DsEditPanel>
          ) : null}
          <StripeTable>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Industry</TableHead>
                <TableHead>Slug</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {surveyTypes.map((row) => (
                <TableRow key={row.id}>
                  <TableCell><strong className="font-medium">{row.name}</strong></TableCell>
                  <TableCell className="text-muted-foreground">{industryName(row.industry_id)}</TableCell>
                  <TableCell><code className="text-[11px]">{row.slug}</code></TableCell>
                  <TableCell>
                    <Pill tone={row.archived_at ? 'neutral' : row.is_active ? 'success' : 'neutral'}>
                      {row.archived_at ? 'Archived' : row.is_active ? 'Active' : 'Inactive'}
                    </Pill>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button type="button" variant="outline" size="sm" className="h-7" onClick={() => setSurveyTypeEdit({ ...row })}>Edit</Button>
                  </TableCell>
                </TableRow>
              ))}
              {!surveyTypes.length ? <TableEmpty colSpan={5}>No survey types yet.</TableEmpty> : null}
            </TableBody>
          </StripeTable>
        </Panel>
      ) : null}

      {!loading && tab === 'packages' ? (
        <div className="card">
          <div className="cardBody">
            <div className="runningSurveyTabs" style={{ marginBottom: 14 }}>
              {PACKAGE_ZONES.map((z) => (
                <button
                  key={z}
                  type="button"
                  className={`runningSurveyTab${packageZone === z ? ' on' : ''}`}
                  onClick={() => setPackageZone(z)}
                >
                  {ZONE_LABELS[z] || z.toUpperCase()}
                </button>
              ))}
            </div>
            <div className="runningSurveyActionBar" style={{ marginBottom: 14 }}>
              <button
                type="button"
                className="btn primary bsm"
                onClick={() =>
                  setPackageEdit({
                    plan_id: '',
                    max_locations: 1,
                    wa_units_included: 100,
                    admin_notes: '',
                    is_active: true,
                    display_order: 100,
                  })
                }
              >
                <Package size={14} /> Link / edit package
              </button>
            </div>
            {packageEdit ? (
              <EditPanel title="Package (plan link)" onClose={() => setPackageEdit(null)} onSave={savePackage} saving={busy}>
                <p className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
                  Zone: <strong>{ZONE_LABELS[packageZone]}</strong>. Requires an existing Plan with <code>service_kind=customer_feedback</code>.
                </p>
                <div className="runningSurveyEditGrid">
                  <Field label="Plan">
                    <select
                      className="input"
                      value={packageEdit.plan_id || ''}
                      onChange={(e) => {
                        const planId = e.target.value
                        const plan = feedbackPlans.find((p) => p.id === planId)
                        setPackageEdit((f) => ({
                          ...f,
                          plan_id: planId,
                          max_locations: plan?.max_locations ?? f.max_locations,
                          wa_units_included: plan?.wa_units_included ?? f.wa_units_included,
                        }))
                      }}
                    >
                      <option value="">Select feedback plan…</option>
                      {feedbackPlans.map((plan) => (
                        <option key={plan.id} value={plan.id}>
                          {plan.name} ({plan.code})
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Max locations">
                    <input className="input" type="number" value={packageEdit.max_locations ?? 1} onChange={(e) => setPackageEdit((f) => ({ ...f, max_locations: Number(e.target.value) }))} />
                  </Field>
                  <Field label="WA units included">
                    <input className="input" type="number" value={packageEdit.wa_units_included ?? 100} onChange={(e) => setPackageEdit((f) => ({ ...f, wa_units_included: Number(e.target.value) }))} />
                  </Field>
                  <Field label="Display order">
                    <input className="input" type="number" value={packageEdit.display_order ?? 100} onChange={(e) => setPackageEdit((f) => ({ ...f, display_order: Number(e.target.value) }))} />
                  </Field>
                  <Field label="Admin notes">
                    <input className="input" value={packageEdit.admin_notes || ''} onChange={(e) => setPackageEdit((f) => ({ ...f, admin_notes: e.target.value }))} />
                  </Field>
                  <Field label="Active">
                    <input type="checkbox" checked={Boolean(packageEdit.is_active)} onChange={(e) => setPackageEdit((f) => ({ ...f, is_active: e.target.checked }))} />
                  </Field>
                </div>
              </EditPanel>
            ) : null}
            <div className="tableWrap">
              <table className="table runningSurveyTable">
                <thead>
                  <tr>
                    <th>Plan</th>
                    <th>Code</th>
                    <th>Locations</th>
                    <th>WA units</th>
                    <th>Prices</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {packages.map((row) => (
                    <tr key={row.id}>
                      <td><strong>{row.plan_name || '—'}</strong></td>
                      <td><code>{row.plan_code || row.plan_id}</code></td>
                      <td>{row.max_locations}</td>
                      <td>{row.wa_units_included}</td>
                      <td className="muted">
                        {(row.prices || []).map((p) => moneyMinor(p.monthly_price_minor, p.currency)).join(' · ') || '—'}
                      </td>
                      <td><span className={statusPill(row.is_active)}>{row.is_active ? 'Active' : 'Inactive'}</span></td>
                      <td>
                        <button type="button" className="btn soft bsm" onClick={() => setPackageEdit({ ...row, plan_id: row.plan_id })}>Edit</button>
                      </td>
                    </tr>
                  ))}
                  {!packages.length ? <tr><td colSpan={7} className="muted">No packages for this zone.</td></tr> : null}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}

      {!loading && tab === 'subscriptions' ? (
        <Panel title="Subscriptions" subtitle="Active customer feedback subscriptions and WhatsApp unit usage.">
          <StripeTable>
            <TableHeader>
              <TableRow>
                <TableHead>Organisation</TableHead>
                <TableHead>Plan</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>WA used</TableHead>
                <TableHead>WA remaining</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {subscriptions.map((row) => (
                <TableRow key={row.org_id}>
                  <TableCell><strong className="font-medium">{row.org_name}</strong></TableCell>
                  <TableCell className="text-muted-foreground">{row.plan_name || '—'}</TableCell>
                  <TableCell><Pill tone="info">{row.status}</Pill></TableCell>
                  <TableCell>{row.wa_units_used ?? 0} / {row.wa_units_included ?? 0}</TableCell>
                  <TableCell>{row.wa_units_remaining ?? 0}</TableCell>
                </TableRow>
              ))}
              {!subscriptions.length ? <TableEmpty colSpan={5}>No customer feedback subscriptions yet.</TableEmpty> : null}
            </TableBody>
          </StripeTable>
        </Panel>
      ) : null}

      {!loading && tab === 'locations' ? (
        <Panel title="Locations" subtitle="Feedback QR locations across organisations.">
          <StripeTable>
            <TableHeader>
              <TableRow>
                <TableHead>Location</TableHead>
                <TableHead>Org ID</TableHead>
                <TableHead>Industry</TableHead>
                <TableHead>Survey type</TableHead>
                <TableHead>Scans</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {locations.map((row) => (
                <TableRow key={row.id}>
                  <TableCell><strong className="font-medium">{row.name || row.branch_code || row.id.slice(0, 8)}</strong></TableCell>
                  <TableCell className="text-muted-foreground">{row.org_id}</TableCell>
                  <TableCell>{row.industry_name || '—'}</TableCell>
                  <TableCell>{row.survey_type_name || '—'}</TableCell>
                  <TableCell>{row.scan_count ?? 0}</TableCell>
                  <TableCell><Pill tone="info">{row.status || '—'}</Pill></TableCell>
                  <TableCell className="whitespace-nowrap text-[11px] text-muted-foreground">{fmtWhen(row.created_at)}</TableCell>
                </TableRow>
              ))}
              {!locations.length ? <TableEmpty colSpan={7}>No feedback locations yet.</TableEmpty> : null}
            </TableBody>
          </StripeTable>
        </Panel>
      ) : null}

      {!loading && tab === 'results' ? (
        <Panel title="Results" subtitle="Latest feedback responses across all locations.">
          <StripeTable>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Location</TableHead>
                <TableHead>Question</TableHead>
                <TableHead>Answer</TableHead>
                <TableHead>Org ID</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {results.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="whitespace-nowrap text-[11px] text-muted-foreground">{fmtWhen(row.created_at)}</TableCell>
                  <TableCell>{row.location_name || row.location_id || '—'}</TableCell>
                  <TableCell><code className="text-[11px]">{row.question_key}</code></TableCell>
                  <TableCell>{row.answer_text || '—'}</TableCell>
                  <TableCell className="text-muted-foreground">{row.org_id}</TableCell>
                </TableRow>
              ))}
              {!results.length ? <TableEmpty colSpan={5}>No feedback responses yet.</TableEmpty> : null}
            </TableBody>
          </StripeTable>
        </Panel>
      ) : null}

      {!loading && tab === 'wa-templates' ? (
        <Panel
          title="WhatsApp templates"
          subtitle="Per-step WhatsApp survey message templates."
          action={
            <Button
              type="button"
              size="sm"
              className="h-8"
              onClick={() =>
                setWaTemplateEdit({
                  industry_id: industries[0]?.id || '',
                  survey_type_id: surveyTypes[0]?.id || '',
                  step_order: 1,
                  template_key: 'question',
                  body_text: '',
                  is_active: true,
                })
              }
            >
              Add template step
            </Button>
          }
        >
          {waTemplateEdit ? (
            <DsEditPanel title={waTemplateEdit.id ? 'Edit WA template' : 'New WA template'} onClose={() => setWaTemplateEdit(null)} onSave={saveWaTemplate} saving={busy}>
              <DsField label="Industry">
                <select className={NATIVE_SELECT_CLS} value={waTemplateEdit.industry_id || ''} onChange={(e) => setWaTemplateEdit((f) => ({ ...f, industry_id: e.target.value }))}>
                  <option value="">—</option>
                  {industries.map((i) => (
                    <option key={i.id} value={i.id}>{i.name}</option>
                  ))}
                </select>
              </DsField>
              <DsField label="Survey type">
                <select className={NATIVE_SELECT_CLS} value={waTemplateEdit.survey_type_id || ''} onChange={(e) => setWaTemplateEdit((f) => ({ ...f, survey_type_id: e.target.value }))}>
                  <option value="">—</option>
                  {surveyTypes.map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </DsField>
              <DsField label="Step order">
                <Input className="h-8" type="number" value={waTemplateEdit.step_order ?? 1} onChange={(e) => setWaTemplateEdit((f) => ({ ...f, step_order: Number(e.target.value) }))} />
              </DsField>
              <DsField label="Template key">
                <Input className="h-8" value={waTemplateEdit.template_key || ''} onChange={(e) => setWaTemplateEdit((f) => ({ ...f, template_key: e.target.value }))} />
              </DsField>
              <DsField label="Body text" className="sm:col-span-2">
                <Textarea rows={4} value={waTemplateEdit.body_text || ''} onChange={(e) => setWaTemplateEdit((f) => ({ ...f, body_text: e.target.value }))} />
              </DsField>
              <DsField label="Active">
                <ActiveCheck checked={Boolean(waTemplateEdit.is_active)} onChange={(e) => setWaTemplateEdit((f) => ({ ...f, is_active: e.target.checked }))} />
              </DsField>
            </DsEditPanel>
          ) : null}
          <StripeTable>
            <TableHeader>
              <TableRow>
                <TableHead>Step</TableHead>
                <TableHead>Key</TableHead>
                <TableHead>Industry</TableHead>
                <TableHead>Survey type</TableHead>
                <TableHead>Body</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {waTemplates.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>{row.step_order}</TableCell>
                  <TableCell><code className="text-[11px]">{row.template_key}</code></TableCell>
                  <TableCell>{industryName(row.industry_id)}</TableCell>
                  <TableCell>{surveyTypes.find((s) => s.id === row.survey_type_id)?.name || row.survey_type_id || '—'}</TableCell>
                  <TableCell className="max-w-[280px] truncate text-muted-foreground">{row.body_text}</TableCell>
                  <TableCell><Pill tone={row.is_active ? 'success' : 'neutral'}>{row.is_active ? 'Active' : 'Inactive'}</Pill></TableCell>
                  <TableCell className="text-right">
                    <Button type="button" variant="outline" size="sm" className="h-7" onClick={() => setWaTemplateEdit({ ...row })}>Edit</Button>
                  </TableCell>
                </TableRow>
              ))}
              {!waTemplates.length ? <TableEmpty colSpan={7}>No WhatsApp templates yet.</TableEmpty> : null}
            </TableBody>
          </StripeTable>
        </Panel>
      ) : null}
    </div>
  )
}
