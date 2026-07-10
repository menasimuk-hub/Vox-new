import React, { useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch, apiUpload } from '../lib/api'
import AgentTestCallModal from '../components/agents/AgentTestCallModal'

const emptyAgent = {
  name: '',
  slug: '',
  description: '',
  system_prompt: '',
  call_workflow: '',
  knowledge_file_ids: [],
  voice_label: '',
  voice_type_label: '',
  telnyx_assistant_id: '',
  base_role: '',
  service_survey_role: '',
  service_interview_role: '',
  service_lead_sales_role: '',
  service_appointment_role: '',
  opening_disclosure_template:
    'Hello {first_name}, this is {agent_name} calling from {company_name}. This call is recorded for quality and assessment. Do you have about 10 to 15 minutes now?',
  supports_survey: false,
  supports_interview: false,
  supports_lead_sales: false,
  supports_appointment: false,
  is_default_survey: false,
  is_default_interview: false,
  is_default_lead_sales: false,
  is_default_appointment: false,
  disclosure_for_survey: true,
  disclosure_for_interview: true,
  disclosure_for_appointment: true,
  disclosure_mandatory: true,
  retry_policy_notes: 'Retry once after 1 hour for busy/no answer.',
  interruption_behavior_notes:
    'Never interrupt the candidate while they are answering. Wait until they finish. If interrupted mid-sentence, restate only the unfinished sentence.',
  voicemail_behavior: 'hang_up',
  missed_call_email_template_interview: '',
  missed_call_followup_notes_interview: '',
  opt_out_policy_notes: 'If remove me is said, stop and never retry.',
  is_active: true,
}

const SERVICE_CATALOG = [
  { id: 'survey', name: 'Survey', icon: 'ti ti-clipboard-list' },
  { id: 'interview', name: 'Interview', icon: 'ti ti-microphone' },
  { id: 'lead_sales', name: 'Lead / Sales', icon: 'ti ti-bolt' },
  { id: 'appointment', name: 'Appointments', icon: 'ti ti-calendar' },
]

function hasWorkflow(agent) {
  return Boolean(String(agent?.call_workflow || '').trim())
}

function isPlaceholderPrompt(prompt) {
  const text = String(prompt || '').trim().toLowerCase()
  return !text || text.includes('not configured')
}

const ENGLISH_TEST_SCRIPT =
  'OPENING\nGreet the candidate in a friendly tone and confirm they can hear you.\n\nQUESTIONS\n1. Tell me briefly about your background.\n2. Why are you interested in this role?\n'
const ARABIC_TEST_SCRIPT =
  'الافتتاحية\nرحّب بالمرشّح بنبرة ودّية وتأكد من أنه يسمعك بوضوح.\n\nالأسئلة\n١. حدّثني باختصار عن خلفيتك المهنية.\n٢. لماذا أنت مهتم بهذه الوظيفة؟\n'

function agentLooksArabic(a) {
  if (!a) return false
  if (/[\u0600-\u06FF]/.test(String(a.opening_disclosure_template || ''))) return true
  if (/[\u0600-\u06FF]/.test(String(a.system_prompt || ''))) return true
  const blob = `${a.name || ''} ${a.voice_label || ''} ${a.voice_type_label || ''} ${a.slug || ''}`.toLowerCase()
  if (blob.includes('عرب')) return true
  return /(?:^|[^a-z])(ar|arabic)(?:$|[^a-z])/.test(blob)
}

