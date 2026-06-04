import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { buildWaSurveySimulatorUrl } from '../lib/waSurveySimulatorLink'
import WaSurveyPhonePreview from '../components/WaSurveyPhonePreview'

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
  const [testPhone, setTestPhone] = useState('')
  const [sendLive, setSendLive] = useState(false)
  const [pageCount, setPageCount] = useState(6)
  const [selectedPageRoles, setSelectedPageRoles] = useState([])
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
      if (deepLinkIndustry) setIndustryId(deepLinkIndustry)
      if (deepLinkTypeId) {
        setSurveyTypeId(deepLinkTypeId)
        setPrivacyMode(deepLinkPrivacy || 'off')
      } else {
        // No deep link — show all industries/types; admin selects before starting.
        setIndustryId('')
        setSurveyTypeId('')
        setPrivacyMode('off')
        setPrefill(null)
      }
    } catch (e) {
      setError(e?.message || 'Failed to load simulator options')
    } finally {
      setLoading(false)
    }
  }, [deepLinkTypeId, deepLinkIndustry, deepLinkPrivacy])

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
      const roles =
        data.page_roles?.length
          ? data.page_roles
          : data.suggested_page_roles?.['6'] || data.suggested_page_roles?.['5'] || []
      setSelectedPageRoles(roles)
      if (roles.length) setPageCount(roles.length)
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
      const payload = {
        survey_type_id: surveyTypeId,
        privacy_mode: privacyMode,
        flow_engine: flowEngine,
        flow_definition_id: flowDefinitionId || undefined,
        page_count: pageCount,
        selected_step_roles: selectedPageRoles.length ? selectedPageRoles : undefined,
        force_outcome_text_fallback: forceTextFallback,
        ai_picker_enabled: aiPickerEnabled,
        simulator_mock_picker: mockPicker,
        skip_test_pack_seed: true,
      }
      if (sendLive && testPhone.trim()) {
        payload.test_phone = testPhone.trim()
      }
      const data = await apiFetch('/admin/wa-survey/simulator/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
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
    sendLive,
    testPhone,
    pageCount,
    selectedPageRoles,
  ])

  const onPageCountChange = (count) => {
    const n = Number(count) || 6
    setPageCount(n)
    const suggested = prefill?.suggested_page_roles?.[String(n)]
    if (suggested?.length) setSelectedPageRoles(suggested)
  }

  const toggleMiddleRole = (role) => {
    const start = selectedPageRoles[0] === 'start' ? ['start'] : []
    const completion = selectedPageRoles[selectedPageRoles.length - 1] === 'completion' ? ['completion'] : []
    const middle = selectedPageRoles.filter((r) => r !== 'start' && r !== 'completion')
    const has = middle.includes(role)
    const nextMiddle = has ? middle.filter((r) => r !== role) : [...middle, role]
    const merged = [...start, ...nextMiddle, ...completion].filter(Boolean)
    if (!merged.includes('start')) merged.unshift('start')
    if (!merged.includes('completion')) merged.push('completion')
    setSelectedPageRoles(merged)
    setPageCount(merged.length)
  }

  const refreshState = useCallback(async (silent = false) => {
    if (!state?.recipient_id) return
    if (!silent) {
      setBusy(true)
      setError('')
    }
    try {
      const data = await apiFetch(
        `/admin/wa-survey/simulator/state/${encodeURIComponent(state.recipient_id)}`
      )
      setState(data.state)
    } catch (e) {
      if (!silent) setError(e?.message || 'Refresh failed')
    } finally {
      if (!silent) setBusy(false)
    }
  }, [state?.recipient_id])

  useEffect(() => {
    if (!state?.live_test || state?.completed) return undefined
    const timer = window.setInterval(() => {
      void refreshState(true)
    }, 4000)
    return () => window.clearInterval(timer)
  }, [state?.live_test, state?.completed, state?.recipient_id, refreshState])

  useEffect(() => {
    if (!autoStartRequested || autoStartDone.current || loading || busy) return
    if (!surveyTypeId || !prefill) return
    if (!prefill.can_start_simulation) return
    if (sendLive) return
    autoStartDone.current = true
    void startSession()
  }, [autoStartRequested, loading, busy, surveyTypeId, prefill, startSession, sendLive])

  const onSurveyTypeChange = async (nextTypeId, nextIndustryId) => {
    if (!nextTypeId) {
      setSurveyTypeId('')
      setPrefill(null)
      return
    }
    setSurveyTypeId(nextTypeId)
    const industryForPrefill = nextIndustryId || industryId || undefined
    await loadPrefill(nextTypeId, privacyMode, industryForPrefill)
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

  const submitAnswer = async (textOverride) => {
    if (!state?.recipient_id) return
    const text = String(textOverride ?? answer).trim()
    if (!text) return
    setBusy(true)
    setError('')
    try {
      const data = await apiFetch('/admin/wa-survey/simulator/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recipient_id: state.recipient_id,
          answer: text,
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

  const tplForRole = useCallback(
    (role) => (templatesInUse || []).find((t) => t.step_role === role),
    [templatesInUse]
  )

  const chatMessages = useMemo(() => {
    if (!state) return []
    const msgs = []
    const startTpl = tplForRole('start')
    const showStart =
      state.awaiting_start ||
      Number(state.step) === 0 ||
      (state.answers || []).length > 0 ||
      !state.completed
    if (showStart && (startTpl?.preview_body || q?.preview_body)) {
      msgs.push({
        role: 'outbound',
        body: startTpl?.preview_body || q?.preview_body,
        footer: startTpl?.footer || q?.footer || '',
        buttons: startTpl?.buttons || q?.buttons,
      })
    }
    for (const row of state.answers || []) {
      const tpl = row.step_role ? tplForRole(row.step_role) : null
      const qBody = row.question || tpl?.preview_body
      if (qBody) {
        msgs.push({
          role: 'outbound',
          body: qBody,
          footer: tpl?.footer,
          buttons: tpl?.buttons,
        })
      }
      if (row.answer) {
        msgs.push({ role: 'inbound', body: String(row.answer) })
      }
    }
    if (!state.completed && !state.awaiting_start && (q?.preview_body || q?.body)) {
      const btnList = Array.isArray(q?.buttons) && q.buttons.length
        ? q.buttons
        : (q?.options || []).map((label) => ({ label: String(label) }))
      msgs.push({
        role: 'outbound',
        body: q.preview_body || q.body,
        footer: q.footer,
        buttons: btnList.length ? btnList : undefined,
      })
    }
    if (state.completed && state.outcome_body_preview) {
      msgs.push({ role: 'outbound', body: state.outcome_body_preview, footer: 'Outcome message' })
    }
    return msgs
  }, [state, q, tplForRole])

  const quickReplies = useMemo(() => {
    if (state?.completed || !q) return []
    if (state.awaiting_start) {
      const fromButtons = (q.buttons || []).map((b) => String(b.label || b.text || b)).filter(Boolean)
      if (fromButtons.length) return fromButtons
      return ['Start survey']
    }
    if (q.button_labels?.length) return q.button_labels.map(String)
    if (q.options?.length) return q.options.map((o) => String(o))
    return []
  }, [q, state?.completed, state?.awaiting_start])

  const flowStepsForPreview = useMemo(() => {
    if (state?.flow_steps?.length) return state.flow_steps
    return (selectedPageRoles || []).map((role, idx) => {
      const tpl = tplForRole(role)
      return {
        step: idx + 1,
        step_role: role,
        title: tpl?.template_name || role.replace(/_/g, ' '),
        body: tpl?.preview_body || '',
        kind: role === 'start' ? 'template_outbound' : role === 'completion' ? 'closing' : 'survey_question',
      }
    })
  }, [state?.flow_steps, selectedPageRoles, tplForRole])

  const deepLinkLabel = deepLinkTypeId
    ? buildWaSurveySimulatorUrl({
        surveyTypeId: deepLinkTypeId,
        privacyMode: deepLinkPrivacy,
        industryId: deepLinkIndustry,
        autoStart: autoStartRequested,
      })
    : ''

  return (
    <div className="page waSurveySimulatorPage">
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
                  const nextIndustry = e.target.value
                  setIndustryId(nextIndustry)
                  setSurveyTypeId('')
                  setPrefill(null)
                }}
              >
                <option value="">All industries</option>
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
                onChange={(e) => void onSurveyTypeChange(e.target.value, industryId)}
                disabled={!surveyTypesForIndustry.length}
              >
                <option value="">
                  {surveyTypesForIndustry.length ? 'Select survey type…' : 'No survey types for this industry'}
                </option>
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
            <label>
              Pages
              <select className="input" value={pageCount} onChange={(e) => onPageCountChange(e.target.value)}>
                {[4, 5, 6].map((n) => (
                  <option key={n} value={n}>
                    {n} steps
                  </option>
                ))}
              </select>
            </label>
          </div>
          {selectedPageRoles.length ? (
            <div className="waSurveySimulatorFlowPath" style={{ marginBottom: 12 }}>
              <div className="muted" style={{ fontSize: '0.85rem', marginBottom: 6 }}>
                Survey path (your saved templates, in order):
              </div>
              <ol style={{ margin: 0, paddingLeft: 20, fontSize: '0.9rem' }}>
                {selectedPageRoles.map((role, idx) => {
                  const tpl = (prefill?.templates_preview || []).find((t) => t.step_role === role)
                  return (
                    <li key={`${role}-${idx}`}>
                      <strong>{idx + 1}.</strong> {role}
                      {tpl?.template_name ? ` — ${tpl.template_name}` : ''}
                    </li>
                  )
                })}
              </ol>
            </div>
          ) : null}
          {(prefill?.middle_step_roles || []).length ? (
            <div style={{ marginBottom: 12 }}>
              <div className="muted" style={{ fontSize: '0.85rem', marginBottom: 6 }}>
                Middle steps in your pack (toggle to change path):
              </div>
              <div className="waSurveySimulatorQuickReplies">
                {(prefill.middle_step_roles || []).map((role) => {
                  const active = selectedPageRoles.includes(role)
                  return (
                    <button
                      key={role}
                      type="button"
                      className={`btn btnSecondary btnSm${active ? ' is-active' : ''}`}
                      onClick={() => toggleMiddleRole(role)}
                    >
                      {role}
                    </button>
                  )
                })}
              </div>
            </div>
          ) : null}
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
          <div className="waSurveySimulatorLiveTestBlock" style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 8 }}>
              <input
                type="checkbox"
                checked={sendLive}
                onChange={(e) => setSendLive(e.target.checked)}
              />{' '}
              Send real WhatsApp to my mobile (Telnyx)
            </label>
            {sendLive ? (
              <>
                <label style={{ display: 'block', marginBottom: 6 }}>
                  Mobile number (E.164)
                  <input
                    className="input"
                    style={{ display: 'block', marginTop: 4, maxWidth: 320 }}
                    placeholder="+447700900123"
                    value={testPhone}
                    onChange={(e) => setTestPhone(e.target.value)}
                    autoComplete="tel"
                  />
                </label>
                <p className="muted" style={{ fontSize: '0.85rem', margin: 0 }}>
                  Sends your approved <strong>start template</strong> to your phone via Telnyx. Tap the button
                  on WhatsApp to open question 1 — this screen refreshes every few seconds.
                  {options?.telnyx_ready && !options.telnyx_ready.whatsapp ? (
                    <span style={{ color: 'crimson' }}> Telnyx WhatsApp is not ready yet.</span>
                  ) : null}
                </p>
              </>
            ) : (
              <p className="muted" style={{ fontSize: '0.85rem', margin: 0 }}>
                Leave unchecked for dry-run only (no Telnyx, reply in the browser).
              </p>
            )}
          </div>
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
              disabled={
                busy ||
                !surveyTypeId ||
                (prefill && !prefill.can_start_simulation) ||
                (sendLive && !testPhone.trim())
              }
              onClick={startSession}
            >
              {sendLive ? 'Send live test to mobile' : 'Start test session'}
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
        <section className="card waSurveySimulatorSessionCard" style={{ marginTop: 16 }}>
          <div className="cardBody">
            <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Live test chat</h2>
            <p className="muted" style={{ fontSize: '0.85rem', marginBottom: 12 }}>
              {state.live_test ? (
                <>
                  Live WhatsApp test to <code>{state.simulator_phone}</code> — reply on your phone.
                </>
              ) : (
                <>
                  Dry-run only — same runtime as production, no Telnyx or OpenAI. Synthetic phone:{' '}
                  <code>{state.simulator_phone || '—'}</code>
                </>
              )}
            </p>
            {state.live_test ? (
              <div style={{ marginBottom: 12 }}>
                <button type="button" className="btn btnSecondary btnSm" disabled={busy} onClick={() => void refreshState()}>
                  Refresh status
                </button>
              </div>
            ) : null}

            <div className="waSurveySimulatorChatColumn">
              <WaSurveyPhonePreview
                businessName={prefill?.survey_type_name || 'Survey'}
                conversationMessages={chatMessages}
                flowSteps={flowStepsForPreview}
                hideFlowNav={!flowStepsForPreview.length}
                approvalStatus={state.live_test ? 'Live WhatsApp test' : 'Saved templates (dry-run)'}
                disclaimer=""
              />
              {!state.completed && !state.live_test ? (
                <div className="waSurveySimulatorComposer">
                  {state.awaiting_start ? (
                    <p className="muted" style={{ fontSize: '0.85rem', marginBottom: 8 }}>
                      Step 1 — tap the start button below (same as WhatsApp quick reply).
                    </p>
                  ) : quickReplies.length ? (
                    <p className="muted" style={{ fontSize: '0.85rem', marginBottom: 8 }}>
                      Reply with a number or tap a choice:
                    </p>
                  ) : null}
                  {quickReplies.length ? (
                    <div className="waSurveySimulatorQuickReplies">
                      {quickReplies.map((label, idx) => (
                        <button
                          key={`${label}-${idx}`}
                          type="button"
                          className="btn btnSecondary btnSm"
                          disabled={busy}
                          onClick={() => void submitAnswer(label)}
                        >
                          {state.awaiting_start ? label : `${idx + 1}. ${label}`}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  <div className="waSurveySimulatorComposerRow">
                    <input
                      className="input"
                      placeholder="Type a reply as the respondent…"
                      value={answer}
                      onChange={(e) => setAnswer(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && void submitAnswer()}
                      disabled={busy}
                    />
                    <button
                      type="button"
                      className="btn btnPrimary"
                      disabled={busy || !answer.trim()}
                      onClick={() => void submitAnswer()}
                    >
                      Send
                    </button>
                  </div>
                </div>
              ) : null}
              {!state.completed && state.live_test ? (
                <p className="muted" style={{ fontSize: '0.9rem', marginTop: 8 }}>
                  Waiting for your reply on WhatsApp… The preview updates when you answer on your phone.
                </p>
              ) : null}
            </div>

            <details style={{ marginTop: 16 }}>
              <summary>Runtime details</summary>
            <div className="waSurveySimulatorRuntimeGrid" style={{ marginTop: 12, marginBottom: 12 }}>
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
                <pre style={{ fontSize: '0.75rem', background: '#f4f4f5', padding: 8 }}>
                  {JSON.stringify(state.outcome_delivery, null, 2)}
                </pre>
              </div>
            ) : null}

            {state.answers?.length ? (
              <details style={{ marginTop: 16 }}>
                <summary>Answer history ({state.answers.length})</summary>
                <pre style={{ fontSize: '0.75rem' }}>{JSON.stringify(state.answers, null, 2)}</pre>
              </details>
            ) : null}
            </details>
          </div>
        </section>
      ) : null}
    </div>
  )
}
