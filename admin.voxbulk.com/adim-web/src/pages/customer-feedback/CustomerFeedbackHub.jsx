import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { MessageCircle, Package, RefreshCw } from 'lucide-react'
import { apiFetch } from '../../lib/api'

const TABS = [
  { key: 'industries', label: 'Industries' },
  { key: 'survey-types', label: 'Survey types' },
  { key: 'packages', label: 'Packages' },
  { key: 'subscriptions', label: 'Subscriptions' },
  { key: 'locations', label: 'Locations' },
  { key: 'results', label: 'Results' },
  { key: 'wa-templates', label: 'WhatsApp templates' },
]

const PACKAGE_ZONES = ['gb', 'eu', 'us', 'ca', 'au']

const ZONE_LABELS = { gb: 'GB', eu: 'EU', us: 'US', ca: 'CA', au: 'AU' }

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

function statusPill(active) {
  return active ? 'leadPill leadPillAdvance' : 'leadPill leadPillNeutral'
}

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

function Field({ label, children }) {
  return (
    <label style={{ display: 'grid', gap: 6 }}>
      <span className="muted" style={{ fontSize: 12 }}>{label}</span>
      {children}
    </label>
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
      if (tab === 'industries') {
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

  const toggleSurveyTypeActive = async (row, nextActive) => {
    setBusy(`type-${row.id}`)
    setError('')
    try {
      await apiFetch(`/admin/customer-feedback/survey-types/${row.id}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ is_active: nextActive }),
      })
      await loadTab()
    } catch (e) {
      setError(e?.message || 'Could not update survey type')
    } finally {
      setBusy(false)
    }
  }

  const toggleWaTemplateActive = async (row, nextActive) => {
    setBusy(`tpl-${row.id}`)
    setError('')
    try {
      await apiFetch(`/admin/customer-feedback/wa-templates/${row.id}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ is_active: nextActive }),
      })
      await loadTab()
    } catch (e) {
      setError(e?.message || 'Could not update template')
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

  return (
    <>
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
          <button type="button" className="btn soft" onClick={refreshAll} disabled={loading}>
            <RefreshCw size={15} />
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className="note runningSurveyError">{error}</div> : null}

      <div className="grid-3 runningSurveyStats">
        {overviewCards.map((c) => (
          <div key={c.label} className="card stat runningSurveyStat">
            <div className="statValue">{c.value}</div>
            <div className="muted">{c.label}</div>
          </div>
        ))}
      </div>

      <div className="note runningSurveyGuide">
        <strong>Billing &amp; refunds (GoCardless only)</strong>
        <ul style={{ margin: '8px 0 0', paddingLeft: 20 }}>
          <li>Customer feedback subscriptions use <strong>Direct Debit (GoCardless)</strong> only — no wallet top-up.</li>
          <li>There is <strong>no overage</strong>; WhatsApp survey units stop when the included allowance is exhausted.</li>
          <li>When units are used up, the customer must <strong>upgrade their package</strong> to continue — process refunds or plan changes via GoCardless mandate/subscription tools.</li>
          <li>Invoices use prefix <code>CF-</code> with <code>service_code=customer_feedback</code>.</li>
        </ul>
      </div>

      <div className="card runningSurveyListCard">
        <div className="cardHead runningSurveyListHead">
          <h3><MessageCircle size={16} /> Customer feedback admin</h3>
          <div className="runningSurveyTabs">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                className={`runningSurveyTab${tab === t.key ? ' on' : ''}`}
                onClick={() => setTab(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="cardBody">
          {loading ? <div className="muted">Loading…</div> : null}

          {!loading && tab === 'industries' ? (
            <>
              <div className="runningSurveyActionBar" style={{ marginBottom: 14 }}>
                <button
                  type="button"
                  className="btn primary bsm"
                  onClick={() => setIndustryEdit({ name: '', slug: '', description: '', is_active: true, sort_order: 100 })}
                >
                  Add industry
                </button>
              </div>
              {industryEdit ? (
                <EditPanel title={industryEdit.id ? 'Edit industry' : 'New industry'} onClose={() => setIndustryEdit(null)} onSave={saveIndustry} saving={busy}>
                  <div className="runningSurveyEditGrid">
                    <Field label="Name">
                      <input className="input" value={industryEdit.name || ''} onChange={(e) => setIndustryEdit((f) => ({ ...f, name: e.target.value }))} />
                    </Field>
                    <Field label="Slug">
                      <input className="input" value={industryEdit.slug || ''} onChange={(e) => setIndustryEdit((f) => ({ ...f, slug: e.target.value }))} />
                    </Field>
                    <Field label="Sort order">
                      <input className="input" type="number" value={industryEdit.sort_order ?? 100} onChange={(e) => setIndustryEdit((f) => ({ ...f, sort_order: Number(e.target.value) }))} />
                    </Field>
                    <Field label="Description">
                      <input className="input" value={industryEdit.description || ''} onChange={(e) => setIndustryEdit((f) => ({ ...f, description: e.target.value }))} />
                    </Field>
                    <Field label="Active">
                      <input type="checkbox" checked={Boolean(industryEdit.is_active)} onChange={(e) => setIndustryEdit((f) => ({ ...f, is_active: e.target.checked }))} />
                    </Field>
                  </div>
                </EditPanel>
              ) : null}
              <div className="tableWrap">
                <table className="table runningSurveyTable">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Slug</th>
                      <th>Order</th>
                      <th>Status</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {industries.map((row) => (
                      <tr key={row.id}>
                        <td><strong>{row.name}</strong></td>
                        <td><code>{row.slug}</code></td>
                        <td>{row.sort_order}</td>
                        <td><span className={statusPill(row.is_active)}>{row.is_active ? 'Active' : 'Inactive'}</span></td>
                        <td>
                          <button type="button" className="btn soft bsm" onClick={() => setIndustryEdit({ ...row })}>Edit</button>
                        </td>
                      </tr>
                    ))}
                    {!industries.length ? <tr><td colSpan={5} className="muted">No industries yet.</td></tr> : null}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}

          {!loading && tab === 'survey-types' ? (
            <>
              <div className="runningSurveyActionBar" style={{ marginBottom: 14 }}>
                <button
                  type="button"
                  className="btn primary bsm"
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
                </button>
              </div>
              {surveyTypeEdit ? (
                <EditPanel title={surveyTypeEdit.id ? 'Edit survey type' : 'New survey type'} onClose={() => setSurveyTypeEdit(null)} onSave={saveSurveyType} saving={busy}>
                  <div className="runningSurveyEditGrid">
                    <Field label="Industry">
                      <select className="input" value={surveyTypeEdit.industry_id || ''} onChange={(e) => setSurveyTypeEdit((f) => ({ ...f, industry_id: e.target.value }))}>
                        {industries.map((i) => (
                          <option key={i.id} value={i.id}>{i.name}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Name">
                      <input className="input" value={surveyTypeEdit.name || ''} onChange={(e) => setSurveyTypeEdit((f) => ({ ...f, name: e.target.value }))} />
                    </Field>
                    <Field label="Slug">
                      <input className="input" value={surveyTypeEdit.slug || ''} onChange={(e) => setSurveyTypeEdit((f) => ({ ...f, slug: e.target.value }))} />
                    </Field>
                    <Field label="Sort order">
                      <input className="input" type="number" value={surveyTypeEdit.sort_order ?? 100} onChange={(e) => setSurveyTypeEdit((f) => ({ ...f, sort_order: Number(e.target.value) }))} />
                    </Field>
                    <Field label="Description">
                      <input className="input" value={surveyTypeEdit.description || ''} onChange={(e) => setSurveyTypeEdit((f) => ({ ...f, description: e.target.value }))} />
                    </Field>
                    <Field label="Active">
                      <input type="checkbox" checked={Boolean(surveyTypeEdit.is_active)} onChange={(e) => setSurveyTypeEdit((f) => ({ ...f, is_active: e.target.checked }))} />
                    </Field>
                  </div>
                </EditPanel>
              ) : null}
              <div className="tableWrap">
                <table className="table runningSurveyTable">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Industry</th>
                      <th>Slug</th>
                      <th>Status</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {surveyTypes.map((row) => (
                      <tr key={row.id} style={!row.is_active ? { opacity: 0.72 } : undefined}>
                        <td><strong>{row.name}</strong></td>
                        <td>{industryName(row.industry_id)}</td>
                        <td><code>{row.slug}</code></td>
                        <td>
                          <span className={statusPill(row.is_active && !row.archived_at)}>
                            {row.archived_at ? 'Archived' : row.is_active ? 'Active' : 'Disabled'}
                          </span>
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                            {row.is_active ? (
                              <button
                                type="button"
                                className="btn soft bsm"
                                disabled={Boolean(busy)}
                                onClick={() => void toggleSurveyTypeActive(row, false)}
                              >
                                Disable
                              </button>
                            ) : (
                              <button
                                type="button"
                                className="btn soft bsm"
                                disabled={Boolean(busy)}
                                onClick={() => void toggleSurveyTypeActive(row, true)}
                              >
                                Enable
                              </button>
                            )}
                            <button type="button" className="btn soft bsm" onClick={() => setSurveyTypeEdit({ ...row })}>Edit</button>
                            <Link className="btn soft bsm" to={`/customer-feedback/survey-types/${row.id}`}>Templates</Link>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {!surveyTypes.length ? <tr><td colSpan={5} className="muted">No survey types yet.</td></tr> : null}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}

          {!loading && tab === 'packages' ? (
            <>
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
            </>
          ) : null}

          {!loading && tab === 'subscriptions' ? (
            <div className="tableWrap">
              <table className="table runningSurveyTable">
                <thead>
                  <tr>
                    <th>Organisation</th>
                    <th>Plan</th>
                    <th>Status</th>
                    <th>WA used</th>
                    <th>WA remaining</th>
                  </tr>
                </thead>
                <tbody>
                  {subscriptions.map((row) => (
                    <tr key={row.org_id}>
                      <td><strong>{row.org_name}</strong></td>
                      <td>{row.plan_name || '—'}</td>
                      <td><span className="leadPill">{row.status}</span></td>
                      <td>{row.wa_units_used ?? 0} / {row.wa_units_included ?? 0}</td>
                      <td>{row.wa_units_remaining ?? 0}</td>
                    </tr>
                  ))}
                  {!subscriptions.length ? <tr><td colSpan={5} className="muted">No customer feedback subscriptions yet.</td></tr> : null}
                </tbody>
              </table>
            </div>
          ) : null}

          {!loading && tab === 'locations' ? (
            <div className="tableWrap">
              <table className="table runningSurveyTable">
                <thead>
                  <tr>
                    <th>Location</th>
                    <th>Org ID</th>
                    <th>Industry</th>
                    <th>Survey type</th>
                    <th>Scans</th>
                    <th>Status</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {locations.map((row) => (
                    <tr key={row.id}>
                      <td><strong>{row.name || row.branch_code || row.id.slice(0, 8)}</strong></td>
                      <td className="muted">{row.org_id}</td>
                      <td>{row.industry_name || '—'}</td>
                      <td>{row.survey_type_name || '—'}</td>
                      <td>{row.scan_count ?? 0}</td>
                      <td><span className="leadPill">{row.status || '—'}</span></td>
                      <td>{fmtWhen(row.created_at)}</td>
                    </tr>
                  ))}
                  {!locations.length ? <tr><td colSpan={7} className="muted">No feedback locations yet.</td></tr> : null}
                </tbody>
              </table>
            </div>
          ) : null}

          {!loading && tab === 'results' ? (
            <div className="tableWrap">
              <table className="table runningSurveyTable">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Location</th>
                    <th>Question</th>
                    <th>Answer</th>
                    <th>Org ID</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((row) => (
                    <tr key={row.id}>
                      <td>{fmtWhen(row.created_at)}</td>
                      <td>{row.location_name || row.location_id || '—'}</td>
                      <td><code>{row.question_key}</code></td>
                      <td>{row.answer_text || '—'}</td>
                      <td className="muted">{row.org_id}</td>
                    </tr>
                  ))}
                  {!results.length ? <tr><td colSpan={5} className="muted">No feedback responses yet.</td></tr> : null}
                </tbody>
              </table>
            </div>
          ) : null}

          {!loading && tab === 'wa-templates' ? (
            <>
              <div className="runningSurveyActionBar" style={{ marginBottom: 14 }}>
                <button
                  type="button"
                  className="btn primary bsm"
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
                </button>
              </div>
              {waTemplateEdit ? (
                <EditPanel title={waTemplateEdit.id ? 'Edit WA template' : 'New WA template'} onClose={() => setWaTemplateEdit(null)} onSave={saveWaTemplate} saving={busy}>
                  <div className="runningSurveyEditGrid">
                    <Field label="Industry">
                      <select className="input" value={waTemplateEdit.industry_id || ''} onChange={(e) => setWaTemplateEdit((f) => ({ ...f, industry_id: e.target.value }))}>
                        <option value="">—</option>
                        {industries.map((i) => (
                          <option key={i.id} value={i.id}>{i.name}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Survey type">
                      <select className="input" value={waTemplateEdit.survey_type_id || ''} onChange={(e) => setWaTemplateEdit((f) => ({ ...f, survey_type_id: e.target.value }))}>
                        <option value="">—</option>
                        {surveyTypes.map((s) => (
                          <option key={s.id} value={s.id}>{s.name}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Step order">
                      <input className="input" type="number" value={waTemplateEdit.step_order ?? 1} onChange={(e) => setWaTemplateEdit((f) => ({ ...f, step_order: Number(e.target.value) }))} />
                    </Field>
                    <Field label="Template key">
                      <input className="input" value={waTemplateEdit.template_key || ''} onChange={(e) => setWaTemplateEdit((f) => ({ ...f, template_key: e.target.value }))} />
                    </Field>
                    <Field label="Body text">
                      <textarea className="input" rows={4} value={waTemplateEdit.body_text || ''} onChange={(e) => setWaTemplateEdit((f) => ({ ...f, body_text: e.target.value }))} />
                    </Field>
                    <Field label="Active">
                      <input type="checkbox" checked={Boolean(waTemplateEdit.is_active)} onChange={(e) => setWaTemplateEdit((f) => ({ ...f, is_active: e.target.checked }))} />
                    </Field>
                  </div>
                </EditPanel>
              ) : null}
              <div className="tableWrap">
                <table className="table runningSurveyTable">
                  <thead>
                    <tr>
                      <th>Step</th>
                      <th>Key</th>
                      <th>Industry</th>
                      <th>Survey type</th>
                      <th>Body</th>
                      <th>Status</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {waTemplates.map((row) => (
                      <tr key={row.id} style={!row.is_active || row.marketing_blocked ? { opacity: 0.72 } : undefined}>
                        <td>{row.step_order}</td>
                        <td><code>{row.template_key}</code></td>
                        <td>{industryName(row.industry_id)}</td>
                        <td>{surveyTypes.find((s) => s.id === row.survey_type_id)?.name || row.survey_type_id || '—'}</td>
                        <td className="muted" style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.body_text}</td>
                        <td>
                          <span className={statusPill(row.is_active && !row.marketing_blocked)}>
                            {row.marketing_blocked ? 'Platform disabled' : row.is_active ? 'Active' : 'Hidden'}
                          </span>
                        </td>
                        <td>
                          <button type="button" className="btn soft bsm" onClick={() => setWaTemplateEdit({ ...row })}>Edit</button>
                          {!row.marketing_blocked ? (
                            row.is_active ? (
                              <button type="button" className="btn soft bsm" disabled={busy === `tpl-${row.id}`} onClick={() => toggleWaTemplateActive(row, false)}>
                                {busy === `tpl-${row.id}` ? '…' : 'Hide'}
                              </button>
                            ) : (
                              <button type="button" className="btn soft bsm" disabled={busy === `tpl-${row.id}`} onClick={() => toggleWaTemplateActive(row, true)}>
                                {busy === `tpl-${row.id}` ? '…' : 'Enable'}
                              </button>
                            )
                          ) : null}
                        </td>
                      </tr>
                    ))}
                    {!waTemplates.length ? <tr><td colSpan={7} className="muted">No WhatsApp templates yet.</td></tr> : null}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </>
  )
}
