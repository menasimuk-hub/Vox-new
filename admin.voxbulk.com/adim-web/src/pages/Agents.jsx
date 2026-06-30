import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CircleCheck, Plus, RotateCw, Snowflake, Users } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { serviceBadges, PlatformVoiceSettings } from '../components/agents/AgentVoiceFields'
import AgentEditPage from './AgentEditPage'
import { KpiCard } from '@/components/ui/KpiCard'
import { Panel } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Pill } from '@/components/ui/Badge'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableLoading,
  TableRow,
} from '@/components/ui/Table'

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
  const [platformSettings, setPlatformSettings] = useState(null)
  const [platformBusy, setPlatformBusy] = useState(false)

  const isEditPage = Boolean(agentId) || window.location.pathname.endsWith('/new')

  const loadPlatformSettings = async () => {
    try {
      const data = await apiFetch('/admin/agents/platform-voice-settings')
      setPlatformSettings(data || null)
    } catch (e) {
      flash(e?.message || 'Failed to load shared voice settings', true)
    }
  }

  const savePlatformSettings = async () => {
    if (!platformSettings) return
    setPlatformBusy(true)
    try {
      const saved = await apiFetch('/admin/agents/platform-voice-settings', {
        method: 'PUT',
        body: JSON.stringify(platformSettings),
      })
      setPlatformSettings(saved)
      flash('Shared voice settings saved.')
    } catch (e) {
      flash(e?.message || 'Could not save shared voice settings', true)
    } finally {
      setPlatformBusy(false)
    }
  }

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
    loadPlatformSettings()
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
    <div className="agentsMainPage ds-scope space-y-4">
      <div className="agentsMainTop">
        <div>
          <h1>Main agents</h1>
          <div className="agentsMainSub">
            Voice agents for surveys and interviews — Telnyx, prompts, and service assignment.
          </div>
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => loadAgents()} disabled={loading || busy}>
            <RotateCw size={14} /> Reload
          </Button>
          <Button type="button" size="sm" className="h-8" onClick={() => navigate('/ai/agents/new')}>
            <Plus size={14} /> New agent
          </Button>
        </div>
      </div>

      {msg ? (
        <div
          className={
            msgError
              ? 'rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive'
              : 'rounded-md border border-success/40 bg-success-soft px-3 py-2 text-sm text-success'
          }
        >
          {msg}
        </div>
      ) : null}

      <PlatformVoiceSettings
        settings={platformSettings}
        onChange={setPlatformSettings}
        onSave={savePlatformSettings}
        busy={platformBusy}
      />

      <div className="grid grid-cols-3 gap-3">
        <KpiCard icon={Users} label="Total agents" value={kpis.total} tone="primary" index={0} />
        <KpiCard icon={CircleCheck} label="Active agents" value={kpis.active} tone="success" index={1} />
        <KpiCard icon={Snowflake} label="Frozen agents" value={kpis.frozen} tone="info" index={2} />
      </div>

      <Panel
        title="Agents"
        subtitle="Active + Survey-enabled agents appear in the dashboard AI voice dropdown."
        action={
          <div className="flex items-center gap-2">
            <Input
              type="search"
              placeholder="Search agents, slugs…"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="h-8 w-[220px]"
            />
            <select
              className="h-8 shrink-0 rounded-md border border-input bg-transparent px-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="all">All statuses</option>
              <option value="active">Active</option>
              <option value="frozen">Frozen</option>
            </select>
          </div>
        }
      >
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Agent</TableHead>
              <TableHead>Services</TableHead>
              <TableHead>Voice</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableLoading colSpan={5}>Loading agents…</TableLoading>
            ) : (
              filtered.map((agent) => {
                const chips = serviceChips(agent)
                const surveyReady = agent.is_active && agent.supports_survey
                return (
                  <TableRow key={agent.id}>
                    <TableCell>
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
                    </TableCell>
                    <TableCell>
                      {chips.length ? (
                        <div className="flex flex-wrap gap-1">
                          {chips.map((b) => (
                            <span key={b} className="agentsChip">
                              {b}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="font-medium">{agent.voice_label || '—'}</div>
                      {agent.voice_type_label ? (
                        <div className="text-[11px] text-muted-foreground">{agent.voice_type_label}</div>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <Pill tone={agent.is_active ? 'success' : 'neutral'}>
                        {agent.is_active ? 'Active' : 'Frozen'}
                      </Pill>
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button type="button" variant="outline" size="sm" className="h-7" onClick={() => duplicateAgent(agent)} disabled={busy}>
                          Duplicate
                        </Button>
                        <Button type="button" size="sm" className="h-7" onClick={() => navigate(`/ai/agents/${agent.id}/edit`)}>
                          Edit
                        </Button>
                        <Button type="button" variant="outline" size="sm" className="h-7" onClick={() => toggleFreeze(agent)} disabled={busy}>
                          {agent.is_active ? 'Freeze' : 'Unfreeze'}
                        </Button>
                        <Button type="button" variant="ghost" size="sm" className="h-7 text-destructive hover:text-destructive" onClick={() => deleteAgent(agent)} disabled={busy}>
                          Delete
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
            {!loading && filtered.length === 0 ? <TableEmpty colSpan={5}>No agents found.</TableEmpty> : null}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
