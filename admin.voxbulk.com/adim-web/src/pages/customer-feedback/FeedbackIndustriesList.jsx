import React, { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiFetch } from '../../lib/api'
import '../../styles/admin-industries.css'

function statusPill(active) {
  return active ? 'badge-active' : 'leadPill leadPillNeutral'
}

export default function FeedbackIndustriesList() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [items, setItems] = useState([])

  const load = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const data = await apiFetch('/admin/customer-feedback/industries')
      setItems(data?.items || [])
    } catch (e) {
      setError(e?.message || 'Could not load industries')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const addIndustry = async () => {
    try {
      const data = await apiFetch('/admin/customer-feedback/industries', {
        method: 'POST',
        body: JSON.stringify({ name: 'New industry', slug: `industry-${Date.now()}`, is_active: true, sort_order: 100 }),
      })
      if (data?.item?.id) navigate(`/customer-feedback/industries/${data.item.id}`)
      else await load()
    } catch (e) {
      setError(e?.message || 'Could not create industry')
    }
  }

  return (
    <div className="pageWrap indHub">
      <div className="pageHead">
        <div>
          <h1>Industries</h1>
          <p>Manage feedback industries, survey types and template approval status.</p>
        </div>
        <div className="pageHeadActions">
          <button type="button" className="btn soft bsm" onClick={async () => {
            try {
              await apiFetch('/admin/customer-feedback/templates/import-md', { method: 'POST', body: JSON.stringify({}) })
              setMsg('Templates imported from MD.')
              await load()
            } catch (e) {
              setError(e?.message || 'Import failed')
            }
          }}>Import English templates</button>
          <button type="button" className="btn primary bsm" onClick={addIndustry}>Add industry</button>
          <Link className="btn soft bsm" to="/customer-feedback/subscriptions">Hub</Link>
        </div>
      </div>

      {error ? <div className="alert error">{error}</div> : null}
      {msg ? <div className="alert ok">{msg}</div> : null}

      <div className="card">
        <div className="tableWrap">
          <table className="table runningSurveyTable">
            <thead>
              <tr>
                <th>Industry</th>
                <th>Slug</th>
                <th>Status</th>
                <th>Survey types</th>
                <th>Templates</th>
                <th>Approved</th>
                <th>Pending</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="muted">Loading…</td></tr>
              ) : items.map((row) => (
                <tr key={row.id}>
                  <td><strong>{row.name}</strong></td>
                  <td><code>{row.slug}</code></td>
                  <td><span className={statusPill(row.is_active)}>{row.is_active ? 'Active' : 'Inactive'}</span></td>
                  <td>{row.survey_type_count ?? '—'}</td>
                  <td className="num-link">{row.template_count ?? '—'}</td>
                  <td>{row.approved_count ?? 0}</td>
                  <td>{row.pending_count ?? 0}</td>
                  <td>
                    <button type="button" className="btn soft bsm" onClick={() => navigate(`/customer-feedback/industries/${row.id}`)}>
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && !items.length ? <tr><td colSpan={8} className="muted">No industries yet.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
