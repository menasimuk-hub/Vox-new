import React, { useState } from 'react'
import { Link } from 'react-router-dom'
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
  { value: 'superadmin', label: 'Superadmin — full console + manage platform admins' },
  { value: 'accountant', label: 'Accountant — billing & organisations (no integrations, secrets, admin CRUD)' },
  { value: 'marketing', label: 'Marketing — SMTP & templates (no billing sinks or integrations)' },
]

export default function AdminUserCreate() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('marketing')
  const [isActive, setIsActive] = useState(true)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setErr('')
    setMsg('')
    try {
      const res = await apiFetch('/admin/admin-users', {
        method: 'POST',
        body: JSON.stringify({
          email: String(email || '').trim(),
          password: String(password || ''),
          role: String(role || '').trim().toLowerCase(),
          is_active: Boolean(isActive),
          is_superuser: String(role || '').trim().toLowerCase() === 'superadmin',
        }),
      })
      setMsg(
        `Created platform admin for ${res?.email || email}. Sign in via the same public VOXBULK login URL using this email and password.`,
      )
      setEmail('')
      setPassword('')
    } catch (e2) {
      setErr(e2?.message || 'Create failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='ds-scope space-y-4'>
      <div className='pageTop'>
        <div>
          <h1>Add platform admin</h1>
          <p>
            Creates a login for internal VOXBULK operators — not organisation users invited to a customer account
            (those live under <strong>Organisations → Users</strong> once you pick an organisation).
          </p>
        </div>
        <div className='actions'>
          <Button asChild variant='secondary' size='sm' className='h-8'>
            <Link to='/platform/users'>Back to list</Link>
          </Button>
        </div>
      </div>

      <Panel
        title='New platform admin'
        subtitle='Superadmin-only create form.'
        action={<Pill tone='info'>Superadmin-only</Pill>}
        className='mx-auto w-full max-w-[720px]'
        bodyClassName='space-y-3'
      >
        {err ? (
          <div className='rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive'>
            {err}
          </div>
        ) : null}
        {msg ? (
          <div className='rounded-md border border-border bg-secondary/40 px-3 py-2 text-sm text-foreground'>{msg}</div>
        ) : null}

        <form onSubmit={submit} className='grid gap-3'>
          <div className='space-y-1'>
            <Label htmlFor='admin-create-email' className='text-[12px]'>
              Email
            </Label>
            <Input
              id='admin-create-email'
              className='h-8'
              type='email'
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder='ops@yourcompany.com'
              required
            />
          </div>

          <div className='space-y-1'>
            <Label htmlFor='admin-create-password' className='text-[12px]'>
              Temporary password
            </Label>
            <Input
              id='admin-create-password'
              className='h-8'
              type='password'
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder='Min 6 characters'
              required
              minLength={6}
            />
          </div>

          <div className='space-y-1'>
            <Label htmlFor='admin-create-role' className='text-[12px]'>
              Platform role
            </Label>
            <Select value={role} onValueChange={setRole}>
              <SelectTrigger id='admin-create-role' className='h-8 text-[12px]'>
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
            <input type='checkbox' checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
            Active (can sign in)
          </label>

          <div className='pt-1'>
            <Button type='submit' size='sm' className='h-8' disabled={busy}>
              {busy ? 'Creating…' : 'Create platform admin'}
            </Button>
          </div>
        </form>
      </Panel>
    </div>
  )
}
