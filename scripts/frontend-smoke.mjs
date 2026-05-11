import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = process.cwd()

const checks = [
  {
    file: 'dashboard.voxbulk.com/dashboard-web/src/main.jsx',
    labels: [
      ['dashboard packages route', '<Route path="/packages"'],
      ['dashboard support route', '<Route path="/support"'],
      ['dashboard FAQ route', '<Route path="/faq"'],
      ['GoCardless start endpoint', '/billing/subscription/gocardless/start'],
      ['GoCardless complete endpoint', '/billing/subscription/gocardless/complete'],
      ['support ticket create endpoint', '/support/tickets/upload'],
      ['Twilio WhatsApp send endpoint', '/whatsapp/send'],
      ['Telnyx call start endpoint', '/calls/start'],
      ['Telnyx call button', 'Start Telnyx voice-agent call'],
      ['Telnyx phone save endpoint', '/auth/me/phone'],
      ['Telnyx phone verify endpoint', '/auth/me/phone/verify'],
      ['Telnyx caller ID status', 'telnyx_verified_number_id'],
      ['FAQ API endpoint', '/faq'],
    ],
  },
  {
    file: 'admin.voxbulk.com/adim-web/src/App.jsx',
    labels: [
      ['admin support tickets route', "/support/tickets"],
      ['admin support detail route', "/support/tickets/:ticketId"],
      ['admin help centre route', "/support/help"],
      ['admin FAQ route', "/support/faq"],
      ['admin operations call queue route', "/operations/call-queue"],
      ['admin agents route', "/ai/agents"],
      ['admin GoCardless route', "/integrations/gocardless"],
      ['admin Telnyx route', "/integrations/telnyx"],
      ['admin Azure Speech route', "/integrations/azure_speech"],
      ['admin OpenAI route', "/integrations/openai"],
      ['admin agent demo route', "/ai/agent-demo"],
    ],
  },
  {
    file: 'admin.voxbulk.com/adim-web/src/components/layout/Sidebar.jsx',
    labels: [
      ['sidebar Telnyx voice settings link', '/integrations/telnyx'],
      ['sidebar Azure Speech settings link', '/integrations/azure_speech'],
      ['sidebar OpenAI settings link', '/integrations/openai'],
      ['sidebar Agents link', '/ai/agents'],
      ['sidebar Vox Sales demo link', '/ai/agent-demo'],
      ['sidebar Twilio legacy label', 'Twilio legacy'],
      ['sidebar Integrations open by default', "'Integrations'"],
    ],
  },
  {
    file: 'admin.voxbulk.com/adim-web/src/pages/OperationsQueue.jsx',
    labels: [
      ['operations recovery list endpoint', '/admin/operations/recovery-jobs'],
      ['operations webhook list endpoint', '/admin/operations/webhooks'],
      ['operations retry button', 'Retry'],
    ],
  },
  {
    file: 'admin.voxbulk.com/adim-web/src/pages/Integrations.jsx',
    labels: [
      ['Twilio sandbox UI', 'Twilio sandbox/test setup'],
      ['Twilio auth token field', 'auth_token_draft'],
      ['Twilio WhatsApp sandbox number field', 'whatsapp_from'],
      ['Twilio voice webhook field', 'voice_webhook_url'],
      ['Twilio caller ID callback field', 'caller_id_status_callback_url'],
      ['Telnyx voice setup', 'Telnyx active voice setup'],
      ['Telnyx API key field', 'api_key_draft'],
      ['Telnyx webhook base field', 'webhook_base_url'],
      ['Telnyx media stream field', 'media_stream_url'],
      ['Azure Speech setup', 'Azure Speech setup'],
      ['Azure British voice field', 'default_voice_id'],
      ['Azure recommended voice default', 'en-GB-AbbiNeural'],
      ['Azure TTS enable field', 'tts_enabled'],
      ['Azure TTS test action', 'Test Azure TTS'],
      ['OpenAI setup', 'OpenAI live call setup'],
      ['OpenAI default realtime model', 'gpt-realtime-1.5'],
      ['OpenAI default model field', 'default_model'],
      ['OpenAI temperature field', 'temperature'],
      ['OpenAI max tokens field', 'max_output_tokens'],
      ['OpenAI test action', 'Test OpenAI'],
      ['GoCardless sandbox UI', 'GoCardless sandbox setup'],
      ['GoCardless token field', 'access_token_draft'],
      ['GoCardless webhook URL field', 'webhook_url'],
      ['GoCardless webhook secret field', 'webhook_secret_draft'],
      ['GoCardless environment field', 'environment'],
    ],
  },
  {
    file: 'admin.voxbulk.com/adim-web/src/pages/Agents.jsx',
    labels: [
      ['agents page title', '<h1>Agents</h1>'],
      ['agents system prompt textarea', 'Call workflow / system prompt'],
      ['agents assignment organisation control', 'Assigned organisations'],
      ['agents assignment business type control', 'Category default'],
      ['agents preview action', 'Preview response'],
      ['agents tool toggle', 'allow_lookup_tool'],
    ],
  },
  {
    file: 'admin.voxbulk.com/adim-web/src/pages/AgentDemo.jsx',
    labels: [
      ['agent demo title', 'Vox Sales Demo Lab'],
      ['agent demo API endpoint', '/admin/demo/agent-call'],
      ['agent demo speech recognition', 'SpeechRecognition'],
      ['agent demo agent slug', 'vox-sales'],
      ['agent demo clear action', 'Clear conversation'],
      ['agent demo start call button', 'Start call'],
      ['agent demo hang up button', 'Hang up'],
      ['agent demo manual play fallback', 'Play Vox Reply'],
      ['agent demo autoplay blocked message', 'Chrome blocked autoplay'],
    ],
  },
  {
    file: 'voxbulk.com/frontend/src/components/AuthModal.tsx',
    labels: [
      ['OAuth provider discovery', 'fetchSocialLoginProviders'],
      ['Google OAuth button path', 'google'],
      ['Facebook OAuth button path', 'facebook'],
      ['LinkedIn OAuth button path', 'linkedin'],
    ],
  },
]

const failures = []

for (const check of checks) {
  const abs = resolve(root, check.file)
  const text = readFileSync(abs, 'utf8')
  for (const [label, needle] of check.labels) {
    if (!text.includes(needle)) {
      failures.push(`${check.file}: missing ${label} (${needle})`)
    }
  }
}

if (failures.length) {
  console.error('Frontend smoke checks failed:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log(`Frontend smoke checks passed (${checks.reduce((n, c) => n + c.labels.length, 0)} assertions).`)
