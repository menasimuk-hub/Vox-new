import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'

export default function WaAppointmentTemplates() {
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [templates, setTemplates] = useState([])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch('/admin/wa-appointment/templates')
      setTemplates(Array.isArray(data?.templates) ? data.templates : [])
    } catch (e) {
      setError(e?.message || 'Could not load appointment templates')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const toggleHidden = async (tpl) => {
    setWorking(`hide-${tpl.id}`)
    try {
      await apiFetch(`/admin/wa-appointment/templates/${tpl.id}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ active_for_appointment: tpl.active_for_appointment === false }),
      })
      setMsg('Template visibility updated')
      await load()
    } catch (e) {
      setError(e?.message || 'Could not update visibility')
    } finally {
      setWorking('')
    }
  }

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>WA Appointment templates</h1>
          <p>Four UTILITY templates for Appointment Manager confirmations and reminders.</p>
        </div>
        <div className="pageTopActions">
          <Link className="btn soft" to="/operations/running-appointments">Running appointments</Link>
          <button type="button" className="btn primary" onClick={() => load().catch((e) => setError(e?.message))}>
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className="card runningSurveyError"><div className="cardBody" style={{ color: '#b91c1c' }}>{error}</div></div> : null}
      {msg ? <div className="card"><div className="cardBody">{msg}</div></div> : null}

      <div className="card">
        <div className="cardHead"><h3>Template pack (4)</h3></div>
        <div className="cardBody" style={{ padding: 0 }}>
          {loading ? <div className="note" style={{ padding: 16 }}>Loading…</div> : null}
          {!loading && !templates.length ? <div className="note" style={{ padding: 16 }}>No templates seeded yet — deploy API migration 0130 and refresh.</div> : null}
          <table className="table compact">
            <thead>
              <tr>
                <th>Label</th>
                <th>Telnyx name</th>
                <th>Status</th>
                <th>Customer visible</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {templates.map((tpl) => (
                <tr key={tpl.id}>
                  <td>
                    <strong>{tpl.display_name || tpl.label}</strong>
                    <div className="muted" style={{ fontSize: 12 }}>{tpl.description || tpl.body}</div>
                  </td>
                  <td><code>{tpl.name}</code></td>
                  <td>{tpl.status || tpl.approval_status || '—'}</td>
                  <td>{tpl.active_for_appointment === false ? 'Hidden' : 'Visible'}</td>
                  <td>
                    <button
                      type="button"
                      className="btn soft"
                      disabled={Boolean(working)}
                      onClick={() => toggleHidden(tpl)}
                    >
                      {tpl.active_for_appointment === false ? 'Show' : 'Hide'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
