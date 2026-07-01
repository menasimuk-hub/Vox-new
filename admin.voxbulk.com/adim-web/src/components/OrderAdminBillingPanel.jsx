import React, { useMemo } from 'react'
import {
  formatDurationSeconds,
  orderCallUsageSummary,
  orderEstimatedDurationMin,
  orderHasBillableSessions,
} from '../lib/serviceOrderAdmin'
import OrderCallRecordsTable from './OrderCallRecordsTable'
import './orderAdminBilling.css'

function moneyMinor(pence, fallback = '—', currencySymbol = '£') {
  const n = Number(pence)
  if (!Number.isFinite(n)) return fallback
  if (currencySymbol === '€') return `€${(n / 100).toFixed(2)}`
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

function MetricCard({ label, value, sub, mono, tone }) {
  return (
    <div className="order-billing-card">
      <div className="order-billing-card-label">{label}</div>
      <div className={`order-billing-card-value${mono ? ' mono' : ''}${tone ? ` val-${tone}` : ''}`}>{value}</div>
      {sub ? <div className="order-billing-card-sub">{sub}</div> : null}
    </div>
  )
}

function EconomicsSection({ title, children }) {
  if (!children) return null
  return (
    <div className="order-billing-economics-block">
      <div className="order-billing-card-label">{title}</div>
      {children}
    </div>
  )
}

export default function OrderAdminBillingPanel({
  order,
  showMetrics = true,
  showCallTable = true,
  showFootnote = true,
  showEconomicsDetail = true,
}) {
  if (!order) return null

  const launch = order.launch_billing || {}
  const settlement = order.billing_settlement || launch.settlement || null
  const financial = order.financial_summary || {}
  const salesRates = financial.sales_rates || {}
  const cfg = order.config || {}
  const estimatedMin = orderEstimatedDurationMin(order)
  const usage = order.call_usage || orderCallUsageSummary(order)
  const costSummary = order.cost_summary || {}
  const isSessionBillable = orderHasBillableSessions(order)

  const channel = String(
    launch.channel || cfg.survey_channel || cfg.channel || order.quote_survey_channel || '',
  ).toLowerCase()
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

  const quoteDisplay = order.quote_total_gbp || financial.quote_total_display || moneyMinor(order.quote_total_pence)
  const retailDisplay = costSummary.total_retail_cost_display || financial.total_retail_cost_display || '—'
  const hasActualRetail = retailDisplay !== '—' && billableMin > 0
  const quoteBreakdown = Array.isArray(financial.quote_breakdown)
    ? financial.quote_breakdown
    : Array.isArray(order.quote_breakdown)
      ? order.quote_breakdown
      : []

  const metrics = useMemo(() => {
    const items = [
      { label: 'Billing mode', value: billingModeLabel(order, launch) },
      {
        label: 'Payment',
        value: order.payment_status || '—',
        sub: order.payment_method || undefined,
        tone: order.payment_status === 'paid' || order.payment_status === 'approved' ? 'ok' : 'muted',
      },
      {
        label: 'Checkout quote',
        value: quoteDisplay,
        sub: 'estimate at launch (not final bill)',
        tone: 'quote',
      },
    ]

    if (holdMinor > 0) {
      items.push({ label: 'Wallet hold', value: moneyMinor(holdMinor), tone: 'money' })
    }

    if (isSessionBillable && (salesRates.interview_per_min_display || launch.unit_rate_minor != null)) {
      items.push({
        label: 'Per minute (sales)',
        value: salesRates.interview_per_min_display || `${moneyMinor(launch.unit_rate_minor)}/min`,
        tone: 'money',
      })
    }

    if (isSessionBillable && (salesRates.connection_fee_display || launch.connection_fee_minor != null)) {
      const conn = salesRates.connection_fee_display || moneyMinor(launch.connection_fee_minor)
      if (conn !== '—' && Number(launch.connection_fee_minor || salesRates.connection_fee_minor) > 0) {
        items.push({ label: 'Connection fee', value: conn, tone: 'money' })
      }
    }

    if (isSessionBillable) {
      items.push({
        label: 'Talk time',
        value:
          connected > 0
            ? formatDurationSeconds(usage.totalSeconds ?? usage.total_duration_seconds)
            : '—',
        sub: connected > 0 ? `${connected} session${connected === 1 ? '' : 's'}` : undefined,
      })
      items.push({
        label: 'Billable min',
        value: `${billableMin} min`,
        sub: 'rounded up per session',
        tone: billableMin > 0 ? 'accent' : undefined,
      })
    }

    items.push({
      label: 'R.cost',
      value: retailDisplay,
      sub: hasActualRetail ? 'actual retail (min × rate + connection)' : 'actual after sessions complete',
      tone: 'retail',
      mono: true,
    })

    items.push({
      label: 'O.cost',
      value: costSummary.total_operator_cost_display || financial.total_operator_cost_display || '—',
      sub: 'Telnyx operator (USD)',
      tone: 'operator',
      mono: true,
    })

    const margin = costSummary.margin_display || financial.margin_display
    if (margin && margin !== '—') {
      items.push({ label: 'Margin', value: margin, sub: 'approx — not FX-adjusted', mono: true })
    }

    if (isSessionBillable && estimatedMin != null) {
      items.push({ label: 'Est. per session', value: `${estimatedMin} min`, sub: 'planning only' })
    }

    if (settlement) {
      items.push(
        { label: 'Included', value: String(settlement.included_minutes ?? settlement.included_units ?? 0) },
        { label: 'Extra billed', value: String(settlement.extra_minutes ?? settlement.extra_units ?? 0) },
        { label: 'Final charge', value: moneyMinor(settlement.final_charge_minor), tone: 'money' },
      )
      if (settlement.hold_refund_minor > 0) {
        items.push({ label: 'Hold refunded', value: moneyMinor(settlement.hold_refund_minor), tone: 'ok' })
      }
    }

    const invId = settlement?.invoice_id || launch.invoice_id || financial.payment_invoice_id || financial.launch_invoice_id
    if (invId) {
      items.push({
        label: 'Invoice',
        value: invId.length > 14 ? `${invId.slice(0, 12)}…` : invId,
        mono: true,
        sub: '/billing/invoices',
      })
    }

    if (financial.ats_wallet_display && financial.ats_wallet_display !== '—') {
      items.push({ label: 'ATS / CV scans', value: financial.ats_wallet_display, tone: 'money' })
    }

    if (isWa && templateLabel) {
      items.push({ label: 'WA template', value: templateLabel })
    }

    return items
  }, [
    order,
    launch,
    holdMinor,
    isSessionBillable,
    isWa,
    estimatedMin,
    usage,
    connected,
    billableMin,
    costSummary,
    financial,
    salesRates,
    settlement,
    templateLabel,
    quoteDisplay,
    retailDisplay,
    hasActualRetail,
  ])

  const walletTxns = Array.isArray(financial.wallet_transactions) ? financial.wallet_transactions : []

  return (
    <div className="order-billing">
      {showMetrics ? (
        <div className="order-billing-grid">
          {metrics.map((m) => (
            <MetricCard key={m.label} {...m} />
          ))}
        </div>
      ) : null}

      {showEconomicsDetail && (quoteBreakdown.length > 0 || salesRates.interview_per_min_display) ? (
        <div className="order-billing-economics">
          {salesRates.interview_per_min_display || salesRates.connection_fee_display ? (
            <EconomicsSection title="Sales prices (rate card at launch)">
              <ul className="order-billing-breakdown-list">
                {salesRates.plan_name ? <li>Plan: {salesRates.plan_name}</li> : null}
                {salesRates.interview_per_min_display ? (
                  <li>Interview: {salesRates.interview_per_min_display}/min</li>
                ) : null}
                {salesRates.connection_fee_display && Number(salesRates.connection_fee_minor) > 0 ? (
                  <li>Connection: {salesRates.connection_fee_display}</li>
                ) : null}
                {salesRates.cv_scan_fee_display && Number(salesRates.cv_scan_fee_minor) > 0 ? (
                  <li>CV scan: {salesRates.cv_scan_fee_display}</li>
                ) : null}
              </ul>
            </EconomicsSection>
          ) : null}
          {quoteBreakdown.length > 0 ? (
            <EconomicsSection title="Quote breakdown">
              <ul className="order-billing-breakdown-list">
                {quoteBreakdown.map((line, idx) => (
                  <li key={`${line.kind}-${idx}`}>
                    {line.detail || line.label || line.kind}
                    {line.amount_pence != null ? ` — ${moneyMinor(line.amount_pence)}` : ''}
                  </li>
                ))}
                <li>
                  <strong>Total quote: {quoteDisplay}</strong>
                </li>
              </ul>
            </EconomicsSection>
          ) : null}
          {walletTxns.length > 0 ? (
            <EconomicsSection title="Wallet transactions">
              <ul className="order-billing-breakdown-list">
                {walletTxns.map((tx) => (
                  <li key={tx.id}>
                    {tx.created_at ? new Date(tx.created_at).toLocaleString() : '—'} — {tx.kind}{' '}
                    {tx.direction === 'debit' ? '−' : '+'}
                    {tx.amount_display || moneyMinor(tx.amount_minor)} ({tx.status || '—'})
                  </li>
                ))}
              </ul>
            </EconomicsSection>
          ) : null}
        </div>
      ) : null}

      {showCallTable && isSessionBillable ? (
        <div className="order-billing-calls">
          <OrderCallRecordsTable order={order} compact />
        </div>
      ) : null}

      {showFootnote && isSessionBillable ? (
        <p className="order-billing-footnote">
          <strong>Checkout quote</strong> is the pre-launch estimate (connection fee + estimated minutes).
          <strong> R.cost</strong> is what you charge from actual billable minutes after sessions finish.
          Each session rounds up to the next full minute. <strong>O.cost</strong> is Telnyx operator cost (USD).
          Margin is shown without FX conversion.
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
