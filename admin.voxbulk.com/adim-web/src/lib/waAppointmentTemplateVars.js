export const APPOINTMENT_VAR_LABELS = {
  appt_confirm_v1: ['First name', 'Appointment type', 'Date', 'Time'],
  appt_confirm_v2: ['First name', 'Appointment type', 'Date and time'],
  appt_reminder_v1: ['First name', 'Appointment type', 'Date', 'Time'],
  appt_reminder_v2: ['First name', 'Appointment type', 'Date'],
}

export function appointmentVarLabels(salesTemplateKey) {
  return APPOINTMENT_VAR_LABELS[salesTemplateKey] || ['Variable 1', 'Variable 2', 'Variable 3', 'Variable 4']
}

export { ensureExampleValues, substituteTemplateVars, varIndexesFromText } from './waSurveyTemplateVars'
