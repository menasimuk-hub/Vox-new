import React, { useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch, apiUpload } from '../lib/api'

const SITE = 'https://voxbulk.com'
const PATH_PREFIX = { blog: '/blog/', news: '/news/', faq: '/faq/' }
const KIND_META = {
  blog: { label: 'Blog post', schema: 'Article', short: 'Blog' },
  news: { label: 'News item', schema: 'NewsArticle', short: 'News' },
  faq: { label: 'FAQ entry', schema: 'FAQPage', short: 'FAQ' },
}
const TABS = [
  ['overview', 'Overview'],
  ['blog', 'Blog'],
  ['news', 'News'],
  ['faq', 'FAQ'],
  ['tech', 'Technical Health'],
  ['redirects', 'Redirects'],
  ['sitemap', 'Sitemap & Robots'],
  ['apis', 'APIs'],
  ['keywords', 'Keyword Ideas'],
  ['settings', 'Site Settings'],
]
const CONTENT_KINDS = ['blog', 'news', 'faq']

const css = `
.sc-page{ --bg:#F4F1EA; --surface:#FFFFFF; --surface-2:#FBF9F4; --border:#E4DDCC; --ink:#2B2620; --muted:#8A8072; --accent:#2E3A59; --accent-hover:#232C44; --accent-soft:#E5E8EF; --danger:#B5473F; --danger-soft:#F6E8E6; --good:#1E7A4C; --good-soft:#E4F0E8; --warn:#B8791A; --warn-soft:#F6ECDD; --radius:10px; --shadow:0 1px 2px rgba(43,38,32,0.06), 0 4px 12px rgba(43,38,32,0.05); max-width:1080px; margin:0 auto; padding:8px 4px 48px; color:var(--ink); }
.sc-page *{ box-sizing:border-box; }
.sc-header{ margin-bottom:26px; }
.sc-header h1{ font-size:22px; font-weight:650; margin:0; letter-spacing:-0.01em; }
.sc-header p{ margin:4px 0 0; color:var(--muted); font-size:13px; }
.sc-tabs{ display:flex; gap:4px; background:var(--surface-2); border:1px solid var(--border); border-radius:999px; padding:4px; width:max-content; max-width:100%; margin-bottom:22px; flex-wrap:wrap; }
.sc-tab{ border:none; background:transparent; color:var(--muted); font-size:13px; font-weight:600; padding:8px 18px; border-radius:999px; cursor:pointer; white-space:nowrap; font-family:inherit; }
.sc-tab.active{ background:var(--accent); color:#fff; }
.sc-tab:not(.active):hover{ color:var(--ink); }
.sc-stat-grid{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:22px; }
.sc-stat-card{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:16px 18px; box-shadow:var(--shadow); }
.sc-stat-card .label{ font-size:11.5px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); font-weight:650; margin-bottom:8px; }
.sc-stat-card .value{ font-size:26px; font-weight:700; }
.sc-stat-card .sub{ font-size:12px; color:var(--muted); margin-top:4px; }
.sc-stat-card.good .value{ color:var(--good); }
.sc-stat-card.warn .value{ color:var(--warn); }
.sc-stat-card.danger .value{ color:var(--danger); }
.sc-kpi-grid{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:22px; }
.sc-kpi-card{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:18px 20px; box-shadow:var(--shadow); position:relative; }
.sc-kpi-head{ display:flex; align-items:center; gap:6px; margin-bottom:10px; }
.sc-kpi-label{ font-size:11.5px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); font-weight:650; }
.sc-info-icon{ width:15px; height:15px; border-radius:50%; border:1px solid var(--muted); color:var(--muted); font-size:10px; font-weight:700; display:inline-flex; align-items:center; justify-content:center; cursor:pointer; flex-shrink:0; background:transparent; padding:0; font-family:inherit; }
.sc-info-icon:hover{ border-color:var(--accent); color:var(--accent); }
.sc-kpi-value{ font-size:30px; font-weight:700; line-height:1; display:flex; align-items:baseline; gap:7px; }
.sc-kpi-value .unit{ font-size:13px; font-weight:600; color:var(--muted); }
.sc-kpi-change{ margin-top:10px; display:inline-flex; align-items:center; gap:5px; font-size:12.5px; font-weight:650; padding:3px 9px; border-radius:999px; }
.sc-kpi-change.good{ background:var(--good-soft); color:var(--good); }
.sc-kpi-change.bad{ background:var(--danger-soft); color:var(--danger); }
.sc-kpi-change.flat{ background:var(--surface-2); color:var(--muted); }
.sc-info-pop{ display:none; position:absolute; top:38px; left:20px; right:20px; z-index:10; background:var(--ink); color:#fff; font-size:12.5px; font-weight:500; line-height:1.5; padding:12px 14px; border-radius:8px; box-shadow:0 10px 30px rgba(0,0,0,0.25); }
.sc-info-pop.open{ display:block; }
.sc-info-pop .src{ display:block; margin-top:7px; color:#C9CFD8; font-size:11.5px; }
.sc-breakdown{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:20px 22px; box-shadow:var(--shadow); margin-bottom:22px; }
.sc-breakdown h3{ margin:0 0 16px; font-size:14.5px; font-weight:650; }
.sc-breakdown-row{ display:flex; align-items:center; gap:14px; margin-bottom:14px; }
.sc-breakdown-row:last-child{ margin-bottom:0; }
.sc-type-label{ width:60px; font-size:13px; font-weight:650; color:var(--muted); flex-shrink:0; }
.sc-bar{ flex:1; height:10px; border-radius:6px; background:var(--surface-2); display:flex; overflow:hidden; border:1px solid var(--border); }
.sc-bar span{ height:100%; }
.sc-totals{ width:150px; text-align:right; font-size:12px; color:var(--muted); flex-shrink:0; }
.sc-toolbar{ display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; gap:10px; flex-wrap:wrap; }
.sc-filters{ display:flex; gap:6px; flex-wrap:wrap; }
.sc-chip{ border:1px solid var(--border); background:var(--surface); color:var(--muted); font-size:12.5px; font-weight:600; padding:6px 13px; border-radius:999px; cursor:pointer; font-family:inherit; }
.sc-chip.active{ background:var(--accent-soft); color:var(--accent); border-color:var(--accent-soft); }
.sc-btn{ font-family:inherit; font-size:13.5px; font-weight:600; border-radius:8px; padding:9px 16px; border:1px solid transparent; cursor:pointer; display:inline-flex; align-items:center; gap:6px; }
.sc-btn-primary{ background:var(--accent); color:#fff; }
.sc-btn-primary:hover{ background:var(--accent-hover); }
.sc-btn-ghost{ background:transparent; color:var(--ink); border-color:var(--border); }
.sc-btn-ghost:hover{ background:var(--surface-2); }
.sc-btn-sm{ padding:6px 12px; font-size:12.5px; }
.sc-btn:disabled{ opacity:0.55; cursor:not-allowed; }
.sc-card{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; box-shadow:var(--shadow); }
.sc-table{ width:100%; border-collapse:collapse; }
.sc-table thead th{ text-align:left; font-size:11.5px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); font-weight:650; padding:12px 18px; border-bottom:1px solid var(--border); background:var(--surface-2); }
.sc-table tbody td{ padding:12px 18px; border-bottom:1px solid var(--border); font-size:14px; vertical-align:middle; }
.sc-table tbody tr:last-child td{ border-bottom:none; }
.sc-table tbody tr:hover{ background:#FBF9F4; }
.sc-row-title{ font-weight:600; }
.sc-row-meta{ font-size:12px; color:var(--muted); margin-top:2px; font-family:Consolas,Menlo,monospace; }
.sc-status{ display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:650; padding:4px 10px; border-radius:999px; }
.sc-status .dot{ width:6px; height:6px; border-radius:50%; background:currentColor; }
.sc-status.indexed,.sc-status.good{ background:var(--good-soft); color:var(--good); }
.sc-status.pending,.sc-status.warn{ background:var(--warn-soft); color:var(--warn); }
.sc-status.excluded,.sc-status.bad{ background:var(--danger-soft); color:var(--danger); }
.sc-actions{ display:flex; gap:4px; justify-content:flex-end; }
.sc-icon-btn{ width:30px; height:30px; border-radius:7px; border:1px solid transparent; background:transparent; display:inline-flex; align-items:center; justify-content:center; cursor:pointer; color:var(--muted); padding:0; }
.sc-icon-btn:hover{ background:var(--surface-2); color:var(--ink); border-color:var(--border); }
.sc-icon-btn svg{ width:16px; height:16px; }
.sc-empty{ padding:56px 20px; text-align:center; color:var(--muted); font-size:14px; }
.sc-empty strong{ display:block; color:var(--ink); font-size:15px; margin-bottom:4px; }
.sc-editor{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); box-shadow:var(--shadow); padding:26px; }
.sc-editor h2{ margin:0 0 4px; font-size:17px; font-weight:650; }
.sc-editor-sub{ font-size:13px; color:var(--muted); margin-bottom:20px; }
.sc-schema-badge{ display:inline-flex; align-items:center; gap:6px; background:var(--accent-soft); color:var(--accent); font-size:12px; font-weight:650; padding:5px 11px; border-radius:999px; }
.sc-editor-grid{ display:grid; grid-template-columns:1.1fr 0.9fr; gap:28px; align-items:start; }
.sc-field{ margin-bottom:16px; }
.sc-field label{ display:flex; justify-content:space-between; font-size:12.5px; font-weight:650; color:var(--muted); margin-bottom:6px; text-transform:uppercase; letter-spacing:.03em; }
.sc-field label .counter{ text-transform:none; letter-spacing:0; font-weight:600; }
.sc-field label .counter.over{ color:var(--danger); }
.sc-field input,.sc-field select,.sc-field textarea{ width:100%; padding:10px 12px; border:1px solid var(--border); border-radius:8px; font-size:14px; font-family:inherit; background:var(--surface-2); color:var(--ink); }
.sc-field textarea{ min-height:80px; resize:vertical; line-height:1.5; }
.sc-help{ font-size:11.5px; color:var(--muted); margin-top:5px; }
.sc-slug-wrap{ display:flex; align-items:center; border:1px solid var(--border); border-radius:8px; background:var(--surface-2); overflow:hidden; }
.sc-slug-wrap span{ padding:10px 0 10px 12px; font-size:13px; color:var(--muted); white-space:nowrap; }
.sc-slug-wrap input{ border:none; background:transparent; padding:10px 12px 10px 2px; }
.sc-slug-wrap input:focus{ outline:none; }
.sc-serp-card{ background:var(--surface-2); border:1px solid var(--border); border-radius:10px; padding:18px 20px; position:sticky; top:20px; }
.sc-serp-card h3{ margin:0 0 12px; font-size:12.5px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); font-weight:650; }
.sc-serp-preview{ background:#fff; border:1px solid var(--border); border-radius:8px; padding:16px 18px; }
.sc-serp-url{ font-size:13px; color:#1a1a1a; display:flex; align-items:center; gap:8px; margin-bottom:3px; }
.sc-favicon{ width:16px; height:16px; border-radius:50%; background:var(--accent); flex-shrink:0; }
.sc-serp-title{ color:#1a0dab; font-size:19px; line-height:1.3; margin:2px 0 4px; font-family:arial,sans-serif; }
.sc-serp-desc{ color:#4d5156; font-size:13.5px; line-height:1.5; font-family:arial,sans-serif; }
.sc-serp-badge{ margin-top:12px; font-size:11.5px; color:var(--muted); display:flex; align-items:center; gap:6px; }
.sc-editor-actions{ display:flex; justify-content:space-between; align-items:center; margin-top:22px; border-top:1px solid var(--border); padding-top:18px; gap:10px; flex-wrap:wrap; }
.sc-editor-actions .right{ display:flex; gap:10px; flex-wrap:wrap; }
.sc-settings-card{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); box-shadow:var(--shadow); padding:22px 24px; margin-bottom:18px; }
.sc-settings-card h3{ margin:0 0 3px; font-size:15px; font-weight:650; }
.sc-card-sub{ font-size:12.5px; color:var(--muted); margin-bottom:18px; }
.sc-settings-row{ display:flex; align-items:center; justify-content:space-between; padding:12px 0; border-top:1px solid var(--border); gap:12px; }
.sc-settings-row:first-of-type{ border-top:none; }
.sc-settings-row .t{ font-size:13.5px; font-weight:600; }
.sc-settings-row .d{ font-size:12px; color:var(--muted); margin-top:2px; max-width:420px; }
.sc-kv-row{ display:grid; grid-template-columns:1fr 2fr; gap:16px; align-items:center; padding:12px 0; border-top:1px solid var(--border); }
.sc-kv-row:first-of-type{ border-top:none; }
.sc-kv-row > label{ font-size:13px; font-weight:600; color:var(--ink); }
.sc-kv-row input,.sc-kv-row textarea,.sc-kv-row select{ width:100%; padding:9px 11px; border:1px solid var(--border); border-radius:8px; font-size:13.5px; font-family:inherit; background:var(--surface-2); color:var(--ink); }
.sc-kv-row textarea{ min-height:64px; resize:vertical; }
.sc-switch{ position:relative; width:40px; height:22px; flex-shrink:0; display:inline-block; }
.sc-switch input{ opacity:0; width:0; height:0; }
.sc-slider{ position:absolute; inset:0; background:var(--border); border-radius:999px; cursor:pointer; transition:.15s; }
.sc-slider::before{ content:""; position:absolute; width:16px; height:16px; left:3px; top:3px; background:#fff; border-radius:50%; transition:.15s; box-shadow:0 1px 2px rgba(0,0,0,0.2); }
.sc-switch input:checked + .sc-slider{ background:var(--accent); }
.sc-switch input:checked + .sc-slider::before{ transform:translateX(18px); }
.sc-copy-row{ display:flex; gap:8px; }
.sc-copy-row input{ flex:1; background:var(--surface-2); border:1px solid var(--border); border-radius:8px; padding:9px 11px; font-size:13px; font-family:Consolas,Menlo,monospace; color:var(--muted); }
.sc-mono{ font-family:Consolas,Menlo,monospace; font-size:13px; min-height:160px; width:100%; padding:12px; border:1px solid var(--border); border-radius:8px; background:var(--surface-2); line-height:1.6; color:var(--ink); }
.sc-metric-row{ display:flex; align-items:center; justify-content:space-between; padding:10px 0; border-top:1px solid var(--border); }
.sc-metric-name{ font-size:13px; font-weight:600; }
.sc-metric-value{ font-size:12.5px; color:var(--muted); margin-top:2px; font-family:Consolas,Menlo,monospace; }
.sc-image-row{ display:flex; gap:10px; align-items:center; }
.sc-msg{ margin-bottom:14px; font-size:13px; color:var(--muted); }
.sc-msg.error{ color:var(--danger); }
.sc-toast{ position:fixed; bottom:26px; left:50%; transform:translateX(-50%) translateY(20px); background:var(--ink); color:#fff; font-size:13.5px; font-weight:600; padding:11px 20px; border-radius:8px; box-shadow:0 8px 24px rgba(0,0,0,0.25); opacity:0; pointer-events:none; transition:all .2s ease; z-index:80; }
.sc-toast.show{ opacity:1; transform:translateX(-50%) translateY(0); }
.sc-preview-modal{ position:fixed; inset:0; background:rgba(43,38,32,0.45); display:flex; align-items:flex-start; justify-content:center; padding:48px 20px; z-index:80; overflow-y:auto; }
.sc-preview-box{ background:#fff; border-radius:12px; width:100%; max-width:560px; box-shadow:0 20px 50px rgba(0,0,0,0.25); overflow:hidden; }
.sc-preview-head{ display:flex; justify-content:space-between; align-items:center; padding:14px 20px; border-bottom:1px solid var(--border); background:var(--surface-2); }
.sc-preview-head span{ font-size:12.5px; font-weight:650; color:var(--muted); text-transform:uppercase; letter-spacing:.03em; }
.sc-preview-body{ padding:26px 28px 34px; }
@media(max-width:760px){ .sc-editor-grid{ grid-template-columns:1fr; } .sc-stat-grid{ grid-template-columns:repeat(2,1fr); } .sc-kpi-grid{ grid-template-columns:1fr; } .sc-kv-row{ grid-template-columns:1fr; } }
`

function fmtDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function fmtDay(iso) {
  if (!iso) return ''
  return String(iso).slice(0, 10)
}

function robotsToUi(robots) {
  const r = (robots || '').toLowerCase()
  if (r.includes('noindex')) return 'noindex'
  if (r.includes('nofollow')) return 'nofollow'
  return 'index'
}

function robotsFromUi(ui) {
  if (ui === 'noindex') return 'noindex'
  if (ui === 'nofollow') return 'index,nofollow'
  return 'index,follow'
}

function statusLabel(s) {
  const v = (s || 'pending').toLowerCase()
  return v.charAt(0).toUpperCase() + v.slice(1)
}

function IconEdit() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  )
}

function IconEyeOff() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-10-8-10-8a18.6 18.6 0 0 1 4.22-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 10 8 10 8a18.5 18.5 0 0 1-2.16 3.19M14.12 14.12a3 3 0 1 1-4.24-4.24" />
      <path d="M1 1l22 22" />
    </svg>
  )
}

function IconEye() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function IconSend() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M22 2 11 13" />
      <path d="M22 2 15 22l-4-9-9-4 20-7Z" />
    </svg>
  )
}

function IconTrash() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 6h18" />
      <path d="M8 6V4h8v2" />
      <path d="M19 6l-1 14H6L5 6" />
    </svg>
  )
}

function emptyDraft() {
  return {
    slug: '',
    meta_title: '',
    meta_description: '',
    canonical_url: '',
    robots: 'index',
    focus_keyword: '',
    tags: '',
    author: '',
    published_at: '',
    last_updated: '',
    social_title: '',
    social_description: '',
    social_image_url: '',
    title: '',
    path: '',
    url: '',
  }
}

const MARKETING_PAGE_KEYS = [
  ['surveys', 'WhatsApp Surveys (/surveys)'],
  ['feedback', 'Customer Feedback (/feedback)'],
  ['recruitment', 'AI Interviews / Recruitment (/recruitment)'],
  ['pricing', 'Pricing (/pricing)'],
  ['contact', 'Contact / Demo (/contact)'],
]

function emptyMarketingPage() {
  return { title: '', description: '', keywords: '', og_description: '' }
}

function emptySettings() {
  return {
    site_name: 'VoxBulk',
    title_template: '%title% | %sitename%',
    default_meta_description: '',
    default_social_image_url: '',
    home_title: '',
    home_description: '',
    home_focus_keyword: '',
    home_tags: '',
    marketing_pages: {
      surveys: emptyMarketingPage(),
      feedback: emptyMarketingPage(),
      recruitment: emptyMarketingPage(),
      pricing: emptyMarketingPage(),
      contact: emptyMarketingPage(),
    },
    schema_organization: true,
    schema_website: true,
    schema_breadcrumbs: true,
    schema_content: true,
    google_site_verification: '',
    google_analytics_id: '',
    meta_pixel_id: '',
    linkedin_partner_id: '',
    google_ads_id: '',
    x_pixel_id: '',
    tiktok_pixel_id: '',
    pinterest_tag_id: '',
    google_news_enabled: false,
    google_news_publication: '',
    google_news_language: 'en',
    gsc_property_url: '',
    gsc_oauth_configured: false,
    gsc_avg_position: null,
    gsc_avg_position_prev: null,
    connections: { gsc: false, psi: false, moz: false, bing: false, yandex: false },
    psi_api_key_set: false,
    moz_access_id_set: false,
    moz_secret_key_set: false,
    bing_api_key_set: false,
    bing_site_url: 'https://voxbulk.com',
    yandex_token_set: false,
    yandex_user_id: '',
    yandex_host_id: '',
    auto_submit_weekly: false,
    auto_indexnow_on_publish: true,
    engines_last_run_at: null,
    indexnow_key: '',
    indexnow_last_pinged_at: null,
    robots_txt: '',
  }
}

