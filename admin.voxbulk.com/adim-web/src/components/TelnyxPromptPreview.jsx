import React, { useCallback, useState } from 'react'
import { apiFetch } from '../lib/api'

export default function TelnyxPromptPreview({ previewUrl, resyncUrl, onResyncDone }) {
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(false)
  const [resyncing, setResyncing] = useState(false)
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
      setMsg('Pushed to Telnyx. Compare planned vs live below.')
    } catch (e) {
      setMsg(e?.message || 'Telnyx resync failed')
    } finally {
      setResyncing(false)
    }
  }

  const inSync = preview?.in_sync === true

  return (
    <div className='telnyxPreviewPanel' style={{ marginTop: 14, padding: 12, border: '1px solid var(--border)', borderRadius: 8 }}>
      <div className='cardHead' style={{ marginBottom: 8, padding: 0 }}>
        <h4 style={{ margin: 0 }}>What Telnyx receives</h4>
        {preview ? (
          <span className={`pill ${inSync ? 'p-green' : 'p-amber'}`} style={{ marginLeft: 8 }}>
            {inSync ? 'In sync' : 'Out of sync'}
          </span>
        ) : null}
      </div>
      <p className='muted' style={{ marginTop: 0, fontSize: 13 }}>
        Telnyx stores <strong>instructions</strong> (system prompt + KB) and <strong>greeting</strong> (first spoken line) as separate fields.
        The textarea above is instructions only — greeting is derived and synced separately.
      </p>
      <div className='actions' style={{ gap: 8, flexWrap: 'wrap' }}>
        <button type='button' className='btn soft' onClick={loadPreview} disabled={loading}>
          {loading ? 'Loading…' : preview ? 'Refresh preview' : 'Check Telnyx'}
        </button>
        {resyncUrl ? (
          <button type='button' className='btn primary' onClick={resync} disabled={resyncing}>
            {resyncing ? 'Syncing…' : 'Resync to Telnyx now'}
          </button>
        ) : null}
        {preview?.live_instructions ? (
          <button type='button' className='btn soft' onClick={() => setShowLive((v) => !v)}>
            {showLive ? 'Hide' : 'Show'} live Telnyx text
          </button>
        ) : null}
      </div>
      {msg ? <p className='muted' style={{ marginTop: 8 }}>{msg}</p> : null}
      {preview ? (
        <div className='grid two' style={{ marginTop: 12, gap: 12 }}>
          <div className='note'>
            <strong>Planned instructions</strong>
            <p className='muted' style={{ margin: '4px 0 0' }}>
              {preview.planned_instructions_chars ?? 0} chars
              {preview.saved_system_prompt_chars != null ? ` · saved script ${preview.saved_system_prompt_chars} chars` : ''}
              {preview.saved_prompt_chars != null ? ` · saved prompt ${preview.saved_prompt_chars} chars` : ''}
            </p>
          </div>
          <div className='note'>
            <strong>Planned greeting</strong>
            <p style={{ margin: '4px 0 0', whiteSpace: 'pre-wrap' }}>{preview.planned_greeting || '—'}</p>
            <p className='muted' style={{ margin: '4px 0 0' }}>
              {preview.planned_greeting_chars ?? 0} chars · not in the instructions textarea
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
