import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const FLOW_LINEAR = 'linear'
const FLOW_GRAPH = 'graph'

export default function WaSurveyFlowSimulator() {
  const [options, setOptions] = useState(null)
  const [industryId, setIndustryId] = useState('')
  const [surveyTypeId, setSurveyTypeId] = useState('')
  const [privacyMode, setPrivacyMode] = useState('off')
  const [flowEngine, setFlowEngine] = useState(FLOW_GRAPH)
  const [forceTextFallback, setForceTextFallback] = useState(false)
  const [state, setState] = useState(null)
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [seedMsg, setSeedMsg] = useState('')

  const loadOptions = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch('/admin/wa-survey/simulator/options')
      setOptions(data)
      setIndustryId(data.default_industry_id || '')
      setSurveyTypeId(data.default_survey_type_id || '')
      setPrivacyMode(data.default_privacy_mode || 'off')
    } catch (e) {
      setError(e?.message || 'Failed to load simulator options')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadOptions()
  }, [loadOptions])

  const surveyTypesForIndustry = (options?.survey_types || []).filter(
    (t) => !industryId || t.industry_id === industryId
  )

  const ensurePack = async () => {
    setBusy(true)
    setSeedMsg('')
    setError('')
    try {
      const data = await apiFetch('/admin/wa-survey/test-pack/ensure', { method: 'POST' })
      setSeedMsg(`Pack ready: ${data.template_count} templates (${data.created} new, ${data.updated} updated)`)
      await loadOptions()
    } catch (e) {
      setError(e?.message || 'Seed failed')
    } finally {
      setBusy(false)
    }
  }

  const startSession = async () => {
    setBusy(true)
    setError('')
    setState(null)
    try {
      const data = await apiFetch('/admin/wa-survey/simulator/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          survey_type_id: surveyTypeId,
          privacy_mode: privacyMode,
          flow_engine: flowEngine,
          page_count: 6,
          selected_step_roles: ['start', 'rating', 'yes_no', 'helpfulness', 'reason', 'completion'],
          force_outcome_text_fallback: forceTextFallback,
        }),
      })
      setState(data.state)
      setAnswer('')
    } catch (e) {
      setError(e?.message || 'Start failed')
    } finally {
      setBusy(false)
    }
  }

  const submitAnswer = async () => {
    if (!state?.recipient_id) return
    setBusy(true)
    setError('')
    try {
      const data = await apiFetch('/admin/wa-survey/simulator/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recipient_id: state.recipient_id,
          answer: answer.trim(),
        }),
      })
      setState(data.state)
      setAnswer('')
    } catch (e) {
      setError(e?.message || 'Answer failed')
    } finally {
      setBusy(false)
    }
  }

  const q = state?.question

  return (
    <div className="page" style={{ maxWidth: 960 }}>
      <p className="muted" style={{ marginBottom: 8 }}>
        <Link to="/settings/wa-survey">← WA Survey types</Link>
      </p>
      <h1>WA Survey flow simulator</h1>
      <p className="muted">
        Internal browser test — uses the real survey runtime with dry-run messaging (no Telnyx / OpenAI).
      </p>

      {loading ? <p className="muted">Loading…</p> : null}
      {error ? <p style={{ color: 'crimson' }}>{error}</p> : null}
      {seedMsg ? <p style={{ color: 'green' }}>{seedMsg}</p> : null}

      <section className="card" style={{ marginTop: 16 }}>
        <div className="cardBody">
          <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Setup</h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 12 }}>
            <label>
              Industry
              <select
                className="input"
                value={industryId}
                onChange={(e) => {
                  setIndustryId(e.target.value)
                  const first = (options?.survey_types || []).find((t) => t.industry_id === e.target.value)
                  if (first) setSurveyTypeId(first.id)
                }}
              >
                {(options?.industries || []).map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Survey type
              <select className="input" value={surveyTypeId} onChange={(e) => setSurveyTypeId(e.target.value)}>
                {surveyTypesForIndustry.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.slug})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Privacy
              <select className="input" value={privacyMode} onChange={(e) => setPrivacyMode(e.target.value)}>
                <option value="off">Off (standard)</option>
                <option value="on">On (anonymous)</option>
              </select>
            </label>
            <label>
              Flow mode
              <select className="input" value={flowEngine} onChange={(e) => setFlowEngine(e.target.value)}>
                <option value={FLOW_LINEAR}>Linear</option>
                <option value={FLOW_GRAPH}>Graph</option>
              </select>
            </label>
          </div>
          <label style={{ display: 'block', marginBottom: 12 }}>
            <input
              type="checkbox"
              checked={forceTextFallback}
              onChange={(e) => setForceTextFallback(e.target.checked)}
            />{' '}
            Force outcome text fallback (simulated template failure)
          </label>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button type="button" className="btn btnSecondary" disabled={busy} onClick={ensurePack}>
              Ensure test pack in DB
            </button>
            <button type="button" className="btn btnPrimary" disabled={busy || !surveyTypeId} onClick={startSession}>
              Start test session
            </button>
          </div>
          {options?.test_pack ? (
            <p className="muted" style={{ marginTop: 12, fontSize: '0.85rem' }}>
              Default pack: {options.test_pack.industry.name} / {options.test_pack.survey_type.name} —{' '}
              {options.test_pack.template_count} templates
            </p>
          ) : null}
        </div>
      </section>

      {state ? (
        <section className="card" style={{ marginTop: 16 }}>
          <div className="cardBody">
            <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Session</h2>
            <pre
              style={{
                fontSize: '0.8rem',
                background: '#f4f4f5',
                padding: 12,
                overflow: 'auto',
                borderRadius: 6,
              }}
            >
              {JSON.stringify(
                {
                  session_id: state.session_id,
                  recipient_id: state.recipient_id,
                  order_id: state.order_id,
                  flow_engine: state.flow_engine,
                  flow_mode: state.flow_mode,
                  step: state.step,
                  total: state.total,
                  current_step_role: state.current_step_role,
                  current_node_key: state.current_node_key,
                  outcome_key: state.outcome_key,
                  completed: state.completed,
                },
                null,
                2
              )}
            </pre>

            {state.completed ? (
              <div>
                <p>
                  <strong>Outcome:</strong> {state.outcome_key || '—'}
                </p>
                <p>
                  <strong>Final delivery:</strong>{' '}
                  {state.outcome_used_text_fallback ? 'text fallback' : 'template send (simulated)'}
                </p>
                <p className="muted">{state.outcome_body_preview}</p>
                <pre style={{ fontSize: '0.75rem', background: '#f4f4f5', padding: 8 }}>
                  {JSON.stringify(state.outcome_delivery, null, 2)}
                </pre>
              </div>
            ) : (
              <div>
                <p>
                  <strong>Step role:</strong> {state.current_step_role || '—'}
                  {state.current_node_key ? (
                    <>
                      {' '}
                      · <strong>Node:</strong> {state.current_node_key}
                    </>
                  ) : null}
                </p>
                <div
                  style={{
                    background: '#e8f5e9',
                    border: '1px solid #c8e6c9',
                    padding: 12,
                    borderRadius: 8,
                    marginBottom: 12,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {q?.body || q?.text || '(no question)'}
                </div>
                {q?.options?.length ? (
                  <p className="muted" style={{ fontSize: '0.85rem' }}>
                    Suggested replies: {q.options.join(' · ')}
                  </p>
                ) : null}
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <input
                    className="input"
                    style={{ flex: '1 1 200px' }}
                    placeholder="Your answer"
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && submitAnswer()}
                  />
                  <button type="button" className="btn btnPrimary" disabled={busy || !answer.trim()} onClick={submitAnswer}>
                    Send answer
                  </button>
                </div>
              </div>
            )}

            {state.answers?.length ? (
              <details style={{ marginTop: 16 }}>
                <summary>Answer history ({state.answers.length})</summary>
                <pre style={{ fontSize: '0.75rem' }}>{JSON.stringify(state.answers, null, 2)}</pre>
              </details>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  )
}
