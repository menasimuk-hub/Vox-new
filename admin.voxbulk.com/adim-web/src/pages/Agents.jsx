import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { apiFetch, apiUpload } from '../lib/api'

const emptyAgent = {
  name: '',
  slug: '',
  description: '',
  system_prompt: '',
  call_workflow: '',
  knowledge_file_ids: [],
  is_active: true,
}

function hasWorkflow(agent) {
  return Boolean(String(agent?.call_workflow || '').trim())
}

function isPlaceholderPrompt(prompt) {
  const text = String(prompt || '').trim().toLowerCase()
  if (!text) return true
  return text.includes('not configured')
}

function hasSystemPrompt(agent) {
  return !isPlaceholderPrompt(agent?.system_prompt)
}

export default function Agents() {
  const navigate = useNavigate()
  const location = useLocation()
  const { agentId } = useParams()
  const [agents, setAgents] = useState([])
  const [assignments, setAssignments] = useState([])
  const [orgs, setOrgs] = useState([])
  const [kbFiles, setKbFiles] = useState([])
  const [assignmentSearch, setAssignmentSearch] = useState('')
  const [orgsToAdd, setOrgsToAdd] = useState([])
  const [orgsToRemove, setOrgsToRemove] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [draft, setDraft] = useState(emptyAgent)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [kbUploading, setKbUploading] = useState(false)
  const [genPhase, setGenPhase] = useState('')
  const lastSyncedAgentId = useRef('')

  const isEditPage = Boolean(agentId) || location.pathname.endsWith('/new')
  const selected = useMemo(() => agents.find((a) => a.id === selectedId) || null, [agents, selectedId])
  const orgById = useMemo(() => Object.fromEntries(orgs.map((o) => [o.id, o])), [orgs])
  const assignmentsByAgent = useMemo(() => {
    const out = {}
    assignments.forEach((row) => {
      if (!row.agent_id || !row.org_id) return
      if (!out[row.agent_id]) out[row.agent_id] = []
      out[row.agent_id].push(row)
    })
    return out
  }, [assignments])

  const loadKb = async () => {
    const data = await apiFetch('/admin/knowledge-base')
    setKbFiles(data?.files || [])
  }

  const load = async () => {
    setMsg('')
    const [agentRows, orgRows] = await Promise.all([
      apiFetch('/admin/agents'),
      apiFetch('/admin/organisations?limit=500').catch(() => []),
    ])
    setAgents(agentRows?.agents || [])
    setAssignments(agentRows?.assignments || [])
    setOrgs(Array.isArray(orgRows) ? orgRows : [])
    await loadKb()

    if (agentId && agentId !== selectedId) {
      const found = agentRows?.agents?.find((a) => a.id === agentId)
      if (found) {
        setSelectedId(found.id)
        setDraft({ ...emptyAgent, ...found, knowledge_file_ids: found.knowledge_file_ids || [] })
      }
    } else if (!selectedId && !location.pathname.endsWith('/new') && agentRows?.agents?.[0]) {
      setSelectedId(agentRows.agents[0].id)
      setDraft({ ...emptyAgent, ...agentRows.agents[0], knowledge_file_ids: agentRows.agents[0].knowledge_file_ids || [] })
    }
  }

  useEffect(() => {
    load().catch((e) => setMsg(e?.message || 'Could not load agents'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selected?.id) return
    if (lastSyncedAgentId.current === selected.id) return
    lastSyncedAgentId.current = selected.id
    setDraft({ ...emptyAgent, ...selected, knowledge_file_ids: selected.knowledge_file_ids || [] })
  }, [selected])

  useEffect(() => {
    if (location.pathname.endsWith('/new')) {
      setSelectedId('')
      setDraft(emptyAgent)
      return
    }
    if (!agentId || !agents.length) return
    const found = agents.find((a) => a.id === agentId)
    if (found) {
      setSelectedId(found.id)
      setDraft({ ...emptyAgent, ...found, knowledge_file_ids: found.knowledge_file_ids || [] })
    }
  }, [agentId, agents, location.pathname])

  const setField = (field, value) => setDraft((s) => ({ ...s, [field]: value }))

  const assignedOrgNames = (agent) => {
    const rows = assignmentsByAgent[agent.id] || []
    if (!rows.length) return '-'
    return rows.map((row) => orgById[row.org_id]?.name || 'Organisation').join(', ')
  }

  const selectedOrgAssignments = useMemo(() => assignmentsByAgent[selectedId] || [], [assignmentsByAgent, selectedId])
  const selectedOrgIds = useMemo(() => selectedOrgAssignments.map((row) => row.org_id).filter(Boolean), [selectedOrgAssignments])
  const assignableOrgs = useMemo(() => {
    const assigned = new Set(selectedOrgAssignments.map((row) => row.org_id))
    const term = assignmentSearch.trim().toLowerCase()
    return orgs
      .filter((org) => !assigned.has(org.id))
      .filter((org) => !term || String(org.name || '').toLowerCase().includes(term))
      .slice(0, 20)
  }, [assignmentSearch, orgs, selectedOrgAssignments])

  const toggleKbFile = (fileId) => {
    setDraft((s) => {
      const ids = new Set(s.knowledge_file_ids || [])
      if (ids.has(fileId)) ids.delete(fileId)
      else ids.add(fileId)
      return { ...s, knowledge_file_ids: Array.from(ids) }
    })
  }

  const save = async () => {
    setBusy(true)
    setMsg('')
    try {
      const body = {
        name: draft.name,
        slug: draft.slug,
        description: draft.description,
        system_prompt: draft.system_prompt,
        call_workflow: draft.call_workflow,
        knowledge_file_ids: draft.knowledge_file_ids || [],
        is_active: draft.is_active,
      }
      const saved = selectedId
        ? await apiFetch(`/admin/agents/${selectedId}`, { method: 'PUT', body: JSON.stringify(body) })
        : await apiFetch('/admin/agents', { method: 'POST', body: JSON.stringify(body) })
      setSelectedId(saved.id)
      setMsg('Agent saved.')
      await load()
      navigate(`/ai/agents/${saved.id}/edit`)
    } catch (e) {
      setMsg(e?.message || 'Could not save agent')
    } finally {
      setBusy(false)
    }
  }

  const generationPayload = (rewrite) => ({
    description: String(draft.description || '').trim(),
    name: draft.name,
    knowledge_file_ids: draft.knowledge_file_ids || [],
    rewrite,
  })

  const generateWorkflow = async () => {
    const description = String(draft.description || '').trim()
    if (!description) {
      setMsg('Add a description first, then generate the call workflow.')
      return
    }
    const rewrite = hasWorkflow(draft)
    if (rewrite && !window.confirm('Replace the existing call workflow?')) {
      setMsg('Workflow generation cancelled.')
      return
    }
    setBusy(true)
    setGenPhase('workflow')
    setMsg('Generating call workflow with AI (reads your knowledge base files)...')
    try {
      const path = selectedId ? `/admin/agents/${selectedId}/generate-workflow` : '/admin/agents/generate-workflow'
      const generated = await apiFetch(path, { method: 'POST', body: JSON.stringify(generationPayload(rewrite)) })
      const workflow = generated.call_workflow || ''
      setDraft((s) => ({ ...s, call_workflow: workflow || s.call_workflow }))
      if (selectedId && workflow) {
        await apiFetch(`/admin/agents/${selectedId}`, {
          method: 'PUT',
          body: JSON.stringify({ call_workflow: workflow }),
        })
        setAgents((rows) => rows.map((a) => (a.id === selectedId ? { ...a, call_workflow: workflow } : a)))
      }
      setMsg('Call workflow generated. Check the Call workflow box below, then click 2. Generate prompt.')
    } catch (e) {
      if (e?.status === 409 && window.confirm(`${e.message}\n\nReplace anyway?`)) {
        const generated = await apiFetch(
          selectedId ? `/admin/agents/${selectedId}/generate-workflow` : '/admin/agents/generate-workflow',
          { method: 'POST', body: JSON.stringify(generationPayload(true)) },
        )
        setDraft((s) => ({ ...s, call_workflow: generated.call_workflow || s.call_workflow }))
        setMsg('Call workflow regenerated.')
      } else {
        setMsg(e?.message || 'Workflow generation failed')
      }
    } finally {
      setBusy(false)
      setGenPhase('')
    }
  }

  const generatePrompt = async () => {
    const description = String(draft.description || '').trim()
    const workflow = String(draft.call_workflow || '').trim()
    if (!description) {
      setMsg('Add a description first.')
      return
    }
    if (!workflow) {
      setMsg('Generate the call workflow first (step 1), or paste workflow text into the Call workflow field.')
      return
    }
    setBusy(true)
    setGenPhase('prompt')
    setMsg('Generating system prompt (30-60 seconds)...')
    const path = selectedId ? `/admin/agents/${selectedId}/generate-prompt` : '/admin/agents/generate-prompt'
    try {
      const generated = await apiFetch(path, {
        method: 'POST',
        body: JSON.stringify({
          ...generationPayload(true),
          call_workflow: workflow,
        }),
      })
      const prompt = String(generated?.system_prompt || '').trim()
      if (!prompt) {
        setMsg('AI returned an empty system prompt. Check DeepSeek under Integrations and try again.')
        return
      }
      setDraft((s) => ({ ...s, system_prompt: prompt }))
      if (selectedId) {
        await apiFetch(`/admin/agents/${selectedId}`, {
          method: 'PUT',
          body: JSON.stringify({ system_prompt: prompt, call_workflow: workflow }),
        })
        setAgents((rows) => rows.map((a) => (a.id === selectedId ? { ...a, system_prompt: prompt, call_workflow: workflow } : a)))
      }
      setMsg('System prompt generated. Review the System prompt field below, then Save agent.')
    } catch (e) {
      const detail = e?.data?.detail
      const extra = typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : ''
      setMsg(extra ? `${e?.message || 'Prompt generation failed'} — ${extra}` : e?.message || 'Prompt generation failed')
    } finally {
      setBusy(false)
      setGenPhase('')
    }
  }

  const uploadKb = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.md')) {
      setMsg('Only .md files are allowed.')
      return
    }
    setKbUploading(true)
    setMsg('')
    try {
      const form = new FormData()
      form.append('file', file)
      await apiUpload('/admin/knowledge-base/upload', form)
      setMsg(`Uploaded ${file.name}.`)
      await loadKb()
    } catch (e) {
      setMsg(e?.message || 'Upload failed')
    } finally {
      setKbUploading(false)
    }
  }

  const deleteKb = async (file) => {
    if (!window.confirm(`Delete "${file.original_filename}" from the library? Agents will lose this link.`)) return
    setBusy(true)
    try {
      await apiFetch(`/admin/knowledge-base/${file.id}`, { method: 'DELETE' })
      setDraft((s) => ({
        ...s,
        knowledge_file_ids: (s.knowledge_file_ids || []).filter((id) => id !== file.id),
      }))
      await loadKb()
      setMsg('Knowledge base file deleted.')
    } catch (e) {
      setMsg(e?.message || 'Could not delete file')
    } finally {
      setBusy(false)
    }
  }

  const setAgentOrganisationAssignments = async (nextOrgIds, successMessage) => {
    if (!selectedId) {
      setMsg('Save the agent first, then assign organisations.')
      return
    }
    setBusy(true)
    try {
      const result = await apiFetch(`/admin/agents/${selectedId}/organisation-assignments`, {
        method: 'PUT',
        body: JSON.stringify({ org_ids: nextOrgIds }),
      })
      setAssignments((rows) => [
        ...rows.filter((row) => !(row.agent_id === selectedId && row.org_id)),
        ...((result?.assignments || []).map((row) => ({ ...row, agent_id: selectedId }))),
      ])
      setOrgsToAdd([])
      setOrgsToRemove([])
      setMsg(successMessage || 'Organisation assignments saved.')
      await load()
    } catch (e) {
      setMsg(e?.message || 'Could not save organisation assignments')
    } finally {
      setBusy(false)
    }
  }

  const removeOrgAssignment = async (assignment) => {
    const previous = assignments
    setAssignments((rows) => rows.filter((row) => row.id !== assignment.id))
    setBusy(true)
    try {
      await apiFetch(`/admin/agents/assignments/${assignment.id}`, { method: 'DELETE' })
      setMsg('Organisation removed.')
    } catch (e) {
      setAssignments(previous)
      setMsg(e?.message || 'Could not remove organisation')
    } finally {
      setBusy(false)
    }
  }

  const newAgent = () => {
    setSelectedId('')
    setDraft(emptyAgent)
    navigate('/ai/agents/new')
  }

  const duplicateAgent = async (agent) => {
    setBusy(true)
    try {
      const copy = {
        name: `${agent.name} Copy`,
        slug: `${agent.slug || 'agent'}-copy-${Date.now().toString().slice(-5)}`,
        description: agent.description,
        system_prompt: agent.system_prompt,
        call_workflow: agent.call_workflow,
        knowledge_file_ids: agent.knowledge_file_ids || [],
        is_active: false,
      }
      const saved = await apiFetch('/admin/agents', { method: 'POST', body: JSON.stringify(copy) })
      setMsg('Agent duplicated.')
      await load()
      navigate(`/ai/agents/${saved.id}/edit`)
    } catch (e) {
      setMsg(e?.message || 'Could not duplicate agent')
    } finally {
      setBusy(false)
    }
  }

  const deleteAgent = async (agent) => {
    if (!window.confirm(`Delete agent "${agent.name}"? This cannot be undone.`)) return
    setBusy(true)
    try {
      await apiFetch(`/admin/agents/${agent.id}`, { method: 'DELETE' })
      setMsg('Agent deleted.')
      setSelectedId('')
      setDraft(emptyAgent)
      await load()
      navigate('/ai/agents')
    } catch (e) {
      setMsg(e?.message || 'Could not delete agent')
    } finally {
      setBusy(false)
    }
  }

  const toggleFreeze = async (agent) => {
    setBusy(true)
    try {
      await apiFetch(`/admin/agents/${agent.id}/${agent.is_active ? 'deactivate' : 'activate'}`, { method: 'POST' })
      setMsg(agent.is_active ? 'Agent frozen.' : 'Agent activated.')
      await load()
    } catch (e) {
      setMsg(e?.message || 'Could not update agent status')
    } finally {
      setBusy(false)
    }
  }

  if (!isEditPage) {
    return (
      <>
        <div className='pageTop'>
          <div>
            <h1>Agents</h1>
            <p>Create voice agents, attach knowledge base files, and assign them to organisations.</p>
          </div>
          <div className='actions'>
            <button type='button' className='btn soft' onClick={() => load().catch((e) => setMsg(e.message))} disabled={busy}>
              {busy ? 'Working...' : 'Reload'}
            </button>
            <button type='button' className='btn primary' onClick={newAgent}>
              New agent
            </button>
          </div>
        </div>
        {msg ? <div className='note' style={{ marginBottom: 16 }}>{msg}</div> : null}

        <section className='card' style={{ marginBottom: 16 }}>
          <div className='cardHead'>
            <h3>Knowledge base library</h3>
            <span className='pill p-cyan'>{kbFiles.length} files</span>
          </div>
          <div className='cardBody stack'>
            <p className='muted'>Upload Markdown files (.md, max 2 MB each). All agents can attach files from this library.</p>
            <div className='actions'>
              <label className='btn soft' style={{ cursor: 'pointer' }}>
                {kbUploading ? 'Uploading...' : 'Upload .md file'}
                <input type='file' accept='.md,text/markdown' hidden onChange={uploadKb} disabled={kbUploading} />
              </label>
            </div>
            <div className='tableWrap'>
              <table className='table'>
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Server path</th>
                    <th>Size</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {kbFiles.map((file) => (
                    <tr key={file.id}>
                      <td>{file.original_filename}</td>
                      <td className='muted' style={{ fontSize: 12 }}>{file.storage_path}</td>
                      <td>{Math.round((file.size_bytes || 0) / 1024)} KB</td>
                      <td>
                        <button type='button' className='btn soft' onClick={() => deleteKb(file)} disabled={busy}>
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!kbFiles.length ? (
                    <tr>
                      <td colSpan={4} className='muted'>
                        No knowledge base files yet.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section className='card'>
          <div className='cardHead'>
            <h3>All agents</h3>
            <span className='pill p-cyan'>{agents.length}</span>
          </div>
          <div className='cardBody'>
            <div className='tableWrap'>
              <table className='table'>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Organisations</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {agents.map((agent) => (
                    <tr key={agent.id}>
                      <td>
                        <strong>{agent.name}</strong>
                        <div className='muted' style={{ fontSize: 12 }}>
                          {agent.slug}
                        </div>
                      </td>
                      <td>{assignedOrgNames(agent)}</td>
                      <td>
                        <span className={`pill ${agent.is_active ? 'p-green' : 'p-amber'}`}>{agent.is_active ? 'Active' : 'Frozen'}</span>
                      </td>
                      <td>
                        <div className='actions'>
                          <button type='button' className='btn soft' onClick={() => duplicateAgent(agent)} disabled={busy}>
                            Duplicate
                          </button>
                          <button type='button' className='btn soft' onClick={() => navigate(`/ai/agents/${agent.id}/edit`)}>
                            Edit
                          </button>
                          <button type='button' className='btn soft' onClick={() => toggleFreeze(agent)} disabled={busy}>
                            {agent.is_active ? 'Freeze' : 'Unfreeze'}
                          </button>
                          <button type='button' className='btn soft' onClick={() => deleteAgent(agent)} disabled={busy}>
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {!agents.length ? (
                    <tr>
                      <td colSpan={4} className='muted'>
                        No agents yet.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </>
    )
  }

  const kbSelectedCount = (draft.knowledge_file_ids || []).length

  return (
    <div className='agentEditPage'>
      <header className='agentEditHero'>
        <div>
          <h1>{selectedId ? draft.name || 'Edit agent' : 'Create agent'}</h1>
          <p>Describe the role, generate prompts with AI, attach knowledge files, and assign organisations.</p>
          <div className='agentEditHeroMeta'>
            <span className={`pill ${draft.is_active ? 'p-green' : 'p-amber'}`}>{draft.is_active ? 'Active' : 'Frozen'}</span>
            {draft.slug ? <span className='pill p-cyan'>{draft.slug}</span> : null}
            <span className='pill'>{kbSelectedCount} KB file{kbSelectedCount === 1 ? '' : 's'}</span>
            <span className='pill'>{selectedOrgAssignments.length} org{selectedOrgAssignments.length === 1 ? '' : 's'}</span>
          </div>
        </div>
        <div className='actions'>
          <button type='button' className='btn soft' onClick={() => navigate('/ai/agents')}>
            Back to list
          </button>
          <button type='button' className='btn primary' onClick={save} disabled={busy || !draft.name?.trim()}>
            {busy ? 'Saving...' : 'Save agent'}
          </button>
        </div>
      </header>
      {msg ? <div className='note' style={{ marginBottom: 20 }}>{msg}</div> : null}

      <div className='agentEditStack'>
        <section className='card'>
          <div className='cardHead'>
            <h3>Basics</h3>
          </div>
          <div className='cardBody stack'>
            <div className='agentFieldGrid3'>
              <label>
                <span className='label'>Name</span>
                <input className='input' value={draft.name || ''} onChange={(e) => setField('name', e.target.value)} placeholder='Vox Sales' />
              </label>
              <label>
                <span className='label'>Slug</span>
                <input className='input' value={draft.slug || ''} onChange={(e) => setField('slug', e.target.value)} placeholder='vox-sales' />
              </label>
              <label className='agentActiveToggle'>
                <input type='checkbox' checked={Boolean(draft.is_active)} onChange={(e) => setField('is_active', e.target.checked)} />
                <span>Agent is active</span>
              </label>
            </div>
            <label>
              <span className='label'>What should this agent do?</span>
              <textarea
                className='input'
                style={{ minHeight: 96 }}
                value={draft.description || ''}
                onChange={(e) => setField('description', e.target.value)}
                placeholder='e.g. Qualify inbound leads, explain VOXBULK, collect company name and email.'
              />
            </label>
            <div className='agentEditToolbar'>
              <p>
                Step 1: workflow from description + knowledge base. Step 2: system prompt from that workflow.
                DeepSeek must be configured under Integrations.
              </p>
              <div className='actions'>
                <button
                  type='button'
                  className='btn soft'
                  onClick={generateWorkflow}
                  disabled={busy || !String(draft.description || '').trim()}
                >
                  {genPhase === 'workflow' ? 'Generating workflow...' : hasWorkflow(draft) ? 'Regenerate workflow' : '1. Generate workflow'}
                </button>
                <button
                  type='button'
                  className='btn primary'
                  onClick={generatePrompt}
                  disabled={busy || !String(draft.description || '').trim() || !hasWorkflow(draft)}
                >
                  {genPhase === 'prompt' ? 'Generating prompt...' : hasSystemPrompt(draft) ? 'Regenerate prompt' : '2. Generate prompt'}
                </button>
              </div>
              {!hasWorkflow(draft) ? (
                <p className='muted' style={{ margin: '10px 0 0', fontSize: 12 }}>
                  Step 2 unlocks when the Call workflow field (below) has text.
                </p>
              ) : null}
            </div>
          </div>
        </section>

        <div className='agentEditRow2'>
          <section className='card'>
            <div className='cardHead'>
              <h3>Call workflow</h3>
              <span className='pill p-cyan'>Step 1</span>
            </div>
            <div className='cardBody'>
              <textarea
                className='input agentPromptArea'
                value={draft.call_workflow || ''}
                onChange={(e) => setField('call_workflow', e.target.value)}
                placeholder='Step-by-step call flow: greeting, questions, handoff, close...'
              />
            </div>
          </section>
          <section className='card'>
            <div className='cardHead'>
              <h3>System prompt</h3>
              <span className='pill p-cyan'>Step 2</span>
            </div>
            <div className='cardBody'>
              <textarea
                className='input agentPromptArea'
                value={draft.system_prompt || ''}
                onChange={(e) => setField('system_prompt', e.target.value)}
                placeholder='Generated or hand-written instructions for the agent...'
              />
            </div>
          </section>
        </div>

        <div className='agentEditRow2'>
          <section className='card'>
            <div className='cardHead'>
              <h3>Knowledge base</h3>
              <span className='pill p-cyan'>{kbSelectedCount} selected</span>
            </div>
            <div className='cardBody stack'>
              <p className='muted' style={{ margin: 0, fontSize: 13 }}>
                Upload .md files on the agents list page. Click a file to attach it to this agent.
              </p>
              <div className='agentKbPanel'>
                {kbFiles.length ? (
                  kbFiles.map((file) => {
                    const selected = (draft.knowledge_file_ids || []).includes(file.id)
                    return (
                      <div
                        key={file.id}
                        role='button'
                        tabIndex={0}
                        className={`agentKbItem${selected ? ' is-selected' : ''}`}
                        onClick={() => toggleKbFile(file.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            toggleKbFile(file.id)
                          }
                        }}
                      >
                        <input type='checkbox' checked={selected} readOnly tabIndex={-1} />
                        <span>
                          <strong>{file.original_filename}</strong>
                          <div className='muted'>{file.storage_path}</div>
                        </span>
                      </div>
                    )
                  })
                ) : (
                  <p className='muted' style={{ margin: 0 }}>No files yet. Upload on the agents list.</p>
                )}
              </div>
            </div>
          </section>

          <section className='card'>
            <div className='cardHead'>
              <h3>Organisations</h3>
              <span className='pill p-cyan'>{selectedOrgAssignments.length} assigned</span>
            </div>
            <div className='cardBody stack'>
              <div>
                <span className='label'>Currently assigned</span>
                <div className='agentOrgAssigned'>
                  {selectedOrgAssignments.length ? (
                    selectedOrgAssignments.map((row) => {
                      const org = orgById[row.org_id]
                      return (
                        <div key={row.id} className='agentOrgRow'>
                          <label style={{ display: 'flex', alignItems: 'center', gap: 8, margin: 0 }}>
                            <input
                              type='checkbox'
                              checked={orgsToRemove.includes(row.org_id)}
                              onChange={() =>
                                setOrgsToRemove((ids) =>
                                  ids.includes(row.org_id) ? ids.filter((x) => x !== row.org_id) : [...ids, row.org_id],
                                )
                              }
                            />
                            <strong>{org?.name || 'Unknown'}</strong>
                          </label>
                          <button type='button' className='btn soft' onClick={() => removeOrgAssignment(row)} disabled={busy}>
                            Remove
                          </button>
                        </div>
                      )
                    })
                  ) : (
                    <p className='muted' style={{ margin: 0, fontSize: 13 }}>No organisations assigned yet.</p>
                  )}
                </div>
                {selectedOrgAssignments.length ? (
                  <div className='actions' style={{ marginTop: 10 }}>
                    <button
                      type='button'
                      className='btn soft'
                      onClick={() =>
                        setAgentOrganisationAssignments(
                          selectedOrgIds.filter((id) => !orgsToRemove.includes(id)),
                          'Removed selected organisations.',
                        )
                      }
                      disabled={busy || !orgsToRemove.length}
                    >
                      Remove selected
                    </button>
                  </div>
                ) : null}
              </div>

              <div>
                <span className='label'>Add organisations</span>
                <input
                  className='input'
                  style={{ width: '100%', minWidth: 0, marginBottom: 10 }}
                  value={assignmentSearch}
                  onChange={(e) => setAssignmentSearch(e.target.value)}
                  placeholder='Search by name...'
                />
                <div className='agentOrgPicker'>
                  {assignableOrgs.length ? (
                    assignableOrgs.map((org) => (
                      <label key={org.id}>
                        <input
                          type='checkbox'
                          checked={orgsToAdd.includes(org.id)}
                          onChange={() =>
                            setOrgsToAdd((ids) => (ids.includes(org.id) ? ids.filter((x) => x !== org.id) : [...ids, org.id]))
                          }
                          disabled={!selectedId}
                        />
                        {org.name}
                      </label>
                    ))
                  ) : (
                    <span className='muted' style={{ fontSize: 13 }}>No more organisations to add, or save the agent first.</span>
                  )}
                </div>
                <div className='actions' style={{ marginTop: 12 }}>
                  <button
                    type='button'
                    className='btn primary'
                    onClick={() => setAgentOrganisationAssignments([...selectedOrgIds, ...orgsToAdd])}
                    disabled={!selectedId || busy || !orgsToAdd.length}
                  >
                    Add selected organisations
                  </button>
                </div>
                {!selectedId ? (
                  <p className='muted' style={{ margin: '10px 0 0', fontSize: 12 }}>Save the agent before assigning organisations.</p>
                ) : null}
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

