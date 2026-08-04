import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import SupportDiskShell from '../components/supportDisk/SupportDiskShell'
import TicketTable from '../components/supportDisk/TicketTable'

export default function SupportTickets({ onlyOpen = true, title = 'Open Tickets' }) {
  const [tickets, setTickets] = useState([])
  const [admins, setAdmins] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [rows, people] = await Promise.all([apiFetch('/admin/support/tickets'), apiFetch('/admin/support/admins').catch(() => [])])
      setTickets(Array.isArray(rows) ? rows : []); setAdmins(Array.isArray(people) ? people : [])
    } catch (e) { setError(e.message || 'Could not load tickets') } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])
  const visible = useMemo(() => onlyOpen ? tickets.filter((t) => ['open', 'pending', 'waiting'].includes(t.status)) : tickets, [tickets, onlyOpen])
  const status = async (ids, value) => { await Promise.all(ids.map((id) => apiFetch(`/admin/support/tickets/${id}/status`, { method: 'POST', body: { status: value } }))); load() }
  const assign = async (ids, value) => { await Promise.all(ids.map((id) => apiFetch(`/admin/support/tickets/${id}/assign`, { method: 'POST', body: { assigned_admin_user_id: value || null } }))); load() }
  return <SupportDiskShell title={title} subtitle={`${visible.length} tickets in this queue`}>
    {error ? <div className="m-4 rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</div> : null}
    <div className="h-[calc(100vh-120px)]"><TicketTable tickets={visible} admins={admins} loading={loading} onOpen={(id) => navigate(`/support/tickets/${id}`)} onBulkStatus={status} onBulkAssign={assign} /></div>
  </SupportDiskShell>
}

