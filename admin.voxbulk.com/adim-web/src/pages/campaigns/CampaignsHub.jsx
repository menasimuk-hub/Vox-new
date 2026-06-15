import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Megaphone } from 'lucide-react'
import { apiFetch } from '../../lib/api'

export default function CampaignsHub() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [orgs, setOrgs] = useState([])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await apiFetch('/admin/organisations?limit=500')
        if (cancelled) return
        setOrgs(Array.isArray(data?.items) ? data.items : [])
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load organisations')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const enabledCount = useMemo(
    () => orgs.filter((o) => Boolean(o?.allowed_services?.campaigns || o?.enabled_services?.campaigns)).length,
    [orgs],
  )

  return (
    <div className="pageStack">
      <div className="pageHead">
        <div>
          <p className="eyebrow">Campaigns</p>
          <h1>Broadcast campaigns hub</h1>
          <p className="muted">Preview module — enable per org under Onboarding → Customer services. Customer API coming soon.</p>
        </div>
      </div>

      {error ? <div className="alert danger">{error}</div> : null}

      <div className="grid3">
        <div className="card">
          <div className="cardBody">
            <p className="muted" style={{ fontSize: 12 }}>Organisations</p>
            <p style={{ fontSize: 28, fontWeight: 700 }}>{loading ? '…' : orgs.length}</p>
          </div>
        </div>
        <div className="card">
          <div className="cardBody">
            <p className="muted" style={{ fontSize: 12 }}>Campaigns enabled</p>
            <p style={{ fontSize: 28, fontWeight: 700 }}>{loading ? '…' : enabledCount}</p>
          </div>
        </div>
        <div className="card">
          <div className="cardBody">
            <p className="muted" style={{ fontSize: 12 }}>Status</p>
            <p style={{ fontSize: 16, fontWeight: 600 }}>UI scaffold v1</p>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="cardHead">
          <h3><Megaphone size={18} style={{ verticalAlign: 'middle', marginRight: 8 }} />Quick links</h3>
        </div>
        <div className="cardBody" style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
          <Link className="btn soft bsm" to="/onboarding/services">Org service toggles</Link>
          <Link className="btn soft bsm" to="/campaigns/templates">Template library (stub)</Link>
          <Link className="btn soft bsm" to="/platform-services/surveys/wa-system-templates">WA system templates</Link>
        </div>
      </div>

      <div className="card">
        <div className="cardHead">
          <h3>Organisations with campaigns access</h3>
        </div>
        <div className="cardBody">
          {loading ? (
            <p className="muted">Loading…</p>
          ) : enabledCount === 0 ? (
            <p className="muted">No organisations have broadcast campaigns enabled yet. Turn on <strong>Campaigns</strong> in onboarding services for a pilot customer.</p>
          ) : (
            <table className="table compact">
              <thead>
                <tr>
                  <th>Organisation</th>
                  <th>Allowed</th>
                  <th>Visible</th>
                </tr>
              </thead>
              <tbody>
                {orgs
                  .filter((o) => Boolean(o?.allowed_services?.campaigns))
                  .slice(0, 50)
                  .map((o) => (
                    <tr key={o.id}>
                      <td>
                        <Link to={`/organisations/${encodeURIComponent(o.id)}`}>{o.name || o.display_name || o.id}</Link>
                      </td>
                      <td>{o?.allowed_services?.campaigns ? 'Yes' : 'No'}</td>
                      <td>{o?.enabled_services?.campaigns ? 'Yes' : 'No'}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
