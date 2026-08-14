export const SALES_OFFER_TYPES = [
  {
    value: 'subscription_trial',
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
  {
    value: 'expo_trial',
    label: 'Expo trial',
    blurb: 'Expo day pass / trial',
    icon: 'ti-building-store',
  },
  {
    value: 'smart_card_trial',
    label: 'Smart Card — 1 month free',
    blurb: '1 month free then pay per seat (card at signup, charged after trial)',
    icon: 'ti-id',
  },
  {
    value: 'smart_card_credit',
    label: 'Smart Card credit',
    blurb: 'Smart Card seat credit (legacy)',
    icon: 'ti-id',
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
  if (offerType === 'smart_card_trial' || offerType === 'smart_card_credit') {
    const days = Number(trialDays) || 30
    return `Smart Card QR · ${days}-day free trial then pay per seat`
  }
  const plan = plans.find((p) => p.code === planCode)
  const planName = plan?.name || planCode || 'Plan'
  return `${planName} · ${trialDays}-day trial`
}
