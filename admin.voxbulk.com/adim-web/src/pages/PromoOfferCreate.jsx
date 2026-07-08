import React, { useEffect, useMemo, useState } from 'react'

import { Link, useNavigate } from 'react-router-dom'

import PlanPickerSelect from '../components/billing/PlanPickerSelect'

import { apiFetch } from '../lib/api'



const OFFER_TYPES = [

  { value: 'dental_trial', label: 'Subscription plan trial' },

  { value: 'survey_credits', label: 'Free survey contacts' },

  { value: 'interview_credits', label: 'Free interviews' },

]



const emptyDraft = {

  code: '',

  name: '',

  offer_type: 'dental_trial',

  plan_code: '',

  survey_contacts_included: 20,

  interview_contacts_included: 3,

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

  if (plan.picker_subtitle) parts.push(plan.picker_subtitle)

  if (plan.price_display) parts.push(plan.price_display)

  return parts.join(' · ') || 'Uses plan defaults'

}



export default function PromoOfferCreate() {

  const navigate = useNavigate()

  const [draft, setDraft] = useState(emptyDraft)

  const [plans, setPlans] = useState([])

  const [loading, setLoading] = useState(true)

  const [saving, setSaving] = useState(false)

  const [error, setError] = useState('')



  const isSubscription = draft.offer_type === 'dental_trial'

  const isSurvey = draft.offer_type === 'survey_credits'

  const isInterview = draft.offer_type === 'interview_credits'



  useEffect(() => {

    let cancelled = false

    ;(async () => {

      setLoading(true)

      try {

        const planRows = await apiFetch('/admin/products/assignable-plans?product_line=core')

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



  const previewName = useMemo(() => {

    if (draft.name.trim()) return draft.name.trim()

    if (isSurvey) return `Promo · ${draft.survey_contacts_included} survey contacts`

    if (isInterview) return `Promo · ${draft.interview_contacts_included} interviews`

    return selectedPlan ? `Promo · ${selectedPlan.name}` : 'New promo offer'

  }, [draft, isSurvey, isInterview, selectedPlan])



  const previewCode = draft.code.trim().toUpperCase() || 'AUTO-GENERATED'



  const save = async () => {

    if (isSubscription && !draft.plan_code) {

      setError('Choose a subscription plan.')

      return

    }

    if (isSurvey && Number(draft.survey_contacts_included) <= 0) {

      setError('Enter how many free survey contacts to include.')

      return

    }

    if (isInterview && Number(draft.interview_contacts_included) <= 0) {

      setError('Enter how many free interviews to include.')

      return

    }

    setSaving(true)

    setError('')

    try {

      const payload = {

        name: draft.name.trim() || undefined,

        code: draft.code.trim() || undefined,

        offer_type: draft.offer_type,

        max_redemptions: Number(draft.max_redemptions) || 1,

        expires_in_days: Number(draft.expires_in_days) || 30,

        prospect_name: draft.prospect_name.trim() || undefined,

        prospect_email: draft.prospect_email.trim() || undefined,

        prospect_phone: draft.prospect_phone.trim() || undefined,

      }

      if (isSubscription) {

        payload.plan_code = draft.plan_code

        payload.trial_days = Number(draft.trial_days) || 0

      }

      if (isSurvey) {

        payload.survey_contacts_included = Number(draft.survey_contacts_included) || 0

      }

      if (isInterview) {

        payload.interview_contacts_included = Number(draft.interview_contacts_included) || 0

      }

      await apiFetch('/admin/promo-offers', { method: 'POST', body: JSON.stringify(payload) })

      navigate('/marketing/promo-offers?created=1', { replace: true })

    } catch (e) {

      setError(e?.message || 'Could not create promo')

    } finally {

      setSaving(false)

    }

  }



  const canSave =

    (isSubscription && plans.length) ||

    (isSurvey && Number(draft.survey_contacts_included) > 0) ||

    (isInterview && Number(draft.interview_contacts_included) > 0)



  if (loading) return <p className='muted' style={{ padding: 24 }}>Loading plans…</p>



  return (

    <>

      <div className='pageTop'>

        <div>

          <Link to='/marketing/promo-offers' className='muted' style={{ fontSize: 13 }}>

            ← Back to promo offers

          </Link>

          <h1 style={{ marginTop: 8 }}>New promo offer</h1>

          <p className='muted'>

            Create a signup code for new customers — subscription trial, free survey contacts, or free interviews.

          </p>

        </div>

        <div className='actions'>

          <Link className='btn soft' to='/marketing/promo-offers'>

            Cancel

          </Link>

          <button type='button' className='btn primary' disabled={saving || !canSave} onClick={save}>

            {saving ? 'Creating…' : 'Create promo'}

          </button>

        </div>

      </div>



      {error ? <div className='note noteWarn'>{error}</div> : null}

      {isSubscription && !plans.length ? (

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

                <h3>Offer type</h3>

                <div className='muted packageMeta'>What the new customer receives after signup</div>

              </div>

            </div>

            <div className='cardBody adminPackageForm'>

              <label className='label'>

                Promo type

                <select

                  className='input'

                  value={draft.offer_type}

                  onChange={(e) => setDraft({ ...draft, offer_type: e.target.value })}

                >

                  {OFFER_TYPES.map((opt) => (

                    <option key={opt.value} value={opt.value}>

                      {opt.label}

                    </option>

                  ))}

                </select>

              </label>

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

                    placeholder={isSurvey ? 'Summer survey trial' : isInterview ? 'Interview starter pack' : 'Summer trial — Dental Pro'}

                  />

                </label>

              </div>

            </div>

          </section>



          {isSubscription ? (

            <section className='card adminPackageEditor'>

              <div className='cardHead'>

                <div>

                  <h3>Subscription plan</h3>

                  <div className='muted packageMeta'>Monthly plan and trial applied at signup</div>

                </div>

              </div>

              <div className='cardBody adminPackageForm'>

                <label className='label'>

                  Plan

                  <PlanPickerSelect
                    productLine="core"
                    value={draft.plan_code}
                    onChange={(code) => setDraft({ ...draft, plan_code: code })}
                    disabled={loading}
                  />

                </label>

                {selectedPlan ? (

                  <div className='promoPlanSummary'>

                    <div>

                      <strong>{selectedPlan.name}</strong>

                      <span className='muted'>{limitsPreview(selectedPlan)}</span>

                    </div>

                    <span className='productPrice'>

                      {selectedPlan.price_display || '—'}

                      <span> / month after trial</span>

                    </span>

                  </div>

                ) : null}

              </div>

            </section>

          ) : null}



          {isSurvey ? (

            <section className='card adminPackageEditor'>

              <div className='cardHead'>

                <div>

                  <h3>Survey credits</h3>

                  <div className='muted packageMeta'>Free survey contacts granted when the new user signs up</div>

                </div>

              </div>

              <div className='cardBody adminPackageForm'>

                <label className='label'>

                  Free survey contacts

                  <input

                    className='input'

                    type='number'

                    min={1}

                    value={draft.survey_contacts_included}

                    onChange={(e) => setDraft({ ...draft, survey_contacts_included: e.target.value })}

                  />

                </label>

                <p className='muted' style={{ margin: 0, fontSize: 12 }}>

                  Example: 20 contacts = one survey campaign with up to 20 people, paid from promo credits in the dashboard.

                </p>

              </div>

            </section>

          ) : null}



          {isInterview ? (

            <section className='card adminPackageEditor'>

              <div className='cardHead'>

                <div>

                  <h3>Interview credits</h3>

                  <div className='muted packageMeta'>Free AI interview sessions granted when the new user signs up</div>

                </div>

              </div>

              <div className='cardBody adminPackageForm'>

                <label className='label'>

                  Free interviews

                  <input

                    className='input'

                    type='number'

                    min={1}

                    value={draft.interview_contacts_included}

                    onChange={(e) => setDraft({ ...draft, interview_contacts_included: e.target.value })}

                  />

                </label>

                <p className='muted' style={{ margin: 0, fontSize: 12 }}>

                  Example: 3 interviews = up to 3 candidates in one interview campaign from promo credits.

                </p>

              </div>

            </section>

          ) : null}



          <section className='card adminPackageEditor'>

            <div className='cardHead'>

              <div>

                <h3>Redemption rules</h3>

                <div className='muted packageMeta'>New-user signup only — one code per prospect</div>

              </div>

            </div>

            <div className='cardBody adminPackageForm'>

              <div className='adminPackageFormRow promoFormRowWide'>

                {isSubscription ? (

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

                ) : null}

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

                Credits or trial apply when admin approves signup (or auto-approve is on). Existing users cannot redeem these codes.

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

                <div className='muted packageMeta'>What the new customer will see on signup</div>

              </div>

            </div>

            <div className='cardBody promoPreviewBody'>

              <div className='promoPreviewHero'>

                <span className='productAvatar'>

                  <i className={`ti ${isSurvey ? 'ti-clipboard-list' : isInterview ? 'ti-briefcase' : 'ti-ticket'}`} />

                </span>

                <div>

                  <strong>{previewName}</strong>

                  <code className='productCode' style={{ marginTop: 8, display: 'inline-block' }}>

                    {previewCode}

                  </code>

                </div>

              </div>

              <ul className='promoPreviewList'>

                {isSubscription ? (

                  <>

                    <li>

                      <i className='ti ti-credit-card' />

                      Plan: <strong>{selectedPlan?.name || draft.plan_code || '—'}</strong>

                    </li>

                    <li>

                      <i className='ti ti-clock' />

                      {Number(draft.trial_days || 0) > 0 ? `${draft.trial_days}-day free trial` : 'No trial — billed immediately'}

                    </li>

                  </>

                ) : null}

                {isSurvey ? (

                  <li>

                    <i className='ti ti-clipboard-list' />

                    <strong>{draft.survey_contacts_included}</strong> free survey contacts

                  </li>

                ) : null}

                {isInterview ? (

                  <li>

                    <i className='ti ti-briefcase' />

                    <strong>{draft.interview_contacts_included}</strong> free interviews

                  </li>

                ) : null}

                <li>

                  <i className='ti ti-users' />

                  Up to {draft.max_redemptions} new signup{Number(draft.max_redemptions) === 1 ? '' : 's'}

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

              <button type='button' className='btn primary' style={{ width: '100%' }} disabled={saving || !canSave} onClick={save}>

                {saving ? 'Creating…' : 'Create promo offer'}

              </button>

            </div>

          </aside>

        </div>

      </div>

    </>

  )

}


