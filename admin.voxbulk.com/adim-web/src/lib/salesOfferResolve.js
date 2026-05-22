export function resolveTemplateForLead(templates, settings, outcome, task) {
  const cats = ['subscription', 'survey', 'interview']
  let recommended = String(outcome?.recommended_offer || '').toLowerCase()
  if (!cats.includes(recommended)) {
    const interest = `${task?.interest_summary || ''} ${task?.sales_intent || ''} ${outcome?.outcome_summary || ''}`.toLowerCase()
    if (interest.includes('interview') || interest.includes('focus group')) recommended = 'interview'
    else if (interest.includes('survey') || interest.includes('questionnaire')) recommended = 'survey'
    else recommended = 'subscription'
  }

  const mappedId = {
    subscription: settings?.sales_template_subscription_id,
    survey: settings?.sales_template_survey_id,
    interview: settings?.sales_template_interview_id,
  }[recommended]

  const active = (templates || []).filter((t) => t.is_active)
  if (mappedId) {
    const hit = active.find((t) => t.id === mappedId)
    if (hit) return { category: recommended, template: hit }
  }

  const typeByCat = {
    subscription: 'dental_trial',
    survey: 'survey_credits',
    interview: 'interview_credits',
  }
  const hit = active.find((t) => t.offer_type === typeByCat[recommended])
  return { category: recommended, template: hit || active[0] || null }
}

export function templateSummary(template) {
  if (!template) return 'No template configured'
  if (template.offer_type === 'survey_credits') return `${template.survey_contacts_included} survey contacts`
  if (template.offer_type === 'interview_credits') return `${template.interview_contacts_included} interviews`
  return `${template.plan_code || 'plan'} · ${template.trial_days} day trial`
}
