import React, { useCallback, useEffect, useState } from 'react'

import { useNavigate } from 'react-router-dom'

import { bundledLegalRows, fetchLegalPagesList } from '../lib/legalPagesApi'



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

  const [offline, setOffline] = useState(false)

  const [rows, setRows] = useState([])



  const load = useCallback(async () => {

    setError('')

    setLoading(true)

    try {

      const result = await fetchLegalPagesList()

      setRows(result.rows)

      setOffline(Boolean(result.offline))

      if (result.offline) {

        setError(

          'API legal routes are not live yet — showing bundled VoxLegal content. You can still edit each tab; saves go to your browser until the API is deployed.',

        )

      }

    } catch (e) {

      setOffline(true)

      setRows(bundledLegalRows())

      setError(

        `${e?.message || 'Could not load legal pages'}. Showing bundled content — you can edit locally until API deploy: cd voxbulk-api && alembic upgrade head && systemctl restart voxbulk-api`,

      )

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

          <p>Edit each tab on the unified Legal & policies page. HTML you save here appears on voxbulk.com/legal-policies.</p>

        </div>

      </div>



      <div className='pageShell'>

        {error ? (

          <div className='note' style={{ borderColor: offline ? 'rgba(245,166,35,0.45)' : 'rgba(255,0,0,0.35)', marginBottom: 14 }}>

            {error}

          </div>

        ) : null}



        <div className='card'>

          <div className='cardHead'>

            <h3>Platform legal pages</h3>

            <span className={`pill ${offline ? 'p-amber' : 'p-cyan'}`}>{offline ? 'Offline mode' : 'Public site'}</span>

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

                          <a

                            href={`https://voxbulk.com/legal-policies?tab=${encodeURIComponent(row.slug)}`}

                            target='_blank'

                            rel='noreferrer'

                          >

                            /legal-policies?tab={row.slug}

                          </a>

                        </td>

                        <td>

                          <span className={`pill ${row.is_published ? 'p-green' : 'p-amber'}`}>

                            {offline ? 'Bundled / local draft' : row.is_published ? 'Published' : 'Draft'}

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

          {offline ? (

            <>

              <strong>Offline editing:</strong> click Edit, change HTML, press Save — drafts stay in this browser.

              To publish on the live site without the API, update{' '}

              <code>voxbulk.com/frontend/src/data/legalDefaultBodies.json</code> on the server, then rebuild the public frontend.

            </>

          ) : (

            <>Paste HTML in the editor (headings, paragraphs, lists, tables). Each slug maps to a tab on the public Legal & policies page.</>

          )}

        </div>

      </div>

    </>

  )

}


