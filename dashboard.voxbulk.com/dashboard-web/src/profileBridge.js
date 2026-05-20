import { apiFetch } from './lib/api.js'
import { setClientSession, setProfileCache } from './clientContext.js'

export async function loadProfileIntoForm() {
  try {
    const org = await apiFetch('/organisations/me')
    setProfileCache({
      company_name: org.name || '',
      organiser_name: org.contact_name || '',
      caller_id: org.contact_name || org.name || '',
      phone: org.contact_phone || '',
      website: org.website || '',
    })
    fillProfileForm(org)
    return org
  } catch {
    return null
  }
}

function fillProfileForm(org = {}) {
  const set = (id, value) => {
    const el = document.getElementById(id)
    if (el && value != null) el.value = String(value)
  }
  set('prof-company-name', org.name || '')
  set('prof-organiser-name', org.contact_name || '')
  set('prof-caller-id', org.contact_name || org.name || '')
  set('prof-phone', org.contact_phone || '')
  set('prof-website', org.website || '')
}

export async function saveProfileFromForm() {
  const read = (id) => document.getElementById(id)?.value?.trim() || ''
  const company = read('prof-company-name')
  const organiser = read('prof-organiser-name')
  const phone = read('prof-phone')
  const website = read('prof-website')

  if (!company) {
    window.toast?.('Enter your company name in Profile settings', 'tr')
    return null
  }

  const updated = await apiFetch('/organisations/me', {
    method: 'PATCH',
    body: JSON.stringify({
      name: company,
      contact_name: organiser || company,
      contact_phone: phone || null,
      website: website || null,
    }),
  })

  setProfileCache({
    company_name: updated.name || company,
    organiser_name: updated.contact_name || organiser,
    caller_id: read('prof-caller-id') || updated.contact_name || updated.name,
    phone: updated.contact_phone || phone,
    website: updated.website || website,
  })

  try {
    await apiFetch('/organisations/me/ai-config', {
      method: 'PUT',
      body: JSON.stringify({
        ai_identity: {
          organisation_name: updated.name,
          assistant_name: organiser || updated.name,
        },
      }),
    })
  } catch {
    /* ai-config optional */
  }

  window.__voxbulkSession = {
    ...(window.__voxbulkSession || {}),
    org: updated,
  }
  setClientSession(window.__voxbulkSession)

  window.toast?.('Profile saved — surveys will use this name', 'tg')
  return updated
}

export function initProfileBridge(session = {}) {
  window.__voxbulkSession = session
  if (session.org) {
    setProfileCache({
      company_name: session.org.name || '',
      organiser_name: session.org.contact_name || '',
      caller_id: session.org.contact_name || session.org.name || '',
      phone: session.org.contact_phone || '',
      website: session.org.website || '',
    })
    fillProfileForm(session.org)
  }

  loadProfileIntoForm()

  document.getElementById('prof-save-btn')?.addEventListener('click', async (e) => {
    e.preventDefault()
    const btn = e.currentTarget
    btn.disabled = true
    try {
      await saveProfileFromForm()
    } catch (err) {
      window.toast?.(err.message || 'Could not save profile', 'tr')
    } finally {
      btn.disabled = false
    }
  })

  ;['prof-company-name', 'prof-organiser-name', 'prof-caller-id'].forEach((id) => {
    document.getElementById(id)?.addEventListener('change', () => {
      setProfileCache({
        company_name: document.getElementById('prof-company-name')?.value?.trim() || '',
        organiser_name: document.getElementById('prof-organiser-name')?.value?.trim() || '',
        caller_id: document.getElementById('prof-caller-id')?.value?.trim() || '',
      })
    })
  })
}
