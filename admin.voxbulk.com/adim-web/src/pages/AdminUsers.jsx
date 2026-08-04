import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { useAdminProfile } from '../context/AdminProfileContext'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
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

export default function AdminUsers() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [rows, setRows] = useState([])
  const { profile } = useAdminProfile()
  const canManage = !!profile?.can_manage_admin_users

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch('/admin/admin-users')
      setRows(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e?.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const del = async (id) => {
    if (!canManage) return
    const ok = window.confirm(
      'Disable and remove this platform admin login? Organisation users on customer accounts are unaffected.',
    )
    if (!ok) return
    try {
      await apiFetch(`/admin/admin-users/${encodeURIComponent(id)}`, { method: 'DELETE' })
      await load()
    } catch (e) {
      setError(e?.message || 'Delete failed')
    }
  }

  return (
    <div className='ds-scope space-y-4'>
      <div className='pageTop'>
        <div>
          <h1>Platform admin users</h1>
          <p>
            Separate from <strong>organisation users</strong> (managed under each organisation). Platform admins
            manage VOXBULK internally (billing, onboarding, integrations, SMTP/templates). Only{' '}
            <strong>superadmin</strong> can create/delete these users.
          </p>
        </div>
        <div className='actions'>
          <Button asChild variant='secondary' size='sm' className='h-8'>
            <Link to='/platform/users/new'>Add platform admin</Link>
          </Button>
          <Button variant='outline' size='sm' className='h-8' onClick={load} disabled={loading}>
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
        title='Users'
        subtitle='Platform console logins (not organisation invites).'
        action={<Pill tone='info'>{rows.length} total</Pill>}
        bodyClassName='overflow-x-auto'
        className='mx-auto w-full max-w-[980px]'
      >
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Email</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Superadmin</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className='text-right'>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableLoading colSpan={6} />
            ) : rows.length === 0 ? (
              <TableEmpty colSpan={6}>No admin users found.</TableEmpty>
            ) : (
              rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>{r.email}</TableCell>
                  <TableCell>{r.is_active ? 'Active' : 'Disabled'}</TableCell>
                  <TableCell>{r.is_superuser ? 'Yes' : 'No'}</TableCell>
                  <TableCell className='text-muted-foreground'>{r.role || '-'}</TableCell>
                  <TableCell className='text-muted-foreground'>
                    {r.created_at ? new Date(r.created_at).toLocaleString() : '-'}
                  </TableCell>
                  <TableCell className='text-right'>
                    {canManage ? (
                      <div className='inline-flex items-center gap-2'>
                        <Button asChild variant='secondary' size='sm' className='h-8'>
                          <Link to={`/platform/users/${encodeURIComponent(r.id)}/edit`}>Edit</Link>
                        </Button>
                        <Button variant='outline' size='sm' className='h-8' onClick={() => del(r.id)}>
                          Delete
                        </Button>
                      </div>
                    ) : (
                      <span className='text-muted-foreground'>—</span>
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
