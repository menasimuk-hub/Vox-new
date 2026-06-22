import React from 'react'
import {
  formatDurationSeconds,
  orderCallUsageSummary,
  orderEstimatedDurationMin,
} from '../lib/serviceOrderAdmin'
import OrderCallRecordsTable from './OrderCallRecordsTable'

function moneyMinor(pence, fallback = '—') {
  const n = Number(pence)
  if (!Number.isFinite(n)) return fallback
  return `£${(n / 100).toFixed(2)}`
}

function billingModeLabel(order, launch) {
  const phase = order.billing_phase || launch.billing_phase
  const method = String(launch.payment_method || order.payment_method || '').toLowerCase()
  if (phase === 'held') return 'PAYG — wallet hold (125%)'
  if (phase === 'pending_settlement') return 'Subscription — invoice after campaign if extra'
  if (phase === 'settled') return 'Settled'
  if (method.includes('allowance')) return 'Subscription — allowance'
  if (method.includes('gocardless') || method.includes('direct_debit')) return 'Direct Debit'
  if (method === 'wallet') return 'Wallet'
  return method || '—'
}

export default function OrderAdminBillingPanel({ order }) {
  if (!order) return null

  const launch = order.launch_billing || {}
  const settlement = order.billing_settlement || launch.settlement || null
  const cfg = order.config || {}
  const estimatedMin = orderEstimatedDurationMin(order)
  const usage = order.call_usage || orderCallUsageSummary(order)
  const quoteLines = Array.isArray(order.quote_breakdown) ? order.quote_breakdown : []
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
    (cfg.builder_template_ids?.length ? `${cfg.builder_template_ids.length} builder template(s)` : null)

  const holdMinor = launch.wallet_hold_minor ?? launch.wallet_charge_minor

  return (
    <>
      <div className="note runningSurveyBillingPanel">
        <strong>Billing &amp; usage</strong>
        <div className="runningSurveyMetaGrid" style={{ marginTop: 10 }}>
          <div className="runningSurveyMetaBlock">
            <div className="runningSurveyMetaLabel">Order ID</div>
            <div className="occ-mono" style={{ fontSize: 12 }}>{order.id}</div>
          </div>
          <div className="runningSurveyMetaBlock">
            <div className="runningSurveyMetaLabel">Billing mode</div>
            <div>{billingModeLabel(order, launch)}</div>
          </div>
          <div className="runningSurveyMetaBlock">
            <div className="runningSurveyMetaLabel">Quote total (estimate)</div>
            <div>{order.quote_total_gbp || moneyMinor(order.quote_total_pence)}</div>
          </div>
          {holdMinor > 0 ? (
            <div className="runningSurveyMetaBlock">
              <div className="runningSurveyMetaLabel">Wallet hold at launch</div>
              <div>{moneyMinor(holdMinor)}</div>
            </div>
          ) : null}
          {isPhone && estimatedMin != null ? (
            <div className="runningSurveyMetaBlock">
              <div className="runningSurveyMetaLabel">Estimated per call</div>
              <div>{estimatedMin} min (hold / planning only)</div>
            </div>
          ) : null}
          {isPhone && launch.unit_rate_minor != null ? (
            <div className="runningSurveyMetaBlock">
              <div className="runningSurveyMetaLabel">Per-minute rate</div>
              <div>{moneyMinor(launch.unit_rate_minor)}/min</div>
            </div>
          ) : null}
          {isPhone ? (
            <div className="runningSurveyMetaBlock">
              <div className="runningSurveyMetaLabel">Actual Telnyx talk time</div>
              <div>
                {(usage.connected ?? usage.connected_calls) > 0
                  ? `${formatDurationSeconds(usage.totalSeconds ?? usage.total_duration_seconds)} (${usage.connected ?? usage.connected_calls} call${(usage.connected ?? usage.connected_calls) === 1 ? '' : 's'})`
                  : '—'}
              </div>
            </div>
          ) : null}
          {isPhone ? (
            <div className="runningSurveyMetaBlock">
              <div className="runningSurveyMetaLabel">Billable minutes (rounded up)</div>
              <div>{usage.billableMinutes ?? usage.billable_minutes_actual ?? settlement?.total_billable_minutes ?? 0} min</div>
            </div>
          ) : null}
          {costSummary.total_retail_cost_display ? (
            <div className="runningSurveyMetaBlock">
              <div className="runningSurveyMetaLabel">R.cost (retail total)</div>
              <div>{costSummary.total_retail_cost_display}</div>
            </div>
          ) : null}
          {costSummary.total_operator_cost_display && costSummary.total_operator_cost_display !== '—' ? (
            <div className="runningSurveyMetaBlock">
              <div className="runningSurveyMetaLabel">O.cost (Telnyx total)</div>
              <div>{costSummary.total_operator_cost_display}</div>
            </div>
          ) : null}
          {settlement ? (
            <>
              <div className="runningSurveyMetaBlock">
                <div className="runningSurveyMetaLabel">Included (allowance)</div>
                <div>{settlement.included_minutes ?? settlement.included_units ?? 0}</div>
              </div>
              <div className="runningSurveyMetaBlock">
                <div className="runningSurveyMetaLabel">Extra (invoiced)</div>
                <div>{settlement.extra_minutes ?? settlement.extra_units ?? 0}</div>
              </div>
              <div className="runningSurveyMetaBlock">
                <div className="runningSurveyMetaLabel">Final charge</div>
                <div>{moneyMinor(settlement.final_charge_minor)}</div>
              </div>
              {settlement.hold_refund_minor > 0 ? (
                <div className="runningSurveyMetaBlock">
                  <div className="runningSurveyMetaLabel">Hold refunded</div>
                  <div>{moneyMinor(settlement.hold_refund_minor)}</div>
                </div>
              ) : null}
            </>
          ) : null}
          {(settlement?.invoice_id || launch.invoice_id) ? (
            <div className="runningSurveyMetaBlock">
              <div className="runningSurveyMetaLabel">Invoice</div>
              <div className="occ-mono" style={{ fontSize: 12 }}>{settlement?.invoice_id || launch.invoice_id}</div>
            </div>
          ) : null}
          {isWa && templateLabel ? (
            <div className="runningSurveyMetaBlock">
              <div className="runningSurveyMetaLabel">WhatsApp template</div>
              <div>{templateLabel}</div>
            </div>
          ) : null}
        </div>
        {isPhone ? (
          <p className="muted" style={{ marginTop: 10, marginBottom: 0, fontSize: 13 }}>
            Invoices use <strong>actual</strong> call time after the campaign finishes. Each call rounds up to the next full minute.
            Subscription customers are invoiced only for <strong>extra</strong> minutes beyond plan allowance.
          </p>
        ) : null}
        {launch.reconciliation ? (
          <div style={{ marginTop: 10, fontSize: 13 }}>
            <strong>Legacy reconciliation</strong>
            <div className="muted">
              Charged {moneyMinor(launch.reconciliation.charged_minor)} · actual{' '}
              {moneyMinor(launch.reconciliation.actual_minor)}
              {launch.reconciliation.refund_minor > 0
                ? ` · refunded ${moneyMinor(launch.reconciliation.refund_minor)}`
                : ''}
            </div>
          </div>
        ) : null}
      </div>
      {isPhone ? <OrderCallRecordsTable order={order} /> : null}
    </>
  )
}