export default function SeoControl() {
  const [tab, setTab] = useState('overview')
  const [filter, setFilter] = useState('all')
  const [overview, setOverview] = useState(null)
  const [items, setItems] = useState([])
  const [health, setHealth] = useState(null)
  const [redirects, setRedirects] = useState([])
  const [sitemap, setSitemap] = useState(null)
  const [engines, setEngines] = useState(null)
  const [keywords, setKeywords] = useState([])
  const [bingKey, setBingKey] = useState('')
  const [yandexToken, setYandexToken] = useState('')
  const [settings, setSettings] = useState(emptySettings())
  const [robotsTxt, setRobotsTxt] = useState('')
  const [rdFrom, setRdFrom] = useState('')
  const [rdTo, setRdTo] = useState('')
  const [rdType, setRdType] = useState(301)
  const [psiKey, setPsiKey] = useState('')
  const [mozAccessId, setMozAccessId] = useState('')
  const [mozSecretKey, setMozSecretKey] = useState('')
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [toast, setToast] = useState('')
  const [infoOpen, setInfoOpen] = useState(null)
  const [editing, setEditing] = useState(null)
  const [draft, setDraft] = useState(emptyDraft())
  const [previewOpen, setPreviewOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef(null)
  const settingsFileRef = useRef(null)
  const toastTimer = useRef(null)

  const showToast = (text) => {
    setToast(text)
    if (toastTimer.current) clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToast(''), 2600)
  }

  const errMsg = (e, fallback) => e?.message || fallback

  const loadOverview = async () => {
    const data = await apiFetch('/admin/seo/overview')
    setOverview(data)
  }

  const loadContent = async (kind) => {
    const data = await apiFetch(`/admin/seo/content/${kind}`)
    setItems(data?.items || [])
  }

  const loadHealth = async () => {
    const data = await apiFetch('/admin/seo/health')
    setHealth(data)
  }

  const loadRedirects = async () => {
    const data = await apiFetch('/admin/seo/redirects')
    setRedirects(data?.items || [])
  }

  const loadSitemap = async () => {
    const data = await apiFetch('/admin/seo/sitemap')
    setSitemap(data)
    if (data?.indexnow_key !== undefined || data) {
      /* robots loaded via settings */
    }
  }

  const loadSettings = async () => {
    const data = await apiFetch('/admin/seo/settings')
    setSettings({ ...emptySettings(), ...data })
    setRobotsTxt(data?.robots_txt || '')
  }

  const loadEngines = async () => {
    const data = await apiFetch('/admin/seo/engines')
    setEngines(data)
  }

  const loadKeywords = async () => {
    const data = await apiFetch('/admin/seo/keywords')
    setKeywords(data?.items || [])
  }

  const refreshTab = async (nextTab = tab) => {
    setLoading(true)
    setMsg('')
    try {
      if (nextTab === 'overview') await loadOverview()
      else if (CONTENT_KINDS.includes(nextTab)) await loadContent(nextTab)
      else if (nextTab === 'tech') await loadHealth()
      else if (nextTab === 'redirects') await loadRedirects()
      else if (nextTab === 'sitemap') {
        await Promise.all([loadSitemap(), loadSettings(), loadEngines()])
      } else if (nextTab === 'apis') {
        await Promise.all([loadSettings(), loadEngines()])
      } else if (nextTab === 'keywords') await loadKeywords()
      else if (nextTab === 'settings') await Promise.all([loadSettings(), loadEngines()])
    } catch (e) {
      setMsg(errMsg(e, 'Failed to load'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshTab(tab)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search || '')
    const nextTab = params.get('tab')
    if (nextTab && TABS.some(([id]) => id === nextTab)) {
      setTab(nextTab)
    }
    const gsc = params.get('gsc')
    if (gsc === 'connected') {
      showToast('Google Search Console connected')
    } else if (gsc === 'error') {
      setMsg(params.get('message') || 'Google Search Console OAuth failed')
    }
    if (gsc || nextTab) {
      const url = new URL(window.location.href)
      url.searchParams.delete('gsc')
      url.searchParams.delete('message')
      url.searchParams.delete('tab')
      window.history.replaceState({}, '', url.pathname + url.search)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const close = () => setInfoOpen(null)
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [])

  const switchTab = (id) => {
    setEditing(null)
    setDraft(emptyDraft())
    setFilter('all')
    setTab(id)
  }

  const filtered = useMemo(() => {
    if (filter === 'all') return items
    return items.filter((i) => (i.index_status || 'pending') === filter)
  }, [items, filter])

  const openEditor = (item) => {
    setEditing(item)
    setDraft({
      slug: item.slug || '',
      meta_title: item.meta_title || '',
      meta_description: item.meta_description || '',
      canonical_url: item.canonical_url || '',
      robots: robotsToUi(item.robots),
      focus_keyword: item.focus_keyword || '',
      tags: item.tags || '',
      author: item.author || '',
      published_at: fmtDay(item.published_at),
      last_updated: fmtDay(item.last_updated),
      social_title: item.social_title || '',
      social_description: item.social_description || '',
      social_image_url: item.social_image_url || '',
      title: item.title || '',
      path: item.path || '',
      url: item.url || `${SITE}${PATH_PREFIX[tab]}${item.slug || ''}`,
    })
  }

  const closeEditor = () => {
    setEditing(null)
    setDraft(emptyDraft())
    setPreviewOpen(false)
  }

  const saveEditor = async () => {
    if (!editing) return
    setBusy(true)
    setMsg('')
    try {
      await apiFetch(`/admin/seo/content/${tab}/${editing.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          slug: draft.slug,
          meta_title: draft.meta_title,
          meta_description: draft.meta_description,
          canonical_url: draft.canonical_url,
          robots: robotsFromUi(draft.robots),
          focus_keyword: draft.focus_keyword,
          tags: draft.tags,
          author: draft.author,
          published_at: draft.published_at || null,
          social_title: draft.social_title,
          social_description: draft.social_description,
          social_image_url: draft.social_image_url || null,
        }),
      })
      showToast('SEO settings saved')
      closeEditor()
      await loadContent(tab)
    } catch (e) {
      setMsg(errMsg(e, 'Save failed'))
    } finally {
      setBusy(false)
    }
  }

  const toggleIndex = async (item) => {
    try {
      await apiFetch(`/admin/seo/content/${tab}/${item.id}/toggle-index`, { method: 'POST' })
      showToast('Index setting updated')
      await loadContent(tab)
    } catch (e) {
      setMsg(errMsg(e, 'Could not toggle index'))
    }
  }

  const requestIndexing = async (item, { closeAfter } = {}) => {
    try {
      await apiFetch(`/admin/seo/content/${tab}/${item.id}/request-indexing`, { method: 'POST' })
      showToast('Indexing requested')
      if (closeAfter) closeEditor()
      await loadContent(tab)
    } catch (e) {
      setMsg(errMsg(e, 'Could not request indexing'))
    }
  }

  const onUploadSocial = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await apiUpload('/admin/seo/upload-image', fd)
      setDraft((d) => ({ ...d, social_image_url: res.image_url || '' }))
      showToast('Image uploaded')
    } catch (e) {
      setMsg(errMsg(e, 'Image upload failed'))
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const onUploadSettingsImage = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await apiUpload('/admin/seo/upload-image', fd)
      setSettings((s) => ({ ...s, default_social_image_url: res.image_url || '' }))
      showToast('Default social image uploaded')
    } catch (e) {
      setMsg(errMsg(e, 'Image upload failed'))
    } finally {
      setUploading(false)
      if (settingsFileRef.current) settingsFileRef.current.value = ''
    }
  }

  const runPsi = async () => {
    setBusy(true)
    try {
      const data = await apiFetch('/admin/seo/health/psi', { method: 'POST' })
      setHealth(data)
      showToast('PageSpeed check complete')
    } catch (e) {
      setMsg(errMsg(e, 'PageSpeed check failed'))
    } finally {
      setBusy(false)
    }
  }

  const scanBroken = async () => {
    setBusy(true)
    try {
      const data = await apiFetch('/admin/seo/health/broken-links/scan', { method: 'POST' })
      setHealth(data)
      showToast('Broken-link scan complete')
    } catch (e) {
      setMsg(errMsg(e, 'Scan failed'))
    } finally {
      setBusy(false)
    }
  }

  const markFixed = async (url) => {
    try {
      const data = await apiFetch('/admin/seo/health/broken-links/mark-fixed', {
        method: 'POST',
        body: JSON.stringify({ url }),
      })
      setHealth(data)
      showToast('Marked fixed')
    } catch (e) {
      setMsg(errMsg(e, 'Still broken or check failed'))
    }
  }

  const addRedirect = async () => {
    if (!rdFrom.trim() || !rdTo.trim()) {
      setMsg('From and To paths are required')
      return
    }
    setBusy(true)
    try {
      await apiFetch('/admin/seo/redirects', {
        method: 'POST',
        body: JSON.stringify({
          from_path: rdFrom.trim(),
          to_path: rdTo.trim(),
          status_code: Number(rdType) || 301,
        }),
      })
      setRdFrom('')
      setRdTo('')
      showToast('Redirect added')
      await loadRedirects()
    } catch (e) {
      setMsg(errMsg(e, 'Could not add redirect'))
    } finally {
      setBusy(false)
    }
  }

  const deleteRedirect = async (id) => {
    if (!window.confirm('Delete this redirect?')) return
    try {
      await apiFetch(`/admin/seo/redirects/${id}`, { method: 'DELETE' })
      showToast('Redirect deleted')
      await loadRedirects()
    } catch (e) {
      setMsg(errMsg(e, 'Delete failed'))
    }
  }

  const regenerateSitemap = async () => {
    setBusy(true)
    try {
      const data = await apiFetch('/admin/seo/sitemap/regenerate', { method: 'POST' })
      setSitemap((s) => ({ ...s, ...data }))
      showToast('Sitemap regenerated')
    } catch (e) {
      setMsg(errMsg(e, 'Regenerate failed'))
    } finally {
      setBusy(false)
    }
  }

  const submitGoogle = async () => {
    setBusy(true)
    try {
      const data = await apiFetch('/admin/seo/sitemap/submit-google', { method: 'POST' })
      setSitemap((s) => ({ ...s, last_submitted_at: data.submitted_at }))
      await loadEngines().catch(() => {})
      showToast(data.ok ? data.note || 'Submitted to Google' : data.error || 'Google submit failed')
    } catch (e) {
      setMsg(errMsg(e, 'Submit failed'))
    } finally {
      setBusy(false)
    }
  }

  const submitAllEngines = async () => {
    setBusy(true)
    try {
      const data = await apiFetch('/admin/seo/engines/submit-all', { method: 'POST' })
      setEngines((e) => ({ ...(e || {}), engines_last_result: data, engines_last_run_at: data.ran_at }))
      await Promise.all([loadSitemap(), loadEngines()])
      const parts = ['google', 'bing', 'yandex', 'indexnow']
        .map((k) => {
          const r = data?.[k]
          if (!r) return null
          if (r.skipped) return `${k}: skipped`
          return `${k}: ${r.ok ? 'ok' : 'fail'}`
        })
        .filter(Boolean)
      showToast(`Submit finished — ${parts.join(', ')}`)
    } catch (e) {
      setMsg(errMsg(e, 'Engine submit failed'))
    } finally {
      setBusy(false)
    }
  }

  const connectBing = async () => {
    setBusy(true)
    try {
      await apiFetch('/admin/seo/engines/connect-bing', {
        method: 'POST',
        body: JSON.stringify({ api_key: bingKey, site_url: settings.bing_site_url || SITE }),
      })
      setBingKey('')
      showToast('Bing Webmaster connected')
      await Promise.all([loadEngines(), loadSettings()])
    } catch (e) {
      setMsg(errMsg(e, 'Bing connect failed'))
    } finally {
      setBusy(false)
    }
  }

  const disconnectBing = async () => {
    setBusy(true)
    try {
      await apiFetch('/admin/seo/engines/disconnect-bing', { method: 'POST' })
      showToast('Bing disconnected')
      await Promise.all([loadEngines(), loadSettings()])
    } catch (e) {
      setMsg(errMsg(e, 'Bing disconnect failed'))
    } finally {
      setBusy(false)
    }
  }

  const connectYandex = async () => {
    setBusy(true)
    try {
      await apiFetch('/admin/seo/engines/connect-yandex', {
        method: 'POST',
        body: JSON.stringify({ oauth_token: yandexToken }),
      })
      setYandexToken('')
      showToast('Yandex Webmaster connected')
      await Promise.all([loadEngines(), loadSettings()])
    } catch (e) {
      setMsg(errMsg(e, 'Yandex connect failed'))
    } finally {
      setBusy(false)
    }
  }

  const disconnectYandex = async () => {
    setBusy(true)
    try {
      await apiFetch('/admin/seo/engines/disconnect-yandex', { method: 'POST' })
      showToast('Yandex disconnected')
      await Promise.all([loadEngines(), loadSettings()])
    } catch (e) {
      setMsg(errMsg(e, 'Yandex disconnect failed'))
    } finally {
      setBusy(false)
    }
  }

  const refreshKeywords = async () => {
    setBusy(true)
    try {
      const data = await apiFetch('/admin/seo/keywords/refresh', { method: 'POST' })
      setKeywords(data?.items || [])
      showToast(`Found ${data?.suggested_count || 0} new keyword ideas`)
    } catch (e) {
      setMsg(errMsg(e, 'Keyword refresh failed'))
    } finally {
      setBusy(false)
    }
  }

  const acceptKeyword = async (idea) => {
    setBusy(true)
    try {
      const data = await apiFetch(`/admin/seo/keywords/${idea.id}/accept`, {
        method: 'POST',
        body: JSON.stringify({ target: idea.target || 'home' }),
      })
      showToast(data?.note || 'Keyword saved to page fields')
      await loadKeywords()
      await loadSettings().catch(() => {})
    } catch (e) {
      setMsg(errMsg(e, 'Accept failed'))
    } finally {
      setBusy(false)
    }
  }

  const dismissKeyword = async (idea) => {
    setBusy(true)
    try {
      await apiFetch(`/admin/seo/keywords/${idea.id}/dismiss`, { method: 'POST' })
      showToast('Dismissed')
      await loadKeywords()
    } catch (e) {
      setMsg(errMsg(e, 'Dismiss failed'))
    } finally {
      setBusy(false)
    }
  }

  const saveRobots = async () => {
    setBusy(true)
    try {
      const data = await apiFetch('/admin/seo/robots', {
        method: 'PUT',
        body: JSON.stringify({ robots_txt: robotsTxt }),
      })
      setRobotsTxt(data.robots_txt || robotsTxt)
      showToast('robots.txt saved')
    } catch (e) {
      setMsg(errMsg(e, 'Save failed'))
    } finally {
      setBusy(false)
    }
  }

  const generateIndexNow = async () => {
    setBusy(true)
    try {
      const data = await apiFetch('/admin/seo/indexnow/generate-key', { method: 'POST' })
      setSitemap((s) => ({ ...s, indexnow_key: data.indexnow_key }))
      setSettings((s) => ({ ...s, indexnow_key: data.indexnow_key }))
      showToast('IndexNow key generated')
    } catch (e) {
      setMsg(errMsg(e, 'Could not generate key'))
    } finally {
      setBusy(false)
    }
  }

  const notifyIndexNow = async () => {
    setBusy(true)
    try {
      const data = await apiFetch('/admin/seo/indexnow/notify', { method: 'POST' })
      setSitemap((s) => ({ ...s, indexnow_last_pinged_at: new Date().toISOString() }))
      showToast(data.ok ? `Notified ${data.url_count} URL(s)` : 'IndexNow ping sent')
    } catch (e) {
      setMsg(errMsg(e, 'IndexNow notify failed'))
    } finally {
      setBusy(false)
    }
  }

  const saveSettings = async (extra = {}) => {
    setBusy(true)
    setMsg('')
    try {
      const payload = {
        site_name: settings.site_name,
        title_template: settings.title_template,
        default_meta_description: settings.default_meta_description,
        default_social_image_url: settings.default_social_image_url || null,
        home_title: settings.home_title,
        home_description: settings.home_description,
        home_focus_keyword: settings.home_focus_keyword,
        home_tags: settings.home_tags,
        marketing_pages: settings.marketing_pages || {},
        schema_organization: !!settings.schema_organization,
        schema_website: !!settings.schema_website,
        schema_breadcrumbs: !!settings.schema_breadcrumbs,
        schema_content: !!settings.schema_content,
        google_site_verification: settings.google_site_verification,
        google_analytics_id: settings.google_analytics_id,
        meta_pixel_id: settings.meta_pixel_id,
        linkedin_partner_id: settings.linkedin_partner_id,
        google_ads_id: settings.google_ads_id,
        x_pixel_id: settings.x_pixel_id,
        tiktok_pixel_id: settings.tiktok_pixel_id,
        pinterest_tag_id: settings.pinterest_tag_id,
        google_news_enabled: !!settings.google_news_enabled,
        google_news_publication: settings.google_news_publication,
        google_news_language: settings.google_news_language,
        gsc_property_url: settings.gsc_property_url,
        auto_submit_weekly: !!settings.auto_submit_weekly,
        auto_indexnow_on_publish: !!settings.auto_indexnow_on_publish,
        bing_site_url: settings.bing_site_url || SITE,
        ...extra,
      }
      const data = await apiFetch('/admin/seo/settings', {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
      setSettings({ ...emptySettings(), ...data })
      showToast('Saved')
      return data
    } catch (e) {
      setMsg(errMsg(e, 'Save failed'))
      return null
    } finally {
      setBusy(false)
    }
  }

  const testGoogle = async () => {
    setBusy(true)
    try {
      const data = await apiFetch('/admin/seo/engines/test-google', { method: 'POST' })
      showToast(data.detail || 'Google OK')
      await loadSettings()
    } catch (e) {
      setMsg(errMsg(e, 'Google test failed'))
    } finally {
      setBusy(false)
    }
  }

  const testBing = async () => {
    setBusy(true)
    try {
      const data = await apiFetch('/admin/seo/engines/test-bing', { method: 'POST' })
      showToast(data.detail || 'Bing OK')
    } catch (e) {
      setMsg(errMsg(e, 'Bing test failed'))
    } finally {
      setBusy(false)
    }
  }

  const testYandex = async () => {
    setBusy(true)
    try {
      const data = await apiFetch('/admin/seo/engines/test-yandex', { method: 'POST' })
      showToast(data.detail || 'Yandex OK')
    } catch (e) {
      setMsg(errMsg(e, 'Yandex test failed'))
    } finally {
      setBusy(false)
    }
  }

  const connectGsc = async () => {
    setBusy(true)
    setMsg('')
    try {
      if (settings.gsc_property_url) {
        await apiFetch('/admin/seo/settings', {
          method: 'PUT',
          body: JSON.stringify({ gsc_property_url: settings.gsc_property_url }),
        })
      }
      const data = await apiFetch('/admin/seo/gsc/oauth/start')
      const url = data?.authorize_url
      if (!url) throw new Error('No authorize URL returned')
      window.location.href = url
    } catch (e) {
      setMsg(errMsg(e, 'Could not start Google Search Console OAuth'))
      setBusy(false)
    }
  }

  const disconnectGsc = async () => {
    setBusy(true)
    try {
      await apiFetch('/admin/seo/gsc/disconnect', { method: 'POST' })
      await loadSettings()
      await loadOverview().catch(() => {})
      showToast('Google Search Console disconnected')
    } catch (e) {
      setMsg(errMsg(e, 'Could not disconnect GSC'))
    } finally {
      setBusy(false)
    }
  }

  const refreshGsc = async () => {
    setBusy(true)
    try {
      const data = await apiFetch('/admin/seo/gsc/refresh', { method: 'POST' })
      await loadSettings()
      await loadOverview().catch(() => {})
      showToast(data?.note || 'Search Console ranking refreshed')
    } catch (e) {
      setMsg(errMsg(e, 'Could not refresh GSC ranking'))
    } finally {
      setBusy(false)
    }
  }

  const connectPsi = async () => {
    if (!psiKey.trim()) {
      setMsg('Enter a PageSpeed Insights API key')
      return
    }
    setBusy(true)
    try {
      await apiFetch('/admin/seo/settings/connect-psi', {
        method: 'POST',
        body: JSON.stringify({ api_key: psiKey.trim() }),
      })
      setPsiKey('')
      await loadSettings()
      showToast('PageSpeed Insights connected')
    } catch (e) {
      setMsg(errMsg(e, 'Could not connect PSI'))
    } finally {
      setBusy(false)
    }
  }

  const connectMoz = async () => {
    if (!mozAccessId.trim() || !mozSecretKey.trim()) {
      setMsg('Enter Moz Access ID and Secret Key')
      return
    }
    setBusy(true)
    try {
      await apiFetch('/admin/seo/settings/connect-moz', {
        method: 'POST',
        body: JSON.stringify({
          access_id: mozAccessId.trim(),
          secret_key: mozSecretKey.trim(),
        }),
      })
      setMozAccessId('')
      setMozSecretKey('')
      await loadSettings()
      showToast('Moz connected')
    } catch (e) {
      setMsg(errMsg(e, 'Could not connect Moz'))
    } finally {
      setBusy(false)
    }
  }

  const copyText = async (text) => {
    try {
      await navigator.clipboard.writeText(text)
      showToast('Copied')
    } catch {
      showToast('Copy failed')
    }
  }

  const setSetting = (key, value) => setSettings((s) => ({ ...s, [key]: value }))

  const ranking = overview?.ranking
  const byKind = overview?.by_kind || {}
  const totals = CONTENT_KINDS.reduce(
    (acc, k) => {
      const c = byKind[k] || {}
      acc.total += c.total || 0
      acc.indexed += c.indexed || 0
      acc.pending += c.pending || 0
      acc.excluded += c.excluded || 0
      return acc
    },
    { total: 0, indexed: 0, pending: 0, excluded: 0 },
  )

  const titleLen = (draft.meta_title || '').length
  const descLen = (draft.meta_description || '').length
  const serpTitle = draft.meta_title || draft.title || 'Untitled'
  const serpDesc = draft.meta_description || 'No meta description set — Google may generate one automatically.'
  const serpUrl = `voxbulk.com${PATH_PREFIX[tab] || '/'}${draft.slug || ''}`
  const socialTitle = draft.social_title || draft.meta_title || draft.title || 'Untitled'
  const socialDesc = draft.social_description || draft.meta_description || 'No description set.'
  const socialImg = draft.social_image_url || ''

  const broken = health?.broken_links || []
  const structured = health?.structured_data || {}
  const structuredEntries = Object.entries(structured)
  const structuredOk = structuredEntries.filter(([, v]) => v && v.ok).length
  const structuredBad = structuredEntries.length - structuredOk

  const conn = settings.connections || {}
  const indexKey = sitemap?.indexnow_key || settings.indexnow_key || ''

  const renderKpi = (key, label, unit, current, previous, connected, info, source, higherIsBetter) => {
    const showDash = !connected || current == null
    let changeCls = 'flat'
    let changeText = connected ? 'No change' : 'Connect in Site Settings'
    if (!showDash && previous != null) {
      const delta = Number(current) - Number(previous)
      const improved = higherIsBetter ? delta > 0 : delta < 0
      changeCls = delta === 0 ? 'flat' : improved ? 'good' : 'bad'
      changeText =
        delta === 0
          ? 'No change'
          : `${Math.abs(delta).toFixed(key === 'ranking' ? 1 : 0)}${key === 'ranking' ? ' positions' : ' points'} vs previous`
    }
    return (
      <div className="sc-kpi-card" key={key}>
        <div className="sc-kpi-head">
          <span className="sc-kpi-label">{label}</span>
          <button
            type="button"
            className="sc-info-icon"
            onClick={(e) => {
              e.stopPropagation()
              setInfoOpen(infoOpen === key ? null : key)
            }}
          >
            i
          </button>
        </div>
        <div className="sc-kpi-value">
          {showDash ? '—' : current}
          {!showDash ? <span className="unit">{unit}</span> : null}
        </div>
        <div className={`sc-kpi-change ${changeCls}`}>{changeText}</div>
        <div className={`sc-info-pop ${infoOpen === key ? 'open' : ''}`}>
          {info}
          <span className="src">{source}</span>
        </div>
      </div>
    )
  }

  const renderContentList = () => {
    const meta = KIND_META[tab]
    if (editing) {
      return (
        <div className="sc-editor">
          <h2>Edit SEO — {draft.title || 'Untitled'}</h2>
          <div className="sc-editor-sub">
            {meta.label} · <span className="sc-schema-badge">{meta.schema} schema</span>
          </div>

          <div className="sc-editor-grid" style={{ gridTemplateColumns: '1fr 1fr 1fr', marginBottom: 4 }}>
            <div className="sc-field" style={{ marginBottom: 8 }}>
              <label>Author</label>
              <input
                type="text"
                value={draft.author}
                onChange={(e) => setDraft((d) => ({ ...d, author: e.target.value }))}
                placeholder="e.g. Sarah Chen"
              />
            </div>
            <div className="sc-field" style={{ marginBottom: 8 }}>
              <label>Published date</label>
              <input
                type="text"
                value={draft.published_at}
                onChange={(e) => setDraft((d) => ({ ...d, published_at: e.target.value }))}
                placeholder="YYYY-MM-DD"
              />
            </div>
            <div className="sc-field" style={{ marginBottom: 8 }}>
              <label>Last updated</label>
              <input type="text" value={draft.last_updated || 'Auto on save'} readOnly />
            </div>
          </div>
          <div className="sc-help" style={{ margin: '-6px 0 18px' }}>
            Author and freshness signals matter for blog and news. Last updated is set automatically on save.
          </div>

          <div className="sc-editor-grid">
            <div>
              <div className="sc-field">
                <label>Focus keyword</label>
                <input
                  type="text"
                  value={draft.focus_keyword}
                  onChange={(e) => setDraft((d) => ({ ...d, focus_keyword: e.target.value }))}
                  placeholder="Main term to rank for"
                />
              </div>
              <div className="sc-field">
                <label>Related keywords / tags</label>
                <input
                  type="text"
                  value={draft.tags}
                  onChange={(e) => setDraft((d) => ({ ...d, tags: e.target.value }))}
                  placeholder="Comma-separated"
                />
              </div>
              <div className="sc-field">
                <label>URL slug</label>
                <div className="sc-slug-wrap">
                  <span>voxbulk.com{PATH_PREFIX[tab]}</span>
                  <input
                    type="text"
                    value={draft.slug}
                    onChange={(e) => setDraft((d) => ({ ...d, slug: e.target.value }))}
                  />
                </div>
                <div className="sc-help">Changing this creates a 301 redirect from the old URL.</div>
              </div>
              <div className="sc-field">
                <label>
                  Meta title <span className={`counter ${titleLen > 60 ? 'over' : ''}`}>{titleLen} / 60</span>
                </label>
                <input
                  type="text"
                  value={draft.meta_title}
                  onChange={(e) => setDraft((d) => ({ ...d, meta_title: e.target.value }))}
                  placeholder={draft.title}
                />
              </div>
              <div className="sc-field">
                <label>
                  Meta description <span className={`counter ${descLen > 160 ? 'over' : ''}`}>{descLen} / 160</span>
                </label>
                <textarea
                  value={draft.meta_description}
                  onChange={(e) => setDraft((d) => ({ ...d, meta_description: e.target.value }))}
                  placeholder="Short summary shown under the title in search results"
                />
              </div>
              <div className="sc-field">
                <label>Canonical URL <span style={{ fontWeight: 500 }}>(optional)</span></label>
                <input
                  type="url"
                  value={draft.canonical_url}
                  onChange={(e) => setDraft((d) => ({ ...d, canonical_url: e.target.value }))}
                  placeholder="Leave blank to use the default URL"
                />
              </div>
              <div className="sc-field">
                <label>Robots directive</label>
                <select
                  value={draft.robots}
                  onChange={(e) => setDraft((d) => ({ ...d, robots: e.target.value }))}
                >
                  <option value="index">Index & follow (default)</option>
                  <option value="noindex">Noindex (hide from Google)</option>
                  <option value="nofollow">Index, don&apos;t follow links</option>
                </select>
              </div>
            </div>
            <div className="sc-serp-card">
              <h3>Google preview</h3>
              <div className="sc-serp-preview">
                <div className="sc-serp-url">
                  <span className="sc-favicon" />
                  <span>{serpUrl}</span>
                </div>
                <div className="sc-serp-title">{serpTitle}</div>
                <div className="sc-serp-desc">{serpDesc}</div>
              </div>
              <div className="sc-serp-badge">
                {draft.robots === 'noindex'
                  ? 'This page will be hidden from Google search results'
                  : 'Eligible to appear in Google search results'}
              </div>
            </div>
          </div>

          <div className="sc-editor-grid" style={{ marginTop: 6, borderTop: '1px solid var(--border)', paddingTop: 22 }}>
            <div>
              <h3 style={{ margin: '0 0 3px', fontSize: 14.5, fontWeight: 650 }}>Social sharing</h3>
              <div className="sc-help" style={{ marginBottom: 14 }}>
                Controls how this page looks when shared on Facebook, LinkedIn, WhatsApp, and X.
              </div>
              <div className="sc-field">
                <label>Social title</label>
                <input
                  type="text"
                  value={draft.social_title}
                  onChange={(e) => setDraft((d) => ({ ...d, social_title: e.target.value }))}
                  placeholder={draft.meta_title || draft.title}
                />
              </div>
              <div className="sc-field">
                <label>Social description</label>
                <textarea
                  value={draft.social_description}
                  onChange={(e) => setDraft((d) => ({ ...d, social_description: e.target.value }))}
                  placeholder={draft.meta_description}
                />
              </div>
              <div className="sc-field">
                <label>Social image</label>
                <div className="sc-image-row">
                  <input
                    type="url"
                    value={draft.social_image_url}
                    onChange={(e) => setDraft((d) => ({ ...d, social_image_url: e.target.value }))}
                    placeholder="1200×630px works best"
                    style={{ flex: 1 }}
                  />
                  <button
                    type="button"
                    className="sc-btn sc-btn-ghost sc-btn-sm"
                    disabled={uploading}
                    onClick={() => fileRef.current?.click()}
                  >
                    {uploading ? 'Uploading…' : 'Upload'}
                  </button>
                  <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={onUploadSocial} />
                </div>
              </div>
            </div>
            <div className="sc-serp-card">
              <h3>Facebook · LinkedIn · WhatsApp · X preview</h3>
              <div className="sc-serp-preview" style={{ padding: 0, overflow: 'hidden' }}>
                <div
                  style={{
                    width: '100%',
                    height: 150,
                    background: 'var(--surface-2)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--muted)',
                    fontSize: 12,
                  }}
                >
                  {socialImg ? (
                    <img src={socialImg} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  ) : (
                    'No image set'
                  )}
                </div>
                <div style={{ padding: '12px 14px', borderTop: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 11, textTransform: 'uppercase', color: 'var(--muted)', letterSpacing: '.03em' }}>
                    voxbulk.com
                  </div>
                  <div style={{ fontSize: 14.5, fontWeight: 650, marginTop: 3 }}>{socialTitle}</div>
                  <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 3, lineHeight: 1.4 }}>{socialDesc}</div>
                </div>
              </div>
            </div>
          </div>

          <div className="sc-editor-actions">
            <button type="button" className="sc-btn sc-btn-ghost" onClick={closeEditor}>
              Cancel
            </button>
            <div className="right">
              <button type="button" className="sc-btn sc-btn-ghost" onClick={() => setPreviewOpen(true)}>
                Preview
              </button>
              <button
                type="button"
                className="sc-btn sc-btn-ghost"
                onClick={() => requestIndexing(editing, { closeAfter: false })}
              >
                Request indexing
              </button>
              <button type="button" className="sc-btn sc-btn-primary" disabled={busy} onClick={saveEditor}>
                {busy ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )
    }

    return (
      <div>
        <div className="sc-toolbar">
          <div className="sc-filters">
            {['all', 'indexed', 'pending', 'excluded'].map((f) => (
              <button
                key={f}
                type="button"
                className={`sc-chip ${filter === f ? 'active' : ''}`}
                onClick={() => setFilter(f)}
              >
                {f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
          <span className="sc-row-meta">
            {loading ? 'Loading…' : `${filtered.length} ${filtered.length === 1 ? 'item' : 'items'}`}
          </span>
        </div>
        <div className="sc-card">
          {!loading && filtered.length === 0 ? (
            <div className="sc-empty">
              <strong>Nothing matches this filter</strong>
              Try a different status filter above.
            </div>
          ) : (
            <table className="sc-table">
              <thead>
                <tr>
                  <th style={{ width: '40%' }}>{meta.label}</th>
                  <th>URL</th>
                  <th>Status</th>
                  <th>Last request</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => {
                  const excluded = (item.index_status || '') === 'excluded' || robotsToUi(item.robots) === 'noindex'
                  return (
                    <tr key={item.id}>
                      <td>
                        <div className="sc-row-title">{item.title || 'Untitled'}</div>
                        <div className="sc-row-meta">
                          {robotsToUi(item.robots) === 'noindex' ? 'noindex' : 'index, follow'}
                          {item.author ? ` · ${item.author}` : ''}
                        </div>
                      </td>
                      <td>
                        <div className="sc-row-meta">
                          {PATH_PREFIX[tab]}
                          {item.slug || '—'}
                        </div>
                      </td>
                      <td>
                        <span className={`sc-status ${item.index_status || 'pending'}`}>
                          <span className="dot" />
                          {statusLabel(item.index_status)}
                        </span>
                      </td>
                      <td>
                        <span className="sc-row-meta">{fmtDate(item.index_requested_at)}</span>
                      </td>
                      <td>
                        <div className="sc-actions">
                          <button type="button" className="sc-icon-btn" title="Edit SEO" onClick={() => openEditor(item)}>
                            <IconEdit />
                          </button>
                          <button
                            type="button"
                            className="sc-icon-btn"
                            title={excluded ? 'Allow indexing' : 'Exclude from index'}
                            onClick={() => toggleIndex(item)}
                          >
                            {excluded ? <IconEye /> : <IconEyeOff />}
                          </button>
                          <button
                            type="button"
                            className="sc-icon-btn"
                            title="Request indexing"
                            onClick={() => requestIndexing(item)}
                          >
                            <IconSend />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="sc-page">
      <style>{css}</style>
      <div className="sc-header">
        <h1>SEO & Indexing</h1>
        <p>Manage search visibility across your blog, news, and FAQ content</p>
      </div>

      <div className="sc-tabs">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`sc-tab ${tab === id ? 'active' : ''}`}
            onClick={() => switchTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {msg ? (
        <div className={`sc-msg ${/fail|could not|required|error|invalid/i.test(msg) ? 'error' : ''}`}>{msg}</div>
      ) : null}

      {tab === 'overview' ? (
        <div>
          <div className="sc-kpi-grid">
            {renderKpi(
              'ranking',
              'Average Google ranking',
              'avg position',
              ranking?.current,
              ranking?.previous,
              ranking?.connected,
              'Lower is better. Average position of queries where your site appears in Google Search.',
              'Source: Google Search Console (connect in APIs tab)',
              false,
            )}
          </div>

          <div className="sc-stat-grid">
            <div className="sc-stat-card">
              <div className="label">Total pages</div>
              <div className="value">{loading && !overview ? '—' : totals.total}</div>
              <div className="sub">Blog, News & FAQ combined</div>
            </div>
            <div className="sc-stat-card good">
              <div className="label">Indexed</div>
              <div className="value">{totals.indexed}</div>
              <div className="sub">Visible in Google search</div>
            </div>
            <div className="sc-stat-card warn">
              <div className="label">Pending</div>
              <div className="value">{totals.pending}</div>
              <div className="sub">Awaiting next crawl</div>
            </div>
            <div className="sc-stat-card danger">
              <div className="label">Excluded</div>
              <div className="value">{totals.excluded}</div>
              <div className="sub">Marked noindex</div>
            </div>
          </div>

          <div className="sc-breakdown">
            <h3>Indexing status by content type</h3>
            {CONTENT_KINDS.map((kind) => {
              const c = byKind[kind] || { indexed: 0, pending: 0, excluded: 0, total: 0 }
              const total = c.total || 1
              return (
                <div className="sc-breakdown-row" key={kind}>
                  <div className="sc-type-label">{KIND_META[kind].short}</div>
                  <div className="sc-bar">
                    <span style={{ width: `${((c.indexed || 0) / total) * 100}%`, background: 'var(--good)' }} />
                    <span style={{ width: `${((c.pending || 0) / total) * 100}%`, background: 'var(--warn)' }} />
                    <span style={{ width: `${((c.excluded || 0) / total) * 100}%`, background: 'var(--danger)' }} />
                  </div>
                  <div className="sc-totals">
                    {c.indexed || 0} indexed · {c.pending || 0} pending · {c.excluded || 0} excluded
                  </div>
                </div>
              )
            })}
          </div>

          <div className="sc-settings-card">
            <h3>Google Search Console</h3>
            <div className="sc-card-sub">Last sitemap submission and crawl summary</div>
            <div className="sc-settings-row">
              <div>
                <div className="t">Sitemap last submitted</div>
                <div className="d">{fmtDate(overview?.sitemap_last_submitted_at) === '—' ? 'Not submitted yet' : fmtDate(overview?.sitemap_last_submitted_at)}</div>
              </div>
              <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" onClick={() => switchTab('sitemap')}>
                Go to Sitemap
              </button>
            </div>
            <div className="sc-settings-row">
              <div>
                <div className="t">Pages awaiting indexing</div>
                <div className="d">Request indexing individually from the Blog, News, or FAQ tab</div>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {CONTENT_KINDS.includes(tab) ? renderContentList() : null}

      {tab === 'tech' ? (
        <div>
          <div className="sc-kpi-grid" style={{ gridTemplateColumns: '1fr' }}>
            <div className="sc-kpi-card" style={{ maxWidth: 340 }}>
              <div className="sc-kpi-head">
                <span className="sc-kpi-label">Site health score</span>
                <button
                  type="button"
                  className="sc-info-icon"
                  onClick={(e) => {
                    e.stopPropagation()
                    setInfoOpen(infoOpen === 'health' ? null : 'health')
                  }}
                >
                  i
                </button>
              </div>
              <div className="sc-kpi-value">
                {health?.site_health_score != null ? health.site_health_score : '—'}{' '}
                <span className="unit">/ 100</span>
              </div>
              <div className="sc-kpi-change flat">
                {health?.checked_at ? `Last checked ${fmtDate(health.checked_at)}` : 'Run a check to score'}
              </div>
              <div className={`sc-info-pop ${infoOpen === 'health' ? 'open' : ''}`}>
                Blended score across page speed, broken links, and structured data.
                <span className="src">Recalculated when a check runs</span>
              </div>
            </div>
          </div>

          <div className="sc-settings-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <h3>Page speed & Core Web Vitals</h3>
                <div className="sc-card-sub">Google&apos;s real-world speed thresholds — requires PageSpeed API key</div>
              </div>
              <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" disabled={busy} onClick={runPsi}>
                Recheck
              </button>
            </div>
            <div className="sc-settings-row">
              <div>
                <div className="t">Overall assessment</div>
                <div className="d">{health?.psi_score != null ? `PSI score ${health.psi_score}` : 'Not checked yet'}</div>
              </div>
              <span className={`sc-status ${health?.psi_score >= 90 ? 'good' : health?.psi_score >= 50 ? 'warn' : health?.psi_score != null ? 'bad' : 'pending'}`}>
                <span className="dot" />
                {health?.psi_score != null ? (health.psi_score >= 90 ? 'Good' : health.psi_score >= 50 ? 'Needs work' : 'Poor') : '—'}
              </span>
            </div>
            {[
              ['LCP', health?.lcp_ms != null ? `${health.lcp_ms} ms` : '—'],
              ['INP / TBT', health?.inp_ms != null ? `${health.inp_ms} ms` : '—'],
              ['CLS', health?.cls != null ? String(health.cls) : '—'],
            ].map(([name, val]) => (
              <div className="sc-metric-row" key={name}>
                <div>
                  <div className="sc-metric-name">{name}</div>
                  <div className="sc-metric-value">{val}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="sc-settings-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3>Mobile-friendliness</h3>
                <div className="sc-card-sub">{health?.mobile_note || 'Run PageSpeed to refresh'}</div>
              </div>
              <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" disabled={busy} onClick={runPsi}>
                Recheck
              </button>
            </div>
          </div>

          <div className="sc-settings-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3>HTTPS / SSL certificate</h3>
                <div className="sc-card-sub">voxbulk.com is served over HTTPS</div>
              </div>
              <span className="sc-status good">
                <span className="dot" />
                Secure
              </span>
            </div>
          </div>

          <div className="sc-settings-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <h3>Broken links (404s)</h3>
                <div className="sc-card-sub">Links pointing to pages that no longer exist</div>
              </div>
              <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" disabled={busy} onClick={scanBroken}>
                Rescan site
              </button>
            </div>
            <div className="sc-card" style={{ marginTop: 6, boxShadow: 'none' }}>
              {broken.length === 0 ? (
                <div className="sc-empty">
                  <strong>No broken links found</strong>
                  Nice — your last scan came back clean.
                </div>
              ) : (
                <table className="sc-table">
                  <thead>
                    <tr>
                      <th>Broken URL</th>
                      <th>Found on</th>
                      <th>Status</th>
                      <th style={{ textAlign: 'right' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {broken.map((b) => (
                      <tr key={b.url}>
                        <td>
                          <div className="sc-row-meta">{b.url}</div>
                        </td>
                        <td>
                          <div className="sc-row-meta">{b.source || '—'}</div>
                        </td>
                        <td>{b.status}</td>
                        <td style={{ textAlign: 'right' }}>
                          <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" onClick={() => markFixed(b.url)}>
                            Mark fixed
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          <div className="sc-settings-card">
            <h3>Structured data</h3>
            <div className="sc-card-sub">Schema.org markup across Blog, News, and FAQ</div>
            <div className="sc-settings-row">
              <div className="t">
                {structuredOk} valid, {structuredBad} with issues
              </div>
            </div>
            {structuredEntries.map(([type, info]) => (
              <div className="sc-settings-row" key={type}>
                <div>
                  <div className="t">{type}</div>
                  <div className="d">{info?.count != null ? `${info.count} page(s)` : ''}</div>
                </div>
                <span className={`sc-status ${info?.ok ? 'good' : 'warn'}`}>
                  <span className="dot" />
                  {info?.ok ? 'OK' : 'Check'}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {tab === 'redirects' ? (
        <div>
          <div className="sc-settings-card">
            <h3>Add a redirect</h3>
            <div className="sc-card-sub">Send visitors and search engines from an old URL to a new one</div>
            <div className="sc-kv-row">
              <label>From (old path)</label>
              <div>
                <input type="text" value={rdFrom} onChange={(e) => setRdFrom(e.target.value)} placeholder="/blog/old-post-name" />
              </div>
            </div>
            <div className="sc-kv-row">
              <label>To (new path or URL)</label>
              <div>
                <input type="text" value={rdTo} onChange={(e) => setRdTo(e.target.value)} placeholder="/blog/new-post-name" />
              </div>
            </div>
            <div className="sc-kv-row">
              <label>Redirect type</label>
              <div>
                <select value={rdType} onChange={(e) => setRdType(Number(e.target.value))}>
                  <option value={301}>301 — Permanent</option>
                  <option value={302}>302 — Temporary</option>
                </select>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button type="button" className="sc-btn sc-btn-primary sc-btn-sm" disabled={busy} onClick={addRedirect}>
                Add redirect
              </button>
            </div>
          </div>
          <div className="sc-toolbar">
            <span className="sc-row-meta">
              {loading ? 'Loading…' : `${redirects.length} redirect${redirects.length === 1 ? '' : 's'}`}
            </span>
          </div>
          <div className="sc-card">
            {redirects.length === 0 && !loading ? (
              <div className="sc-empty">
                <strong>No redirects yet</strong>
                They&apos;re also created automatically when you change a page&apos;s URL slug.
              </div>
            ) : (
              <table className="sc-table">
                <thead>
                  <tr>
                    <th>From</th>
                    <th>To</th>
                    <th>Type</th>
                    <th>Created</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {redirects.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <div className="sc-row-meta">{r.from_path}</div>
                      </td>
                      <td>
                        <div className="sc-row-meta">{r.to_path}</div>
                      </td>
                      <td>{r.status_code}</td>
                      <td>
                        <span className="sc-row-meta">{fmtDate(r.created_at)}</span>
                      </td>
                      <td>
                        <div className="sc-actions">
                          <button type="button" className="sc-icon-btn" title="Delete" onClick={() => deleteRedirect(r.id)}>
                            <IconTrash />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      ) : null}

      {tab === 'sitemap' ? (
        <div>
          <div className="sc-settings-card">
            <h3>XML Sitemap</h3>
            <div className="sc-card-sub">Automatically generated from published blog, news, and FAQ pages</div>
            <div className="sc-settings-row">
              <div>
                <div className="t">{sitemap?.count != null ? `${sitemap.count} URLs included` : '— URLs included'}</div>
                <div className="d">Last generated {fmtDate(sitemap?.last_generated_at)}</div>
              </div>
              <button type="button" className="sc-btn sc-btn-primary sc-btn-sm" disabled={busy} onClick={regenerateSitemap}>
                Regenerate now
              </button>
            </div>
            <div className="sc-settings-row">
              <div className="t">Sitemap URL</div>
            </div>
            <div className="sc-copy-row">
              <input type="text" readOnly value={sitemap?.sitemap_url || `${SITE}/sitemap.xml`} />
              <button
                type="button"
                className="sc-btn sc-btn-ghost sc-btn-sm"
                onClick={() => copyText(sitemap?.sitemap_url || `${SITE}/sitemap.xml`)}
              >
                Copy
              </button>
            </div>
          </div>

          <div className="sc-settings-card">
            <h3>
              Google News sitemap{' '}
              <span className={`sc-status ${settings.google_news_enabled ? 'good' : 'pending'}`} style={{ marginLeft: 6 }}>
                <span className="dot" />
                {settings.google_news_enabled ? 'Enabled' : 'Disabled'}
              </span>
            </h3>
            <div className="sc-card-sub">
              News articles published in the last 48 hours — configure publication in Site Settings
            </div>
            <div className="sc-settings-row">
              <div>
                <div className="t">{sitemap?.news_eligible_count || 0} article(s) currently eligible</div>
                <div className="d">Configure publication name and language in Site Settings → Google News</div>
              </div>
              <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" onClick={() => switchTab('settings')}>
                Go to settings
              </button>
            </div>
            <div className="sc-copy-row">
              <input type="text" readOnly value={sitemap?.news_sitemap_url || `${SITE}/news-sitemap.xml`} />
              <button
                type="button"
                className="sc-btn sc-btn-ghost sc-btn-sm"
                onClick={() => copyText(sitemap?.news_sitemap_url || `${SITE}/news-sitemap.xml`)}
              >
                Copy
              </button>
            </div>
          </div>

          <div className="sc-settings-card">
            <h3>What “Submit” means</h3>
            <div className="sc-card-sub">
              Submit sends your <strong>sitemap URL list</strong> to search engines — not keywords.
              The sitemap already includes homepage, product pages (/surveys, /feedback, /recruitment, /pricing, …),
              Blog posts, News, and FAQ pages that are set to index.
              Keyword Ideas only save phrases onto your pages; they are never “submitted” as keywords.
            </div>
          </div>

          <div className="sc-settings-card">
            <h3>Search engines — submit sitemap</h3>
            <div className="sc-card-sub">
              1) Rebuild sitemap list → 2) IndexNow ping (Bing/Yandex, if key exists) → 3) Tell Google / Bing / Yandex to fetch{' '}
              <code>https://voxbulk.com/sitemap.xml</code>. Google needs a fresh Connect after write-scope was enabled
              (old connection was read-only → 403).
            </div>
            <div className="sc-settings-row">
              <div>
                <div className="t">Last multi-engine run</div>
                <div className="d">
                  {engines?.engines_last_run_at ? fmtDate(engines.engines_last_run_at) : 'Not run yet'}
                </div>
              </div>
              <button type="button" className="sc-btn sc-btn-primary sc-btn-sm" disabled={busy} onClick={submitAllEngines}>
                Submit to all connected engines
              </button>
            </div>
            <div className="sc-settings-row">
              <div>
                <div className="t">
                  Google{' '}
                  <span className={`sc-status ${engines?.google?.connected ? 'good' : 'pending'}`} style={{ marginLeft: 6 }}>
                    <span className="dot" />
                    {engines?.google?.connected ? 'Connected' : 'Not connected'}
                  </span>
                </div>
                <div className="d">
                  Last: {engines?.google?.last_submitted_at ? fmtDate(engines.google.last_submitted_at) : '—'}
                  {engines?.google?.last_error ? ` · ${engines.google.last_error}` : ''}
                  {!engines?.google?.last_error && !engines?.google?.last_submitted_at
                    ? ''
                    : ''}
                  {(engines?.google?.last_error || '').includes('insufficient') ||
                  (engines?.google?.last_error || '').includes('403')
                    ? ' → Fix: APIs tab → Google → Disconnect → Connect again (approve write access).'
                    : ''}
                </div>
              </div>
              <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" disabled={busy} onClick={submitGoogle}>
                Submit to Google only
              </button>
            </div>
            <div className="sc-settings-row">
              <div>
                <div className="t">
                  Bing{' '}
                  <span className={`sc-status ${engines?.bing?.connected ? 'good' : 'pending'}`} style={{ marginLeft: 6 }}>
                    <span className="dot" />
                    {engines?.bing?.connected ? 'Connected' : 'Not connected'}
                  </span>
                </div>
                <div className="d">
                  Last: {engines?.bing?.last_submitted_at ? fmtDate(engines.bing.last_submitted_at) : '—'}
                  {engines?.bing?.last_error ? ` · ${engines.bing.last_error}` : ''}
                </div>
              </div>
              <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" onClick={() => switchTab('apis')}>
                Connect in APIs
              </button>
            </div>
            <div className="sc-settings-row">
              <div>
                <div className="t">
                  Yandex{' '}
                  <span className={`sc-status ${engines?.yandex?.connected ? 'good' : 'pending'}`} style={{ marginLeft: 6 }}>
                    <span className="dot" />
                    {engines?.yandex?.connected ? 'Connected' : 'Not connected'}
                  </span>
                </div>
                <div className="d">
                  Last: {engines?.yandex?.last_submitted_at ? fmtDate(engines.yandex.last_submitted_at) : '—'}
                  {engines?.yandex?.last_error ? ` · ${engines.yandex.last_error}` : ''}
                </div>
              </div>
              <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" onClick={() => switchTab('apis')}>
                Connect in APIs
              </button>
            </div>
            <div className="sc-settings-row">
              <div>
                <div className="t">Weekly auto-submit (Mondays 06:15 UTC)</div>
                <div className="d">Celery beat runs when enabled below — toggle in Site Settings</div>
              </div>
              <span className={`sc-status ${settings.auto_submit_weekly ? 'good' : 'pending'}`}>
                <span className="dot" />
                {settings.auto_submit_weekly ? 'On' : 'Off'}
              </span>
            </div>
          </div>

          <div className="sc-settings-card">
            <h3>
              IndexNow protocol{' '}
              <span className={`sc-status ${indexKey ? 'good' : 'pending'}`} style={{ marginLeft: 6 }}>
                <span className="dot" />
                {indexKey ? 'Key ready' : 'Not set up'}
              </span>
            </h3>
            <div className="sc-card-sub">
              Instantly notifies Bing, Yandex, and other engines when content changes. Google does not support IndexNow.
              When auto-on-publish is on, saving Blog/News/FAQ SEO also pings IndexNow for that URL.
            </div>
            <div className="sc-settings-row">
              <div>
                <div className="t">API key</div>
                <div className="d">
                  {indexKey ? `${indexKey.slice(0, 12)}… (hosted at /${indexKey}.txt)` : 'Not generated yet'}
                </div>
              </div>
              <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" disabled={busy} onClick={generateIndexNow}>
                Generate key
              </button>
            </div>
            <div className="sc-settings-row">
              <div>
                <div className="t">Last pinged</div>
                <div className="d">
                  {fmtDate(sitemap?.indexnow_last_pinged_at || settings.indexnow_last_pinged_at) === '—'
                    ? 'Never'
                    : fmtDate(sitemap?.indexnow_last_pinged_at || settings.indexnow_last_pinged_at)}
                </div>
              </div>
              <button type="button" className="sc-btn sc-btn-primary sc-btn-sm" disabled={busy} onClick={notifyIndexNow}>
                Notify search engines now
              </button>
            </div>
          </div>

          <div className="sc-settings-card">
            <h3>robots.txt</h3>
            <div className="sc-card-sub">Controls which crawlers can access your site. Changes apply site-wide.</div>
            <textarea className="sc-mono" value={robotsTxt} onChange={(e) => setRobotsTxt(e.target.value)} />
            <div className="sc-editor-actions" style={{ borderTop: 'none', paddingTop: 14 }}>
              <span className="sc-help" style={{ fontSize: 12 }}>
                Editing this affects all search engine crawlers immediately.
              </span>
              <button type="button" className="sc-btn sc-btn-primary sc-btn-sm" disabled={busy} onClick={saveRobots}>
                Save robots.txt
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {tab === 'apis' ? (
        <div>
          <div className="sc-settings-card">
            <h3>Search & SEO APIs</h3>
            <div className="sc-card-sub">
              Each service has its own card. Save credentials, Connect (Google OAuth), then Test. Sitemap submit stays on the Sitemap tab — not here.
            </div>
          </div>

          <div className="sc-settings-card">
            <h3>
              Google Search Console{' '}
              <span className={`sc-status ${conn.gsc ? 'good' : 'pending'}`} style={{ marginLeft: 6 }}>
                <span className="dot" />
                {conn.gsc ? 'Connected' : 'Not connected'}
              </span>
            </h3>
            <div className="sc-card-sub">
              {settings.gsc_oauth_configured
                ? 'If sitemap submit returns 403 insufficient scopes: Disconnect, then Connect again and approve access (write scope is required to submit sitemaps). Ranking refresh also uses this connection.'
                : 'First save Client ID/secret under Integrations → Google Search Console, then return here.'}
            </div>
            <div className="sc-kv-row">
              <label>Property URL</label>
              <div>
                <input
                  type="text"
                  value={settings.gsc_property_url}
                  onChange={(e) => setSetting('gsc_property_url', e.target.value)}
                  placeholder="sc-domain:voxbulk.com"
                />
              </div>
            </div>
            <div className="sc-editor-actions" style={{ borderTop: 'none', paddingTop: 8, gap: 8, flexWrap: 'wrap' }}>
              <button type="button" className="sc-btn sc-btn-primary sc-btn-sm" disabled={busy} onClick={() => saveSettings()}>
                Save
              </button>
              {!settings.gsc_oauth_configured ? (
                <a className="sc-btn sc-btn-ghost sc-btn-sm" href="/integrations/google_search_console">
                  Open credentials
                </a>
              ) : null}
              {conn.gsc ? (
                <>
                  <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" disabled={busy} onClick={testGoogle}>
                    Test
                  </button>
                  <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" disabled={busy} onClick={refreshGsc}>
                    Refresh ranking
                  </button>
                  <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" disabled={busy} onClick={disconnectGsc}>
                    Disconnect
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="sc-btn sc-btn-ghost sc-btn-sm"
                  disabled={busy || !settings.gsc_oauth_configured}
                  onClick={connectGsc}
                >
                  Connect
                </button>
              )}
            </div>
          </div>

          <div className="sc-settings-card">
            <h3>
              Bing Webmaster{' '}
              <span className={`sc-status ${conn.bing || settings.bing_api_key_set ? 'good' : 'pending'}`} style={{ marginLeft: 6 }}>
                <span className="dot" />
                {conn.bing || settings.bing_api_key_set ? 'Connected' : 'Not connected'}
              </span>
            </h3>
            <div className="sc-card-sub">API key from Bing Webmaster Tools → Settings → API Access</div>
            <div className="sc-kv-row">
              <label>Site URL</label>
              <div>
                <input
                  type="text"
                  value={settings.bing_site_url || SITE}
                  onChange={(e) => setSetting('bing_site_url', e.target.value)}
                  placeholder="https://voxbulk.com"
                />
              </div>
            </div>
            <div className="sc-kv-row">
              <label>API key</label>
              <div>
                <input
                  type="password"
                  value={bingKey}
                  onChange={(e) => setBingKey(e.target.value)}
                  placeholder={settings.bing_api_key_set ? '•••••••• (saved)' : 'Paste API key'}
                />
              </div>
            </div>
            <div className="sc-editor-actions" style={{ borderTop: 'none', paddingTop: 8, gap: 8, flexWrap: 'wrap' }}>
              <button type="button" className="sc-btn sc-btn-primary sc-btn-sm" disabled={busy} onClick={() => saveSettings()}>
                Save site URL
              </button>
              <button type="button" className="sc-btn sc-btn-primary sc-btn-sm" disabled={busy || !bingKey} onClick={connectBing}>
                Save &amp; Connect
              </button>
              <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" disabled={busy || !(conn.bing || settings.bing_api_key_set)} onClick={testBing}>
                Test
              </button>
              {conn.bing || settings.bing_api_key_set ? (
                <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" disabled={busy} onClick={disconnectBing}>
                  Disconnect
                </button>
              ) : null}
            </div>
          </div>

          <div className="sc-settings-card">
            <h3>
              Yandex Webmaster{' '}
              <span className={`sc-status ${conn.yandex || settings.yandex_token_set ? 'good' : 'pending'}`} style={{ marginLeft: 6 }}>
                <span className="dot" />
                {conn.yandex || settings.yandex_token_set ? 'Connected' : 'Not connected'}
              </span>
            </h3>
            <div className="sc-card-sub">
              OAuth token from a Yandex OAuth app with Webmaster access
              {settings.yandex_host_id ? ` · host ${settings.yandex_host_id}` : ''}
            </div>
            <div className="sc-kv-row">
              <label>OAuth token</label>
              <div>
                <input
                  type="password"
                  value={yandexToken}
                  onChange={(e) => setYandexToken(e.target.value)}
                  placeholder={settings.yandex_token_set ? '•••••••• (saved)' : 'Paste OAuth token'}
                />
              </div>
            </div>
            <div className="sc-editor-actions" style={{ borderTop: 'none', paddingTop: 8, gap: 8, flexWrap: 'wrap' }}>
              <button type="button" className="sc-btn sc-btn-primary sc-btn-sm" disabled={busy || !yandexToken} onClick={connectYandex}>
                Save &amp; Connect
              </button>
              <button
                type="button"
                className="sc-btn sc-btn-ghost sc-btn-sm"
                disabled={busy || !(conn.yandex || settings.yandex_token_set)}
                onClick={testYandex}
              >
                Test
              </button>
              {conn.yandex || settings.yandex_token_set ? (
                <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" disabled={busy} onClick={disconnectYandex}>
                  Disconnect
                </button>
              ) : null}
            </div>
          </div>

          <div className="sc-settings-card">
            <h3>
              Google PageSpeed Insights{' '}
              <span className={`sc-status ${conn.psi ? 'good' : 'pending'}`} style={{ marginLeft: 6 }}>
                <span className="dot" />
                {conn.psi ? 'Connected' : 'Not connected'}
              </span>
            </h3>
            <div className="sc-card-sub">Optional. Powers Core Web Vitals on Technical Health.</div>
            <div className="sc-kv-row">
              <label>API key</label>
              <div>
                <input
                  type="text"
                  value={psiKey}
                  onChange={(e) => setPsiKey(e.target.value)}
                  placeholder={settings.psi_api_key_set ? '•••••••• (saved)' : 'AIza...'}
                />
              </div>
            </div>
            <div className="sc-editor-actions" style={{ borderTop: 'none', paddingTop: 8 }}>
              <button type="button" className="sc-btn sc-btn-primary sc-btn-sm" disabled={busy || !psiKey} onClick={connectPsi}>
                Save &amp; Connect
              </button>
            </div>
          </div>

          <div className="sc-settings-card">
            <h3>IndexNow</h3>
            <div className="sc-card-sub">Free instant notify for Bing/Yandex. Generate once on Sitemap tab, then Test notify there.</div>
            <div className="sc-settings-row">
              <div>
                <div className="t">{indexKey ? `Key ready (${indexKey.slice(0, 10)}…)` : 'Not generated'}</div>
                <div className="d">Open Sitemap &amp; Robots tab to generate / notify</div>
              </div>
              <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" onClick={() => switchTab('sitemap')}>
                Go to Sitemap
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {tab === 'keywords' ? (
        <div>
          <div className="sc-settings-card">
            <h3>Keyword ideas</h3>
            <div className="sc-card-sub">
              Click <strong>Save keyword</strong> to add a phrase to homepage or product-page keyword fields only.
              There is no “submit keywords” to Google — engines only get URLs/sitemaps.
            </div>
            <div className="sc-settings-row">
              <div>
                <div className="t">{keywords.filter((k) => k.status === 'suggested').length} suggestions</div>
                <div className="d">Save = store on your pages. No new landing pages. No engine submit.</div>
              </div>
              <button type="button" className="sc-btn sc-btn-primary sc-btn-sm" disabled={busy} onClick={refreshKeywords}>
                Find new ideas
              </button>
            </div>
          </div>
          <div className="sc-settings-card" style={{ padding: 0, overflow: 'hidden' }}>
            <table className="sc-table">
              <thead>
                <tr>
                  <th>Phrase</th>
                  <th>Target</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {keywords.length === 0 ? (
                  <tr>
                    <td colSpan={4} style={{ color: 'var(--muted)' }}>
                      No ideas yet — click Find new ideas
                    </td>
                  </tr>
                ) : (
                  keywords.map((idea) => (
                    <tr key={idea.id}>
                      <td>{idea.phrase}</td>
                      <td>
                        {idea.status === 'suggested' ? (
                          <select
                            value={idea.target || 'home'}
                            onChange={(e) =>
                              setKeywords((rows) =>
                                rows.map((r) => (r.id === idea.id ? { ...r, target: e.target.value } : r)),
                              )
                            }
                          >
                            <option value="home">Homepage</option>
                            <option value="surveys">Surveys</option>
                            <option value="feedback">Feedback</option>
                            <option value="recruitment">Recruitment</option>
                            <option value="pricing">Pricing</option>
                            <option value="contact">Contact</option>
                          </select>
                        ) : (
                          idea.target || '—'
                        )}
                      </td>
                      <td>
                        <span
                          className={`sc-status ${
                            idea.status === 'accepted' ? 'good' : idea.status === 'dismissed' ? 'pending' : 'warn'
                          }`}
                        >
                          <span className="dot" />
                          {idea.status}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                        {idea.status === 'suggested' ? (
                          <>
                            <button
                              type="button"
                              className="sc-btn sc-btn-primary sc-btn-sm"
                              disabled={busy}
                              onClick={() => acceptKeyword(idea)}
                              style={{ marginRight: 6 }}
                            >
                              Save keyword
                            </button>
                            <button
                              type="button"
                              className="sc-btn sc-btn-ghost sc-btn-sm"
                              disabled={busy}
                              onClick={() => dismissKeyword(idea)}
                            >
                              Dismiss
                            </button>
                          </>
                        ) : null}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {tab === 'settings' ? (
        <div>
          <div className="sc-settings-card">
            <h3>Homepage SEO</h3>
            <div className="sc-card-sub">Your main page isn&apos;t a blog/news/FAQ item, so it gets its own keyword settings here</div>
            <div className="sc-kv-row">
              <label>Homepage title</label>
              <div>
                <input type="text" value={settings.home_title} onChange={(e) => setSetting('home_title', e.target.value)} />
              </div>
            </div>
            <div className="sc-kv-row">
              <label>Homepage meta description</label>
              <div>
                <textarea value={settings.home_description} onChange={(e) => setSetting('home_description', e.target.value)} />
              </div>
            </div>
            <div className="sc-kv-row">
              <label>Focus keyword</label>
              <div>
                <input
                  type="text"
                  value={settings.home_focus_keyword}
                  onChange={(e) => setSetting('home_focus_keyword', e.target.value)}
                />
              </div>
            </div>
            <div className="sc-kv-row">
              <label>Related keywords / tags</label>
              <div>
                <input type="text" value={settings.home_tags} onChange={(e) => setSetting('home_tags', e.target.value)} />
              </div>
            </div>
            <div className="sc-editor-actions" style={{ borderTop: 'none', paddingTop: 12 }}>
              <button type="button" className="sc-btn sc-btn-primary sc-btn-sm" disabled={busy} onClick={() => saveSettings()}>
                Save homepage SEO
              </button>
            </div>
          </div>

          <div className="sc-settings-card">
            <h3>Product pages SEO</h3>
            <div className="sc-card-sub">
              Titles, descriptions and keywords for main marketing pages. Edit here anytime — changes apply after you save and the public site is redeployed/refreshed.
            </div>
            {MARKETING_PAGE_KEYS.map(([key, label]) => {
              const page = (settings.marketing_pages && settings.marketing_pages[key]) || emptyMarketingPage()
              const setPageField = (field, value) => {
                setSettings((s) => ({
                  ...s,
                  marketing_pages: {
                    ...(s.marketing_pages || {}),
                    [key]: { ...(s.marketing_pages?.[key] || emptyMarketingPage()), [field]: value },
                  },
                }))
              }
              return (
                <div key={key} style={{ borderTop: '1px solid var(--border)', paddingTop: 16, marginTop: 16 }}>
                  <div style={{ fontWeight: 600, marginBottom: 10 }}>{label}</div>
                  <div className="sc-kv-row">
                    <label>Title</label>
                    <div>
                      <input type="text" value={page.title || ''} onChange={(e) => setPageField('title', e.target.value)} />
                    </div>
                  </div>
                  <div className="sc-kv-row">
                    <label>Meta description</label>
                    <div>
                      <textarea
                        value={page.description || ''}
                        onChange={(e) => setPageField('description', e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="sc-kv-row">
                    <label>Keywords</label>
                    <div>
                      <input
                        type="text"
                        value={page.keywords || ''}
                        onChange={(e) => setPageField('keywords', e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="sc-kv-row">
                    <label>Social / OG description</label>
                    <div>
                      <textarea
                        value={page.og_description || ''}
                        onChange={(e) => setPageField('og_description', e.target.value)}
                      />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

            <div className="sc-editor-actions" style={{ borderTop: 'none', paddingTop: 12 }}>
              <button type="button" className="sc-btn sc-btn-primary sc-btn-sm" disabled={busy} onClick={() => saveSettings()}>
                Save product pages SEO
              </button>
            </div>

          <div className="sc-settings-card">
            <h3>Default meta</h3>
            <div className="sc-card-sub">Fallback values used when a page doesn&apos;t set its own</div>
            <div className="sc-kv-row">
              <label>Site name</label>
              <div>
                <input type="text" value={settings.site_name} onChange={(e) => setSetting('site_name', e.target.value)} />
              </div>
            </div>
            <div className="sc-kv-row">
              <label>Title template</label>
              <div>
                <input
                  type="text"
                  value={settings.title_template}
                  onChange={(e) => setSetting('title_template', e.target.value)}
                />
                <div className="sc-help">Use %title% and %sitename% as placeholders</div>
              </div>
            </div>
            <div className="sc-kv-row">
              <label>Default meta description</label>
              <div>
                <textarea
                  value={settings.default_meta_description}
                  onChange={(e) => setSetting('default_meta_description', e.target.value)}
                />
              </div>
            </div>
            <div className="sc-kv-row">
              <label>Default social image</label>
              <div className="sc-image-row">
                <input
                  type="text"
                  value={settings.default_social_image_url || ''}
                  onChange={(e) => setSetting('default_social_image_url', e.target.value)}
                  placeholder="Paste an image URL, or upload"
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  className="sc-btn sc-btn-ghost sc-btn-sm"
                  disabled={uploading}
                  onClick={() => settingsFileRef.current?.click()}
                >
                  Upload
                </button>
                <input
                  ref={settingsFileRef}
                  type="file"
                  accept="image/*"
                  style={{ display: 'none' }}
                  onChange={onUploadSettingsImage}
                />
              </div>
            </div>
          </div>

          <div className="sc-settings-card">
            <h3>Structured data</h3>
            <div className="sc-card-sub">Schema.org markup that helps Google show rich results</div>
            {[
              ['schema_organization', 'Organization schema', 'Adds your logo and social profiles to Google\'s knowledge panel'],
              ['schema_website', 'WebSite + Sitelinks search box', 'Lets Google show a search box under your site in results'],
              ['schema_breadcrumbs', 'Breadcrumbs', 'Shows the page path in search results'],
              ['schema_content', 'Article / NewsArticle / FAQPage schema', 'Applied automatically to Blog, News, and FAQ entries'],
            ].map(([key, title, desc]) => (
              <div className="sc-settings-row" key={key}>
                <div>
                  <div className="t">{title}</div>
                  <div className="d">{desc}</div>
                </div>
                <label className="sc-switch">
                  <input
                    type="checkbox"
                    checked={!!settings[key]}
                    onChange={(e) => setSetting(key, e.target.checked)}
                  />
                  <span className="sc-slider" />
                </label>
              </div>
            ))}
          </div>

          <div className="sc-settings-card">
            <h3>Search Console & Analytics</h3>
            <div className="sc-card-sub">Verification and tracking codes</div>
            <div className="sc-kv-row">
              <label>Search Console verification</label>
              <div>
                <input
                  type="text"
                  value={settings.google_site_verification}
                  onChange={(e) => setSetting('google_site_verification', e.target.value)}
                  placeholder="google-site-verification=..."
                />
              </div>
            </div>
            <div className="sc-kv-row">
              <label>Google Analytics ID</label>
              <div>
                <input
                  type="text"
                  value={settings.google_analytics_id}
                  onChange={(e) => setSetting('google_analytics_id', e.target.value)}
                  placeholder="G-XXXXXXXXXX"
                />
              </div>
            </div>
          </div>

          <div className="sc-settings-card">
            <h3>Ad pixels & retargeting</h3>
            <div className="sc-card-sub">These load site-wide to track conversions and build retargeting audiences</div>
            {[
              ['meta_pixel_id', 'Meta Pixel', 'e.g. 123456789012345'],
              ['linkedin_partner_id', 'LinkedIn Insight Tag', 'e.g. 1234567'],
              ['google_ads_id', 'Google Ads conversion ID', 'e.g. AW-123456789'],
              ['x_pixel_id', 'X (Twitter) Pixel', 'e.g. o1a2b'],
              ['tiktok_pixel_id', 'TikTok Pixel', 'e.g. CXXXXXXXXXXXXXXXXXXX'],
              ['pinterest_tag_id', 'Pinterest Tag', 'e.g. 2612345678901'],
            ].map(([key, label, ph]) => (
              <div className="sc-kv-row" key={key}>
                <label>{label}</label>
                <div>
                  <input type="text" value={settings[key] || ''} onChange={(e) => setSetting(key, e.target.value)} placeholder={ph} />
                </div>
              </div>
            ))}
          </div>

          <div className="sc-settings-card">
            <h3>Google News</h3>
            <div className="sc-card-sub">Needs its own sitemap and a registered publication</div>
            <div className="sc-settings-row">
              <div>
                <div className="t">Enable Google News sitemap</div>
                <div className="d">Articles published in the last 48 hours</div>
              </div>
              <label className="sc-switch">
                <input
                  type="checkbox"
                  checked={!!settings.google_news_enabled}
                  onChange={(e) => setSetting('google_news_enabled', e.target.checked)}
                />
                <span className="sc-slider" />
              </label>
            </div>
            <div className="sc-kv-row">
              <label>Publication name</label>
              <div>
                <input
                  type="text"
                  value={settings.google_news_publication}
                  onChange={(e) => setSetting('google_news_publication', e.target.value)}
                />
              </div>
            </div>
            <div className="sc-kv-row">
              <label>Content language</label>
              <div>
                <select
                  value={settings.google_news_language || 'en'}
                  onChange={(e) => setSetting('google_news_language', e.target.value)}
                >
                  <option value="en">English</option>
                  <option value="tr">Turkish</option>
                  <option value="es">Spanish</option>
                  <option value="fr">French</option>
                  <option value="de">German</option>
                  <option value="ar">Arabic</option>
                </select>
              </div>
            </div>
          </div>

          <div className="sc-settings-card">
            <h3>Auto indexing</h3>
            <div className="sc-card-sub">
              Connect Google / Bing / Yandex under the APIs tab. Sitemap submit is on Sitemap &amp; Robots.
            </div>
            <div className="sc-settings-row">
              <div>
                <div className="t">Weekly auto-submit to connected engines</div>
                <div className="d">Mondays 06:15 UTC — requires Celery beat on VPS</div>
              </div>
              <label className="sc-switch">
                <input
                  type="checkbox"
                  checked={!!settings.auto_submit_weekly}
                  onChange={(e) => setSetting('auto_submit_weekly', e.target.checked)}
                />
                <span className="sc-slider" />
              </label>
            </div>
            <div className="sc-settings-row">
              <div>
                <div className="t">IndexNow on Blog / News / FAQ save</div>
                <div className="d">Pings Bing &amp; Yandex when you save SEO for an indexable page</div>
              </div>
              <label className="sc-switch">
                <input
                  type="checkbox"
                  checked={settings.auto_indexnow_on_publish !== false}
                  onChange={(e) => setSetting('auto_indexnow_on_publish', e.target.checked)}
                />
                <span className="sc-slider" />
              </label>
            </div>
            <div className="sc-editor-actions" style={{ borderTop: 'none', paddingTop: 12, gap: 8 }}>
              <button type="button" className="sc-btn sc-btn-primary sc-btn-sm" disabled={busy} onClick={() => saveSettings()}>
                Save auto indexing
              </button>
              <button type="button" className="sc-btn sc-btn-ghost sc-btn-sm" onClick={() => switchTab('apis')}>
                Open APIs tab
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button type="button" className="sc-btn sc-btn-primary" disabled={busy} onClick={() => saveSettings()}>
              {busy ? 'Saving…' : 'Save all settings'}
            </button>
          </div>
        </div>
      ) : null}

      {previewOpen && editing ? (
        <div
          className="sc-preview-modal"
          onClick={(e) => {
            if (e.target === e.currentTarget) setPreviewOpen(false)
          }}
        >
          <div className="sc-preview-box">
            <div className="sc-preview-head">
              <span>SEO preview</span>
              <button type="button" className="sc-icon-btn" onClick={() => setPreviewOpen(false)}>
                ×
              </button>
            </div>
            <div className="sc-preview-body">
              <div className="sc-serp-preview">
                <div className="sc-serp-url">
                  <span className="sc-favicon" />
                  <span>{serpUrl}</span>
                </div>
                <div className="sc-serp-title">{serpTitle}</div>
                <div className="sc-serp-desc">{serpDesc}</div>
              </div>
              <div style={{ marginTop: 16 }}>
                <a
                  href={draft.url || `${SITE}${PATH_PREFIX[tab]}${draft.slug}`}
                  target="_blank"
                  rel="noreferrer"
                  className="sc-btn sc-btn-primary"
                  style={{ textDecoration: 'none' }}
                >
                  Open live page
                </a>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <div className={`sc-toast ${toast ? 'show' : ''}`}>{toast}</div>
    </div>
  )
}
