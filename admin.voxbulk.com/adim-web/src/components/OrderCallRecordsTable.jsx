import React from 'react'
import { formatDurationSeconds } from '../lib/serviceOrderAdmin'

export default function OrderCallRecordsTable({ order }) {
  const recipients = Array.isArray(order?.recipients) ? order.recipients : []
  const settlementCalls = order?.billing_settlement?.call_records
  const rows =
    Array.isArray(settlementCalls) && settlementCalls.length
      ? settlementCalls.map((c) => ({
          key: c.recipient_id,
          name: c.name,
          phone: c.phone,
          call_type: c.call_type,
          duration_seconds: c.duration_seconds,
          billable_minutes: c.billable_minutes,
          status: c.status,
          hangup_cause: c.hangup_cause,
        }))
      : recipients.map((r) => ({
          key: r.id,
          name: r.name,
          phone: r.phone,
          call_type: r.call_type,
          duration_seconds: r.duration_seconds,
          billable_minutes: r.billable_minutes,
          status: r.status,
          hangup_cause: r.hangup_cause,
        }))

  const phoneRows = rows.filter(
    (r) =>
      r.duration_seconds != null ||
      r.billable_minutes != null ||
      ['completed', 'no_answer', 'busy', 'failed', 'opted_out', 'calling'].includes(
        String(r.status || '').toLowerCase(),
      ),
  )

  if (!phoneRows.length) {
    return (
      <div className="note" style={{ marginTop: 12 }}>
        <strong>Call records</strong>
        <p className="muted" style={{ margin: '8px 0 0' }}>No call attempts recorded yet.</p>
      </div>
    )
  }

  return (
    <div className="note" style={{ marginTop: 12 }}>
      <strong>Call records</strong>
      <p className="muted" style={{ margin: '6px 0 10px', fontSize: 13 }}>
        Telnyx talk time per contact. Billable minutes round up (50s → 1 min, 1m 05s → 2 min).
      </p>
      <div className="tableWrap">
        <table className="table runningSurveyContactsTable">
          <thead>
            <tr>
              <th>Contact</th>
              <th>Phone</th>
              <th>Call type</th>
              <th>Duration</th>
              <th>Billable min</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {phoneRows.map((r) => (
              <tr key={r.key}>
                <td>{r.name || '—'}</td>
                <td>{r.phone || '—'}</td>
                <td>{r.call_type || '—'}</td>
                <td>{formatDurationSeconds(r.duration_seconds)}</td>
                <td>{r.billable_minutes != null ? r.billable_minutes : '—'}</td>
                <td>{r.status || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
