import React, { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../../lib/api'

const REMOTE_AUDIO_ID = 'voxbulk-agent-test-remote-audio'
const ACTIVE_TIMEOUT_MS = 45_000

function callLooksLive(call) {
  const state = String(call?.state || '').toLowerCase()
  if (state === 'active' || state === 'held' || state === 'speaking' || state === 'answered') {
    return true
  }
  const tracks = call?.remoteStream?.getAudioTracks?.() || []
  return tracks.some((t) => t.readyState === 'live' && t.enabled)
}

function normalizeTelnyxCustomHeaders(raw) {
  if (!raw) return []
  if (Array.isArray(raw)) {
    return raw.filter((h) => String(h?.name || '').trim() && String(h?.value || '').trim())
  }
  return Object.entries(raw)
    .map(([name, value]) => {
      const clean = String(value || '').trim()
      if (!clean) return null
      const headerName = name.startsWith('X-') ? name : `X-${name}`
      return { name: headerName, value: clean }
    })
    .filter(Boolean)
}

async function loadTelnyxRtc() {
  const mod = await import('@telnyx/webrtc')
  return mod.TelnyxRTC
}

export default function AgentTestCallModal({ open, onClose, agentId, testScript, agentLabel }) {
  const [phase, setPhase] = useState('idle')
  const [statusLine, setStatusLine] = useState('')
  const [error, setError] = useState('')
  const telnyxRef = useRef(null)
  const telnyxCallRef = useRef(null)
  const telnyxNotificationRef = useRef(null)
  const localStreamRef = useRef(null)
  const activeTimerRef = useRef(null)

  const cleanupRtc = useCallback(() => {
    if (activeTimerRef.current) {
      clearTimeout(activeTimerRef.current)
      activeTimerRef.current = null
    }
    try {
      const client = telnyxRef.current
      const handler = telnyxNotificationRef.current
      if (client && handler) {
        client.off?.('telnyx.notification', handler)
      }
      telnyxNotificationRef.current = null
      telnyxCallRef.current?.hangup?.()
      telnyxRef.current?.disconnect?.()
    } catch {
      /* ignore */
    }
    telnyxRef.current = null
    telnyxCallRef.current = null
    localStreamRef.current?.getTracks().forEach((t) => t.stop())
    localStreamRef.current = null
  }, [])

  useEffect(() => {
    if (!open) {
      cleanupRtc()
      setPhase('idle')
      setStatusLine('')
      setError('')
    }
  }, [open, cleanupRtc])

  useEffect(() => () => cleanupRtc(), [cleanupRtc])

  const attachRemoteAudio = (call) => {
    const el = document.getElementById(REMOTE_AUDIO_ID)
    const stream = call?.remoteStream ?? null
    if (!el || !stream) return
    if (el.srcObject !== stream) el.srcObject = stream
    el.muted = false
    el.volume = 1
    void el.play().catch(() => {})
  }

  const startTestCall = async () => {
    setError('')
    setPhase('connecting')
    setStatusLine('Requesting microphone…')
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('Microphone not supported in this browser — try Chrome or Edge.')
      }
      const micStream = await navigator.mediaDevices.getUserMedia({ audio: true })
      localStreamRef.current = micStream

      setStatusLine('Syncing agent to Telnyx…')
      const start = await apiFetch(`/admin/agents/${encodeURIComponent(agentId)}/test-webrtc`, {
        method: 'POST',
        body: JSON.stringify({
          test_script: testScript || undefined,
          candidate_name: 'Test User',
        }),
      })
      if (!start?.agent_id) throw new Error('Telnyx assistant is not available')
      if (start.web_calls_enabled === false) {
        throw new Error('Web calls are not enabled for this Telnyx assistant')
      }

      const TelnyxRTC = await loadTelnyxRtc()
      const client = new TelnyxRTC({
        anonymous_login: { target_type: 'ai_assistant', target_id: start.agent_id },
      })
      telnyxRef.current = client

      setStatusLine('Connecting to VoxBulk…')
      await new Promise((resolve, reject) => {
        const t = window.setTimeout(() => reject(new Error('Connection timed out')), 30_000)
        client.on('telnyx.ready', () => {
          window.clearTimeout(t)
          resolve()
        })
        client.on('telnyx.error', (err) => {
          window.clearTimeout(t)
          reject(new Error(err?.message || 'Telnyx connection failed'))
        })
        client.connect()
      })

      let wentLive = false
      const onNotification = (notification) => {
        if (notification?.type === 'userMediaError') {
          setError(notification.errorMessage || 'Microphone error')
          return
        }
        if (notification?.type !== 'callUpdate' || !notification.call) return
        const call = notification.call
        telnyxCallRef.current = call
        attachRemoteAudio(call)
        if (call.state === 'ringing' || call.state === 'new' || call.state === 'answering') {
          setPhase('aiJoining')
          setStatusLine('AI agent is joining…')
        }
        if (callLooksLive(call) && !wentLive) {
          wentLive = true
          if (activeTimerRef.current) clearTimeout(activeTimerRef.current)
          setPhase('live')
          setStatusLine('Connected — speak now')
          attachRemoteAudio(call)
        }
        if (call.state === 'hangup' || call.state === 'destroy' || call.state === 'destroyed') {
          cleanupRtc()
          setPhase('ended')
          setStatusLine('Call ended')
        }
      }
      telnyxNotificationRef.current = onNotification
      client.on('telnyx.notification', onNotification)

      setPhase('aiJoining')
      setStatusLine('Calling AI agent…')
      const codecs = RTCRtpReceiver.getCapabilities('audio')?.codecs || []
      const opus = codecs.find((c) => c.mimeType.toLowerCase().includes('opus'))
      const call = client.newCall({
        destinationNumber: '',
        audio: true,
        video: false,
        remoteElement: REMOTE_AUDIO_ID,
        preferred_codecs: opus ? [opus] : undefined,
        customHeaders: normalizeTelnyxCustomHeaders(start.custom_headers),
      })
      telnyxCallRef.current = call
      attachRemoteAudio(call)

      activeTimerRef.current = setTimeout(() => {
        if (!wentLive) {
          cleanupRtc()
          setPhase('idle')
          setError('The AI agent did not answer — check Telnyx assistant voice settings and try again.')
        }
      }, ACTIVE_TIMEOUT_MS)
    } catch (e) {
      cleanupRtc()
      setPhase('idle')
      setError(e instanceof Error ? e.message : 'Test call failed')
    }
  }

  const endCall = () => {
    cleanupRtc()
    setPhase('ended')
    setStatusLine('')
  }

  if (!open) return null

  return (
    <div className="waSurveyModalBackdrop" role="dialog" aria-modal="true">
      <audio id={REMOTE_AUDIO_ID} autoPlay playsInline className="hidden" />
      <div className="waSurveyModal" style={{ maxWidth: '480px' }}>
        <div className="waSurveyModalHead">
          <div>
            <h2>Test agent — {agentLabel || 'Agent'}</h2>
            <p className="muted">Browser WebRTC call via Telnyx (same as interview meeting room)</p>
          </div>
          <button type="button" className="agentsBtn ghost" onClick={() => { endCall(); onClose() }} aria-label="Close">
            <i className="ti ti-x" />
          </button>
        </div>
        <div className="waSurveyModalBody">
          {error ? <div className="agentsMsg is-error">{error}</div> : null}
          {phase === 'idle' || phase === 'ended' ? (
            <p className="agentsEditNote">
              Place a short browser call using the test script below. The agent prompt is synced to Telnyx before connecting.
            </p>
          ) : null}
          {phase === 'connecting' || phase === 'aiJoining' ? (
            <p className="agentsEditNote">{statusLine || 'Connecting…'}</p>
          ) : null}
          {phase === 'live' ? (
            <p className="agentsEditNote" style={{ color: 'var(--success, #15803d)' }}>
              {statusLine || 'Connected'}
            </p>
          ) : null}
        </div>
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', padding: '16px 20px', borderTop: '1px solid var(--border, #dde3ea)' }}>
          {phase === 'live' ? (
            <button type="button" className="agentsBtn warn" onClick={endCall}>
              <i className="ti ti-phone-off" /> End call
            </button>
          ) : phase === 'connecting' || phase === 'aiJoining' ? (
            <button type="button" className="agentsBtn" disabled>
              Connecting…
            </button>
          ) : (
            <button type="button" className="agentsBtn primary" onClick={() => void startTestCall()}>
              <i className="ti ti-phone" /> Start test call
            </button>
          )}
          <button type="button" className="agentsBtn" onClick={() => { endCall(); onClose() }}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
