export const INTERVIEW_VAR_LABELS = {
  interview_email_sent: ['First name', 'Position title', 'Company name', 'Careers email'],
  interview_booking_confirm: ['First name', 'Position title', 'Booking date', 'Booking time'],
  interview_booking_cancel: ['First name', 'Position title', 'Company name', 'Booking date', 'Booking time'],
  interview_job_closed: ['First name', 'Position title', 'Company name'],
}

export function interviewVarLabels(salesTemplateKey) {
  return INTERVIEW_VAR_LABELS[salesTemplateKey] || ['Variable 1', 'Variable 2', 'Variable 3', 'Variable 4']
}

export { ensureExampleValues, substituteTemplateVars, varIndexesFromText } from './waSurveyTemplateVars'
