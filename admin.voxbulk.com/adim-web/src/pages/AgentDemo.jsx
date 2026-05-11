import React, { useEffect, useMemo, useRef, useState } from 'react'
import Vapi from '@vapi-ai/web'
import { apiFetch, getApiBaseUrl } from '../lib/api'

const DEFAULT_AGENT_SLUG = 'vox-sales'
const FINAL_SEND_DELAY_MS = 150
const TEST_PHRASES = [
  'What does Vox Sales do?',
  'We are a 200 person company with manual operations.',
  'Can you help qualify leads?',
  'Tell me briefly how you help businesses.',
]
const PROVIDERS = [
  { id: 'openai', label: 'OpenAI', voiceMode: 'Azure Speech chunks' },
  { id: 'deepseek', label: 'DeepSeek', voiceMode: 'Azure Speech chunks' },
  { id: 'vapi', label: 'Vapi', voiceMode: 'Vapi voice call' },
  { id: 'telnyx', label: 'Telnyx', voiceMode: 'Outbound phone call' },
]
const STT_PROVIDERS = [
  { id: 'browser', label: 'Browser Web Speech' },
  { id: 'azure_speech', label: 'Azure Speech (settings)' },
  { id: 'elevenlabs', label: 'ElevenLabs Scribe' },
]
const TTS_PROVIDERS = [
  { id: 'azure_speech', label: 'Azure Speech' },
  { id: 'elevenlabs', label: 'ElevenLabs' },
]
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
  const base = getApiBaseUrl()
  return `${base || ''}${path}`
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
  const finalTranscriptRef = useRef('')
  const pendingFinalRef = useRef('')
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
  const [sttProvider, setSttProvider] = useState('browser')
  const [selectedProvider, setSelectedProvider] = useState('openai')
  const [ttsProvider, setTtsProvider] = useState('azure_speech')
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

  const stopRecognition = () => {
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
        startRecognitionLoop({ reason })
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
    activeRequestIdRef.current += 1
    if (sendTimerRef.current) window.clearTimeout(sendTimerRef.current)
    if (recognitionRestartTimerRef.current) window.clearTimeout(recognitionRestartTimerRef.current)
    sendTimerRef.current = null
    recognitionRestartTimerRef.current = null
    try {
      streamAbortRef.current?.abort()
    } catch {
      // ignore
    }
    streamAbortRef.current = null
    audioQueueRef.current = []
    audioPlayingRef.current = false
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
    if (requestId !== activeRequestIdRef.current) return
    if (audioPlayingRef.current) return
    const next = audioQueueRef.current.shift()
    setAudioQueueLength(audioQueueRef.current.length)
    if (!next) {
      audioPlayingRef.current = false
      if (callActiveRef.current && !processingRef.current) scheduleMicRecovery('playback-ended', 30)
      else setCallState('done')
      return
    }
    audioPlayingRef.current = true
    setPlaybackBlocked(false)
    setCallState('speaking')
    const audio = new Audio(next.src)
    audioRef.current = audio
    audio.onplaying = () => {
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
      audioPlayingRef.current = false
      playNextAudioSegment(requestId)
    }
    audio.onerror = () => {
      if (requestId !== activeRequestIdRef.current) return
      audioPlayingRef.current = false
      setPlaybackBlocked(true)
      setError('Browser could not play one returned audio segment.')
      playNextAudioSegment(requestId)
    }
    audio.play().catch(() => {
      if (requestId !== activeRequestIdRef.current) return
      audioPlayingRef.current = false
      setPlaybackBlocked(true)
      setError('Chrome blocked autoplay. Press “Play Vox Reply” to hear the latest segment.')
    })
  }

  const enqueueAudioSegment = (segment, requestId) => {
    if (!segment?.audio_b64 || requestId !== activeRequestIdRef.current) return
    const src = dataUrlFromAudio(segment.audio_b64, segment.audio_mime || 'audio/mpeg')
    audioQueueRef.current.push({ ...segment, src })
    setAudioQueueLength(audioQueueRef.current.length)
    setLatestAudioSrc(src)
    setLatestAudioBytes(segment.audio_bytes || Math.floor((String(segment.audio_b64 || '').length * 3) / 4))
    playNextAudioSegment(requestId)
  }

  const playAudioSrc = async (src) => {
    if (!src) {
      processingRef.current = false
      if (callActiveRef.current) scheduleMicRecovery('manual-audio-missing', 30)
      else setCallState('idle')
      return
    }
    setPlaybackBlocked(false)
    setCallState('speaking')
    const audio = new Audio(src)
    audioRef.current = audio
    audio.onended = resumeListeningAfterAudio
    audio.onplaying = () => {
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
      setError('Browser could not play the returned audio. Try the Play Vox Reply button or check Azure audio output.')
      processingRef.current = false
      if (callActiveRef.current) scheduleMicRecovery('manual-audio-error', 80)
      else setCallState('idle')
    }
    try {
      await audio.play()
    } catch {
      setPlaybackBlocked(true)
      setError('Chrome blocked autoplay. Press “Play Vox Reply” to hear the agent, then the call will continue.')
      processingRef.current = false
      if (callActiveRef.current) scheduleMicRecovery('manual-audio-blocked', 80)
      else setCallState('idle')
    }
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
        }
      })
      .catch(() => {
        setAgentLabel('Vox Sales (using fallback slug vox-sales)')
      })
    apiFetch('/admin/demo/provider-config')
      .then((rows) => {
        const providers = rows?.providers || null
        setProviderConfig(providers)
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
      tts_provider: ttsProvider,
      browser_playback_start: null,
      first_text_latency_ms: null,
      first_audio_latency_ms: null,
      total_completion_ms: null,
      backend: {},
    }
    playbackTimingRef.current = baseTiming
    setLatestTimings(baseTiming)
    try {
      const token = adminToken()
      if (!token) throw new Error('No admin session token available for streaming request.')
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
        body: JSON.stringify({
          agent_slug: agentSlug,
          request_id: requestId,
          provider: selectedProvider,
          stt_provider: sttProvider,
          tts_provider: ttsProvider,
          input: text,
          history: historyPayload,
          speech_finalized_ms: speechFinalizedMs,
          browser_timings: browserTimings,
          voice_id: demoVoice,
          elevenlabs_voice_id: elevenLabsVoiceId,
          elevenlabs_voice_settings: elevenLabsSettings,
          speaking_rate: speechSpeed,
        }),
      })
      if (!response.ok || !response.body) {
        throw new Error(`Streaming request failed: ${response.status} ${response.statusText}`)
      }
      setStreamConnected(true)
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
            throw new Error(data.message || 'Streaming demo failed')
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
    if (sttProvider !== 'elevenlabs') {
      setModuleResult((prev) => ({ ...prev, stt: 'Choose ElevenLabs Scribe first.' }))
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
        setModuleResult((prev) => ({ ...prev, stt: 'Uploading audio to ElevenLabs Scribe...' }))
        try {
          const token = adminToken()
          if (!token) throw new Error('No admin session token available.')
          const form = new FormData()
          form.append('provider', 'elevenlabs')
          form.append('model_id', 'scribe_v1')
          form.append('file', blob, 'elevenlabs-stt-test.webm')
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
            stt: `ElevenLabs STT OK: ${text || '(empty transcript)'} (${result.timings?.elevenlabs_stt_total_ms || '-'} ms)`,
          }))
        } catch (e) {
          setModuleResult((prev) => ({ ...prev, stt: e?.message || 'ElevenLabs STT failed' }))
          setError(e?.message || 'ElevenLabs STT failed')
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
    if (selectedProvider === 'vapi') {
      startVapiCall()
      return
    }
    if (selectedProvider === 'telnyx') {
      startTelnyxPhoneCall()
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
          <p>Choose an agent, select STT, LLM, and TTS providers, then run a browser call or a Telnyx outbound phone call.</p>
          <p className='muted' style={{ marginTop: 6 }}>Using agent: {agentLabel}</p>
        </div>
        <div style={{ display: 'grid', justifyItems: 'end', gap: 6 }}>
          <span className={`pill ${status === 'listening' ? 'p-green' : status === 'preparing_mic' || status === 'interrupted' ? 'p-amber' : status === 'speaking' ? 'p-cyan' : status === 'ended' || status === 'error' ? 'p-amber' : 'p-cyan'}`}>{status}</span>
          <span className='muted' style={{ fontSize: 12 }}>STT {sttProvider} | LLM {providerLabel(selectedProvider)} | TTS {TTS_PROVIDERS.find((provider) => provider.id === ttsProvider)?.label}</span>
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

            <div className='note' style={{ display: 'grid', gap: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                <strong>Speech-to-text</strong>
                <span className={`pill ${recognitionSupported ? 'p-green' : 'p-amber'}`}>{recognitionSupported ? 'Chrome ready' : 'fallback'}</span>
              </div>
              <label className='label'>Provider</label>
              <select className='input' value={sttProvider} onChange={(e) => setSttProvider(e.target.value)}>
                {STT_PROVIDERS.map((provider) => (
                  <option key={provider.id} value={provider.id}>{provider.label}</option>
                ))}
              </select>
              {sttProvider === 'elevenlabs' ? (
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
                  <div className='muted' style={{ fontSize: 12 }}>ElevenLabs STT uses Scribe for a recorded clip. The live continuous call still uses Chrome Web Speech for now.</div>
                </>
              ) : (
                <div className='muted' style={{ fontSize: 12 }}>
                  {sttProvider === 'azure_speech'
                    ? 'Azure STT settings are selectable here, but the live browser loop still captures speech with Chrome until backend streaming STT is added.'
                    : 'For live calls, Chrome Web Speech captures the microphone transcript.'}
                </div>
              )}
            </div>

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
              <button className='btn soft' onClick={runLlmModuleTest} disabled={status === 'thinking' || status === 'speaking'}>
                Test LLM only
              </button>
              {selectedProvider === 'telnyx' ? (
                <div className='muted' style={{ fontSize: 12 }}>
                  Telnyx uses the selected Vox Sales agent in a real outbound phone call. Use Call my phone below.
                </div>
              ) : null}
              {moduleResult.llm ? <div className='muted' style={{ fontSize: 12 }}>{moduleResult.llm}</div> : null}
            </div>

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
              {ttsProvider === 'elevenlabs' ? (
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
              <button className='btn soft' onClick={runTtsModuleTest} disabled={ttsProvider === 'elevenlabs' && !String(elevenLabsVoiceId || providerConfig?.elevenlabs?.default_voice_id || '').trim()}>
                Test TTS only
              </button>
              {moduleResult.tts ? <div className='muted' style={{ fontSize: 12 }}>{moduleResult.tts}</div> : null}
            </div>
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
                  {selectedProvider === 'telnyx' ? 'Call my phone' : 'Start call'}
                </button>
                {selectedProvider !== 'telnyx' ? (
                  <button className='btn soft' type='button' onClick={() => setSelectedProvider('telnyx')} disabled={callActive || status === 'thinking' || status === 'speaking'}>
                    Use Telnyx phone call
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
                Full flow: {sttProvider} transcript {'->'} {providerLabel(selectedProvider)} {'->'} {ttsProvider === 'elevenlabs' ? `ElevenLabs voice ${elevenLabsVoiceId || providerConfig?.elevenlabs?.default_voice_id || 'not set'}` : demoVoice}
              </div>
              {sttProvider !== 'browser' ? (
                <div className='note' style={{ borderColor: 'rgba(245,158,11,0.35)' }}>
                  Live call note: continuous browser calls currently use Chrome Web Speech for the live microphone loop. Use the STT card above to test {STT_PROVIDERS.find((provider) => provider.id === sttProvider)?.label} transcription directly.
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
                  {playbackBlocked ? <div style={{ marginBottom: 8 }}>Chrome blocked autoplay. Press play below.</div> : null}
                  <button className='btn soft' onClick={() => playAudioSrc(latestAudioSrc)} style={{ marginBottom: 8 }}>
                    Play latest reply
                  </button>
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
