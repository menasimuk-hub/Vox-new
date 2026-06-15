import React from 'react'
import { Link } from 'react-router-dom'

const MOCK_TEMPLATES = [
  { id: '1', name: 'Spring offer', status: 'approved', updated: '2 days ago' },
  { id: '2', name: 'Refer a friend', status: 'pending', updated: '4 hours ago' },
]

export default function CampaignTemplates() {
  return (
    <div className="pageStack">
      <div className="pageHead">
        <div>
          <p className="eyebrow">Campaigns</p>
          <h1>Template library</h1>
          <p className="muted">Stub table for broadcast templates. Manage live WhatsApp survey templates via existing admin tools until the campaigns API ships.</p>
        </div>
        <Link className="btn soft bsm" to="/campaigns">Back to hub</Link>
      </div>

      <div className="card">
        <div className="cardBody">
          <table className="table compact">
            <thead>
              <tr>
                <th>Template</th>
                <th>Status</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {MOCK_TEMPLATES.map((row) => (
                <tr key={row.id}>
                  <td>{row.name}</td>
                  <td><span className="leadPill leadPillNeutral">{row.status}</span></td>
                  <td className="muted">{row.updated}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted" style={{ marginTop: 16, fontSize: 13 }}>
            Need production templates today? Use{' '}
            <Link to="/platform-services/surveys/wa-system-templates">WA system templates</Link>{' '}
            or organisation survey custom templates.
          </p>
        </div>
      </div>
    </div>
  )
}