export default function AgentEditPage({ agentId, initialDraft, onClose, onSaved }) {
  const [agent, setAgent] = useState(initialDraft || emptyAgent)
  const [loading, setLoading] = useState(agentId !== 'new')
  const [saving, setSaving] = useState(false)
  const [kbUploading, setKbUploading] = useState(false)
  const [genPhase, setGenPhase] = useState('')
  const [msg, setMsg] = useState('')
  const [msgError, setMsgError] = useState(false)
  const [kbFiles, setKbFiles] = useState([])
  const fileInputRef = useRef(null)
  const [testScript, setTestScript] = useState(ENGLISH_TEST_SCRIPT)
  const [testScriptDirty, setTestScriptDirty] = useState(false)
  const [testCallOpen, setTestCallOpen] = useState(false)

  const flash = (text, isError = false) => {
    setMsg(text)
    setMsgError(isError)
  }

  const loadKb = async () => {
    const data = await apiFetch('/admin/knowledge-base?scope=org')
    setKbFiles(data?.files || [])
  }

  useEffect(() => {
    loadKb().catch(() => {})
  }, [])

  useEffect(() => {
    if (agentId === 'new') {
      setAgent(initialDraft ? { ...emptyAgent, ...initialDraft } : emptyAgent)
      setLoading(false)
      return
    }
    setLoading(true)
    apiFetch(`/admin/agents/${agentId}`)
      .then((data) => setAgent({ ...emptyAgent, ...data, knowledge_file_ids: data.knowledge_file_ids || [] }))
      .catch((e) => flash(e?.message || 'Failed to load agent', true))
      .finally(() => setLoading(false))
  }, [agentId, initialDraft])

  const setField = (field, value) => {
    setAgent((s) => ({ ...s, [field]: value }))
  }

  useEffect(() => {
    if (testScriptDirty) return
    setTestScript(agentLooksArabic(agent) ? ARABIC_TEST_SCRIPT : ENGLISH_TEST_SCRIPT)
  }, [agent.name, agent.voice_label, agent.voice_type_label, agent.slug, agent.opening_disclosure_template, agent.system_prompt, testScriptDirty])

  const validKnowledgeFileIds = useMemo(
    () => (agent.knowledge_file_ids || []).filter((id) => kbFiles.some((f) => f.id === id)),
    [agent.knowledge_file_ids, kbFiles],
  )

  const toggleKbFile = (fileId) => {
    setAgent((s) => {
      const ids = new Set(s.knowledge_file_ids || [])
      if (ids.has(fileId)) ids.delete(fileId)
      else ids.add(fileId)
      return { ...s, knowledge_file_ids: Array.from(ids) }
    })
  }

  const uploadKb = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.md')) {
      flash('Only .md files are allowed for agent knowledge base.', true)
      return
    }
    setKbUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const result = await apiUpload('/admin/knowledge-base/upload?scope=org', form)
      const uploaded = result?.file
      if (uploaded?.id) {
        setAgent((s) => ({
          ...s,
          knowledge_file_ids: [...new Set([...(s.knowledge_file_ids || []), uploaded.id])],
        }))
      }
      await loadKb()
      flash(`Uploaded ${file.name}. Save agent to persist KB link.`)
    } catch (e) {
      flash(e?.message || 'Upload failed', true)
    } finally {
      setKbUploading(false)
    }
  }

  const deleteKb = async (file) => {
    if (!window.confirm(`Delete "${file.original_filename}" from the library?`)) return
    try {
      await apiFetch(`/admin/knowledge-base/${file.id}`, { method: 'DELETE' })
      setAgent((s) => ({
        ...s,
        knowledge_file_ids: (s.knowledge_file_ids || []).filter((id) => id !== file.id),
      }))
      await loadKb()
      flash('Knowledge base file deleted.')
    } catch (e) {
      flash(e?.message || 'Could not delete file', true)
    }
  }

  const generationPayload = (rewrite) => ({
    description: String(agent.description || '').trim(),
    name: agent.name,
    agent_name: agent.voice_label || agent.name,
    knowledge_file_ids: validKnowledgeFileIds,
    rewrite,
  })

  const generateWorkflow = async () => {
    const description = String(agent.description || '').trim()
    if (!description) {
      flash('Add a description first, then generate the call workflow.', true)
      return
    }
    const rewrite = hasWorkflow(agent)
    if (rewrite && !window.confirm('Replace the existing call workflow?')) return

    setSaving(true)
    setGenPhase('workflow')
    flash('Generating call workflow with AI...')
    const path = agent.id ? `/admin/agents/${agent.id}/generate-workflow` : '/admin/agents/generate-workflow'
    try {
      const generated = await apiFetch(path, {
        method: 'POST',
        body: JSON.stringify(generationPayload(rewrite)),
      })
      setField('call_workflow', generated.call_workflow || '')
      flash('Call workflow generated. Review it, then click Generate prompt.')
    } catch (e) {
      flash(e?.message || 'Workflow generation failed', true)
    } finally {
      setSaving(false)
      setGenPhase('')
    }
  }

  const generatePrompt = async () => {
    const description = String(agent.description || '').trim()
    const workflow = String(agent.call_workflow || '').trim()
    if (!description) {
      flash('Add a description first.', true)
      return
    }
    if (!workflow) {
      flash('Generate the call workflow first, or paste workflow text into the Call workflow field.', true)
      return
    }

    setSaving(true)
    setGenPhase('prompt')
    flash('Generating system prompt (30–60 seconds)...')
    const path = agent.id ? `/admin/agents/${agent.id}/generate-prompt` : '/admin/agents/generate-prompt'
    try {
      const generated = await apiFetch(path, {
        method: 'POST',
        body: JSON.stringify({ ...generationPayload(true), call_workflow: workflow }),
      })
      const prompt = String(generated?.system_prompt || '').trim()
      if (!prompt) {
        flash('AI returned an empty system prompt.', true)
        return
      }
      setAgent((s) => ({
        ...s,
        system_prompt: prompt,
        base_role: s.base_role?.trim() ? s.base_role : prompt,
      }))
      flash('System prompt generated. Review System prompt and Base role, then Save agent.')
    } catch (e) {
      flash(e?.message || 'Prompt generation failed', true)
    } finally {
      setSaving(false)
      setGenPhase('')
    }
  }

  const buildSavePayload = () => ({
    name: agent.name,
    slug: agent.slug,
    description: agent.description,
    system_prompt: agent.system_prompt,
    call_workflow: agent.call_workflow,
    knowledge_file_ids: validKnowledgeFileIds,
    is_active: agent.is_active,
    voice_label: agent.voice_label,
    voice_type_label: agent.voice_type_label,
    telnyx_assistant_id: agent.telnyx_assistant_id,
    base_role: agent.base_role,
    service_survey_role: agent.service_survey_role,
    service_interview_role: agent.service_interview_role,
    service_lead_sales_role: agent.service_lead_sales_role,
    service_appointment_role: agent.service_appointment_role,
    opening_disclosure_template: agent.opening_disclosure_template,
    retry_policy_notes: agent.retry_policy_notes,
    interruption_behavior_notes: agent.interruption_behavior_notes,
    voicemail_behavior: agent.voicemail_behavior,
    missed_call_email_template_interview: agent.missed_call_email_template_interview,
    missed_call_followup_notes_interview: agent.missed_call_followup_notes_interview,
    opt_out_policy_notes: agent.opt_out_policy_notes,
    supports_survey: agent.supports_survey,
    supports_interview: agent.supports_interview,
    supports_lead_sales: agent.supports_lead_sales,
    supports_appointment: agent.supports_appointment,
    is_default_survey: agent.is_default_survey,
    is_default_interview: agent.is_default_interview,
    is_default_lead_sales: agent.is_default_lead_sales,
    is_default_appointment: agent.is_default_appointment,
    disclosure_for_survey: agent.disclosure_for_survey,
    disclosure_for_interview: agent.disclosure_for_interview,
    disclosure_for_appointment: agent.disclosure_for_appointment,
    disclosure_mandatory: agent.disclosure_mandatory,
  })

  const saveAgent = async () => {
    if (!agent.name?.trim()) {
      flash('Agent name is required', true)
      return
    }
    if (!agent.slug?.trim()) {
      flash('Slug is required', true)
      return
    }
    if (!agent.telnyx_assistant_id?.trim()) {
      flash('Telnyx Assistant ID is required', true)
      return
    }

    setSaving(true)
    try {
      const body = buildSavePayload()
      const saved = agent.id
        ? await apiFetch(`/admin/agents/${agent.id}`, { method: 'PUT', body: JSON.stringify(body) })
        : await apiFetch('/admin/agents', { method: 'POST', body: JSON.stringify(body) })
      setAgent({ ...emptyAgent, ...saved, knowledge_file_ids: saved.knowledge_file_ids || [] })
      flash('Agent saved.')
      onSaved?.(saved)
    } catch (e) {
      flash(e?.message || 'Failed to save agent', true)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="agentsMainPage agentsEditPage">
        <div className="agentsEditLoading">Loading agent…</div>
      </div>
    )
  }

  const enabledServices = SERVICE_CATALOG.filter((s) => agent[`supports_${s.id}`])
  const kbCount = validKnowledgeFileIds.length

  return (
    <div className="agentsMainPage agentsEditPage">
      <div className="agentsMainTop">
        <div>
          <button type="button" className="agentsEditBack" onClick={onClose}>
            <i className="ti ti-arrow-left" /> Main agents
          </button>
          <h1>{agent.id ? 'Edit agent' : 'Create agent'}</h1>
          <div className="agentsMainSub">
            Voice, prompts, knowledge base, and survey / interview service assignment.
          </div>
          <div className="agentsEditMeta">
            <span className="agentsChip">
              <i className="ti ti-file-text" /> {kbCount} KB
            </span>
            <span className="agentsChip">
              <i className="ti ti-plug" /> {enabledServices.length} services
            </span>
            {agent.supports_survey ? (
              <span className="agentsChip survey">
                <i className="ti ti-clipboard-list" /> Survey
              </span>
            ) : null}
            {agent.supports_interview ? (
              <span className="agentsChip interview">
                <i className="ti ti-microphone" /> Interview
              </span>
            ) : null}
            <span className={`agentsStatus ${agent.is_active ? 'active' : 'frozen'}`}>
              <i className={`ti ${agent.is_active ? 'ti-circle-check' : 'ti-lock'}`} />
              {agent.is_active ? 'Active' : 'Frozen'}
            </span>
          </div>
        </div>
        <div className="agentsMainActions">
          <button type="button" className="agentsBtn" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="agentsBtn primary" onClick={saveAgent} disabled={saving}>
            <i className="ti ti-device-floppy" /> {saving ? 'Saving…' : 'Save agent'}
          </button>
        </div>
      </div>

      {msg ? <div className={`agentsMsg${msgError ? ' is-error' : ''}`}>{msg}</div> : null}

      <div className="agentsEditStack">
        <section className="agentsPanel">
          <div className="agentsToolbar">
            <div className="agentsEditSectionTitle">
              <i className="ti ti-user-circle" /> Basics
            </div>
          </div>
          <div className="agentsEditGrid2">
            <div className="agentsEditField">
              <label>Agent name</label>
              <input className="input" value={agent.name} onChange={(e) => setField('name', e.target.value)} />
            </div>
            <div className="agentsEditField">
              <label>Slug identifier</label>
              <input className="input" value={agent.slug} onChange={(e) => setField('slug', e.target.value)} />
            </div>
            <div className="agentsEditField">
              <label>Voice label (dashboard)</label>
              <input
                className="input"
                value={agent.voice_label || ''}
                onChange={(e) => setField('voice_label', e.target.value)}
                placeholder="Leo, Sophie…"
              />
            </div>
            <div className="agentsEditField">
              <label>Voice type</label>
              <select className="input" value={agent.voice_type_label || ''} onChange={(e) => setField('voice_type_label', e.target.value)}>
                <option value="">Select voice type</option>
                <option value="Female British English">Female British English</option>
                <option value="Male British English">Male British English</option>
                <option value="Female American English">Female American English</option>
                <option value="Male Neutral">Male Neutral</option>
              </select>
            </div>
            <div className="agentsEditField span2">
              <label>Description / purpose (for AI generation)</label>
              <textarea className="input agentPromptAreaSm" rows={4} value={agent.description || ''} onChange={(e) => setField('description', e.target.value)} />
            </div>
            <div className="agentsEditField">
              <label className="agentActiveToggle">
                <input type="checkbox" checked={agent.is_active} onChange={(e) => setField('is_active', e.target.checked)} />
                <span>Active (frozen agents hidden from dashboard)</span>
              </label>
            </div>
          </div>
          <div className="agentsEditActions">
            <button type="button" className="agentsBtn" onClick={generateWorkflow} disabled={saving || !agent.description?.trim()}>
              {genPhase === 'workflow' ? 'Generating workflow…' : hasWorkflow(agent) ? 'Regenerate workflow' : '1. Generate workflow'}
            </button>
            <button
              type="button"
              className="agentsBtn primary"
              onClick={generatePrompt}
              disabled={saving || !agent.description?.trim() || !hasWorkflow(agent)}
            >
              {genPhase === 'prompt' ? 'Generating prompt…' : isPlaceholderPrompt(agent.system_prompt) ? '2. Generate prompt' : 'Regenerate prompt'}
            </button>
          </div>
          {agent.supports_interview ? (
            <p className="agentsEditNote" style={{ marginTop: 8 }}>
              Arabic interview agents: Generate prompt writes <strong>فصحى (MSA)</strong>. The live call still speaks the
              agent&apos;s dialect (Egyptian / Saudi Gulf) via runtime rules.
            </p>
          ) : null}
        </section>

        <section className="agentsPanel">
          <div className="agentsToolbar">
            <div className="agentsEditSectionTitle">
              <i className="ti ti-microphone" /> Telnyx &amp; disclosure
            </div>
          </div>
          <div className="agentsEditGrid2">
            <div className="agentsEditField">
              <label>Telnyx Assistant ID</label>
              <input
                className="input"
                value={agent.telnyx_assistant_id || ''}
                onChange={(e) => setField('telnyx_assistant_id', e.target.value)}
                placeholder="assistant-…"
              />
            </div>
            <div className="agentsEditField">
              <label>Voicemail behavior</label>
              <select className="input" value={agent.voicemail_behavior || 'hang_up'} onChange={(e) => setField('voicemail_behavior', e.target.value)}>
                <option value="hang_up">Hang up for now</option>
                <option value="leave_message">Leave message</option>
                <option value="retry_later">Mark for retry</option>
              </select>
            </div>
            {agent.supports_interview ? (
              <>
                <div className="agentsEditField">
                  <label>Missed-call follow-up email (interview)</label>
                  <p className="agentsEditNote">
                    Sent when a call is not answered and voicemail policy is <strong>Hang up for now</strong>.
                    Manage copy under Email settings → Interview missed call follow-up.
                  </p>
                  <select
                    className="input"
                    value={agent.missed_call_email_template_interview || ''}
                    onChange={(e) => setField('missed_call_email_template_interview', e.target.value)}
                  >
                    <option value="">Default — Interview missed call follow-up</option>
                    <option value="none">Disabled — do not send</option>
                    <option value="interview_missed_call_followup">Interview missed call follow-up</option>
                    <option value="interview_booking_invite">Interview booking invite</option>
                  </select>
                </div>
                <div className="agentsEditField span2">
                  <label>Missed-call experience notes (interview)</label>
                  <p className="agentsEditNote">
                    Optional paragraph inserted into the follow-up email as <code>{'{{followup_message}}'}</code>. Shown on the candidate report.
                  </p>
                  <textarea
                    className="input agentPromptAreaSm"
                    rows={3}
                    value={agent.missed_call_followup_notes_interview || ''}
                    onChange={(e) => setField('missed_call_followup_notes_interview', e.target.value)}
                    placeholder="Please use the link below to choose a call-back time for your short AI phone interview."
                  />
                </div>
              </>
            ) : null}
            <div className="agentsEditField span2">
              <label>Opening disclosure template</label>
              <p className="agentsEditNote">
                Leave blank to use the platform default from Main agents → Shared voice compliance.
              </p>
              <textarea
                className="input agentPromptAreaSm"
                rows={4}
                value={agent.opening_disclosure_template || ''}
                onChange={(e) => setField('opening_disclosure_template', e.target.value)}
              />
            </div>
            <div className="agentsEditField span2">
              <label>Test script (browser test call)</label>
              <p className="agentsEditNote">
                Short script used when you click <strong>Test agent</strong> — same Telnyx WebRTC path as web interviews.
              </p>
              <textarea
                className="input agentPromptAreaSm"
                rows={5}
                value={testScript}
                onChange={(e) => { setTestScript(e.target.value); setTestScriptDirty(true) }}
                placeholder="OPENING + QUESTIONS for a quick voice test…"
              />
            </div>
            <div className="agentsEditField span2 agentsEditActions">
              <button
                type="button"
                className="agentsBtn primary"
                disabled={agentId === 'new' || !agent.telnyx_assistant_id?.trim() || isPlaceholderPrompt(agent.system_prompt)}
                onClick={() => setTestCallOpen(true)}
              >
                <i className="ti ti-phone" /> Test agent
              </button>
              <span className="agentsEditNote" style={{ margin: 0 }}>
                Requires Telnyx Assistant ID and system prompt. Save agent first if you changed Telnyx ID or prompt.
              </span>
            </div>
          </div>
        </section>

        <div className="agentsEditGrid2">
          <section className="agentsPanel">
            <div className="agentsToolbar">
              <div className="agentsEditSectionTitle">
                <i className="ti ti-route" /> Call workflow
              </div>
            </div>
            <p className="agentsEditNote">
              Step-by-step flow after the opening disclosure (e.g. confirm they have time now).
            </p>
            <textarea
              className="input agentPromptArea"
              rows={10}
              value={agent.call_workflow || ''}
              onChange={(e) => setField('call_workflow', e.target.value)}
              placeholder="Step-by-step call flow…"
            />
          </section>
          <section className="agentsPanel">
            <div className="agentsToolbar">
              <div className="agentsEditSectionTitle">
                <i className="ti ti-brain" /> System prompt
              </div>
            </div>
            <textarea
              className="input agentPromptArea"
              rows={10}
              value={agent.system_prompt || ''}
              onChange={(e) => setField('system_prompt', e.target.value)}
              placeholder="Generated or hand-written instructions…"
            />
          </section>
        </div>

        <section className="agentsPanel">
          <div className="agentsToolbar">
            <div className="agentsEditSectionTitle">
              <i className="ti ti-file-text" /> Knowledge base
            </div>
            <label className="agentsBtn">
              {kbUploading ? 'Uploading…' : 'Upload .md'}
              <input ref={fileInputRef} type="file" accept=".md,text/markdown" hidden onChange={uploadKb} disabled={kbUploading} />
            </label>
          </div>
          <p className="agentsEditNote">Upload .md files and tick to attach to this agent. Used during AI prompt generation.</p>
          <div className="agentKbPanel">
            {kbFiles.length ? (
              kbFiles.map((file) => {
                const selected = (agent.knowledge_file_ids || []).includes(file.id)
                return (
                  <div
                    key={file.id}
                    className={`agentKbItem${selected ? ' is-selected' : ''}`}
                    onClick={() => toggleKbFile(file.id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && toggleKbFile(file.id)}
                  >
                    <input type="checkbox" checked={selected} readOnly tabIndex={-1} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <strong>{file.original_filename}</strong>
                      <div className="muted">{Math.round((file.size_bytes || 0) / 1024)} KB</div>
                    </div>
                    <button
                      type="button"
                      className="agentsAction warn"
                      onClick={(e) => {
                        e.stopPropagation()
                        deleteKb(file)
                      }}
                    >
                      <i className="ti ti-trash" />
                    </button>
                  </div>
                )
              })
            ) : (
              <div className="agentsEmpty">No KB files yet. Upload a .md file above.</div>
            )}
          </div>
        </section>

        <section className="agentsPanel">
          <div className="agentsToolbar">
            <div className="agentsEditSectionTitle">
              <i className="ti ti-list-check" /> Service assignment
            </div>
          </div>
          <p className="agentsEditNote">
            Enable <strong>Interview</strong>, <strong>Survey</strong>, or <strong>Appointments</strong> so this agent appears in the matching dashboard flow.
          </p>
          <div className="agentsTableWrap">
            <table className="agentsEditServiceTable">
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Enable</th>
                  <th>Default</th>
                </tr>
              </thead>
              <tbody>
                {SERVICE_CATALOG.map((svc) => (
                  <tr key={svc.id}>
                    <td>
                      <i className={svc.icon} /> {svc.name}
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={agent[`supports_${svc.id}`] || false}
                        onChange={(e) => setField(`supports_${svc.id}`, e.target.checked)}
                      />
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={agent[`is_default_${svc.id}`] || false}
                        onChange={(e) => setField(`is_default_${svc.id}`, e.target.checked)}
                        disabled={!agent[`supports_${svc.id}`]}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <div className="agentsEditGrid2">
          <section className="agentsPanel">
            <div className="agentsToolbar">
              <div className="agentsEditSectionTitle">
                <i className="ti ti-layers-subtract" /> Prompt layers
              </div>
            </div>
            <div className="agentsEditField">
              <label>Base role</label>
              <textarea className="input agentPromptAreaSm" rows={4} value={agent.base_role || ''} onChange={(e) => setField('base_role', e.target.value)} />
            </div>
            <div className="agentsEditField">
              <label>Survey role override</label>
              <textarea className="input agentPromptAreaSm" rows={3} value={agent.service_survey_role || ''} onChange={(e) => setField('service_survey_role', e.target.value)} />
            </div>
            <div className="agentsEditField">
              <label>Interview role override</label>
              <textarea className="input agentPromptAreaSm" rows={3} value={agent.service_interview_role || ''} onChange={(e) => setField('service_interview_role', e.target.value)} />
            </div>
            <div className="agentsEditField">
              <label>Lead / Sales role override</label>
              <textarea className="input agentPromptAreaSm" rows={3} value={agent.service_lead_sales_role || ''} onChange={(e) => setField('service_lead_sales_role', e.target.value)} />
            </div>
            <div className="agentsEditField">
              <label>Appointments role override</label>
              <textarea className="input agentPromptAreaSm" rows={3} value={agent.service_appointment_role || ''} onChange={(e) => setField('service_appointment_role', e.target.value)} />
            </div>
          </section>
          <section className="agentsPanel">
            <div className="agentsToolbar">
              <div className="agentsEditSectionTitle">
                <i className="ti ti-adjustments" /> Behavior settings
              </div>
            </div>
            <div className="agentsEditField">
              <label>Interruption handling</label>
              <textarea className="input agentPromptAreaSm" rows={3} value={agent.interruption_behavior_notes || ''} onChange={(e) => setField('interruption_behavior_notes', e.target.value)} />
            </div>
            <div className="agentsEditField">
              <label>Opt-out handling</label>
              <textarea className="input agentPromptAreaSm" rows={3} value={agent.opt_out_policy_notes || ''} onChange={(e) => setField('opt_out_policy_notes', e.target.value)} />
            </div>
            <div className="agentsEditField">
              <label>Retry policy</label>
              <textarea className="input agentPromptAreaSm" rows={2} value={agent.retry_policy_notes || ''} onChange={(e) => setField('retry_policy_notes', e.target.value)} />
            </div>
            <div className="agentsEditField">
              <label className="agentActiveToggle">
                <input type="checkbox" checked={agent.disclosure_mandatory} onChange={(e) => setField('disclosure_mandatory', e.target.checked)} />
                <span>Mandatory opening disclosure</span>
              </label>
            </div>
          </section>
        </div>

        <div className="agentsEditFooter">
          <button type="button" className="agentsBtn" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="agentsBtn primary" onClick={saveAgent} disabled={saving}>
            <i className="ti ti-device-floppy" /> {saving ? 'Saving…' : 'Save agent'}
          </button>
        </div>
      </div>
      {agentId !== 'new' ? (
        <AgentTestCallModal
          open={testCallOpen}
          onClose={() => setTestCallOpen(false)}
          agentId={agentId}
          testScript={testScript}
          agentLabel={agent.voice_label || agent.name}
        />
      ) : null}
    </div>
  )
}
