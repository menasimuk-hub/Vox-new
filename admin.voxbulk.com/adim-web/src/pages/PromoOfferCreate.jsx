import React, { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const emptyDraft = {
  code: '',
  name: '',
  plan_code: '',
  offer_type: 'dental_trial',
  trial_days: 15,
  max_redemptions: 1,
  expires_in_days: 30,
  prospect_name: '',
  prospect_email: '',
  prospect_phone: '',
}

function money(pence) {
  return `£${(Number(pence || 0) / 100).toFixed(0)}`
}

function limitsPreview(plan) {
  if (!plan) return 'Select a plan to preview included usage.'
  const parts = []
  if (plan.calls_included) parts.push(`${plan.calls_included} calls/mo`)
  if (plan.whatsapp_included) parts.push(`${plan.whatsapp_included} WhatsApp`)
  if (plan.sms_included) parts.push(`${plan.sms_included} SMS`)
  if (plan.overage_per_min_pence) parts.push(`${plan.overage_per_min_pence}p/min overage`)
  return parts.join(' · ') || 'Uses plan defaults'
}

export default function PromoOfferCreate() {
  const navigate = useNavigate()
  const [draft, setDraft] = useState(emptyDraft)
  const [plans, setPlans] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        const planRows = await apiFetch('/admin/products/plans/active')
        if (cancelled) return
        const list = Array.isArray(planRows) ? planRows : []
        setPlans(list)
        if (list.length) {
          setDraft((prev) => ({ ...prev, plan_code: prev.plan_code || list[0].code }))
        }
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load plans')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const selectedPlan = useMemo(
    () => plans.find((p) => p.code === draft.plan_code) || null,
    [plans, draft.plan_code],
  )

  const previewName = draft.name.trim() || (selectedPlan ? `Promo · ${selectedPlan.name}` : 'New promo offer')
  const previewCode = draft.code.trim().toUpperCase() || 'AUTO-GENERATED'

  const save = async () => {
    if (!draft.plan_code) {
      setError('Choose a subscription plan.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const payload = {
        name: draft.name.trim() || undefined,
        code: draft.code.trim() || undefined,
        plan_code: draft.plan_code,
        offer_type: draft.offer_type,
        trial_days: Number(draft.trial_days) || 0,
        max_redemptions: Number(draft.max_redemptions) || 1,
        expires_in_days: Number(draft.expires_in_days) || 30,
        prospect_name: draft.prospect_name.trim() || undefined,
        prospect_email: draft.prospect_email.trim() || undefined,
        prospect_phone: draft.prospect_phone.trim() || undefined,
      }
      await apiFetch('/admin/promo-offers', { method: 'POST', body: JSON.stringify(payload) })
      navigate('/marketing/promo-offers?created=1', { replace: true })
    } catch (e) {
      setError(e?.message || 'Could not create promo')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className='muted' style={{ padding: 24 }}>Loading plans…</p>

  return (
    <>
      <div className='pageTop'>
        <div>
          <Link to='/marketing/promo-offers' className='muted' style={{ fontSize: 13 }}>
            ← Back to promo offers
          </Link>
          <h1 style={{ marginTop: 8 }}>New promo offer</h1>
          <p className='muted'>Create a signup code and share the link with prospects. Trial days and plan limits apply at redemption.</p>
        </div>
        <div className='actions'>
          <Link className='btn soft' to='/marketing/promo-offers'>
            Cancel
          </Link>
          <button type='button' className='btn primary' disabled={saving || !plans.length} onClick={save}>
            {saving ? 'Creating…' : 'Create promo'}
          </button>
        </div>
      </div>

      {error ? <div className='note noteWarn'>{error}</div> : null}
      {!plans.length ? (
        <div className='note noteWarn'>
          No active subscription plans. Create one under{' '}
          <Link to='/billing/products?tab=subscription'>Products hub</Link> first.
        </div>
      ) : null}

      <div className='pageShell productsPlanFormShell promoCreateShell'>
        <div className='promoCreateGrid'>
          <section className='card adminPackageEditor'>
            <div className='cardHead'>
              <div>
                <h3>Offer details</h3>
                <div className='muted packageMeta'>Code, name, and linked subscription plan</div>
              </div>
            </div>
            <div className='cardBody adminPackageForm'>
              <div className='adminPackageFormRow promoFormRowWide'>
                <label className='label'>
                  Promo code
                  <input
                    className='input'
                    value={draft.code}
                    onChange={(e) => setDraft({ ...draft, code: e.target.value.toUpperCase() })}
                    placeholder='Leave blank to auto-generate'
                  />
                </label>
                <label className='label'>
                  Display name
                  <input
                    className='input'
                    value={draft.name}
                    onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                    placeholder='Summer trial — Dental Pro'
                  />
                </label>
              </div>
              <label className='label'>
                Subscription plan
                <select className='input' value={draft.plan_code} onChange={(e) => setDraft({ ...draft, plan_code: e.target.value })}>
                  {plans.map((p) => (
                    <option key={p.id} value={p.code}>
                      {p.name} ({p.code}) — {money(p.price_gbp_pence)}/mo
                    </option>
                  ))}
                </select>
              </label>
              {selectedPlan ? (
                <div className='promoPlanSummary'>
                  <div>
                    <strong>{selectedPlan.name}</strong>
                    <span className='muted'>{limitsPreview(selectedPlan)}</span>
                  </div>
                  <span className='productPrice'>
                    {money(selectedPlan.price_gbp_pence)}
                    <span> / month after trial</span>
                  </span>
                </div>
              ) : null}
            </div>
          </section>

          <section className='card adminPackageEditor'>
            <div className='cardHead'>
              <div>
                <h3>Trial & redemption</h3>
                <div className='muted packageMeta'>How long the offer lasts and how many signups it allows</div>
              </div>
            </div>
            <div className='cardBody adminPackageForm'>
              <div className='adminPackageFormRow promoFormRowWide'>
                <label className='label'>
                  Trial days
                  <input
                    className='input'
                    type='number'
                    min={0}
                    value={draft.trial_days}
                    onChange={(e) => setDraft({ ...draft, trial_days: e.target.value })}
                  />
                </label>
                <label className='label'>
                  Max redemptions
                  <input
                    className='input'
                    type='number'
                    min={1}
                    value={draft.max_redemptions}
                    onChange={(e) => setDraft({ ...draft, max_redemptions: e.target.value })}
                  />
                </label>
                <label className='label'>
                  Expires in (days)
                  <input
                    className='input'
                    type='number'
                    min={1}
                    value={draft.expires_in_days}
                    onChange={(e) => setDraft({ ...draft, expires_in_days: e.target.value })}
                  />
                </label>
              </div>
              <p className='muted' style={{ margin: 0, fontSize: 12 }}>
                After expiry or max redemptions, the code stops working on the public signup page.
              </p>
            </div>
          </section>

          <section className='card adminPackageEditor'>
            <div className='cardHead'>
              <div>
                <h3>Prospect (optional)</h3>
                <div className='muted packageMeta'>For your records — shown in the promo list</div>
              </div>
            </div>
            <div className='cardBody adminPackageForm'>
              <div className='adminPackageFormRow promoFormRowWide'>
                <label className='label'>
                  Name
                  <input
                    className='input'
                    value={draft.prospect_name}
                    onChange={(e) => setDraft({ ...draft, prospect_name: e.target.value })}
                    placeholder='Alex Smith'
                  />
                </label>
                <label className='label'>
                  Email
                  <input
                    className='input'
                    type='email'
                    value={draft.prospect_email}
                    onChange={(e) => setDraft({ ...draft, prospect_email: e.target.value })}
                    placeholder='alex@clinic.example'
                  />
                </label>
                <label className='label'>
                  Phone
                  <input
                    className='input'
                    value={draft.prospect_phone}
                    onChange={(e) => setDraft({ ...draft, prospect_phone: e.target.value })}
                    placeholder='+44…'
                  />
                </label>
              </div>
            </div>
          </section>

          <aside className='card promoPreviewCard'>
            <div className='cardHead'>
              <div>
                <h3>Preview</h3>
                <div className='muted packageMeta'>What the customer will see after you create this offer</div>
              </div>
            </div>
            <div className='cardBody promoPreviewBody'>
              <div className='promoPreviewHero'>
                <span className='productAvatar'>
                  <i className='ti ti-ticket' />
                </span>
                <div>
                  <strong>{previewName}</strong>
                  <code className='productCode' style={{ marginTop: 8, display: 'inline-block' }}>
                    {previewCode}
                  </code>
                </div>
              </div>
              <ul className='promoPreviewList'>
                <li>
                  <i className='ti ti-credit-card' />
                  Plan: <strong>{selectedPlan?.name || draft.plan_code || '—'}</strong>
                </li>
                <li>
                  <i className='ti ti-clock' />
                  {Number(draft.trial_days || 0) > 0 ? `${draft.trial_days}-day free trial` : 'No trial — billed immediately'}
                </li>
                <li>
                  <i className='ti ti-users' />
                  Up to {draft.max_redemptions} signup{Number(draft.max_redemptions) === 1 ? '' : 's'}
                </li>
                <li>
                  <i className='ti ti-calendar' />
                  Link valid for {draft.expires_in_days} days
                </li>
              </ul>
              <div className='promoSignupPreview'>
                <label>Signup URL format</label>
                <code>/signin?promo={previewCode === 'AUTO-GENERATED' ? 'YOURCODE' : previewCode}</code>
              </div>
              <button type='button' className='btn primary' style={{ width: '100%' }} disabled={saving || !plans.length} onClick={save}>
                {saving ? 'Creating…' : 'Create promo offer'}
              </button>
            </div>
          </aside>
        </div>
      </div>
    </>
  )
}
