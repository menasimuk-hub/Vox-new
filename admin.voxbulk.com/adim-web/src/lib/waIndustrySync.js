const PUSH_BATCH = 10

export const EMPTY_INDUSTRY_SYNC_JOB = {
  open: false,
  title: '',
  dryRun: false,
  steps: [],
  phase: 'running',
  summaryRows: [],
  tables: {},
  message: '',
  error: '',
  reportPath: '',
  progressPct: 0,
}

export function createIndustrySyncJob(title) {
  return {
    ...EMPTY_INDUSTRY_SYNC_JOB,
    open: true,
    title,
    steps: [
      { id: 'push', label: '1. Push changed templates to Meta', status: 'pending', detail: '' },
      { id: 'pull', label: '2. Pull status from Meta', status: 'pending', detail: '' },
    ],
    phase: 'running',
    tables: { sync_log: [], pushed: [], refreshed: [], push_failed: [] },
    progressPct: 0,
  }
}

export function flattenIndustryPushBatch(summary) {
  const push = summary?.push || summary
  return {
    content_updated: Number(push.content_updated ?? push.pushed ?? 0),
    refreshed: Number(push.refreshed ?? 0),
    linked: Number(push.linked ?? 0),
    skipped: Number(push.skipped ?? 0),
    error_count: Number(push.error_count ?? summary?.error_count ?? 0),
    errors: push.errors || summary?.errors || [],
    results: push.results || summary?.results || [],
    total: Number(push.total ?? summary?.total ?? 0),
    processed: Number(push.processed ?? summary?.processed ?? 0),
    has_more: Boolean(push.has_more ?? summary?.has_more),
    next_offset: Number(push.next_offset ?? summary?.next_offset ?? 0),
    message: push.message || summary?.message || '',
    pull: summary?.pull,
    ok: summary?.ok !== false && push?.ok !== false,
  }
}

function outcomeLabel(outcome) {
  const map = {
    content_updated: 'Updated on Meta',
    status_refreshed: 'Status refreshed',
    linked: 'Linked',
    skipped: 'Skipped',
    failed: 'Failed',
  }
  return map[outcome] || outcome || '—'
}

function buildSyncTables(acc) {
  const syncLog = []
  for (const r of acc.results || []) {
    syncLog.push({
      name: r.template_name || r.label,
      outcome: outcomeLabel(r.outcome),
      product: r.sync_branch || r.message || r.reason || '—',
    })
  }
  for (const e of acc.errors || []) {
    syncLog.push({
      name: e.template_name || e.label,
      outcome: 'Failed',
      product: e.error || 'Push failed',
    })
  }

  const pushed = (acc.results || [])
    .filter((r) => r.outcome === 'content_updated')
    .map((r) => ({
      name: r.template_name || r.label,
      language: r.sync_branch || '—',
      product: 'updated',
    }))

  const refreshed = (acc.results || [])
    .filter((r) => r.outcome === 'status_refreshed')
    .map((r) => ({
      name: r.template_name || r.label,
      language: r.sync_branch || '—',
      product: 'status only',
    }))

  const failedRows = (acc.errors || []).map((e) => ({
    name: e.template_name || e.label,
    product: 'survey',
    error: e.error,
  }))

  return { sync_log: syncLog, pushed, refreshed, push_failed: failedRows }
}

function buildSummaryRows(acc) {
  const processed = (acc.results?.length || 0) + (acc.errors?.length || 0)
  const remaining = Math.max(0, (acc.total || 0) - processed)
  return [
    { metric: 'Total templates', count: acc.total || 0 },
    { metric: 'Processed so far', count: processed },
    { metric: 'Remaining in queue', count: remaining },
    { metric: 'Content updated on Meta', count: acc.content_updated || 0 },
    { metric: 'Status refreshed only', count: acc.refreshed || 0 },
    { metric: 'Skipped', count: acc.skipped || 0 },
    { metric: 'Failed', count: acc.error_count || 0 },
  ]
}

export class IndustrySyncCancelledError extends Error {
  constructor() {
    super('Sync stopped')
    this.name = 'IndustrySyncCancelledError'
  }
}

function throwIfCancelled(signal) {
  if (signal?.aborted) throw new IndustrySyncCancelledError()
}

export function buildIndustrySyncJobProgress(acc, { running = true, industryName = '' } = {}) {
  const processed = (acc.results?.length || 0) + (acc.errors?.length || 0)
  const total = acc.total || 0
  const progressPct = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0
  const tables = buildSyncTables(acc)
  return {
    phase: running ? 'running' : acc.error_count ? 'error' : 'done',
    summaryRows: buildSummaryRows(acc),
    tables,
    progressPct,
    message: running
      ? `Syncing ${industryName || 'industry'}… ${processed}/${total || '?'} templates`
      : acc.error_count
        ? `Synced ${industryName}: ${acc.content_updated} updated, ${acc.error_count} failed`
        : `Synced ${industryName}: ${acc.content_updated} template(s) updated on Meta`,
    error: acc.error_count
      ? acc.errors.map((e) => `${e.template_name || e.label}: ${e.error}`).join('\n')
      : '',
  }
}

