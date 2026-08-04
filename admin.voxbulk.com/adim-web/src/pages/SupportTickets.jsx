import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import SupportDiskShell from '../components/supportDisk/SupportDiskShell'
import TicketTable from '../components/supportDisk/TicketTable'

export default function SupportTickets({ onlyOpen = true, title = 'Open Tickets' }) {
  const [tickets, setTickets] = useState([])
  const [admins, setAdmins] = useState([])
  const [cannedReplies, setCannedReplies] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [rows, people, canned] = await Promise.all([apiFetch('/admin/support/tickets'), apiFetch('/admin/support/admins').catch(() => []), apiFetch('/admin/support/canned/replies?active_only=true').catch(() => [])])
      setTickets(Array.isArray(rows) ? rows : []); setAdmins(Array.isArray(people) ? people : []); setCannedReplies(Array.isArray(canned) ? canned : [])
    } catch (e) { setError(e.message || 'Could not load tickets') } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])
  const visible = useMemo(() => onlyOpen ? tickets.filter((t) => ['open', 'pending', 'waiting'].includes(t.status)) : tickets, [tickets, onlyOpen])
  const status = async (ids, value) => { await apiFetch('/admin/support/tickets/bulk-status', { method: 'POST', body: { ticket_ids: ids, status: value } }); load() }
  const assign = async (ids, value) => { await apiFetch('/admin/support/tickets/bulk-assign', { method: 'POST', body: { ticket_ids: ids, assigned_admin_user_id: value || null } }); load() }
  const remove = async (ids) => { await status(ids, 'closed') }
  return <SupportDiskShell title={title} subtitle={`${visible.length} tickets in this queue`}>
    {error ? <div className="m-4 rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</div> : null}
    <div className="h-[calc(100vh-120px)]"><TicketTable tickets={visible} admins={admins} cannedReplies={cannedReplies} loading={loading} onOpen={(id) => navigate(`/support/tickets/${id}`)} onBulkStatus={status} onBulkAssign={assign} onDelete={remove} /></div>
  </SupportDiskShell>
}

