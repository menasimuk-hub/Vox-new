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
      const [d, a, c, h, f, kb] = await Promise.all([
        apiFetch(`/admin/support/tickets/${ticketId}`),
        apiFetch('/admin/support/admins').catch(() => []),
        apiFetch('/admin/support/canned/replies?active_only=true').catch(() => []),
        apiFetch('/admin/support/help-links?active_only=true').catch(() => []),
        apiFetch('/admin/faq/items?surface=dashboard&visible_only=true&limit=200').catch(() => []),
        apiFetch('/admin/support/kb/articles?kind=article&published_only=true').catch(() => []),
      ])
      setDetail(d)
      setAdmins(Array.isArray(a) ? a : [])
      setCanned(Array.isArray(c) ? c : [])
      setLinks(Array.isArray(h) ? h : [])
      const faqRows = Array.isArray(f) ? f.filter((x) => x.is_published !== false) : []
      const kbRows = Array.isArray(kb)
        ? kb.map((x) => ({ id: `kb-${x.id}`, question: x.title, answer: `${x.body || ''}\n\n${x.url || ''}`.trim() }))
        : []
      setFaqs([...faqRows, ...kbRows])
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
  const polishReply = async (draft) => {
    const data = await apiFetch(`/admin/support/tickets/${ticketId}/polish-reply`, { method: 'POST', body: { draft } })
    return data.polished
  }
  const writeReply = async () => {
    const recent = (detail?.messages || []).slice(-6).map((message) => `${message.sender_type}: ${message.body}`).join('\n')
    const prompt = `Write a concise, professional customer support reply. Return only the reply text.\n\nTicket: ${detail?.ticket?.subject || ''}\nRequester: ${detail?.ticket?.requester_email || detail?.ticket?.created_by_email || 'Customer'}\nConversation:\n${recent}`
    return polishReply(prompt)
  }
  const archiveTicket = async () => {
    await apiFetch(`/admin/support/tickets/${ticketId}/status`, { method: 'POST', body: { status: 'closed' } })
    navigate('/support/archive')
  }
  const t = detail?.ticket
  return <SupportDiskShell title={t?.public_ref || 'Ticket detail'} subtitle={t?.organisation_name || 'Support Disk conversation'}>
    {error ? <div className="m-4 rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</div> : null}
    {!t ? <div className="p-10 text-center text-muted-foreground">Loading ticket…</div> : <div className="h-[calc(100vh-120px)]"><TicketDetail ticket={t} messages={detail.messages || []} admins={admins} cannedReplies={canned} helpLinks={links} faqs={faqs} onBack={() => navigate('/support/tickets')} onStatusChange={updateStatus} onAssign={assign} onSend={sendReply} onPolish={polishReply} onWriteAi={writeReply} onArchive={archiveTicket} /></div>}
  </SupportDiskShell>
}

