/**
 * Deep link into the WA Survey flow simulator with prefilled survey type context.
 */
export function buildWaSurveySimulatorUrl({
  surveyTypeId,
  privacyMode = 'off',
  autoStart = true,
  industryId = '',
} = {}) {
  const params = new URLSearchParams()
  if (surveyTypeId) params.set('survey_type_id', surveyTypeId)
  if (privacyMode) params.set('privacy_mode', privacyMode)
  if (industryId) params.set('industry_id', industryId)
  if (autoStart) params.set('auto_start', '1')
  const qs = params.toString()
  return `/settings/wa-survey/simulator${qs ? `?${qs}` : ''}`
}
