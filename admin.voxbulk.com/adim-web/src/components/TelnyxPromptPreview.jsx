import React, { useCallback, useState } from 'react'
import { apiFetch } from '../lib/api'

export default function TelnyxPromptPreview({
  previewUrl,
  resyncUrl,
  pullGreetingUrl,
  onPullGreeting,
  onResyncDone,
}) {
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(false)
  const [resyncing, setResyncing] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [msg, setMsg] = useState('')
  const [showLive, setShowLive] = useState(false)

  const loadPreview = useCallback(async () => {
    if (!previewUrl) return
    setLoading(true)
    setMsg('')
    try {
      const data = await apiFetch(previewUrl)
      setPreview(data)
    } catch (e) {
      setMsg(e?.message || 'Could not load Telnyx preview')
      setPreview(null)
    } finally {
      setLoading(false)
    }
  }, [previewUrl])

  async function resync() {
    if (!resyncUrl) return
    setResyncing(true)
    setMsg('')
    try {
      const result = await apiFetch(resyncUrl, { method: 'POST' })
      onResyncDone?.(result)
      await loadPreview()
      setMsg(result?.telnyx_sync_warning || 'Instructions pushed to Telnyx. Greeting pushes only when the greeting field is filled — then Save.')
    } catch (e) {
      setMsg(e?.message || 'Telnyx resync failed')
    } finally {
      setResyncing(false)
    }
  }

  async function pullGreeting() {
    if (!pullGreetingUrl) return
    setPulling(true)
    setMsg('')
    try {
      const result = await apiFetch(pullGreetingUrl, { method: 'POST' })
      const g = String(result?.telnyx_greeting || '').trim()
      onPullGreeting?.(g)
      await loadPreview()
      setMsg(g ? 'Copied live Telnyx greeting into the field above — click Save settings to keep it.' : 'No greeting on Telnyx.')
    } catch (e) {
      setMsg(e?.message || 'Could not pull greeting from Telnyx')
    } finally {
      setPulling(false)
    }
  }

  const inSync = preview?.in_sync === true
  const willPushGreeting = preview?.greeting_will_push === true || Boolean(preview?.saved_greeting)

  return (
    <div className='telnyxPreviewPanel' style={{ marginTop: 14, padding: 12, border: '1px solid var(--border)', borderRadius: 8 }}>
      <div className='cardHead' style={{ marginBottom: 8, padding: 0 }}>
        <h4 style={{ margin: 0 }}>What Telnyx has vs what we push</h4>
        {preview ? (
          <span className={`pill ${inSync ? 'p-green' : 'p-amber'}`} style={{ marginLeft: 8 }}>
            {inSync ? 'In sync' : 'Out of sync'}
          </span>
        ) : null}
      </div>
      <p className='muted' style={{ marginTop: 0, fontSize: 13 }}>
        <strong>Instructions</strong> = system prompt + KB. <strong>Greeting</strong> = first spoken line (separate Telnyx field).
        Resync updates instructions only unless the greeting field above is filled.
      </p>
      <div className='actions' style={{ gap: 8, flexWrap: 'wrap' }}>
        <button type='button' className='btn soft' onClick={loadPreview} disabled={loading}>
          {loading ? 'Loading…' : preview ? 'Refresh preview' : 'Check Telnyx'}
        </button>
        {resyncUrl ? (
          <button type='button' className='btn primary' onClick={resync} disabled={resyncing}>
            {resyncing ? 'Syncing…' : 'Resync instructions to Telnyx'}
          </button>
        ) : null}
        {pullGreetingUrl ? (
          <button type='button' className='btn soft' onClick={pullGreeting} disabled={pulling}>
            {pulling ? 'Pulling…' : 'Pull greeting from Telnyx'}
          </button>
        ) : null}
        {preview?.live_instructions ? (
          <button type='button' className='btn soft' onClick={() => setShowLive((v) => !v)}>
            {showLive ? 'Hide' : 'Show'} live instructions
          </button>
        ) : null}
      </div>
      {msg ? <p className='muted' style={{ marginTop: 8 }}>{msg}</p> : null}
      {preview ? (
        <div className='grid two' style={{ marginTop: 12, gap: 12 }}>
          <div className='note'>
            <strong>We will push (instructions)</strong>
            <p className='muted' style={{ margin: '4px 0 0' }}>{preview.planned_instructions_chars ?? 0} chars</p>
          </div>
          <div className='note'>
            <strong>We will push (greeting)</strong>
            <p style={{ margin: '4px 0 0', whiteSpace: 'pre-wrap' }}>
              {willPushGreeting ? (preview.planned_greeting || preview.saved_greeting || '—') : '(empty — Telnyx greeting unchanged on resync)'}
            </p>
          </div>
          {preview.live_instructions_chars > 0 || preview.live_greeting ? (
            <>
              <div className='note'>
                <strong>Live on Telnyx (instructions)</strong>
                <p className='muted' style={{ margin: '4px 0 0' }}>{preview.live_instructions_chars} chars</p>
              </div>
              <div className='note'>
                <strong>Live on Telnyx (greeting)</strong>
                <p style={{ margin: '4px 0 0', whiteSpace: 'pre-wrap' }}>{preview.live_greeting || '—'}</p>
              </div>
            </>
          ) : preview.live_error ? (
            <p className='muted' style={{ gridColumn: '1 / -1' }}>Live fetch: {preview.live_error}</p>
          ) : null}
        </div>
      ) : null}
      {showLive && preview?.live_instructions ? (
        <pre className='frontpagePromptPreview' style={{ marginTop: 12, maxHeight: 240, overflow: 'auto' }}>
          {preview.live_instructions}
        </pre>
      ) : null}
    </div>
  )
}
