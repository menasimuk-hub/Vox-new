import React, { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const emptyAgent = {
  name: '',
  slug: '',
  description: '',
  business_type: '',
  category_id: '',
  system_prompt: '',
  conversation_style: 'Warm, natural, concise, human, not scripted. British English.',
  default_model: 'gpt-realtime-1.5',
  default_voice: 'en-GB-AbbiNeural',
  use_azure_tts: true,
  use_azure_stt: true,
  allow_lookup_tool: true,
  allow_booking_tool: false,
  allow_reschedule_tool: false,
  allow_cancel_tool: false,
  is_active: true,
  is_template: false,
}

export default function Agents() {
  const navigate = useNavigate()
  const location = useLocation()
  const { agentId } = useParams()
  const [agents, setAgents] = useState([])
  const [assignments, setAssignments] = useState([])
  const [orgs, setOrgs] = useState([])
  const [categories, setCategories] = useState([])
  const [assignmentSearch, setAssignmentSearch] = useState('')
  const [orgsToAdd, setOrgsToAdd] = useState([])
  const [orgsToRemove, setOrgsToRemove] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [draft, setDraft] = useState(emptyAgent)
  const [previewInput, setPreviewInput] = useState('Hi, I need to move my appointment.')
  const [previewOrgId, setPreviewOrgId] = useState('')
  const [previewResult, setPreviewResult] = useState(null)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const isEditPage = Boolean(agentId) || location.pathname.endsWith('/new')
  const selected = useMemo(() => agents.find((a) => a.id === selectedId) || null, [agents, selectedId])
  const orgById = useMemo(() => Object.fromEntries(orgs.map((o) => [o.id, o])), [orgs])
  const categoryById = useMemo(() => Object.fromEntries(categories.map((c) => [c.id, c])), [categories])
  const assignmentsByAgent = useMemo(() => {
    const out = {}
    assignments.forEach((row) => {
      if (!row.agent_id) return
      if (!out[row.agent_id]) out[row.agent_id] = []
      out[row.agent_id].push(row)
    })
    return out
  }, [assignments])

  const load = async () => {
    setMsg('')
    const [agentRows, orgRows, categoryRows] = await Promise.all([
      apiFetch('/admin/agents'),
      apiFetch('/admin/organisations?limit=500').catch(() => []),
      apiFetch('/admin/categories').catch(() => []),
    ])
    setAgents(agentRows?.agents || [])
    setAssignments(agentRows?.assignments || [])
    setOrgs(Array.isArray(orgRows) ? orgRows : [])
    setCategories(Array.isArray(categoryRows) ? categoryRows : [])
    if (!previewOrgId && Array.isArray(orgRows) && orgRows[0]?.id) setPreviewOrgId(orgRows[0].id)
    if (agentId && agentId !== selectedId) {
      const found = agentRows?.agents?.find((a) => a.id === agentId)
      if (found) {
        setSelectedId(found.id)
        setDraft({ ...emptyAgent, ...found })
      }
    } else if (!selectedId && !location.pathname.endsWith('/new') && agentRows?.agents?.[0]) {
      setSelectedId(agentRows.agents[0].id)
      setDraft({ ...emptyAgent, ...agentRows.agents[0] })
    }
  }

  useEffect(() => {
    load().catch((e) => setMsg(e?.message || 'Could not load agents'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selected) setDraft({ ...emptyAgent, ...selected })
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
      setDraft({ ...emptyAgent, ...found })
    }
  }, [agentId, agents, location.pathname])

  const setField = (field, value) => setDraft((s) => ({ ...s, [field]: value }))

  const assignedLabel = (agent) => {
    const rows = assignmentsByAgent[agent.id] || []
    if (!rows.length) return 'Not assigned'
    return rows
      .map((row) => row.org_id ? orgById[row.org_id]?.name || 'Organisation' : categoryById[row.category_id]?.name || 'Business type')
      .join(', ')
  }
  const selectedAgentAssignments = useMemo(() => assignmentsByAgent[selectedId] || [], [assignmentsByAgent, selectedId])
  const selectedOrgAssignments = useMemo(() => selectedAgentAssignments.filter((row) => row.org_id), [selectedAgentAssignments])
  const selectedOrgIds = useMemo(() => selectedOrgAssignments.map((row) => row.org_id).filter(Boolean), [selectedOrgAssignments])
  const selectedCategoryAssignments = useMemo(() => selectedAgentAssignments.filter((row) => row.category_id), [selectedAgentAssignments])
  const assignableOrgs = useMemo(() => {
    const assigned = new Set(selectedOrgAssignments.map((row) => row.org_id))
    const term = assignmentSearch.trim().toLowerCase()
    return orgs
      .filter((org) => !assigned.has(org.id))
      .filter((org) => !term || String(org.name || '').toLowerCase().includes(term))
      .slice(0, 20)
  }, [assignmentSearch, orgs, selectedOrgAssignments])

  const save = async () => {
    setBusy(true)
    setMsg('')
    try {
      const body = JSON.stringify(draft)
      const saved = selectedId
        ? await apiFetch(`/admin/agents/${selectedId}`, { method: 'PUT', body })
        : await apiFetch('/admin/agents', { method: 'POST', body })
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

  const reloadPage = async () => {
    setBusy(true)
    setMsg('Reloading agent data...')
    try {
      await load()
      setMsg('Agent data reloaded.')
    } catch (e) {
      setMsg(e?.message || 'Could not reload agent data')
    } finally {
      setBusy(false)
    }
  }

  const setAgentOrganisationAssignments = async (nextOrgIds, successMessage) => {
    if (!selectedId) {
      setMsg('Save the agent first, then add organisations.')
      return
    }
    const uniqueOrgIds = Array.from(new Set(nextOrgIds.filter(Boolean)))
    setBusy(true)
    setMsg('Saving organisation assignments...')
    try {
      const result = await apiFetch(`/admin/agents/${selectedId}/organisation-assignments`, {
        method: 'PUT',
        body: JSON.stringify({ org_ids: uniqueOrgIds }),
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

  const assignOrg = async (orgId, agentId) => {
    if (!orgId || !agentId) return
    await setAgentOrganisationAssignments([...selectedOrgIds, orgId], 'Organisation assigned to agent.')
  }

  const removeOrgAssignment = async (assignment) => {
    if (!assignment?.id) return
    const previousAssignments = assignments
    setAssignments((rows) => rows.filter((row) => row.id !== assignment.id))
    setOrgsToRemove((rows) => rows.filter((id) => id !== assignment.org_id))
    setBusy(true)
    setMsg('Removing organisation assignment...')
    try {
      await apiFetch(`/admin/agents/assignments/${assignment.id}`, { method: 'DELETE' })
      setMsg('Organisation removed from agent.')
    } catch (e) {
      setAssignments(previousAssignments)
      setMsg(`${e?.message || 'Could not remove organisation assignment'} — if this keeps happening, restart FastAPI so the latest delete endpoint is active.`)
    } finally {
      setBusy(false)
    }
  }

  const toggleOrgToAdd = (orgId) => {
    setOrgsToAdd((rows) => rows.includes(orgId) ? rows.filter((id) => id !== orgId) : [...rows, orgId])
  }

  const toggleOrgToRemove = (orgId) => {
    setOrgsToRemove((rows) => rows.includes(orgId) ? rows.filter((id) => id !== orgId) : [...rows, orgId])
  }

  const addSelectedOrganisations = async () => {
    if (!selectedId || !orgsToAdd.length) return
    await setAgentOrganisationAssignments(
      [...selectedOrgIds, ...orgsToAdd],
      `${orgsToAdd.length} organisation${orgsToAdd.length === 1 ? '' : 's'} assigned to agent.`
    )
  }

  const removeSelectedOrganisations = async () => {
    if (!orgsToRemove.length) return
    const previousAssignments = assignments
    const removeSet = new Set(orgsToRemove)
    const count = orgsToRemove.length
    setAssignments((rows) => rows.filter((row) => !(row.agent_id === selectedId && removeSet.has(row.org_id))))
    setOrgsToRemove([])
    setBusy(true)
    setMsg(`Removing ${count} organisation${count === 1 ? '' : 's'}...`)
    try {
      const rowsToDelete = selectedOrgAssignments.filter((row) => removeSet.has(row.org_id))
      for (const row of rowsToDelete) {
        await apiFetch(`/admin/agents/assignments/${row.id}`, { method: 'DELETE' })
      }
      setMsg(`${count} organisation${count === 1 ? '' : 's'} removed from agent.`)
    } catch (e) {
      setAssignments(previousAssignments)
      setMsg(`${e?.message || 'Could not remove selected organisations'} — if this keeps happening, restart FastAPI so the latest delete endpoint is active.`)
    } finally {
      setBusy(false)
    }
  }

  const assignCategory = async (categoryId, agentId) => {
    if (!categoryId || !agentId) return
    setBusy(true)
    setMsg('Saving category default assignment...')
    try {
      await apiFetch(`/admin/agents/assignments/business-type/${categoryId}`, {
        method: 'PUT',
        body: JSON.stringify({ agent_id: agentId }),
      })
      setMsg('Category default assignment saved.')
      await load()
    } catch (e) {
      setMsg(e?.message || 'Could not save category default assignment')
    } finally {
      setBusy(false)
    }
  }

  const preview = async () => {
    setBusy(true)
    setPreviewResult(null)
    setMsg('')
    try {
      const res = await apiFetch('/admin/agents/preview', {
        method: 'POST',
        body: JSON.stringify({ agent_id: selectedId || null, org_id: previewOrgId || null, input: previewInput }),
      })
      setPreviewResult(res)
    } catch (e) {
      setMsg(e?.message || 'Preview failed')
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
    setMsg('')
    try {
      const copy = {
        ...agent,
        id: undefined,
        name: `${agent.name} Copy`,
        slug: `${agent.slug || 'agent'}-copy-${Date.now().toString().slice(-5)}`,
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
    setMsg('')
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
    setMsg('')
    try {
      await apiFetch(`/admin/agents/${agent.id}/${agent.is_active ? 'deactivate' : 'activate'}`, { method: 'POST' })
      setMsg(agent.is_active ? 'Agent frozen.' : 'Agent unfrozen.')
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
            <p>Manage all AI call agents. Open an agent to edit its workflow, modules, assignment, and tools.</p>
          </div>
          <div className='actions'>
            <button className='btn soft' onClick={reloadPage} disabled={busy}>{busy ? 'Working...' : 'Reload'}</button>
            <button className='btn primary' onClick={newAgent}>New agent</button>
          </div>
        </div>
        {msg ? <div className='note' style={{ marginBottom: 16 }}>{msg}</div> : null}
        <div className='card'>
          <div className='cardHead'>
            <h3>All agents</h3>
            <span className='pill p-cyan'>{agents.length}</span>
          </div>
          <div className='cardBody'>
            <div className='tableWrap'>
              <table className='table'>
                <thead>
                  <tr>
                    <th>Agent name</th>
                    <th>Assigned to</th>
                    <th>Status</th>
                    <th>Modules</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {agents.map((agent) => (
                    <tr key={agent.id}>
                      <td>
                        <strong>{agent.name}</strong>
                        <div className='muted' style={{ fontSize: 12 }}>{agent.slug}</div>
                      </td>
                      <td>{assignedLabel(agent)}</td>
                      <td><span className={`pill ${agent.is_active ? 'p-green' : 'p-amber'}`}>{agent.is_active ? 'Active' : 'Frozen'}</span></td>
                      <td className='muted' style={{ fontSize: 12 }}>
                        STT {agent.use_azure_stt ? 'Azure' : 'Off'} · LLM {agent.default_model || 'Default'} · TTS {agent.use_azure_tts ? 'Azure' : 'Off'} · SIP later
                      </td>
                      <td>
                        <div className='actions'>
                          <button className='btn soft' onClick={() => duplicateAgent(agent)} disabled={busy}>Duplicate</button>
                          <button className='btn soft' onClick={() => navigate(`/ai/agents/${agent.id}/edit`)}>Edit</button>
                          <button className='btn soft' onClick={() => toggleFreeze(agent)} disabled={busy}>{agent.is_active ? 'Freeze' : 'Unfreeze'}</button>
                          <button className='btn soft' onClick={() => deleteAgent(agent)} disabled={busy}>Delete</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {!agents.length ? (
                    <tr><td colSpan={5} className='muted'>No agents yet.</td></tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>{selectedId ? `Edit ${draft.name || 'agent'}` : 'Create agent'}</h1>
          <p>Configure the call workflow, assignment, AI modules, tools, and prompt for this agent.</p>
        </div>
        <div className='actions'>
          <button className='btn soft' onClick={() => navigate('/ai/agents')}>Back to list</button>
          <button className='btn soft' onClick={reloadPage} disabled={busy}>{busy ? 'Working...' : 'Reload'}</button>
          <button className='btn primary' onClick={save} disabled={busy || !draft.name?.trim() || !draft.system_prompt?.trim()}>
            {busy ? 'Saving…' : 'Save agent'}
          </button>
        </div>
      </div>
      {msg ? <div className='note' style={{ marginBottom: 16 }}>{msg}</div> : null}

      <div className='card' style={{ marginBottom: 16 }}>
        <div className='cardHead'>
          <h3>Agent basics</h3>
          <span className={`pill ${draft.is_active ? 'p-green' : 'p-amber'}`}>{draft.is_active ? 'Active' : 'Frozen'}</span>
        </div>
        <div className='cardBody stack'>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12 }}>
            <label><span className='label'>Agent name</span><input className='input' value={draft.name || ''} onChange={(e) => setField('name', e.target.value)} placeholder='Vox Sales' /></label>
            <label><span className='label'>Slug</span><input className='input' value={draft.slug || ''} onChange={(e) => setField('slug', e.target.value)} placeholder='vox-sales' /></label>
            <label><span className='label'>Business type</span><input className='input' value={draft.business_type || ''} onChange={(e) => setField('business_type', e.target.value)} placeholder='clinic, sales, support...' /></label>
            <label>
              <span className='label'>Category</span>
              <select className='input' value={draft.category_id || ''} onChange={(e) => setField('category_id', e.target.value)}>
                <option value=''>No category</option>
                {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <label style={{ gridColumn: 'span 2' }}><span className='label'>Description</span><input className='input' value={draft.description || ''} onChange={(e) => setField('description', e.target.value)} placeholder='Short internal description' /></label>
          </div>
        </div>
      </div>

      <div className='card' style={{ marginBottom: 16 }}>
        <div className='cardHead'>
          <h3>Module control</h3>
          <span className='pill p-cyan'>STT · LLM · TTS · SIP</span>
        </div>
        <div className='cardBody'>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
            <div className='note' style={{ display: 'grid', gap: 8 }}>
              <strong>Speech-to-text module</strong>
              <select className='input' value={draft.use_azure_stt ? 'azure_speech' : 'browser'} onChange={(e) => setField('use_azure_stt', e.target.value === 'azure_speech')}>
                <option value='browser'>Browser Web Speech</option>
                <option value='azure_speech'>Azure Speech</option>
                <option value='elevenlabs'>ElevenLabs Scribe (demo test)</option>
              </select>
              <div className='muted' style={{ fontSize: 12 }}>Saved today as Azure STT on/off. ElevenLabs STT is available in the demo lab.</div>
            </div>
            <div className='note' style={{ display: 'grid', gap: 8 }}>
              <strong>LLM module</strong>
              <input className='input' value={draft.default_model || ''} onChange={(e) => setField('default_model', e.target.value)} placeholder='gpt-4o-mini, deepseek-chat...' />
              <div className='muted' style={{ fontSize: 12 }}>Model/provider routing uses current platform provider settings.</div>
            </div>
            <div className='note' style={{ display: 'grid', gap: 8 }}>
              <strong>Text-to-speech module</strong>
              <select className='input' value={draft.use_azure_tts ? 'azure_speech' : 'off'} onChange={(e) => setField('use_azure_tts', e.target.value === 'azure_speech')}>
                <option value='azure_speech'>Azure Speech</option>
                <option value='elevenlabs'>ElevenLabs (demo/test)</option>
                <option value='off'>Off</option>
              </select>
              <input className='input' value={draft.default_voice || ''} onChange={(e) => setField('default_voice', e.target.value)} placeholder='Voice ID' />
              <div className='muted' style={{ fontSize: 12 }}>Saved today as Azure TTS on/off plus default voice. ElevenLabs voice is tested in demo lab.</div>
            </div>
            <div className='note' style={{ display: 'grid', gap: 8 }}>
              <strong>SIP module</strong>
              <select className='input' disabled value='later'>
                <option value='later'>Coming later</option>
              </select>
              <div className='muted' style={{ fontSize: 12 }}>Design placeholder for SIP routing/provider selection.</div>
            </div>
          </div>
        </div>
      </div>

      <div className='grid-12'>
        <div className='span-5 stack'>
          <div className='card'>
            <div className='cardHead'>
              <h3>Assigned organisations</h3>
              <span className='pill p-cyan'>{selectedOrgAssignments.length}</span>
            </div>
            <div className='cardBody stack'>
              <div className='note'>
                Add the one or two organisations that should use this agent. This is saved in the database as organisation agent assignments.
              </div>
              <div style={{ display: 'grid', gap: 10 }}>
                {selectedOrgAssignments.length ? selectedOrgAssignments.map((row) => {
                  const org = orgById[row.org_id]
                  return (
                    <div key={row.id} className='note' style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1 }}>
                        <input type='checkbox' checked={orgsToRemove.includes(row.org_id)} onChange={() => toggleOrgToRemove(row.org_id)} />
                        <span>
                          <strong>{org?.name || 'Unknown organisation'}</strong>
                          <div className='muted' style={{ fontSize: 12 }}>Assigned to this agent</div>
                        </span>
                      </label>
                      <button className='btn soft' onClick={() => removeOrgAssignment(row)} disabled={busy}>
                        Remove
                      </button>
                    </div>
                  )
                }) : <div className='note'>No organisations assigned yet.</div>}
              </div>
              {selectedOrgAssignments.length ? (
                <div className='actions'>
                  <button className='btn soft' onClick={() => setOrgsToRemove(selectedOrgAssignments.map((row) => row.org_id))} disabled={busy}>
                    Select all assigned
                  </button>
                  <button className='btn primary' onClick={removeSelectedOrganisations} disabled={busy || !orgsToRemove.length}>
                    Remove selected ({orgsToRemove.length})
                  </button>
                </div>
              ) : null}
              <div style={{ display: 'grid', gap: 8 }}>
                <label className='label'>Add organisation</label>
                <input className='input' value={assignmentSearch} onChange={(e) => setAssignmentSearch(e.target.value)} placeholder='Search organisation name...' />
                <div className='note' style={{ display: 'grid', gap: 8, maxHeight: 220, overflowY: 'auto' }}>
                  {assignableOrgs.length ? assignableOrgs.map((org) => (
                    <label key={org.id} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type='checkbox' checked={orgsToAdd.includes(org.id)} onChange={() => toggleOrgToAdd(org.id)} disabled={!selectedId || busy} />
                      <span>{org.name}</span>
                    </label>
                  )) : <div className='muted'>No organisations found or all visible organisations are already assigned.</div>}
                </div>
                <div className='actions'>
                  <button className='btn soft' onClick={() => setOrgsToAdd(assignableOrgs.map((org) => org.id))} disabled={!selectedId || busy || !assignableOrgs.length}>
                    Select visible
                  </button>
                  <button className='btn primary' onClick={addSelectedOrganisations} disabled={!selectedId || busy || !orgsToAdd.length}>
                    Add selected ({orgsToAdd.length})
                  </button>
                </div>
                {!selectedId ? <div className='muted' style={{ fontSize: 12 }}>Save the agent first, then add organisations.</div> : null}
              </div>
            </div>
          </div>

          <div className='card'>
            <div className='cardHead'>
              <h3>Category default assignment</h3>
              <span className='pill p-amber'>Optional</span>
            </div>
            <div className='cardBody stack'>
              <div className='note'>
                This is different from organisation assignment. Organisation assignment is exact: that customer uses this agent. Category default is a fallback rule: any organisation in this category can use this agent when no organisation-specific agent is set.
              </div>
              {selectedCategoryAssignments.length ? (
                <div className='note'>
                  Current category default: {selectedCategoryAssignments.map((row) => categoryById[row.category_id]?.name || 'Business type').join(', ')}
                </div>
              ) : null}
              <select className='input' onChange={(e) => assignCategory(e.target.value, selectedId)} value=''>
                <option value=''>Assign as category default...</option>
                {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <div className='muted' style={{ fontSize: 12 }}>If you do not want category fallback rules, leave this empty.</div>
            </div>
          </div>
        </div>

        <div className='span-7 stack'>
          <div className='card'>
            <div className='cardHead'><h3>Edit agent settings</h3></div>
            <div className='cardBody stack'>
              <label><span className='label'>Call workflow / system prompt</span><textarea className='input' style={{ minHeight: 260 }} value={draft.system_prompt || ''} onChange={(e) => setField('system_prompt', e.target.value)} /></label>
              <label><span className='label'>Tone / personality</span><textarea className='input' style={{ minHeight: 90 }} value={draft.conversation_style || ''} onChange={(e) => setField('conversation_style', e.target.value)} /></label>
              <div className='actions' style={{ flexWrap: 'wrap' }}>
                {[
                  ['allow_lookup_tool', 'Lookup tool'],
                  ['allow_booking_tool', 'Booking tool'],
                  ['allow_reschedule_tool', 'Reschedule tool'],
                  ['allow_cancel_tool', 'Cancel tool'],
                  ['is_active', 'Active / not frozen'],
                  ['is_template', 'Template'],
                ].map(([key, label]) => (
                  <label key={key} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <input type='checkbox' checked={Boolean(draft[key])} onChange={(e) => setField(key, e.target.checked)} />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
              <div className='actions'><button className='btn primary' onClick={save} disabled={busy || !draft.name?.trim() || !draft.system_prompt?.trim()}>{busy ? 'Saving…' : 'Save agent'}</button></div>
            </div>
          </div>

          <div className='card'>
            <div className='cardHead'><h3>Preview/test agent response</h3></div>
            <div className='cardBody stack'>
              <select className='input' value={previewOrgId} onChange={(e) => setPreviewOrgId(e.target.value)}>
                <option value=''>Use first organisation</option>
                {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </select>
              <textarea className='input' value={previewInput} onChange={(e) => setPreviewInput(e.target.value)} />
              <div className='actions'><button className='btn primary' onClick={preview} disabled={busy || !previewInput.trim()}>{busy ? 'Testing…' : 'Preview response'}</button></div>
              {previewResult ? <div className='note'><strong>{previewResult.agent_slug}</strong><br />{previewResult.assistant_text}</div> : null}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
