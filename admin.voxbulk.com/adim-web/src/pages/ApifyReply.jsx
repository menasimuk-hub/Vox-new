import React, { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Textarea } from '@/components/ui/Textarea'
import './ai-team.css'

/**
 * Full thread + reply for Apify Tracking.
 * Routes:
 *   /marketing/apify/inbox/:messageId
 *   /marketing/apify/recipients/:recipientId/reply
 *   /marketing/apify/recipients/:recipientId  (sent email detail)
 */
export default function ApifyReply() {
  const { messageId, recipientId } = useParams()
  const location = useLocation()
  const kind = messageId ? 'inbox' : 'recipient'
  const id = messageId || recipientId
  const navigate = useNavigate()
  const composeMode = Boolean(messageId) || location.pathname.endsWith('/reply')

  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [banner, setBanner] = useState(null)
  const [meta, setMeta] = useState(null)
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [showCompose, setShowCompose] = useState(composeMode)

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
          name: m.full_name || m.from_email,
          company: m.company_name,
          campaign_name: m.campaign_name,
          inbound_subject: m.inbound_subject || m.subject,
          inbound_body: m.inbound_body || m.body_text,
          outbound_subject: m.outbound_subject,
          outbound_text: m.outbound_text,
          outbound_html: m.outbound_html,
          matched: m.matched,
          received_at: m.received_at,
          sent_at: null,
          status: m.matched ? 'replied' : 'inbox',
        })
        const base = (m.inbound_subject || m.subject || 'VoxBulk').trim() || 'VoxBulk'
        setSubject(base.toLowerCase().startsWith('re:') ? base : `Re: ${base}`)
        setBody('')
        setShowCompose(true)
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
          inbound_subject: r.inbound_subject || r.last_inbound_subject,
          inbound_body: r.inbound_body || r.last_inbound_body,
          outbound_subject: r.outbound_subject || r.last_outbound_subject,
          outbound_text: r.outbound_text || r.last_outbound_text,
          outbound_html: r.outbound_html || r.last_outbound_html,
          sent_at: r.sent_at,
          replied_at: r.replied_at,
          status: r.status,
        })
        const base = (r.inbound_subject || r.last_inbound_subject || r.campaign_subject || r.campaign_name || 'VoxBulk').trim() || 'VoxBulk'
        setSubject(base.toLowerCase().startsWith('re:') ? base : `Re: ${base}`)
        setBody('')
        setShowCompose(composeMode || Boolean(r.last_inbound_body || r.inbound_body || r.replied_at))
      }
    } catch (e) {
      setError(e?.message || 'Could not load message')
      setMeta(null)
    } finally {
      setLoading(false)
    }
  }, [kind, id, composeMode])

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
      setShowCompose(true)
      const tags = Array.isArray(data.kb_tags) ? data.kb_tags : []
      if (data.from_is_free_email || tags.includes('free_personal_email')) {
        showBanner('ok', 'AI reply ready · KB: free/personal email → advise company email signup (edit if needed)')
      } else if (tags.length) {
        showBanner('ok', `AI reply ready · KB: ${tags[0].replace(/_/g, ' ')} — edit if needed, then Send`)
      } else {
        showBanner('ok', 'Professional AI reply ready — edit if needed, then Send')
      }
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
      window.setTimeout(() => navigate('/marketing/apify?tab=tracking&filter=sent'), 600)
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
        <Button asChild variant="ghost">
          <Link to="/marketing/apify?tab=tracking&filter=sent">← Back to Sent</Link>
        </Button>
        <p style={{ color: 'crimson', marginTop: 16 }}>{error || 'Message not found'}</p>
      </div>
    )
  }

  const hasOutbound = Boolean(meta.outbound_html || meta.outbound_text || meta.outbound_subject)
  const hasInbound = Boolean(meta.inbound_body || meta.inbound_subject)

  return (
    <div className="ai-team-page">
      <div className="ait-topbar">
        <div className="ait-topbar-left">
          <div className="ait-logo-mark">AP</div>
          <div>
            <div className="ait-page-title">{hasInbound ? 'Conversation' : 'Sent email'}</div>
            <div className="ait-page-sub">{meta.name || meta.email}</div>
          </div>
        </div>
        <div className="ait-topbar-right">
          <Button asChild variant="ghost" size="sm">
            <Link to="/marketing/apify?tab=tracking&filter=sent">← Sent</Link>
          </Button>
          <Button asChild variant="ghost" size="sm">
            <Link to="/marketing/apify?tab=tracking">Tracking</Link>
          </Button>
          {kind === 'inbox' && (
            <Button variant="destructive" size="sm" disabled={!!busy} onClick={deleteMessage}>
              <i className="ti ti-trash" style={{ marginRight: 6 }} />Delete
            </Button>
          )}
        </div>
      </div>

      {banner && <div className={`ait-msg-banner ${banner.type}`}>{banner.text}</div>}
      {error && !banner && <div className="ait-msg-banner err">{error}</div>}

      <div className="ait-thread-page">
        <Panel className="ait-thread-meta">
          <div className="p-3.5">
            <div className="ait-fg-2" style={{ marginBottom: 0 }}>
              <div>
                <div className="ait-thread-label">Contact</div>
                <div className="ait-contact-name">{meta.name || '—'}</div>
                <div className="ait-contact-email">{meta.email}</div>
              </div>
              <div>
                <div className="ait-thread-label">Campaign</div>
                <div>{meta.campaign_name || '—'}</div>
                {meta.company ? <div className="ait-contact-email">{meta.company}</div> : null}
              </div>
            </div>
          </div>
        </Panel>

        {hasOutbound && (
          <Panel
            title="What you sent"
            action={meta.sent_at ? <span className="text-xs text-muted-foreground">{new Date(meta.sent_at).toLocaleString()}</span> : null}
          >
            <div className="space-y-3">
              <div className="ait-thread-subject">{meta.outbound_subject || '(no subject)'}</div>
              {meta.outbound_html ? (
                <div className="ait-email-client-frame">
                  <iframe title="sent-email" className="ait-html-preview" srcDoc={meta.outbound_html} />
                </div>
              ) : (
                <pre className="ait-thread-plain">{meta.outbound_text || '—'}</pre>
              )}
            </div>
          </Panel>
        )}

        {hasInbound ? (
          <Panel
            title="Their reply"
            action={
              meta.replied_at || meta.received_at ? (
                <span className="text-xs text-muted-foreground">
                  {new Date(meta.replied_at || meta.received_at).toLocaleString()}
                </span>
              ) : null
            }
          >
            <div className="ait-inbound-box">
              <strong>{meta.inbound_subject || '(no subject)'}</strong>
              <pre>{meta.inbound_body || '—'}</pre>
            </div>
          </Panel>
        ) : (
          <Panel>
            <p className="m-0 text-xs text-muted-foreground">No reply received yet for this contact.</p>
          </Panel>
        )}

        <Panel
          title="Your response"
          action={
            !showCompose && (
              <Button size="sm" variant="outline" onClick={() => setShowCompose(true)}>Compose reply</Button>
            )
          }
        >
          {showCompose && (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="reply-to">To</Label>
                <Input id="reply-to" value={meta.email || ''} readOnly />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="reply-subject">Subject</Label>
                <Input id="reply-subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="reply-message">Message</Label>
                <Textarea
                  id="reply-message"
                  className="min-h-[180px]"
                  value={body}
                  placeholder="Click AI Generate Reply for a professional draft, or type your own"
                  onChange={(e) => setBody(e.target.value)}
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button disabled={!!busy} onClick={generateAiReply}>
                  <i className="ti ti-sparkles" style={{ marginRight: 8 }} />
                  {busy === 'ai' ? 'Generating…' : 'AI Generate Reply'}
                </Button>
                <Button variant="outline" disabled={!!busy || !body.trim()} onClick={sendReply}>
                  <i className="ti ti-send" style={{ marginRight: 8 }} />
                  {busy === 'send' ? 'Sending…' : 'Send reply'}
                </Button>
              </div>
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}
