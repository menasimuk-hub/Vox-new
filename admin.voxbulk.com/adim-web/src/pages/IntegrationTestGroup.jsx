import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Pill } from '@/components/ui/Badge'
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

export default function IntegrationTestGroup() {
  const [items, setItems] = useState([])
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [flash, setFlash] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await apiFetch('/admin/integration-testers')
      setItems(Array.isArray(res?.items) ? res.items : [])
    } catch (e) {
      setError(e?.message || 'Failed to load testers')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const add = async (e) => {
    e.preventDefault()
    const value = email.trim()
    if (!value) return
    setBusy(true)
    setError('')
    try {
      await apiFetch('/admin/integration-testers', {
        method: 'POST',
        body: JSON.stringify({ email: value }),
      })
      setEmail('')
      setFlash('Tester added')
      window.setTimeout(() => setFlash(''), 3000)
      await load()
    } catch (err) {
      setError(err?.message || 'Could not add email')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id) => {
    setBusy(true)
    setError('')
    try {
      await apiFetch(`/admin/integration-testers/${id}`, { method: 'DELETE' })
      setFlash('Tester removed')
      window.setTimeout(() => setFlash(''), 3000)
      await load()
    } catch (err) {
      setError(err?.message || 'Could not remove')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="ds-scope space-y-4">
      <div className="min-w-0">
        <h1 className="text-[15px] font-semibold leading-tight text-foreground">Integration Test group</h1>
        <p className="text-[11px] leading-tight text-muted-foreground">
          Login emails that can see integrations set to <strong>Testing</strong> (dashboard tiles and linked FAQs).
          Live integrations are visible to everyone.
        </p>
      </div>

      {flash ? (
        <div className="rounded-md border border-success/40 bg-success-soft px-3 py-2 text-sm text-success">
          {flash}
        </div>
      ) : null}
      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <Panel title="Add tester" subtitle="Email must match a dashboard login.">
        <form onSubmit={add} className="flex flex-wrap items-center gap-2">
          <Input
            type="email"
            placeholder="tester@example.com"
            value={email}
            onChange={(ev) => setEmail(ev.target.value)}
            className="h-8 min-w-[260px] flex-1"
            disabled={busy}
          />
          <Button type="submit" size="sm" className="h-8" disabled={busy || !email.trim()}>
            {busy ? 'Saving…' : 'Add email'}
          </Button>
        </form>
      </Panel>

      <Panel
        title="Testers"
        subtitle="Emails allowed to see Testing-mode integrations."
        action={
          <div className="flex items-center gap-2">
            <Pill tone="info">{items.length}</Pill>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7"
              onClick={() => void load()}
              disabled={loading || busy}
            >
              Refresh
            </Button>
          </div>
        }
        bodyClassName="p-0"
      >
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Email</TableHead>
              <TableHead>Added</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && <TableLoading colSpan={3} />}
            {!loading && items.length === 0 && <TableEmpty colSpan={3}>No tester emails yet.</TableEmpty>}
            {!loading &&
              items.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="font-medium">{row.email}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {row.created_at ? String(row.created_at).replace('T', ' ').slice(0, 19) : '—'}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7"
                        disabled={busy}
                        onClick={() => void remove(row.id)}
                      >
                        Remove
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
