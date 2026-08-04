import React, { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Pill } from '@/components/ui/Badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select'

const ROLES = [
  { value: 'superadmin', label: 'Superadmin (full access, can manage admins)' },
  { value: 'accountant', label: 'Accountant (billing & organisations — no integrations / admin CRUD)' },
  { value: 'marketing', label: 'Marketing (email / templates — no integrations or billing sinks)' },
]

export default function AdminUserEdit() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('marketing')
  const [active, setActive] = useState(true)
  const [newPassword, setNewPassword] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setErr('')
      try {
        const rows = await apiFetch('/admin/admin-users')
        const row = Array.isArray(rows) ? rows.find((r) => r.id === id) : null
        if (!row) throw new Error('Admin user not found')
        if (cancelled) return
        setEmail(row.email || '')
        setRole(String(row.role || 'marketing').toLowerCase())
        setActive(!!row.is_active)
      } catch (e) {
        if (!cancelled) setErr(e?.message || 'Load failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [id])

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    setErr('')
    try {
      const body = {
        role: String(role || '').trim().toLowerCase(),
        is_active: Boolean(active),
      }
      const pw = String(newPassword || '').trim()
      if (pw.length > 0) {
        body.password = pw
      }
      await apiFetch(`/admin/admin-users/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) })
      navigate('/platform/users')
    } catch (e2) {
      setErr(e2?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className='ds-scope space-y-4'>
      <div className='pageTop'>
        <div>
          <h1>Edit platform admin</h1>
          <p>
            Updates the <strong>platform</strong> admin account backing this login (not organisation / invite users
            listed on an organisation).
          </p>
        </div>
        <div className='actions'>
          <Button type='button' variant='secondary' size='sm' className='h-8' onClick={() => navigate('/platform/users')}>
            Back to list
          </Button>
        </div>
      </div>

      <Panel
        title={email || id}
        subtitle='Superadmin-only edit form.'
        action={<Pill tone='info'>Superadmin-only</Pill>}
        className='mx-auto w-full max-w-[720px]'
        bodyClassName='space-y-3'
      >
        {err ? (
          <div className='rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive'>
            {err}
          </div>
        ) : null}
        {loading ? (
          <p className='text-sm text-muted-foreground'>Loading…</p>
        ) : (
          <form onSubmit={save} className='grid gap-3'>
            <div className='space-y-1'>
              <Label htmlFor='admin-edit-email' className='text-[12px]'>
                Email
              </Label>
              <Input id='admin-edit-email' className='h-8' value={email} readOnly />
            </div>

            <div className='space-y-1'>
              <Label htmlFor='admin-edit-role' className='text-[12px]'>
                Platform role
              </Label>
              <Select value={role} onValueChange={setRole}>
                <SelectTrigger id='admin-edit-role' className='h-8 text-[12px]'>
                  <SelectValue placeholder='Select a role' />
                </SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => (
                    <SelectItem key={r.value} value={r.value}>
                      {r.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <label className='flex cursor-pointer items-center gap-2.5 text-sm text-muted-foreground'>
              <input type='checkbox' checked={active} onChange={(e) => setActive(e.target.checked)} />
              Active (can sign in)
            </label>

            <div className='space-y-1'>
              <Label htmlFor='admin-edit-password' className='text-[12px]'>
                New password (optional)
              </Label>
              <Input
                id='admin-edit-password'
                className='h-8'
                type='password'
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder='Leave blank to keep current password'
                minLength={6}
                autoComplete='new-password'
              />
            </div>

            <div className='pt-1'>
              <Button type='submit' size='sm' className='h-8' disabled={saving}>
                {saving ? 'Saving…' : 'Save changes'}
              </Button>
            </div>
          </form>
        )}
      </Panel>
    </div>
  )
}
