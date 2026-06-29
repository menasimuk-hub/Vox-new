import React, { useEffect, useState } from 'react'
import { currencySymbol, money } from '../lib/billingAdminUtils'

export default function RefundResolveModal({ row, open, onClose, onSubmit, busy }) {
  const [action, setAction] = useState('approve_wallet')
  const [note, setNote] = useState('')
  const [externalPence, setExternalPence] = useState('')

  useEffect(() => {
    if (!open || !row) return
    setAction('approve_wallet')
    setNote('')
    const defaultMajor = Number(row.calculated_unused_value_pence || 0) / 100
    setExternalPence(defaultMajor > 0 ? defaultMajor.toFixed(2) : '')
  }, [open, row])

  if (!open || !row) return null

  const currency = row.billing_currency || 'GBP'
  const sym = currencySymbol(currency)
  const provider = String(row.source_payment_provider || 'unknown').toLowerCase()
  const isStripe = provider === 'stripe' && String(row.source_payment_reference || '').startsWith('pi_')
  const isGc = provider === 'gocardless'

  const handleSubmit = (e) => {
    e.preventDefault()
    const payload = { admin_notes: note.trim() }
    if (action === 'approve_wallet') {
      onSubmit(row, 'approved', { ...payload, issue_wallet_credit: true })
    } else if (action === 'mark_external') {
      const major = Number(externalPence)
      if (!Number.isFinite(major) || major <= 0) return
      onSubmit(row, 'completed', { ...payload, approved_external_refund_pence: Math.round(major * 100) })
    } else if (action === 'reject') {
      onSubmit(row, 'rejected', payload)
    }
  }

  return (
    <div className="occ-modal-overlay open" role="presentation" onClick={onClose}>
      <div className="occ-modal" role="dialog" onClick={(e) => e.stopPropagation()}>
        <div className="occ-modal-head">
          <h3>Resolve refund review</h3>
          <button type="button" className="occ-modal-close" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="occ-modal-body" style={{ display: 'grid', gap: 12 }}>
            <div>
              <strong>{row.organisation_name}</strong>
              <div className="muted" style={{ fontSize: 12 }}>{row.org_email}</div>
            </div>
            <div className="occ-info-grid">
              <div>
                <span className="occ-info-row-label">Unused value</span>
                <span className="occ-info-row-value">{money(row.calculated_unused_value_pence, currency)}</span>
              </div>
              <div>
                <span className="occ-info-row-label">Requested type</span>
                <span className="occ-info-row-value">{row.requested_refund_type || '—'}</span>
              </div>
              <div>
                <span className="occ-info-row-label">Provider</span>
                <span className="occ-info-row-value">{provider}</span>
              </div>
              <div>
                <span className="occ-info-row-label">Payment ref</span>
                <span className="occ-info-row-value" style={{ wordBreak: 'break-all' }}>{row.source_payment_reference || '—'}</span>
              </div>
            </div>
            {isGc ? (
              <div className="note" style={{ fontSize: 12 }}>
                GoCardless: process payout in GoCardless dashboard, then choose Mark external refunded.
              </div>
            ) : null}
            {isStripe ? (
              <div className="note" style={{ fontSize: 12 }}>
                Stripe: Mark external refunded will attempt auto-refund when payment ref is a PaymentIntent.
              </div>
            ) : null}
            <label style={{ display: 'grid', gap: 4 }}>
              <span>Action</span>
              <select className="input" value={action} onChange={(e) => setAction(e.target.value)}>
                <option value="approve_wallet">Approve wallet credit</option>
                <option value="mark_external">Mark external refunded</option>
                <option value="reject">Reject</option>
              </select>
            </label>
            {action === 'mark_external' ? (
              <label style={{ display: 'grid', gap: 4 }}>
                <span>External refund amount ({sym})</span>
                <input className="input" type="number" step="0.01" min="0" value={externalPence} onChange={(e) => setExternalPence(e.target.value)} />
              </label>
            ) : null}
            <label style={{ display: 'grid', gap: 4 }}>
              <span>Admin note</span>
              <textarea className="input" rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Required for audit trail" />
            </label>
          </div>
          <div className="occ-modal-foot">
            <button type="button" className="btn soft" onClick={onClose} disabled={busy}>Cancel</button>
            <button type="submit" className="btn primary" disabled={busy || !note.trim()}>
              {busy ? 'Saving…' : 'Confirm'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
