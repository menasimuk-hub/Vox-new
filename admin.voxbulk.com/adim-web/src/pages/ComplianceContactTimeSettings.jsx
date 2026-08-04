import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import '../styles/contact-time-settings.css'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const DEFAULT_TIMEZONES = [
  'UTC',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Madrid',
  'Europe/Paris',
  'Europe/Rome',
  'Europe/Dublin',
  'America/New_York',
  'America/Chicago',
  'America/Los_Angeles',
  'America/Toronto',
  'America/Sao_Paulo',
  'Asia/Kolkata',
  'Asia/Dubai',
  'Asia/Singapore',
  'Africa/Johannesburg',
  'Australia/Sydney',
]

const selectClass =
  'flex h-8 w-full rounded-md border border-input bg-transparent px-3 py-1 text-[12px] shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring'

function timeToPct(t) {
  const [h, m] = String(t || '00:00').split(':').map(Number)
  return ((h * 60 + m) / 1440) * 100
}

function DayChips({ days, type, onToggle }) {
  return (
    <div className="days-row">
      {DAYS.map((d) => {
        const on = days.includes(d)
        return (
          <button
            key={d}
            type="button"
            className={`day-chip ${on ? `on ${type}` : ''}`}
            onClick={() => onToggle(d)}
          >
            {d[0]}
            {d[1]}
          </button>
        )
      })}
    </div>
  )
}

function DialPreview({ callStart, callEnd, waStart, waEnd }) {
  const cs = timeToPct(callStart)
  const ce = timeToPct(callEnd)
  const ws = timeToPct(waStart)
  const we = timeToPct(waEnd)
  return (
    <div className="dial-card">
      <div className="dial-label">24-hour window · recipient local time</div>
      <div className="dial-row">
        <span className="dial-name">
          <span className="dial-swatch" style={{ background: 'var(--accent)' }} /> Calling
        </span>
        <div className="dial-track">
          <div
            className="dial-fill"
            style={{ left: `${cs}%`, width: `${Math.max(ce - cs, 1)}%`, background: 'var(--accent)' }}
          />
        </div>
      </div>
      <div className="dial-row">
        <span className="dial-name">
          <span className="dial-swatch" style={{ background: 'var(--slate)' }} /> WA survey
        </span>
        <div className="dial-track">
          <div
            className="dial-fill"
            style={{ left: `${ws}%`, width: `${Math.max(we - ws, 1)}%`, background: 'var(--slate)' }}
          />
        </div>
      </div>
      <div className="dial-ticks">
        <span>00:00</span>
        <span>06:00</span>
        <span>12:00</span>
        <span>18:00</span>
        <span>24:00</span>
      </div>
    </div>
  )
}

