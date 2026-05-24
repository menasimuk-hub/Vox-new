import React, { useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'

export default function AgentEditPage({ agentId, onClose }) {
  const [agent, setAgent] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [knowledgeFiles, setKnowledgeFiles] = useState([])
  const [generatedPrompt, setGeneratedPrompt] = useState('')

  const SERVICE_CATALOG = [
    { id: 'survey', name: 'Survey', icon: 'ti ti-clipboard-list' },
    { id: 'interview', name: 'Interview', icon: 'ti ti-microphone' },
    { id: 'lead_sales', name: 'Lead / Sales', icon: 'ti ti-bolt' },
  ]

  // Load agent if editing
  useEffect(() => {
    if (agentId === 'new') {
      setAgent({
        name: '',
        slug: '',
        description: '',
        voice_label: '',
        voice_type_label: '',
        telnyx_assistant_id: '',
        base_role: '',
        service_survey_role: '',
        service_interview_role: '',
        service_lead_sales_role: '',
        opening_disclosure_template: 'Hello, this is {agent_name}, the AI assistant calling from {company_name}. This call is recorded for quality and service purposes.',
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
      })
      setLoading(false)
    } else {
      apiFetch(`/admin/agents/${agentId}`)
        .then(data => setAgent(data))
        .catch(e => setMsg(e?.message || 'Failed to load agent'))
        .finally(() => setLoading(false))
    }
  }, [agentId])

  const setField = (field, value) => {
    setAgent(s => ({ ...s, [field]: value }))
  }

  const generateAIPrompt = async () => {
    const serviceSum = document.getElementById('aiServiceSummary')?.value || ''
    const audience = document.getElementById('aiTargetAudience')?.value || ''
    const tone = document.getElementById('aiTone')?.value || 'Friendly and professional'
    const rules = document.getElementById('aiRules')?.value || ''

    if (!serviceSum.trim()) {
      setMsg('Please fill in the service summary')
      return
    }

    setSaving(true)
    try {
      // Call backend DeepSeek prompt generator
      const result = await apiFetch('/admin/agents/generate-prompt-legacy', {
        method: 'POST',
        body: JSON.stringify({
          description: serviceSum,
          name: agent.name || 'AI Agent',
          agent_name: agent.voice_label || agent.name || 'the assistant',
          knowledge_file_ids: knowledgeFiles.filter(f => f.attached).map(f => f.id),
        }),
      })

      setGeneratedPrompt(result?.system_prompt || '')
      setMsg('AI prompt generated! Review and adapt to Base role if needed.')
    } catch (e) {
      setMsg(e?.message || 'Failed to generate prompt')
    } finally {
      setSaving(false)
    }
  }

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

    setSaving(true)
    try {
      if (agent.id) {
        await apiFetch(`/admin/agents/${agent.id}`, {
          method: 'PUT',
          body: JSON.stringify(agent),
        })
        setMsg('Agent updated!')
      } else {
        const created = await apiFetch('/admin/agents', {
          method: 'POST',
          body: JSON.stringify(agent),
        })
        setAgent(created)
        setMsg('Agent created!')
      }
      setTimeout(onClose, 1000)
    } catch (e) {
      setMsg(e?.message || 'Failed to save agent')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div style={{ padding: 32, textAlign: 'center' }}>Loading...</div>
  if (!agent) return <div style={{ padding: 32, textAlign: 'center', color: '#e11d48' }}>Agent not found</div>

  const enabledServices = SERVICE_CATALOG.filter(s => agent[`supports_${s.id}`])
  const kbCount = knowledgeFiles.filter(f => f.attached).length

  return (
    <div style={styles.container}>
      <div style={styles.topbar}>
        <div style={styles.topbarLeft}>
          <button
            onClick={onClose}
            style={{ ...styles.backBtn, background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, color: '#475569', fontSize: 13, fontWeight: 500 }}
          >
            <i className="ti ti-arrow-left"></i> Agents
          </button>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#0f172a' }}>
              {agent.id ? 'Edit agent' : 'Create agent'}
            </div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>
              Configure voice, prompts, and service assignment
            </div>
          </div>
        </div>
        <div style={styles.headerActions}>
          <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
            <div style={styles.stat}>
              <i className="ti ti-file-text"></i>
              <span>{kbCount}</span> KB files
            </div>
            <div style={styles.stat}>
              <i className="ti ti-building"></i>
              <span>{enabledServices.length}</span> services
            </div>
          </div>
          <button
            onClick={saveAgent}
            disabled={saving}
            style={{ ...styles.btn, ...styles.btnPrimary }}
          >
            <i className="ti ti-device-floppy"></i> {saving ? 'Saving...' : 'Save agent'}
          </button>
        </div>
      </div>

      {msg && (
        <div style={{ ...styles.msg, margin: '0 32px 16px', padding: '12px 16px', borderRadius: 8 }}>
          {msg}
        </div>
      )}

      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '0 32px' }}>
        {/* BASICS */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardTitle}>
              <i className="ti ti-user-circle" style={{ color: '#2563eb' }}></i> Basics
            </div>
          </div>
          <div style={styles.grid2}>
            <div style={styles.formGroup}>
              <label style={styles.label}>
                <i className="ti ti-forms"></i> Agent name
              </label>
              <input
                value={agent.name}
                onChange={(e) => setField('name', e.target.value)}
                style={styles.input}
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>
                <i className="ti ti-link"></i> Slug identifier
              </label>
              <input
                value={agent.slug}
                onChange={(e) => setField('slug', e.target.value)}
                style={styles.input}
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>
                <i className="ti ti-id"></i> Voice label
              </label>
              <input
                value={agent.voice_label || ''}
                onChange={(e) => setField('voice_label', e.target.value)}
                placeholder="Sophie, James, etc."
                style={styles.input}
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>
                <i className="ti ti-microphone"></i> Voice type
              </label>
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
              <label style={styles.label}>
                <i className="ti ti-info-circle"></i> Description / purpose
              </label>
              <textarea
                value={agent.description || ''}
                onChange={(e) => setField('description', e.target.value)}
                style={{ ...styles.textarea }}
                rows="3"
              />
            </div>
          </div>
        </div>

        {/* TELNYX & VOICE */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardTitle}>
              <i className="ti ti-microphone" style={{ color: '#d97706' }}></i> Voice identity & Telnyx
            </div>
          </div>
          <div style={styles.grid2}>
            <div style={styles.formGroup}>
              <label style={styles.label}>
                <i className="ti ti-id-badge"></i> Telnyx Assistant ID
              </label>
              <input
                value={agent.telnyx_assistant_id || ''}
                onChange={(e) => setField('telnyx_assistant_id', e.target.value)}
                placeholder="asst_..."
                style={styles.input}
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>
                <i className="ti ti-toggle-left"></i> Is active
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={agent.is_active}
                  onChange={(e) => setField('is_active', e.target.checked)}
                />
                {agent.is_active ? 'Active' : 'Frozen'}
              </label>
            </div>
            <div style={{ ...styles.formGroup, gridColumn: '1 / -1' }}>
              <label style={styles.label}>
                <i className="ti ti-shield-check"></i> Opening disclosure template
              </label>
              <textarea
                value={agent.opening_disclosure_template || ''}
                onChange={(e) => setField('opening_disclosure_template', e.target.value)}
                style={styles.textarea}
                rows="3"
              />
              <div style={styles.sectionNote}>Use {'{agent_name}'} and {'{company_name}'} as placeholders</div>
            </div>
          </div>
        </div>

        {/* KNOWLEDGE BASE */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardTitle}>
              <i className="ti ti-file-text" style={{ color: '#16a34a' }}></i> Knowledge Base Files
            </div>
            <div style={styles.stat}>{kbCount} attached</div>
          </div>
          <div style={styles.kbUploadArea}>
            <i className="ti ti-cloud-upload" style={{ fontSize: 28, color: '#94a3b8' }}></i>
            <div>
              <div style={{ fontWeight: 600, color: '#334155', marginBottom: 4 }}>Drop knowledge files here</div>
              <div style={{ fontSize: 12, color: '#64748b' }}>
                Markdown, PDF, or text files — used to enhance generated prompts
              </div>
            </div>
            <input
              type="file"
              multiple
              accept=".md,.txt,.pdf"
              onChange={async (e) => {
                const files = e.currentTarget.files
                if (!files?.length) return
                setSaving(true)
                try {
                  for (const file of files) {
                    const form = new FormData()
                    form.append('file', file)
                    const result = await apiFetch(`/admin/agents/${agent.id || 'temp'}/knowledge-files`, {
                      method: 'POST',
                      body: form,
                    })
                    setKnowledgeFiles(s => [...s.filter(f => f.id !== result.id), result])
                  }
                  setMsg('Files uploaded!')
                } catch (err) {
                  setMsg(err?.message || 'Upload failed')
                } finally {
                  setSaving(false)
                }
              }}
              style={{ display: 'none' }}
            />
          </div>
          {kbCount > 0 && (
            <div style={{ marginTop: 16 }}>
              {knowledgeFiles.filter(f => f.attached).map((file) => (
                <div key={file.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid #e2e8f0' }}>
                  <i className="ti ti-file" style={{ color: '#64748b' }}></i>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, color: '#0f172a' }}>{file.name}</div>
                    <div style={{ fontSize: 11, color: '#94a3b8' }}>{file.size_kb}KB</div>
                  </div>
                  <button
                    onClick={async () => {
                      try {
                        await apiFetch(`/admin/agents/${agent.id}/knowledge-files/${file.id}`, { method: 'DELETE' })
                        setKnowledgeFiles(s => s.filter(f => f.id !== file.id))
                      } catch (err) {
                        setMsg(err?.message)
                      }
                    }}
                    style={{ background: 'none', border: 'none', color: '#e11d48', cursor: 'pointer' }}
                  >
                    <i className="ti ti-trash"></i>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* AI PROMPT GENERATION */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardTitle}>
              <i className="ti ti-wand" style={{ color: '#5f4be3' }}></i> AI prompt generation
            </div>
          </div>
          <div style={styles.grid2}>
            <div style={styles.formGroup}>
              <label style={styles.label}>
                <i className="ti ti-bulb"></i> Service summary
              </label>
              <textarea
                id="aiServiceSummary"
                style={styles.textarea}
                rows="3"
                placeholder="Run short outbound AI survey calls for customer feedback..."
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>
                <i className="ti ti-users"></i> Target audience
              </label>
              <input
                id="aiTargetAudience"
                placeholder="Customers / patients / leads"
                style={styles.input}
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>
                <i className="ti ti-message"></i> Tone
              </label>
              <select id="aiTone" style={styles.input}>
                <option>Friendly and professional</option>
                <option>Warm and calm</option>
                <option>Short and direct</option>
                <option>Polite and formal</option>
              </select>
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>
                <i className="ti ti-list"></i> Must ask / must avoid
              </label>
              <textarea
                id="aiRules"
                style={styles.textarea}
                rows="2"
                placeholder="Must say the call is recorded. Do not ask 'is this a good time'..."
              />
            </div>
            <div style={{ ...styles.formGroup, gridColumn: '1 / -1' }}>
              <label style={styles.label}>
                <i className="ti ti-rocket"></i> Generated base prompt
              </label>
              <textarea
                value={generatedPrompt}
                onChange={(e) => setGeneratedPrompt(e.target.value)}
                style={styles.textarea}
                rows="10"
                placeholder="Click Generate to create..."
              />
            </div>
          </div>
          <div style={styles.sectionNote}>Fill the fields above, then generate a clean base prompt you can edit</div>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 14 }}>
            <button
              onClick={() => setGeneratedPrompt('')}
              style={styles.btn}
              disabled={saving}
            >
              <i className="ti ti-trash"></i> Clear
            </button>
            <button
              onClick={generateAIPrompt}
              style={{ ...styles.btn, ...styles.btnPrimary }}
              disabled={saving}
            >
              <i className="ti ti-wand"></i> {saving ? 'Generating...' : 'Generate AI prompt'}
            </button>
          </div>
        </div>

        {/* SERVICE ASSIGNMENT */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardTitle}>
              <i className="ti ti-list-check" style={{ color: '#5f4be3' }}></i> Service assignment
            </div>
          </div>
          <div style={{ overflowX: 'auto' }}>
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
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontWeight: 500 }}>
                        <i className={svc.icon}></i> {svc.name}
                      </div>
                    </td>
                    <td style={styles.serviceTd}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <input
                          type="checkbox"
                          checked={agent[`supports_${svc.id}`] || false}
                          onChange={(e) => setField(`supports_${svc.id}`, e.target.checked)}
                        />
                      </label>
                    </td>
                    <td style={styles.serviceTd}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <input
                          type="checkbox"
                          checked={agent[`is_default_${svc.id}`] || false}
                          onChange={(e) => setField(`is_default_${svc.id}`, e.target.checked)}
                          disabled={!agent[`supports_${svc.id}`]}
                        />
                      </label>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* PROMPT LAYERS */}
        <div style={styles.grid2}>
          <div style={styles.card}>
            <div style={styles.cardHeader}>
              <div style={styles.cardTitle}>
                <i className="ti ti-sparkles" style={{ color: '#5f4be3' }}></i> Prompt layers
              </div>
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Base role</label>
              <textarea
                value={agent.base_role || ''}
                onChange={(e) => setField('base_role', e.target.value)}
                style={styles.textarea}
                rows="4"
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Survey role override</label>
              <textarea
                value={agent.service_survey_role || ''}
                onChange={(e) => setField('service_survey_role', e.target.value)}
                style={styles.textarea}
                rows="3"
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Interview role override</label>
              <textarea
                value={agent.service_interview_role || ''}
                onChange={(e) => setField('service_interview_role', e.target.value)}
                style={styles.textarea}
                rows="3"
              />
            </div>
          </div>

          <div style={styles.card}>
            <div style={styles.cardHeader}>
              <div style={styles.cardTitle}>
                <i className="ti ti-settings" style={{ color: '#e11d48' }}></i> Behavior settings
              </div>
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Interruption handling</label>
              <textarea
                value={agent.interruption_behavior_notes || ''}
                onChange={(e) => setField('interruption_behavior_notes', e.target.value)}
                style={styles.textarea}
                rows="3"
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Opt-out handling</label>
              <textarea
                value={agent.opt_out_policy_notes || ''}
                onChange={(e) => setField('opt_out_policy_notes', e.target.value)}
                style={styles.textarea}
                rows="3"
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>Retry policy</label>
              <textarea
                value={agent.retry_policy_notes || ''}
                onChange={(e) => setField('retry_policy_notes', e.target.value)}
                style={styles.textarea}
                rows="2"
              />
            </div>
          </div>
        </div>

        {/* SAVE */}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 28, marginBottom: 28 }}>
          <button onClick={onClose} style={styles.btn}>
            <i className="ti ti-x"></i> Cancel
          </button>
          <button
            onClick={saveAgent}
            disabled={saving}
            style={{ ...styles.btn, ...styles.btnPrimary }}
          >
            <i className="ti ti-device-floppy"></i> {saving ? 'Saving...' : 'Save agent'}
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
    backdropFilter: 'blur(2px)',
  },
  topbarLeft: { display: 'flex', alignItems: 'center', gap: 24 },
  backBtn: { color: '#475569', textDecoration: 'none', fontSize: 13, fontWeight: 500 },
  headerActions: { display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' },
  stat: { fontSize: 12, color: '#64748b', display: 'flex', alignItems: 'center', gap: 6, background: '#f1f5f9', padding: '4px 12px', borderRadius: 20 },
  btn: { display: 'inline-flex', alignItems: 'center', gap: 8, padding: '8px 18px', borderRadius: 40, fontWeight: 600, fontSize: 13, border: '1px solid #e2e8f0', cursor: 'pointer', background: '#fff', color: '#0f172a' },
  btnPrimary: { background: '#2563eb', color: '#fff', borderColor: '#2563eb' },
  msg: { background: '#fef2f2', borderLeft: '4px solid #e11d48', color: '#991b1b' },
  card: { background: '#fff', borderRadius: 20, border: '1px solid #e2e8f0', padding: '24px 28px', marginBottom: 28, boxShadow: '0 1px 3px rgba(0,0,0,0.05)' },
  cardHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap' },
  cardTitle: { fontSize: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 10 },
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 },
  formGroup: { display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 18 },
  label: { fontSize: 12, fontWeight: 600, color: '#475569', display: 'flex', alignItems: 'center', gap: 6 },
  input: { background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 14, padding: '10px 14px', fontSize: 13, fontFamily: 'inherit', color: '#0f172a' },
  textarea: { background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 14, padding: '10px 14px', fontSize: 13, fontFamily: 'inherit', color: '#0f172a', resize: 'vertical', minHeight: 80 },
  sectionNote: { color: '#64748b', fontSize: 12, marginTop: 8 },
  serviceTable: { width: '100%', borderCollapse: 'collapse' },
  serviceTh: { textAlign: 'left', padding: '14px 8px 14px 0', fontWeight: 600, fontSize: 12, color: '#475569', borderBottom: '1px solid #e2e8f0' },
  serviceTd: { padding: '14px 8px 14px 0', borderBottom: '1px solid #e2e8f0', verticalAlign: 'middle' },
  kbUploadArea: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, padding: '24px', borderRadius: 14, border: '2px dashed #cbd5e1', background: '#f8fafc', textAlign: 'center', cursor: 'pointer', transition: 'all 0.2s' },
}
