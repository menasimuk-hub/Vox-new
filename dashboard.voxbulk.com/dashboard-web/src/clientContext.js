/** Client (tenant) identity for surveys/interviews — not Voxbulk platform branding. */

let session = {}
let sampleRecipientFirstName = ''
let profileCache = {
  company_name: '',
  organiser_name: '',
  caller_id: '',
  phone: '',
  website: '',
}

export function setProfileCache(data = {}) {
  profileCache = { ...profileCache, ...data }
}

function firstWord(name) {
  return String(name || '').trim().split(/\s+/).filter(Boolean)[0] || ''
}

export function setSampleRecipientFirstName(name) {
  sampleRecipientFirstName = firstWord(name)
}

export function getSampleRecipientFirstName() {
  return sampleRecipientFirstName
}

export function setClientSession(nextSession = {}) {
  session = nextSession || {}
  syncWaPreviewHeader()
}

function initialsFromName(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return String(name || '??').slice(0, 2).toUpperCase()
}

function isPlatformBrand(name) {
  return /voxbulk|retover/i.test(String(name || ''))
}

export function getOrganisationName() {
  const fromProfile = profileCache.company_name?.trim()
  if (fromProfile && !isPlatformBrand(fromProfile)) return fromProfile
  const fromDom = document.getElementById('prof-company-name')?.value?.trim()
  if (fromDom && !isPlatformBrand(fromDom)) return fromDom
  const ai = session.aiConfig?.ai_identity
  const org = session.org || {}
  const candidates = [ai?.organisation_name, org.name, org.contact_name].map((s) => String(s || '').trim()).filter(Boolean)
  for (const name of candidates) {
    if (!isPlatformBrand(name)) return name
  }
  return 'Your business'
}

/** Person introducing the survey — from Profile settings “Survey organiser”. */
export function getSurveyOrganiserName() {
  const fromProfile = profileCache.organiser_name?.trim()
  if (fromProfile && !isPlatformBrand(fromProfile)) return fromProfile
  const fromDom = document.getElementById('prof-organiser-name')?.value?.trim()
  if (fromDom && !isPlatformBrand(fromDom)) return fromDom
  const org = session.org || {}
  if (org.contact_name && !isPlatformBrand(org.contact_name)) return String(org.contact_name).trim()
  const assistant = getAssistantName()
  if (assistant) return assistant
  return getOrganisationName()
}

export function getAssistantName() {
  const ai = session.aiConfig?.ai_identity
  const raw = String(ai?.assistant_name || '').trim()
  if (raw && !isPlatformBrand(raw)) return raw
  return ''
}

/** Name shown as WhatsApp sender (assistant or business name). */
export function getWaSenderLabel() {
  return getSurveyOrganiserName() || getOrganisationName()
}

export function getTerminologyLabel() {
  const ai = session.aiConfig?.ai_identity
  return String(ai?.terminology_label || 'customer').trim() || 'customer'
}

/** Placeholders for preview — uses first contact from upload when available. */
export function getWaPlaceholders({ forPreview = true } = {}) {
  const orgName = getOrganisationName()
  const recipient = getSampleRecipientFirstName() || (forPreview ? 'there' : '{first_name}')
  return {
    first_name: recipient,
    clinic_name: orgName,
    organisation_name: orgName,
    assistant_name: getWaSenderLabel(),
    business_name: orgName,
  }
}

/** Strip AI template junk and apply real profile names. */
export function applyScriptPlaceholders(text, { forPreview = false } = {}) {
  const orgName = getOrganisationName()
  const organiser = getSurveyOrganiserName()
  const vars = getWaPlaceholders({ forPreview })
  vars.organiser_name = organiser
  vars.survey_organiser = organiser
  vars.your_name = organiser

  let out = String(text || '')
  const bracketReplacements = [
    [/\[Your Name\]/gi, organiser],
    [/\[your name\]/gi, organiser],
    [/\[Clinic\/Business Name\]/gi, orgName],
    [/\[Clinic Name\]/gi, orgName],
    [/\[Business Name\]/gi, orgName],
    [/\[Company Name\]/gi, orgName],
    [/\[Organisation Name\]/gi, orgName],
  ]
  bracketReplacements.forEach(([pattern, value]) => {
    out = out.replace(pattern, value)
  })
  out = out.replace(/\bVOXBULK\b/gi, orgName)
  out = out.replace(/\bVoxbulk\b/g, orgName)
  out = out.replace(/\bfrom VOXBULK\b/gi, `from ${orgName}`)
  out = out.replace(/\bon behalf of VOXBULK\b/gi, `on behalf of ${orgName}`)
  out = out.replace(/\bI'm calling on behalf of \[Clinic\/Business Name\]/gi, `I'm calling on behalf of ${orgName}`)

  Object.entries(vars).forEach(([key, value]) => {
    out = out.replaceAll(`{${key}}`, value)
  })
  return out
}

export function materialiseScriptPayload(payload = {}, { forPreview = false } = {}) {
  const out = { ...payload }
  if (out.script_text) out.script_text = applyScriptPlaceholders(out.script_text, { forPreview })
  if (out.intro) out.intro = applyScriptPlaceholders(out.intro, { forPreview })
  if (out.closing) out.closing = applyScriptPlaceholders(out.closing, { forPreview })
  if (out.whatsapp_flow) {
    const wa = { ...out.whatsapp_flow }
    if (wa.intro) wa.intro = applyScriptPlaceholders(wa.intro, { forPreview })
    if (wa.closing) wa.closing = applyScriptPlaceholders(wa.closing, { forPreview })
    if (Array.isArray(wa.questions)) {
      wa.questions = wa.questions.map((q) => {
        if (typeof q === 'string') return applyScriptPlaceholders(q, { forPreview })
        return { ...q, text: applyScriptPlaceholders(q.text, { forPreview }) }
      })
    }
    out.whatsapp_flow = wa
  }
  return out
}

/** Payload sent to AI script generation so scripts use client identity. */
export function getClientContextForApi() {
  const org = session.org || {}
  const ai = session.aiConfig?.ai_identity || {}
  const orgName = getOrganisationName()
  let assistant = String(ai.assistant_name || '').trim()
  if (!assistant || isPlatformBrand(assistant)) assistant = getSurveyOrganiserName()
  return {
    organisation_name: orgName,
    assistant_name: assistant || orgName,
    survey_organiser_name: getSurveyOrganiserName(),
    terminology_label: getTerminologyLabel(),
    contact_name: getSurveyOrganiserName(),
    website: String(profileCache.website || org.website || '').trim(),
  }
}

export function syncWaPreviewHeader() {
  const orgName = getOrganisationName()
  const title = document.getElementById('sur-wa-org-title')
  const avatar = document.getElementById('sur-wa-org-avatar')
  const sub = document.getElementById('sur-wa-preview-sub')
  if (title) title.textContent = orgName
  if (avatar) {
    avatar.classList.add('wa-survey-avatar-initials')
    avatar.textContent = initialsFromName(orgName)
  }
  if (sub) {
    sub.textContent = `Messages appear from ${orgName} — not Voxbulk`
  }
}
