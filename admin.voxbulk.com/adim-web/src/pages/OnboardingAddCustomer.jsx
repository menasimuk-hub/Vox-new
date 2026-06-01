import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'

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
    <>
      <div className='pageTop'>
        <div>
          <h1>Add customer</h1>
          <p>Create a new organisation and first login user. All required fields must be completed before the account is active.</p>
        </div>
        <div className='actions'>
          <button type='button' className='btn soft' onClick={() => navigate('/organisations')}>
            All organisations
          </button>
        </div>
      </div>

      <div className='card' style={{ maxWidth: 640 }}>
        <div className='cardHead'>
          <h3>Organisation &amp; user</h3>
          <span className='pill p-cyan'>Admin setup</span>
        </div>
        <div className='cardBody'>
          {error ? (
            <div className='note' style={{ marginBottom: 14, borderColor: 'rgba(220,38,38,0.35)' }}>
              {error}
            </div>
          ) : null}
          <form className='stack' style={{ gap: 14 }} onSubmit={submit}>
            <div className='formField'>
              <label className='label' htmlFor='add-org-name'>
                Organisation name <span style={{ color: '#dc2626' }}>*</span>
              </label>
              <input
                id='add-org-name'
                className='input'
                required
                value={form.orgName}
                onChange={(e) => set('orgName', e.target.value)}
                placeholder='Acme Dental Ltd'
              />
            </div>
            <div className='formField'>
              <label className='label' htmlFor='add-country'>
                Country
              </label>
              <select id='add-country' className='select' value={form.country} onChange={(e) => set('country', e.target.value)}>
                {COUNTRIES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
            <div className='orgProfileGrid2'>
              <div className='formField'>
                <label className='label' htmlFor='add-contact-name'>
                  Contact name
                </label>
                <input id='add-contact-name' className='input' value={form.contactName} onChange={(e) => set('contactName', e.target.value)} />
              </div>
              <div className='formField'>
                <label className='label' htmlFor='add-contact-email'>
                  Contact email
                </label>
                <input id='add-contact-email' className='input' type='email' value={form.contactEmail} onChange={(e) => set('contactEmail', e.target.value)} />
              </div>
            </div>

            <hr style={{ border: 0, borderTop: '1px solid var(--line)' }} />

            <div className='formField'>
              <label className='label' htmlFor='add-user-email'>
                User email (login) <span style={{ color: '#dc2626' }}>*</span>
              </label>
              <input
                id='add-user-email'
                className='input'
                type='email'
                required
                autoComplete='off'
                value={form.userEmail}
                onChange={(e) => set('userEmail', e.target.value)}
                placeholder='owner@clinic.com'
              />
            </div>
            <div className='formField'>
              <label className='label' htmlFor='add-password'>
                Password <span style={{ color: '#dc2626' }}>*</span>
              </label>
              <input
                id='add-password'
                className='input'
                type='password'
                required
                minLength={6}
                autoComplete='new-password'
                value={form.password}
                onChange={(e) => set('password', e.target.value)}
                placeholder='Minimum 6 characters'
              />
            </div>
            <div className='formField'>
              <label className='label' htmlFor='add-role'>
                Role <span style={{ color: '#dc2626' }}>*</span>
              </label>
              <select id='add-role' className='select' required value={form.role} onChange={(e) => set('role', e.target.value)}>
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>

            <div className='actions'>
              <button type='submit' className='btn primary' disabled={busy}>
                {busy ? 'Creating…' : 'Create organisation & user'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  )
}
