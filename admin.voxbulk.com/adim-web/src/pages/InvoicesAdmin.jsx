import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch, apiFetchBlob, apiFetchText } from '../lib/api'
import { buildEmailTestVariables } from '../lib/messagingConstants'

const money = (pence, currency = 'GBP') => {
  const amount = Number(pence || 0) / 100
  try {
    return new Intl.NumberFormat('en-GB', { style: 'currency', currency: currency || 'GBP' }).format(amount)
  } catch {
    return `£${amount.toFixed(2)}`
  }
}

const dateText = (value) => (value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—')
const dateShort = (value) => (value ? new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—')

const TABS = [
  { id: 'invoices', label: 'All invoices', icon: 'ti-receipt' },
  { id: 'requests', label: 'Billing requests', icon: 'ti-file-description' },
  { id: 'template', label: 'Invoice template', icon: 'ti-file-invoice' },
  { id: 'vat', label: 'VAT by country', icon: 'ti-world' },
]

const STATUS_OPTIONS = ['', 'paid', 'issued', 'open', 'pending', 'collecting', 'failed', 'past_due', 'disputed', 'refunded']

function substitutePlaceholders(template, variables) {
  let out = String(template || '')
  Object.entries(variables || {}).forEach(([key, val]) => {
    out = out.replace(new RegExp(`\\{\\{\\s*${key}\\s*\\}\\}`, 'g'), String(val ?? ''))
  })
  return out
}

function statusPillClass(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'paid') return 'p-green'
  if (s === 'failed') return 'p-red'
  if (s === 'issued' || s === 'open') return 'p-amber'
  return ''
}

function normTag(value) {
  return String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_')
}

function truncate(text, max = 48) {
  const s = String(text || '').trim()
  if (!s) return '—'
  return s.length > max ? `${s.slice(0, max)}…` : s
}

function buildInvoiceTags(row) {
  const tags = []
  const provider = row.provider || 'internal'
  tags.push(provider)
  if (row.country_code) tags.push(row.country_code)
  if (row.tax_rate_percent != null) tags.push(`VAT ${row.tax_rate_percent}%`)
  const paymentMethod = row.payment_method
  if (paymentMethod && normTag(paymentMethod) !== normTag(provider)) {
    tags.push(paymentMethod)
  }
  return tags
}

function resolveInvoiceLifecycle(inv) {
  if (inv?.lifecycle) return inv.lifecycle
  const st = String(inv?.status || '').toLowerCase()
  const ddActive = st === 'collecting' || (st === 'pending' && inv?.dd_payment_id)
  const locked = ['paid', 'void', 'cancelled', 'refunded', 'disputed', 'credited'].includes(st) || Boolean(inv?.disputed)
  if (ddActive) {
    return {
      can_edit: false,
      can_void: false,
      is_locked: true,
      lock_reason: 'Direct Debit collection is in progress.',
      suggested_action_label: 'Stop DD collection before editing or voiding.',
    }
  }
  if (locked) {
    return {
      can_edit: false,
      can_void: false,
      is_locked: true,
      lock_reason: st === 'paid' ? 'Paid invoices cannot be edited or voided.' : 'This invoice is locked.',
      suggested_action_label: 'Use credit note, refund, or reissue instead.',
    }
  }
  return { can_edit: true, can_void: true, is_locked: false, lock_reason: null, suggested_action_label: null }
}

export default function InvoicesAdmin() {
  const [tab, setTab] = useState(() => {
    const params = new URLSearchParams(window.location.search)
    const t = params.get('tab')
    return t && TABS.some((x) => x.id === t) ? t : 'invoices'
  })
  const [invoices, setInvoices] = useState([])
  const [billingRequests, setBillingRequests] = useState([])
  const [vatRates, setVatRates] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [filters, setFilters] = useState({ search: '', status: '', provider: '' })
  const [templateDraft, setTemplateDraft] = useState({ subject: '', body: '', is_enabled: true })
  const [templateSaving, setTemplateSaving] = useState(false)
  const [templateMsg, setTemplateMsg] = useState('')
  const [vatDraft, setVatDraft] = useState({ country_code: '', country_name: '', vat_rate_percent: '0', notes: '' })
  const [editInvoice, setEditInvoice] = useState(null)
  const [editAmount, setEditAmount] = useState('')
  const [editDue, setEditDue] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [editBusy, setEditBusy] = useState(false)

  const previewHtml = useMemo(
    () => substitutePlaceholders(templateDraft.body, buildEmailTestVariables('invoice_document')),
    [templateDraft.body],
  )

  const loadInvoices = useCallback(async () => {
    const params = new URLSearchParams({ limit: '200' })
    if (filters.search.trim()) params.set('search', filters.search.trim())
    if (filters.status) params.set('status', filters.status)
    if (filters.provider.trim()) params.set('provider', filters.provider.trim())
    const rows = await apiFetch(`/admin/billing/invoices/recent?${params.toString()}`)
    setInvoices(Array.isArray(rows) ? rows : [])
  }, [filters])

  const loadVat = useCallback(async () => {
    const rows = await apiFetch('/admin/billing/vat-rates')
    setVatRates(Array.isArray(rows) ? rows : [])
  }, [])

  const loadBillingRequests = useCallback(async () => {
    const res = await apiFetch('/admin/billing/requests?limit=200')
    setBillingRequests(Array.isArray(res?.items) ? res.items : [])
  }, [])

  const loadTemplate = useCallback(async () => {
    const row = await apiFetch('/admin/email/templates/invoice_document')
    setTemplateDraft({
      subject: row.subject || '',
      body: row.body || '',
      is_enabled: row.is_enabled !== false,
    })
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        if (tab === 'invoices') await loadInvoices()
        if (tab === 'requests') await loadBillingRequests()
        if (tab === 'vat') await loadVat()
        if (tab === 'template') await loadTemplate()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [tab, loadInvoices, loadBillingRequests, loadVat, loadTemplate])

  const stats = useMemo(() => {
    const paidRows = invoices.filter((r) => String(r.status || '').toLowerCase() === 'paid')
    const paidTotal = paidRows.reduce((sum, r) => sum + Number(r.amount_gbp_pence || 0), 0)
    return { count: invoices.length, paid: paidRows.length, paidTotal, total: invoices.reduce((s, r) => s + Number(r.amount_gbp_pence || 0), 0) }
  }, [invoices])


  const downloadPdf = async (invoiceId, invoiceNumber) => {
    setBusy(invoiceId)
    try {
      const blob = await apiFetchBlob(`/admin/billing/invoices/${encodeURIComponent(invoiceId)}/pdf`)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `invoice-${invoiceNumber || invoiceId}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e?.message || 'PDF download failed')
    } finally {
      setBusy('')
    }
  }

  const viewHtml = async (invoiceId) => {
    setBusy(invoiceId)
    try {
      const html = await apiFetchText(`/admin/billing/invoices/${encodeURIComponent(invoiceId)}/html`)
      const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
      window.open(URL.createObjectURL(blob), '_blank', 'noopener')
    } catch (e) {
      setError(e?.message || 'Could not open invoice HTML')
    } finally {
      setBusy('')
    }
  }

  const resendEmail = async (invoiceId) => {
    setBusy(invoiceId)
    setError('')
    try {
      await apiFetch(`/admin/billing/invoices/${encodeURIComponent(invoiceId)}/resend-email`, { method: 'POST' })
      await loadInvoices()
    } catch (e) {
      setError(e?.message || 'Resend failed')
    } finally {
      setBusy('')
    }
  }

  const disputeInvoice = async (row) => {
    const note = window.prompt('Dispute note (optional):', row.dispute_note || '')
    if (note === null) return
    setBusy(row.id)
    setError('')
    try {
      await apiFetch(`/admin/billing/invoices/${encodeURIComponent(row.id)}/dispute`, {
        method: 'POST',
        body: JSON.stringify({ note }),
      })
      await loadInvoices()
    } catch (e) {
      setError(e?.message || 'Dispute failed')
    } finally {
      setBusy('')
    }
  }

  const resolveDispute = async (row) => {
    const note = window.prompt('Resolution note (optional):', '')
    if (note === null) return
    setBusy(row.id)
    setError('')
    try {
      await apiFetch(`/admin/billing/invoices/${encodeURIComponent(row.id)}/resolve-dispute`, {
        method: 'POST',
        body: JSON.stringify({ note }),
      })
      await loadInvoices()
    } catch (e) {
      setError(e?.message || 'Resolve failed')
    } finally {
      setBusy('')
    }
  }

  const bankRefund = async (row) => {
    const note = window.prompt('Bank refund note (logged against invoice):', 'Manual bank refund')
    if (note === null) return
    if (!window.confirm(`Record bank refund for ${money(row.amount_gbp_pence, row.currency)}?`)) return
    setBusy(row.id)
    setError('')
    try {
      await apiFetch(`/admin/billing/invoices/${encodeURIComponent(row.id)}/bank-refund`, {
        method: 'POST',
        body: JSON.stringify({ note }),
      })
      await loadInvoices()
    } catch (e) {
      setError(e?.message || 'Bank refund failed')
    } finally {
      setBusy('')
    }
  }

  const billingInvoice = (invoiceId, path, options = {}) =>
    apiFetch(`/admin/billing/invoices/${encodeURIComponent(invoiceId)}${path}`, options)

  const openEditInvoice = (row) => {
    setEditInvoice(row)
    setEditAmount(String((row.subtotal_pence ?? row.amount_gbp_pence ?? 0) / 100))
    setEditDue(row.due_date ? String(row.due_date).slice(0, 10) : '')
    setEditDesc(row.description || '')
  }

  const saveEditInvoice = async () => {
    if (!editInvoice?.id) return
    const gbp = Number(editAmount)
    if (!Number.isFinite(gbp) || gbp <= 0) {
      setError('Enter a positive amount')
      return
    }
    setEditBusy(true)
    setError('')
    try {
      await billingInvoice(editInvoice.id, '', {
        method: 'PATCH',
        body: JSON.stringify({
          amount_minor: Math.round(gbp * 100),
          due_date: editDue || undefined,
          description: editDesc.trim() || undefined,
        }),
      })
      setEditInvoice(null)
      await loadInvoices()
    } catch (e) {
      setError(e?.message || 'Invoice edit failed')
    } finally {
      setEditBusy(false)
    }
  }

  const voidInvoice = async (row) => {
    if (!row?.id) return
    const reason = window.prompt('Reason for voiding this invoice (required for audit):', 'Voided by support')
    if (!reason) return
    setBusy(row.id)
    setError('')
    try {
      await billingInvoice(row.id, '/void', {
        method: 'POST',
        body: JSON.stringify({ reason }),
      })
      await loadInvoices()
    } catch (e) {
      setError(e?.message || 'Void failed')
    } finally {
      setBusy('')
    }
  }

  const markInvoicePaid = async (row) => {
    if (!row?.id) return
    setBusy(row.id)
    setError('')
    try {
      await billingInvoice(row.id, '/mark-paid', { method: 'POST', body: '{}' })
      await loadInvoices()
    } catch (e) {
      setError(e?.message || 'Mark paid failed')
    } finally {
      setBusy('')
    }
  }

  const collectInvoiceWallet = async (row) => {
    if (!row?.id) return
    setBusy(row.id)
    setError('')
    try {
      await billingInvoice(row.id, '/collect', {
        method: 'POST',
        body: JSON.stringify({ method: 'wallet' }),
      })
      await loadInvoices()
    } catch (e) {
      setError(e?.message || 'Collect payment failed')
    } finally {
      setBusy('')
    }
  }

  const saveTemplate = async () => {
    setTemplateSaving(true)
    setTemplateMsg('')
    setError('')
    try {
      await apiFetch('/admin/email/templates/invoice_document', {
        method: 'PUT',
        body: JSON.stringify({
          title: 'Invoice document (PDF)',
          subject: templateDraft.subject,
          body: templateDraft.body,
          is_enabled: templateDraft.is_enabled,
        }),
      })
      setTemplateMsg('Invoice template saved.')
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setTemplateSaving(false)
    }
  }

  const saveVat = async () => {
    const code = vatDraft.country_code.trim().toUpperCase()
    if (code.length !== 2) {
      setError('Country code must be 2 letters (e.g. AE, GB)')
      return
    }
    setBusy('vat')
    setError('')
    try {
      await apiFetch(`/admin/billing/vat-rates/${encodeURIComponent(code)}`, {
        method: 'PUT',
        body: JSON.stringify({
          country_name: vatDraft.country_name.trim() || code,
          vat_rate_percent: Number(vatDraft.vat_rate_percent || 0),
          is_enabled: true,
          notes: vatDraft.notes.trim() || null,
        }),
      })
      setVatDraft({ country_code: '', country_name: '', vat_rate_percent: '0', notes: '' })
      await loadVat()
    } catch (e) {
      setError(e?.message || 'Save VAT rate failed')
    } finally {
      setBusy('')
    }
  }

  const updateVatRow = async (row) => {
    setBusy(row.country_code)
    try {
      await apiFetch(`/admin/billing/vat-rates/${encodeURIComponent(row.country_code)}`, {
        method: 'PUT',
        body: JSON.stringify(row),
      })
      await loadVat()
    } catch (e) {
      setError(e?.message || 'Update failed')
    } finally {
      setBusy('')
    }
  }

  const sortedInvoices = useMemo(() => {
    const rank = (status) => {
      const s = String(status || '').toLowerCase()
      if (s === 'paid') return 0
      if (s === 'issued' || s === 'open') return 1
      if (s === 'failed') return 2
      return 3
    }
    return [...invoices].sort((a, b) => {
      const byRank = rank(a.status) - rank(b.status)
      if (byRank !== 0) return byRank
      return new Date(b.created_at || 0) - new Date(a.created_at || 0)
    })
  }, [invoices])

  const renderInvoiceRow = (row) => {
    const number = row.invoice_number || row.external_invoice_id
    const isBusy = busy === row.id
    const lifecycle = resolveInvoiceLifecycle(row)
    const st = String(row.status || '').toLowerCase()
    const isPaid = st === 'paid'
    return (
      <tr key={row.id} className="invoiceListRow">
        <td>
          <code className="invoiceIdPill" title={number}>{number}</code>
        </td>
        <td className="invoiceListDate muted">{dateShort(row.created_at)}</td>
        <td className="invoiceListOrg" title={row.organisation_name || ''}>
          {truncate(row.organisation_name, 28)}
        </td>
        <td className="invoiceListEmail muted" title={row.client_email}>
          {truncate(row.client_email, 26)}
        </td>
        <td className="invoiceListAmount">
          <strong>{money(row.amount_gbp_pence, row.currency)}</strong>
        </td>
        <td>
          <span className={`pill invoiceStatusPill ${statusPillClass(row.status)}`}>{row.status || '—'}</span>
          {row.disputed ? <span className="invoiceTag invoiceTagMuted" style={{ marginLeft: 6 }}>disputed</span> : null}
          {row.dd_retry_count > 0 ? (
            <span className="invoiceTag invoiceTagMuted" style={{ marginLeft: 6 }} title={row.dd_next_retry_at || ''}>
              DD retry {row.dd_retry_count}
            </span>
          ) : null}
        </td>
        <td className="invoiceListTags">
          <div className="invoiceListTagWrap">
            {buildInvoiceTags(row).map((label) => (
              <span key={`${row.id}-${label}`} className="invoiceTag">{label}</span>
            ))}
          </div>
        </td>
        <td className="invoiceListNotify">
          {row.emailed_at ? (
            <span className="invoiceTag invoiceTagOk" title={dateText(row.emailed_at)}>
              <i className="ti ti-mail-check" /> Sent
            </span>
          ) : (
            <span className="invoiceTag invoiceTagMuted">Not sent</span>
          )}
        </td>
        <td className="invoiceListDesc muted" title={row.description || ''}>
          {truncate(row.description, 36)}
        </td>
        <td className="invoiceListActions">
          <div className="actions invoiceRowActions" style={{ flexWrap: 'wrap', justifyContent: 'flex-end', gap: 4 }}>
            <button type="button" className="btn soft xs" disabled={isBusy} onClick={() => viewHtml(row.id)} title="View invoice">
              View
            </button>
            <button type="button" className="btn soft xs" disabled={isBusy} onClick={() => downloadPdf(row.id, number)} title="Download PDF">
              PDF
            </button>
            {lifecycle.can_edit ? (
              <button type="button" className="btn soft xs" disabled={isBusy} onClick={() => openEditInvoice(row)} title="Edit invoice">
                Edit
              </button>
            ) : null}
            {lifecycle.can_void ? (
              <button type="button" className="btn soft xs" disabled={isBusy} onClick={() => voidInvoice(row)} title="Void invoice">
                Void
              </button>
            ) : lifecycle.is_locked ? (
              <button
                type="button"
                className="btn soft xs"
                title={lifecycle.suggested_action_label || lifecycle.lock_reason || ''}
                onClick={() => setError(lifecycle.suggested_action_label || lifecycle.lock_reason || 'Invoice is locked')}
              >
                Locked
              </button>
            ) : null}
            {!isPaid ? (
              <>
                <button type="button" className="btn soft xs" disabled={isBusy} onClick={() => collectInvoiceWallet(row)} title="Collect from wallet">
                  Collect
                </button>
                <button type="button" className="btn primary xs" disabled={isBusy} onClick={() => markInvoicePaid(row)} title="Mark paid">
                  Mark paid
                </button>
              </>
            ) : (
              <span className="pill p-green">Paid</span>
            )}
            <button type="button" className="btn soft xs" disabled={isBusy} onClick={() => resendEmail(row.id)} title="Resend email">
              Resend
            </button>
            {row.org_id ? (
              <Link className="btn soft xs" to="/organisations/all-users" title="Open Organisation Control Center">
                OCC
              </Link>
            ) : null}
            {!row.disputed && st !== 'refunded' ? (
              <button type="button" className="btn soft xs" disabled={isBusy} onClick={() => disputeInvoice(row)} title="Mark disputed">
                Dispute
              </button>
            ) : null}
            {row.disputed ? (
              <button type="button" className="btn soft xs" disabled={isBusy} onClick={() => resolveDispute(row)} title="Resolve dispute">
                Resolve
              </button>
            ) : null}
            {st !== 'refunded' ? (
              <button type="button" className="btn soft xs" disabled={isBusy} onClick={() => bankRefund(row)} title="Log bank refund">
                Refund
              </button>
            ) : null}
          </div>
        </td>
      </tr>
    )
  }

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Invoices</h1>
          <p>All billing invoices, printable PDF template, and VAT rates by country.</p>
          <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            Use <strong>Edit</strong> / <strong>Void</strong> on unpaid rows below, or open <Link to="/organisations/all-users">Organisation Control Center</Link> → select org → <strong>Invoices</strong> tab for wallet credits and full billing controls.
          </p>
        </div>
        <div className="actions">
          {tab === 'invoices' ? (
            <button type="button" className="btn soft" onClick={loadInvoices} disabled={loading}>
              Refresh
            </button>
          ) : null}
        </div>
      </div>

      <div className="emailTabBar" role="tablist" style={{ marginBottom: 16 }}>
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={`emailTabBtn ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            <i className={`ti ${t.icon}`} /> {t.label}
          </button>
        ))}
      </div>

      {error ? <div className="note" style={{ borderColor: 'rgba(220,38,38,0.35)', marginBottom: 12 }}>{error}</div> : null}

      {tab === 'invoices' ? (
        <>
          {billingRequests.filter((r) => String(r.status || '').toLowerCase() === 'pending').length > 0 ? (
            <div className="card" style={{ marginBottom: 16, borderColor: 'var(--amber, #f59e0b)' }}>
              <div className="cardBody" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <div>
                  <strong>{billingRequests.filter((r) => String(r.status || '').toLowerCase() === 'pending').length} pending billing request(s)</strong>
                  <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                    Cancellation and refund reviews awaiting admin action.
                  </div>
                </div>
                <Link className="btn" to="/invoices?tab=requests">
                  View billing requests
                </Link>
              </div>
            </div>
          ) : null}
          <div className="invoiceStatsBar">
            <span className="invoiceStatChip">
              <i className="ti ti-receipt" />
              <strong>{stats.count}</strong> invoices
            </span>
            <span className="invoiceStatChip invoiceStatPaid">
              <i className="ti ti-circle-check" />
              <strong>{stats.paid}</strong> paid
              <span className="muted">({money(stats.paidTotal)})</span>
            </span>
            <span className="invoiceStatChip">
              <i className="ti ti-sum" />
              Total <strong>{money(stats.total)}</strong>
            </span>
          </div>

          <div className="card invoiceHubFilters invoiceHubFiltersCompact">
            <div className="cardBody invoiceFilterGrid">
              <label className="msgFieldBlockTight">
                <span className="label">Search</span>
                <input
                  className="input inputCompact"
                  value={filters.search}
                  onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
                  placeholder="Invoice #, email, org"
                  onKeyDown={(e) => e.key === 'Enter' && loadInvoices()}
                />
              </label>
              <label className="msgFieldBlockTight">
                <span className="label">Status</span>
                <select className="input inputCompact" value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}>
                  {STATUS_OPTIONS.map((s) => (
                    <option key={s || 'all'} value={s}>{s || 'All'}</option>
                  ))}
                </select>
              </label>
              <label className="msgFieldBlockTight">
                <span className="label">Provider</span>
                <input className="input inputCompact" value={filters.provider} onChange={(e) => setFilters((f) => ({ ...f, provider: e.target.value }))} placeholder="gocardless" />
              </label>
              <button type="button" className="btn primary btnCompact" onClick={loadInvoices}>Apply</button>
            </div>
          </div>

          <div className="card invoiceListCard">
            <div className="cardHead invoiceListHead">
              <h3>All invoices</h3>
              <span className="pill p-cyan">{sortedInvoices.length} shown</span>
            </div>
            <div className="cardBody invoiceTableWrap">
              {loading ? <div className="muted invoiceListEmpty">Loading…</div> : null}
              {!loading && !sortedInvoices.length ? (
                <div className="muted invoiceListEmpty">No invoices yet. Complete a GoCardless payment to create one.</div>
              ) : null}
              {!loading && sortedInvoices.length ? (
                <table className="table invoiceDenseTable invoiceListTable">
                  <thead>
                    <tr>
                      <th>Invoice</th>
                      <th>Date</th>
                      <th>Organisation</th>
                      <th>Email</th>
                      <th>Amount</th>
                      <th>Status</th>
                      <th>Tags</th>
                      <th>Sent</th>
                      <th>Description</th>
                      <th style={{ textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>{sortedInvoices.map(renderInvoiceRow)}</tbody>
                </table>
              ) : null}
            </div>
          </div>
        </>
      ) : null}

      {tab === 'requests' ? (
        <div className="card invoiceListCard">
          <div className="cardHead invoiceListHead">
            <h3>Billing requests</h3>
            <span className="pill p-cyan">{billingRequests.length} shown</span>
          </div>
          <div className="cardBody invoiceTableWrap">
            {loading ? <div className="muted invoiceListEmpty">Loading…</div> : null}
            {!loading && !billingRequests.length ? (
              <div className="muted invoiceListEmpty">No cancellation or refund review requests yet.</div>
            ) : null}
            {!loading && billingRequests.length ? (
              <table className="table invoiceDenseTable invoiceListTable">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Organisation</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Refund</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {billingRequests.map((row) => (
                    <tr key={`${row.type}-${row.id}`}>
                      <td>{dateShort(row.requested_at)}</td>
                      <td>{row.org_name || row.org_id || '—'}</td>
                      <td>{String(row.type || '').replace('_', ' ')}</td>
                      <td><span className={`pill ${row.status === 'pending' ? 'p-amber' : row.status === 'approved' ? 'p-green' : ''}`}>{row.status || '—'}</span></td>
                      <td>{row.requested_refund_type ? String(row.requested_refund_type).replace(/_/g, ' ') : '—'}</td>
                      <td style={{ textAlign: 'right' }}>
                        {row.org_id ? (
                          <Link className="btn btnCompact" to={`/organisations/${encodeURIComponent(row.org_id)}/control-center`}>
                            Open org
                          </Link>
                        ) : null}
                        {row.support_ticket_id ? (
                          <Link className="btn btnCompact" to={`/support/tickets/${row.support_ticket_id}`} style={{ marginLeft: 8 }}>
                            Ticket
                          </Link>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </div>
        </div>
      ) : null}

      {tab === 'template' ? (
        <div className="card msgTemplateEditor">
          <div className="cardHead">
            <h3>Invoice document HTML</h3>
            <span className="pill p-cyan">PDF + dashboard view</span>
          </div>
          <div className="cardBody">
            <p className="fieldHint" style={{ marginBottom: 14 }}>
              Placeholders: <code>{'{{invoice_number}}'}</code>, <code>{'{{organisation_name}}'}</code>, <code>{'{{line_items_html}}'}</code>,{' '}
              <code>{'{{subtotal}}'}</code>, <code>{'{{tax_amount}}'}</code>, <code>{'{{amount}}'}</code>.
              Email notification: <Link to="/settings/email/templates/new_invoice/edit">new_invoice</Link>.
            </p>

            <div className="emailEditorSplit invoiceTemplateSplit">
              <div className="emailEditorFields">
                <label className="label">Subject (reference)</label>
                <input
                  className="input msgFieldSubjectBox"
                  value={templateDraft.subject}
                  onChange={(e) => setTemplateDraft((d) => ({ ...d, subject: e.target.value }))}
                />
                <label className="label emailBodyLabel">HTML body</label>
                <textarea
                  className="input msgFieldBodyBox invoiceTemplateEditor"
                  value={templateDraft.body}
                  onChange={(e) => setTemplateDraft((d) => ({ ...d, body: e.target.value }))}
                  placeholder="<html>…</html>"
                />
              </div>

              <div className="msgFieldBlock msgFieldBlockTight emailEditorPreviewCol">
                <label className="label">
                  <i className="ti ti-eye" style={{ marginRight: 6 }} />
                  Live HTML preview
                </label>
                <div className="emailPreviewBox emailPreviewBoxTall invoiceDocPreviewBox">
                  {previewHtml ? (
                    <div className="emailPreviewInner invoiceDocPreviewInner" dangerouslySetInnerHTML={{ __html: previewHtml }} />
                  ) : (
                    <p className="muted" style={{ margin: 0 }}>HTML preview appears here.</p>
                  )}
                </div>
              </div>
            </div>

            <div className="actions" style={{ marginTop: 16 }}>
              <button type="button" className="btn primary" onClick={saveTemplate} disabled={templateSaving}>
                <i className="ti ti-device-floppy" />
                {templateSaving ? 'Saving…' : 'Save invoice template'}
              </button>
              {templateMsg ? <span className="muted" style={{ fontSize: 12 }}>{templateMsg}</span> : null}
            </div>
          </div>
        </div>
      ) : null}

      {tab === 'vat' ? (
        <>
          <div className="card" style={{ marginBottom: 14 }}>
            <div className="cardHead"><h3>Add / update country VAT</h3></div>
            <div className="cardBody invoiceFilterGrid">
              <label className="msgFieldBlockTight">
                <span className="label">Code</span>
                <input className="input" maxLength={2} value={vatDraft.country_code} onChange={(e) => setVatDraft((d) => ({ ...d, country_code: e.target.value.toUpperCase() }))} placeholder="AE" />
              </label>
              <label className="msgFieldBlockTight">
                <span className="label">Country</span>
                <input className="input" value={vatDraft.country_name} onChange={(e) => setVatDraft((d) => ({ ...d, country_name: e.target.value }))} placeholder="United Arab Emirates" />
              </label>
              <label className="msgFieldBlockTight">
                <span className="label">VAT %</span>
                <input className="input" type="number" min="0" step="0.01" value={vatDraft.vat_rate_percent} onChange={(e) => setVatDraft((d) => ({ ...d, vat_rate_percent: e.target.value }))} />
              </label>
              <label className="msgFieldBlockTight">
                <span className="label">Notes</span>
                <input className="input" value={vatDraft.notes} onChange={(e) => setVatDraft((d) => ({ ...d, notes: e.target.value }))} placeholder="Optional" />
              </label>
              <button type="button" className="btn primary" disabled={busy === 'vat'} onClick={saveVat}>Save</button>
            </div>
          </div>

          <div className="card">
            <div className="cardHead"><h3>VAT rates</h3></div>
            <div className="cardBody invoiceTableWrap">
              {loading ? <div className="muted">Loading…</div> : null}
              {!loading && vatRates.length ? (
                <table className="table invoiceDenseTable">
                  <thead>
                    <tr>
                      <th>Code</th>
                      <th>Country</th>
                      <th>VAT %</th>
                      <th>Enabled</th>
                      <th>Notes</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {vatRates.map((row) => (
                      <tr key={row.country_code}>
                        <td><code>{row.country_code}</code></td>
                        <td>{row.country_name}</td>
                        <td>
                          <input
                            className="input"
                            style={{ width: 90 }}
                            type="number"
                            min="0"
                            step="0.01"
                            defaultValue={row.vat_rate_percent}
                            onBlur={(e) => updateVatRow({ ...row, vat_rate_percent: Number(e.target.value || 0) })}
                          />
                        </td>
                        <td>
                          <input
                            type="checkbox"
                            defaultChecked={row.is_enabled !== false}
                            onChange={(e) => updateVatRow({ ...row, is_enabled: e.target.checked })}
                          />
                        </td>
                        <td className="muted" style={{ fontSize: 12 }}>{row.notes || '—'}</td>
                        <td className="muted" style={{ fontSize: 11 }}>{row.updated_at ? dateText(row.updated_at) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : null}
            </div>
          </div>
        </>
      ) : null}

      {editInvoice ? (
        <div className="card" style={{ position: 'fixed', inset: 0, zIndex: 50, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div className="card" style={{ width: 'min(420px, 92vw)' }}>
            <div className="cardHead"><h3>Edit invoice {editInvoice.invoice_number || editInvoice.id?.slice(0, 8)}</h3></div>
            <div className="cardBody invoiceFilterGrid">
              <label className="msgFieldBlockTight">
                <span className="label">Amount (£ ex VAT)</span>
                <input className="input" type="number" min="0" step="0.01" value={editAmount} onChange={(e) => setEditAmount(e.target.value)} />
              </label>
              <label className="msgFieldBlockTight">
                <span className="label">Due date</span>
                <input className="input" type="date" value={editDue} onChange={(e) => setEditDue(e.target.value)} />
              </label>
              <label className="msgFieldBlockTight">
                <span className="label">Description</span>
                <input className="input" type="text" value={editDesc} onChange={(e) => setEditDesc(e.target.value)} />
              </label>
              <div className="actions">
                <button type="button" className="btn soft" onClick={() => setEditInvoice(null)} disabled={editBusy}>Cancel</button>
                <button type="button" className="btn primary" onClick={saveEditInvoice} disabled={editBusy}>{editBusy ? 'Saving…' : 'Save'}</button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
