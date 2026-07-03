import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Inbox, RefreshCw } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { Button } from '../components/ui/Button'
import { cn } from '../lib/utils'

function formatWhen(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

export default function WaInboundMessages() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [q, setQ] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ limit: '200' })
      if (q.trim()) params.set('q', q.trim())
      const data = await apiFetch(`/admin/wa-messages/inbound?${params}`)
      setRows(Array.isArray(data?.messages) ? data.messages : [])
    } catch (e) {
      setError(e?.message || 'Could not load inbound messages')
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [q])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="space-y-4 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Inbox className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-lg font-semibold">WhatsApp inbound messages</h1>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Every message received on WhatsApp via the Meta webhook (and legacy providers).
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to="/ai/wa-templates"
            className="inline-flex h-8 items-center gap-1 rounded-md border px-2.5 text-xs text-muted-foreground hover:bg-accent"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> WA Templates
          </Link>
          <Button size="sm" variant="outline" className="h-8 gap-1.5 text-xs" onClick={() => void load()} disabled={loading}>
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
            Refresh
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input
          className="h-8 w-full max-w-sm rounded-md border border-input bg-background px-2 text-xs"
          placeholder="Search phone or body…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void load()
          }}
        />
        <Button size="sm" className="h-8 text-xs" onClick={() => void load()}>
          Search
        </Button>
      </div>

      {error ? <p className="text-xs text-destructive">{error}</p> : null}

      <div className="overflow-hidden rounded-lg border bg-card">
        <table className="w-full text-left text-xs">
          <thead className="border-b bg-surface-muted/50 text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">When</th>
              <th className="px-3 py-2 font-medium">From</th>
              <th className="px-3 py-2 font-medium">To</th>
              <th className="px-3 py-2 font-medium">Provider</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Message</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-muted-foreground">
                  No inbound messages yet. Replies appear here when Meta delivers webhooks.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id} className="border-b last:border-0 hover:bg-accent/30">
                  <td className="whitespace-nowrap px-3 py-2 text-muted-foreground">{formatWhen(row.created_at)}</td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono">{row.from_number || '—'}</td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono">{row.to_number || '—'}</td>
                  <td className="px-3 py-2">{row.provider || '—'}</td>
                  <td className="px-3 py-2">{row.status || '—'}</td>
                  <td className="max-w-md truncate px-3 py-2" title={row.body || ''}>
                    {row.body || '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
