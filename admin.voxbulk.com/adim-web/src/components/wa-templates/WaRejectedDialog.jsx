import React, { useState } from 'react'
import { AlertTriangle, RefreshCw, X } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import { apiFetch } from '../../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../../lib/waSurveyFeedback'

export default function WaRejectedDialog({ row, open, onClose, onDone, onError }) {
  const [busy, setBusy] = useState(false)
  if (!open || !row) return null

  const reason =
    row.rejectionReason ||
    row.raw?.rejection_reason ||
    row.raw?.last_push_error ||
    'No rejection reason was stored. Meta may have rejected marketing language, missing examples, or a duplicate name.'

  const body =
    row.raw?.body_preview ||
    row.raw?.body ||
    row.raw?.body_text ||
    ''

  const regenerate = async () => {
    setBusy(true)
    try {
      const product = row.product || row.raw?.product
      let result
      if (product === 'interview') {
        // Interview rows share the same template table — use survey regenerate path.
        result = await apiFetch(`/admin/wa-survey/templates/${row.id}/regenerate`, {
          method: 'POST',
          timeoutMs: 180000,
          quietNetworkHint: true,
        })
      } else if (product === 'feedback') {
        result = await apiFetch(`/admin/customer-feedback/wa-templates/${row.id}/push`, {
          method: 'POST',
          timeoutMs: 180000,
          quietNetworkHint: true,
        })
      } else {
        result = await apiFetch(`/admin/wa-survey/templates/${row.id}/regenerate`, {
          method: 'POST',
          timeoutMs: 180000,
          quietNetworkHint: true,
        })
      }
      onDone?.(formatActionSuccess(result, 'Template regenerated and submitted to Meta').message)
      onClose?.()
    } catch (e) {
      onError?.(formatWaSurveyError(e, 'Regenerate failed').detailText || e?.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4" role="presentation" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-xl border bg-surface p-4 shadow-lg"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-destructive/10 text-destructive">
            <AlertTriangle className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold">Rejected template</div>
            <div className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground" title={row.name}>
              {row.name}
            </div>
          </div>
          <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={onClose}>
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>

        <div className="mt-3 space-y-3 text-xs">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Why Meta rejected it</div>
            <p className="mt-1 whitespace-pre-wrap rounded-md border border-destructive/20 bg-destructive/5 px-2.5 py-2 text-destructive">
              {reason}
            </p>
          </div>
          {body ? (
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Current body</div>
              <p className="mt-1 whitespace-pre-wrap rounded-md border bg-surface-muted/40 px-2.5 py-2 text-foreground">
                {body}
              </p>
            </div>
          ) : null}
          <p className="text-muted-foreground">
            Regenerate rewrites the body to avoid common rejection reasons, assigns a new Meta template name, and submits
            it again for approval.
          </p>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" size="sm" variant="ghost" className="h-8 text-xs" onClick={onClose} disabled={busy}>
            Close
          </Button>
          <Button type="button" size="sm" className="h-8 gap-1.5 text-xs" onClick={() => void regenerate()} disabled={busy}>
            <RefreshCw className={cn('h-3.5 w-3.5', busy && 'animate-spin')} />
            {busy ? 'Regenerating…' : 'Regenerate & sync to Meta'}
          </Button>
        </div>
      </div>
    </div>
  )
}