export default function ComplianceContactTimeSettings() {
  const [loading, setLoading] = useState(true)
  const [busyCall, setBusyCall] = useState(false)
  const [busyWa, setBusyWa] = useState(false)
  const [savedCall, setSavedCall] = useState(false)
  const [savedWa, setSavedWa] = useState(false)
  const [timezones, setTimezones] = useState(DEFAULT_TIMEZONES)

  const [callDays, setCallDays] = useState(['Mon', 'Tue', 'Wed', 'Thu', 'Fri'])
  const [callStart, setCallStart] = useState('08:00')
  const [callEnd, setCallEnd] = useState('21:00')
  const [callTz, setCallTz] = useState('Europe/London')

  const [waDays, setWaDays] = useState(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'])
  const [waStart, setWaStart] = useState('09:00')
  const [waEnd, setWaEnd] = useState('20:00')
  const [waTz, setWaTz] = useState('Europe/London')

  const applyPayload = useCallback((data) => {
    const calling = data?.calling || {}
    const wa = data?.wa_survey || {}
    setCallDays(calling.days || ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'])
    setCallStart(calling.start || '08:00')
    setCallEnd(calling.end || '21:00')
    setCallTz(calling.fallback_tz || 'Europe/London')
    setWaDays(wa.days || ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'])
    setWaStart(wa.start || '09:00')
    setWaEnd(wa.end || '20:00')
    setWaTz(wa.fallback_tz || 'Europe/London')
    if (Array.isArray(data?.timezones) && data.timezones.length) {
      setTimezones(data.timezones)
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiFetch('/admin/compliance/contact-time')
      applyPayload(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [applyPayload])

  useEffect(() => {
    void load()
  }, [load])

  const flashSaved = (setter) => {
    setter(true)
    setTimeout(() => setter(false), 1600)
  }

  const saveCalling = async () => {
    setBusyCall(true)
    try {
      const data = await apiFetch('/admin/compliance/contact-time/calling', {
        method: 'PUT',
        body: JSON.stringify({
          days: callDays,
          start: callStart,
          end: callEnd,
          fallback_tz: callTz,
        }),
      })
      applyPayload(data)
      flashSaved(setSavedCall)
    } catch (e) {
      alert(e?.message || 'Failed to save calling hours')
    } finally {
      setBusyCall(false)
    }
  }

  const saveWa = async () => {
    setBusyWa(true)
    try {
      const data = await apiFetch('/admin/compliance/contact-time/whatsapp', {
        method: 'PUT',
        body: JSON.stringify({
          days: waDays,
          start: waStart,
          end: waEnd,
          fallback_tz: waTz,
        }),
      })
      applyPayload(data)
      flashSaved(setSavedWa)
    } catch (e) {
      alert(e?.message || 'Failed to save survey hours')
    } finally {
      setBusyWa(false)
    }
  }

  const toggleCallDay = (day) => {
    setCallDays((prev) => (prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]))
  }

  const toggleWaDay = (day) => {
    setWaDays((prev) => (prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]))
  }

  if (loading) {
    return (
      <div className="ds-scope contact-time-page">
        <div className="wrap">
          <p className="text-sm text-muted-foreground">Loading contact time settings…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="ds-scope contact-time-page space-y-4">
      <div className="wrap space-y-4">
        <div>
          <p className="eyebrow">Outreach ops · internal</p>
          <h1>Contact time settings</h1>
          <p className="sub">
            Set one calling window and one WhatsApp survey window. The system applies both in each recipient&apos;s local
            time — detected automatically from their mobile number&apos;s country code, no manual country setup needed.
          </p>
        </div>

        <div className="locale-strip">
          <span className="dot-live" />
          Local time is resolved from the recipient&apos;s <b>mobile number prefix</b> (e.g. +44 → UK time, +971 → UAE
          time) at the moment a call or survey is queued.
        </div>

        <DialPreview callStart={callStart} callEnd={callEnd} waStart={waStart} waEnd={waEnd} />

        <div className="grid gap-4 md:grid-cols-2">
          <Panel
            title={
              <span className="inline-flex items-center gap-2">
                <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: 'var(--accent)' }} />
                Calling hours
              </span>
            }
            subtitle="Outbound calls only go out inside this window, in the recipient's own local time."
            bodyClassName="space-y-3"
          >
            <div>
              <Label className="mb-1.5 text-[11px] text-muted-foreground">Active days</Label>
              <DayChips days={callDays} type="call" onToggle={toggleCallDay} />
            </div>
            <div>
              <Label className="mb-1.5 text-[11px] text-muted-foreground">Window (recipient local time)</Label>
              <div className="flex items-center gap-2">
                <Input className="h-8" type="time" value={callStart} onChange={(e) => setCallStart(e.target.value)} />
                <span className="text-xs text-muted-foreground">to</span>
                <Input className="h-8" type="time" value={callEnd} onChange={(e) => setCallEnd(e.target.value)} />
              </div>
            </div>
            <div>
              <Label className="mb-1.5 text-[11px] text-muted-foreground">Fallback time zone</Label>
              <select className={selectClass} value={callTz} onChange={(e) => setCallTz(e.target.value)}>
                {timezones.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </div>
            <p className="m-0 text-[11px] text-muted-foreground">
              Used only if a number&apos;s country can&apos;t be detected (landline ports, unrecognized prefixes, VOIP
              ranges).
            </p>
            <div className="flex items-center gap-2 pt-1">
              <Button type="button" size="sm" className="h-8" disabled={busyCall} onClick={() => void saveCalling()}>
                {busyCall ? 'Saving…' : 'Save calling hours'}
              </Button>
              {savedCall ? <span className="text-xs text-success">Saved</span> : null}
            </div>
          </Panel>

          <Panel
            title={
              <span className="inline-flex items-center gap-2">
                <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: 'var(--slate)' }} />
                WhatsApp survey hours
              </span>
            }
            subtitle="First WA Survey template send only — in the recipient's local time. Customer Feedback and active sessions are not restricted."
            bodyClassName="space-y-3"
          >
            <div>
              <Label className="mb-1.5 text-[11px] text-muted-foreground">Active days</Label>
              <DayChips days={waDays} type="wa" onToggle={toggleWaDay} />
            </div>
            <div>
              <Label className="mb-1.5 text-[11px] text-muted-foreground">Window (recipient local time)</Label>
              <div className="flex items-center gap-2">
                <Input className="h-8" type="time" value={waStart} onChange={(e) => setWaStart(e.target.value)} />
                <span className="text-xs text-muted-foreground">to</span>
                <Input className="h-8" type="time" value={waEnd} onChange={(e) => setWaEnd(e.target.value)} />
              </div>
            </div>
            <div>
              <Label className="mb-1.5 text-[11px] text-muted-foreground">Fallback time zone</Label>
              <select className={selectClass} value={waTz} onChange={(e) => setWaTz(e.target.value)}>
                {timezones.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </div>
            <p className="m-0 text-[11px] text-muted-foreground">
              Keep at least a 1 hour buffer after calling hours close so replies land during working hours.
            </p>
            <div className="flex items-center gap-2 pt-1">
              <Button type="button" size="sm" className="h-8" disabled={busyWa} onClick={() => void saveWa()}>
                {busyWa ? 'Saving…' : 'Save survey hours'}
              </Button>
              {savedWa ? <span className="text-xs text-success">Saved</span> : null}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  )
}
