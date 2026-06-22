import React, { useMemo } from 'react'
import {
  formatDurationSeconds,
  orderCallUsageSummary,
  orderEstimatedDurationMin,
} from '../lib/serviceOrderAdmin'
import OrderCallRecordsTable from './OrderCallRecordsTable'
import './orderAdminBilling.css'

function moneyMinor(pence, fallback = '—') {
  const n = Number(pence)
  if (!Number.isFinite(n)) return fallback
  return `£${(n / 100).toFixed(2)}`
}

function billingModeLabel(order, launch) {
  const phase = order.billing_phase || launch.billing_phase
  const method = String(launch.payment_method || order.payment_method || '').toLowerCase()
  if (phase === 'held') return 'PAYG hold (125%)'
  if (phase === 'pending_settlement') return 'Sub — settle after'
  if (phase === 'settled') return 'Settled'
  if (method.includes('allowance')) return 'Subscription'
  if (method.includes('gocardless') || method.includes('direct_debit')) return 'Direct Debit'
  if (method === 'wallet') return 'Wallet'
  return method || '—'
}

function MetricCard({ label, value, sub, mono }) {
  return (
    <div className="order-billing-card">
      <div className="order-billing-card-label">{label}</div>
      <div className={`order-billing-card-value${mono ? ' mono' : ''}`}>{value}</div>
      {sub ? <div className="order-billing-card-sub">{sub}</div> : null}
    </div>
  )
}

export default function OrderAdminBillingPanel({
  order,
  showMetrics = true,
  showCallTable = true,
  showFootnote = true,
}) {
  if (!order) return null

  const launch = order.launch_billing || {}
  const settlement = order.billing_settlement || launch.settlement || null
  const cfg = order.config || {}
  const estimatedMin = orderEstimatedDurationMin(order)
  const usage = order.call_usage || orderCallUsageSummary(order)
  const costSummary = order.cost_summary || {}

  const channel = String(
    launch.channel || cfg.survey_channel || cfg.channel || order.quote_survey_channel || '',
  ).toLowerCase()
  const isPhone = channel === 'ai_call' || channel === 'phone' || channel === 'call'
  const isWa = channel === 'whatsapp' || channel === 'wa'

  const templateLabel =
    cfg.wa_template_name ||
    cfg.template_name ||
    cfg.telnyx_wa_template_id ||
    (cfg.builder_template_ids?.length ? `${cfg.builder_template_ids.length} template(s)` : null)

  const holdMinor = launch.wallet_hold_minor ?? launch.wallet_charge_minor
  const connected = usage.connected ?? usage.connected_calls ?? 0
  const billableMin =
    usage.billableMinutes ?? usage.billable_minutes_actual ?? settlement?.total_billable_minutes ?? 0

  const metrics = useMemo(() => {
    const items = [
      { label: 'Billing mode', value: billingModeLabel(order, launch) },
      { label: 'Payment', value: order.payment_status || '—', sub: order.payment_method || undefined },
      { label: 'Quote (est.)', value: order.quote_total_gbp || moneyMinor(order.quote_total_pence) },
    ]

    if (holdMinor > 0) {
      items.push({ label: 'Wallet hold', value: moneyMinor(holdMinor) })
    }

    if (isPhone && launch.unit_rate_minor != null) {
      items.push({ label: 'Per minute', value: `${moneyMinor(launch.unit_rate_minor)}/min` })
    }

    if (isPhone) {
      items.push({
        label: 'Talk time',
        value:
          connected > 0
            ? formatDurationSeconds(usage.totalSeconds ?? usage.total_duration_seconds)
            : '—',
        sub: connected > 0 ? `${connected} call${connected === 1 ? '' : 's'}` : undefined,
      })
      items.push({ label: 'Billable min', value: `${billableMin} min` })
    }

    if (costSummary.total_retail_cost_display && costSummary.total_retail_cost_display !== '—') {
      items.push({ label: 'R.cost', value: costSummary.total_retail_cost_display, mono: true })
    }

    if (costSummary.total_operator_cost_display && costSummary.total_operator_cost_display !== '—') {
      items.push({ label: 'O.cost', value: costSummary.total_operator_cost_display, mono: true })
    }

    if (isPhone && estimatedMin != null) {
      items.push({ label: 'Est. per call', value: `${estimatedMin} min`, sub: 'planning only' })
    }

    if (settlement) {
      items.push(
        { label: 'Included', value: String(settlement.included_minutes ?? settlement.included_units ?? 0) },
        { label: 'Extra billed', value: String(settlement.extra_minutes ?? settlement.extra_units ?? 0) },
        { label: 'Final charge', value: moneyMinor(settlement.final_charge_minor) },
      )
      if (settlement.hold_refund_minor > 0) {
        items.push({ label: 'Hold refunded', value: moneyMinor(settlement.hold_refund_minor) })
      }
    }

    if (settlement?.invoice_id || launch.invoice_id) {
      const invId = settlement?.invoice_id || launch.invoice_id
      items.push({
        label: 'Invoice',
        value: invId.length > 14 ? `${invId.slice(0, 12)}…` : invId,
        mono: true,
      })
    }

    if (isWa && templateLabel) {
      items.push({ label: 'WA template', value: templateLabel })
    }

    return items
  }, [
    order,
    launch,
    holdMinor,
    isPhone,
    isWa,
    estimatedMin,
    usage,
    connected,
    billableMin,
    costSummary,
    settlement,
    templateLabel,
  ])

  return (
    <div className="order-billing">
      {showMetrics ? (
        <div className="order-billing-grid">
          {metrics.map((m) => (
            <MetricCard key={m.label} {...m} />
          ))}
        </div>
      ) : null}

      {showCallTable && isPhone ? (
        <div className="order-billing-calls">
          <OrderCallRecordsTable order={order} compact />
        </div>
      ) : null}

      {showFootnote && isPhone ? (
        <p className="order-billing-footnote">
          Billing uses actual call time after the campaign finishes; each call rounds up to the next full minute.
          Subscription plans are invoiced only for extra minutes beyond allowance.
        </p>
      ) : null}

      {launch.reconciliation ? (
        <div className="order-billing-legacy">
          Legacy reconciliation — charged {moneyMinor(launch.reconciliation.charged_minor)}, actual{' '}
          {moneyMinor(launch.reconciliation.actual_minor)}
          {launch.reconciliation.refund_minor > 0
            ? `, refunded ${moneyMinor(launch.reconciliation.refund_minor)}`
            : ''}
        </div>
      ) : null}
    </div>
  )
}
