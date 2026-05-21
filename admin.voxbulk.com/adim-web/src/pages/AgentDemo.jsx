import React, { useEffect, useMemo, useRef, useState } from 'react'
import Vapi from '@vapi-ai/web'
import { apiFetch, resolveApiUrl, resolveApiWebSocketUrl } from '../lib/api'

const DEFAULT_AGENT_SLUG = 'vox-sales'
const FINAL_SEND_DELAY_MS = 150
const EARLY_PARTIAL_DELAY_MS = 350
const EARLY_PARTIAL_MIN_WORDS = 5
const BARGE_IN_MIN_WORDS = 2
const TEST_PHRASES = [
  'What does Vox Sales do?',
  'We are a 200 person company with manual operations.',
  'Can you help qualify leads?',
  'Tell me briefly how you help businesses.',
]
const PROVIDERS = [
  { id: 'groq', label: 'Groq', voiceMode: 'Groq LLM' },
  { id: 'deepseek', label: 'DeepSeek', voiceMode: 'DeepSeek LLM' },
  { id: 'vapi', label: 'Vapi', voiceMode: 'Vapi voice call' },
]
const STT_PROVIDERS = [
  { id: 'deepgram', label: 'Deepgram realtime' },
  { id: 'elevenlabs', label: 'ElevenLabs Scribe' },
  { id: 'groq', label: 'Groq Whisper' },
]
const TTS_PROVIDERS = [
  { id: 'cartesia', label: 'Cartesia' },
  { id: 'elevenlabs', label: 'ElevenLabs' },
  { id: 'groq_orpheus', label: 'Groq Orpheus' },
]
const GROQ_ORPHEUS_VOICES = ['austin', 'hannah', 'diana', 'daniel', 'autumn', 'troy']

const DEFAULT_VOX_CALL_PROMPT = `You are Vox, a friendly, professional British sales representative for VOXBULK.

You are speaking on a live browser voice call, so keep replies short, natural, and easy to listen to.

Call style:
- Sound warm, calm, confident, and human.
- Use British English.
- Reply in one or two short sentences.
- Ask one main question at a time.
- Do not sound scripted, robotic, or pushy.
- Do not invent prices or unavailable features.

Conversation flow:
1. Greet naturally and introduce yourself as Vox from VOXBULK.
2. Ask for the caller's first name.
3. Ask for their best email address.
4. Ask what company or clinic they are with.
5. Ask what they would like help improving.

When relevant, explain VOXBULK simply:
VOXBULK helps clinics and teams recover missed opportunities through rebooking, missed-call recovery, faster patient follow-up, and reduced admin workload.

If the caller gives a short answer, acknowledge it briefly and continue with the next natural question.`
const DEMO_VOICES = [
  { id: 'en-GB-RyanNeural', label: 'Ryan - UK male (default)' },
  { id: 'en-GB-ThomasNeural', label: 'Thomas - UK male backup' },
]

