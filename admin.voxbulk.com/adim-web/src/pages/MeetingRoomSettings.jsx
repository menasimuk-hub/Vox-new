import React, { useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from '../lib/api'

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

  const flash = (text, isError = false) => {
    setMsg(text)
    setMsgError(isError)
  }

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
    <div className="page">
      <div className="page-header">
        <h1>Meeting room</h1>
        <p className="muted">Default AI agent and language for browser interview meetings.</p>
      </div>

      {msg ? (
        <div className="note" style={{ borderColor: msgError ? 'rgba(220,38,38,0.35)' : undefined }}>
          {msg}
        </div>
      ) : null}

      {loading ? (
        <p className="muted">Loading…</p>
      ) : (
        <div className="card" style={{ maxWidth: 560 }}>
          <div className="form-grid">
            <label className="field">
              <span>Agent</span>
              <select className="input" value={agentId} onChange={(e) => setAgentId(e.target.value)}>
                <option value="">— Select interview agent —</option>
                {interviewAgents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name || a.slug || a.id}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Language</span>
              <select
                className="input"
                value={languageCode}
                onChange={(e) => setLanguageCode(e.target.value)}
              >
                {languages.map((row) => (
                  <option key={row.code} value={row.code}>
                    {row.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div style={{ marginTop: 16 }}>
            <button className="btn primary" type="button" disabled={busy} onClick={() => void save()}>
              {busy ? 'Saving…' : 'Save settings'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
