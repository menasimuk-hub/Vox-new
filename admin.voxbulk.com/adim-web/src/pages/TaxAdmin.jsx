import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'

export default function TaxAdmin() {
  const [vatRates, setVatRates] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [vatDraft, setVatDraft] = useState({ country_code: '', country_name: '', vat_rate_percent: '0', notes: '' })

  const loadVat = useCallback(async () => {
    const rows = await apiFetch('/admin/billing/vat-rates')
    setVatRates(Array.isArray(rows) ? rows : [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        await loadVat()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loadVat])

  const saveVat = async () => {
    const code = vatDraft.country_code.trim().toUpperCase()
    if (code.length !== 2) {
      setError('Country code must be 2 letters (e.g. GB, DE)')
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

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Tax &amp; VAT</h1>
          <p>Country VAT rates used on invoices. Same data as Invoices → VAT by country.</p>
          <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            Invoice template settings: <Link to="/billing/invoices?tab=template">Invoices → Invoice template</Link>
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn soft" onClick={loadVat} disabled={loading}>Refresh</button>
        </div>
      </div>

      {error ? <div className="note" style={{ borderColor: 'rgba(220,38,38,0.35)', marginBottom: 12 }}>{error}</div> : null}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="cardHead"><h3>Add / update VAT rate</h3></div>
        <div className="cardBody invoiceFilterGrid">
          <label className="msgFieldBlockTight">
            <span className="label">Country code</span>
            <input className="input" value={vatDraft.country_code} onChange={(e) => setVatDraft((d) => ({ ...d, country_code: e.target.value }))} placeholder="GB" />
          </label>
          <label className="msgFieldBlockTight">
            <span className="label">Country name</span>
            <input className="input" value={vatDraft.country_name} onChange={(e) => setVatDraft((d) => ({ ...d, country_name: e.target.value }))} />
          </label>
          <label className="msgFieldBlockTight">
            <span className="label">VAT %</span>
            <input className="input" type="number" min="0" step="0.01" value={vatDraft.vat_rate_percent} onChange={(e) => setVatDraft((d) => ({ ...d, vat_rate_percent: e.target.value }))} />
          </label>
          <label className="msgFieldBlockTight" style={{ gridColumn: '1 / -1' }}>
            <span className="label">Notes</span>
            <input className="input" value={vatDraft.notes} onChange={(e) => setVatDraft((d) => ({ ...d, notes: e.target.value }))} />
          </label>
          <button type="button" className="btn primary" disabled={busy === 'vat'} onClick={saveVat}>{busy === 'vat' ? 'Saving…' : 'Save rate'}</button>
        </div>
      </div>

      <div className="card">
        <div className="cardHead"><h3>VAT by country</h3></div>
        <div className="cardBody invoiceTableWrap">
          {loading ? <p className="muted">Loading…</p> : null}
          {!loading && !vatRates.length ? <p className="muted">No VAT rates configured.</p> : null}
          {!loading && vatRates.length > 0 ? (
            <table className="table billingTable">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Country</th>
                  <th>VAT %</th>
                  <th>Enabled</th>
                  <th>Notes</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {vatRates.map((row) => (
                  <tr key={row.country_code}>
                    <td><strong>{row.country_code}</strong></td>
                    <td>{row.country_name}</td>
                    <td>{row.vat_rate_percent}%</td>
                    <td>{row.is_enabled ? 'Yes' : 'No'}</td>
                    <td className="muted">{row.notes || '—'}</td>
                    <td>
                      <button type="button" className="btn soft xs" disabled={busy === row.country_code} onClick={() => updateVatRow({ ...row, is_enabled: !row.is_enabled })}>
                        {row.is_enabled ? 'Disable' : 'Enable'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
      </div>
    </>
  )
}
