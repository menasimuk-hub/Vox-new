import React, { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import './ai-team.css'

/**
 * Full-page reply for Apify Tracking.
 * Routes:
 *   /marketing/apify/inbox/:messageId
 *   /marketing/apify/recipients/:recipientId/reply
 */
export default function ApifyReply() {
  const { messageId, recipientId } = useParams()
  const kind = messageId ? 'inbox' : 'recipient'
  const id = messageId || recipientId
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [banner, setBanner] = useState(null)
  const [meta, setMeta] = useState(null)
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')

  const showBanner = (type, text) => {
    setBanner({ type, text })
    window.setTimeout(() => setBanner(null), 5000)
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      if (kind === 'inbox') {
        const data = await apiFetch(`/admin/ai-team/tracking/inbox/${id}`)
        const m = data.message || data
        setMeta({
          kind: 'inbox',
          id: m.id,
          email: m.from_email,
          name: m.from_email,
          inbound_subject: m.subject,
          inbound_body: m.body_text,
          matched: m.matched,
          received_at: m.received_at,
        })
        const base = (m.subject || 'VoxBulk').trim() || 'VoxBulk'
        setSubject(base.toLowerCase().startsWith('re:') ? base : `Re: ${base}`)
        setBody('')
      } else {
        const data = await apiFetch(`/admin/ai-team/tracking/recipients/${id}`)
        const r = data.recipient || data
        setMeta({
          kind: 'recipient',
          id: r.id,
          email: r.email,
          name: r.full_name || r.email,
          company: r.company_name,
          campaign_name: r.campaign_name,
          inbound_subject: r.last_inbound_subject,
          inbound_body: r.last_inbound_body,
        })
        const base = (r.last_inbound_subject || r.campaign_subject || r.campaign_name || 'VoxBulk').trim() || 'VoxBulk'
        setSubject(base.toLowerCase().startsWith('re:') ? base : `Re: ${base}`)
        setBody('')
      }
    } catch (e) {
      setError(e?.message || 'Could not load message')
      setMeta(null)
    } finally {
      setLoading(false)
    }
  }, [kind, id])

  useEffect(() => {
    load()
  }, [load])

  const generateAiReply = async () => {
    if (!id) return
    setBusy('ai')
    setError('')
    try {
      const path = kind === 'inbox'
        ? `/admin/ai-team/tracking/inbox/${id}/ai-reply`
        : `/admin/ai-team/tracking/recipients/${id}/ai-reply`
      const data = await apiFetch(path, { method: 'POST' })
      if (data.subject) setSubject(data.subject)
      setBody(data.body || '')
      showBanner('ok', 'Professional AI reply ready — edit if needed, then Send')
    } catch (e) {
      setError(e?.message || 'AI generate failed')
      showBanner('err', e?.message || 'AI generate failed')
    } finally {
      setBusy('')
    }
  }

  const sendReply = async () => {
    if (!id) return
    if (!body.trim()) {
      showBanner('err', 'Enter a reply message (or click AI Generate Reply)')
      return
    }
    setBusy('send')
    setError('')
    try {
      const path = kind === 'inbox'
        ? `/admin/ai-team/tracking/inbox/${id}/reply`
        : `/admin/ai-team/tracking/recipients/${id}/reply`
      const data = await apiFetch(path, {
        method: 'POST',
        body: JSON.stringify({ body, subject }),
      })
      showBanner('ok', data.message || 'Reply sent')
      window.setTimeout(() => navigate('/marketing/apify?tab=tracking'), 600)
    } catch (e) {
      setError(e?.message || 'Send failed')
      showBanner('err', e?.message || 'Send failed')
    } finally {
      setBusy('')
    }
  }

  const deleteMessage = async () => {
    if (kind !== 'inbox' || !id) return
    if (!window.confirm(`Delete inbox message from ${meta?.email || 'unknown'}?`)) return
    setBusy('del')
    try {
      await apiFetch(`/admin/ai-team/tracking/inbox/${id}`, { method: 'DELETE' })
      navigate('/marketing/apify?tab=tracking')
    } catch (e) {
      showBanner('err', e?.message || 'Delete failed')
      setBusy('')
    }
  }

  if (loading) {
    return (
      <div className="ai-team-page" style={{ padding: 24 }}>
        <div className="muted">Loading message…</div>
      </div>
    )
  }

  if (!meta) {
    return (
      <div className="ai-team-page" style={{ padding: 24, maxWidth: 720 }}>
        <Link to="/marketing/apify?tab=tracking">← Back to Tracking</Link>
        <p style={{ color: 'crimson', marginTop: 16 }}>{error || 'Message not found'}</p>
      </div>
    )
  }

  return (
    <div className="ai-team-page">
      <div className="ait-topbar">
        <div className="ait-topbar-left">
          <div className="ait-logo-mark">AP</div>
          <div>
            <div className="ait-page-title">Reply</div>
            <div className="ait-page-sub">{meta.name || meta.email}</div>
          </div>
        </div>
        <div className="ait-topbar-right">
          <Link className="ait-btn ghost sm" to="/marketing/apify?tab=tracking">← Tracking</Link>
          {kind === 'inbox' && (
            <button type="button" className="ait-btn danger sm" disabled={!!busy} onClick={deleteMessage}>
              <i className="ti ti-trash" style={{ marginRight: 6 }} />Delete
            </button>
          )}
        </div>
      </div>

      {banner && <div className={`ait-msg-banner ${banner.type}`}>{banner.text}</div>}
      {error && !banner && <div className="ait-msg-banner err">{error}</div>}

      <div className="ait-card" style={{ maxWidth: 860, margin: '0 auto' }}>
        <div className="ait-card-hdr">
          <span className="ait-card-title">
            {kind === 'inbox' ? 'Inbox message' : 'Received reply'} · compose response
          </span>
        </div>
        <div className="ait-card-body">
          <div className="ait-field">
            <label>To</label>
            <input value={meta.email || ''} readOnly />
          </div>
          {(meta.company || meta.campaign_name) && (
            <p className="ait-hint" style={{ marginTop: 0 }}>
              {[meta.company, meta.campaign_name].filter(Boolean).join(' · ')}
            </p>
          )}

          <div className="ait-field">
            <label>Received message</label>
            <div className="ait-inbound-box">
              {meta.inbound_subject ? <strong>{meta.inbound_subject}</strong> : <strong>(no subject)</strong>}
              <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto' }}>
                {meta.inbound_body || '—'}
              </pre>
            </div>
          </div>

          <div className="ait-field">
            <label>Subject</label>
            <input value={subject} onChange={(e) => setSubject(e.target.value)} />
          </div>

          <div className="ait-field">
            <label>Your reply</label>
            <textarea
              style={{ minHeight: 200 }}
              value={body}
              placeholder="Click “AI Generate Reply” for a professional draft, or type your own…"
              onChange={(e) => setBody(e.target.value)}
            />
          </div>

          <div className="ait-btn-row" style={{ flexWrap: 'wrap' }}>
            <button
              type="button"
              className="ait-btn primary"
              disabled={!!busy}
              onClick={generateAiReply}
              title="Generate a professional reply with AI"
            >
              <i className="ti ti-sparkles" style={{ marginRight: 8 }} />
              {busy === 'ai' ? 'Generating…' : 'AI Generate Reply'}
            </button>
            <button type="button" className="ait-btn" disabled={!!busy || !body.trim()} onClick={sendReply}>
              <i className="ti ti-send" style={{ marginRight: 8 }} />
              {busy === 'send' ? 'Sending…' : 'Send reply'}
            </button>
            <button type="button" className="ait-btn ghost" disabled={!!busy} onClick={() => navigate('/marketing/apify?tab=tracking')}>
              Cancel
            </button>
          </div>
          <p className="ait-hint" style={{ marginTop: 12 }}>
            AI writes a professional draft you can edit before sending. Requires DeepSeek configured in Integrations.
          </p>
        </div>
      </div>
    </div>
  )
}
