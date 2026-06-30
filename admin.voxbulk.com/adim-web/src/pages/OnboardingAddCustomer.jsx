import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
  { value: 'owner', label: 'Owner' },
  { value: 'manager', label: 'Manager' },
  { value: 'dental', label: 'Dental' },
  { value: 'receptionist', label: 'Receptionist' },
]

const COUNTRIES = [
  { value: 'United Kingdom', label: 'United Kingdom (GB)' },
  { value: 'United States', label: 'United States (USA)' },
  { value: 'Canada', label: 'Canada (CA)' },
  { value: 'Australia', label: 'Australia (AU)' },
]

export default function OnboardingAddCustomer() {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    orgName: '',
    country: 'United Kingdom',
    contactName: '',
    contactEmail: '',
    userEmail: '',
    password: '',
    role: 'owner',
  })

  const set = (key, value) => setForm((s) => ({ ...s, [key]: value }))

  const submit = async (e) => {
    e.preventDefault()
    setError('')

    const orgName = form.orgName.trim()
    const userEmail = form.userEmail.trim().toLowerCase()
    const password = form.password.trim()
    const role = form.role.trim()

    if (!orgName) {
      setError('Organisation name is required.')
      return
    }
    if (!userEmail || !userEmail.includes('@')) {
      setError('A valid user email is required.')
      return
    }
    if (password.length < 6) {
      setError('Password is required (minimum 6 characters).')
      return
    }
    if (!role) {
      setError('User role is required.')
      return
    }

    setBusy(true)
    try {
      const org = await apiFetch('/admin/organisations', {
        method: 'POST',
        body: JSON.stringify({
          name: orgName,
          country: form.country.trim() || null,
          contact_name: form.contactName.trim() || null,
          contact_email: form.contactEmail.trim() || userEmail,
        }),
      })
      await apiFetch(`/admin/organisations/${org.id}/users`, {
        method: 'POST',
        body: JSON.stringify({
          email: userEmail,
          password,
          role,
        }),
      })
      const users = await apiFetch(`/admin/organisations/${org.id}/users`)
      const created = Array.isArray(users) ? users.find((u) => String(u.email || '').toLowerCase() === userEmail) : null
      localStorage.setItem('voxbulk_admin_selected_org_id', org.id)
      const userQuery = created?.user_id ? `&user_id=${encodeURIComponent(created.user_id)}` : ''
      navigate(`/organisations/profile?tab=users${userQuery}`)
    } catch (err) {
      setError(err?.message || 'Could not create customer')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='ds-scope space-y-4'>
      <div className='pageTop'>
        <div>
          <h1>Add customer</h1>
          <p>Create a new organisation and first login user. All required fields must be completed before the account is active.</p>
        </div>
        <div className='actions'>
          <Button type='button' variant='outline' size='sm' className='h-8' onClick={() => navigate('/organisations')}>
            All organisations
          </Button>
        </div>
      </div>

      <form onSubmit={submit} className='space-y-4'>
        <Panel
          title='Organisation'
          subtitle='Company details for the new account.'
          action={<Pill tone='info'>Admin setup</Pill>}
        >
          {error ? (
            <div className='mb-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive'>
              {error}
            </div>
          ) : null}
          <div className='grid gap-3 sm:grid-cols-2'>
            <div className='space-y-1 sm:col-span-2'>
              <Label htmlFor='add-org-name' className='text-[12px]'>
                Organisation name <span className='text-destructive'>*</span>
              </Label>
              <Input
                id='add-org-name'
                className='h-8'
                required
                value={form.orgName}
                onChange={(e) => set('orgName', e.target.value)}
                placeholder='Acme Dental Ltd'
              />
            </div>
            <div className='space-y-1'>
              <Label htmlFor='add-country' className='text-[12px]'>
                Country
              </Label>
              <Select value={form.country} onValueChange={(v) => set('country', v)}>
                <SelectTrigger id='add-country' className='h-8 text-[12px]'>
                  <SelectValue placeholder='Select a country' />
                </SelectTrigger>
                <SelectContent>
                  {COUNTRIES.map((c) => (
                    <SelectItem key={c.value} value={c.value}>
                      {c.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='space-y-1'>
              <Label htmlFor='add-contact-name' className='text-[12px]'>
                Contact name
              </Label>
              <Input
                id='add-contact-name'
                className='h-8'
                value={form.contactName}
                onChange={(e) => set('contactName', e.target.value)}
              />
            </div>
            <div className='space-y-1 sm:col-span-2'>
              <Label htmlFor='add-contact-email' className='text-[12px]'>
                Contact email
              </Label>
              <Input
                id='add-contact-email'
                className='h-8'
                type='email'
                value={form.contactEmail}
                onChange={(e) => set('contactEmail', e.target.value)}
              />
            </div>
          </div>
        </Panel>

        <Panel title='First login user' subtitle='Owner / staff account used to sign in.'>
          <div className='grid gap-3 sm:grid-cols-2'>
            <div className='space-y-1'>
              <Label htmlFor='add-user-email' className='text-[12px]'>
                User email (login) <span className='text-destructive'>*</span>
              </Label>
              <Input
                id='add-user-email'
                className='h-8'
                type='email'
                required
                autoComplete='off'
                value={form.userEmail}
                onChange={(e) => set('userEmail', e.target.value)}
                placeholder='owner@clinic.com'
              />
            </div>
            <div className='space-y-1'>
              <Label htmlFor='add-password' className='text-[12px]'>
                Password <span className='text-destructive'>*</span>
              </Label>
              <Input
                id='add-password'
                className='h-8'
                type='password'
                required
                minLength={6}
                autoComplete='new-password'
                value={form.password}
                onChange={(e) => set('password', e.target.value)}
                placeholder='Minimum 6 characters'
              />
            </div>
            <div className='space-y-1'>
              <Label htmlFor='add-role' className='text-[12px]'>
                Role <span className='text-destructive'>*</span>
              </Label>
              <Select value={form.role} onValueChange={(v) => set('role', v)}>
                <SelectTrigger id='add-role' className='h-8 text-[12px]'>
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
          </div>
          <div className='mt-3 flex justify-end'>
            <Button type='submit' size='sm' className='h-8' disabled={busy}>
              {busy ? 'Creating…' : 'Create organisation & user'}
            </Button>
          </div>
        </Panel>
      </form>
    </div>
  )
}
