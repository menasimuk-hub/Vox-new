import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import SupportDiskShell from '../components/supportDisk/SupportDiskShell'
import TicketDetail from '../components/supportDisk/TicketDetail'

export default function SupportTicketDetail() {
  const { ticketId } = useParams()
  const navigate = useNavigate()
  const [detail, setDetail] = useState(null)
  const [admins, setAdmins] = useState([])
  const [canned, setCanned] = useState([])
  const [links, setLinks] = useState([])
  const [faqs, setFaqs] = useState([])
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const [d, a, c, h, f] = await Promise.all([
        apiFetch(`/admin/support/tickets/${ticketId}`),
        apiFetch('/admin/support/admins').catch(() => []),
        apiFetch('/admin/support/canned/replies?active_only=true').catch(() => []),
        apiFetch('/admin/support/help-links').catch(() => []),
        apiFetch('/admin/faq/items?limit=200').catch(() => []),
      ])
      setDetail(d)
      setAdmins(Array.isArray(a) ? a : [])
      setCanned(Array.isArray(c) ? c : [])
      setLinks(Array.isArray(h) ? h : [])
      setFaqs(Array.isArray(f) ? f : [])
    } catch (e) {
      setError(e?.message || 'Could not load ticket')
    }
  }, [ticketId])

  useEffect(() => { load() }, [load])

  const updateStatus = async (status) => {
    await apiFetch(`/admin/support/tickets/${ticketId}/status`, { method: 'POST', body: JSON.stringify({ status }) })
    await load()
  }

  const assign = async (adminId) => {
    await apiFetch(`/admin/support/tickets/${ticketId}/assign`, { method: 'POST', body: JSON.stringify({ assigned_admin_user_id: adminId || null }) })
    await load()
  }

  const sendReply = async (message, internal) => {
    await apiFetch(`/admin/support/tickets/${ticketId}/reply`, {
      method: 'POST',
      body: { message, is_internal_note: internal },
    })
    await load()
  }
  const t = detail?.ticket
  return <SupportDiskShell title={t?.public_ref || 'Ticket detail'} subtitle={t?.organisation_name || 'Support Disk conversation'}>
    {error ? <div className="m-4 rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</div> : null}
    {!t ? <div className="p-10 text-center text-muted-foreground">Loading ticket…</div> : <div className="h-[calc(100vh-120px)]"><TicketDetail ticket={t} messages={detail.messages || []} admins={admins} cannedReplies={canned} helpLinks={links} faqs={faqs} onBack={() => navigate('/support/tickets')} onStatusChange={updateStatus} onAssign={assign} onSend={sendReply} onPolish={async (draft) => { const data = await apiFetch(`/admin/support/tickets/${ticketId}/polish-reply`, { method: 'POST', body: { draft } }); return data.polished }} /></div>}
  </SupportDiskShell>
}