export function buildIndustrySyncJobCancelled(acc, { industryName = '' } = {}) {
  const processed = (acc.results?.length || 0) + (acc.errors?.length || 0)
  const base = buildIndustrySyncJobProgress(acc, { running: false, industryName })
  return {
    ...base,
    phase: 'cancelled',
    message: `Stopped — ${processed} of ${acc.total || '?'} template(s) processed for ${industryName || 'industry'}`,
    error: '',
  }
}

export async function runWaIndustryPushAll(apiFetch, industryId, { onProgress, signal } = {}) {
  const acc = {
    content_updated: 0,
    refreshed: 0,
    linked: 0,
    skipped: 0,
    error_count: 0,
    errors: [],
    results: [],
    total: 0,
    pull: null,
    ok: true,
  }
  let offset = 0
  let batchNum = 0
  const path = `/admin/wa-survey/industries/${encodeURIComponent(industryId)}/templates/push-all`

  for (;;) {
    throwIfCancelled(signal)
    batchNum += 1
    onProgress?.({ batchNum, offset, step: 'push', acc: { ...acc }, running: true })
    const summary = await apiFetch(path, {
      method: 'POST',
      body: JSON.stringify({
        offset,
        limit: PUSH_BATCH,
        force_push: false,
        force_utility_category: false,
        phase: 'push',
      }),
      timeoutMs: 300000,
      quietNetworkHint: true,
      signal,
    })
    const flat = flattenIndustryPushBatch(summary)
    acc.content_updated += flat.content_updated
    acc.refreshed += flat.refreshed
    acc.linked += flat.linked
    acc.skipped += flat.skipped
    acc.error_count += flat.error_count
    acc.errors.push(...flat.errors)
    acc.results.push(...flat.results)
    acc.total = flat.total || acc.total
    acc.ok = acc.ok && flat.ok
    onProgress?.({ batchNum, offset, flat, acc: { ...acc }, done: !flat.has_more, running: flat.has_more })
    if (!flat.has_more) break
    offset = flat.next_offset
  }

  throwIfCancelled(signal)
  onProgress?.({ step: 'pull', acc: { ...acc }, running: true })
  try {
    const pullSummary = await apiFetch(path, {
      method: 'POST',
      body: JSON.stringify({ phase: 'pull' }),
      timeoutMs: 300000,
      quietNetworkHint: true,
      signal,
    })
    acc.pull = pullSummary?.pull || pullSummary
    acc.ok = acc.ok && pullSummary?.ok !== false
  } catch (e) {
    if (signal?.aborted || e?.name === 'IndustrySyncCancelledError') throwIfCancelled(signal)
    acc.ok = false
    acc.error_count += 1
    acc.errors.push({
      template_name: '(pull status)',
      error: e?.message || 'Pull status from Meta failed',
    })
  }
  onProgress?.({ step: 'pull', acc: { ...acc }, done: true, running: false })

  return acc
}

export function buildIndustrySyncJobDone(acc, industryName) {
  return buildIndustrySyncJobProgress(acc, { running: false, industryName })
}

export async function runWaFeedbackIndustryPushAll(apiFetch, industryId, { onProgress, signal, batchSize = 10 } = {}) {
  const acc = {
    content_updated: 0,
    refreshed: 0,
    linked: 0,
    skipped: 0,
    error_count: 0,
    errors: [],
    results: [],
    total: 0,
    pull: null,
    ok: true,
  }
  let offset = 0
  let batchNum = 0
  const path = `/admin/customer-feedback/industries/${encodeURIComponent(industryId)}/sync-telnyx`

  for (;;) {
    throwIfCancelled(signal)
    batchNum += 1
    onProgress?.({ batchNum, offset, step: 'push', acc: { ...acc }, running: true })
    const summary = await apiFetch(path, {
      method: 'POST',
      body: JSON.stringify({
        offset,
        limit: batchSize,
        phase: 'push',
      }),
      timeoutMs: 300000,
      quietNetworkHint: true,
      signal,
    })
    const flat = flattenIndustryPushBatch(summary)
    acc.content_updated += flat.content_updated
    acc.refreshed += flat.refreshed
    acc.linked += flat.linked
    acc.skipped += flat.skipped
    acc.error_count += flat.error_count
    acc.errors.push(...flat.errors)
    acc.results.push(...flat.results)
    acc.total = flat.total || acc.total
    acc.ok = acc.ok && flat.ok
    onProgress?.({ batchNum, offset, flat, acc: { ...acc }, done: !flat.has_more, running: flat.has_more, step: 'push' })
    if (!flat.has_more) break
    offset = flat.next_offset
  }

  throwIfCancelled(signal)
  onProgress?.({ step: 'pull', acc: { ...acc }, running: true })
  try {
    const pullSummary = await apiFetch(path, {
      method: 'POST',
      body: JSON.stringify({ phase: 'pull' }),
      timeoutMs: 300000,
      quietNetworkHint: true,
      signal,
    })
    acc.pull = pullSummary?.pull || pullSummary
    acc.ok = acc.ok && pullSummary?.ok !== false
  } catch (e) {
    if (signal?.aborted || e?.name === 'IndustrySyncCancelledError') throwIfCancelled(signal)
    acc.ok = false
    acc.error_count += 1
    acc.errors.push({
      template_name: '(pull status)',
      error: e?.message || 'Pull status from Meta failed',
    })
  }
  onProgress?.({ step: 'pull', acc: { ...acc }, done: true, running: false })

  return acc
}
