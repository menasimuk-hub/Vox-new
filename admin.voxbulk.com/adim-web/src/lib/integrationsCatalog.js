export const INTEGRATION_PROVIDERS = [
  { key: 'dentally', label: 'Dentally', icon: 'ti-building-hospital', blurb: 'Practice management sync and API.' },
  { key: 'telnyx', label: 'Telnyx', icon: 'ti-phone', blurb: 'Voice, SMS, and WhatsApp messaging.' },
  { key: 'azure_speech', label: 'Azure Speech', icon: 'ti-microphone', blurb: 'Speech-to-text and text-to-speech.' },
  { key: 'openai', label: 'OpenAI', icon: 'ti-brain', blurb: 'Realtime call reasoning models.' },
  { key: 'deepseek', label: 'DeepSeek', icon: 'ti-sparkles', blurb: 'LLM for demos and sales outcomes.' },
  { key: 'groq', label: 'Groq', icon: 'ti-bolt', blurb: 'Fast STT, LLM, and Orpheus TTS.' },
  { key: 'deepinfra', label: 'DeepInfra', icon: 'ti-microphone-2', blurb: 'Whisper STT for WA survey voice-note transcription.' },
  { key: 'deepgram', label: 'Deepgram', icon: 'ti-activity', blurb: 'Streaming speech-to-text.' },
  { key: 'cartesia', label: 'Cartesia', icon: 'ti-volume', blurb: 'Streaming text-to-speech.' },
  { key: 'elevenlabs', label: 'ElevenLabs', icon: 'ti-player-play', blurb: 'High-quality TTS voices.' },
  { key: 'vapi', label: 'Vapi', icon: 'ti-headset', blurb: 'Browser voice calls and lead recordings.' },
  { key: 'gocardless', label: 'GoCardless', icon: 'ti-credit-card', blurb: 'Direct Debit mandates for subscriptions and campaign extras.' },
  { key: 'stripe', label: 'Stripe', icon: 'ti-brand-stripe', blurb: 'Card payments for wallet top-ups.' },
  { key: 'airwallex', label: 'Airwallex', icon: 'ti-world-dollar', blurb: 'Card payments for wallet top-ups.' },
  { key: 'zoom', label: 'Zoom', icon: 'ti-brand-zoom', blurb: 'Interview campaigns via Zoom.' },
  { key: 'calendly', label: 'Calendly', icon: 'ti-calendar', blurb: 'OAuth + scheduling links for interview shortlist.' },
  { key: 'cal_com', label: 'Cal.com', icon: 'ti-calendar-event', blurb: 'OAuth + Cal.com booking links for interview shortlist.' },
  { key: 'google_calendar', label: 'Google Calendar', icon: 'ti-calendar-stats', blurb: 'OAuth + appointment schedule URLs for interview shortlist.' },
  { key: 'hubspot', label: 'HubSpot', icon: 'ti-brand-hubspot', blurb: 'OAuth + CRM sync and HubSpot Meetings for shortlisted candidates.' },
]

export const INTEGRATION_EXTRAS = [
  {
    key: 'webhooks',
    label: 'Webhooks',
    icon: 'ti-link',
    blurb: 'Inbound webhook endpoints (GoCardless, Vapi, Telnyx).',
    route: '/integrations/webhooks',
    kind: 'config',
  },
  {
    key: 'social-login',
    label: 'Social login',
    icon: 'ti-brand-google',
    blurb: 'Google, Apple, and LinkedIn sign-in.',
    route: '/integrations/social-login',
    kind: 'config',
  },
]

export function isIntegrationConnected(summary) {
  if (!summary || summary.error) return false
  if (!summary.exists) return false
  if (!summary.is_enabled) return false
  return Boolean(summary.configured)
}

export function integrationCardStatus(summary, { kind } = {}) {
  if (kind === 'config') {
    return { connected: null, label: 'Configure', pillClass: 'p-cyan', cardClass: 'isConfig' }
  }
  if (!summary) {
    return { connected: false, label: 'Loading…', pillClass: 'p-amber', cardClass: 'isLoading' }
  }
  if (summary.error) {
    return { connected: false, label: 'Not connected', pillClass: 'p-red', cardClass: 'isDisconnected' }
  }
  if (isIntegrationConnected(summary)) {
    return { connected: true, label: 'Connected', pillClass: 'p-green', cardClass: 'isConnected' }
  }
  if (!summary.exists) {
    return { connected: false, label: 'Not connected', pillClass: 'p-red', cardClass: 'isDisconnected' }
  }
  if (!summary.is_enabled) {
    return { connected: false, label: 'Disabled', pillClass: 'p-red', cardClass: 'isDisconnected' }
  }
  return { connected: false, label: 'Incomplete', pillClass: 'p-red', cardClass: 'isDisconnected' }
}

export function providerLabel(key) {
  const row = INTEGRATION_PROVIDERS.find((p) => p.key === key)
  return row?.label || key
}
