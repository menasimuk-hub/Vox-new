import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import AgentEditPage from './AgentEditPage'

export default function Agents() {
  const navigate = useNavigate()
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [editingAgentId, setEditingAgentId] = useState(null)
  const [msg, setMsg] = useState('')

  // Load agents list
  const loadAgents = async () => {
    setLoading(true)
    try {
      const data = await apiFetch('/admin/agents')
      setAgents(data?.agents || [])
    } catch (e) {
      setMsg(e?.message || 'Failed to load agents')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAgents()
  }, [])

  // Filtered agents
  const filtered = useMemo(() => {
    let list = agents
    if (statusFilter === 'active') list = list.filter(a => a.is_active)
    if (statusFilter === 'frozen') list = list.filter(a => !a.is_active)
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase()
      list = list.filter(a => 
        a.name.toLowerCase().includes(term) ||
        a.slug.toLowerCase().includes(term)
      )
    }
    return list
  }, [agents, searchTerm, statusFilter])

  // KPIs
  const kpis = useMemo(() => ({
    total: agents.length,
    active: agents.filter(a => a.is_active).length,
    frozen: agents.filter(a => !a.is_active).length,
  }), [agents])

  // Service badges
  const serviceBadges = (agent) => {
    const badges = []
    if (agent.supports_survey) badges.push('Survey')
    if (agent.supports_interview) badges.push('Interview')
    if (agent.supports_lead_sales) badges.push('Lead / Sales')
    if (agent.is_default_survey || agent.is_default_interview || agent.is_default_lead_sales) {
      badges.push('Default')
    }
    return badges
  }

  // If editing, show edit page
  if (editingAgentId) {
    return (
      <AgentEditPage
        agentId={editingAgentId}
        onClose={() => {
          setEditingAgentId(null)
          loadAgents()
        }}
      />
    )
  }

  // Main list view
  return (
    <div style={styles.wrap}>
      <div style={styles.top}>
        <div>
          <a href="#" onClick={(e) => { e.preventDefault(); navigate('/') }} style={styles.crumb}>
            <i className="ti ti-arrow-left"></i> Dashboard
          </a>
          <h1 style={styles.title}>Main agents</h1>
          <div style={styles.sub}>Manage voice agents, Telnyx IDs, layered prompts, and service assignment.</div>
        </div>
        <button
          style={{ ...styles.btn, ...styles.btnPrimary }}
          onClick={() => setEditingAgentId('new')}
        >
          <i className="ti ti-plus"></i> New agent
        </button>
      </div>

      {msg && (
        <div style={{ ...styles.msg, marginBottom: 16, padding: '12px 16px' }}>
          {msg}
        </div>
      )}

      <div style={styles.kpis}>
        <div style={styles.kpi}>
          <div style={styles.kpiLabel}>Total agents</div>
          <div style={styles.kpiValue}>{kpis.total}</div>
        </div>
        <div style={styles.kpi}>
          <div style={styles.kpiLabel}>Active agents</div>
          <div style={styles.kpiValue}>{kpis.active}</div>
        </div>
        <div style={styles.kpi}>
          <div style={styles.kpiLabel}>Frozen agents</div>
          <div style={styles.kpiValue}>{kpis.frozen}</div>
        </div>
      </div>

      <div style={styles.panel}>
        <div style={styles.toolbar}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 800, display: 'flex', alignItems: 'center', gap: 8 }}>
              <i className="ti ti-list-details" style={{ color: '#2563eb' }}></i> Agents
            </div>
            <div style={styles.sub}>Manage voice agents, organisations, status, and actions.</div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', width: '100%', maxWidth: 520 }}>
            <div style={styles.search}>
              <input
                type="search"
                placeholder="Search agents, slugs..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                style={{ ...styles.searchInput, width: '100%' }}
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{ ...styles.select, maxWidth: 180 }}
            >
              <option value="all">All statuses</option>
              <option value="active">Active</option>
              <option value="frozen">Frozen</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div style={{ padding: 32, textAlign: 'center', color: '#64748b' }}>
            <i className="ti ti-loader"></i> Loading agents...
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: 32, textAlign: 'center', color: '#64748b' }}>
            <i className="ti ti-inbox"></i> No agents found
          </div>
        ) : (
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Agent</th>
                  <th style={styles.th}>Services</th>
                  <th style={styles.th}>Voice label</th>
                  <th style={styles.th}>Status</th>
                  <th style={styles.th}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((agent) => (
                  <tr key={agent.id} style={styles.tr}>
                    <td style={styles.td}>
                      <div style={styles.agentName}>
                        <div style={styles.avatar}>
                          {(agent.name || 'A')[0].toUpperCase()}
                        </div>
                        <div>
                          <div style={styles.name}>{agent.name} <span style={styles.chip}>{agent.slug}</span></div>
                          <div style={styles.slug}>{agent.description || '—'}</div>
                          <div style={styles.chips}>
                            {serviceBadges(agent).map((b) => (
                              <span key={b} style={styles.chip}>{b}</span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td style={styles.td}>
                      {serviceBadges(agent).filter(b => b !== 'Default').map((b) => (
                        <span key={b} style={styles.chip}>{b}</span>
                      ))}
                    </td>
                    <td style={styles.td}>{agent.voice_label || '—'}</td>
                    <td style={styles.td}>
                      <span style={{
                        ...styles.status,
                        ...(agent.is_active ? styles.statusActive : styles.statusFrozen)
                      }}>
                        <i className={`ti ${agent.is_active ? 'ti-circle-check' : 'ti-lock'}`}></i>
                        {agent.is_active ? ' Active' : ' Frozen'}
                      </span>
                    </td>
                    <td style={styles.td}>
                      <div style={styles.actions}>
                        <button
                          style={{ ...styles.actionBtn }}
                          onClick={() => {
                            const newAgent = JSON.parse(JSON.stringify(agent))
                            newAgent.id = null
                            newAgent.slug = newAgent.slug + '-copy-' + Math.random().toString(36).slice(2, 8)
                            setEditingAgentId('new')
                          }}
                        >
                          Duplicate
                        </button>
                        <button
                          style={{ ...styles.actionBtn, ...styles.actionBtnPrimary }}
                          onClick={() => setEditingAgentId(agent.id)}
                        >
                          Edit
                        </button>
                        <button
                          style={{ ...styles.actionBtn }}
                          onClick={() => {
                            if (window.confirm(`${agent.is_active ? 'Freeze' : 'Unfreeze'} ${agent.name}?`)) {
                              apiFetch(`/admin/agents/${agent.id}`, {
                                method: 'PUT',
                                body: JSON.stringify({ is_active: !agent.is_active }),
                              }).then(loadAgents).catch(e => setMsg(e?.message))
                            }
                          }}
                        >
                          {agent.is_active ? 'Freeze' : 'Unfreeze'}
                        </button>
                        <button
                          style={{ ...styles.actionBtn, ...styles.actionBtnWarn }}
                          onClick={() => {
                            if (window.confirm(`Delete ${agent.name}? This cannot be undone.`)) {
                              apiFetch(`/admin/agents/${agent.id}`, { method: 'DELETE' })
                                .then(loadAgents)
                                .catch(e => setMsg(e?.message))
                            }
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

const styles = {
  wrap: { maxWidth: 1400, margin: '0 auto', padding: '0 28px 28px' },
  top: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 16,
    padding: '16px 0 14px',
    borderBottom: '1px solid #e3e8f0',
    position: 'sticky',
    top: 0,
    background: '#f7f9fc',
    zIndex: 10,
    backdropFilter: 'blur(2px)',
  },
  title: { fontSize: 17, fontWeight: 800, letterSpacing: '-.03em', margin: 0 },
  sub: { marginTop: 3, fontSize: 11, color: '#64748b' },
  crumb: { fontSize: 12, color: '#64748b', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer' },
  btn: { border: '1px solid #e3e8f0', background: '#fff', color: '#0f172a', padding: '8px 14px', borderRadius: 999, fontSize: 12, fontWeight: 700, cursor: 'pointer', display: 'inline-flex', gap: 7, alignItems: 'center' },
  btnPrimary: { background: '#2563eb', borderColor: '#2563eb', color: '#fff' },
  kpis: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, margin: '16px 0 14px' },
  kpi: { background: '#fff', border: '1px solid #e3e8f0', borderRadius: 16, padding: '14px 16px', boxShadow: '0 1px 3px rgba(15,23,42,.05)' },
  kpiLabel: { fontSize: 11, color: '#64748b' },
  kpiValue: { fontSize: 22, fontWeight: 800, lineHeight: 1.1, marginTop: 4 },
  panel: { background: '#fff', border: '1px solid #e3e8f0', borderRadius: 18, boxShadow: '0 1px 3px rgba(15,23,42,.05)' },
  toolbar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', margin: '18px 20px 16px', paddingBottom: 16, borderBottom: '1px solid #e3e8f0' },
  search: { flex: 1, minWidth: 240, maxWidth: 380 },
  searchInput: { border: '1px solid #e3e8f0', background: '#f1f5fb', color: '#0f172a', borderRadius: 12, padding: '9px 12px', font: 'inherit', fontSize: 12 },
  select: { width: '100%', border: '1px solid #e3e8f0', background: '#f1f5fb', color: '#0f172a', borderRadius: 12, padding: '9px 12px', font: 'inherit', fontSize: 12 },
  tableWrap: { overflowX: 'auto' },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: { textAlign: 'left', padding: '11px 10px', fontSize: 11, color: '#64748b', borderBottom: '1px solid #e3e8f0', whiteSpace: 'nowrap' },
  tr: { borderBottom: '1px solid #e3e8f0' },
  td: { padding: '14px 10px', borderBottom: '1px solid #e3e8f0', verticalAlign: 'middle', fontSize: 12 },
  agentName: { display: 'flex', alignItems: 'flex-start', gap: 10 },
  avatar: { width: 36, height: 36, borderRadius: 12, display: 'grid', placeItems: 'center', fontWeight: 800, background: '#e7efff', color: '#2563eb', flex: 'none' },
  name: { fontSize: 13, fontWeight: 800, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  slug: { fontSize: 11, color: '#64748b', marginTop: 2 },
  chips: { display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 },
  chip: { padding: '4px 8px', borderRadius: 999, background: '#f1f5fb', fontSize: 10, color: '#334155', fontWeight: 700 },
  status: { padding: '4px 10px', borderRadius: 999, fontSize: 10, fontWeight: 800, display: 'inline-flex', gap: 6, alignItems: 'center' },
  statusActive: { background: '#e6f6f0', color: '#0f7b5a' },
  statusFrozen: { background: '#eef2ff', color: '#6d28d9' },
  actions: { display: 'flex', gap: 6, flexWrap: 'wrap' },
  actionBtn: { border: '1px solid #e3e8f0', background: '#fff', color: '#0f172a', padding: '6px 10px', borderRadius: 999, fontSize: 11, fontWeight: 700, cursor: 'pointer' },
  actionBtnPrimary: { background: '#2563eb', borderColor: '#2563eb', color: '#fff' },
  actionBtnWarn: { color: '#e11d48' },
  msg: { background: '#fef2f2', borderLeft: '4px solid #e11d48', color: '#991b1b', borderRadius: 8 },
}
