import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { buildWaSurveySimulatorUrl } from '../lib/waSurveySimulatorLink'

const FLOW_LINEAR = 'linear'
const FLOW_GRAPH = 'graph'

export default function WaSurveyFlowSimulator() {
  const [searchParams] = useSearchParams()
  const deepLinkTypeId = searchParams.get('survey_type_id') || ''
  const deepLinkPrivacy = searchParams.get('privacy_mode') || 'off'
  const deepLinkIndustry = searchParams.get('industry_id') || ''
  const autoStartRequested = searchParams.get('auto_start') === '1'

  const [options, setOptions] = useState(null)
  const [prefill, setPrefill] = useState(null)
  const [industryId, setIndustryId] = useState('')
  const [surveyTypeId, setSurveyTypeId] = useState('')
  const [privacyMode, setPrivacyMode] = useState('off')
  const [flowEngine, setFlowEngine] = useState(FLOW_GRAPH)
  const [flowDefinitionId, setFlowDefinitionId] = useState('')
  const [forceTextFallback, setForceTextFallback] = useState(false)
  const [aiPickerEnabled, setAiPickerEnabled] = useState(false)
  const [mockPicker, setMockPicker] = useState(true)
  const [state, setState] = useState(null)
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [seedMsg, setSeedMsg] = useState('')
  const autoStartDone = useRef(false)

  const loadOptions = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch('/admin/wa-survey/simulator/options')
      setOptions(data)
      if (!deepLinkTypeId) {
        setIndustryId(data.default_industry_id || '')
        setSurveyTypeId(data.default_survey_type_id || '')
        setPrivacyMode(data.default_privacy_mode || 'off')
      }
    } catch (e) {
      setError(e?.message || 'Failed to load simulator options')
    } finally {
      setLoading(false)
    }
  }, [deepLinkTypeId])

  const loadPrefill = useCallback(async (typeId, pm, industryOverride) => {
    if (!typeId) {
      setPrefill(null)
      return null
    }
    try {
      const prefillQs = new URLSearchParams({ privacy_mode: pm })
      const industryQs = industryOverride || deepLinkIndustry || industryId
      if (industryQs) prefillQs.set('industry_id', industryQs)
      const data = await apiFetch(
        `/admin/wa-survey/types/${encodeURIComponent(typeId)}/simulator-prefill?${prefillQs}`
      )
      setPrefill(data)
      setIndustryId(data.industry_id || deepLinkIndustry || '')
      setSurveyTypeId(data.survey_type_id || typeId)
      setPrivacyMode(data.privacy_mode || pm)
      setFlowEngine(data.flow_engine || FLOW_LINEAR)
      setFlowDefinitionId(data.flow_definition_id || '')
      setAiPickerEnabled(Boolean(data.ai_picker_enabled_default))
      return data
    } catch (e) {
      setPrefill(null)
      setError(e?.message || 'Could not load simulator prefill')
      return null
    }
  }, [deepLinkIndustry])

  useEffect(() => {
    loadOptions()
  }, [loadOptions])

  useEffect(() => {
    if (!deepLinkTypeId || loading) return
    void loadPrefill(deepLinkTypeId, deepLinkPrivacy || 'off')
  }, [deepLinkTypeId, deepLinkPrivacy, loading, loadPrefill])

  const surveyTypesForIndustry = (options?.survey_types || []).filter(
    (t) => !industryId || t.industry_id === industryId
  )

  const startSession = useCallback(async () => {
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
          flow_definition_id: flowDefinitionId || undefined,
          page_count: 6,
          selected_step_roles: ['start', 'rating', 'yes_no', 'helpfulness', 'reason', 'completion'],
          force_outcome_text_fallback: forceTextFallback,
          ai_picker_enabled: aiPickerEnabled,
          simulator_mock_picker: mockPicker,
          skip_test_pack_seed: true,
        }),
      })
      setState(data.state)
      setAnswer('')
    } catch (e) {
      setError(e?.message || 'Start failed')
    } finally {
      setBusy(false)
    }
  }, [
    surveyTypeId,
    privacyMode,
    flowEngine,
    flowDefinitionId,
    forceTextFallback,
    aiPickerEnabled,
    mockPicker,
  ])

  useEffect(() => {
    if (!autoStartRequested || autoStartDone.current || loading || busy) return
    if (!surveyTypeId || !prefill) return
    if (!prefill.can_start_simulation) return
    autoStartDone.current = true
    void startSession()
  }, [autoStartRequested, loading, busy, surveyTypeId, prefill, startSession])

  const onSurveyTypeChange = async (nextTypeId, nextIndustryId) => {
    setSurveyTypeId(nextTypeId)
    if (nextIndustryId) setIndustryId(nextIndustryId)
    await loadPrefill(nextTypeId, privacyMode, nextIndustryId || industryId)
  }

  const onPrivacyChange = async (pm) => {
    setPrivacyMode(pm)
    if (surveyTypeId) await loadPrefill(surveyTypeId, pm)
  }

  const ensurePack = async () => {
    setBusy(true)
    setSeedMsg('')
    setError('')
    try {
      const data = await apiFetch('/admin/wa-survey/test-pack/ensure', { method: 'POST' })
      setSeedMsg(`Pack ready: ${data.template_count} templates (${data.created} new, ${data.updated} updated)`)
      await loadOptions()
      if (surveyTypeId) await loadPrefill(surveyTypeId, privacyMode)
    } catch (e) {
      setError(e?.message || 'Seed failed')
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

  const templatesInUse = useMemo(() => {
    if (state?.templates_in_use?.length) return state.templates_in_use
    return prefill?.templates_preview || []
  }, [state, prefill])

  const q = state?.question
  const deepLinkLabel = deepLinkTypeId
    ? buildWaSurveySimulatorUrl({
        surveyTypeId: deepLinkTypeId,
        privacyMode: deepLinkPrivacy,
        industryId: deepLinkIndustry,
        autoStart: autoStartRequested,
      })
    : ''

  return (
    <div className="page" style={{ maxWidth: 960 }}>
      <p className="muted" style={{ marginBottom: 8 }}>
        <Link to="/settings/wa-survey">← WA Survey types</Link>
        {deepLinkTypeId && prefill?.survey_type_name ? (
          <>
            {' '}
            ·{' '}
            <Link to={`/settings/wa-survey/${deepLinkTypeId}`} style={{ color: 'var(--grn)' }}>
              {prefill.survey_type_name}
            </Link>
          </>
        ) : null}
      </p>
      <h1>WA Survey flow simulator</h1>
      <p className="muted">
        Internal browser test — uses the real survey runtime with dry-run messaging (no Telnyx / OpenAI).
      </p>
      <p className="muted" style={{ fontSize: '0.85rem' }}>
        Admin app only: port <strong>5174</strong>. Deep link example:{' '}
        <code style={{ fontSize: '0.8rem' }}>{deepLinkLabel || '/settings/wa-survey/simulator?survey_type_id=…'}</code>
      </p>

      {prefill?.use_saved_templates ? (
        <p className="muted" style={{ fontSize: '0.85rem', marginBottom: 8 }}>
          <span className="pill ok">Using latest saved templates</span> for this survey type and privacy mode.
        </p>
      ) : null}

      {loading ? <p className="muted">Loading…</p> : null}
      {error ? <p style={{ color: 'crimson' }}>{error}</p> : null}
      {seedMsg ? <p style={{ color: 'green' }}>{seedMsg}</p> : null}

      {prefill && (prefill.blocking_errors?.length || prefill.warnings?.length) ? (
        <section className="card" style={{ marginTop: 12 }}>
          <div className="cardBody">
            <h2 style={{ marginTop: 0, fontSize: '1.05rem' }}>Pre-flight</h2>
            {(prefill.blocking_errors || []).length ? (
              <div className="alert error">
                <strong>Cannot start until fixed</strong>
                <ul className="waSurveyReadinessList">
                  {(prefill.blocking_errors || []).map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {(prefill.warnings || []).length ? (
              <div className="alert warn">
                <strong>Warnings</strong>
                <ul className="waSurveyReadinessList">
                  {(prefill.warnings || []).slice(0, 8).map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}

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
                  if (first) void onSurveyTypeChange(first.id, e.target.value)
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
              <select
                className="input"
                value={surveyTypeId}
                onChange={(e) => void onSurveyTypeChange(e.target.value)}
              >
                {surveyTypesForIndustry.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.slug})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Privacy
              <select className="input" value={privacyMode} onChange={(e) => void onPrivacyChange(e.target.value)}>
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
          {flowDefinitionId ? (
            <p className="muted" style={{ fontSize: '0.85rem', marginBottom: 8 }}>
              Published flow: <code>{flowDefinitionId}</code>
              {prefill?.published_flow?.name ? ` (${prefill.published_flow.name})` : ''}
            </p>
          ) : flowEngine === FLOW_GRAPH ? (
            <p className="muted" style={{ fontSize: '0.85rem', marginBottom: 8 }}>
              No published graph — simulator will compile a draft graph from the step bank.
            </p>
          ) : null}
          <label style={{ display: 'block', marginBottom: 8 }}>
            <input
              type="checkbox"
              checked={aiPickerEnabled}
              onChange={(e) => setAiPickerEnabled(e.target.checked)}
              disabled={flowEngine !== FLOW_GRAPH}
            />{' '}
            Enable AI picker on graph
            {prefill && !prefill.platform_picker_enabled ? (
              <span className="muted"> (platform kill switch off)</span>
            ) : null}
          </label>
          <label style={{ display: 'block', marginBottom: 8 }}>
            <input
              type="checkbox"
              checked={mockPicker}
              onChange={(e) => setMockPicker(e.target.checked)}
              disabled={!aiPickerEnabled}
            />{' '}
            Use mock picker (no OpenAI call)
          </label>
          <label style={{ display: 'block', marginBottom: 12 }}>
            <input
              type="checkbox"
              checked={forceTextFallback}
              onChange={(e) => setForceTextFallback(e.target.checked)}
            />{' '}
            Force outcome text fallback (simulated template failure)
          </label>
          {options?.platform_picker ? (
            <p className="muted" style={{ fontSize: '0.85rem' }}>
              Platform picker: {options.platform_picker.ai_picker_enabled ? 'enabled' : 'disabled'} (kill switch)
            </p>
          ) : null}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button type="button" className="btn btnSecondary" disabled={busy} onClick={ensurePack}>
              Ensure test pack in DB
            </button>
            <button
              type="button"
              className="btn btnPrimary"
              disabled={busy || !surveyTypeId || (prefill && !prefill.can_start_simulation)}
              onClick={startSession}
            >
              Start test session
            </button>
          </div>
        </div>
      </section>

      {templatesInUse.length ? (
        <section className="card" style={{ marginTop: 16 }}>
          <div className="cardBody">
            <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Templates in use</h2>
            <div className="tableWrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Role</th>
                    <th>Template</th>
                    <th>Status</th>
                    <th>Usage</th>
                  </tr>
                </thead>
                <tbody>
                  {templatesInUse.map((row, idx) => (
                    <tr key={`${row.step_role}-${row.template_id}-${idx}`}>
                      <td>
                        {row.step_role}
                        {row.outcome_key ? ` (${row.outcome_key})` : ''}
                      </td>
                      <td>{row.template_name || row.template_id || '—'}</td>
                      <td>
                        <span className={`pill ${String(row.status).toUpperCase() === 'APPROVED' ? 'ok' : 'warn'}`}>
                          {row.status || '—'}
                        </span>
                      </td>
                      <td>{row.usage || row.action_type || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ) : null}

      {state ? (
        <section className="card" style={{ marginTop: 16 }}>
          <div className="cardBody">
            <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Session</h2>
            <div className="waSurveySimulatorRuntimeGrid" style={{ marginBottom: 12 }}>
              <div>
                <span className="muted">Step role</span>
                <div><strong>{state.current_step_role || '—'}</strong></div>
              </div>
              <div>
                <span className="muted">Node key</span>
                <div><strong>{state.current_node_key || '—'}</strong></div>
              </div>
              <div>
                <span className="muted">Outcome</span>
                <div><strong>{state.outcome_key || '—'}</strong></div>
              </div>
              <div>
                <span className="muted">Delivery</span>
                <div>
                  <strong>
                    {state.completed
                      ? state.outcome_used_text_fallback
                        ? 'Text fallback'
                        : state.outcome_action_type === 'send_template'
                          ? 'Template send (simulated)'
                          : state.outcome_action_type || '—'
                      : '—'}
                  </strong>
                </div>
              </div>
            </div>

            {state.last_branch_decision ? (
              <details open style={{ marginBottom: 12 }}>
                <summary>Last branch decision</summary>
                <pre style={{ fontSize: '0.75rem', background: '#f4f4f5', padding: 8 }}>
                  {JSON.stringify(state.last_branch_decision, null, 2)}
                </pre>
                <p className="muted" style={{ fontSize: '0.85rem' }}>
                  Rule: {state.last_branch_decision.rule_key} · {state.last_branch_decision.from_role} →{' '}
                  {state.last_branch_decision.to_role}
                </p>
              </details>
            ) : null}

            {state.picker_debug ? (
              <details style={{ marginBottom: 12 }}>
                <summary>Last picker decision</summary>
                <pre style={{ fontSize: '0.75rem', background: '#f4f4f5', padding: 8 }}>
                  {JSON.stringify(state.picker_debug, null, 2)}
                </pre>
              </details>
            ) : null}

            {state.completed ? (
              <div>
                <p className="muted">{state.outcome_body_preview}</p>
                <pre style={{ fontSize: '0.75rem', background: '#f4f4f5', padding: 8 }}>
                  {JSON.stringify(state.outcome_delivery, null, 2)}
                </pre>
              </div>
            ) : (
              <div>
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
