export function surveyRespondedCount(report) {
  if (!report || typeof report !== 'object') return 0
  return Number(report.completed ?? report.sent ?? 0)
}

export function surveyFailedCount(report) {
  if (!report || typeof report !== 'object') return 0
  return Number(report.failed ?? 0)
}
