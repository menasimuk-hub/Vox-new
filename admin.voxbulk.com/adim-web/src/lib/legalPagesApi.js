import { apiFetch } from './api'
import bundledDefaults from '../data/legalDefaultBodies.json'

export const LEGAL_PAGE_META = [
  { slug: 'terms', title: 'Terms & Conditions' },
  { slug: 'privacy', title: 'Privacy Policy' },
  { slug: 'cookies', title: 'Cookie Policy' },
  { slug: 'gdpr', title: 'GDPR' },
  { slug: 'legal', title: 'Legal' },
]

const ADMIN_LIST_PATHS = ['/admin/email/legal-pages', '/admin/legal-pages']

function draftStorageKey(slug) {
  return `vox_legal_draft_${slug}`
}

export function readLocalLegalDraft(slug) {
  try {
    const raw = localStorage.getItem(draftStorageKey(slug))
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function writeLocalLegalDraft(slug, draft) {
  localStorage.setItem(draftStorageKey(slug), JSON.stringify({ ...draft, saved_at: new Date().toISOString() }))
}

export function bundledLegalRows() {
  return LEGAL_PAGE_META.map((meta) => ({
    slug: meta.slug,
    title: meta.title,
    public_path: '/legal-policies',
    meta_description: '',
    body: bundledDefaults[meta.slug] || '',
    is_published: true,
    updated_at: readLocalLegalDraft(meta.slug)?.saved_at || null,
    offline: true,
  }))
}

export function bundledLegalPage(slug) {
  const meta = LEGAL_PAGE_META.find((row) => row.slug === slug)
  if (!meta) return null
  const local = readLocalLegalDraft(slug)
  return {
    slug,
    title: local?.title || meta.title,
    public_path: '/legal-policies',
    meta_description: local?.meta_description || '',
    body: local?.body || bundledDefaults[slug] || '',
    is_published: local?.is_published !== false,
    updated_at: local?.saved_at || null,
    offline: true,
  }
}

async function tryList(path) {
  const data = await apiFetch(path)
  if (!Array.isArray(data)) throw new Error('Unexpected legal pages response')
  return { rows: data, apiBase: path, offline: false }
}

export async function fetchLegalPagesList() {
  let lastError = null
  for (const path of ADMIN_LIST_PATHS) {
    try {
      return await tryList(path)
    } catch (e) {
      lastError = e
      if (e?.status !== 404) throw e
    }
  }
  return { rows: bundledLegalRows(), apiBase: null, offline: true, lastError }
}

export async function fetchLegalPage(slug) {
  let lastError = null
  for (const base of ADMIN_LIST_PATHS) {
    try {
      const row = await apiFetch(`${base}/${encodeURIComponent(slug)}`)
      return { row, apiBase: base, offline: false }
    } catch (e) {
      lastError = e
      if (e?.status !== 404) throw e
    }
  }
  const row = bundledLegalPage(slug)
  if (!row) throw lastError || new Error('Legal page not found')
  return { row, apiBase: null, offline: true, lastError }
}

export async function saveLegalPage(slug, payload, apiBase) {
  const bases = apiBase ? [apiBase] : ADMIN_LIST_PATHS
  let lastError = null
  for (const base of bases) {
    try {
      const row = await apiFetch(`${base}/${encodeURIComponent(slug)}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
      return { row, apiBase: base, offline: false }
    } catch (e) {
      lastError = e
      if (e?.status !== 404) throw e
    }
  }

  writeLocalLegalDraft(slug, payload)
  return {
    row: { ...payload, slug, public_path: '/legal-policies', updated_at: new Date().toISOString() },
    apiBase: null,
    offline: true,
    lastError,
  }
}

export async function copyText(text) {
  if (navigator?.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return true
  }
  return false
}
