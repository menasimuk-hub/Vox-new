import React, { useState } from 'react'
import { createPortal } from 'react-dom'
import { FileUp, Play, Search, Upload, X } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import { MetaSyncNamingNote } from './waTemplatesUi'
import { resolveApiUrl } from '../../lib/api'
import { readAdminAccessToken } from '../../lib/sessionStorage'

function buildImportUrl(product, industryId) {
  const path =
    product === 'feedback'
      ? `/admin/customer-feedback/industries/${encodeURIComponent(industryId)}/import-md`
      : `/admin/wa-survey/industries/${encodeURIComponent(industryId)}/import-md`
  return resolveApiUrl(path)
}

async function uploadIndustryMd({ product, industryId, file, fields, signal }) {
  const url = buildImportUrl(product, industryId)
  const form = new FormData()
  form.append('file', file)
  Object.entries(fields || {}).forEach(([k, v]) => form.append(k, String(v)))

  const token = readAdminAccessToken()
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(url, { method: 'POST', body: form, headers, signal })
  const rawText = await res.text()
  let data = {}
  try {
    data = rawText ? JSON.parse(rawText) : {}
  } catch {
    data = {}
  }
  if (!res.ok) {
    const detail = data?.detail
    let msg =
      typeof detail === 'string'
        ? detail
        : detail?.message || (Array.isArray(detail) ? detail.map((d) => d?.msg || JSON.stringify(d)).join('; ') : null)
    if (!msg && rawText && !rawText.trimStart().startsWith('<')) {
      msg = rawText.slice(0, 400)
    }
    if (!msg) {
      msg = `${res.status} ${res.statusText || 'Request failed'}`.trim()
    }
    throw new Error(msg)
  }
  return data
}

