import React from 'react'
import { SALES_OFFER_TYPES, offerSummary } from '../lib/salesOfferTypes'

export default function SalesOfferTypePicker({
  offerType,
  onOfferTypeChange,
  offerPlan,
  onOfferPlanChange,
  offerTrialDays,
  onOfferTrialDaysChange,
  surveyContacts,
  onSurveyContactsChange,
  interviewContacts,
  onInterviewContactsChange,
  offerPlans = [],
  compact = false,
}) {
  const summary = offerSummary({
    offerType,
    planCode: offerPlan,
    trialDays: offerTrialDays,
    surveyContacts,
    interviewContacts,
    plans: offerPlans,
  })

  return (
    <div className={`salesOfferPicker${compact ? ' salesOfferPickerCompact' : ''}`}>
      <div className='salesOfferTypeGrid'>
        {SALES_OFFER_TYPES.map((type) => {
          const active = offerType === type.value
          return (
            <button
              key={type.value}
              type='button'
              className={`salesOfferTypeCard${active ? ' isActive' : ''}`}
              onClick={() => onOfferTypeChange(type.value)}
            >
              <span className='salesOfferTypeIcon'>
                <i className={`ti ${type.icon}`} />
              </span>
              <strong>{type.label}</strong>
              <span className='muted'>{type.blurb}</span>
            </button>
          )
        })}
      </div>

      <div className='salesOfferDetails'>
        {offerType === 'dental_trial' ? (
          <div className='salesOfferFields'>
            <label className='salesOfferField'>
              <span>Package</span>
              <select
                className='input inputCompact'
                value={offerPlan}
                onChange={(e) => {
                  const code = e.target.value
                  onOfferPlanChange(code)
                  const picked = offerPlans.find((p) => p.code === code)
                  if (picked?.trial_days_default) onOfferTrialDaysChange(picked.trial_days_default)
                }}
              >
                {offerPlans.length ? (
                  offerPlans.map((p) => (
                    <option key={p.code} value={p.code}>
                      {p.name} — £{(Number(p.price_gbp_pence || 0) / 100).toFixed(0)}
                    </option>
                  ))
                ) : (
                  <>
                    <option value='dental_1'>Dental P1 — £199</option>
                    <option value='dental_2'>Dental P2 — £299</option>
                  </>
                )}
              </select>
            </label>
            <label className='salesOfferField'>
              <span>Trial days</span>
              <input
                className='input inputCompact'
                type='number'
                min={1}
                max={90}
                value={offerTrialDays}
                onChange={(e) => onOfferTrialDaysChange(e.target.value)}
              />
            </label>
          </div>
        ) : null}

        {offerType === 'survey_credits' ? (
          <label className='salesOfferField'>
            <span>Free survey contacts</span>
            <input
              className='input inputCompact'
              type='number'
              min={1}
              max={9999}
              value={surveyContacts}
              onChange={(e) => onSurveyContactsChange(e.target.value)}
            />
          </label>
        ) : null}

        {offerType === 'interview_credits' ? (
          <label className='salesOfferField'>
            <span>Free interviews</span>
            <input
              className='input inputCompact'
              type='number'
              min={1}
              max={9999}
              value={interviewContacts}
              onChange={(e) => onInterviewContactsChange(e.target.value)}
            />
          </label>
        ) : null}

        <div className='salesOfferPreview'>
          <span className='muted'>Customer receives</span>
          <strong>{summary}</strong>
          <span className='muted'>A unique signup code is created for this lead.</span>
        </div>
      </div>
    </div>
  )
}
