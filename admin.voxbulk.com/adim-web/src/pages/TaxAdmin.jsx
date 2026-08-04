import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableLoading,
  TableRow,
} from '@/components/ui/Table'

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
    <div className="ds-scope space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0">
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">Tax &amp; VAT</h1>
          <p className="text-[11px] leading-tight text-muted-foreground">
            Country VAT rates used on invoices. Same data as Invoices → VAT by country.
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            Invoice template settings:{' '}
            <Link
              to="/billing/invoices?tab=template"
              className="font-medium text-foreground underline-offset-2 hover:underline"
            >
              Invoices → Invoice template
            </Link>
          </p>
        </div>
        <div className="ml-auto">
          <Button type="button" variant="outline" size="sm" className="h-8" onClick={loadVat} disabled={loading}>
            Refresh
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <Panel title="Add / update VAT rate" bodyClassName="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="space-y-1.5">
            <Label className="text-[11px] text-muted-foreground">Country code</Label>
            <Input
              className="h-8"
              value={vatDraft.country_code}
              onChange={(e) => setVatDraft((d) => ({ ...d, country_code: e.target.value }))}
              placeholder="GB"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-[11px] text-muted-foreground">Country name</Label>
            <Input
              className="h-8"
              value={vatDraft.country_name}
              onChange={(e) => setVatDraft((d) => ({ ...d, country_name: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-[11px] text-muted-foreground">VAT %</Label>
            <Input
              className="h-8"
              type="number"
              min="0"
              step="0.01"
              value={vatDraft.vat_rate_percent}
              onChange={(e) => setVatDraft((d) => ({ ...d, vat_rate_percent: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2 lg:col-span-3">
            <Label className="text-[11px] text-muted-foreground">Notes</Label>
            <Input
              className="h-8"
              value={vatDraft.notes}
              onChange={(e) => setVatDraft((d) => ({ ...d, notes: e.target.value }))}
            />
          </div>
        </div>
        <Button type="button" size="sm" className="h-8" disabled={busy === 'vat'} onClick={saveVat}>
          {busy === 'vat' ? 'Saving…' : 'Save rate'}
        </Button>
      </Panel>

      <Panel title="VAT by country">
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Code</TableHead>
              <TableHead>Country</TableHead>
              <TableHead>VAT %</TableHead>
              <TableHead>Enabled</TableHead>
              <TableHead>Notes</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? <TableLoading colSpan={6} /> : null}
            {!loading && !vatRates.length ? (
              <TableEmpty colSpan={6}>No VAT rates configured.</TableEmpty>
            ) : null}
            {!loading &&
              vatRates.map((row) => (
                <TableRow key={row.country_code}>
                  <TableCell>
                    <strong className="font-medium">{row.country_code}</strong>
                  </TableCell>
                  <TableCell>{row.country_name}</TableCell>
                  <TableCell>{row.vat_rate_percent}%</TableCell>
                  <TableCell>{row.is_enabled ? 'Yes' : 'No'}</TableCell>
                  <TableCell className="text-muted-foreground">{row.notes || '—'}</TableCell>
                  <TableCell className="text-right">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-7"
                      disabled={busy === row.country_code}
                      onClick={() => updateVatRow({ ...row, is_enabled: !row.is_enabled })}
                    >
                      {row.is_enabled ? 'Disable' : 'Enable'}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
