import React, { useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch, apiUpload } from '../lib/api'

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
  opening_disclosure_template:
    'Hello, this is {agent_name}, the AI assistant calling from {company_name}. This call is recorded for quality and service purposes.',
  supports_survey: false,
  supports_interview: false,
  supports_lead_sales: false,
  is_default_survey: false,
  is_default_interview: false,
  is_default_lead_sales: false,
  disclosure_for_survey: true,
  disclosure_for_interview: true,
  disclosure_mandatory: true,
  retry_policy_notes: 'Retry once after 1 hour for busy/no answer.',
  interruption_behavior_notes: 'If interrupted before disclosure, restart it clearly.',
  voicemail_behavior: 'hang_up',
  opt_out_policy_notes: 'If remove me is said, stop and never retry.',
  is_active: true,
}

const SERVICE_CATALOG = [
  { id: 'survey', name: 'Survey', icon: 'ti ti-clipboard-list' },
  { id: 'interview', name: 'Interview', icon: 'ti ti-microphone' },
  { id: 'lead_sales', name: 'Lead / Sales', icon: 'ti ti-bolt' },
]

function hasWorkflow(agent) {
  return Boolean(String(agent?.call_workflow || '').trim())
}

function isPlaceholderPrompt(prompt) {
  const text = String(prompt || '').trim().toLowerCase()
  return !text || text.includes('not configured')
}

