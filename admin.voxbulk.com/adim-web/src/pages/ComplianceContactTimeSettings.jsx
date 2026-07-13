import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'
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
      <div className="contact-time-page">
        <div className="wrap">
          <p className="loading-msg">Loading contact time settings…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="contact-time-page">
      <div className="wrap">
        <p className="eyebrow">Outreach ops · internal</p>
        <h1>Contact time settings</h1>
        <p className="sub">
          Set one calling window and one WhatsApp survey window. The system applies both in each recipient&apos;s local
          time — detected automatically from their mobile number&apos;s country code, no manual country setup needed.
        </p>

        <div className="locale-strip">
          <span className="dot-live" />
          Local time is resolved from the recipient&apos;s <b>mobile number prefix</b> (e.g. +44 → UK time, +971 → UAE
          time) at the moment a call or survey is queued.
        </div>

        <DialPreview callStart={callStart} callEnd={callEnd} waStart={waStart} waEnd={waEnd} />

        <div className="cards">
          <div className="card call">
            <p className="card-title">
              <span className="sw" style={{ background: 'var(--accent)' }} />
              Calling hours
            </p>
            <p className="card-desc">Outbound calls only go out inside this window, in the recipient&apos;s own local time.</p>
            <p className="field-label">Active days</p>
            <DayChips days={callDays} type="call" onToggle={toggleCallDay} />
            <p className="field-label">Window (recipient local time)</p>
            <div className="time-row">
              <input type="time" value={callStart} onChange={(e) => setCallStart(e.target.value)} />
              <span className="time-sep">to</span>
              <input type="time" value={callEnd} onChange={(e) => setCallEnd(e.target.value)} />
            </div>
            <p className="field-label">Fallback time zone</p>
            <select value={callTz} onChange={(e) => setCallTz(e.target.value)}>
              {timezones.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
            <div className="note">
              Used only if a number&apos;s country can&apos;t be detected (landline ports, unrecognized prefixes, VOIP
              ranges).
            </div>
            <div className="save-row">
              <button type="button" className="save-btn call" disabled={busyCall} onClick={() => void saveCalling()}>
                Save calling hours
              </button>
              <span className={`saved-flag ${savedCall ? 'show' : ''}`}>Saved</span>
            </div>
          </div>

          <div className="card wa">
            <p className="card-title">
              <span className="sw" style={{ background: 'var(--slate)' }} />
              WhatsApp survey hours
            </p>
            <p className="card-desc">
              First WA Survey template send only — in the recipient&apos;s local time. Customer Feedback and active
              sessions are not restricted.
            </p>
            <p className="field-label">Active days</p>
            <DayChips days={waDays} type="wa" onToggle={toggleWaDay} />
            <p className="field-label">Window (recipient local time)</p>
            <div className="time-row">
              <input type="time" value={waStart} onChange={(e) => setWaStart(e.target.value)} />
              <span className="time-sep">to</span>
              <input type="time" value={waEnd} onChange={(e) => setWaEnd(e.target.value)} />
            </div>
            <p className="field-label">Fallback time zone</p>
            <select value={waTz} onChange={(e) => setWaTz(e.target.value)}>
              {timezones.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
            <div className="note">Keep at least a 1 hour buffer after calling hours close so replies land during working hours.</div>
            <div className="save-row">
              <button type="button" className="save-btn wa" disabled={busyWa} onClick={() => void saveWa()}>
                Save survey hours
              </button>
              <span className={`saved-flag ${savedWa ? 'show' : ''}`}>Saved</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
