import React, { useMemo, useState } from 'react'
import { usePricingPlans, usePricingSettings, penceToPounds, poundsToPence } from './pricingUtils'
import PricingPageFrame, { PricingFormulaBox } from './PricingPageFrame'

function calcPreview(d, settings) {
  const price = Number(d.price_gbp_pence || 0)
  const perMin = Number(d.per_min_pence || 0)
  const wa = Number(settings?.whatsapp_survey_fee_pence || 0)
  const cv = Number(settings?.ats_cv_scan_fee_pence || 0)
  return {
    minutes: perMin > 0 ? Math.floor(price / perMin) : 0,
    wa: wa > 0 ? Math.floor(price / wa) : 0,
    cv: cv > 0 ? Math.floor(price / cv) : 0,
  }
}

function NumInput({ value, onChange, wide }) {
  return (
    <div className={`pricingCellBox${wide ? ' pricingCellBoxWide' : ''}`}>
      <input
        className="input pricingInputInline"
        type="number"
        step="0.01"
        value={value}
        onChange={onChange}
      />
    </div>
  )
}

function CalcBox({ value, title }) {
  return (
    <div className="pricingCellBox calc" title={title}>
      {value}
    </div>
  )
}

function PlanRow({ plan, settings, onSave }) {
  const [draft, setDraft] = useState(null)
  const d = draft || plan
  const set = (field, value) => setDraft({ ...d, [field]: value })
  const preview = calcPreview(d, settings)

  if (plan.is_enterprise) {
    return (
      <tr className="pricingPlanRow">
        <td className="pricingPlanName">
          <strong>{plan.name}</strong>
          <span className="pricingPlanCode">{plan.code}</span>
        </td>
        <td colSpan={6} className="muted pricingTdCenter">Custom — use Custom org tab</td>
        <td className="pricingTdCenter">
          <label className="svcPriceToggle"><input type="checkbox" checked={Boolean(d.is_active)} onChange={(e) => set('is_active', e.target.checked)} /><span className="svcPriceToggleUi" /></label>
        </td>
        <td className="pricingTdCenter">
          <button className="btn soft pricingSaveBtn" type="button" onClick={() => onSave(plan.id, draft || plan)}>Save</button>
        </td>
      </tr>
    )
  }

  const priceTip = `${penceToPounds(d.price_gbp_pence)} ÷ ${penceToPounds(d.per_min_pence)}`
  const waTip = `${penceToPounds(d.price_gbp_pence)} ÷ ${penceToPounds(settings?.whatsapp_survey_fee_pence)}`
  const cvTip = `${penceToPounds(d.price_gbp_pence)} ÷ ${penceToPounds(settings?.ats_cv_scan_fee_pence)}`

  return (
    <tr className="pricingPlanRow">
      <td className="pricingPlanName">
        <strong>{plan.name}</strong>
        <span className="pricingPlanCode">{plan.code}</span>
      </td>
      <td className="pricingTdNum">
        <NumInput wide value={penceToPounds(d.price_gbp_pence)} onChange={(e) => set('price_gbp_pence', poundsToPence(e.target.value))} />
      </td>
      <td className="pricingTdNum">
        <NumInput value={penceToPounds(d.per_min_pence)} onChange={(e) => set('per_min_pence', poundsToPence(e.target.value))} />
      </td>
      <td className="pricingTdNum">
        <NumInput value={penceToPounds(d.extra_per_min_pence ?? d.overage_per_min_pence)} onChange={(e) => set('extra_per_min_pence', poundsToPence(e.target.value))} />
      </td>
      <td className="pricingTdNum"><CalcBox value={preview.minutes} title={priceTip} /></td>
      <td className="pricingTdNum"><CalcBox value={preview.wa} title={waTip} /></td>
      <td className="pricingTdNum"><CalcBox value={preview.cv} title={cvTip} /></td>
      <td className="pricingTdCenter">
        <label className="svcPriceToggle"><input type="checkbox" checked={Boolean(d.is_featured)} onChange={(e) => set('is_featured', e.target.checked)} /><span className="svcPriceToggleUi" /></label>
      </td>
      <td className="pricingTdCenter">
        <label className="svcPriceToggle"><input type="checkbox" checked={Boolean(d.is_active)} onChange={(e) => set('is_active', e.target.checked)} /><span className="svcPriceToggleUi" /></label>
      </td>
      <td className="pricingTdCenter">
        <button className="btn soft pricingSaveBtn" type="button" onClick={() => onSave(plan.id, draft || plan)}>Save</button>
      </td>
    </tr>
  )
}

export default function PricingPlans() {
  const { plans, loading, error, msg, savePlan, seed } = usePricingPlans()
  const { settings } = usePricingSettings()

  const visiblePlans = useMemo(() => {
    const vox = plans.filter((p) => p.service_kind === 'voxbulk')
    return [...(vox.length ? vox : plans)].sort((a, b) => (a.sort_order ?? 100) - (b.sort_order ?? 100))
  }, [plans])

  if (loading) return <p className="muted">Loading plans…</p>

  const wa = settings ? penceToPounds(settings.whatsapp_survey_fee_pence) : '—'
  const cv = settings ? penceToPounds(settings.ats_cv_scan_fee_pence) : '—'

  return (
    <PricingPageFrame
      title="Subscription plans"
      description="Edit prices on the left; green boxes are auto-calculated when you save."
      error={error}
      msg={msg}
      actions={<button className="btn soft" type="button" onClick={() => void seed()}>Seed defaults</button>}
    >
      <PricingFormulaBox
        items={[
          'Mins/mo = Monthly ÷ Cost/min',
          `WA = Monthly ÷ £${wa}`,
          `CV = Monthly ÷ £${cv}`,
          'Extra min = charged after included mins used up',
        ]}
      />
      <div className="tableWrap pricingTableWrap">
        <table className="table pricingTable pricingTablePlans">
          <thead>
            <tr>
              <th className="pricingThPlan">Plan</th>
              <th className="pricingThNum">Monthly £</th>
              <th className="pricingThNum">Cost/min</th>
              <th className="pricingThNum">Extra/min</th>
              <th className="pricingThNum pricingThCalc">Mins</th>
              <th className="pricingThNum pricingThCalc">WA</th>
              <th className="pricingThNum pricingThCalc">CV</th>
              <th className="pricingThToggle">Feat.</th>
              <th className="pricingThToggle">On</th>
              <th className="pricingThAction" />
            </tr>
          </thead>
          <tbody>
            {visiblePlans.map((p) => (
              <PlanRow key={p.id} plan={p} settings={settings} onSave={savePlan} />
            ))}
          </tbody>
        </table>
      </div>
    </PricingPageFrame>
  )
}
