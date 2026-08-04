import React, { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiFetch, getAdminAccessTokenRaw, resolveApiUrl } from '../lib/api'

function dt(v) {
  if (!v) return '—'
  try { return new Date(v).toLocaleString() } catch { return String(v) }
}

function Badge({ value }) {
  const v = String(value || '').toLowerCase()
  const cls = v === 'closed' ? 'p-green' : v === 'pending' ? 'p-amber' : 'p-cyan'
  return <span className={`pill ${cls}`}>{value || '—'}</span>
}

export default function SupportTicketDetail() {
  const { ticketId } = useParams()
  const navigate = useNavigate()
  const [detail, setDetail] = useState(null)
  const [admins, setAdmins] = useState([])
  const [reply, setReply] = useState('')
  const [internal, setInternal] = useState(false)
  const [canned, setCanned] = useState([])
  const [cannedSearch, setCannedSearch] = useState('')
  const [cannedOpen, setCannedOpen] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const [d, a] = await Promise.all([
        apiFetch(`/admin/support/tickets/${ticketId}`),
        apiFetch('/admin/support/admins').catch(() => []),
      ])
      setDetail(d)
      setAdmins(Array.isArray(a) ? a : [])
    } catch (e) {
      setError(e?.message || 'Could not load ticket')
    }
  }, [ticketId])

  const loadCanned = useCallback(async () => {
    const qs = new URLSearchParams({ active_only: 'true' })
    if (cannedSearch.trim()) qs.set('search', cannedSearch.trim())
    setCanned(await apiFetch(`/admin/support/canned/replies?${qs.toString()}`).catch(() => []))
  }, [cannedSearch])

  useEffect(() => { load() }, [load])
  useEffect(() => { loadCanned() }, [loadCanned])

  const updateStatus = async (status) => {
    await apiFetch(`/admin/support/tickets/${ticketId}/status`, { method: 'POST', body: JSON.stringify({ status }) })
    await load()
  }

  const assign = async (adminId) => {
    await apiFetch(`/admin/support/tickets/${ticketId}/assign`, { method: 'POST', body: JSON.stringify({ assigned_admin_user_id: adminId || null }) })
    await load()
  }

  const sendReply = async () => {
    if (!reply.trim()) return
    await apiFetch(`/admin/support/tickets/${ticketId}/reply`, {
      method: 'POST',
      body: JSON.stringify({ message: reply.trim(), is_internal_note: internal }),
    })
    setReply('')
    setInternal(false)
    await load()
  }

  const downloadAttachment = async (a) => {
    const res = await fetch(resolveApiUrl(`/admin/support/attachments/${a.id}`), {
      headers: { Authorization: `Bearer ${getAdminAccessTokenRaw()}` },
    })
    if (!res.ok) {
      setError('Could not download attachment')
      return
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = a.filename
    link.click()
    URL.revokeObjectURL(url)
  }

  const t = detail?.ticket

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>{t ? `${t.public_ref} · ${t.subject}` : 'Ticket detail'}</h1>
          <p>{t ? `${t.organisation_name || '—'} · ${t.created_by_email || '—'}` : 'Loading ticket...'}</p>
        </div>
        <div className="actions"><Link className="btn soft" to="/support/tickets">Back to tickets</Link><button className="btn soft" onClick={load}>Refresh</button></div>
      </div>
      {error ? <div className="card" style={{ marginBottom: 16, borderColor: '#fecaca' }}><div className="cardBody" style={{ color: '#b91c1c' }}>{error}</div></div> : null}
      {!t ? <div className="card"><div className="cardBody muted">Loading...</div></div> : (
        <div className={`ticketDetailLayout ${cannedOpen ? '' : 'cannedHidden'}`}>
          <main className="stack">
            <div className="card">
              <div className="cardHead"><h3>Ticket information</h3><Badge value={t.status} /></div>
              <div className="cardBody">
                <div className="grid-4">
                  <div className="listRow"><span>Reference</span><strong>{t.public_ref}</strong></div>
                  <div className="listRow"><span>Category</span><strong>{t.category}</strong></div>
                  <div className="listRow"><span>Created</span><strong>{dt(t.created_at)}</strong></div>
                  <div className="listRow"><span>Last activity</span><strong>{dt(t.last_message_at)}</strong></div>
                </div>
                <div className="filters" style={{ marginTop: 14 }}>
                  <select className="input" value={t.status} onChange={(e) => updateStatus(e.target.value)}><option value="open">open</option><option value="pending">pending</option><option value="closed">closed</option></select>
                  <select className="input" value={t.assigned_admin_user_id || ''} onChange={(e) => assign(e.target.value)}><option value="">Unassigned</option>{admins.map((a) => <option key={a.id} value={a.id}>{a.email}</option>)}</select>
                </div>
              </div>
            </div>
            <div className="card">
              <div className="cardHead"><h3>Conversation</h3></div>
              <div className="cardBody threadPanel">
                {(detail.messages || []).map((m) => <div className={`threadBubble ${m.sender_type}`} key={m.id}><strong>{m.sender_email || m.sender_type}</strong>{m.is_internal_note ? <span className="pill p-amber">Internal</span> : null}<p>{m.body}</p>{(m.attachments || []).length ? <div className="attachmentList">{m.attachments.map((a) => <button className="pill p-cyan" key={a.id} onClick={() => downloadAttachment(a)}>{a.filename}</button>)}</div> : null}<small>{dt(m.created_at)}</small></div>)}
              </div>
            </div>
            <div className="card">
              <div className="cardHead"><h3>Reply</h3><button className="btn soft" onClick={() => setCannedOpen((v) => !v)}>{cannedOpen ? 'Hide canned replies' : 'Show canned replies'}</button></div>
              <div className="cardBody">
                <textarea className="input replyTextareaFull" rows={9} value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Write your reply..." />
                <div className="actions" style={{ marginTop: 12 }}><label style={{ display: 'flex', gap: 8, alignItems: 'center' }}><input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> Internal note</label><button className="btn primary" onClick={sendReply}>Send reply</button></div>
              </div>
            </div>
          </main>
          {cannedOpen ? <aside className="card cannedSidebar"><div className="cardHead"><h3>Canned replies</h3></div><div className="cardBody"><input className="input" value={cannedSearch} onChange={(e) => setCannedSearch(e.target.value)} placeholder="Search canned replies..." /><div className="cannedList" style={{ marginTop: 12 }}>{canned.length ? canned.map((c) => <div key={c.id} className="cannedItem"><strong>{c.title}</strong><span>{c.category_name || 'Uncategorised'}</span><p><b>Q:</b> {c.question}</p><p><b>A:</b> {c.answer}</p><button className="btn soft" type="button" onClick={() => setReply(c.answer)}>Apply reply</button></div>) : <p className="muted">No canned replies found.</p>}</div></div></aside> : null}
        </div>
      )}
    </>
  )
}

