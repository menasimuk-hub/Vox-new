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
  { id: 'template', label: 'Invoice template', icon: 'ti-file-invoice' },
  { id: 'vat', label: 'VAT by country', icon: 'ti-world' },
]

const STATUS_OPTIONS = ['', 'paid', 'issued', 'open', 'failed']

function substitutePlaceholders(template, variables) {
  let out = String(template || '')
  Object.entries(variables || {}).forEach(([key, val]) => {
    out = out.replace(new RegExp(`\\{\\{\\s*${key}\\s*\\}\\}`, 'g'), String(val ?? ''))
  })
  return out
}

function statusClass(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'paid') return 'invoiceCardPaid'
  if (s === 'failed') return 'invoiceCardFailed'
  return 'invoiceCardPending'
}

export default function InvoicesAdmin() {
  const [tab, setTab] = useState('invoices')
  const [invoices, setInvoices] = useState([])
  const [vatRates, setVatRates] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [filters, setFilters] = useState({ search: '', status: '', provider: '' })
  const [templateDraft, setTemplateDraft] = useState({ subject: '', body: '', is_enabled: true })
  const [templateSaving, setTemplateSaving] = useState(false)
  const [templateMsg, setTemplateMsg] = useState('')
  const [vatDraft, setVatDraft] = useState({ country_code: '', country_name: '', vat_rate_percent: '0', notes: '' })

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
  }, [tab, loadInvoices, loadVat, loadTemplate])

  const stats = useMemo(() => {
    const paidRows = invoices.filter((r) => String(r.status || '').toLowerCase() === 'paid')
    const paidTotal = paidRows.reduce((sum, r) => sum + Number(r.amount_gbp_pence || 0), 0)
    return { count: invoices.length, paid: paidRows.length, paidTotal, total: invoices.reduce((s, r) => s + Number(r.amount_gbp_pence || 0), 0) }
  }, [invoices])

  const paidInvoices = useMemo(
    () => invoices.filter((r) => String(r.status || '').toLowerCase() === 'paid'),
    [invoices],
  )

  const otherInvoices = useMemo(
    () => invoices.filter((r) => String(r.status || '').toLowerCase() !== 'paid'),
    [invoices],
  )

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

  const renderInvoiceCard = (row) => {
    const number = row.invoice_number || row.external_invoice_id
    const isPaid = String(row.status || '').toLowerCase() === 'paid'
    return (
      <article key={row.id} className={`invoiceCard ${statusClass(row.status)}`}>
        <div className="invoiceCardTop">
          <div className="invoiceCardIdBlock">
            <span className="invoiceCardLabel">Invoice</span>
            <code className="invoiceCardId">{number}</code>
          </div>
          <span className={`pill ${isPaid ? 'p-green' : 'p-amber'}`}>{row.status}</span>
        </div>
        <div className="invoiceCardAmount">{money(row.amount_gbp_pence, row.currency)}</div>
        <div className="invoiceCardMeta">
          <div><i className="ti ti-building" /> {row.organisation_name || '—'}</div>
          <div><i className="ti ti-mail" /> {row.client_email}</div>
          <div><i className="ti ti-calendar" /> {dateShort(row.created_at)}</div>
          {row.description ? <div><i className="ti ti-file-description" /> {row.description}</div> : null}
          <div className="invoiceCardTags">
            {row.tax_rate_percent != null ? <span className="invoiceTag">VAT {row.tax_rate_percent}%</span> : null}
            <span className="invoiceTag">{row.provider}</span>
            {row.emailed_at ? <span className="invoiceTag invoiceTagOk"><i className="ti ti-check" /> Emailed</span> : <span className="invoiceTag">Not emailed</span>}
          </div>
        </div>
        <div className="invoiceCardActions">
          <button type="button" className="btn soft xs" disabled={busy === row.id} onClick={() => viewHtml(row.id)}>
            <i className="ti ti-eye" /> View
          </button>
          <button type="button" className="btn soft xs" disabled={busy === row.id} onClick={() => downloadPdf(row.id, number)}>
            <i className="ti ti-download" /> PDF
          </button>
          <button type="button" className="btn primary xs" disabled={busy === row.id} onClick={() => resendEmail(row.id)}>
            <i className="ti ti-send" /> Email
          </button>
        </div>
      </article>
    )
  }

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Invoices</h1>
          <p>All billing invoices, printable PDF template, and VAT rates by country.</p>
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
          <div className="grid-3" style={{ marginBottom: 14 }}>
            <div className="card stat" style={{ '--accent': '#0f766e' }}>
              <div className="muted">Invoices</div>
              <div className="statValue">{stats.count}</div>
            </div>
            <div className="card stat" style={{ '--accent': '#059669' }}>
              <div className="muted">Paid</div>
              <div className="statValue">{stats.paid}</div>
              <span className="pill p-green">{money(stats.paidTotal)} collected</span>
            </div>
            <div className="card stat" style={{ '--accent': '#7c3aed' }}>
              <div className="muted">Listed total</div>
              <div className="statValue">{money(stats.total)}</div>
            </div>
          </div>

          <div className="card invoiceHubFilters">
            <div className="cardBody invoiceFilterGrid">
              <label className="msgFieldBlockTight">
                <span className="label">Search invoice ID, email, org</span>
                <input
                  className="input"
                  value={filters.search}
                  onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
                  placeholder="INV-2026-0001 or email"
                />
              </label>
              <label className="msgFieldBlockTight">
                <span className="label">Status</span>
                <select className="input" value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}>
                  {STATUS_OPTIONS.map((s) => (
                    <option key={s || 'all'} value={s}>{s || 'All statuses'}</option>
                  ))}
                </select>
              </label>
              <label className="msgFieldBlockTight">
                <span className="label">Provider</span>
                <input className="input" value={filters.provider} onChange={(e) => setFilters((f) => ({ ...f, provider: e.target.value }))} placeholder="gocardless" />
              </label>
              <button type="button" className="btn primary" onClick={loadInvoices}>Apply</button>
            </div>
          </div>

          {loading ? <div className="muted" style={{ marginTop: 16 }}>Loading…</div> : null}
          {!loading && !invoices.length ? (
            <div className="card" style={{ marginTop: 14 }}>
              <div className="cardBody muted">No invoices yet. Complete a GoCardless sandbox payment to create one.</div>
            </div>
          ) : null}

          {!loading && paidInvoices.length ? (
            <section className="invoiceSection">
              <div className="invoiceSectionHead">
                <h3><i className="ti ti-circle-check" /> Paid invoices</h3>
                <span className="muted">{paidInvoices.length} invoice{paidInvoices.length === 1 ? '' : 's'}</span>
              </div>
              <div className="invoiceCardGrid">{paidInvoices.map(renderInvoiceCard)}</div>
            </section>
          ) : null}

          {!loading && otherInvoices.length ? (
            <section className="invoiceSection">
              <div className="invoiceSectionHead">
                <h3><i className="ti ti-clock" /> Other invoices</h3>
                <span className="muted">{otherInvoices.length} invoice{otherInvoices.length === 1 ? '' : 's'}</span>
              </div>
              <div className="invoiceCardGrid invoiceCardGridCompact">{otherInvoices.map(renderInvoiceCard)}</div>
            </section>
          ) : null}
        </>
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
    </>
  )
}
