import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'

function fmtTime(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return '—'
  }
}

export default function LegalPages() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [rows, setRows] = useState([])

  const load = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const data = await apiFetch('/admin/legal-pages')
      setRows(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e?.message || 'Could not load legal pages')
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Legal pages</h1>
          <p>Edit Terms, Privacy, Cookie, GDPR, and Legal pages. HTML you save here appears on the public voxbulk.com site.</p>
        </div>
      </div>

      <div className='pageShell'>
        {error ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)', marginBottom: 14 }}>{error}</div> : null}

        <div className='card'>
          <div className='cardHead'>
            <h3>Platform legal pages</h3>
            <span className='pill p-cyan'>Public site</span>
          </div>
          <div className='cardBody'>
            {loading ? (
              <div className='note'>Loading…</div>
            ) : rows.length ? (
              <div className='tableWrap'>
                <table className='table'>
                  <thead>
                    <tr>
                      <th>Page</th>
                      <th>Public URL</th>
                      <th>Status</th>
                      <th>Last updated</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.slug}>
                        <td>
                          <strong>{row.title}</strong>
                          <div className='muted' style={{ fontSize: 12 }}>{row.slug}</div>
                        </td>
                        <td>
                          <a href={`https://voxbulk.com${row.public_path}`} target='_blank' rel='noreferrer'>
                            {row.public_path}
                          </a>
                        </td>
                        <td>
                          <span className={`pill ${row.is_published ? 'p-green' : 'p-amber'}`}>
                            {row.is_published ? 'Published' : 'Draft'}
                          </span>
                        </td>
                        <td className='muted'>{fmtTime(row.updated_at)}</td>
                        <td>
                          <button type='button' className='btn soft' onClick={() => navigate(`/settings/legal/${encodeURIComponent(row.slug)}/edit`)}>
                            Edit
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className='note'>No legal pages found.</div>
            )}
          </div>
        </div>

        <div className='note' style={{ marginTop: 16 }}>
          Paste HTML in the editor (headings, paragraphs, lists). Use the live preview before saving. Unpublished pages return 404 on the public site.
        </div>
      </div>
    </>
  )
}
