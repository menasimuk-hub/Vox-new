import React from 'react'
import { RefreshCw } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Textarea } from '@/components/ui/Textarea'
import { Pill } from '@/components/ui/Badge'

function fmtWhen(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

export default function ScriptModeration() {
  const [items, setItems] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [busyId, setBusyId] = React.useState('')
  const [notes, setNotes] = React.useState({})

  const load = React.useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await apiFetch('/admin/platform-services/script-moderation/queue')
      setItems(Array.isArray(res?.items) ? res.items : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load moderation queue')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    void load()
  }, [load])

  const act = async (orderId, action) => {
    setBusyId(orderId)
    setError('')
    try {
      await apiFetch(`/admin/platform-services/orders/${encodeURIComponent(orderId)}/script-moderation/${action}`, {
        method: 'POST',
        body: JSON.stringify({ note: String(notes[orderId] || '').trim() }),
      })
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : `Could not ${action} script`)
    } finally {
      setBusyId('')
    }
  }

  return (
    <div className='ds-scope space-y-4'>
      <div className='pageTop'>
        <div>
          <h1>Script moderation</h1>
          <p>Review flagged interview and survey scripts before customers can launch calls.</p>
        </div>
        <div className='actions'>
          <Button variant='outline' size='sm' className='h-8' type='button' onClick={() => void load()} disabled={loading}>
            <RefreshCw className={loading ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
            Refresh
          </Button>
        </div>
      </div>

      {error ? (
        <div className='rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive'>
          {error}
        </div>
      ) : null}

      <Panel
        title='Pending review'
        subtitle='Scripts waiting for admin approval before launch.'
        action={<Pill tone='info'>{items.length} queued</Pill>}
        bodyClassName='space-y-3'
      >
        {loading ? <p className='text-sm text-muted-foreground'>Loading…</p> : null}
        {!loading && items.length === 0 ? (
          <p className='text-sm text-muted-foreground'>No scripts waiting for admin approval.</p>
        ) : null}
        {!loading && items.length > 0 ? (
          <div className='space-y-4'>
            {items.map((row) => (
              <div
                key={row.order_id}
                className='space-y-2.5 rounded-lg border border-border bg-surface-muted/40 p-3'
              >
                <div className='flex flex-wrap items-start justify-between gap-3'>
                  <div>
                    <strong className='text-sm text-foreground'>{row.title || row.order_id}</strong>
                    <div className='text-[12px] text-muted-foreground'>
                      {row.service_code} · {row.status} · payment {row.payment_status || '—'}
                    </div>
                  </div>
                  <div className='text-[12px] text-muted-foreground'>{fmtWhen(row.updated_at)}</div>
                </div>
                <div>
                  <Pill tone='warning' className='capitalize'>
                    {String(row.script_moderation_category || 'flagged')}
                  </Pill>
                </div>
                <p className='m-0 text-sm text-foreground'>
                  {String(row.script_moderation_reason || 'Flagged by content review.')}
                </p>
                <pre className='m-0 max-h-[180px] overflow-auto whitespace-pre-wrap rounded-md border border-border bg-background p-2 text-[12px] text-foreground'>
                  {String(row.script_excerpt || '')}
                </pre>
                <Textarea
                  rows={2}
                  placeholder='Optional admin note'
                  value={String(notes[row.order_id] || '')}
                  onChange={(e) => setNotes((s) => ({ ...s, [row.order_id]: e.target.value }))}
                />
                <div className='flex flex-wrap gap-2'>
                  <Button
                    size='sm'
                    className='h-8'
                    type='button'
                    disabled={busyId === row.order_id}
                    onClick={() => void act(row.order_id, 'approve')}
                  >
                    Approve script
                  </Button>
                  <Button
                    variant='outline'
                    size='sm'
                    className='h-8'
                    type='button'
                    disabled={busyId === row.order_id}
                    onClick={() => void act(row.order_id, 'reject')}
                  >
                    Reject
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </Panel>
    </div>
  )
}
