import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { serviceBadges } from '../components/agents/AgentVoiceFields'
import AgentEditPage from './AgentEditPage'

function agentInitial(agent) {
  const label = agent.voice_label || agent.name || 'A'
  return label.trim()[0]?.toUpperCase() || 'A'
}

function serviceChips(agent) {
  const badges = serviceBadges(agent)
  return badges.filter((b) => !b.startsWith('Default'))
}

export default function Agents() {
  const navigate = useNavigate()
  const { agentId } = useParams()
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [msg, setMsg] = useState('')
  const [msgError, setMsgError] = useState(false)

  const isEditPage = Boolean(agentId) || window.location.pathname.endsWith('/new')

  const loadAgents = async () => {
    setLoading(true)
    try {
      const agentRows = await apiFetch('/admin/agents')
      setAgents(agentRows?.agents || [])
    } catch (e) {
      setMsg(e?.message || 'Failed to load agents')
      setMsgError(true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAgents()
  }, [])

  const filtered = useMemo(() => {
    let list = agents
    if (statusFilter === 'active') list = list.filter((a) => a.is_active)
    if (statusFilter === 'frozen') list = list.filter((a) => !a.is_active)
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase()
      list = list.filter(
        (a) =>
          String(a.name || '').toLowerCase().includes(term) ||
          String(a.slug || '').toLowerCase().includes(term) ||
          String(a.voice_label || '').toLowerCase().includes(term) ||
          String(a.description || '').toLowerCase().includes(term),
      )
    }
    return list
  }, [agents, searchTerm, statusFilter])

  const kpis = useMemo(
    () => ({
      total: agents.length,
      active: agents.filter((a) => a.is_active).length,
      frozen: agents.filter((a) => !a.is_active).length,
    }),
    [agents],
  )

  const flash = (text, isError = false) => {
    setMsg(text)
    setMsgError(isError)
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
        voice_label: agent.voice_label,
        voice_type_label: agent.voice_type_label,
        telnyx_assistant_id: agent.telnyx_assistant_id,
        base_role: agent.base_role,
        service_survey_role: agent.service_survey_role,
        service_interview_role: agent.service_interview_role,
        service_lead_sales_role: agent.service_lead_sales_role,
        opening_disclosure_template: agent.opening_disclosure_template,
        supports_survey: agent.supports_survey,
        supports_interview: agent.supports_interview,
        supports_lead_sales: agent.supports_lead_sales,
      }
      const saved = await apiFetch('/admin/agents', { method: 'POST', body: JSON.stringify(copy) })
      flash('Agent duplicated.')
      await loadAgents()
      navigate(`/ai/agents/${saved.id}/edit`)
    } catch (e) {
      flash(e?.message || 'Could not duplicate agent', true)
    } finally {
      setBusy(false)
    }
  }

  const toggleFreeze = async (agent) => {
    setBusy(true)
    try {
      await apiFetch(`/admin/agents/${agent.id}/${agent.is_active ? 'deactivate' : 'activate'}`, { method: 'POST' })
      flash(agent.is_active ? 'Agent frozen.' : 'Agent activated.')
      await loadAgents()
    } catch (e) {
      flash(e?.message || 'Could not update agent status', true)
    } finally {
      setBusy(false)
    }
  }

  const deleteAgent = async (agent) => {
    if (!window.confirm(`Delete ${agent.name}? This cannot be undone.`)) return
    setBusy(true)
    try {
      await apiFetch(`/admin/agents/${agent.id}`, { method: 'DELETE' })
      flash('Agent deleted.')
      await loadAgents()
    } catch (e) {
      flash(e?.message || 'Could not delete agent', true)
    } finally {
      setBusy(false)
    }
  }

  if (isEditPage) {
    return (
      <AgentEditPage
        agentId={agentId || 'new'}
        onClose={() => navigate('/ai/agents')}
        onSaved={(saved) => {
          loadAgents()
          if (!agentId && saved?.id) navigate(`/ai/agents/${saved.id}/edit`)
        }}
      />
    )
  }

  return (
    <div className="agentsMainPage">
      <div className="agentsMainTop">
        <div>
          <h1>Main agents</h1>
          <div className="agentsMainSub">
            Voice agents for dashboard surveys — Telnyx, prompts, and service assignment.
          </div>
        </div>
        <div className="agentsMainActions">
          <button type="button" className="agentsBtn" onClick={() => loadAgents()} disabled={loading || busy}>
            Reload
          </button>
          <button type="button" className="agentsBtn primary" onClick={() => navigate('/ai/agents/new')}>
            <i className="ti ti-plus"></i> New agent
          </button>
        </div>
      </div>

      {msg ? <div className={`agentsMsg${msgError ? ' is-error' : ''}`}>{msg}</div> : null}

      <div className="agentsKpis">
        <div className="agentsKpi">
          <div className="agentsKpiLabel">Total agents</div>
          <div className="agentsKpiValue">{kpis.total}</div>
        </div>
        <div className="agentsKpi">
          <div className="agentsKpiLabel">Active agents</div>
          <div className="agentsKpiValue">{kpis.active}</div>
        </div>
        <div className="agentsKpi">
          <div className="agentsKpiLabel">Frozen agents</div>
          <div className="agentsKpiValue">{kpis.frozen}</div>
        </div>
      </div>

      <div className="agentsPanel">
        <div className="agentsToolbar">
          <div>
            <div className="agentsToolbarTitle">
              <i className="ti ti-list-details"></i> Agents
            </div>
            <div className="agentsMainSub" style={{ marginTop: 3 }}>
              Active + Survey enabled agents appear in dashboard AI voice dropdown.
            </div>
          </div>
          <div className="agentsToolbarRight">
            <div className="agentsSearch">
              <input
                type="search"
                placeholder="Search agents, slugs..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <select className="agentsSelect" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="all">All statuses</option>
              <option value="active">Active</option>
              <option value="frozen">Frozen</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div className="agentsEmpty">Loading agents...</div>
        ) : filtered.length === 0 ? (
          <div className="agentsEmpty">No agents found.</div>
        ) : (
          <div className="agentsTableWrap">
            <table className="agentsTable">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Services</th>
                  <th>Voice</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((agent) => {
                  const chips = serviceChips(agent)
                  const surveyReady = agent.is_active && agent.supports_survey
                  return (
                    <tr key={agent.id}>
                      <td>
                        <div className="agentsAgentCell">
                          <div className="agentsAvatar">{agentInitial(agent)}</div>
                          <div style={{ minWidth: 0 }}>
                            <div className="agentsNameRow">
                              {agent.name}
                              <span className="agentsSlugChip" title={agent.slug}>
                                {agent.slug}
                              </span>
                            </div>
                            <div className="agentsDesc" title={agent.description || ''}>
                              {agent.description || '—'}
                            </div>
                            <div className="agentsChips">
                              {chips.map((b) => (
                                <span key={b} className="agentsChip">
                                  {b}
                                </span>
                              ))}
                              {agent.is_default_survey ? <span className="agentsChip">Default</span> : null}
                              {surveyReady ? <span className="agentsChip survey">Dashboard</span> : null}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td>
                        {chips.length ? (
                          chips.map((b) => (
                            <span key={b} className="agentsChip" style={{ marginRight: 4 }}>
                              {b}
                            </span>
                          ))
                        ) : (
                          <span className="agentsMutedDash">—</span>
                        )}
                      </td>
                      <td>
                        <div style={{ fontWeight: 600, fontSize: 11 }}>{agent.voice_label || '—'}</div>
                        {agent.voice_type_label ? (
                          <div className="agentsMutedDash">{agent.voice_type_label}</div>
                        ) : null}
                      </td>
                      <td>
                        <span className={`agentsStatus ${agent.is_active ? 'active' : 'frozen'}`}>
                          <i className={`ti ${agent.is_active ? 'ti-circle-check' : 'ti-lock'}`}></i>
                          {agent.is_active ? 'Active' : 'Frozen'}
                        </span>
                      </td>
                      <td>
                        <div className="agentsRowActions">
                          <button type="button" className="agentsAction" onClick={() => duplicateAgent(agent)} disabled={busy}>
                            Duplicate
                          </button>
                          <button
                            type="button"
                            className="agentsAction primary"
                            onClick={() => navigate(`/ai/agents/${agent.id}/edit`)}
                          >
                            Edit
                          </button>
                          <button type="button" className="agentsAction" onClick={() => toggleFreeze(agent)} disabled={busy}>
                            {agent.is_active ? 'Freeze' : 'Unfreeze'}
                          </button>
                          <button type="button" className="agentsAction warn" onClick={() => deleteAgent(agent)} disabled={busy}>
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