function DryRunReport({ result }) {
  if (!result) return null
  const summary = result.summary || {}
  return (
    <div className="mt-3 max-h-[40vh] space-y-3 overflow-y-auto rounded-md border bg-surface-muted/30 p-3 text-xs">
      <div className={cn('font-medium', result.ok ? 'text-success' : 'text-destructive')}>{result.message}</div>
      <div>
        <div className="mb-1 font-semibold uppercase tracking-wider text-muted-foreground">Summary</div>
        <ul className="space-y-0.5">
          {Object.entries(summary).map(([k, v]) => (
            <li key={k} className="flex justify-between gap-2">
              <span className="text-muted-foreground">{k.replace(/_/g, ' ')}</span>
              <span className="font-mono tabular-nums">{String(v)}</span>
            </li>
          ))}
        </ul>
      </div>
      {(result.plan_steps || []).length ? (
        <div>
          <div className="mb-1 font-semibold uppercase tracking-wider text-muted-foreground">What will happen</div>
          <ol className="list-decimal space-y-1 pl-4">
            {result.plan_steps.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>
        </div>
      ) : null}
      {(result.errors || []).length ? (
        <div>
          <div className="mb-1 font-semibold text-destructive">Errors ({result.errors.length})</div>
          <ul className="list-disc space-y-0.5 pl-4 text-destructive">
            {result.errors.slice(0, 20).map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {(result.warnings || []).length ? (
        <div>
          <div className="mb-1 font-semibold text-warning-foreground">Warnings ({result.warnings.length})</div>
          <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
            {result.warnings.slice(0, 15).map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {(result.topics || []).slice(0, 8).map((t) => (
        <div key={t.slug || t.name} className="rounded border bg-background p-2">
          <div className="font-medium">
            {t.index}. {t.name}{' '}
            <span className="text-muted-foreground">({t.language_count} langs · {t.action})</span>
          </div>
          <div className="mt-0.5 text-muted-foreground">{t.english_body_preview}</div>
          <div className="mt-0.5 font-mono text-[10px]">Buttons: {(t.english_buttons || []).join(' / ')}</div>
          {t.meta_name_preview ? (
            <div className="mt-1 truncate font-mono text-[10px] text-muted-foreground" title={t.meta_name_preview}>
              Meta: {t.meta_name_preview}
            </div>
          ) : null}
        </div>
      ))}
      {(result.topics || []).length > 8 ? (
        <p className="text-muted-foreground">… and {result.topics.length - 8} more topics</p>
      ) : null}
    </div>
  )
}

export default function WaIndustryJobPanel({
  open,
  product,
  industry,
  onClose,
  onDryRunDone,
  onImportDone,
  onStartSync,
  busy = false,
  lastDryRun = null,
}) {
  const [file, setFile] = useState(null)
  const [replace, setReplace] = useState(false)
  const [createMissing, setCreateMissing] = useState(true)
  const [syncAfter, setSyncAfter] = useState(false)
  const [batchSize, setBatchSize] = useState(5)
  const [delaySec, setDelaySec] = useState(15)
  const [working, setWorking] = useState(false)
  const [localDryRun, setLocalDryRun] = useState(lastDryRun)
  const [error, setError] = useState('')

  if (!open || !industry) return null

  const feedbackOnly = product === 'feedback'

  const runDryRun = async () => {
    if (!file) {
      setError('Choose a Markdown file first')
      return
    }
    setError('')
    setWorking(true)
    try {
      const result = await uploadIndustryMd({
        product,
        industryId: industry.id,
        file,
        fields: {
          dry_run: true,
          replace,
          create_missing: createMissing,
          min_langs: 19,
        },
      })
      setLocalDryRun(result)
      onDryRunDone?.(result)
    } catch (e) {
      setError(e?.message || 'Validate failed')
    } finally {
      setWorking(false)
    }
  }

  const runImport = async () => {
    if (!file) {
      setError('Choose a Markdown file first')
      return
    }
    if (!localDryRun?.ok) {
      setError('Run Validate first — fix errors before import')
      return
    }
    setError('')
    setWorking(true)
    try {
      const result = await uploadIndustryMd({
        product,
        industryId: industry.id,
        file,
        fields: {
          dry_run: false,
          replace,
          create_missing: createMissing,
          min_langs: 19,
        },
      })
      onImportDone?.(result)
      if (syncAfter) {
        onStartSync?.({ batchSize, delaySec })
        onClose?.()
      }
    } catch (e) {
      setError(e?.message || 'Import failed')
    } finally {
      setWorking(false)
    }
  }

  const dialog = (
    <div className="fixed inset-0 z-[210] flex items-center justify-center bg-black/50 p-4" role="presentation">
      <div
        className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border bg-surface shadow-lg"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div>
            <h3 className="text-sm font-semibold">Industry actions — {industry.name}</h3>
            <p className="text-[11px] text-muted-foreground">
              Upload MD → Validate (dry-run) → Import → Sync to Meta (manual)
            </p>
          </div>
          <Button type="button" variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={onClose} disabled={working || busy}>
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {feedbackOnly ? (
            <MetaSyncNamingNote
              industrySlug={industry.slug}
              exampleMetaName={
                (localDryRun?.topics || []).find((t) => t.meta_name_preview)?.meta_name_preview || ''
              }
            />
          ) : (
            <p className="text-[11px] text-muted-foreground">
              Multi-language import is enabled for Customer Feedback. Survey uses single-language ABC blocks.
            </p>
          )}

          <label className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed bg-surface-muted/20 px-4 py-6 text-center">
            <FileUp className="h-8 w-8 text-muted-foreground" />
            <span className="text-xs font-medium">{file ? file.name : 'Choose .md template file'}</span>
            <input
              type="file"
              accept=".md,text/markdown"
              className="hidden"
              onChange={(e) => {
                setFile(e.target.files?.[0] || null)
                setLocalDryRun(null)
                setError('')
              }}
            />
          </label>

          <div className="grid grid-cols-1 gap-2 text-xs">
            <label className="flex items-start gap-2 rounded-md border border-border/60 bg-surface-muted/20 p-2">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={replace}
                onChange={(e) => setReplace(e.target.checked)}
              />
              <span>
                <span className="font-medium text-foreground">Replace all templates</span>
                <span className="mt-0.5 block text-muted-foreground">
                  Deletes every existing row (and tries Meta cleanup) then imports only what is in the file.
                  Use for a full refresh — not for adding one language.
                </span>
              </span>
            </label>
            {!replace ? (
              <p className="rounded-md border border-success/30 bg-success/5 px-2 py-1.5 text-success">
                Merge mode — keeps existing languages; adds missing ones (e.g. Turkish) and updates matching rows from
                the file.
              </p>
            ) : null}
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={createMissing} onChange={(e) => setCreateMissing(e.target.checked)} />
              Create missing topics
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={syncAfter} onChange={(e) => setSyncAfter(e.target.checked)} />
              Start Meta sync immediately after import
            </label>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <label className="block space-y-1 text-xs">
              <span className="text-muted-foreground">Batch size</span>
              <input
                type="number"
                min={1}
                max={20}
                className="h-8 w-full rounded-md border px-2"
                value={batchSize}
                onChange={(e) => setBatchSize(Number(e.target.value) || 5)}
              />
            </label>
            <label className="block space-y-1 text-xs">
              <span className="text-muted-foreground">Delay between batches (sec)</span>
              <input
                type="number"
                min={0}
                max={120}
                className="h-8 w-full rounded-md border px-2"
                value={delaySec}
                onChange={(e) => setDelaySec(Number(e.target.value) || 15)}
              />
            </label>
          </div>

          {error ? <p className="text-xs text-destructive">{error}</p> : null}
          <DryRunReport result={localDryRun} />
        </div>

        <div className="flex flex-wrap gap-2 border-t bg-surface px-4 py-3">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 gap-1 text-xs"
            disabled={working || busy || !file}
            onClick={() => void runDryRun()}
          >
            <Search className="h-3.5 w-3.5" /> Validate file (dry-run)
          </Button>
          <Button
            type="button"
            size="sm"
            variant="default"
            className="h-8 gap-1 text-xs"
            disabled={working || busy || !file || !localDryRun?.ok}
            onClick={() => void runImport()}
          >
            <Upload className="h-3.5 w-3.5" /> Import & replace
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 gap-1 text-xs ml-auto"
            disabled={working || busy}
            onClick={() => {
              onStartSync?.({ batchSize, delaySec })
              onClose?.()
            }}
          >
            <Play className="h-3.5 w-3.5" /> Sync to Meta only
          </Button>
        </div>
      </div>
    </div>
  )

  if (typeof document === 'undefined') return dialog
  return createPortal(dialog, document.body)
}
