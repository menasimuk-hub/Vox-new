import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch, apiFetchBlob, apiFetchText } from '../lib/api'
import { buildEmailTestVariables } from '../lib/messagingConstants'
import { currencySymbol, money } from '../lib/billingAdminUtils'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Textarea } from '@/components/ui/Textarea'
import { Pill } from '@/components/ui/Badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs'

const dateText = (value) => (value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—')
const dateShort = (value) => (value ? new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—')

const TABS = [
  { id: 'invoices', label: 'All invoices', icon: 'ti-receipt' },
  { id: 'requests', label: 'Billing requests', icon: 'ti-file-description' },
  { id: 'template', label: 'Invoice template', icon: 'ti-file-invoice' },
  { id: 'vat', label: 'VAT by country', icon: 'ti-world' },
]

const STATUS_OPTIONS = ['', 'paid', 'due', 'issued', 'open', 'pending', 'collecting', 'failed', 'past_due', 'disputed', 'refunded']

function substitutePlaceholders(template, variables) {
  let out = String(template || '')
  Object.entries(variables || {}).forEach(([key, val]) => {
    out = out.replace(new RegExp(`\\{\\{\\s*${key}\\s*\\}\\}`, 'g'), String(val ?? ''))
  })
  return out
}

function statusPillTone(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'paid' || s === 'approved') return 'success'
  if (s === 'failed' || s === 'rejected') return 'danger'
  if (s === 'issued' || s === 'open' || s === 'pending') return 'warning'
  return 'neutral'
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
  const locked = ['paid', 'void', 'cancelled', 'canceled', 'refunded', 'disputed', 'credited'].includes(st) || Boolean(inv?.disputed)
  if (ddActive) {
    return {
      can_edit: false,
      can_void: false,
      is_locked: true,
      suggested_action: 'stop_collection',
      lock_reason: 'Direct Debit collection is in progress.',
      suggested_action_label: 'Stop DD collection before editing or cancelling.',
    }
  }
  if (locked) {
    return {
      can_edit: false,
      can_void: false,
      is_locked: true,
      lock_reason: st === 'paid' ? 'Paid invoices cannot be edited or cancelled.' : 'This invoice is locked.',
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
  const [menuOpenId, setMenuOpenId] = useState('')
  const [viewInvoice, setViewInvoice] = useState(null)

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
    setError('')
    try {
      const blob = await apiFetchBlob(`/admin/billing/invoices/${encodeURIComponent(invoiceId)}/pdf`)
      if (!blob || blob.size === 0) throw new Error('PDF was empty — check invoice template and server PDF libraries.')
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `invoice-${invoiceNumber || invoiceId}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 30_000)
    } catch (e) {
      setError(e?.message || 'PDF download failed')
    } finally {
      setBusy('')
    }
  }

  const viewHtml = async (invoiceId) => {
    setBusy(invoiceId)
    setError('')
    // Open synchronously on the click gesture so the browser does not block the tab.
    const win = window.open('about:blank', '_blank')
    try {
      const html = await apiFetchText(`/admin/billing/invoices/${encodeURIComponent(invoiceId)}/html`)
      if (!html || !String(html).trim()) throw new Error('Invoice HTML was empty — check the Invoice template tab.')
      const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      if (win && !win.closed) {
        win.location.href = url
      } else {
        const a = document.createElement('a')
        a.href = url
        a.target = '_blank'
        a.rel = 'noopener'
        document.body.appendChild(a)
        a.click()
        a.remove()
        setError('Pop-up was blocked — allow pop-ups for Admin, or use the link that just opened.')
      }
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (e) {
      if (win && !win.closed) win.close()
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
    const reason = window.prompt('Reason for cancelling this invoice (required for audit):', 'Cancelled by support')
    if (!reason) return
    if (!window.confirm(`Cancel invoice ${row.invoice_number || row.id?.slice(0, 8)}?`)) return
    setBusy(row.id)
    setError('')
    setMenuOpenId('')
    try {
      await billingInvoice(row.id, '/cancel', {
        method: 'POST',
        body: JSON.stringify({ reason }),
      })
      await loadInvoices()
    } catch (e) {
      setError(e?.message || 'Cancel failed')
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

  const collectInvoiceDD = async (row) => {
    if (!row?.id) return
    if (!window.confirm(`Collect ${money(row.amount_gbp_pence, row.currency)} via Direct Debit?`)) return
    setBusy(row.id)
    setError('')
    try {
      await billingInvoice(row.id, '/collect', {
        method: 'POST',
        body: JSON.stringify({ method: 'direct_debit' }),
      })
      await loadInvoices()
    } catch (e) {
      setError(e?.message || 'DD collect failed')
    } finally {
      setBusy('')
    }
  }

  const stopDdCollection = async (row) => {
    if (!row?.id) return
    const note = window.prompt('Reason for stopping DD collection:', 'Admin stop collection')
    if (note === null) return
    setBusy(row.id)
    setError('')
    try {
      await apiFetch(`/admin/billing/invoices/${encodeURIComponent(row.id)}/stop-dd-collection`, {
        method: 'POST',
        body: JSON.stringify({ reason: note }),
      })
      await loadInvoices()
    } catch (e) {
      setError(e?.message || 'Stop DD failed')
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
    const isCancelled = st === 'void' || st === 'cancelled' || st === 'canceled'
    const menuOpen = menuOpenId === row.id
    const tags = buildInvoiceTags(row)
    return (
      <tr key={row.id} className="invoiceListRow">
        <td>
          <button type="button" className="invoiceIdLink" onClick={() => setViewInvoice(row)} title="View details">
            <code className="invoiceIdPill">{number}</code>
          </button>
          {row.description ? <div className="invoiceSubLine muted" title={row.description}>{truncate(row.description, 40)}</div> : null}
        </td>
        <td className="invoiceListDate muted">{dateShort(row.created_at)}</td>
        <td className="invoiceListOrg" title={row.organisation_name || row.client_email || ''}>
          <div className="invoiceOrgName">{truncate(row.organisation_name, 32)}</div>
          {row.client_email ? <div className="invoiceSubLine muted">{truncate(row.client_email, 28)}</div> : null}
        </td>
        <td className="invoiceListAmount">
          <strong>{money(row.amount_gbp_pence, row.currency)}</strong>
        </td>
        <td>
          <Pill tone={statusPillTone(isCancelled ? 'failed' : row.status)} className="invoiceStatusPill">
            {isCancelled ? 'cancelled' : (row.status || '—')}
          </Pill>
          {row.disputed ? <span className="invoiceMiniFlag">disputed</span> : null}
          {row.emailed_at ? <span className="invoiceMiniFlag ok" title={dateText(row.emailed_at)}>sent</span> : null}
          {tags.length ? (
            <div className="invoiceMiniTags">
              {tags.slice(0, 2).map((label) => (
                <span key={`${row.id}-${label}`} className="invoiceTag">{label}</span>
              ))}
            </div>
          ) : null}
        </td>
        <td className="invoiceListActions">
          <div className="invoiceIconActions">
            <button type="button" className="invoiceIconBtn" disabled={isBusy} onClick={() => setViewInvoice(row)} title="View">
              <i className="ti ti-eye" />
            </button>
            <button type="button" className="invoiceIconBtn" disabled={isBusy} onClick={() => viewHtml(row.id)} title="Open HTML">
              <i className="ti ti-file-text" />
            </button>
            <button type="button" className="invoiceIconBtn" disabled={isBusy} onClick={() => downloadPdf(row.id, number)} title="Download PDF">
              <i className="ti ti-download" />
            </button>
            {lifecycle.can_edit ? (
              <button type="button" className="invoiceIconBtn" disabled={isBusy} onClick={() => openEditInvoice(row)} title="Edit">
                <i className="ti ti-pencil" />
              </button>
            ) : null}
            {lifecycle.can_void ? (
              <button type="button" className="invoiceIconBtn danger" disabled={isBusy} onClick={() => voidInvoice(row)} title="Cancel invoice">
                <i className="ti ti-x" />
              </button>
            ) : null}
            {lifecycle.suggested_action === 'stop_collection' ? (
              <button type="button" className="invoiceIconBtn warn" disabled={isBusy} onClick={() => stopDdCollection(row)} title="Stop DD collection">
                <i className="ti ti-player-stop" />
              </button>
            ) : null}
            <div className="invoiceMoreWrap">
              <button
                type="button"
                className={`invoiceIconBtn${menuOpen ? ' on' : ''}`}
                disabled={isBusy}
                onClick={() => setMenuOpenId(menuOpen ? '' : row.id)}
                title="More actions"
              >
                <i className="ti ti-dots-vertical" />
              </button>
              {menuOpen ? (
                <div className="invoiceMoreMenu">
                  {!isPaid && !isCancelled ? (
                    <>
                      <button type="button" onClick={() => { setMenuOpenId(''); markInvoicePaid(row) }}>Mark paid</button>
                      <button type="button" onClick={() => { setMenuOpenId(''); collectInvoiceWallet(row) }}>Collect wallet</button>
                      <button type="button" onClick={() => { setMenuOpenId(''); collectInvoiceDD(row) }}>Collect Direct Debit</button>
                    </>
                  ) : null}
                  <button type="button" onClick={() => { setMenuOpenId(''); resendEmail(row.id) }}>Resend email</button>
                  {row.org_id ? (
                    <Link to={`/organisations/${encodeURIComponent(row.org_id)}/control-center`} onClick={() => setMenuOpenId('')}>
                      Open org billing
                    </Link>
                  ) : null}
                  {!row.disputed && st !== 'refunded' && !isCancelled ? (
                    <button type="button" onClick={() => { setMenuOpenId(''); disputeInvoice(row) }}>Dispute</button>
                  ) : null}
                  {row.disputed ? (
                    <button type="button" onClick={() => { setMenuOpenId(''); resolveDispute(row) }}>Resolve dispute</button>
                  ) : null}
                  {st !== 'refunded' && !isCancelled ? (
                    <button type="button" onClick={() => { setMenuOpenId(''); bankRefund(row) }}>Log bank refund</button>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        </td>
      </tr>
    )
  }

  return (
    <div className="ds-scope space-y-4">
      <div className="pageTop">
        <div>
          <h1>Invoices</h1>
          <p>All billing invoices, printable PDF template, and VAT rates by country.</p>
          <p className="mt-1.5 text-xs text-muted-foreground">
            Compact invoice list — use icons to view, edit, or cancel. More actions (collect, mark paid, refund) are under ⋮.
          </p>
        </div>
        <div className="actions">
          {tab === 'invoices' ? (
            <Button type="button" variant="outline" size="sm" className="h-8" onClick={loadInvoices} disabled={loading}>
              Refresh
            </Button>
          ) : null}
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="h-auto flex-wrap">
          {TABS.map((t) => (
            <TabsTrigger key={t.id} value={t.id} className="gap-1.5 text-[12px]">
              <i className={`ti ${t.icon}`} /> {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {tab === 'invoices' ? (
        <>
          {billingRequests.filter((r) => String(r.status || '').toLowerCase() === 'pending').length > 0 ? (
            <Panel className="border-warning/40" bodyClassName="flex flex-wrap items-center justify-between gap-3">
              <div>
                <strong>{billingRequests.filter((r) => String(r.status || '').toLowerCase() === 'pending').length} pending billing request(s)</strong>
                <div className="mt-1 text-[13px] text-muted-foreground">
                  Cancellation and refund reviews awaiting admin action.
                </div>
              </div>
              <Button type="button" size="sm" className="h-8" onClick={() => setTab('requests')}>
                View billing requests
              </Button>
            </Panel>
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

          <Panel title="Filters" bodyClassName="flex flex-wrap items-end gap-3">
            <label className="grid min-w-[160px] flex-1 gap-1">
              <Label className="text-[11px] text-muted-foreground">Search</Label>
              <Input
                className="h-8"
                value={filters.search}
                onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
                placeholder="Invoice #, email, org"
                onKeyDown={(e) => e.key === 'Enter' && loadInvoices()}
              />
            </label>
            <label className="grid min-w-[120px] gap-1">
              <Label className="text-[11px] text-muted-foreground">Status</Label>
              <select
                className="flex h-8 w-full rounded-md border border-input bg-transparent px-3 py-1 text-[12px] shadow-sm"
                value={filters.status}
                onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s || 'all'} value={s}>{s || 'All'}</option>
                ))}
              </select>
            </label>
            <label className="grid min-w-[120px] gap-1">
              <Label className="text-[11px] text-muted-foreground">Provider</Label>
              <Input
                className="h-8"
                value={filters.provider}
                onChange={(e) => setFilters((f) => ({ ...f, provider: e.target.value }))}
                placeholder="gocardless"
              />
            </label>
            <Button type="button" size="sm" className="h-8" onClick={loadInvoices}>Apply</Button>
          </Panel>

          <Panel
            title="All invoices"
            action={<Pill tone="info">{sortedInvoices.length} shown</Pill>}
            bodyClassName="invoiceTableWrap overflow-x-auto"
          >
            {loading ? <div className="text-sm text-muted-foreground">Loading…</div> : null}
            {!loading && !sortedInvoices.length ? (
              <div className="text-sm text-muted-foreground">No invoices yet. Complete a GoCardless payment to create one.</div>
            ) : null}
            {!loading && sortedInvoices.length ? (
              <table className="table invoiceDenseTable invoiceListTable">
                <thead>
                  <tr>
                    <th>Invoice</th>
                    <th>Date</th>
                    <th>Organisation</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th style={{ textAlign: 'right', width: 168 }}>Actions</th>
                  </tr>
                </thead>
                <tbody>{sortedInvoices.map(renderInvoiceRow)}</tbody>
              </table>
            ) : null}
          </Panel>
        </>
      ) : null}

      {tab === 'requests' ? (
        <Panel
          title="Billing requests"
          action={<Pill tone="info">{billingRequests.length} shown</Pill>}
          bodyClassName="invoiceTableWrap overflow-x-auto"
        >
          {loading ? <div className="text-sm text-muted-foreground">Loading…</div> : null}
          {!loading && !billingRequests.length ? (
            <div className="text-sm text-muted-foreground">No cancellation or refund review requests yet.</div>
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
                    <td><Pill tone={statusPillTone(row.status)}>{row.status || '—'}</Pill></td>
                    <td>{row.requested_refund_type ? String(row.requested_refund_type).replace(/_/g, ' ') : '—'}</td>
                    <td style={{ textAlign: 'right' }}>
                      {row.org_id ? (
                        <Button asChild variant="outline" size="sm" className="h-7 text-xs">
                          <Link to={`/organisations/${encodeURIComponent(row.org_id)}/control-center`}>
                            Open org
                          </Link>
                        </Button>
                      ) : null}
                      {row.support_ticket_id ? (
                        <Button asChild variant="outline" size="sm" className="ml-2 h-7 text-xs">
                          <Link to={`/support/tickets/${row.support_ticket_id}`}>
                            Ticket
                          </Link>
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </Panel>
      ) : null}

      {tab === 'template' ? (
        <Panel
          title="Invoice document HTML"
          action={<Pill tone="info">PDF + dashboard view</Pill>}
          bodyClassName="space-y-4"
        >
          <p className="m-0 text-[11px] text-muted-foreground">
            Placeholders: <code>{'{{invoice_number}}'}</code>, <code>{'{{organisation_name}}'}</code>, <code>{'{{line_items_html}}'}</code>,{' '}
            <code>{'{{subtotal}}'}</code>, <code>{'{{tax_amount}}'}</code>, <code>{'{{amount}}'}</code>.
            Email notification: <Link to="/settings/email/templates/new_invoice/edit" className="text-primary hover:underline">new_invoice</Link>.
          </p>

          <div className="emailEditorSplit invoiceTemplateSplit">
            <div className="emailEditorFields space-y-2">
              <Label className="text-[11px] text-muted-foreground">Subject (reference)</Label>
              <Input
                className="h-8"
                value={templateDraft.subject}
                onChange={(e) => setTemplateDraft((d) => ({ ...d, subject: e.target.value }))}
              />
              <Label className="text-[11px] text-muted-foreground">HTML body</Label>
              <Textarea
                className="min-h-[280px] font-mono text-[12px]"
                value={templateDraft.body}
                onChange={(e) => setTemplateDraft((d) => ({ ...d, body: e.target.value }))}
                placeholder="<html>…</html>"
              />
            </div>

            <div className="msgFieldBlock msgFieldBlockTight emailEditorPreviewCol space-y-2">
              <Label className="text-[11px] text-muted-foreground">
                <i className="ti ti-eye mr-1.5" />
                Live HTML preview
              </Label>
              <div className="emailPreviewBox emailPreviewBoxTall invoiceDocPreviewBox">
                {previewHtml ? (
                  <div className="emailPreviewInner invoiceDocPreviewInner" dangerouslySetInnerHTML={{ __html: previewHtml }} />
                ) : (
                  <p className="m-0 text-sm text-muted-foreground">HTML preview appears here.</p>
                )}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" className="h-8" onClick={saveTemplate} disabled={templateSaving}>
              <i className="ti ti-device-floppy" />
              {templateSaving ? 'Saving…' : 'Save invoice template'}
            </Button>
            {templateMsg ? <span className="text-xs text-muted-foreground">{templateMsg}</span> : null}
          </div>
        </Panel>
      ) : null}

      {tab === 'vat' ? (
        <>
          <Panel title="Add / update country VAT" bodyClassName="flex flex-wrap items-end gap-3">
            <label className="grid min-w-[80px] gap-1">
              <Label className="text-[11px] text-muted-foreground">Code</Label>
              <Input className="h-8" maxLength={2} value={vatDraft.country_code} onChange={(e) => setVatDraft((d) => ({ ...d, country_code: e.target.value.toUpperCase() }))} placeholder="AE" />
            </label>
            <label className="grid min-w-[180px] flex-1 gap-1">
              <Label className="text-[11px] text-muted-foreground">Country</Label>
              <Input className="h-8" value={vatDraft.country_name} onChange={(e) => setVatDraft((d) => ({ ...d, country_name: e.target.value }))} placeholder="United Arab Emirates" />
            </label>
            <label className="grid min-w-[100px] gap-1">
              <Label className="text-[11px] text-muted-foreground">VAT %</Label>
              <Input className="h-8" type="number" min="0" step="0.01" value={vatDraft.vat_rate_percent} onChange={(e) => setVatDraft((d) => ({ ...d, vat_rate_percent: e.target.value }))} />
            </label>
            <label className="grid min-w-[160px] flex-1 gap-1">
              <Label className="text-[11px] text-muted-foreground">Notes</Label>
              <Input className="h-8" value={vatDraft.notes} onChange={(e) => setVatDraft((d) => ({ ...d, notes: e.target.value }))} placeholder="Optional" />
            </label>
            <Button type="button" size="sm" className="h-8" disabled={busy === 'vat'} onClick={saveVat}>Save</Button>
          </Panel>

          <Panel title="VAT rates" bodyClassName="invoiceTableWrap overflow-x-auto">
            {loading ? <div className="text-sm text-muted-foreground">Loading…</div> : null}
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
                        <Input
                          className="h-8 w-[90px]"
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
                      <td className="text-xs text-muted-foreground">{row.notes || '—'}</td>
                      <td className="text-[11px] text-muted-foreground">{row.updated_at ? dateText(row.updated_at) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </Panel>
        </>
      ) : null}

      {editInvoice ? (
        <div className="invoiceModalScrim" onClick={() => !editBusy && setEditInvoice(null)}>
          <div className="invoiceModalCard ds-scope" onClick={(e) => e.stopPropagation()}>
            <div className="invoiceModalHead">
              <h3>Edit invoice {editInvoice.invoice_number || editInvoice.id?.slice(0, 8)}</h3>
              <button type="button" className="invoiceIconBtn" onClick={() => setEditInvoice(null)} disabled={editBusy}><i className="ti ti-x" /></button>
            </div>
            <div className="invoiceModalBody space-y-3">
              <label className="grid gap-1">
                <Label className="text-[11px] text-muted-foreground">Amount ({editInvoice?.currency ? `${currencySymbol(editInvoice.currency)} ex VAT` : 'ex VAT'})</Label>
                <Input className="h-8" type="number" min="0" step="0.01" value={editAmount} onChange={(e) => setEditAmount(e.target.value)} />
              </label>
              <label className="grid gap-1">
                <Label className="text-[11px] text-muted-foreground">Due date</Label>
                <Input className="h-8" type="date" value={editDue} onChange={(e) => setEditDue(e.target.value)} />
              </label>
              <label className="grid gap-1">
                <Label className="text-[11px] text-muted-foreground">Description</Label>
                <Input className="h-8" type="text" value={editDesc} onChange={(e) => setEditDesc(e.target.value)} />
              </label>
              <div className="invoiceModalActions flex gap-2">
                <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => setEditInvoice(null)} disabled={editBusy}>Close</Button>
                <Button type="button" size="sm" className="h-8" onClick={saveEditInvoice} disabled={editBusy}>{editBusy ? 'Saving…' : 'Save changes'}</Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {viewInvoice ? (
        <div className="invoiceModalScrim" onClick={() => setViewInvoice(null)}>
          <div className="invoiceModalCard invoiceViewCard ds-scope" onClick={(e) => e.stopPropagation()}>
            <div className="invoiceModalHead">
              <h3>{viewInvoice.invoice_number || viewInvoice.external_invoice_id || 'Invoice'}</h3>
              <button type="button" className="invoiceIconBtn" onClick={() => setViewInvoice(null)}><i className="ti ti-x" /></button>
            </div>
            <div className="invoiceModalBody invoiceViewGrid">
              <div><span className="label">Organisation</span><strong>{viewInvoice.organisation_name || '—'}</strong></div>
              <div><span className="label">Email</span><strong>{viewInvoice.client_email || '—'}</strong></div>
              <div><span className="label">Amount</span><strong>{money(viewInvoice.amount_gbp_pence, viewInvoice.currency)}</strong></div>
              <div><span className="label">Status</span><strong>{viewInvoice.status || '—'}</strong></div>
              <div><span className="label">Created</span><strong>{dateText(viewInvoice.created_at)}</strong></div>
              <div><span className="label">Due</span><strong>{dateShort(viewInvoice.due_date)}</strong></div>
              <div className="invoiceViewFull"><span className="label">Description</span><strong>{viewInvoice.description || '—'}</strong></div>
              <div className="invoiceViewFull"><span className="label">Provider / method</span><strong>{[viewInvoice.provider, viewInvoice.payment_method].filter(Boolean).join(' · ') || '—'}</strong></div>
              <div className="invoiceModalActions invoiceViewFull flex flex-wrap gap-2">
                <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => viewHtml(viewInvoice.id)}><i className="ti ti-file-text" /> HTML</Button>
                <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => downloadPdf(viewInvoice.id, viewInvoice.invoice_number)}><i className="ti ti-download" /> PDF</Button>
                {resolveInvoiceLifecycle(viewInvoice).can_edit ? (
                  <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => { setViewInvoice(null); openEditInvoice(viewInvoice) }}><i className="ti ti-pencil" /> Edit</Button>
                ) : null}
                {resolveInvoiceLifecycle(viewInvoice).can_void ? (
                  <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => { setViewInvoice(null); voidInvoice(viewInvoice) }}><i className="ti ti-x" /> Cancel</Button>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
