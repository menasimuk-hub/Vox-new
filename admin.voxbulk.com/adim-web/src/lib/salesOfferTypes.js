export const SALES_OFFER_TYPES = [
  {
    value: 'dental_trial',
    label: 'Subscription trial',
    blurb: 'Plan + trial days after signup',
    icon: 'ti-credit-card',
  },
  {
    value: 'survey_credits',
    label: 'Free surveys',
    blurb: 'Survey contacts credited on signup',
    icon: 'ti-clipboard-list',
  },
  {
    value: 'interview_credits',
    label: 'Free interviews',
    blurb: 'Interview contacts credited on signup',
    icon: 'ti-users',
  },
]

export function categoryLabel(category) {
  if (category === 'survey') return 'Free surveys'
  if (category === 'interview') return 'Free interviews'
  return 'Subscription trial'
}

export function offerTypeLabel(value) {
  return SALES_OFFER_TYPES.find((t) => t.value === value)?.label || value
}

export function offerSummary({ offerType, planCode, trialDays, surveyContacts, interviewContacts, plans = [] }) {
  if (offerType === 'survey_credits') {
    return `${surveyContacts} free survey contact${Number(surveyContacts) === 1 ? '' : 's'}`
  }
  if (offerType === 'interview_credits') {
    return `${interviewContacts} free interview${Number(interviewContacts) === 1 ? '' : 's'}`
  }
  const plan = plans.find((p) => p.code === planCode)
  const planName = plan?.name || planCode || 'Plan'
  return `${planName} · ${trialDays}-day trial`
}
