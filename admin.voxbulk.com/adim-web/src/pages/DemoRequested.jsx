import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Input } from '../components/ui/Input'
import { Textarea } from '../components/ui/Textarea'

const LANGS = [
  { id: 'en', label: 'English' },
  { id: 'ar', label: 'Arabic' },
]

const emptyManual = {
  contact_name: '',
  email: '',
  company_name: '',
  whatsapp: '',
  website: '',
  preferred_language: 'en',
  message: '',
}

export default function DemoRequested() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [statusFilter, setStatusFilter] = useState('pending')
  const [manualOpen, setManualOpen] = useState(false)
  const [manual, setManual] = useState(emptyManual)
  const [compose, setCompose] = useState(null)
  const [settings, setSettings] = useState({ provider_agent_id: '', from_email: '', soft_cap_minutes: 7 })
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const q = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : ''
      const [list, st, preview] = await Promise.all([
        apiFetch(`/admin/ai-demo/requests${q}`),
        apiFetch('/admin/ai-demo/settings'),
        apiFetch('/admin/ai-demo/invite-preview').catch(() => null),
      ])
      setItems(list.items || [])
      setSettings({
        provider_agent_id: st.provider_agent_id || '',
        from_email: st.from_email || '',
        soft_cap_minutes: st.soft_cap_minutes || 7,
        notes: st.notes || '',
        _previewSubject: preview?.subject || '',
        _previewBody: preview?.body || '',
      })
    } catch (e) {
      setError(e?.message || 'Failed to load demo requests')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    refresh()
  }, [refresh])

  const openApprove = (row) => {
    setCompose({
      id: row.id,
      mode: 'approve',
      subject_override: settings._previewSubject || '',
      body_override: settings._previewBody || '',
      skip_wa: false,
    })
  }

  const sendApprove = async () => {
    if (!compose?.id) return
    setBusy(true)
    try {
      await apiFetch(`/admin/ai-demo/requests/${compose.id}/approve`, {
        method: 'POST',
        body: JSON.stringify({
          subject_override: compose.subject_override || null,
          body_override: compose.body_override || null,
          skip_wa: Boolean(compose.skip_wa),
        }),
      })
      setCompose(null)
      await refresh()
    } catch (e) {
      alert(e?.message || 'Approve failed')
    } finally {
      setBusy(false)
    }
  }

  const reject = async (id) => {
    const reason = window.prompt('Reject reason (optional)') || ''
    setBusy(true)
    try {
      await apiFetch(`/admin/ai-demo/requests/${id}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      })
      await refresh()
    } catch (e) {
      alert(e?.message || 'Reject failed')
    } finally {
      setBusy(false)
    }
  }

  const resend = async (id) => {
    setBusy(true)
    try {
      await apiFetch(`/admin/ai-demo/requests/${id}/resend`, { method: 'POST' })
      await refresh()
    } catch (e) {
      alert(e?.message || 'Resend failed')
    } finally {
      setBusy(false)
    }
  }

  const sendManual = async () => {
    setBusy(true)
    try {
      await apiFetch('/admin/ai-demo/requests/manual', {
        method: 'POST',
        body: JSON.stringify(manual),
      })
      setManualOpen(false)
      setManual(emptyManual)
      setStatusFilter('')
      await refresh()
    } catch (e) {
      alert(e?.message || 'Send failed')
    } finally {
      setBusy(false)
    }
  }

  const saveSettings = async () => {
    setBusy(true)
    try {
      await apiFetch('/admin/ai-demo/settings', {
        method: 'PUT',
        body: JSON.stringify({
          provider_agent_id: settings.provider_agent_id,
          from_email: settings.from_email,
          soft_cap_minutes: Number(settings.soft_cap_minutes) || 7,
          notes: settings.notes || '',
        }),
      })
      await refresh()
    } catch (e) {
      alert(e?.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='space-y-4 p-4 md:p-6'>
      <div className='flex flex-wrap items-center justify-between gap-3'>
        <div>
          <h1 className='text-xl font-semibold'>Demo requested</h1>
          <p className='text-sm text-muted-foreground'>Approve website requests or send a manual AI demo invite.</p>
        </div>
        <div className='flex gap-2'>
          <Button variant='outline' onClick={() => refresh()} disabled={loading || busy}>
            Refresh
          </Button>
          <Button onClick={() => setManualOpen(true)}>New demo invite</Button>
        </div>
      </div>

      {error && <div className='rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm'>{error}</div>}

      <Card>
        <CardHeader>
          <CardTitle className='text-base'>Telnyx / email settings</CardTitle>
        </CardHeader>
        <CardContent className='grid gap-3 md:grid-cols-3'>
          <label className='text-sm'>
            Telnyx assistant ID
            <Input
              className='mt-1'
              value={settings.provider_agent_id}
              onChange={(e) => setSettings((s) => ({ ...s, provider_agent_id: e.target.value }))}
              placeholder='Falls back to Talk-to-us assistant if empty'
            />
          </label>
          <label className='text-sm'>
            From / reply email
            <Input
              className='mt-1'
              value={settings.from_email}
              onChange={(e) => setSettings((s) => ({ ...s, from_email: e.target.value }))}
              placeholder='hello@voxbulk.com'
            />
          </label>
          <label className='text-sm'>
            Soft cap (minutes)
            <Input
              className='mt-1'
              type='number'
              min={3}
              max={30}
              value={settings.soft_cap_minutes}
              onChange={(e) => setSettings((s) => ({ ...s, soft_cap_minutes: e.target.value }))}
            />
          </label>
          <div className='md:col-span-3'>
            <Button onClick={saveSettings} disabled={busy}>
              Save settings
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className='flex flex-wrap gap-2'>
        {['pending', 'approved', 'active', 'completed', 'rejected', ''].map((s) => (
          <Button
            key={s || 'all'}
            size='sm'
            variant={statusFilter === s ? 'default' : 'outline'}
            onClick={() => setStatusFilter(s)}
          >
            {s || 'all'}
          </Button>
        ))}
      </div>

      <Card>
        <CardContent className='p-0 overflow-x-auto'>
          <table className='w-full text-sm'>
            <thead>
              <tr className='border-b text-left'>
                <th className='p-3'>When</th>
                <th className='p-3'>Contact</th>
                <th className='p-3'>Company</th>
                <th className='p-3'>WhatsApp</th>
                <th className='p-3'>Lang</th>
                <th className='p-3'>Source</th>
                <th className='p-3'>Status</th>
                <th className='p-3'>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td className='p-4 text-muted-foreground' colSpan={8}>
                    Loading…
                  </td>
                </tr>
              )}
              {!loading && items.length === 0 && (
                <tr>
                  <td className='p-4 text-muted-foreground' colSpan={8}>
                    No requests
                  </td>
                </tr>
              )}
              {items.map((row) => (
                <tr key={row.id} className='border-b align-top'>
                  <td className='p-3 whitespace-nowrap'>{row.created_at ? new Date(row.created_at).toLocaleString() : '—'}</td>
                  <td className='p-3'>
                    <div className='font-medium'>{row.contact_name}</div>
                    <div className='text-muted-foreground'>{row.email}</div>
                    {row.message && <div className='mt-1 max-w-xs text-xs text-muted-foreground line-clamp-3'>{row.message}</div>}
                  </td>
                  <td className='p-3'>
                    <div>{row.company_name}</div>
                    <a className='text-xs text-primary underline' href={row.website} target='_blank' rel='noreferrer'>
                      {row.website}
                    </a>
                  </td>
                  <td className='p-3 whitespace-nowrap'>{row.whatsapp_e164}</td>
                  <td className='p-3'>{row.preferred_language}</td>
                  <td className='p-3'>
                    <Badge variant='secondary'>{row.source}</Badge>
                  </td>
                  <td className='p-3'>
                    <Badge>{row.status}</Badge>
                  </td>
                  <td className='p-3'>
                    <div className='flex flex-col gap-1'>
                      {row.status === 'pending' && (
                        <>
                          <Button size='sm' disabled={busy} onClick={() => openApprove(row)}>
                            Approve / send
                          </Button>
                          <Button size='sm' variant='outline' disabled={busy} onClick={() => reject(row.id)}>
                            Reject
                          </Button>
                        </>
                      )}
                      {['approved', 'active'].includes(row.status) && !row.demo_completed_at && (
                        <Button size='sm' variant='outline' disabled={busy} onClick={() => resend(row.id)}>
                          Resend
                        </Button>
                      )}
                      {row.frontpage_lead_call_id && (
                        <a className='text-xs text-primary underline' href={`/marketing/lead-sources`}>
                          View lead
                        </a>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {manualOpen && (
        <div className='fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4'>
          <div className='w-full max-w-lg rounded-lg border bg-background p-4 shadow-lg'>
            <h2 className='text-lg font-semibold mb-3'>New demo invite</h2>
            <div className='grid gap-2'>
              {['contact_name', 'email', 'company_name', 'whatsapp', 'website'].map((k) => (
                <Input
                  key={k}
                  placeholder={k.replace(/_/g, ' ')}
                  value={manual[k]}
                  onChange={(e) => setManual((m) => ({ ...m, [k]: e.target.value }))}
                />
              ))}
              <select
                className='h-9 rounded-md border px-2'
                value={manual.preferred_language}
                onChange={(e) => setManual((m) => ({ ...m, preferred_language: e.target.value }))}
              >
                {LANGS.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.label}
                  </option>
                ))}
              </select>
              <Textarea
                placeholder='Optional message / notes'
                value={manual.message}
                onChange={(e) => setManual((m) => ({ ...m, message: e.target.value }))}
              />
            </div>
            <div className='mt-4 flex justify-end gap-2'>
              <Button variant='ghost' onClick={() => setManualOpen(false)}>
                Cancel
              </Button>
              <Button disabled={busy} onClick={sendManual}>
                Send invite
              </Button>
            </div>
          </div>
        </div>
      )}

      {compose && (
        <div className='fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4'>
          <div className='w-full max-w-2xl rounded-lg border bg-background p-4 shadow-lg max-h-[90vh] overflow-y-auto'>
            <h2 className='text-lg font-semibold mb-3'>Approve & send demo invite</h2>
            <p className='text-sm text-muted-foreground mb-2'>Edit the email or send as-is. WhatsApp will notify them to check email/spam.</p>
            <Input
              className='mb-2'
              value={compose.subject_override}
              onChange={(e) => setCompose((c) => ({ ...c, subject_override: e.target.value }))}
              placeholder='Subject'
            />
            <Textarea
              className='min-h-[240px] font-mono text-xs'
              value={compose.body_override}
              onChange={(e) => setCompose((c) => ({ ...c, body_override: e.target.value }))}
            />
            <label className='mt-2 flex items-center gap-2 text-sm'>
              <input
                type='checkbox'
                checked={Boolean(compose.skip_wa)}
                onChange={(e) => setCompose((c) => ({ ...c, skip_wa: e.target.checked }))}
              />
              Skip WhatsApp notice
            </label>
            <div className='mt-4 flex justify-end gap-2'>
              <Button variant='ghost' onClick={() => setCompose(null)}>
                Cancel
              </Button>
              <Button
                variant='outline'
                disabled={busy}
                onClick={async () => {
                  setBusy(true)
                  try {
                    await apiFetch(`/admin/ai-demo/requests/${compose.id}/approve`, {
                      method: 'POST',
                      body: JSON.stringify({ skip_wa: Boolean(compose.skip_wa) }),
                    })
                    setCompose(null)
                    await refresh()
                  } catch (e) {
                    alert(e?.message || 'Send failed')
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                Send directly
              </Button>
              <Button disabled={busy} onClick={sendApprove}>
                Send edited email
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
