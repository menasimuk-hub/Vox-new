import React from 'react'
import { apiFetch } from '../lib/api'

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
    <div className='page'>
      <div className='pageHead'>
        <div>
          <h1>Script moderation</h1>
          <p>Review flagged interview and survey scripts before customers can launch calls.</p>
        </div>
        <button className='btn soft' type='button' onClick={() => void load()} disabled={loading}>
          Refresh
        </button>
      </div>

      {error ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.35)' }}>{error}</div> : null}

      <div className='card'>
        <div className='cardHead'>
          <h3>Pending review</h3>
          <span className='pill'>{items.length} queued</span>
        </div>
        <div className='cardBody'>
          {loading ? <p className='muted'>Loading…</p> : null}
          {!loading && items.length === 0 ? (
            <p className='muted'>No scripts waiting for admin approval.</p>
          ) : null}
          {!loading && items.length > 0 ? (
            <div className='stack' style={{ gap: 16 }}>
              {items.map((row) => (
                <div key={row.order_id} className='note' style={{ display: 'grid', gap: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                    <div>
                      <strong>{row.title || row.order_id}</strong>
                      <div className='muted' style={{ fontSize: 12 }}>
                        {row.service_code} · {row.status} · payment {row.payment_status || '—'}
                      </div>
                    </div>
                    <div className='muted' style={{ fontSize: 12 }}>{fmtWhen(row.updated_at)}</div>
                  </div>
                  <div>
                    <span className='pill' style={{ textTransform: 'capitalize' }}>
                      {String(row.script_moderation_category || 'flagged')}
                    </span>
                  </div>
                  <p style={{ margin: 0 }}>{String(row.script_moderation_reason || 'Flagged by content review.')}</p>
                  <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: 12, maxHeight: 180, overflow: 'auto' }}>
                    {String(row.script_excerpt || '')}
                  </pre>
                  <textarea
                    className='input'
                    rows={2}
                    placeholder='Optional admin note'
                    value={String(notes[row.order_id] || '')}
                    onChange={(e) => setNotes((s) => ({ ...s, [row.order_id]: e.target.value }))}
                  />
                  <div className='actions'>
                    <button
                      className='btn primary'
                      type='button'
                      disabled={busyId === row.order_id}
                      onClick={() => void act(row.order_id, 'approve')}
                    >
                      Approve script
                    </button>
                    <button
                      className='btn soft'
                      type='button'
                      disabled={busyId === row.order_id}
                      onClick={() => void act(row.order_id, 'reject')}
                    >
                      Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
