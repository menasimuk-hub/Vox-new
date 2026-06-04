import React, { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { formatWaSurveyError } from '../lib/waSurveyFeedback'

function statusPill(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'published') return 'ok'
  if (s === 'draft') return 'warn'
  return 'muted'
}

export default function WaSurveyFlows() {
  const { typeId } = useParams()
  const [privacyMode, setPrivacyMode] = useState('off')
  const [flows, setFlows] = useState([])
  const [selectedFlowId, setSelectedFlowId] = useState('')
  const [validation, setValidation] = useState(null)
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  const loadFlows = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const qs = `?privacy_mode=${encodeURIComponent(privacyMode)}`
      const data = await apiFetch(
        `/admin/wa-survey/types/${encodeURIComponent(typeId)}/flows${qs}`
      )
      const list = Array.isArray(data?.flows) ? data.flows : []
      setFlows(list)
      setSelectedFlowId((prev) => {
        if (prev && list.some((f) => f.id === prev)) return prev
        const pub = list.find((f) => f.status === 'published' && f.is_default)
        return pub?.id || list[0]?.id || ''
      })
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load flows').message)
    } finally {
      setLoading(false)
    }
  }, [typeId, privacyMode])

  useEffect(() => {
    loadFlows()
  }, [loadFlows])

  const runValidate = async () => {
    if (!selectedFlowId) return
    setWorking('validate')
    setError('')
    setMsg('')
    setValidation(null)
    try {
      const data = await apiFetch(
        `/admin/wa-survey/flows/${encodeURIComponent(selectedFlowId)}/validate`,
        { method: 'POST', body: '{}' }
      )
      setValidation(data)
      if (data.ok) {
        setMsg('Validation passed — safe to publish (warnings may still apply).')
      } else {
        setError('Validation failed — fix errors before publish.')
      }
    } catch (e) {
      setError(formatWaSurveyError(e, 'Validate failed').message)
    } finally {
      setWorking('')
    }
  }

  const runPublish = async () => {
    if (!selectedFlowId) return
    setWorking('publish')
    setError('')
    setMsg('')
    try {
      const data = await apiFetch(
        `/admin/wa-survey/flows/${encodeURIComponent(selectedFlowId)}/publish`,
        { method: 'POST', body: '{}' }
      )
      setMsg(data.message || 'Flow published.')
      await loadFlows()
      if (selectedFlowId) {
        const v = await apiFetch(
          `/admin/wa-survey/flows/${encodeURIComponent(selectedFlowId)}/validate`,
          { method: 'POST', body: '{}' }
        )
        setValidation(v)
      }
    } catch (e) {
      setError(formatWaSurveyError(e, 'Publish failed').message)
    } finally {
      setWorking('')
    }
  }

  const createDraft = async () => {
    setWorking('create')
    setError('')
    try {
      const data = await apiFetch(
        `/admin/wa-survey/types/${encodeURIComponent(typeId)}/flows`,
        {
          method: 'POST',
          body: JSON.stringify({
            privacy_mode: privacyMode,
            name: `Flow ${privacyMode}`,
            is_default: flows.length === 0,
          }),
        }
      )
      setMsg('Draft flow created — add nodes via API or test pack, then validate.')
      if (data?.flow?.id) setSelectedFlowId(data.flow.id)
      await loadFlows()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Create draft failed').message)
    } finally {
      setWorking('')
    }
  }

  const publishBlocked = validation && validation.ok === false

  return (
    <>
      <div className="pageTop">
        <div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            <Link to="/settings/wa-survey" style={{ color: 'var(--grn)' }}>
              WA Survey
            </Link>{' '}
            /{' '}
            <Link to={`/settings/wa-survey/${typeId}`} style={{ color: 'var(--grn)' }}>
              Type
            </Link>{' '}
            / Flows
          </div>
          <h1>Survey flows</h1>
          <p className="pageLead">
            Validate and publish graph flows. Errors block publish; warnings are shown but do not block.
          </p>
        </div>
        <div className="pageTopActions">
          <Link className="btn" to={`/settings/wa-survey/${typeId}`}>
            Back to type
          </Link>
          <Link className="btn" to="/settings/wa-survey/simulator">
            Open simulator
          </Link>
        </div>
      </div>

      {error ? (
        <div className="alert error">
          <strong>{error}</strong>
        </div>
      ) : null}
      {msg ? (
        <div className="alert ok">
          <strong>{msg}</strong>
        </div>
      ) : null}

      <section className="card">
        <div className="cardHead waSurveyTemplatesHead">
          <h2>Flows</h2>
          <div className="waSurveyTemplatesActions">
            <select
              className="input"
              value={privacyMode}
              onChange={(e) => setPrivacyMode(e.target.value)}
              aria-label="Privacy mode"
            >
              <option value="off">Privacy off</option>
              <option value="on">Privacy on</option>
            </select>
            <button type="button" className="btn sm" onClick={createDraft} disabled={working === 'create'}>
              New draft
            </button>
          </div>
        </div>
        <div className="cardBody">
          {loading ? (
            <p className="muted">Loading…</p>
          ) : (
            <div className="tableWrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Status</th>
                    <th>Default</th>
                    <th>Version</th>
                    <th>Updated</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {flows.length ? flows.map((f) => (
                    <tr key={f.id} className={f.id === selectedFlowId ? 'waSurveyFlowRowSelected' : ''}>
                      <td>{f.name}</td>
                      <td>
                        <span className={`pill ${statusPill(f.status)}`}>{f.status}</span>
                      </td>
                      <td>{f.is_default ? 'Yes' : '—'}</td>
                      <td>{f.version}</td>
                      <td className="muted">{f.updated_at ? f.updated_at.slice(0, 10) : '—'}</td>
                      <td>
                        <button
                          type="button"
                          className="btn sm"
                          onClick={() => {
                            setSelectedFlowId(f.id)
                            setValidation(null)
                          }}
                        >
                          Select
                        </button>
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={6} className="muted">
                        No flows for this privacy mode — create a draft or run the test pack seed.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {selectedFlowId ? (
        <section className="card">
          <div className="cardHead">
            <h2>Validate &amp; publish</h2>
          </div>
          <div className="cardBody">
            <p className="muted" style={{ marginBottom: 12 }}>
              Flow ID: <code>{selectedFlowId}</code>
            </p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
              <button type="button" className="btn" onClick={runValidate} disabled={working === 'validate'}>
                {working === 'validate' ? 'Validating…' : 'Validate'}
              </button>
              <button
                type="button"
                className="btn primary"
                onClick={runPublish}
                disabled={working === 'publish' || publishBlocked}
                title={publishBlocked ? 'Fix validation errors first' : ''}
              >
                {working === 'publish' ? 'Publishing…' : 'Publish'}
              </button>
            </div>

            {validation ? (
              <div className="waSurveyReadinessBlock">
                <p>
                  <span className={`pill ${validation.ok ? 'ok' : 'error'}`}>
                    {validation.ok ? 'OK' : 'Blocked'}
                  </span>
                </p>
                {(validation.errors || []).length ? (
                  <div className="alert error" style={{ marginTop: 12 }}>
                    <strong>Errors (must fix)</strong>
                    <ul className="waSurveyReadinessList">
                      {(validation.errors || []).map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {(validation.warnings || []).length ? (
                  <div className="alert warn" style={{ marginTop: 12 }}>
                    <strong>Warnings</strong>
                    <ul className="waSurveyReadinessList">
                      {(validation.warnings || []).map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="muted">Run validate to see errors and warnings before publish.</p>
            )}
          </div>
        </section>
      ) : null}
    </>
  )
}
