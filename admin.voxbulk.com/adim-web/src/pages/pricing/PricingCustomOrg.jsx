import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'
import { penceToPounds, poundsToPence } from './pricingUtils'
import PricingPageFrame, { PricingField } from './PricingPageFrame'

const empty = {
  org_id: '',
  label: '',
  monthly_price_gbp_pence: '',
  per_min_pence: '',
  connection_fee_pence: '',
  minutes_included: '',
  whatsapp_included: '',
  cv_scans_included: '',
  interview_per_min_pence: '',
  whatsapp_survey_fee_pence: '',
  ats_cv_scan_fee_pence: '',
  notes: '',
  is_active: true,
}

export default function PricingCustomOrg() {
  const [rows, setRows] = useState([])
  const [orgs, setOrgs] = useState([])
  const [draft, setDraft] = useState(empty)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    const [custom, orgList] = await Promise.all([
      apiFetch('/admin/pricing/custom'),
      apiFetch('/organisations?limit=200'),
    ])
    setRows(Array.isArray(custom) ? custom : [])
    setOrgs(Array.isArray(orgList?.items) ? orgList.items : Array.isArray(orgList) ? orgList : [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try { await load() } catch (e) { if (!cancelled) setError(e?.message || 'Load failed') }
      finally { if (!cancelled) setLoading(false) }
    })()
    return () => { cancelled = true }
  }, [load])

  const set = (field, value) => setDraft({ ...draft, [field]: value })

  const toPayload = (d) => ({
    org_id: d.org_id,
    label: d.label || undefined,
    monthly_price_gbp_pence: d.monthly_price_gbp_pence === '' ? null : poundsToPence(d.monthly_price_gbp_pence),
    per_min_pence: d.per_min_pence === '' ? null : poundsToPence(d.per_min_pence),
    connection_fee_pence: d.connection_fee_pence === '' ? null : poundsToPence(d.connection_fee_pence),
    minutes_included: d.minutes_included === '' ? null : Number(d.minutes_included),
    whatsapp_included: d.whatsapp_included === '' ? null : Number(d.whatsapp_included),
    cv_scans_included: d.cv_scans_included === '' ? null : Number(d.cv_scans_included),
    interview_per_min_pence: d.interview_per_min_pence === '' ? null : poundsToPence(d.interview_per_min_pence),
    whatsapp_survey_fee_pence: d.whatsapp_survey_fee_pence === '' ? null : poundsToPence(d.whatsapp_survey_fee_pence),
    ats_cv_scan_fee_pence: d.ats_cv_scan_fee_pence === '' ? null : poundsToPence(d.ats_cv_scan_fee_pence),
    notes: d.notes || undefined,
    is_active: Boolean(d.is_active),
  })

  const create = async () => {
    setError('')
    try {
      await apiFetch('/admin/pricing/custom', { method: 'POST', body: JSON.stringify(toPayload(draft)) })
      setDraft(empty)
      await load()
      setMsg('Custom pricing created.')
    } catch (e) { setError(e?.message || 'Create failed') }
  }

  const remove = async (id) => {
    if (!window.confirm('Delete custom pricing?')) return
    await apiFetch(`/admin/pricing/custom/${encodeURIComponent(id)}`, { method: 'DELETE' })
    await load()
  }

  if (loading) return <p className="muted">Loading…</p>

  return (
    <PricingPageFrame
      title="Custom org pricing"
      description="Enterprise deals — set bespoke rates for one organisation."
      error={error}
      msg={msg}
    >
      {rows.length > 0 && (
        <div className="tableWrap pricingTableWrap" style={{ marginBottom: 16 }}>
          <table className="table pricingTable pricingTableCompact">
            <thead>
              <tr>
                <th>Organisation</th>
                <th className="pricingThNum">Monthly £</th>
                <th className="pricingThNum">Per min £</th>
                <th>Active</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td><strong>{r.org_name || r.org_id}</strong><div className="muted pricingPlanCode">{r.label}</div></td>
                  <td className="pricingTdNum"><span className="pricingCellBox calc">{r.monthly_price_gbp_pence == null ? '—' : penceToPounds(r.monthly_price_gbp_pence)}</span></td>
                  <td className="pricingTdNum"><span className="pricingCellBox calc">{r.per_min_pence == null ? '—' : penceToPounds(r.per_min_pence)}</span></td>
                  <td className="pricingTdCenter">{r.is_active ? 'Yes' : 'No'}</td>
                  <td className="pricingTdCenter"><button className="btn soft pricingSaveBtn" type="button" onClick={() => void remove(r.id)}>Delete</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="pricingSectionLabel">Add custom pricing</p>
      <div className="pricingGrid5">
        <PricingField label="Organisation" compact>
          <select className="input pricingInputSm" value={draft.org_id} onChange={(e) => set('org_id', e.target.value)}>
            <option value="">Select…</option>
            {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        </PricingField>
        <PricingField label="Label" compact>
          <input className="input pricingInputSm" value={draft.label} onChange={(e) => set('label', e.target.value)} placeholder="Deal name" />
        </PricingField>
        <PricingField label="Monthly £" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={draft.monthly_price_gbp_pence} onChange={(e) => set('monthly_price_gbp_pence', e.target.value)} />
        </PricingField>
        <PricingField label="Per min £" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={draft.per_min_pence} onChange={(e) => set('per_min_pence', e.target.value)} />
        </PricingField>
        <PricingField label="Conn. fee £" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={draft.connection_fee_pence} onChange={(e) => set('connection_fee_pence', e.target.value)} />
        </PricingField>
        <PricingField label="Mins incl." compact>
          <input className="input pricingInputSm pricingInputNum" type="number" value={draft.minutes_included} onChange={(e) => set('minutes_included', e.target.value)} />
        </PricingField>
        <PricingField label="WA incl." compact>
          <input className="input pricingInputSm pricingInputNum" type="number" value={draft.whatsapp_included} onChange={(e) => set('whatsapp_included', e.target.value)} />
        </PricingField>
        <PricingField label="CV incl." compact>
          <input className="input pricingInputSm pricingInputNum" type="number" value={draft.cv_scans_included} onChange={(e) => set('cv_scans_included', e.target.value)} />
        </PricingField>
        <PricingField label="IV per min £" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={draft.interview_per_min_pence} onChange={(e) => set('interview_per_min_pence', e.target.value)} />
        </PricingField>
        <PricingField label="WA fee £" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={draft.whatsapp_survey_fee_pence} onChange={(e) => set('whatsapp_survey_fee_pence', e.target.value)} />
        </PricingField>
        <PricingField label="ATS fee £" compact>
          <input className="input pricingInputSm pricingInputNum" type="number" step="0.01" value={draft.ats_cv_scan_fee_pence} onChange={(e) => set('ats_cv_scan_fee_pence', e.target.value)} />
        </PricingField>
        <PricingField label="Active" compact>
          <label className="svcPriceToggle" style={{ marginTop: 4 }}><input type="checkbox" checked={Boolean(draft.is_active)} onChange={(e) => set('is_active', e.target.checked)} /><span className="svcPriceToggleUi" /></label>
        </PricingField>
      </div>
      <div className="pricingGrid5" style={{ marginTop: 10 }}>
        <PricingField label="Notes" compact wide fullRow>
          <input className="input pricingInputSm" value={draft.notes} onChange={(e) => set('notes', e.target.value)} placeholder="Optional notes" />
        </PricingField>
      </div>
      <div className="pricingActions"><button className="btn" type="button" onClick={() => void create()}>Create</button></div>
    </PricingPageFrame>
  )
}
