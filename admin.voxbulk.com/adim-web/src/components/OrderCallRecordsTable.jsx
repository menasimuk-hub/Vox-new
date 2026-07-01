import React from 'react'
import { formatDurationSeconds, recipientSessionChannel } from '../lib/serviceOrderAdmin'

export default function OrderCallRecordsTable({ order, compact = false }) {
  const recipients = Array.isArray(order?.recipients) ? order.recipients : []
  const settlementCalls = order?.billing_settlement?.call_records
  const rows =
    Array.isArray(settlementCalls) && settlementCalls.length
      ? settlementCalls.map((c) => ({
          key: c.recipient_id,
          name: c.name,
          phone: c.phone,
          email: c.email,
          session_channel: c.call_channel || c.channel,
          call_type: c.call_type,
          duration_seconds: c.duration_seconds,
          billable_minutes: c.billable_minutes,
          retail_cost_display: c.retail_cost_display,
          operator_cost_display: c.operator_cost_display,
          margin_display: c.margin_display,
          status: c.status,
          hangup_cause: c.hangup_cause,
        }))
      : recipients.map((r) => ({
          key: r.id,
          name: r.name,
          phone: r.phone,
          email: r.email,
          session_channel: recipientSessionChannel(r, order),
          call_type: r.call_type,
          duration_seconds: r.duration_seconds,
          billable_minutes: r.billable_minutes,
          retail_cost_display: r.retail_cost_display,
          operator_cost_display: r.operator_cost_display,
          margin_display: r.margin_display,
          status: r.status,
          hangup_cause: r.hangup_cause,
        }))

  const sessionRows = rows.filter(
    (r) =>
      r.duration_seconds != null ||
      r.billable_minutes != null ||
      ['completed', 'no_answer', 'busy', 'failed', 'opted_out', 'calling', 'in_progress'].includes(
        String(r.status || '').toLowerCase(),
      ),
  )

  if (!sessionRows.length) {
    if (compact) {
      return <p className="order-billing-footnote">No call or meeting sessions recorded yet.</p>
    }
    return (
      <div className="note" style={{ marginTop: 12 }}>
        <strong>Sessions</strong>
        <p className="muted" style={{ margin: '8px 0 0' }}>No call or meeting sessions recorded yet.</p>
      </div>
    )
  }

  const table = (
    <div className="tableWrap">
      <table className={`table runningSurveyContactsTable${compact ? ' compact' : ''}`}>
        <thead>
          <tr>
            <th>Contact</th>
            <th>Phone</th>
            <th>Email</th>
            <th>Channel</th>
            <th>Type</th>
            <th>Duration</th>
            <th>Min</th>
            <th>R.cost</th>
            <th>O.cost</th>
            <th>Margin</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {sessionRows.map((r) => (
            <tr key={r.key}>
              <td>{r.name || '—'}</td>
              <td>{r.phone || '—'}</td>
              <td>{r.email || '—'}</td>
              <td>{r.session_channel || '—'}</td>
              <td>{r.call_type || '—'}</td>
              <td>{formatDurationSeconds(r.duration_seconds)}</td>
              <td>{r.billable_minutes != null ? r.billable_minutes : '—'}</td>
              <td className="occ-mono">{r.retail_cost_display || '—'}</td>
              <td className="occ-mono">{r.operator_cost_display || '—'}</td>
              <td className="occ-mono">{r.margin_display || '—'}</td>
              <td>{r.status || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )

  if (compact) {
    return (
      <div>
        <div className="order-billing-card-label" style={{ marginBottom: 6 }}>Sessions</div>
        {table}
      </div>
    )
  }

  return (
    <div className="note" style={{ marginTop: 12 }}>
      <strong>Sessions</strong>
      {table}
    </div>
  )
}
