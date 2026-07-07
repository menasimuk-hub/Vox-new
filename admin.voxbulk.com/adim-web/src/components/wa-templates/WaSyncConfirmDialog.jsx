import React from 'react'
import { createPortal } from 'react-dom'
import { Button } from '@/components/ui/Button'
import { syncProfileActionLabel } from '../../lib/waSyncProfile'

export default function WaSyncConfirmDialog({ open, title, action, profile, detail, onConfirm, onCancel }) {
  if (!open) return null
  const actionLabel = syncProfileActionLabel(profile, action || 'Sync')
  return createPortal(
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 p-4">
      <div
        className="w-full max-w-md rounded-lg border bg-surface shadow-lg"
        role="dialog"
        aria-modal="true"
        aria-labelledby="wa-sync-confirm-title"
      >
        <div className="border-b px-4 py-3">
          <h2 id="wa-sync-confirm-title" className="text-sm font-semibold">
            {title || 'Confirm sync'}
          </h2>
        </div>
        <div className="space-y-2 px-4 py-3 text-xs text-muted-foreground">
          <p>
            <span className="font-medium text-foreground">{actionLabel}</span>
            {profile?.label ? (
              <>
                {' '}
                using <span className="font-medium text-foreground">{profile.label}</span>
              </>
            ) : null}
            ?
          </p>
          {detail ? <p>{detail}</p> : null}
          <p className="text-[11px]">Templates stay global in the database — only the Meta/Telnyx destination changes.</p>
        </div>
        <div className="flex justify-end gap-2 border-t px-4 py-3">
          <Button type="button" variant="ghost" size="sm" className="h-8 text-xs" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" size="sm" className="h-8 text-xs" onClick={onConfirm}>
            {actionLabel}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
