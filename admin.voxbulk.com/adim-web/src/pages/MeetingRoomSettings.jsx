import React, { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Label } from '@/components/ui/Label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select'

export default function MeetingRoomSettings() {
  const [agents, setAgents] = useState([])
  const [languages, setLanguages] = useState([])
  const [agentId, setAgentId] = useState('')
  const [languageCode, setLanguageCode] = useState('en')
  const [msg, setMsg] = useState('')
  const [msgError, setMsgError] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const interviewAgents = useMemo(
    () => agents.filter((a) => a.is_active && a.supports_interview),
    [agents],
  )

  const flash = (text, isError = false) => {
    setMsg(text)
    setMsgError(isError)
  }

  const load = async () => {
    setLoading(true)
    try {
      const agentRows = await apiFetch('/admin/agents')
      setAgents(agentRows?.agents || [])
      const langRes = await apiFetch('/admin/meeting-room/language-options')
      setLanguages(langRes?.languages || [])
      const settings = await apiFetch('/admin/meeting-room/settings')
      setAgentId(String(settings?.agent_id || ''))
      setLanguageCode(String(settings?.language_code || 'en'))
    } catch (e) {
      flash(e?.message || 'Failed to load meeting room settings', true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const save = async () => {
    setBusy(true)
    try {
      const saved = await apiFetch('/admin/meeting-room/settings', {
        method: 'PUT',
        body: JSON.stringify({
          agent_id: agentId || null,
          language_code: languageCode,
        }),
      })
      setAgentId(String(saved?.agent_id || ''))
      setLanguageCode(String(saved?.language_code || 'en'))
      flash('Meeting room settings saved.')
    } catch (e) {
      flash(e?.message || 'Could not save meeting room settings', true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='ds-scope space-y-4'>
      <div className='pageTop'>
        <div>
          <h1>Meeting room</h1>
          <p>Default AI agent and language for browser interview meetings.</p>
        </div>
      </div>

      {msg ? (
        <div
          className={
            msgError
              ? 'rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive'
              : 'rounded-md border border-border bg-secondary/40 px-3 py-2 text-sm text-foreground'
          }
        >
          {msg}
        </div>
      ) : null}

      {loading ? (
        <p className='text-sm text-muted-foreground'>Loading…</p>
      ) : (
        <Panel title='Defaults' subtitle='Agent and language applied to new meeting rooms.' className='max-w-xl'>
          <div className='grid gap-3'>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Agent</Label>
              <Select value={agentId || '__none__'} onValueChange={(v) => setAgentId(v === '__none__' ? '' : v)}>
                <SelectTrigger className='h-8 text-[12px]'>
                  <SelectValue placeholder='— Select interview agent —' />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='__none__'>— Select interview agent —</SelectItem>
                  {interviewAgents.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {a.name || a.slug || a.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='space-y-1'>
              <Label className='text-[12px]'>Language</Label>
              <Select value={languageCode} onValueChange={setLanguageCode}>
                <SelectTrigger className='h-8 text-[12px]'>
                  <SelectValue placeholder='Language' />
                </SelectTrigger>
                <SelectContent>
                  {languages.map((row) => (
                    <SelectItem key={row.code} value={row.code}>
                      {row.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='pt-1'>
              <Button type='button' size='sm' className='h-8' disabled={busy} onClick={() => void save()}>
                {busy ? 'Saving…' : 'Save settings'}
              </Button>
            </div>
          </div>
        </Panel>
      )}
    </div>
  )
}