export default function AgentEditPage({ agentId, initialDraft, onClose, onSaved }) {
  const [agent, setAgent] = useState(initialDraft || emptyAgent)
  const [loading, setLoading] = useState(agentId !== 'new')
  const [saving, setSaving] = useState(false)
  const [kbUploading, setKbUploading] = useState(false)
  const [genPhase, setGenPhase] = useState('')
  const [msg, setMsg] = useState('')
  const [kbFiles, setKbFiles] = useState([])
  const fileInputRef = useRef(null)

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
      .catch((e) => setMsg(e?.message || 'Failed to load agent'))
      .finally(() => setLoading(false))
  }, [agentId, initialDraft])

  const setField = (field, value) => {
    setAgent((s) => ({ ...s, [field]: value }))
  }

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
      setMsg('Only .md files are allowed for agent knowledge base.')
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
      setMsg(`Uploaded ${file.name}. Save agent to persist KB link.`)
    } catch (e) {
      setMsg(e?.message || 'Upload failed')
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
      setMsg('Knowledge base file deleted.')
    } catch (e) {
      setMsg(e?.message || 'Could not delete file')
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
      setMsg('Add a description first, then generate the call workflow.')
      return
    }
    const rewrite = hasWorkflow(agent)
    if (rewrite && !window.confirm('Replace the existing call workflow?')) return

    setSaving(true)
    setGenPhase('workflow')
    setMsg('Generating call workflow with AI...')
    const path = agent.id ? `/admin/agents/${agent.id}/generate-workflow` : '/admin/agents/generate-workflow'
    try {
      const generated = await apiFetch(path, {
        method: 'POST',
        body: JSON.stringify(generationPayload(rewrite)),
      })
      const workflow = generated.call_workflow || ''
      setField('call_workflow', workflow)
      setMsg('Call workflow generated. Review it, then click Generate prompt.')
    } catch (e) {
      setMsg(e?.message || 'Workflow generation failed')
    } finally {
      setSaving(false)
      setGenPhase('')
    }
  }

  const generatePrompt = async () => {
    const description = String(agent.description || '').trim()
    const workflow = String(agent.call_workflow || '').trim()
    if (!description) {
      setMsg('Add a description first.')
      return
    }
    if (!workflow) {
      setMsg('Generate the call workflow first, or paste workflow text into the Call workflow field.')
      return
    }

    setSaving(true)
    setGenPhase('prompt')
    setMsg('Generating system prompt (30-60 seconds)...')
    const path = agent.id ? `/admin/agents/${agent.id}/generate-prompt` : '/admin/agents/generate-prompt'
    try {
      const generated = await apiFetch(path, {
        method: 'POST',
        body: JSON.stringify({ ...generationPayload(true), call_workflow: workflow }),
      })
      const prompt = String(generated?.system_prompt || '').trim()
      if (!prompt) {
        setMsg('AI returned an empty system prompt.')
        return
      }
      setAgent((s) => ({
        ...s,
        system_prompt: prompt,
        base_role: s.base_role?.trim() ? s.base_role : prompt,
      }))
      setMsg('System prompt generated. Review System prompt and Base role, then Save agent.')
    } catch (e) {
      setMsg(e?.message || 'Prompt generation failed')
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
    opening_disclosure_template: agent.opening_disclosure_template,
    retry_policy_notes: agent.retry_policy_notes,
    interruption_behavior_notes: agent.interruption_behavior_notes,
    voicemail_behavior: agent.voicemail_behavior,
    opt_out_policy_notes: agent.opt_out_policy_notes,
    supports_survey: agent.supports_survey,
    supports_interview: agent.supports_interview,
    supports_lead_sales: agent.supports_lead_sales,
    is_default_survey: agent.is_default_survey,
    is_default_interview: agent.is_default_interview,
    is_default_lead_sales: agent.is_default_lead_sales,
    disclosure_for_survey: agent.disclosure_for_survey,
    disclosure_for_interview: agent.disclosure_for_interview,
    disclosure_mandatory: agent.disclosure_mandatory,
  })

  const saveAgent = async () => {
    if (!agent.name?.trim()) {
      setMsg('Agent name is required')
      return
    }
    if (!agent.slug?.trim()) {
      setMsg('Slug is required')
      return
    }
    if (!agent.telnyx_assistant_id?.trim()) {
      setMsg('Telnyx Assistant ID is required')
      return
    }
    if (agent.supports_survey && !agent.is_active) {
      setMsg('Warning: frozen agents will not appear in dashboard survey agent dropdown.')
    }

    setSaving(true)
    try {
      const body = buildSavePayload()
      const saved = agent.id
        ? await apiFetch(`/admin/agents/${agent.id}`, { method: 'PUT', body: JSON.stringify(body) })
        : await apiFetch('/admin/agents', { method: 'POST', body: JSON.stringify(body) })
      setAgent({ ...emptyAgent, ...saved, knowledge_file_ids: saved.knowledge_file_ids || [] })
      setMsg('Agent saved.')
      onSaved?.(saved)
    } catch (e) {
      setMsg(e?.message || 'Failed to save agent')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div style={{ padding: 32, textAlign: 'center' }}>Loading...</div>

  const enabledServices = SERVICE_CATALOG.filter((s) => agent[`supports_${s.id}`])
  const kbCount = validKnowledgeFileIds.length

  return (
    <div style={styles.container}>
      <div style={styles.topbar}>
        <div style={styles.topbarLeft}>
          <button type="button" onClick={onClose} style={styles.backBtn}>
            <i className="ti ti-arrow-left"></i> Agents
          </button>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#0f172a' }}>
              {agent.id ? 'Edit agent' : 'Create agent'}
            </div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>
              Configure voice, prompts, KB files, and survey/interview assignment
            </div>
          </div>
        </div>
        <div style={styles.headerActions}>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <div style={styles.stat}>
              <i className="ti ti-file-text"></i> {kbCount} KB
            </div>
            <div style={styles.stat}>
              <i className="ti ti-building"></i> {enabledServices.length} services
            </div>
            {agent.supports_survey ? (
              <div style={{ ...styles.stat, background: '#e7efff', color: '#2563eb' }}>
                <i className="ti ti-phone"></i> Dashboard survey
              </div>
            ) : null}
          </div>
          <button type="button" onClick={saveAgent} disabled={saving} style={{ ...styles.btn, ...styles.btnPrimary }}>
            <i className="ti ti-device-floppy"></i> {saving ? 'Saving...' : 'Save agent'}
          </button>
        </div>
      </div>

      {msg ? (
        <div style={{ ...styles.msg, margin: '0 32px 16px', padding: '12px 16px', borderRadius: 8 }}>{msg}</div>
      ) : null}

      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '0 32px 32px' }}>
        <div style={styles.card}>
          <div style={styles.cardTitle}>
            <i className="ti ti-user-circle" style={{ color: '#2563eb' }}></i> Basics
          </div>
          <div style={styles.grid2}>
            <div style={styles.formGroup}>
              <label style={styles.label}>Agent name</label>
              <input value={agent.name} onChange={(e) => setField('name', e.target.value)} style={styles.input} />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Slug identifier</label>
              <input value={agent.slug} onChange={(e) => setField('slug', e.target.value)} style={styles.input} />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Voice label (shown in dashboard)</label>
              <input
                value={agent.voice_label || ''}
                onChange={(e) => setField('voice_label', e.target.value)}
                placeholder="Sophie, James..."
                style={styles.input}
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Voice type</label>
              <select
                value={agent.voice_type_label || ''}
                onChange={(e) => setField('voice_type_label', e.target.value)}
                style={styles.input}
              >
                <option value="">Select voice type</option>
                <option value="Female British English">Female British English</option>
                <option value="Male British English">Male British English</option>
                <option value="Female American English">Female American English</option>
                <option value="Male Neutral">Male Neutral</option>
              </select>
            </div>
            <div style={{ ...styles.formGroup, gridColumn: '1 / -1' }}>
              <label style={styles.label}>Description / purpose (used for AI generation)</label>
              <textarea
                value={agent.description || ''}
                onChange={(e) => setField('description', e.target.value)}
                style={styles.textarea}
                rows={3}
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>
                <input
                  type="checkbox"
                  checked={agent.is_active}
                  onChange={(e) => setField('is_active', e.target.checked)}
                  style={{ marginRight: 8 }}
                />
                Active (frozen agents hidden from dashboard)
              </label>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 8 }}>
            <button type="button" onClick={generateWorkflow} disabled={saving || !agent.description?.trim()} style={styles.btn}>
              {genPhase === 'workflow' ? 'Generating workflow...' : hasWorkflow(agent) ? 'Regenerate workflow' : '1. Generate workflow'}
            </button>
            <button
              type="button"
              onClick={generatePrompt}
              disabled={saving || !agent.description?.trim() || !hasWorkflow(agent)}
              style={{ ...styles.btn, ...styles.btnPrimary }}
            >
              {genPhase === 'prompt' ? 'Generating prompt...' : isPlaceholderPrompt(agent.system_prompt) ? '2. Generate prompt' : 'Regenerate prompt'}
            </button>
          </div>
        </div>

        <div style={styles.card}>
          <div style={styles.cardTitle}>
            <i className="ti ti-microphone" style={{ color: '#d97706' }}></i> Telnyx & disclosure
          </div>
          <div style={styles.grid2}>
            <div style={styles.formGroup}>
              <label style={styles.label}>Telnyx Assistant ID</label>
              <input
                value={agent.telnyx_assistant_id || ''}
                onChange={(e) => setField('telnyx_assistant_id', e.target.value)}
                placeholder="asst_..."
                style={styles.input}
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Voicemail behavior</label>
              <select
                value={agent.voicemail_behavior || 'hang_up'}
                onChange={(e) => setField('voicemail_behavior', e.target.value)}
                style={styles.input}
              >
                <option value="hang_up">Hang up</option>
                <option value="leave_message">Leave message</option>
                <option value="retry_later">Mark for retry</option>
              </select>
            </div>
            <div style={{ ...styles.formGroup, gridColumn: '1 / -1' }}>
              <label style={styles.label}>Opening disclosure template</label>
              <div style={styles.sectionNote}>
                Leave blank to use the platform default from Main agents → Shared voice compliance.
                Changes apply to new script generation and live calls; regenerate approved survey scripts after editing.
              </div>
              <textarea
                value={agent.opening_disclosure_template || ''}
                onChange={(e) => setField('opening_disclosure_template', e.target.value)}
                style={styles.textarea}
                rows={3}
              />
            </div>
          </div>
        </div>

        <div style={styles.grid2}>
          <div style={styles.card}>
            <div style={styles.cardTitle}>Call workflow</div>
            <div style={styles.sectionNote}>
              Step-by-step flow after the opening disclosure (e.g. ask if they have time now). Leave blank to rely on generated script defaults.
            </div>
            <textarea
              value={agent.call_workflow || ''}
              onChange={(e) => setField('call_workflow', e.target.value)}
              style={styles.textarea}
              rows={8}
              placeholder="Step-by-step call flow..."
            />
          </div>
          <div style={styles.card}>
            <div style={styles.cardTitle}>System prompt</div>
            <textarea
              value={agent.system_prompt || ''}
              onChange={(e) => setField('system_prompt', e.target.value)}
              style={styles.textarea}
              rows={8}
              placeholder="Generated or hand-written instructions..."
            />
          </div>
        </div>

        <div style={styles.card}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div style={styles.cardTitle}>
              <i className="ti ti-file-text" style={{ color: '#16a34a' }}></i> Knowledge base
            </div>
            <label style={{ ...styles.btn, cursor: 'pointer' }}>
              {kbUploading ? 'Uploading...' : 'Upload .md'}
              <input ref={fileInputRef} type="file" accept=".md,text/markdown" hidden onChange={uploadKb} disabled={kbUploading} />
            </label>
          </div>
          <div style={styles.sectionNote}>Upload .md files and tick to attach to this agent. Used during AI prompt generation.</div>
          <div style={{ marginTop: 12 }}>
            {kbFiles.length ? (
              kbFiles.map((file) => {
                const selected = (agent.knowledge_file_ids || []).includes(file.id)
                return (
                  <div
                    key={file.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      padding: '10px 0',
                      borderBottom: '1px solid #e2e8f0',
                      cursor: 'pointer',
                      background: selected ? '#f0f7ff' : 'transparent',
                    }}
                    onClick={() => toggleKbFile(file.id)}
                  >
                    <input type="checkbox" checked={selected} readOnly />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, fontWeight: 600 }}>{file.original_filename}</div>
                      <div style={{ fontSize: 11, color: '#94a3b8' }}>
                        {Math.round((file.size_bytes || 0) / 1024)} KB
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        deleteKb(file)
                      }}
                      style={{ background: 'none', border: 'none', color: '#e11d48', cursor: 'pointer' }}
                    >
                      <i className="ti ti-trash"></i>
                    </button>
                  </div>
                )
              })
            ) : (
              <div style={{ color: '#64748b', fontSize: 13 }}>No KB files yet. Upload a .md file above.</div>
            )}
          </div>
        </div>

        <div style={styles.card}>
          <div style={styles.cardTitle}>
            <i className="ti ti-list-check" style={{ color: '#5f4be3' }}></i> Service assignment
          </div>
          <div style={styles.sectionNote}>
            Enable Survey to make this agent appear in the dashboard AI voice survey dropdown.
          </div>
          <table style={styles.serviceTable}>
            <thead>
              <tr>
                <th style={styles.serviceTh}>Service</th>
                <th style={styles.serviceTh}>Enable</th>
                <th style={styles.serviceTh}>Default</th>
              </tr>
            </thead>
            <tbody>
              {SERVICE_CATALOG.map((svc) => (
                <tr key={svc.id}>
                  <td style={styles.serviceTd}>
                    <i className={svc.icon}></i> {svc.name}
                  </td>
                  <td style={styles.serviceTd}>
                    <input
                      type="checkbox"
                      checked={agent[`supports_${svc.id}`] || false}
                      onChange={(e) => setField(`supports_${svc.id}`, e.target.checked)}
                    />
                  </td>
                  <td style={styles.serviceTd}>
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

        <div style={styles.grid2}>
          <div style={styles.card}>
            <div style={styles.cardTitle}>Prompt layers</div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Base role</label>
              <textarea value={agent.base_role || ''} onChange={(e) => setField('base_role', e.target.value)} style={styles.textarea} rows={4} />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Survey role override</label>
              <textarea
                value={agent.service_survey_role || ''}
                onChange={(e) => setField('service_survey_role', e.target.value)}
                style={styles.textarea}
                rows={3}
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Interview role override</label>
              <textarea
                value={agent.service_interview_role || ''}
                onChange={(e) => setField('service_interview_role', e.target.value)}
                style={styles.textarea}
                rows={3}
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Lead / Sales role override</label>
              <textarea
                value={agent.service_lead_sales_role || ''}
                onChange={(e) => setField('service_lead_sales_role', e.target.value)}
                style={styles.textarea}
                rows={3}
              />
            </div>
          </div>
          <div style={styles.card}>
            <div style={styles.cardTitle}>Behavior settings</div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Interruption handling</label>
              <textarea
                value={agent.interruption_behavior_notes || ''}
                onChange={(e) => setField('interruption_behavior_notes', e.target.value)}
                style={styles.textarea}
                rows={3}
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Opt-out handling</label>
              <textarea
                value={agent.opt_out_policy_notes || ''}
                onChange={(e) => setField('opt_out_policy_notes', e.target.value)}
                style={styles.textarea}
                rows={3}
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Retry policy</label>
              <textarea
                value={agent.retry_policy_notes || ''}
                onChange={(e) => setField('retry_policy_notes', e.target.value)}
                style={styles.textarea}
                rows={2}
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>
                <input
                  type="checkbox"
                  checked={agent.disclosure_mandatory}
                  onChange={(e) => setField('disclosure_mandatory', e.target.checked)}
                  style={{ marginRight: 8 }}
                />
                Mandatory opening disclosure
              </label>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button type="button" onClick={onClose} style={styles.btn}>
            Cancel
          </button>
          <button type="button" onClick={saveAgent} disabled={saving} style={{ ...styles.btn, ...styles.btnPrimary }}>
            {saving ? 'Saving...' : 'Save agent'}
          </button>
        </div>
      </div>
    </div>
  )
}

const styles = {
  container: { width: '100%', background: '#f8fafc' },
  topbar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '16px 32px',
    borderBottom: '1px solid #e2e8f0',
    background: '#f8fafc',
    position: 'sticky',
    top: 0,
    zIndex: 40,
  },
  topbarLeft: { display: 'flex', alignItems: 'center', gap: 24 },
  backBtn: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    color: '#475569',
    fontSize: 13,
    fontWeight: 500,
  },
  headerActions: { display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' },
  stat: {
    fontSize: 12,
    color: '#64748b',
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    background: '#f1f5f9',
    padding: '4px 12px',
    borderRadius: 20,
  },
  btn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 18px',
    borderRadius: 40,
    fontWeight: 600,
    fontSize: 13,
    border: '1px solid #e2e8f0',
    cursor: 'pointer',
    background: '#fff',
    color: '#0f172a',
  },
  btnPrimary: { background: '#2563eb', color: '#fff', borderColor: '#2563eb' },
  msg: { background: '#fef2f2', borderLeft: '4px solid #e11d48', color: '#991b1b' },
  card: {
    background: '#fff',
    borderRadius: 20,
    border: '1px solid #e2e8f0',
    padding: '24px 28px',
    marginBottom: 20,
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
  },
  cardTitle: { fontSize: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 },
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 },
  formGroup: { display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 },
  label: { fontSize: 12, fontWeight: 600, color: '#475569' },
  input: {
    background: '#f1f5f9',
    border: '1px solid #e2e8f0',
    borderRadius: 14,
    padding: '10px 14px',
    fontSize: 13,
    fontFamily: 'inherit',
    color: '#0f172a',
  },
  textarea: {
    background: '#f1f5f9',
    border: '1px solid #e2e8f0',
    borderRadius: 14,
    padding: '10px 14px',
    fontSize: 13,
    fontFamily: 'inherit',
    color: '#0f172a',
    resize: 'vertical',
    width: '100%',
    boxSizing: 'border-box',
  },
  sectionNote: { color: '#64748b', fontSize: 12 },
  serviceTable: { width: '100%', borderCollapse: 'collapse', marginTop: 12 },
  serviceTh: {
    textAlign: 'left',
    padding: '10px 8px 10px 0',
    fontWeight: 600,
    fontSize: 12,
    color: '#475569',
    borderBottom: '1px solid #e2e8f0',
  },
  serviceTd: { padding: '10px 8px 10px 0', borderBottom: '1px solid #e2e8f0' },
}
