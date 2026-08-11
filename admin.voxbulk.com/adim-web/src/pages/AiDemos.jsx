import React, { useCallback, useEffect, useMemo, useState } from 'react'
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
  website: 'https://voxbulk.com',
  preferred_language: 'en',
  voice_region: '',
  message: '',
}

function fmt(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString()
}

export default function AiDemos() {
  const [tab, setTab] = useState('inbox')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [manual, setManual] = useState(emptyManual)
  const [batchText, setBatchText] = useState('')
  const [batchLang, setBatchLang] = useState('en')
  const [batchRegion, setBatchRegion] = useState('')
  const [batchMsg, setBatchMsg] = useState('You are invited to a live VoxBulk AI demo.')
  const [compose, setCompose] = useState(null)
  const [detail, setDetail] = useState(null)
  const [settings, setSettings] = useState({
    provider_agent_id: '',
    from_email: '',
    soft_cap_minutes: 7,
    agent_by_region: {},
    regions: [],
  })
  const [agents, setAgents] = useState([])
  const [busy, setBusy] = useState(false)
  const [batchResult, setBatchResult] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const q = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : ''
      const [list, st, preview, agentList] = await Promise.all([
        apiFetch(`/admin/ai-demo/requests${q}`),
        apiFetch('/admin/ai-demo/settings'),
        apiFetch('/admin/ai-demo/invite-preview').catch(() => null),
        apiFetch('/admin/ai-demo/agents').catch(() => ({ items: [] })),
      ])
      setItems(list.items || [])
      setAgents(Array.isArray(agentList?.items) ? agentList.items : [])
      setSettings({
        provider_agent_id: st.provider_agent_id || '',
        from_email: st.from_email || '',
        soft_cap_minutes: st.soft_cap_minutes || 7,
        notes: st.notes || '',
        agent_by_region: st.agent_by_region && typeof st.agent_by_region === 'object' ? st.agent_by_region : {},
        regions: Array.isArray(st.regions) ? st.regions : [],
        _previewSubject: preview?.subject || '',
        _previewBody: preview?.body || '',
      })
    } catch (e) {
      setError(e?.message || 'Failed to load AI demos')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    refresh()
  }, [refresh])

  const stats = useMemo(() => {
    const total = items.length
    const opened = items.filter((r) => r.opened_at).length
    const clicked = items.filter((r) => r.link_clicked_at).length
    const completed = items.filter((r) => r.demo_completed_at).length
    return { total, opened, clicked, completed }
  }, [items])

  const openApprove = (row) => {
    setCompose({
      id: row.id,
      subject_override: settings._previewSubject || '',
      body_override: settings._previewBody || '',
      skip_wa: !row.whatsapp_e164,
      voice_region: row.voice_region || '',
    })
  }

  const openDetail = async (id) => {
    setBusy(true)
    try {
      const data = await apiFetch(`/admin/ai-demo/requests/${id}`)
      setDetail(data)
    } catch (e) {
      alert(e?.message || 'Failed to load detail')
    } finally {
      setBusy(false)
    }
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
          voice_region: compose.voice_region || null,
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
        body: JSON.stringify({
          ...manual,
          whatsapp: manual.whatsapp || null,
          skip_wa: !manual.whatsapp,
          voice_region: manual.voice_region || null,
        }),
      })
      setManual(emptyManual)
      setTab('inbox')
      await refresh()
    } catch (e) {
      alert(e?.message || 'Send failed')
    } finally {
      setBusy(false)
    }
  }

  const sendBatch = async () => {
    setBusy(true)
    setBatchResult(null)
    try {
      const data = await apiFetch('/admin/ai-demo/requests/batch', {
        method: 'POST',
        body: JSON.stringify({
          emails_text: batchText,
          preferred_language: batchLang,
          message: batchMsg,
          skip_wa: true,
          voice_region: batchRegion || null,
        }),
      })
      setBatchResult(data)
      setBatchText('')
      await refresh()
    } catch (e) {
      alert(e?.message || 'Batch send failed')
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
          from_email: settings.from_email,
          soft_cap_minutes: Number(settings.soft_cap_minutes) || 7,
          notes: settings.notes || '',
          agent_by_region: settings.agent_by_region || {},
        }),
      })
      await refresh()
    } catch (e) {
      alert(e?.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const duplicateDemoAgents = async () => {
    if (
      !window.confirm(
        'Create dedicated AI Demo Telnyx agents (copies) for each mapped region and remap Settings? Interview agents stay untouched.',
      )
    ) {
      return
    }
    setBusy(true)
    try {
      const data = await apiFetch('/admin/ai-demo/agents/duplicate-for-demo', { method: 'POST' })
      alert(`Done. Created/updated ${data?.results?.length || 0} mapping(s). Refreshing…`)
      await refresh()
    } catch (e) {
      alert(e?.message || 'Duplicate failed')
    } finally {
      setBusy(false)
    }
  }

  const syncDemoTelnyxTools = async () => {
    setBusy(true)
    try {
      const data = await apiFetch('/admin/ai-demo/agents/sync-telnyx-tools', { method: 'POST' })
      alert(`Telnyx tools synced on ${data?.synced || 0}/${data?.total || 0} AI Demo agents`)
    } catch (e) {
      alert(e?.message || 'Tool sync failed')
    } finally {
      setBusy(false)
    }
  }

  const ensureVoxbulkDemoOrg = async () => {
    if (
      !window.confirm(
        'Create or refresh the shared “Voxbulk Demo” organisation (logo, address, seed Feedback/Surveys/Interviews) used by the real-dashboard AI demo?',
      )
    ) {
      return
    }
    setBusy(true)
    try {
      const data = await apiFetch('/admin/ai-demo/ensure-demo-org', { method: 'POST' })
      const locs = data?.feedback_locations?.length ?? 0
      alert(
        `Voxbulk Demo ready.\norg=${data?.org_id}\nowner=${data?.owner_email}\nseed_skipped=${Boolean(data?.seed?.skipped)}\nfeedback_locations=${locs}`,
      )
    } catch (e) {
      alert(e?.message || 'Ensure demo org failed')
    } finally {
      setBusy(false)
    }
  }

  const upsertKbDefaults = async () => {
    if (!window.confirm('Refresh all AI Demo knowledge bases with the latest talk/sales prompts from code?')) return
    setBusy(true)
    try {
      const data = await apiFetch('/admin/ai-demo/knowledge-bases/upsert-defaults', { method: 'POST' })
      alert(`KB upserted: created ${data?.created || 0}, updated ${data?.updated || 0}`)
    } catch (e) {
      alert(e?.message || 'KB upsert failed')
    } finally {
      setBusy(false)
    }
  }

  const setRegionAgent = (code, agentId) => {
    setSettings((s) => {
      const next = { ...(s.agent_by_region || {}) }
      if (!agentId) delete next[code]
      else next[code] = agentId
      return { ...s, agent_by_region: next }
    })
  }

  const agentsForRegion = (code) => {
    if (!agents.length) return []
    if (code === 'DEFAULT') return agents
    const preferred = agents.filter((a) => String(a.accent_region || '').toUpperCase() === code)
    const rest = agents.filter((a) => String(a.accent_region || '').toUpperCase() !== code)
    return [...preferred, ...rest]
  }

  const voiceRegionOptions = useMemo(() => {
    const regions = Array.isArray(settings.regions) ? settings.regions : []
    const map = settings.agent_by_region || {}
    return regions
      .filter((r) => r.code !== 'DEFAULT')
      .map((r) => {
        const agentId = map[r.code]
        const agent = agents.find((a) => a.id === agentId)
        const configured = Boolean(agentId && agent)
        return {
          code: r.code,
          label: configured ? `${r.label} — ${agent.name}` : `${r.label} (not mapped in Settings)`,
          configured,
        }
      })
  }, [settings.regions, settings.agent_by_region, agents])

  const VoiceRegionSelect = ({ value, onChange, id }) => (
    <label className='text-sm block'>
      Voice agent market
      <select
        id={id}
        className='mt-1 h-9 w-full rounded-md border px-2'
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value=''>Auto from WhatsApp country</option>
        {voiceRegionOptions.map((r) => (
          <option key={r.code} value={r.code} disabled={!r.configured}>
            {r.label}
          </option>
        ))}
      </select>
      <span className='mt-1 block text-xs text-muted-foreground'>
        Choose GB / AU / Arabic (SA) etc. Uses the agent you mapped in Settings.
      </span>
    </label>
  )

  return (
    <div className='space-y-4 p-4 md:p-6'>
      <div className='flex flex-wrap items-center justify-between gap-3'>
        <div>
          <h1 className='text-xl font-semibold'>AI Demos</h1>
          <p className='text-sm text-muted-foreground'>
            Approve website requests, send single or multi-email invites, and track opens, clicks, sessions, and transcripts.
          </p>
        </div>
        <div className='flex gap-2'>
          <Button variant='outline' onClick={() => refresh()} disabled={loading || busy}>
            Refresh
          </Button>
          <Button onClick={() => setTab('send')}>Send invites</Button>
        </div>
      </div>

      {error && <div className='rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm'>{error}</div>}

      <div className='grid gap-3 sm:grid-cols-4'>
        {[
          ['Total', stats.total],
          ['Opened', stats.opened],
          ['Clicked', stats.clicked],
          ['Completed', stats.completed],
        ].map(([label, value]) => (
          <Card key={label}>
            <CardContent className='p-4'>
              <div className='text-xs text-muted-foreground uppercase tracking-wide'>{label}</div>
              <div className='text-2xl font-semibold mt-1'>{value}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className='flex flex-wrap gap-2'>
        {[
          ['inbox', 'Inbox'],
          ['send', 'Send'],
          ['settings', 'Settings'],
        ].map(([id, label]) => (
          <Button key={id} size='sm' variant={tab === id ? 'default' : 'outline'} onClick={() => setTab(id)}>
            {label}
          </Button>
        ))}
      </div>

      {tab === 'settings' && (
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>Voice agents by market</CardTitle>
          </CardHeader>
          <CardContent className='grid gap-4'>
            <p className='text-sm text-muted-foreground'>
              Pick which Admin → Agents voice talks for each market. Visitors are matched from their WhatsApp country
              code (+44 → GB, +61 → AU, +1 → US, +353 → IE, +966 → SA, +20 → EG). Unmapped markets use Default, then
              Talk-to-us.
            </p>
            {!agents.length ? (
              <p className='text-sm text-amber-700'>
                No agents with a Telnyx assistant ID found. Create/activate agents under Admin → Agents first.
              </p>
            ) : null}
            <div className='grid gap-3 md:grid-cols-2'>
              {(settings.regions || []).map((r) => (
                <label key={r.code} className='text-sm'>
                  {r.label}
                  <select
                    className='mt-1 h-9 w-full rounded-md border px-2'
                    value={settings.agent_by_region?.[r.code] || ''}
                    onChange={(e) => setRegionAgent(r.code, e.target.value)}
                  >
                    <option value=''>— Not set —</option>
                    {agentsForRegion(r.code).map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.label}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
            <div className='grid gap-3 md:grid-cols-2 border-t pt-4'>
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
            </div>
            <div className='flex flex-wrap gap-2'>
              <Button onClick={saveSettings} disabled={busy}>
                Save settings
              </Button>
              <Button variant='outline' onClick={duplicateDemoAgents} disabled={busy}>
                Duplicate → AI Demo agents only
              </Button>
              <Button variant='outline' onClick={syncDemoTelnyxTools} disabled={busy}>
                Sync Telnyx demo tools
              </Button>
              <Button variant='outline' onClick={ensureVoxbulkDemoOrg} disabled={busy}>
                Ensure Voxbulk Demo org
              </Button>
              <Button variant='outline' onClick={upsertKbDefaults} disabled={busy}>
                Refresh KB talk/sales copy
              </Button>
            </div>
            <p className='text-xs text-muted-foreground'>
              Duplicate creates new Telnyx assistants named “AI Demo — …”. Sync Telnyx demo tools attaches webhook tools
              (highlight_dashboard, show_qr_code, show_pricing, …) to those assistants only — interview agents stay
              untouched. Ensure Voxbulk Demo org creates the shared real-dashboard workspace (logo, address, seed data)
              that magic-link Start opens.
            </p>
          </CardContent>
        </Card>
      )}

      {tab === 'send' && (
        <div className='grid gap-4 lg:grid-cols-2'>
          <Card>
            <CardHeader>
              <CardTitle className='text-base'>Single invite</CardTitle>
            </CardHeader>
            <CardContent className='grid gap-2'>
              {['contact_name', 'email', 'company_name', 'whatsapp', 'website'].map((k) => (
                <Input
                  key={k}
                  placeholder={k.replace(/_/g, ' ') + (k === 'whatsapp' ? ' (optional)' : '')}
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
              <VoiceRegionSelect
                id='manual-voice-region'
                value={manual.voice_region}
                onChange={(v) => setManual((m) => ({ ...m, voice_region: v }))}
              />
              <Textarea
                placeholder='Optional message / notes'
                value={manual.message}
                onChange={(e) => setManual((m) => ({ ...m, message: e.target.value }))}
              />
              <Button disabled={busy || !manual.email} onClick={sendManual}>
                Send invite
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className='text-base'>Multi-email batch (max 50)</CardTitle>
            </CardHeader>
            <CardContent className='grid gap-2'>
              <Textarea
                className='min-h-[160px] font-mono text-xs'
                placeholder={'one@company.com\ntwo@company.com\nor comma-separated'}
                value={batchText}
                onChange={(e) => setBatchText(e.target.value)}
              />
              <select className='h-9 rounded-md border px-2' value={batchLang} onChange={(e) => setBatchLang(e.target.value)}>
                {LANGS.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.label}
                  </option>
                ))}
              </select>
              <VoiceRegionSelect id='batch-voice-region' value={batchRegion} onChange={setBatchRegion} />
              <Textarea placeholder='Optional note in invite context' value={batchMsg} onChange={(e) => setBatchMsg(e.target.value)} />
              <Button disabled={busy || !batchText.trim()} onClick={sendBatch}>
                Send batch
              </Button>
              {batchResult && (
                <div className='text-sm rounded-md border p-3'>
                  Sent {batchResult.sent}, failed {batchResult.failed}
                  {batchResult.errors?.length ? (
                    <ul className='mt-2 text-xs text-destructive space-y-1'>
                      {batchResult.errors.map((e) => (
                        <li key={e.email}>
                          {e.email}: {e.error}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {tab === 'inbox' && (
        <>
          <div className='flex flex-wrap gap-2'>
            {['', 'pending', 'approved', 'active', 'completed', 'rejected'].map((s) => (
              <Button key={s || 'all'} size='sm' variant={statusFilter === s ? 'default' : 'outline'} onClick={() => setStatusFilter(s)}>
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
                    <th className='p-3'>Tracking</th>
                    <th className='p-3'>Source</th>
                    <th className='p-3'>Status</th>
                    <th className='p-3'>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loading && (
                    <tr>
                      <td className='p-4 text-muted-foreground' colSpan={6}>
                        Loading…
                      </td>
                    </tr>
                  )}
                  {!loading && items.length === 0 && (
                    <tr>
                      <td className='p-4 text-muted-foreground' colSpan={6}>
                        No demos yet
                      </td>
                    </tr>
                  )}
                  {items.map((row) => (
                    <tr key={row.id} className='border-b align-top'>
                      <td className='p-3 whitespace-nowrap'>{fmt(row.created_at)}</td>
                      <td className='p-3'>
                        <div className='font-medium'>{row.contact_name}</div>
                        <div className='text-muted-foreground'>{row.email}</div>
                        <div className='text-xs text-muted-foreground'>{row.company_name}</div>
                      </td>
                      <td className='p-3'>
                        <div className='flex flex-wrap gap-1'>
                          <Badge variant={row.email_sent_at ? 'active' : 'secondary'}>sent {row.email_sent_at ? '' : '—'}</Badge>
                          <Badge variant={row.opened_at ? 'active' : 'secondary'}>open {row.open_count || 0}</Badge>
                          <Badge variant={row.link_clicked_at ? 'active' : 'secondary'}>click {row.click_count || 0}</Badge>
                          {row.demo_completed_at ? <Badge variant='active'>done</Badge> : null}
                        </div>
                      </td>
                      <td className='p-3'>
                        <Badge variant='secondary'>{row.source}</Badge>
                      </td>
                      <td className='p-3'>
                        <Badge>{row.status}</Badge>
                      </td>
                      <td className='p-3'>
                        <div className='flex flex-col gap-1'>
                          <Button size='sm' variant='outline' disabled={busy} onClick={() => openDetail(row.id)}>
                            Detail
                          </Button>
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
                            <a className='text-xs text-primary underline' href='/marketing/lead-sources'>
                              Lead sources
                            </a>
                          )}
                          {row.lead_sales_task_id && (
                            <a className='text-xs text-primary underline' href={`/marketing/lead-sales/${row.lead_sales_task_id}`}>
                              Lead sales
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
        </>
      )}

      {compose && (
        <div className='fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4'>
          <div className='w-full max-w-2xl rounded-lg border bg-background p-4 shadow-lg max-h-[90vh] overflow-y-auto'>
            <h2 className='text-lg font-semibold mb-3'>Approve & send demo invite</h2>
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
            <div className='mt-3'>
              <VoiceRegionSelect
                id='approve-voice-region'
                value={compose.voice_region}
                onChange={(v) => setCompose((c) => ({ ...c, voice_region: v }))}
              />
            </div>
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
                      body: JSON.stringify({
                        skip_wa: Boolean(compose.skip_wa),
                        voice_region: compose.voice_region || null,
                      }),
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

      {detail && (
        <div className='fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4'>
          <div className='w-full max-w-3xl rounded-lg border bg-background p-4 shadow-lg max-h-[90vh] overflow-y-auto'>
            <div className='flex items-start justify-between gap-3 mb-3'>
              <div>
                <h2 className='text-lg font-semibold'>{detail.contact_name}</h2>
                <p className='text-sm text-muted-foreground'>
                  {detail.email} · {detail.company_name}
                </p>
              </div>
              <Button variant='ghost' onClick={() => setDetail(null)}>
                Close
              </Button>
            </div>

            <div className='grid gap-2 sm:grid-cols-2 text-sm mb-4'>
              <div>Sent: {fmt(detail.email_sent_at)}</div>
              <div>
                Opened: {fmt(detail.opened_at)} ({detail.open_count || 0})
              </div>
              <div>
                Clicked: {fmt(detail.link_clicked_at)} ({detail.click_count || 0})
              </div>
              <div>Completed: {fmt(detail.demo_completed_at)}</div>
              <div>WhatsApp: {detail.whatsapp_e164 || '—'}</div>
              <div>Lang: {detail.preferred_language}</div>
            </div>

            {detail.lead && (
              <Card className='mb-4'>
                <CardHeader>
                  <CardTitle className='text-base'>Lead outcome</CardTitle>
                </CardHeader>
                <CardContent className='text-sm space-y-2'>
                  <div>
                    Recommendation: <strong>{detail.lead.recommendation || '—'}</strong> · Sentiment:{' '}
                    {detail.lead.sentiment || '—'}
                  </div>
                  <div>Interest: {detail.lead.interest_summary || '—'}</div>
                  <div>Services: {(detail.lead.services_explored || []).join(', ') || '—'}</div>
                  <div>Volumes: {detail.lead.volume_needs ? JSON.stringify(detail.lead.volume_needs) : '—'}</div>
                  {detail.lead.transcript_text && (
                    <pre className='mt-2 max-h-48 overflow-auto rounded border bg-muted/30 p-2 text-xs whitespace-pre-wrap'>
                      {detail.lead.transcript_text}
                    </pre>
                  )}
                  <div className='flex gap-3 pt-1'>
                    <a className='text-primary underline text-xs' href='/marketing/lead-sources'>
                      Lead sources
                    </a>
                    {detail.lead_sales_task_id && (
                      <a className='text-primary underline text-xs' href={`/marketing/lead-sales/${detail.lead_sales_task_id}`}>
                        Open sales task
                      </a>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader>
                <CardTitle className='text-base'>Sessions</CardTitle>
              </CardHeader>
              <CardContent className='space-y-3 text-sm'>
                {(detail.sessions || []).length === 0 && <div className='text-muted-foreground'>No sessions yet</div>}
                {(detail.sessions || []).map((s) => (
                  <div key={s.id} className='rounded border p-3'>
                    <div className='font-medium'>
                      {s.status} · {s.active_service_code || 'no KB yet'}
                    </div>
                    <div className='text-xs text-muted-foreground'>
                      started {fmt(s.started_at)} · ended {fmt(s.ended_at)} · {s.duration_seconds || 0}s
                    </div>
                    {s.transcript_log && (
                      <pre className='mt-2 max-h-40 overflow-auto text-xs whitespace-pre-wrap'>{s.transcript_log}</pre>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