function slugify(raw) {
  return String(raw || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function speechRecognitionCtor() {
  if (typeof window === 'undefined') return null
  return window.SpeechRecognition || window.webkitSpeechRecognition || null
}

function dataUrlFromAudio(audioB64, mime) {
  if (!audioB64) return ''
  return `data:${mime || 'audio/wav'};base64,${audioB64}`
}

function streamUrl(path) {
  return resolveApiUrl(path)
}

function adminToken() {
  if (typeof window === 'undefined') return ''
  return localStorage.getItem('retover_admin_access_token') || localStorage.getItem('access_token') || localStorage.getItem('retover_access_token') || ''
}

function parseSseBlock(block) {
  let event = 'message'
  const dataLines = []
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return null
  try {
    return { event, data: JSON.parse(dataLines.join('\n')) }
  } catch {
    return { event, data: { raw: dataLines.join('\n') } }
  }
}

function errorText(e) {
  const detail = e?.data?.detail
  if (detail?.message) return detail.message
  if (detail?.openai_payload) return JSON.stringify(detail.openai_payload)
  if (detail && typeof detail === 'object') return JSON.stringify(detail)
  return e?.message || 'Backend call failed'
}

function providerLabel(providerId) {
  return PROVIDERS.find((provider) => provider.id === providerId)?.label || providerId
}

export default function AgentDemo() {
  const recognitionRef = useRef(null)
  const audioRef = useRef(null)
  const audioContextRef = useRef(null)
  const audioUnlockedRef = useRef(false)
  const finalTranscriptRef = useRef('')
  const pendingFinalRef = useRef('')
  const partialSendTimerRef = useRef(null)
  const earlySentRef = useRef(false)
  const bargeInTranscriptRef = useRef('')
  const callActiveRef = useRef(false)
  const processingRef = useRef(false)
  const sendTimerRef = useRef(null)
  const idleTimerRef = useRef(null)
  const conversationEndRef = useRef(null)
  const speechFinalReadyAtRef = useRef(0)
  const playbackTimingRef = useRef(null)
  const streamAbortRef = useRef(null)
  const audioQueueRef = useRef([])
  const audioPlayingRef = useRef(false)
  const vapiRef = useRef(null)
  const vapiActiveRef = useRef(false)
  const activeRequestIdRef = useRef(0)
  const recognitionActiveRef = useRef(false)
  const recognitionStartingRef = useRef(false)
  const recognitionSessionRef = useRef(0)
  const recognitionRestartTimerRef = useRef(null)
  const sttRecorderRef = useRef(null)
  const sttRecorderChunksRef = useRef([])
  const sttRecorderStreamRef = useRef(null)
  const deepgramSocketRef = useRef(null)
  const deepgramRecorderRef = useRef(null)
  const deepgramStreamRef = useRef(null)
  const realtimeSocketRef = useRef(null)
  const realtimeRecorderRef = useRef(null)
  const realtimeStreamRef = useRef(null)
  const realtimePlaybackRequestIdRef = useRef(0)
  const statusRef = useRef('idle')
  const micReadyAtRef = useRef(0)
  const recoveryStartedAtRef = useRef(0)
  const [status, setStatus] = useState('idle')
  const [callActive, setCallActive] = useState(false)
  const [liveTranscript, setLiveTranscript] = useState('')
  const [textInput, setTextInput] = useState('')
  const [messages, setMessages] = useState([])
  const [latestAudioSrc, setLatestAudioSrc] = useState('')
  const [latestAudioBytes, setLatestAudioBytes] = useState(0)
  const [playbackBlocked, setPlaybackBlocked] = useState(false)
  const [audioUnlocked, setAudioUnlocked] = useState(false)
  const [error, setError] = useState('')
  const [agentSlug, setAgentSlug] = useState(DEFAULT_AGENT_SLUG)
  const [agentLabel, setAgentLabel] = useState('Vox Sales')
  const [agents, setAgents] = useState([])
  const [currentAgent, setCurrentAgent] = useState(null)
  const [callPrompt, setCallPrompt] = useState('')
  const [promptMessage, setPromptMessage] = useState('')
  const [promptSaving, setPromptSaving] = useState(false)
  const [latestTimings, setLatestTimings] = useState(null)
  const [streamConnected, setStreamConnected] = useState(false)
  const [chunksReceived, setChunksReceived] = useState(0)
  const [audioQueueLength, setAudioQueueLength] = useState(0)
  const [demoVoice, setDemoVoice] = useState('en-GB-RyanNeural')
  const [speechSpeed, setSpeechSpeed] = useState('normal')
  const [turnTakingMetrics, setTurnTakingMetrics] = useState({})
  const [voiceMode, setVoiceMode] = useState('streaming')
  const [sttProvider, setSttProvider] = useState('deepgram')
  const [selectedProvider, setSelectedProvider] = useState('groq')
  const [ttsProvider, setTtsProvider] = useState('cartesia')
  const [groqTtsVoice, setGroqTtsVoice] = useState('austin')
  const [cartesiaVoiceId, setCartesiaVoiceId] = useState('')
  const [elevenLabsVoiceId, setElevenLabsVoiceId] = useState('')
  const [elevenLabsSettings, setElevenLabsSettings] = useState({
    stability: '',
    similarity_boost: '',
    style: '',
    speed: '',
    speaker_boost: true,
  })
  const [moduleTestText, setModuleTestText] = useState('Hello, this is a quick text to speech test.')
  const [moduleResult, setModuleResult] = useState({})
  const [sttRecording, setSttRecording] = useState(false)
  const [providerConfig, setProviderConfig] = useState(null)
  const [vapiActive, setVapiActive] = useState(false)
  const [telnyxPhone, setTelnyxPhone] = useState('')
  const [telnyxCall, setTelnyxCall] = useState(null)
  const [telnyxCalling, setTelnyxCalling] = useState(false)
  const telnyxPollRef = useRef(null)
  const [conversationOpen, setConversationOpen] = useState(false)

  const recognitionSupported = useMemo(() => Boolean(speechRecognitionCtor()), [])
  const listening = status === 'listening'
  const latencySummary = useMemo(() => {
    const firstText = latestTimings?.first_text_latency_ms ?? latestTimings?.backend?.first_text_ms ?? latestTimings?.backend?.first_openai_token
    const firstAudio = latestTimings?.first_audio_latency_ms ?? latestTimings?.backend?.first_audio_ms
    const total = latestTimings?.total_completion_ms ?? latestTimings?.backend?.completed_ms ?? latestTimings?.backend?.full_complete
    return {
      firstText,
      firstAudio,
      total,
      label: latestTimings
        ? `First text: ${firstText != null ? `${(firstText / 1000).toFixed(1)}s` : 'waiting'} | First audio: ${firstAudio != null ? `${(firstAudio / 1000).toFixed(1)}s` : 'waiting'} | Total: ${total != null ? `${(total / 1000).toFixed(1)}s` : 'waiting'}`
        : 'No latency data yet. Send a test turn or start a call.',
    }
  }, [latestTimings])

  const setCallState = (next) => {
    statusRef.current = next
    setStatus(next)
  }

  const logAudio = (stage, details = {}) => {
    console.info('vox_audio_playback', {
      stage,
      status: statusRef.current,
      queue_length: audioQueueRef.current.length,
      audio_unlocked: audioUnlockedRef.current,
      ...details,
    })
  }

  const logRealtime = (stage, details = {}) => {
    console.info('vox_realtime_pipeline', {
      stage,
      status: statusRef.current,
      processing: processingRef.current,
      audio_playing: audioPlayingRef.current,
      ...details,
    })
  }

  const unlockAudioPlayback = async (source = 'user-gesture') => {
    if (typeof window === 'undefined') return false
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext
    try {
      if (AudioContextCtor && !audioContextRef.current) {
        audioContextRef.current = new AudioContextCtor()
      }
      if (audioContextRef.current?.state === 'suspended') {
        await audioContextRef.current.resume()
      }
    } catch (e) {
      logAudio('audio_context_resume_failed', { source, message: e?.message || String(e) })
    }

    try {
      const silent = new Audio('data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQQAAAAAAA==')
      silent.muted = true
      silent.volume = 0
      silent.playsInline = true
      await silent.play()
      silent.pause()
      audioUnlockedRef.current = true
      setAudioUnlocked(true)
      setPlaybackBlocked(false)
      logAudio('unlocked', { source, audio_context_state: audioContextRef.current?.state || 'none' })
      return true
    } catch (e) {
      const unlockedByContext = audioContextRef.current?.state === 'running'
      audioUnlockedRef.current = unlockedByContext
      setAudioUnlocked(unlockedByContext)
      logAudio('unlock_failed', { source, message: e?.message || String(e), audio_context_state: audioContextRef.current?.state || 'none' })
      return unlockedByContext
    }
  }

  const resetIdleTimer = () => {
    if (idleTimerRef.current) window.clearTimeout(idleTimerRef.current)
    if (!callActiveRef.current) return
    idleTimerRef.current = window.setTimeout(() => {
      if (callActiveRef.current && !processingRef.current) {
        hangUp('ended')
        setError('Call ended after a long silent pause.')
      }
    }, 90000)
  }

  const clearTimers = () => {
    if (sendTimerRef.current) window.clearTimeout(sendTimerRef.current)
    if (idleTimerRef.current) window.clearTimeout(idleTimerRef.current)
    if (recognitionRestartTimerRef.current) window.clearTimeout(recognitionRestartTimerRef.current)
    sendTimerRef.current = null
    idleTimerRef.current = null
    recognitionRestartTimerRef.current = null
  }

  const stopDeepgramStream = () => {
    if (partialSendTimerRef.current) window.clearTimeout(partialSendTimerRef.current)
    partialSendTimerRef.current = null
    try {
      deepgramRecorderRef.current?.stop?.()
    } catch {
      // ignore recorder cleanup races
    }
    try {
      deepgramSocketRef.current?.send?.('close')
      deepgramSocketRef.current?.close?.()
    } catch {
      // ignore websocket cleanup races
    }
    try {
      deepgramStreamRef.current?.getTracks?.().forEach((track) => track.stop())
    } catch {
      // ignore stream cleanup races
    }
    deepgramRecorderRef.current = null
    deepgramSocketRef.current = null
    deepgramStreamRef.current = null
  }

  const stopRealtimeVoiceStream = () => {
    try {
      realtimeRecorderRef.current?.stop?.()
    } catch {
      // ignore recorder cleanup races
    }
    try {
      realtimeSocketRef.current?.send?.(JSON.stringify({ type: 'close' }))
      realtimeSocketRef.current?.close?.()
    } catch {
      // ignore websocket cleanup races
    }
    try {
      realtimeStreamRef.current?.getTracks?.().forEach((track) => track.stop())
    } catch {
      // ignore stream cleanup races
    }
    realtimeRecorderRef.current = null
    realtimeSocketRef.current = null
    realtimeStreamRef.current = null
  }

  const stopRecognition = () => {
    stopDeepgramStream()
    stopRealtimeVoiceStream()
    recognitionSessionRef.current += 1
    recognitionStartingRef.current = false
    recognitionActiveRef.current = false
    try {
      recognitionRef.current?.stop()
    } catch {
      // ignore browser speech recognition cleanup races
    }
    recognitionRef.current = null
  }

  const stopVapiCall = () => {
    try {
      vapiRef.current?.stop?.()
    } catch {
      // ignore Vapi cleanup races
    }
    vapiActiveRef.current = false
    setVapiActive(false)
  }

  const cleanupSttRecorder = () => {
    try {
      sttRecorderStreamRef.current?.getTracks?.().forEach((track) => track.stop())
    } catch {
      // ignore recorder cleanup races
    }
    sttRecorderRef.current = null
    sttRecorderStreamRef.current = null
    sttRecorderChunksRef.current = []
    setSttRecording(false)
  }

  const scheduleMicRecovery = (reason = 'recovery', delayMs = 40) => {
    if (!callActiveRef.current) return
    recoveryStartedAtRef.current = performance.now()
    micReadyAtRef.current = 0
    setTurnTakingMetrics((prev) => ({
      ...prev,
      recognizer_ready_to_first_transcript_ms: null,
      last_mic_ready_reason: reason,
    }))
    setCallState('preparing_mic')
    if (recognitionRestartTimerRef.current) window.clearTimeout(recognitionRestartTimerRef.current)
    recognitionRestartTimerRef.current = window.setTimeout(() => {
      recognitionRestartTimerRef.current = null
      if (callActiveRef.current && !processingRef.current && !audioPlayingRef.current) {
        if (sttProvider === 'deepgram') startDeepgramRecognitionLoop({ reason })
        else startRecognitionLoop({ reason })
      }
    }, delayMs)
  }

  const resumeListeningAfterAudio = () => {
    processingRef.current = false
    setPlaybackBlocked(false)
    if (callActiveRef.current) scheduleMicRecovery('manual-audio-ended', 30)
    else setCallState('idle')
  }

  const stopStreamingAndAudio = ({ measureInterrupt = false } = {}) => {
    const stopStartedAt = performance.now()
    logAudio('stop_requested', { measure_interrupt: measureInterrupt })
    activeRequestIdRef.current += 1
    if (sendTimerRef.current) window.clearTimeout(sendTimerRef.current)
    if (partialSendTimerRef.current) window.clearTimeout(partialSendTimerRef.current)
    if (recognitionRestartTimerRef.current) window.clearTimeout(recognitionRestartTimerRef.current)
    sendTimerRef.current = null
    partialSendTimerRef.current = null
    recognitionRestartTimerRef.current = null
    try {
      streamAbortRef.current?.abort()
    } catch {
      // ignore
    }
    streamAbortRef.current = null
    audioQueueRef.current = []
    audioPlayingRef.current = false
    logAudio('audio_stopped', { measure_interrupt: measureInterrupt })
    setAudioQueueLength(0)
    setStreamConnected(false)
    try {
      audioRef.current?.pause()
      if (audioRef.current) audioRef.current.currentTime = 0
    } catch {
      // ignore
    }
    audioRef.current = null
    if (measureInterrupt) {
      setTurnTakingMetrics((prev) => ({
        ...prev,
        interrupt_to_audio_stop_ms: Math.round(performance.now() - stopStartedAt),
      }))
    }
  }

  const playNextAudioSegment = (requestId) => {
    if (requestId !== activeRequestIdRef.current) {
      logAudio('skip_stale_request', { request_id: requestId, active_request_id: activeRequestIdRef.current })
      return
    }
    if (audioPlayingRef.current) {
      logAudio('already_playing', { request_id: requestId })
      return
    }
    const next = audioQueueRef.current.shift()
    setAudioQueueLength(audioQueueRef.current.length)
    if (!next) {
      audioPlayingRef.current = false
      logAudio('queue_empty', { request_id: requestId })
      if (callActiveRef.current && !processingRef.current && deepgramSocketRef.current) setCallState('listening')
      else if (callActiveRef.current && !processingRef.current) scheduleMicRecovery('playback-ended', 30)
      else setCallState('done')
      return
    }
    audioPlayingRef.current = true
    setPlaybackBlocked(false)
    setCallState('speaking')
    const audio = new Audio(next.src)
    audio.preload = 'auto'
    audio.playsInline = true
    audioRef.current = audio
    logAudio('playback_attempt', {
      request_id: requestId,
      index: next.index,
      provider: next.tts_provider,
      mime: next.audio_mime,
      bytes: next.audio_bytes,
    })
    audio.onloadeddata = () => {
      logAudio('audio_decoded', { request_id: requestId, index: next.index, ready_state: audio.readyState, duration: audio.duration })
    }
    audio.onplaying = () => {
      logAudio('playback_started', { request_id: requestId, index: next.index, current_time: audio.currentTime })
      if (next.turn_id && realtimeSocketRef.current?.readyState === WebSocket.OPEN) {
        realtimeSocketRef.current.send(JSON.stringify({
          type: 'audio_playing',
          turn_id: next.turn_id,
          index: next.index,
          at_ms: Math.round(performance.now()),
        }))
      }
      const now = performance.now()
      const pending = playbackTimingRef.current
      if (pending && pending.browser_audio_playback_start_ms == null) {
        setLatestTimings({
          ...pending,
          browser_audio_playback_start_ms: Math.round(now - pending.turn_start_at),
          browser_playback_start: Math.round(now - pending.turn_start_at),
        })
      }
    }
    audio.onended = () => {
      if (requestId !== activeRequestIdRef.current) return
      logAudio('playback_ended', { request_id: requestId, index: next.index })
      audioPlayingRef.current = false
      playNextAudioSegment(requestId)
    }
    audio.onerror = () => {
      if (requestId !== activeRequestIdRef.current) return
      audioPlayingRef.current = false
      setPlaybackBlocked(true)
      const mediaError = audio.error ? `${audio.error.code}:${audio.error.message || 'media error'}` : 'unknown media error'
      logAudio('playback_error', { request_id: requestId, index: next.index, media_error: mediaError })
      setError(`Browser could not play one returned audio segment (${mediaError}).`)
      playNextAudioSegment(requestId)
    }
    audio.play().catch(() => {
      if (requestId !== activeRequestIdRef.current) return
      audioPlayingRef.current = false
      setPlaybackBlocked(true)
      audioQueueRef.current.unshift(next)
      setAudioQueueLength(audioQueueRef.current.length)
      logAudio('autoplay_blocked', { request_id: requestId, index: next.index })
      setError('Browser blocked audio autoplay. Click Enable audio / Play latest reply once, then the queue can continue.')
    })
  }

  const enqueueAudioSegment = (segment, requestId) => {
    if (!segment?.audio_b64 || requestId !== activeRequestIdRef.current) {
      logAudio('chunk_ignored', { request_id: requestId, active_request_id: activeRequestIdRef.current, has_audio: Boolean(segment?.audio_b64) })
      return
    }
    const src = dataUrlFromAudio(segment.audio_b64, segment.audio_mime || 'audio/mpeg')
    logAudio('chunk_received', {
      request_id: requestId,
      index: segment.index,
      provider: segment.tts_provider,
      mime: segment.audio_mime,
      bytes: segment.audio_bytes,
    })
    audioQueueRef.current.push({ ...segment, src })
    setAudioQueueLength(audioQueueRef.current.length)
    setLatestAudioSrc(src)
    setLatestAudioBytes(segment.audio_bytes || Math.floor((String(segment.audio_b64 || '').length * 3) / 4))
    logAudio('chunk_queued', { request_id: requestId, index: segment.index, queue_length: audioQueueRef.current.length })
    playNextAudioSegment(requestId)
  }

  const playAudioSrc = async (src) => {
    if (!src) {
      processingRef.current = false
      if (callActiveRef.current) scheduleMicRecovery('manual-audio-missing', 30)
      else setCallState('idle')
      return
    }
    await unlockAudioPlayback('manual-play-latest')
    setPlaybackBlocked(false)
    setCallState('speaking')
    const audio = new Audio(src)
    audio.preload = 'auto'
    audio.playsInline = true
    audioRef.current = audio
    audio.onended = resumeListeningAfterAudio
    audio.onloadeddata = () => logAudio('manual_audio_decoded', { ready_state: audio.readyState, duration: audio.duration })
    audio.onplaying = () => {
      logAudio('manual_playback_started', {})
      const now = performance.now()
      const pending = playbackTimingRef.current
      if (pending) {
        setLatestTimings({
          ...pending,
          browser_audio_playback_start_ms: Math.round(now - pending.turn_start_at),
          browser_total_roundtrip_ms: Math.round(now - pending.turn_start_at),
        })
        console.info('vox_demo_turn_timings', {
          ...pending,
          browser_audio_playback_start_ms: Math.round(now - pending.turn_start_at),
          browser_total_roundtrip_ms: Math.round(now - pending.turn_start_at),
        })
      }
    }
    audio.onerror = () => {
      setPlaybackBlocked(true)
      const mediaError = audio.error ? `${audio.error.code}:${audio.error.message || 'media error'}` : 'unknown media error'
      logAudio('manual_playback_error', { media_error: mediaError })
      setError(`Browser could not play the returned audio (${mediaError}).`)
      processingRef.current = false
      if (callActiveRef.current) scheduleMicRecovery('manual-audio-error', 80)
      else setCallState('idle')
    }
    try {
      await audio.play()
    } catch {
      setPlaybackBlocked(true)
      logAudio('manual_playback_blocked', {})
      setError('Browser blocked audio playback. Click Enable audio, then Play latest reply.')
      processingRef.current = false
      if (callActiveRef.current) scheduleMicRecovery('manual-audio-blocked', 80)
      else setCallState('idle')
    }
  }

  const resumeQueuedAudio = async () => {
    await unlockAudioPlayback('resume-queued-audio')
    setPlaybackBlocked(false)
    playNextAudioSegment(activeRequestIdRef.current)
  }

  useEffect(() => {
    apiFetch('/admin/agents')
      .then((rows) => {
        const agents = rows?.agents || []
        setAgents(agents)
        const found = agents.find((a) => slugify(a.slug) === DEFAULT_AGENT_SLUG || slugify(a.name) === DEFAULT_AGENT_SLUG || /vox/i.test(a.name || '') && /sales?/i.test(a.name || ''))
        if (found?.slug) {
          setCurrentAgent(found)
          setAgentSlug(found.slug)
          setAgentLabel(`${found.name || 'Vox Sales'} (${found.slug})`)
          setCallPrompt(found.system_prompt || '')
        } else if (agents[0]?.slug) {
          setCurrentAgent(agents[0])
          setAgentSlug(agents[0].slug)
          setAgentLabel(`${agents[0].name || 'Selected agent'} (${agents[0].slug})`)
          setCallPrompt(agents[0].system_prompt || '')
        }
      })
      .catch(() => {
        setAgentLabel('Vox Sales (using fallback slug vox-sales)')
      })
    apiFetch('/admin/demo/provider-config')
      .then((rows) => {
        const providers = rows?.providers || null
        setProviderConfig(providers)
        if (providers?.cartesia?.voice_id) setCartesiaVoiceId(providers.cartesia.voice_id)
        if (providers?.elevenlabs?.default_voice_id) setElevenLabsVoiceId(providers.elevenlabs.default_voice_id)
        if (providers?.elevenlabs?.config) {
          const cfg = providers.elevenlabs.config
          setElevenLabsSettings((prev) => ({
            ...prev,
            stability: cfg.stability ?? '',
            similarity_boost: cfg.similarity_boost ?? '',
            style: cfg.style ?? '',
            speed: cfg.speed ?? '',
            speaker_boost: cfg.speaker_boost !== false,
          }))
        }
      })
      .catch(() => setProviderConfig(null))
    return () => {
      clearTimers()
      stopStreamingAndAudio()
      stopRecognition()
      stopVapiCall()
      cleanupSttRecorder()
      if (telnyxPollRef.current) window.clearInterval(telnyxPollRef.current)
    }
  }, [])

  const saveCallPrompt = async () => {
    if (!currentAgent?.id || !callPrompt.trim()) return
    setPromptSaving(true)
    setPromptMessage('')
    try {
      const saved = await apiFetch(`/admin/agents/${currentAgent.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          ...currentAgent,
          system_prompt: callPrompt.trim(),
        }),
      })
      setCurrentAgent(saved)
      setAgentSlug(saved.slug || agentSlug)
      setAgentLabel(`${saved.name || 'Vox Sales'} (${saved.slug || agentSlug})`)
      setCallPrompt(saved.system_prompt || callPrompt.trim())
      setPromptMessage('Call prompt saved. New calls will use this prompt.')
    } catch (e) {
      setPromptMessage(e?.message || 'Could not save call prompt')
    } finally {
      setPromptSaving(false)
    }
  }

  const selectAgent = (agentId) => {
    const found = agents.find((agent) => String(agent.id) === String(agentId))
    if (!found) return
    if (callActiveRef.current || processingRef.current || status === 'speaking' || status === 'thinking') {
      setError('Hang up or wait for the current turn to finish before changing agents.')
      return
    }
    setCurrentAgent(found)
    setAgentSlug(found.slug || DEFAULT_AGENT_SLUG)
    setAgentLabel(`${found.name || 'Selected agent'} (${found.slug || 'no-slug'})`)
    setCallPrompt(found.system_prompt || '')
    setPromptMessage('Selected agent loaded. This prompt is the call workflow for new turns.')
    setMessages([])
    setLiveTranscript('')
    setLatestTimings(null)
  }

  const startVapiCall = async () => {
    setError('')
    stopStreamingAndAudio()
    stopRecognition()
    const cfg = providerConfig?.vapi
    if (!cfg?.configured || !cfg?.public_key || !cfg?.assistant_id) {
      setError(`Vapi is not configured. Missing: ${(cfg?.missing || ['VAPI_PUBLIC_KEY', 'VAPI_ASSISTANT_ID']).join(', ')}`)
      setCallState('error')
      return
    }
    try {
      if (!vapiRef.current) {
        const vapi = new Vapi(cfg.public_key)
        vapi.on('call-start', () => {
          vapiActiveRef.current = true
          setVapiActive(true)
          setCallActive(true)
          setCallState('listening')
          setStreamConnected(true)
        })
        vapi.on('call-end', () => {
          vapiActiveRef.current = false
          setVapiActive(false)
          setCallActive(false)
          setStreamConnected(false)
          setLatestTimings((prev) => prev?.turn_start_at ? { ...prev, total_completion_ms: Math.round(performance.now() - prev.turn_start_at) } : prev)
          setCallState('ended')
        })
        vapi.on('speech-start', () => {
          setCallState('speaking')
          setLatestTimings((prev) => {
            if (!prev?.turn_start_at || prev.first_audio_latency_ms != null) return prev
            const elapsed = Math.round(performance.now() - prev.turn_start_at)
            return { ...prev, first_audio_latency_ms: elapsed, browser_playback_start: elapsed }
          })
        })
        vapi.on('speech-end', () => {
          if (vapiActiveRef.current) setCallState('listening')
        })
        vapi.on('message', (message) => {
          const role = message?.role || message?.message?.role
          const content = message?.transcript || message?.content || message?.message?.content || ''
          if (!content || !['user', 'assistant'].includes(role)) return
          setMessages((rows) => [...rows, { role, text: String(content) }])
          if (role === 'assistant') {
            setLatestTimings((prev) => {
              if (!prev?.turn_start_at || prev.first_text_latency_ms != null) return prev
              return { ...prev, first_text_latency_ms: Math.round(performance.now() - prev.turn_start_at) }
            })
          }
        })
        vapi.on('error', (e) => {
          setError(e?.message || 'Vapi browser call failed')
          setCallState('error')
        })
        vapiRef.current = vapi
      }
      setCallState('preparing_mic')
      setCallActive(true)
      const startedAt = performance.now()
      setLatestTimings({
        turn_start_at: startedAt,
        selected_provider: 'vapi',
        first_text_latency_ms: null,
        first_audio_latency_ms: null,
        total_completion_ms: null,
        backend: { selected_provider: 'vapi', voice_mode: 'vapi_assistant' },
      })
      await vapiRef.current.start(cfg.assistant_id)
    } catch (e) {
      setError(e?.message || 'Could not start Vapi call')
      setCallState('error')
    }
  }

  const sendVapiText = (text) => {
    if (!vapiRef.current || !vapiActiveRef.current) {
      setError('Start the Vapi call first, then use the test phrase.')
      return
    }
    try {
      const message = { role: 'user', content: text }
      vapiRef.current.send?.({ type: 'add-message', message })
      setMessages((rows) => [...rows, { role: 'user', text }])
    } catch (e) {
      setError(e?.message || 'Could not send text message to Vapi call')
    }
  }

  const pollTelnyxCall = (callId) => {
    if (telnyxPollRef.current) window.clearInterval(telnyxPollRef.current)
    telnyxPollRef.current = window.setInterval(async () => {
      try {
        const result = await apiFetch(`/admin/demo/telnyx-call/${callId}`)
        const call = result?.call
        if (!call) return
        setTelnyxCall(call)
        const nextStatus = String(call.status || '').toLowerCase()
        setCallState(nextStatus || 'telnyx')
        if (['completed', 'hangup', 'ended', 'failed'].includes(nextStatus)) {
          window.clearInterval(telnyxPollRef.current)
          telnyxPollRef.current = null
          setCallActive(false)
          callActiveRef.current = false
        }
      } catch (e) {
        setError(e?.message || 'Could not refresh Telnyx call status')
      }
    }, 3000)
  }

  const startTelnyxPhoneCall = async () => {
    const cfg = providerConfig?.telnyx
    if (!cfg?.configured) {
      setError(`Telnyx is not configured. Missing: ${(cfg?.missing || ['api_key', 'connection_id', 'default_outbound_number', 'outbound_voice_profile_id', 'voice_webhook_url']).join(', ')}`)
      return
    }
    const toNumber = telnyxPhone.trim()
    if (!toNumber) {
      setError('Enter your phone number first.')
      return
    }
    setError('')
    setTelnyxCalling(true)
    setTelnyxCall(null)
    try {
      const result = await apiFetch('/admin/demo/telnyx-call', {
        method: 'POST',
        body: JSON.stringify({ to_number: toNumber, agent_slug: agentSlug || DEFAULT_AGENT_SLUG }),
      })
      const call = result?.call
      setTelnyxCall(call || null)
      callActiveRef.current = true
      setCallActive(true)
      setCallState(call?.status || 'queued')
      if (call?.id) pollTelnyxCall(call.id)
    } catch (e) {
      setError(normalizeBackendError(e) || 'Could not start Telnyx phone call')
      setCallState('error')
    } finally {
      setTelnyxCalling(false)
    }
  }

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, liveTranscript])

  const isDgcRealtime = () => voiceMode === 'streaming' && sttProvider === 'deepgram' && selectedProvider === 'groq' && ttsProvider === 'cartesia'

  const startRealtimeVoiceCall = async () => {
    setError('')
    stopStreamingAndAudio()
    stopRecognition()
    await unlockAudioPlayback('realtime-start-call')
    try {
      const token = adminToken()
      if (!token) throw new Error('No admin session token available for realtime voice.')
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      realtimeStreamRef.current = stream
      const ws = new WebSocket(`${resolveApiWebSocketUrl('/admin/demo/voice/realtime')}?token=${encodeURIComponent(token)}`)
      realtimeSocketRef.current = ws
      const recorder = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm' })
      realtimeRecorderRef.current = recorder
      callActiveRef.current = true
      setCallActive(true)
      setCallState('preparing_mic')
      setStreamConnected(false)
      setMessages((rows) => rows)
      setLatestTimings({
        turn_start_at: performance.now(),
        selected_provider: 'groq',
        stt_provider: 'deepgram',
        tts_provider: 'cartesia',
        voice_mode: 'realtime_websocket',
        backend: {},
      })
      playbackTimingRef.current = {
        turn_start_at: performance.now(),
        selected_provider: 'groq',
        stt_provider: 'deepgram',
        tts_provider: 'cartesia',
        voice_mode: 'realtime_websocket',
        backend: {},
      }

      recorder.ondataavailable = (event) => {
        if (event.data?.size && ws.readyState === WebSocket.OPEN) ws.send(event.data)
      }

      ws.onopen = () => {
        ws.send(JSON.stringify({
          type: 'start',
          agent_slug: agentSlug,
          provider: 'groq',
          tts_provider: 'cartesia',
          cartesia_voice_id: cartesiaVoiceId,
          voice_id: cartesiaVoiceId,
          history: messages.map((m) => ({ role: m.role, content: m.text })),
        }))
      }

      ws.onmessage = (event) => {
        let data = null
        try { data = JSON.parse(event.data) } catch { return }
        logRealtime(data.type || 'event', data)
        if (data.type === 'connected' || data.type === 'ready') {
          setStreamConnected(true)
          setCallState('listening')
          if (recorder.state === 'inactive') recorder.start(120)
          return
        }
        if (data.type === 'stt_partial' || data.type === 'stt_final') {
          const text = String(data.text || '').trim()
          if (text) setLiveTranscript(text)
          return
        }
        if (data.type === 'barge_in') {
          stopStreamingAndAudio({ measureInterrupt: true })
          setCallState('listening')
          return
        }
        if (data.type === 'llm_start') {
          activeRequestIdRef.current += 1
          realtimePlaybackRequestIdRef.current = activeRequestIdRef.current
          processingRef.current = true
          setCallState('thinking')
          setMessages((rows) => [...rows, { role: 'user', text: data.text || '' }, { role: 'assistant', text: '', streaming: true }])
          return
        }
        if (data.type === 'llm_text_delta') {
          setChunksReceived((n) => n + 1)
          setMessages((rows) => {
            const next = [...rows]
            for (let i = next.length - 1; i >= 0; i -= 1) {
              if (next[i].role === 'assistant') {
                next[i] = { ...next[i], text: `${next[i].text || ''}${data.delta || ''}`, streaming: true }
                break
              }
            }
            return next
          })
          return
        }
        if (data.type === 'metrics') {
          setLatestTimings((prev) => ({
            ...(prev || {}),
            first_text_latency_ms: prev?.first_text_latency_ms ?? data.first_llm_token_ms,
            backend: { ...((prev || {}).backend || {}), ...data },
          }))
          return
        }
        if (data.type === 'tts_audio_ready') {
          setLatestTimings((prev) => ({
            ...(prev || {}),
            first_audio_latency_ms: data.is_first_audio ? (prev?.first_audio_latency_ms ?? data.elapsed_ms) : prev?.first_audio_latency_ms,
            backend: { ...((prev || {}).backend || {}), cartesia_ws_first_chunk_ms: data.cartesia_ws_first_chunk_ms },
          }))
          enqueueAudioSegment(data, realtimePlaybackRequestIdRef.current)
          return
        }
        if (data.type === 'done') {
          processingRef.current = false
          setLatestTimings((prev) => ({
            ...(prev || {}),
            total_completion_ms: data.metrics?.completed_ms,
            backend: { ...((prev || {}).backend || {}), ...(data.metrics || {}) },
          }))
          setMessages((rows) => {
            const next = [...rows]
            for (let i = next.length - 1; i >= 0; i -= 1) {
              if (next[i].role === 'assistant') {
                next[i] = { ...next[i], text: data.agent_text || next[i].text || '', streaming: false }
                break
              }
            }
            return next
          })
          if (!audioPlayingRef.current && audioQueueRef.current.length === 0) setCallState('listening')
          return
        }
        if (data.type === 'error') {
          setError(data.message || 'Realtime voice failed')
          processingRef.current = false
          setCallState('error')
        }
      }
      ws.onerror = () => {
        setError('Realtime voice WebSocket failed.')
        setCallState('error')
      }
      ws.onclose = () => {
        realtimeSocketRef.current = null
        setStreamConnected(false)
        if (callActiveRef.current) setCallState('ended')
      }
    } catch (e) {
      stopRealtimeVoiceStream()
      setError(e?.message || 'Could not start realtime voice call.')
      setCallState('error')
    }
  }


  const startDeepgramRecognitionLoop = async ({ reason = 'deepgram-listen', bargeIn = false } = {}) => {
    setError('')
    if (!callActiveRef.current) return
    if (!bargeIn && (processingRef.current || statusRef.current === 'speaking' || audioPlayingRef.current)) return
    if (deepgramSocketRef.current || deepgramRecorderRef.current) return
    if (!bargeIn) setCallState('preparing_mic')
    finalTranscriptRef.current = ''
    pendingFinalRef.current = ''
    bargeInTranscriptRef.current = ''
    earlySentRef.current = false
    setLiveTranscript('')
    try {
      const token = adminToken()
      if (!token) throw new Error('No admin session token available for Deepgram streaming.')
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      deepgramStreamRef.current = stream
      const ws = new WebSocket(`${resolveApiWebSocketUrl('/admin/demo/stt/deepgram/stream')}?token=${encodeURIComponent(token)}`)
      deepgramSocketRef.current = ws
      const recorder = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm' })
      deepgramRecorderRef.current = recorder
      ws.onopen = () => {
        setCallState('preparing_mic')
      }
      recorder.ondataavailable = (event) => {
        if (event.data?.size && ws.readyState === WebSocket.OPEN) ws.send(event.data)
      }
      ws.onmessage = (event) => {
        resetIdleTimer()
        let payload = null
        try { payload = JSON.parse(event.data) } catch { return }
        if (payload?.type === 'ready') {
          logRealtime('stt_ready', { provider: 'deepgram', reason, barge_in: bargeIn })
          micReadyAtRef.current = performance.now()
          if (recoveryStartedAtRef.current) {
            setTurnTakingMetrics((prev) => ({
              ...prev,
              playback_end_to_recognizer_ready_ms: Math.round(micReadyAtRef.current - recoveryStartedAtRef.current),
              last_mic_ready_reason: reason,
            }))
            recoveryStartedAtRef.current = 0
          }
          if (!bargeIn) setCallState('listening')
          resetIdleTimer()
          if (recorder.state === 'inactive') recorder.start(250)
          return
        }
        if (payload?.type !== 'transcript') return
        const text = String(payload.text || '').trim()
        if (!text) return
        logRealtime(payload.is_final || payload.speech_final ? 'stt_final' : 'stt_partial', {
          text,
          confidence: payload.confidence,
          speech_final: Boolean(payload.speech_final),
          barge_in: bargeIn,
        })
        const wordCount = text.split(/\s+/).filter(Boolean).length
        if ((bargeIn || audioPlayingRef.current || processingRef.current || statusRef.current === 'speaking') && wordCount >= BARGE_IN_MIN_WORDS) {
          const merged = `${bargeInTranscriptRef.current} ${text}`.trim()
          bargeInTranscriptRef.current = merged
          logRealtime('barge_in_detected', { text: merged })
          stopStreamingAndAudio({ measureInterrupt: true })
          processingRef.current = false
          if (sendTimerRef.current) window.clearTimeout(sendTimerRef.current)
          sendTimerRef.current = window.setTimeout(() => {
            const bargeText = bargeInTranscriptRef.current.trim()
            bargeInTranscriptRef.current = ''
            if (bargeText && callActiveRef.current && !processingRef.current) {
              stopRecognition()
              sendToAgent(bargeText, messages, true)
            }
          }, payload.speech_final ? 50 : FINAL_SEND_DELAY_MS)
          return
        }
        if (micReadyAtRef.current) {
          setTurnTakingMetrics((prev) => prev.recognizer_ready_to_first_transcript_ms != null ? prev : {
            ...prev,
            recognizer_ready_to_first_transcript_ms: Math.round(performance.now() - micReadyAtRef.current),
          })
        }
        if (payload.is_final || payload.speech_final) {
          if (!speechFinalReadyAtRef.current) speechFinalReadyAtRef.current = performance.now()
          finalTranscriptRef.current = `${finalTranscriptRef.current} ${text}`.trim()
          pendingFinalRef.current = `${pendingFinalRef.current} ${text}`.trim()
          setLiveTranscript(finalTranscriptRef.current)
        } else {
          setLiveTranscript(`${finalTranscriptRef.current} ${text}`.trim())
          if (!earlySentRef.current && wordCount >= EARLY_PARTIAL_MIN_WORDS) {
            if (partialSendTimerRef.current) window.clearTimeout(partialSendTimerRef.current)
            partialSendTimerRef.current = window.setTimeout(() => {
              const partialToSend = `${finalTranscriptRef.current} ${text}`.trim()
              if (partialToSend && callActiveRef.current && !processingRef.current && !earlySentRef.current) {
                earlySentRef.current = true
                speechFinalReadyAtRef.current = speechFinalReadyAtRef.current || performance.now()
                logRealtime('early_partial_send', { text: partialToSend })
                stopRecognition()
                sendToAgent(partialToSend, messages, true)
              }
            }, EARLY_PARTIAL_DELAY_MS)
          }
        }
        if (payload.speech_final) {
          if (sendTimerRef.current) window.clearTimeout(sendTimerRef.current)
          sendTimerRef.current = window.setTimeout(() => {
            const finalToSend = pendingFinalRef.current.trim()
            pendingFinalRef.current = ''
            if (finalToSend && callActiveRef.current && !processingRef.current) {
              stopRecognition()
              sendToAgent(finalToSend, messages, true)
            }
          }, FINAL_SEND_DELAY_MS)
        }
      }
      ws.onerror = () => {
        setError('Deepgram streaming connection failed.')
        stopDeepgramStream()
        if (callActiveRef.current) scheduleMicRecovery('deepgram-error-recovery', 250)
      }
      ws.onclose = () => {
        deepgramSocketRef.current = null
        if (callActiveRef.current && !processingRef.current && statusRef.current !== 'speaking' && !audioPlayingRef.current) {
          scheduleMicRecovery('deepgram-ended', 120)
        }
      }
    } catch (e) {
      stopDeepgramStream()
      setError(e?.message || 'Could not start Deepgram microphone stream.')
      setCallState(callActiveRef.current ? 'error' : 'idle')
      if (callActiveRef.current) scheduleMicRecovery('deepgram-start-retry', 250)
    }
  }

  const startRecognitionLoop = ({ reason = 'listen' } = {}) => {
    setError('')
    if (!recognitionSupported) {
      setError('This browser does not support speech recognition. Use Chrome or the text input below.')
      setCallState('error')
      return
    }
    if (!callActiveRef.current || processingRef.current || statusRef.current === 'speaking' || audioPlayingRef.current) return
    if (recognitionActiveRef.current || recognitionStartingRef.current) return
    recognitionStartingRef.current = true
    recognitionActiveRef.current = false
    setCallState('preparing_mic')
    const Recognition = speechRecognitionCtor()
    const recognition = new Recognition()
    const sessionId = recognitionSessionRef.current + 1
    recognitionSessionRef.current = sessionId
    recognition.lang = 'en-GB'
    recognition.continuous = true
    recognition.interimResults = true
    finalTranscriptRef.current = ''
    pendingFinalRef.current = ''
    setLiveTranscript('')
    recognition.onstart = () => {
      if (sessionId !== recognitionSessionRef.current) return
      recognitionStartingRef.current = false
      recognitionActiveRef.current = true
      micReadyAtRef.current = performance.now()
      if (recoveryStartedAtRef.current) {
        setTurnTakingMetrics((prev) => ({
          ...prev,
          playback_end_to_recognizer_ready_ms: Math.round(micReadyAtRef.current - recoveryStartedAtRef.current),
          last_mic_ready_reason: reason,
        }))
        recoveryStartedAtRef.current = 0
      }
      setCallState('listening')
      resetIdleTimer()
    }
    recognition.onerror = (event) => {
      if (sessionId !== recognitionSessionRef.current) return
      recognitionStartingRef.current = false
      recognitionActiveRef.current = false
      const reason = event?.error === 'not-allowed' ? 'Microphone permission denied.' : `Speech recognition error: ${event?.error || 'unknown'}`
      setError(reason)
      setCallState('error')
      if (event?.error === 'not-allowed') hangUp('ended')
    }
    recognition.onresult = (event) => {
      if (sessionId !== recognitionSessionRef.current) return
      resetIdleTimer()
      let interim = ''
      let finalText = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const chunk = event.results[i][0]?.transcript || ''
        if (event.results[i].isFinal) finalText += chunk
        else interim += chunk
      }
      if ((finalText.trim() || interim.trim()) && micReadyAtRef.current) {
        setTurnTakingMetrics((prev) => {
          if (prev.recognizer_ready_to_first_transcript_ms != null) return prev
          return {
            ...prev,
            recognizer_ready_to_first_transcript_ms: Math.round(performance.now() - micReadyAtRef.current),
          }
        })
      }
      if (finalText.trim()) {
        if (!speechFinalReadyAtRef.current) speechFinalReadyAtRef.current = performance.now()
        finalTranscriptRef.current = `${finalTranscriptRef.current} ${finalText}`.trim()
        pendingFinalRef.current = `${pendingFinalRef.current} ${finalText}`.trim()
        if (sendTimerRef.current) window.clearTimeout(sendTimerRef.current)
        sendTimerRef.current = window.setTimeout(() => {
          const finalToSend = pendingFinalRef.current.trim()
          pendingFinalRef.current = ''
          if (finalToSend && callActiveRef.current && !processingRef.current) {
            stopRecognition()
            sendToAgent(finalToSend, messages, true)
          }
        }, FINAL_SEND_DELAY_MS)
      }
      setLiveTranscript(`${finalTranscriptRef.current} ${interim}`.trim())
    }
    recognition.onend = () => {
      if (sessionId !== recognitionSessionRef.current) return
      recognitionStartingRef.current = false
      recognitionActiveRef.current = false
      recognitionRef.current = null
      if (callActiveRef.current && !processingRef.current && statusRef.current !== 'speaking' && !audioPlayingRef.current) {
        scheduleMicRecovery('recognition-ended', 120)
      }
    }
    recognitionRef.current = recognition
    try {
      recognition.start()
    } catch (e) {
      recognitionStartingRef.current = false
      recognitionActiveRef.current = false
      setError(e?.message || 'Could not start microphone')
      setCallState(callActiveRef.current ? 'error' : 'idle')
      if (callActiveRef.current) scheduleMicRecovery('recognition-start-retry', 250)
    }
  }

  const sendToAgent = async (input, history = messages, fromSpeech = false) => {
    const text = String(input || '').trim()
    if (!text || processingRef.current) return
    if (!fromSpeech) await unlockAudioPlayback('send-to-agent')
    if (selectedProvider === 'vapi') {
      sendVapiText(text)
      return
    }
    stopRecognition()
    stopStreamingAndAudio()
    const requestId = activeRequestIdRef.current
    const now = performance.now()
    const turnStartAt = fromSpeech && speechFinalReadyAtRef.current ? speechFinalReadyAtRef.current : now
    const speechFinalReadyAt = fromSpeech && speechFinalReadyAtRef.current ? speechFinalReadyAtRef.current : turnStartAt
    speechFinalReadyAtRef.current = 0
    processingRef.current = true
    setError('')
    setCallState('thinking')
    setLiveTranscript(text)
    setChunksReceived(0)
    setLatestAudioSrc('')
    setLatestAudioBytes(0)
    const historyPayload = history.map((m) => ({ role: m.role, content: m.text }))
    const requestSentAt = performance.now()
    const speechFinalizedMs = Math.round(requestSentAt - speechFinalReadyAt)
    const browserTimings = {
      speech_final_transcript_ready_ms: Math.round(speechFinalReadyAt - turnStartAt),
      request_sent_ms: Math.round(requestSentAt - turnStartAt),
      browser_speech_finalized: Math.round(speechFinalReadyAt - turnStartAt),
      request_sent: Math.round(requestSentAt - turnStartAt),
    }
    console.info('vox_demo_request_sent', browserTimings)
    setMessages((rows) => [...rows, { role: 'user', text }])
    setMessages((rows) => [...rows, { role: 'assistant', text: '', streaming: true }])
    const baseTiming = {
      turn_start_at: turnStartAt,
      speech_final_transcript_ready_ms: browserTimings.speech_final_transcript_ready_ms,
      browser_request_sent_ms: browserTimings.request_sent_ms,
      browser_speech_finalized: browserTimings.browser_speech_finalized,
      request_sent: browserTimings.request_sent,
      selected_provider: selectedProvider,
      voice_mode: voiceMode,
      stt_provider: sttProvider,
      tts_provider: ttsProvider,
      browser_playback_start: null,
      first_text_latency_ms: null,
      first_audio_latency_ms: null,
      total_completion_ms: null,
      backend: {},
    }
    playbackTimingRef.current = baseTiming
    setLatestTimings(baseTiming)
    const requestPayload = {
      agent_slug: agentSlug,
      request_id: requestId,
      provider: selectedProvider,
      stt_provider: sttProvider,
      tts_provider: ttsProvider,
      groq_tts_voice: groqTtsVoice,
      cartesia_voice_id: cartesiaVoiceId,
      input: text,
      history: historyPayload,
      speech_finalized_ms: speechFinalizedMs,
      browser_timings: browserTimings,
      voice_id: demoVoice,
      elevenlabs_voice_id: elevenLabsVoiceId,
      elevenlabs_voice_settings: elevenLabsSettings,
      speaking_rate: speechSpeed,
      voice_mode: voiceMode,
    }
    try {
      const token = adminToken()
      if (!token) throw new Error('No admin session token available for voice request.')
      if (voiceMode === 'sequential') {
        const result = await apiFetch('/admin/demo/agent-call', {
          method: 'POST',
          body: JSON.stringify(requestPayload),
        })
        const src = dataUrlFromAudio(result.audio_b64, result.audio_mime || 'audio/wav')
        setLatestAudioSrc(src)
        setLatestAudioBytes(result.audio_bytes || 0)
        setMessages((rows) => {
          const next = [...rows]
          for (let i = next.length - 1; i >= 0; i -= 1) {
            if (next[i].role === 'assistant') {
              next[i] = { ...next[i], text: result.agent_text || '', streaming: false }
              break
            }
          }
          return next
        })
        setLatestTimings((prev) => ({
          ...(prev || baseTiming),
          total_completion_ms: result.timings?.total_roundtrip_ms ?? Math.round(performance.now() - turnStartAt),
          selected_provider: result.provider || selectedProvider,
          tts_provider: result.voice?.tts_provider || ttsProvider,
          backend: { ...((prev || baseTiming).backend || {}), ...(result.timings || {}) },
        }))
        processingRef.current = false
        await playAudioSrc(src)
        return
      }
      const controller = new AbortController()
      streamAbortRef.current = controller
      const response = await fetch(streamUrl('/admin/demo/agent-call/stream'), {
        method: 'POST',
        signal: controller.signal,
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'text/event-stream',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestPayload),
      })
      if (!response.ok || !response.body) {
        throw new Error(`Streaming request failed: ${response.status} ${response.statusText}`)
      }
      setStreamConnected(true)
      if (sttProvider === 'deepgram') {
        window.setTimeout(() => startDeepgramRecognitionLoop({ reason: 'barge-in-monitor', bargeIn: true }), 0)
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let assistantText = ''
      let finished = false

      while (!finished) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split(/\n\n|\r\n\r\n/)
        buffer = blocks.pop() || ''
        for (const block of blocks) {
          const parsed = parseSseBlock(block)
          if (!parsed) continue
          const { event, data } = parsed
          if (requestId !== activeRequestIdRef.current || (data?.request_id != null && String(data.request_id) !== String(requestId))) continue
          if (event === 'transcript_received') {
            setCallState('thinking')
          } else if (event === 'llm_text_delta') {
            assistantText += data.delta || ''
            setChunksReceived((n) => n + 1)
            setMessages((rows) => {
              const next = [...rows]
              for (let i = next.length - 1; i >= 0; i -= 1) {
                if (next[i].role === 'assistant') {
                  next[i] = { ...next[i], text: assistantText, streaming: true }
                  break
                }
              }
              return next
            })
          } else if (event === 'metrics') {
            setLatestTimings((prev) => {
              const next = { ...(prev || baseTiming), backend: { ...((prev || baseTiming).backend || {}), ...data } }
              if ((data.first_openai_token != null || data.first_llm_token_ms != null) && next.first_text_latency_ms == null) next.first_text_latency_ms = data.first_openai_token ?? data.first_llm_token_ms
              return next
            })
          } else if (event === 'tts_audio_ready') {
            setLatestTimings((prev) => {
              const next = { ...(prev || baseTiming), backend: { ...((prev || baseTiming).backend || {}), azure_first_byte: data.azure_first_byte, azure_chunk_finish: data.azure_chunk_finish } }
              if (data.is_first_audio && next.first_audio_latency_ms == null) next.first_audio_latency_ms = data.elapsed_ms
              return next
            })
            enqueueAudioSegment(data, requestId)
          } else if (event === 'done') {
            finished = true
            if (!audioPlayingRef.current && audioQueueRef.current.length === 0) setCallState('done')
            setLatestTimings((prev) => ({
              ...(prev || baseTiming),
              total_completion_ms: data.metrics?.completed_ms ?? Math.round(performance.now() - turnStartAt),
              selected_provider: data.provider || selectedProvider,
              backend: { ...((prev || baseTiming).backend || {}), ...(data.metrics || {}) },
            }))
            setMessages((rows) => {
              const next = [...rows]
              for (let i = next.length - 1; i >= 0; i -= 1) {
                if (next[i].role === 'assistant') {
                  next[i] = { ...next[i], text: data.agent_text || assistantText, streaming: false }
                  break
                }
              }
              return next
            })
          } else if (event === 'error') {
            const message = data.message || 'Streaming demo failed'
            setMessages((rows) => {
              const next = [...rows]
              for (let i = next.length - 1; i >= 0; i -= 1) {
                if (next[i].role === 'assistant') {
                  next[i] = { ...next[i], text: message, streaming: false }
                  break
                }
              }
              return next
            })
            throw new Error(message)
          }
        }
      }
      setStreamConnected(false)
      processingRef.current = false
      if (callActiveRef.current && !audioPlayingRef.current && audioQueueRef.current.length === 0) scheduleMicRecovery('stream-complete-no-audio', 30)
    } catch (e) {
      if (e?.name === 'AbortError') return
      const detail = e?.data?.detail
      const available = detail?.available_agents ? ` Available agents: ${detail.available_agents.map((a) => `${a.name} (${a.slug})`).join(', ')}` : ''
      setError(`${errorText(e)}${available}`)
      processingRef.current = false
      setStreamConnected(false)
      if (callActiveRef.current) scheduleMicRecovery('stream-error-recovery', 80)
      else setCallState('idle')
    }
  }

  const runTtsModuleTest = async () => {
    const text = moduleTestText.trim()
    if (!text) return
    setError('')
    setModuleResult((prev) => ({ ...prev, tts: 'Testing TTS...' }))
    try {
      const result = await apiFetch('/admin/demo/module-test/tts', {
        method: 'POST',
        body: JSON.stringify({
          text,
          tts_provider: ttsProvider,
          voice_id: demoVoice,
          elevenlabs_voice_id: elevenLabsVoiceId,
          elevenlabs_voice_settings: elevenLabsSettings,
          cartesia_voice_id: cartesiaVoiceId,
          groq_tts_voice: groqTtsVoice,
          speaking_rate: speechSpeed,
        }),
      })
      const src = dataUrlFromAudio(result.audio_b64, result.audio_mime || 'audio/mpeg')
      setLatestAudioSrc(src)
      setLatestAudioBytes(result.audio_bytes || 0)
      setModuleResult((prev) => ({
        ...prev,
        tts: `${result.tts_provider || ttsProvider} OK using voice ${result.voice_id || 'default'} (${result.audio_bytes || 0} bytes)`,
      }))
      await playAudioSrc(src)
    } catch (e) {
      setModuleResult((prev) => ({ ...prev, tts: errorText(e) }))
      setError(errorText(e))
    }
  }

  const runLlmModuleTest = async () => {
    const text = textInput.trim() || TEST_PHRASES[0]
    setError('')
    setModuleResult((prev) => ({ ...prev, llm: 'Testing LLM...' }))
    try {
      const result = await apiFetch('/admin/demo/module-test/llm', {
        method: 'POST',
        body: JSON.stringify({ provider: selectedProvider, text }),
      })
      if (result.ok === false) {
        setModuleResult((prev) => ({ ...prev, llm: `${providerLabel(selectedProvider)} failed: ${JSON.stringify(result.openai_payload || result.message || result)}` }))
        return
      }
      setModuleResult((prev) => ({ ...prev, llm: result.assistant_text || result.message || 'LLM test completed.' }))
    } catch (e) {
      setModuleResult((prev) => ({ ...prev, llm: errorText(e) }))
      setError(errorText(e))
    }
  }

  const startElevenLabsSttTest = async () => {
    if (!['deepgram', 'elevenlabs', 'groq'].includes(sttProvider)) {
      setModuleResult((prev) => ({ ...prev, stt: 'Choose Deepgram, ElevenLabs Scribe, or Groq Whisper first.' }))
      return
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setModuleResult((prev) => ({ ...prev, stt: 'This browser cannot record audio for ElevenLabs STT. Use Chrome.' }))
      return
    }
    setError('')
    setLiveTranscript('')
    setModuleResult((prev) => ({ ...prev, stt: 'Recording... speak now, then click Stop.' }))
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      sttRecorderStreamRef.current = stream
      sttRecorderChunksRef.current = []
      const recorder = new MediaRecorder(stream)
      sttRecorderRef.current = recorder
      recorder.ondataavailable = (event) => {
        if (event.data?.size) sttRecorderChunksRef.current.push(event.data)
      }
      recorder.onstop = async () => {
        const chunks = sttRecorderChunksRef.current
        const mime = recorder.mimeType || 'audio/webm'
        const blob = new Blob(chunks, { type: mime })
        cleanupSttRecorder()
        if (!blob.size) {
          setModuleResult((prev) => ({ ...prev, stt: 'No audio was recorded.' }))
          return
        }
        setModuleResult((prev) => ({ ...prev, stt: `Uploading audio to ${sttProvider}...` }))
        try {
          const token = adminToken()
          if (!token) throw new Error('No admin session token available.')
          const form = new FormData()
          form.append('provider', sttProvider)
          form.append('model_id', sttProvider === 'elevenlabs' ? 'scribe_v1' : sttProvider === 'groq' ? 'whisper-large-v3-turbo' : sttProvider === 'deepgram' ? 'nova-3' : '')
          form.append('file', blob, `${sttProvider}-stt-test.webm`)
          const response = await fetch(streamUrl('/admin/demo/module-test/stt'), {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` },
            body: form,
          })
          const result = await response.json()
          if (!response.ok || result.ok === false) {
            throw new Error(result?.detail?.message || result?.detail || result?.error?.message || 'ElevenLabs STT failed')
          }
          const text = result.text || ''
          setLiveTranscript(text)
          setTextInput(text)
          setModuleResult((prev) => ({
            ...prev,
          stt: `${sttProvider} STT OK: ${text || '(empty transcript)'} (${result.timings?.elevenlabs_stt_total_ms || result.timings?.deepgram_stt_total_ms || result.timings?.groq_stt_total_ms || '-'} ms)`,
          }))
        } catch (e) {
          setModuleResult((prev) => ({ ...prev, stt: e?.message || `${sttProvider} STT failed` }))
          setError(e?.message || `${sttProvider} STT failed`)
        }
      }
      recorder.start()
      setSttRecording(true)
    } catch (e) {
      cleanupSttRecorder()
      setModuleResult((prev) => ({ ...prev, stt: e?.message || 'Could not start microphone recording.' }))
      setError(e?.message || 'Could not start microphone recording.')
    }
  }

  const stopElevenLabsSttTest = () => {
    try {
      sttRecorderRef.current?.stop()
    } catch {
      cleanupSttRecorder()
    }
  }

  const startCall = () => {
    setError('')
    void unlockAudioPlayback('start-call')
    if (selectedProvider === 'vapi') {
      startVapiCall()
      return
    }
    if (selectedProvider === 'telnyx') {
      startTelnyxPhoneCall()
      return
    }
    if (isDgcRealtime()) {
      void startRealtimeVoiceCall()
      return
    }
    stopStreamingAndAudio()
    callActiveRef.current = true
    setCallActive(true)
    setTurnTakingMetrics({})
    scheduleMicRecovery('start-call', 0)
  }

  function hangUp(nextStatus = 'ended') {
    stopStreamingAndAudio()
    stopRecognition()
    stopRealtimeVoiceStream()
    stopVapiCall()
    callActiveRef.current = false
    processingRef.current = false
    setCallActive(false)
    clearTimers()
    setCallState(nextStatus)
  }

  const interruptCurrentReply = () => {
    const clickedAt = performance.now()
    stopStreamingAndAudio({ measureInterrupt: true })
    stopRecognition()
    if (selectedProvider === 'vapi') stopVapiCall()
    processingRef.current = false
    setPlaybackBlocked(false)
    setTurnTakingMetrics((prev) => ({
      ...prev,
      interrupt_click_at: Math.round(clickedAt),
      recognizer_ready_to_first_transcript_ms: null,
    }))
    setCallState('interrupted')
    if (callActiveRef.current) scheduleMicRecovery('interrupt', 30)
    else setCallState('idle')
  }

  const sendTyped = () => {
    void unlockAudioPlayback('typed-send')
    const text = textInput.trim()
    setTextInput('')
    sendToAgent(text, messages, false)
  }

  const clearConversation = () => {
    setMessages([])
    setLiveTranscript('')
    setLatestAudioSrc('')
    setLatestAudioBytes(0)
    setPlaybackBlocked(false)
    setError('')
    setLatestTimings(null)
    playbackTimingRef.current = null
    hangUp('idle')
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Vox Sales Demo Lab</h1>
          <p>Choose an agent, then run a browser voice call, Vapi web call, or Telnyx outbound phone call.</p>
          <p className='muted' style={{ marginTop: 6 }}>Using agent: {agentLabel}</p>
        </div>
        <div style={{ display: 'grid', justifyItems: 'end', gap: 6 }}>
          <span className={`pill ${status === 'listening' ? 'p-green' : status === 'preparing_mic' || status === 'interrupted' ? 'p-amber' : status === 'speaking' ? 'p-cyan' : status === 'ended' || status === 'error' ? 'p-amber' : 'p-cyan'}`}>{status}</span>
          <span className='muted' style={{ fontSize: 12 }}>{selectedProvider === 'vapi' ? `Vapi assistant ${providerConfig?.vapi?.assistant_id || 'not configured'}` : `STT ${sttProvider} | LLM ${providerLabel(selectedProvider)} | TTS ${TTS_PROVIDERS.find((provider) => provider.id === ttsProvider)?.label}`}</span>
        </div>
      </div>

      {error ? <div className='note' style={{ borderColor: 'rgba(255,0,0,0.35)', marginBottom: 16 }}>{error}</div> : null}

      <div className='card' style={{ marginBottom: 16 }}>
        <div className='cardHead'>
          <div>
            <h3>1. Configure Modules</h3>
            <p className='muted' style={{ margin: '4px 0 0' }}>Set the providers once here. The full call and module tests use these selections.</p>
          </div>
          <span className='pill p-cyan'>STT · LLM · TTS</span>
        </div>
        <div className='cardBody'>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 14 }}>
            <div className='note' style={{ display: 'grid', gap: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                <strong>Agent workflow</strong>
                <span className='pill p-cyan'>{agents.length || 0} agents</span>
              </div>
              <label className='label'>Agent</label>
              <select className='input' value={currentAgent?.id || ''} onChange={(e) => selectAgent(e.target.value)} disabled={callActive || status === 'speaking' || status === 'thinking'}>
                <option value=''>Select an agent</option>
                {agents.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name || agent.slug} {agent.slug ? `(${agent.slug})` : ''}
                  </option>
                ))}
              </select>
              <div className='muted' style={{ fontSize: 12 }}>The selected agent's saved system prompt is the call workflow used for this demo.</div>
            </div>

            {selectedProvider !== 'vapi' ? (
              <div className='note' style={{ display: 'grid', gap: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                  <strong>Speech-to-text</strong>
                <span className={`pill ${recognitionSupported ? 'p-green' : 'p-amber'}`}>{recognitionSupported ? 'Chrome ready' : 'fallback'}</span>
              </div>
              <label className='label'>Mode</label>
              <select className='input' value={voiceMode} onChange={(e) => setVoiceMode(e.target.value)} disabled={callActive || status === 'speaking' || status === 'thinking'}>
                <option value='streaming'>Streaming</option>
                <option value='sequential'>Sequential</option>
              </select>
              <label className='label'>Provider</label>
              <select className='input' value={sttProvider} onChange={(e) => setSttProvider(e.target.value)}>
                {STT_PROVIDERS.map((provider) => (
                  <option key={provider.id} value={provider.id}>{provider.label}</option>
                ))}
              </select>
              {['elevenlabs', 'groq', 'azure_speech', 'deepgram'].includes(sttProvider) ? (
                <>
                  <div className='actions'>
                    <button className='btn soft' onClick={startElevenLabsSttTest} disabled={sttRecording}>
                      Record STT test
                    </button>
                    <button className='btn primary' onClick={stopElevenLabsSttTest} disabled={!sttRecording}>
                      Stop and transcribe
                    </button>
                  </div>
                  {moduleResult.stt ? <div className='muted' style={{ fontSize: 12 }}>{moduleResult.stt}</div> : null}
                  <div className='muted' style={{ fontSize: 12 }}>{sttProvider === 'deepgram' ? 'Deepgram realtime is used for live calls and this recorded module test.' : sttProvider === 'groq' ? 'Groq Whisper uses whisper-large-v3-turbo and forces language=en.' : 'ElevenLabs STT uses Scribe for a recorded clip.'}</div>
                </>
              ) : (
                <div className='muted' style={{ fontSize: 12 }}>
                  {sttProvider === 'azure_speech'
                    ? 'Azure STT settings are selectable here, but the live browser loop still captures speech with Chrome until backend streaming STT is added.'
                    : 'For live calls, Chrome Web Speech captures the microphone transcript.'}
                </div>
              )}
              </div>
            ) : null}

            <div className='note' style={{ display: 'grid', gap: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                <strong>LLM</strong>
                <span className='pill p-cyan'>{providerLabel(selectedProvider)}</span>
              </div>
              <label className='label'>Provider</label>
              <select className='input' value={selectedProvider} onChange={(e) => setSelectedProvider(e.target.value)} disabled={callActive || status === 'speaking' || status === 'thinking'}>
                {PROVIDERS.map((provider) => (
                  <option key={provider.id} value={provider.id}>{provider.label}</option>
                ))}
              </select>
              {selectedProvider !== 'vapi' ? (
                <button className='btn soft' onClick={runLlmModuleTest} disabled={status === 'thinking' || status === 'speaking'}>
                  Test LLM only
                </button>
              ) : (
                <div className='note'>Vapi owns STT, LLM, TTS, interruption handling, and voice settings from the Vapi dashboard. This app only stores the public key, optional API key, and assistant ID, then starts the web call.</div>
              )}
              {moduleResult.llm ? <div className='muted' style={{ fontSize: 12 }}>{moduleResult.llm}</div> : null}
            </div>

            {selectedProvider === 'vapi' ? (
              <div className='note' style={{ display: 'grid', gap: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                  <strong>Vapi assistant</strong>
                  <span className={`pill ${providerConfig?.vapi?.configured ? 'p-green' : 'p-amber'}`}>{providerConfig?.vapi?.configured ? 'Configured' : 'Not configured'}</span>
                </div>
                <div className='muted' style={{ fontSize: 12 }}>
                  Assistant ID: {providerConfig?.vapi?.assistant_id || 'not set'}
                </div>
                <div className='muted' style={{ fontSize: 12 }}>
                  Configure Vapi STT, model, tools, and voice in the Vapi dashboard. This demo will start a web call using that assistant.
                </div>
                <button className='btn soft' type='button' onClick={() => window.location.assign('/integrations/vapi')} disabled={callActive || status === 'thinking' || status === 'speaking'}>
                  Open Vapi integration
                </button>
              </div>
            ) : (
              <div className='note' style={{ display: 'grid', gap: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                  <strong>Text-to-speech</strong>
                <span className='pill p-cyan'>{TTS_PROVIDERS.find((provider) => provider.id === ttsProvider)?.label}</span>
              </div>
              <label className='label'>TTS provider</label>
              <select className='input' value={ttsProvider} onChange={(e) => setTtsProvider(e.target.value)}>
                {TTS_PROVIDERS.map((provider) => (
                  <option key={provider.id} value={provider.id}>{provider.label}</option>
                ))}
              </select>
              {ttsProvider === 'groq_orpheus' ? (
                <>
                  <label className='label'>Groq Orpheus voice</label>
                  <select className='input' value={groqTtsVoice} onChange={(e) => setGroqTtsVoice(e.target.value)}>
                    {GROQ_ORPHEUS_VOICES.map((voice) => (
                      <option key={voice} value={voice}>{voice}</option>
                    ))}
                  </select>
                </>
              ) : ttsProvider === 'cartesia' ? (
                <>
                  <label className='label'>Cartesia voice ID</label>
                  <input className='input' value={cartesiaVoiceId} onChange={(e) => setCartesiaVoiceId(e.target.value)} placeholder={providerConfig?.cartesia?.voice_id || 'Use admin default or paste voice_id'} />
                  <div className='muted' style={{ fontSize: 12 }}>Cartesia audio is generated as soon as sentence chunks are ready for low first-audio latency.</div>
                </>
              ) : ttsProvider === 'elevenlabs' ? (
                <>
                  <label className='label'>ElevenLabs voice ID</label>
                  <input className='input' value={elevenLabsVoiceId} onChange={(e) => setElevenLabsVoiceId(e.target.value)} placeholder='Use admin default or paste voice_id' />
                  <details>
                    <summary style={{ cursor: 'pointer', fontWeight: 700 }}>Voice settings</summary>
                    <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
                      {[
                        ['stability', 'Stability'],
                        ['similarity_boost', 'Similarity boost'],
                        ['style', 'Style'],
                        ['speed', 'Speed'],
                      ].map(([field, label]) => (
                        <input key={field} className='input' value={String(elevenLabsSettings[field] ?? '')} onChange={(e) => setElevenLabsSettings((prev) => ({ ...prev, [field]: e.target.value }))} placeholder={label} />
                      ))}
                      <label style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <input type='checkbox' checked={elevenLabsSettings.speaker_boost !== false} onChange={(e) => setElevenLabsSettings((prev) => ({ ...prev, speaker_boost: e.target.checked }))} />
                        <span>Speaker boost</span>
                      </label>
                    </div>
                  </details>
                </>
              ) : (
                <>
                  <label className='label'>Azure voice</label>
                  <select className='input' value={demoVoice} onChange={(e) => setDemoVoice(e.target.value)}>
                    {DEMO_VOICES.map((voice) => (
                      <option key={voice.id} value={voice.id}>{voice.label}</option>
                    ))}
                  </select>
                  <label className='label'>Speech speed</label>
                  <select className='input' value={speechSpeed} onChange={(e) => setSpeechSpeed(e.target.value)}>
                    <option value='normal'>Normal</option>
                    <option value='slightly_fast'>Slightly fast</option>
                  </select>
                </>
              )}
              <textarea className='input' rows={2} value={moduleTestText} onChange={(e) => setModuleTestText(e.target.value)} />
              <button className='btn soft' onClick={runTtsModuleTest} disabled={(ttsProvider === 'elevenlabs' && !String(elevenLabsVoiceId || providerConfig?.elevenlabs?.default_voice_id || '').trim()) || (ttsProvider === 'cartesia' && !String(cartesiaVoiceId || providerConfig?.cartesia?.voice_id || '').trim())}>
                Test TTS only
              </button>
              {moduleResult.tts ? <div className='muted' style={{ fontSize: 12 }}>{moduleResult.tts}</div> : null}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className='grid-12'>
        <div className='span-5 stack'>
          <div className='card'>
            <div className='cardHead'>
              <div>
                <h3>2. Run Full Call</h3>
                <p className='muted' style={{ margin: '4px 0 0' }}>Uses the module choices above.</p>
              </div>
              <span className={`pill ${status === 'listening' ? 'p-green' : status === 'speaking' ? 'p-cyan' : status === 'preparing_mic' ? 'p-amber' : 'p-cyan'}`}>{status}</span>
            </div>
            <div className='cardBody stack'>
              <div className='note' style={{ borderColor: status === 'listening' ? 'rgba(34,197,94,0.45)' : 'rgba(245,158,11,0.35)' }}>
                {status === 'listening'
                  ? 'Mic is ready. Speak normally, then pause.'
                  : status === 'preparing_mic'
                    ? 'Preparing microphone. Wait for listening before speaking.'
                    : status === 'speaking'
                      ? 'Vox is speaking. Use interrupt if you want to talk now.'
                      : status === 'thinking'
                        ? 'Vox is thinking and streaming the reply.'
                        : callActive ? 'Call active.' : 'Call idle.'}
              </div>
              <div className='actions'>
                <button className='btn primary' onClick={startCall} disabled={callActive || status === 'processing' || status === 'thinking' || status === 'speaking'}>
                  {selectedProvider === 'telnyx' ? 'Call my phone' : selectedProvider === 'vapi' ? (vapiActive ? 'Vapi call active' : 'Start Vapi web call') : 'Start call'}
                </button>
                <button className='btn soft' type='button' onClick={resumeQueuedAudio}>
                  {audioUnlocked ? 'Audio ready' : 'Enable audio'}
                </button>
                {selectedProvider !== 'vapi' ? (
                  <button className='btn soft' type='button' onClick={() => setSelectedProvider('vapi')} disabled={callActive || status === 'thinking' || status === 'speaking'}>
                    Use Vapi web call
                  </button>
                ) : null}
                <button className='btn primary' onClick={interruptCurrentReply} disabled={!callActive || (status !== 'speaking' && status !== 'thinking' && !streamConnected && audioQueueLength === 0)}>
                  Stop AI & talk
                </button>
                <button className='btn soft' onClick={() => hangUp('ended')} disabled={!callActive && status !== 'speaking' && status !== 'processing' && status !== 'thinking'}>
                  Hang up
                </button>
                <button className='btn soft' onClick={clearConversation}>
                  Clear
                </button>
              </div>
              {selectedProvider === 'vapi' ? (
                <div className='note'>
                  <strong>Vapi web call mode</strong>
                  <div className='muted' style={{ fontSize: 12, marginTop: 6 }}>
                    This skips the app STT/LLM/TTS modules. Vapi starts the configured assistant directly in the browser using the assistant ID saved in Integrations.
                  </div>
                  <div className='muted' style={{ fontSize: 12, marginTop: 8 }}>
                    Vapi status: {providerConfig?.vapi?.configured ? `ready (${providerConfig?.vapi?.assistant_id || 'assistant'})` : `missing ${(providerConfig?.vapi?.missing || []).join(', ') || 'settings'}`}
                  </div>
                  {vapiActive ? <div className='pill p-green' style={{ marginTop: 10, width: 'fit-content' }}>Web call active</div> : null}
                </div>
              ) : null}
              {selectedProvider === 'telnyx' ? (
                <div className='note'>
                  <strong>Telnyx phone call mode</strong>
                  <div className='muted' style={{ fontSize: 12, marginTop: 6 }}>
                    This skips the browser voice loop. VOXBULK calls your phone and uses the selected Vox Sales agent prompt on the real call.
                  </div>
                  <label className='label'>My phone number</label>
                  <input className='input' value={telnyxPhone} onChange={(e) => setTelnyxPhone(e.target.value)} placeholder='+44...' />
                  <div className='muted' style={{ fontSize: 12, marginTop: 8 }}>
                    Uses admin-saved Telnyx settings and the selected agent prompt/workflow.
                  </div>
                  <div className='actions' style={{ marginTop: 10 }}>
                    <button className='btn primary' onClick={startTelnyxPhoneCall} disabled={telnyxCalling || !telnyxPhone.trim()}>
                      {telnyxCalling ? 'Calling...' : 'Call my phone'}
                    </button>
                  </div>
                  <div className='muted' style={{ fontSize: 12, marginTop: 8 }}>
                    Telnyx status: {telnyxCall?.status || (providerConfig?.telnyx?.configured ? 'ready' : `missing ${(providerConfig?.telnyx?.missing || []).join(', ') || 'settings'}`)}
                    {telnyxCall?.external_call_id ? ` | ${telnyxCall.external_call_id}` : ''}
                  </div>
                </div>
              ) : null}
              <div className='note'>
                {selectedProvider === 'vapi'
                  ? `Full flow: Vapi assistant ${providerConfig?.vapi?.assistant_id || 'not configured'} (configured in Vapi dashboard)`
                  : <>Full flow: {sttProvider} transcript {'->'} {providerLabel(selectedProvider)} {'->'} {ttsProvider === 'cartesia' ? `Cartesia voice ${cartesiaVoiceId || providerConfig?.cartesia?.voice_id || 'not set'}` : ttsProvider === 'elevenlabs' ? `ElevenLabs voice ${elevenLabsVoiceId || providerConfig?.elevenlabs?.default_voice_id || 'not set'}` : `Groq Orpheus ${groqTtsVoice}`}</>}
              </div>
              {sttProvider !== 'deepgram' ? (
                <div className='note' style={{ borderColor: 'rgba(245,158,11,0.35)' }}>
                  Live call note: Deepgram is the realtime live STT path. ElevenLabs and Groq STT are available as recorded module tests.
                </div>
              ) : null}
              <label className='label'>Live transcript</label>
              <textarea className='input' rows={4} value={liveTranscript} readOnly placeholder='Your live transcript appears here while you speak.' />
              <label className='label'>Text fallback / quick send</label>
              <textarea className='input' rows={3} value={textInput} onChange={(e) => setTextInput(e.target.value)} placeholder='Type what you want to say to Vox Sales...' />
              <div className='actions'>
                <button className='btn primary' onClick={sendTyped} disabled={!textInput.trim() || status === 'processing' || status === 'thinking' || status === 'speaking'}>
                  Send typed message
                </button>
                {TEST_PHRASES.map((phrase) => (
                  <button key={phrase} className='btn soft' onClick={() => sendToAgent(phrase, messages, false)} disabled={status === 'processing' || status === 'thinking' || status === 'speaking'}>
                    {phrase}
                  </button>
                ))}
              </div>
              {latestAudioSrc ? (
                <div className='note'>
                  {playbackBlocked ? <div style={{ marginBottom: 8 }}>Browser blocked autoplay. Click Enable audio, then resume playback.</div> : null}
                  <div className='actions' style={{ marginBottom: 8 }}>
                    <button className='btn soft' type='button' onClick={resumeQueuedAudio}>
                      Enable audio / resume queue
                    </button>
                    <button className='btn soft' type='button' onClick={() => playAudioSrc(latestAudioSrc)}>
                    Play latest reply
                    </button>
                  </div>
                  <audio controls src={latestAudioSrc} style={{ width: '100%' }} />
                  <div className='muted' style={{ fontSize: 12, marginTop: 6 }}>Latest audio: {latestAudioBytes || '-'} bytes</div>
                </div>
              ) : null}
            </div>
          </div>
        </div>

        <div className='span-7 stack'>
          <div className='card'>
            <div className='cardHead'>
              <div>
                <h3>3. Results</h3>
                <p className='muted' style={{ margin: '4px 0 0' }}>Latency, latest reply audio, and conversation access.</p>
              </div>
              <button className='btn primary' onClick={() => setConversationOpen(true)}>
                Open conversation ({messages.length})
              </button>
            </div>
            <div className='cardBody stack'>
              <div className='note' style={{ display: 'grid', gap: 8 }}>
                <strong>Latency</strong>
                <div>{latencySummary.label}</div>
                <div className='muted' style={{ fontSize: 12 }}>
                  First text measures first LLM token. First audio measures first playable TTS chunk. Total measures backend stream completion.
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10 }}>
                <div className='note'>
                  <div className='label'>First text</div>
                  <strong>{latencySummary.firstText != null ? `${(latencySummary.firstText / 1000).toFixed(1)}s` : '-'}</strong>
                </div>
                <div className='note'>
                  <div className='label'>First audio</div>
                  <strong>{latencySummary.firstAudio != null ? `${(latencySummary.firstAudio / 1000).toFixed(1)}s` : '-'}</strong>
                </div>
                <div className='note'>
                  <div className='label'>Total</div>
                  <strong>{latencySummary.total != null ? `${(latencySummary.total / 1000).toFixed(1)}s` : '-'}</strong>
                </div>
              </div>
              <div className='note'>
                <div className='label'>Latest transcript / reply</div>
                <div style={{ whiteSpace: 'pre-wrap', marginTop: 6 }}>
                  {messages.length ? messages[messages.length - 1]?.text || 'Streaming...' : 'No messages yet. Start a call or use a test phrase.'}
                </div>
              </div>
              <div className='actions'>
                <button className='btn primary' onClick={() => setConversationOpen(true)}>
                  Open conversation popup
                </button>
                <button className='btn soft' onClick={clearConversation}>
                  Clear conversation
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {conversationOpen ? (
        <div
          role='dialog'
          aria-modal='true'
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 80,
            background: 'rgba(15,23,42,0.62)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 20,
          }}
          onClick={() => setConversationOpen(false)}
        >
          <div className='card' style={{ width: 'min(980px, 100%)', maxHeight: '86vh', margin: 0, display: 'flex', flexDirection: 'column' }} onClick={(e) => e.stopPropagation()}>
            <div className='cardHead'>
              <div>
                <h3>Conversation</h3>
                <p className='muted' style={{ margin: '4px 0 0' }}>{messages.length} messages | Status: {status}</p>
              </div>
              <div className='actions'>
                <button className='btn soft' onClick={clearConversation}>
                  Clear
                </button>
                <button className='btn primary' onClick={() => setConversationOpen(false)}>
                  Close
                </button>
              </div>
            </div>
            <div className='cardBody' style={{ overflowY: 'auto' }}>
              <div style={{ display: 'grid', gap: 10 }}>
                {messages.length === 0 ? <div className='note'>Choose modules, click “Start call”, allow microphone access, speak, then pause. Or use a test phrase.</div> : null}
                {messages.map((m, idx) => (
                  <div key={`${m.role}-${idx}`} className='note' style={{ borderColor: m.role === 'user' ? 'rgba(14,165,233,0.35)' : 'rgba(34,197,94,0.35)' }}>
                    <div className='label'>{m.role === 'user' ? 'You said' : `${agentLabel} replied`}{m.streaming ? ' streaming...' : ''}</div>
                    <div style={{ whiteSpace: 'pre-wrap', marginTop: 4 }}>{m.text || (m.streaming ? 'Waiting for first words...' : '')}</div>
                  </div>
                ))}
                <div ref={conversationEndRef} />
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <details className='card' style={{ marginTop: 16 }}>
        <summary className='cardHead' style={{ cursor: 'pointer' }}>
          <h3>Advanced: prompt, timings, and debug</h3>
          <span className={`pill ${streamConnected ? 'p-green' : 'p-cyan'}`}>{streamConnected ? 'stream connected' : 'closed'}</span>
        </summary>
        <div className='cardBody'>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 }}>
            <div className='note' style={{ display: 'grid', gap: 10 }}>
              <strong>Vox Sales call prompt</strong>
              <textarea className='input' rows={8} value={callPrompt} onChange={(e) => setCallPrompt(e.target.value)} placeholder='Load Vox Sales agent to edit the call prompt.' />
              {promptMessage ? <div className='muted' style={{ fontSize: 12 }}>{promptMessage}</div> : null}
              <div className='actions'>
                <button className='btn primary' onClick={saveCallPrompt} disabled={promptSaving || !currentAgent?.id || !callPrompt.trim()}>
                  {promptSaving ? 'Saving prompt...' : 'Save call prompt'}
                </button>
                <button className='btn soft' onClick={() => setCallPrompt(DEFAULT_VOX_CALL_PROMPT)} disabled={promptSaving}>
                  Use recommended prompt
                </button>
              </div>
            </div>

            <div className='note' style={{ display: 'grid', gap: 4, fontSize: 13 }}>
              <strong>Latest timings</strong>
              {latestTimings ? (
                <>
                  <div>First audio: {latestTimings.first_audio_latency_ms != null ? `${(latestTimings.first_audio_latency_ms / 1000).toFixed(1)}s` : 'waiting'}</div>
                  <div>Total: {(latestTimings.total_completion_ms ?? latestTimings.backend?.full_complete) != null ? `${((latestTimings.total_completion_ms ?? latestTimings.backend?.full_complete) / 1000).toFixed(1)}s` : 'waiting'}</div>
                  <div>First text: {latestTimings.first_text_latency_ms ?? latestTimings.backend?.first_text_ms ?? 'waiting'} ms</div>
                  <div>First sentence: {latestTimings.backend?.first_sentence_ready ?? latestTimings.backend?.first_sentence_ready_ms ?? '-'} ms</div>
                  <div>Playback start: {latestTimings.browser_playback_start ?? latestTimings.browser_audio_playback_start_ms ?? 'waiting'} ms</div>
                  <div>Interrupt to audio stop: {turnTakingMetrics.interrupt_to_audio_stop_ms ?? '-'} ms</div>
                  <div>Playback end to mic ready: {turnTakingMetrics.playback_end_to_recognizer_ready_ms ?? '-'} ms</div>
                </>
              ) : (
                <div>No timing data yet.</div>
              )}
            </div>

            <div className='note' style={{ display: 'grid', gap: 4, fontSize: 13 }}>
              <strong>Debug</strong>
              <div>Status: {status}</div>
              <div>Recognizer active: {recognitionActiveRef.current ? 'yes' : 'no'}</div>
              <div>Recognizer starting: {recognitionStartingRef.current ? 'yes' : 'no'}</div>
              <div>DeepSeek configured: {providerConfig?.deepseek?.configured ? 'yes' : 'no'}</div>
              <div>Vapi configured: {providerConfig?.vapi?.configured ? 'yes' : 'no'}</div>
              <div>ElevenLabs configured: {providerConfig?.elevenlabs?.configured ? 'yes' : 'no'}</div>
              <div>Chunks received: {chunksReceived}</div>
              <div>Audio queue length: {audioQueueLength}</div>
              <div>Streaming endpoint: /admin/demo/agent-call/stream</div>
            </div>
          </div>
        </div>
      </details>
    </>
  )
}
