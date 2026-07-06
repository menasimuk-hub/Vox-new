import React, { useCallback, useEffect, useState } from 'react'
import {
  ChevronDown,
  Globe,
  Image as ImageIcon,
  Link2,
  Pencil,
  Phone,
  Plus,
  RefreshCw,
  Reply,
  Save,
  Trash2,
  Type as TypeIcon,
  Wrench,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Label } from '@/components/ui/Label'
import { Switch } from '@/components/ui/Switch'
import { Sheet, SheetClose, SheetContent } from '@/components/ui/Sheet'
import { apiFetch } from '../../lib/api'
import { formatWaSurveyError } from '../../lib/waSurveyFeedback'
import WaPhonePreview from './WaPhonePreview'
import {
  IconBtn,
  LANGS,
  FEEDBACK_LANG_CHIPS,
  feedbackChipToLanguage,
  StatusDot,
  formatRelativeWhen,
  langChipClass,
  langCodeToChip,
  mapApprovalStatus,
  mapCategory,
} from './waTemplatesUi'

function parseComponents(raw) {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }
  return []
}

function bodyFromComponents(components) {
  const body = (components || []).find((c) => String(c?.type || '').toUpperCase() === 'BODY')
  return body?.text || ''
}

function footerFromComponents(components) {
  const footer = (components || []).find((c) => String(c?.type || '').toUpperCase() === 'FOOTER')
  return footer?.text || ''
}

function headerFromComponents(components) {
  const header = (components || []).find((c) => String(c?.type || '').toUpperCase() === 'HEADER')
  if (!header) return undefined
  const format = String(header.format || header.type || '').toUpperCase()
  if (format === 'IMAGE') return { type: 'image', text: '' }
  if (header.text) return { type: 'text', text: header.text }
  return undefined
}

function buttonsFromComponents(components) {
  const comp = (components || []).find((c) => String(c?.type || '').toUpperCase() === 'BUTTONS')
  const list = Array.isArray(comp?.buttons) ? comp.buttons : []
  return list.map((b) => {
    const kind = String(b.type || '').toUpperCase()
    if (kind === 'URL') return { type: 'url', text: b.text || '', url: b.url || '' }
    if (kind === 'PHONE_NUMBER') return { type: 'phone', text: b.text || '', phone: b.phone_number || '' }
    return { type: 'quick_reply', text: b.text || '' }
  })
}

const STOP_FOOTER = 'Reply STOP to opt out'

function buildComponents(draft) {
  const components = []
  if (draft.header?.type === 'text' && draft.header.text) {
    components.push({ type: 'HEADER', format: 'TEXT', text: draft.header.text })
  } else if (draft.header?.type === 'image') {
    components.push({ type: 'HEADER', format: 'IMAGE' })
  }
  const vars = draft.variables || []
  const body = {
    type: 'BODY',
    text: draft.body || '',
  }
  if (vars.length) body.example = { body_text: [vars] }
  components.push(body)
  // Every WhatsApp template must include the opt-out footer.
  components.push({ type: 'FOOTER', text: STOP_FOOTER })
  if ((draft.buttons || []).length) {
    const buttons = draft.buttons.map((b) => {
      if (b.type === 'url') return { type: 'URL', text: b.text, url: b.url || 'https://' }
      if (b.type === 'phone') return { type: 'PHONE_NUMBER', text: b.text, phone_number: b.phone || '+1' }
      return { type: 'QUICK_REPLY', text: b.text }
    })
    components.push({ type: 'BUTTONS', buttons })
  }
  return components
}

function isLocalDraftTemplate(tpl) {
  const recordId = String(tpl?.telnyx_record_id || tpl?.record_id || '').trim()
  if (recordId.startsWith('local-')) return true
  if (tpl?.is_local_only === true) return true
  const status = String(tpl?.status || '').toUpperCase()
  return status === 'LOCAL_DRAFT' || status === 'DRAFT'
}

/** Thank-you / open-text templates accept free text or voice — buttons are optional. */
const BUTTONS_OPTIONAL_KINDS = new Set([
  'thank_you',
  'tell_us_more',
  'open_question',
  'final_feedback',
  'final_feedback_text',
  'reason',
])

function buttonsAreOptional(draft, editTarget) {
  const role = String(
    draft?.step_role ||
      draft?.template_key ||
      editTarget?.systemKind ||
      editTarget?.templateKey ||
      '',
  )
    .trim()
    .toLowerCase()
  if (BUTTONS_OPTIONAL_KINDS.has(role)) return true
  const name = String(draft?.name || draft?.display_name || '').toLowerCase()
  if (/thank_you|tell_us_more|open_question|final_feedback/.test(name)) return true
  return false
}

function shortMetaName(name, max = 28) {
  const full = String(name || '').trim()
  if (!full) return '—'
  if (full.length <= max) return full
  return `${full.slice(0, max - 1)}…`
}

function buttonsFromFeedbackTpl(tpl) {
  const fromComponents = buttonsFromComponents(
    parseComponents(tpl?.draft_components || tpl?.remote_components || tpl?.components),
  )
  if (fromComponents.length) return fromComponents
  const raw = tpl?.buttons
  if (!Array.isArray(raw)) return []
  return raw
    .map((b) => {
      if (typeof b === 'string') return { type: 'quick_reply', text: b }
      const text = String(b?.text || b?.title || '').trim()
      if (!text) return null
      return { type: 'quick_reply', text }
    })
    .filter(Boolean)
}

function apiTemplateToDraft(tpl, product) {
  const components = parseComponents(tpl?.draft_components || tpl?.remote_components || tpl?.components)
  const body = bodyFromComponents(components) || tpl?.body || tpl?.body_text || ''
  const footer = footerFromComponents(components) || tpl?.footer || STOP_FOOTER
  const buttons =
    product === 'feedback' ? buttonsFromFeedbackTpl(tpl) : buttonsFromComponents(components)
  const lang = langCodeToChip(tpl?.language)
  const metaName = String(tpl?.name || '').trim()
  return {
    id: tpl.id,
    name: metaName || String(tpl?.display_name || '').trim(),
    display_name: String(tpl?.display_name || '').trim(),
    langs: [lang],
    category: mapCategory(tpl),
    status: mapApprovalStatus(tpl),
    used: tpl.usage_count ?? tpl.used_count ?? 0,
    updated: formatRelativeWhen(tpl.updated_at || tpl.last_pushed_at),
    header: headerFromComponents(components),
    body,
    footer,
    buttons,
    variables: Array.isArray(tpl.example_values) ? [...tpl.example_values] : [],
    language: tpl.language || 'en_GB',
    product,
    active:
      product === 'interview'
        ? tpl.active_for_interview !== false
        : product === 'appointment'
          ? tpl.active_for_appointment !== false
          : tpl.active_for_survey !== false,
    step_role: tpl.step_role || tpl.template_key || null,
    template_key: tpl.template_key || null,
    components,
    is_local_only: isLocalDraftTemplate(tpl),
    telnyx_record_id: tpl?.telnyx_record_id || null,
    last_push_error: tpl?.last_push_error || null,
    draft_not_live_on_meta: Boolean(tpl?.draft_not_live_on_meta),
  }
}

function Field({ label, hint, children }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <Label className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</Label>
        {hint ? <span className="text-[10px] text-muted-foreground">{hint}</span> : null}
      </div>
      {children}
    </div>
  )
}

function Section({ title, icon: Icon, right, children }) {
  return (
    <div className="rounded-lg border bg-surface p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs font-semibold">
          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
          {title}
        </div>
        {right}
      </div>
      {children}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="rounded-md border bg-surface px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-xs font-medium">{value}</div>
    </div>
  )
}

/**
 * Design EditSheet wired to real template APIs.
 * editTarget: { product: 'survey'|'interview'|'appointment'|'feedback', templateId, surveyTypeId?, systemMode? }
 */
export default function WaEditSheet({ editTarget, onClose, onSaved }) {
  const open = Boolean(editTarget?.templateId)
  const [draft, setDraft] = useState(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [fixSyncing, setFixSyncing] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [surveyTypes, setSurveyTypes] = useState([])
  const [usageOpen, setUsageOpen] = useState(false)
  const [langVariants, setLangVariants] = useState([])
  const [activeTemplateId, setActiveTemplateId] = useState(null)
  const [metaNameExpanded, setMetaNameExpanded] = useState(false)
  const [removingLangId, setRemovingLangId] = useState(null)
  const [addingLangChip, setAddingLangChip] = useState(null)

  const showToast = (msg) => {
    setToast(msg)
    window.setTimeout(() => setToast(''), 2500)
  }

  const load = useCallback(async () => {
    if (!editTarget?.templateId) return
    setLoading(true)
    setError('')
    setUsageOpen(false)
    try {
      const product = editTarget.product
      let tpl
      let types = []
      let variants = []
      if (product === 'survey' || product === 'system') {
        const data = await apiFetch(`/admin/wa-survey/templates/${editTarget.templateId}`)
        tpl = data.template
        types = Array.isArray(data.survey_types) ? data.survey_types : []
        if (editTarget.systemMode && editTarget.surveyTypeId) {
          types = types.filter((row) => String(row.survey_type_id) === String(editTarget.surveyTypeId))
        }
      } else if (product === 'interview') {
        const data = await apiFetch(`/admin/wa-interview/templates/${editTarget.templateId}`)
        tpl = data.template || data
      } else if (product === 'appointment') {
        const data = await apiFetch(`/admin/wa-appointment/templates/${editTarget.templateId}`)
        tpl = data.template || data
      } else if (product === 'feedback') {
        if (editTarget.systemMode) {
          const data = await apiFetch('/admin/customer-feedback/system-templates')
          const kinds = Array.isArray(data?.kinds) ? data.kinds : []
          const all = kinds.flatMap((k) => (Array.isArray(k.templates) ? k.templates : []))
          tpl = all.find((t) => String(t.id) === String(editTarget.templateId))
          variants = []
        } else {
          const data = await apiFetch(`/admin/customer-feedback/survey-types/${editTarget.surveyTypeId}`)
          const templates = Array.isArray(data?.item?.templates) ? data.item.templates : []
          variants = templates.map((row) => ({
            id: row.id,
            language: row.language || 'en_GB',
            tpl: row.body || row.body_text ? { ...row, body: row.body || row.body_text } : row,
          }))
          tpl = templates.find((t) => String(t.id) === String(editTarget.templateId)) || templates[0]
        }
        if (!tpl) throw new Error('Template not found')
        if (!tpl.body && tpl.body_text) tpl = { ...tpl, body: tpl.body_text }
      } else {
        throw new Error('Unknown product')
      }
      if ((product === 'survey' || product === 'system') && editTarget.surveyTypeId && !editTarget.systemMode) {
        try {
          const typeData = await apiFetch(`/admin/wa-survey/types/${editTarget.surveyTypeId}`)
          const templates = Array.isArray(typeData?.templates) ? typeData.templates : []
          if (templates.length) {
            variants = templates.map((row) => ({
              id: row.id,
              language: row.language || 'en_GB',
              tpl: row,
            }))
            const match = templates.find((t) => String(t.id) === String(editTarget.templateId))
            if (match) tpl = match
          } else {
            variants = [{ id: tpl.id, language: tpl.language || 'en_GB', tpl }]
          }
        } catch {
          variants = [{ id: tpl.id, language: tpl.language || 'en_GB', tpl }]
        }
      } else if (product !== 'feedback' || editTarget.systemMode) {
        variants = tpl ? [{ id: tpl.id, language: tpl.language || 'en_GB', tpl }] : []
      }
      setLangVariants(variants)
      setActiveTemplateId(tpl?.id ?? editTarget.templateId)
      const nextDraft = apiTemplateToDraft(tpl, product === 'system' ? 'survey' : product)
      const variantLangs = [
        ...new Set(variants.map((v) => langCodeToChip(v.language)).filter(Boolean)),
      ]
      setDraft({
        ...nextDraft,
        langs: variantLangs.length ? variantLangs : nextDraft.langs,
        footer: STOP_FOOTER,
      })
      setSurveyTypes(types)
      setMetaNameExpanded(false)
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load template').message)
      setDraft(null)
    } finally {
      setLoading(false)
    }
  }, [editTarget])

  useEffect(() => {
    if (open) void load()
    else {
      setDraft(null)
      setError('')
      setSurveyTypes([])
    }
  }, [open, load])

  const update = (k, v) => setDraft((d) => (d ? { ...d, [k]: v } : d))

  const addVariable = () =>
    setDraft((d) =>
      d
        ? {
            ...d,
            variables: [...d.variables, `Variable ${d.variables.length + 1}`],
            body: `${d.body} {{${d.variables.length + 1}}}`,
          }
        : d,
    )

  const addButton = (type) =>
    setDraft((d) => {
      if (!d) return d
      if (d.buttons.length >= 3) {
        setError('Max 3 buttons allowed by WhatsApp')
        return d
      }
      const nb =
        type === 'url'
          ? { type: 'url', text: 'Visit site', url: 'https://' }
          : type === 'phone'
            ? { type: 'phone', text: 'Call us', phone: '+1' }
            : { type: 'quick_reply', text: 'Reply' }
      return { ...d, buttons: [...d.buttons, nb] }
    })

  const save = async () => {
    if (!draft || !editTarget) return
    setSaving(true)
    setError('')
    try {
      const templateId = activeTemplateId || editTarget.templateId
      const components = buildComponents(draft)
      if (!(draft.buttons || []).length && !buttonsAreOptional(draft, editTarget)) {
        throw new Error('Add at least one quick-reply button before saving.')
      }
      const category = draft.category === 'Marketing' ? 'MARKETING' : 'UTILITY'
      const product = editTarget.product === 'system' ? 'survey' : editTarget.product

      const displayName = draft.display_name || draft.name
      if (product === 'survey') {
        await apiFetch(`/admin/wa-survey/templates/${templateId}`, {
          method: 'PUT',
          body: JSON.stringify({
            display_name: displayName,
            category,
            language: draft.language || 'en_GB',
            active_for_survey: draft.active,
            components,
            example_values: draft.variables,
            step_role: draft.step_role || null,
          }),
        })
      } else if (product === 'interview') {
        await apiFetch(`/admin/wa-interview/templates/${templateId}`, {
          method: 'PUT',
          body: JSON.stringify({
            display_name: displayName,
            category,
            language: draft.language || 'en_GB',
            active_for_interview: draft.active,
            components,
            example_values: draft.variables,
          }),
        })
      } else if (product === 'appointment') {
        await apiFetch(`/admin/wa-appointment/templates/${templateId}`, {
          method: 'PUT',
          body: JSON.stringify({
            display_name: displayName,
            category,
            language: draft.language || 'en_GB',
            active_for_appointment: draft.active,
            components,
            example_values: draft.variables,
          }),
        })
      } else if (product === 'feedback') {
        await apiFetch('/admin/customer-feedback/wa-templates', {
          method: 'POST',
          body: JSON.stringify({
            id: templateId,
            body_text: draft.body,
            meta_category: category.toLowerCase(),
            language: draft.language || 'en_GB',
            is_active: draft.active,
            buttons: draft.buttons,
            survey_type_id: editTarget.surveyTypeId,
          }),
        })
      }
      showToast('Template saved')
      onSaved?.(draft)
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not save template').message)
    } finally {
      setSaving(false)
    }
  }

  const sync = async () => {
    if (!editTarget) return
    setSyncing(true)
    setError('')
    try {
      const product = editTarget.product === 'system' ? 'survey' : editTarget.product
      const ids =
        langVariants.length > 1
          ? langVariants.map((v) => v.id)
          : [activeTemplateId || editTarget.templateId]
      if (product === 'survey') {
        for (const id of ids) {
          await apiFetch(`/admin/wa-survey/templates/${id}/push`, {
            method: 'POST',
            body: JSON.stringify({ force_push: false }),
            timeoutMs: 180000,
          })
        }
      } else if (product === 'interview') {
        await apiFetch(`/admin/wa-interview/templates/${ids[0]}/push`, { method: 'POST', body: '{}' })
      } else if (product === 'appointment') {
        await apiFetch(`/admin/wa-appointment/templates/${ids[0]}/push`, { method: 'POST', body: '{}' })
      } else if (product === 'feedback') {
        for (const id of ids) {
          await apiFetch(`/admin/customer-feedback/wa-templates/${id}/push`, {
            method: 'POST',
            timeoutMs: 180000,
          })
        }
      } else {
        showToast('Synced with Meta')
        return
      }
      showToast(ids.length > 1 ? `Synced ${ids.length} languages with Meta` : 'Synced with Meta')
      onSaved?.()
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Sync failed').detailText || e?.message)
    } finally {
      setSyncing(false)
    }
  }

  const fixAndSync = async () => {
    if (!editTarget) return
    const templateId = activeTemplateId || editTarget.templateId
    setFixSyncing(true)
    setError('')
    const payload = {
      fix_and_sync: true,
      repair: true,
      utility_rewrite: false,
      force_push: true,
    }
    const pushPath = `/admin/wa-survey/templates/${templateId}/push`
    const fixPath = `/admin/wa-survey/templates/${templateId}/fix-and-sync`
    try {
      let data
      try {
        data = await apiFetch(pushPath, {
          method: 'POST',
          body: JSON.stringify(payload),
          timeoutMs: 240000,
        })
      } catch (firstErr) {
        if (firstErr?.status === 404) {
          data = await apiFetch(fixPath, {
            method: 'POST',
            body: JSON.stringify(payload),
            timeoutMs: 240000,
          })
        } else {
          throw firstErr
        }
      }
      const action = String(data?.action || 'ok')
      const steps = Array.isArray(data?.steps) ? data.steps.join(' → ') : ''
      showToast(
        data?.message ||
          (action === 'linked'
            ? 'Linked to Meta'
            : action === 'synced_sibling'
              ? 'Synced from sibling Meta row'
              : 'Fix & sync complete'),
      )
      if (steps) {
        console.info('[wa-template fix-and-sync]', steps)
      }
      onSaved?.()
      await load()
    } catch (e) {
      const msg = formatWaSurveyError(e, 'Fix & sync failed')
      if (e?.status === 404) {
        setError(
          `${msg.detailText || msg.message}\n\nThe API may not be restarted after deploy. On VPS: git pull && VOX_SKIP_BUILD=1 ./deploy-vps.sh`,
        )
      } else {
        setError(msg.detailText || e?.message)
      }
    } finally {
      setFixSyncing(false)
    }
  }

  const saveMappings = async () => {
    if (!editTarget?.templateId) return
    setSaving(true)
    try {
      const mappings = surveyTypes
        .filter((st) => st.linked || st.usable_as_standard || st.usable_as_anonymous || st.is_default_standard || st.is_default_anonymous)
        .map((st) => ({
          survey_type_id: st.survey_type_id,
          usable_as_standard: Boolean(st.usable_as_standard),
          usable_as_anonymous: Boolean(st.usable_as_anonymous),
          is_default_standard: Boolean(st.is_default_standard),
          is_default_anonymous: Boolean(st.is_default_anonymous),
        }))
      const data = await apiFetch(`/admin/wa-survey/templates/${editTarget.templateId}/mappings`, {
        method: 'PUT',
        body: JSON.stringify({ mappings }),
      })
      setSurveyTypes(data.survey_types || [])
      showToast('Mappings saved')
      onSaved?.()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not save mappings').message)
    } finally {
      setSaving(false)
    }
  }

  const toggleSurveyType = (id, field) => {
    setSurveyTypes((rows) =>
      rows.map((st) => (String(st.survey_type_id) === String(id) ? { ...st, [field]: !st[field], linked: true } : st)),
    )
  }

  const isFeedbackTopic = editTarget?.product === 'feedback' && !editTarget?.systemMode
  const langChips = isFeedbackTopic ? FEEDBACK_LANG_CHIPS : LANGS

  const switchLanguageVariant = (variant, chip) => {
    const product = editTarget?.product === 'system' ? 'survey' : editTarget?.product
    const allLangs = [...new Set(langVariants.map((v) => langCodeToChip(v.language)).filter(Boolean))]
    setActiveTemplateId(variant.id)
    setDraft({
      ...apiTemplateToDraft(variant.tpl, product),
      langs: allLangs.length ? allLangs : [chip],
      footer: STOP_FOOTER,
    })
  }

  const removeLanguageVariant = async (variant) => {
    if (!variant || langVariants.length <= 1) return
    const chip = langCodeToChip(variant.language)
    if (
      !window.confirm(
        `Remove the ${chip} language version for this topic? The local template row will be deleted (Meta name unchanged for other languages).`,
      )
    ) {
      return
    }
    setRemovingLangId(variant.id)
    setError('')
    try {
      await apiFetch(`/admin/customer-feedback/wa-templates/${variant.id}`, { method: 'DELETE' })
      showToast(`${chip} language removed`)
      onSaved?.()
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not remove language').message)
    } finally {
      setRemovingLangId(null)
    }
  }

  const addLanguageVariant = async (chip) => {
    if (!editTarget?.surveyTypeId) return
    const anchor = langVariants.find((v) => langCodeToChip(v.language) === 'EN') || langVariants[0]
    if (!anchor?.tpl) {
      setError('Save the English version first before adding languages')
      return
    }
    setAddingLangChip(chip)
    setError('')
    try {
      const language = feedbackChipToLanguage(chip)
      const buttons = buttonsFromFeedbackTpl(anchor.tpl)
      const data = await apiFetch('/admin/customer-feedback/wa-templates', {
        method: 'POST',
        body: JSON.stringify({
          survey_type_id: editTarget.surveyTypeId,
          industry_id: anchor.tpl.industry_id,
          template_key: anchor.tpl.template_key || 'question',
          step_order: anchor.tpl.step_order || 1,
          step_role: anchor.tpl.step_role,
          body_text: anchor.tpl.body || anchor.tpl.body_text || '',
          language,
          meta_category: anchor.tpl.meta_category || 'utility',
          buttons: buttons.map((b) => b.text).filter(Boolean),
          is_active: anchor.tpl.is_active !== false,
        }),
      })
      const created = data?.item
      showToast(`${chip} language added — edit text then Save`)
      onSaved?.()
      await load()
      const createdId = created?.id
      if (createdId) {
        setActiveTemplateId(createdId)
      }
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not add language').message)
    } finally {
      setAddingLangChip(null)
    }
  }

  const t = draft
  const showUsage = (editTarget?.product === 'survey' || editTarget?.product === 'system') && !editTarget?.systemMode
  const showFixAndSync = editTarget?.product === 'survey' || editTarget?.product === 'system'
  const metaNameReadOnly = Boolean(t && !t.is_local_only)

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose?.()}>
      <SheetContent
        side="right"
        className="waTemplatesHub ds-scope w-full overflow-hidden border-l p-0 sm:max-w-[960px]"
      >
        {loading ? (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">Loading template…</div>
        ) : null}
        {t && !loading ? (
          <div className="flex h-full flex-col">
            <div className="flex h-12 shrink-0 items-center gap-3 border-b bg-surface-muted/50 px-4">
              <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10 text-primary">
                <Pencil className="h-3.5 w-3.5" />
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold">Edit template</div>
                <div className="truncate font-mono text-[11px] text-muted-foreground" title={t.name}>
                  {t.name}
                </div>
              </div>
              <div className="ml-auto flex items-center gap-1">
                {showFixAndSync ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 gap-1 text-xs"
                    onClick={() => void fixAndSync()}
                    disabled={fixSyncing || syncing || saving}
                    title="Repair draft, UTILITY-rewrite, push or link to Meta"
                  >
                    <Wrench className={cn('h-3.5 w-3.5', fixSyncing && 'animate-spin')} />
                    {fixSyncing ? 'Fixing…' : 'Fix & Sync'}
                  </Button>
                ) : null}
                <Button
                  size="sm"
                  variant="ghost"
                  className="wa-hub-ghost-btn h-7 gap-1 text-xs"
                  onClick={() => void sync()}
                  disabled={syncing || fixSyncing}
                >
                  <RefreshCw className={cn('h-3.5 w-3.5', syncing && 'animate-spin')} /> Sync
                </Button>
                <SheetClose asChild>
                  <Button size="sm" variant="ghost" className="wa-hub-ghost-btn h-7 gap-1 text-xs">
                    <X className="h-3.5 w-3.5" /> Cancel
                  </Button>
                </SheetClose>
                <Button
                  size="sm"
                  className="wa-hub-primary-btn h-7 gap-1 text-xs"
                  onClick={() => void save()}
                  disabled={saving}
                >
                  <Save className="h-3.5 w-3.5" /> {saving ? 'Saving…' : 'Save'}
                </Button>
              </div>
            </div>

            {error ? (
              <div className="border-b border-destructive/30 bg-destructive/10 px-4 py-2 text-xs text-destructive whitespace-pre-wrap">{error}</div>
            ) : null}
            {!error && t?.last_push_error ? (
              <div className="border-b border-warning/30 bg-warning/10 px-4 py-2 text-xs text-warning-foreground whitespace-pre-wrap">
                Last push error: {t.last_push_error}
              </div>
            ) : null}
            {toast ? (
              <div className="border-b border-success/30 bg-success-soft px-4 py-2 text-xs text-success">{toast}</div>
            ) : null}

            <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[1fr_340px]">
              <div className="space-y-4 overflow-y-auto p-4">
                <div className="grid grid-cols-2 gap-3">
                  <Field
                    label="Template name"
                    hint={metaNameReadOnly ? 'Meta name (read-only)' : 'Local draft'}
                  >
                    {metaNameReadOnly ? (
                      <span
                        role="text"
                        className={cn(
                          'block min-h-8 cursor-pointer select-text break-all font-mono text-xs leading-8 text-muted-foreground',
                          !metaNameExpanded && 'truncate',
                        )}
                        title={metaNameExpanded ? 'Click to shorten' : (t.name || 'Click to show full name')}
                        onClick={() => setMetaNameExpanded((v) => !v)}
                      >
                        {metaNameExpanded ? t.name || '—' : shortMetaName(t.name)}
                      </span>
                    ) : (
                      <Input
                        value={t.name || ''}
                        onChange={(e) => update('name', e.target.value)}
                        className="h-8 font-mono text-xs"
                        title={t.name}
                      />
                    )}
                  </Field>
                  <Field label="Category">
                    <select
                      value={t.category}
                      onChange={(e) => update('category', e.target.value)}
                      className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
                    >
                      <option value="Utility">Utility</option>
                      <option value="Marketing">Marketing</option>
                    </select>
                  </Field>
                </div>
                <Field label="Display label">
                  <Input
                    value={t.display_name || t.name || ''}
                    onChange={(e) => update('display_name', e.target.value)}
                    className="h-8 text-xs"
                    placeholder="Friendly label shown in admin lists"
                  />
                </Field>

                <Field
                  label="Languages"
                  hint={
                    isFeedbackTopic
                      ? `${langVariants.length} of ${FEEDBACK_LANG_CHIPS.length} — tap to edit, + empty tab to add, × to remove`
                      : langVariants.length > 1
                        ? 'Tap a language to edit that version'
                        : 'All language tags — more can be added later'
                  }
                >
                  <div className="flex flex-wrap gap-1.5">
                    {langChips.map((l) => {
                      const variant = langVariants.find((v) => langCodeToChip(v.language) === l)
                      const current = langCodeToChip(t.language) === l
                      const on = Boolean(variant)
                      const busy = removingLangId === variant?.id || addingLangChip === l
                      return (
                        <span key={l} className="inline-flex items-center gap-0.5">
                          <button
                            type="button"
                            disabled={busy || removingLangId != null}
                            onClick={() => {
                              if (variant) {
                                switchLanguageVariant(variant, l)
                                return
                              }
                              if (isFeedbackTopic) {
                                void addLanguageVariant(l)
                                return
                              }
                              update('langs', t.langs.includes(l) ? t.langs.filter((x) => x !== l) : [...t.langs, l])
                            }}
                            className={cn(
                              'h-6 rounded-md px-2 text-[11px] font-medium uppercase ring-1 ring-inset transition-all',
                              langChipClass(l, { active: current, muted: !on && !current }),
                              busy && 'opacity-60',
                            )}
                            title={
                              variant
                                ? `Edit ${l}`
                                : isFeedbackTopic
                                  ? `Add ${l} (copies English draft)`
                                  : `Toggle ${l}`
                            }
                          >
                            {addingLangChip === l ? '…' : on ? l : `+ ${l}`}
                          </button>
                          {isFeedbackTopic && variant && langVariants.length > 1 && current ? (
                            <button
                              type="button"
                              className="inline-flex h-5 w-5 items-center justify-center rounded text-destructive hover:bg-destructive/10"
                              title={`Remove ${l} language`}
                              disabled={busy}
                              onClick={() => void removeLanguageVariant(variant)}
                            >
                              <X className="h-3 w-3" />
                            </button>
                          ) : null}
                        </span>
                      )
                    })}
                  </div>
                </Field>

                <Section title="Header" icon={TypeIcon}>
                  <div className="grid grid-cols-[120px_1fr] items-center gap-2">
                    <select
                      value={t.header?.type ?? 'none'}
                      onChange={(e) => {
                        const v = e.target.value
                        update(
                          'header',
                          v === 'none' ? undefined : { type: v, text: t.header?.text ?? '' },
                        )
                      }}
                      className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                    >
                      <option value="none">None</option>
                      <option value="text">Text</option>
                      <option value="image">Image</option>
                    </select>
                    {t.header?.type === 'text' ? (
                      <Input
                        value={t.header.text ?? ''}
                        onChange={(e) => update('header', { type: 'text', text: e.target.value })}
                        maxLength={60}
                        placeholder="Header text (max 60 chars)"
                        className="h-8 text-xs"
                      />
                    ) : null}
                    {t.header?.type === 'image' ? (
                      <div className="flex h-8 items-center justify-center gap-1 rounded-md border border-dashed text-[11px] text-muted-foreground">
                        <ImageIcon className="h-3.5 w-3.5" /> Upload media on sync
                      </div>
                    ) : null}
                  </div>
                </Section>

                <Section
                  title="Body"
                  icon={TypeIcon}
                  right={
                    <Button size="sm" variant="outline" className="h-6 gap-1 text-[11px]" onClick={addVariable}>
                      <Plus className="h-3 w-3" /> Variable
                    </Button>
                  }
                >
                  <Textarea
                    value={t.body}
                    onChange={(e) => update('body', e.target.value)}
                    rows={5}
                    maxLength={1024}
                    className="resize-none font-mono text-xs"
                  />
                  <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                    <span>Use *bold*, _italic_, ~strike~, ```mono```</span>
                    <span className="tabular-nums">{t.body.length}/1024</span>
                  </div>
                  {t.variables.length > 0 ? (
                    <div className="mt-2 space-y-1">
                      {t.variables.map((v, i) => (
                        <div key={i} className="flex items-center gap-2">
                          <span className="inline-flex h-6 min-w-[36px] items-center justify-center rounded bg-primary/10 px-1.5 font-mono text-[11px] text-primary">
                            {`{{${i + 1}}}`}
                          </span>
                          <Input
                            value={v}
                            onChange={(e) => {
                              const next = [...t.variables]
                              next[i] = e.target.value
                              update('variables', next)
                            }}
                            className="h-7 text-xs"
                            placeholder="Sample value / description"
                          />
                          <IconBtn
                            icon={Trash2}
                            label="Remove"
                            tone="danger"
                            onClick={() => update('variables', t.variables.filter((_, x) => x !== i))}
                          />
                        </div>
                      ))}
                    </div>
                  ) : null}
                </Section>

                <Section title="Footer" icon={TypeIcon}>
                  <Input
                    value={STOP_FOOTER}
                    readOnly
                    maxLength={60}
                    className="h-8 cursor-default bg-surface-muted/50 text-xs text-muted-foreground"
                    title="Required on every WhatsApp template"
                  />
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    Required on every WhatsApp template (saved automatically).
                  </p>
                </Section>

                <Section
                  title="Buttons"
                  icon={Reply}
                  right={
                    <div className="relative">
                      <details className="group">
                        <summary className="flex h-6 cursor-pointer list-none items-center gap-1 rounded-md border px-2 text-[11px] font-medium">
                          <Plus className="h-3 w-3" /> Add button <ChevronDown className="h-3 w-3" />
                        </summary>
                        <div className="absolute right-0 z-10 mt-1 min-w-[140px] rounded-md border bg-background p-1 shadow-md">
                          <button type="button" className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-accent" onClick={() => addButton('quick_reply')}>
                            <Reply className="h-3.5 w-3.5" /> Quick reply
                          </button>
                          <button type="button" className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-accent" onClick={() => addButton('url')}>
                            <Link2 className="h-3.5 w-3.5" /> URL
                          </button>
                          <button type="button" className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-accent" onClick={() => addButton('phone')}>
                            <Phone className="h-3.5 w-3.5" /> Phone
                          </button>
                        </div>
                      </details>
                    </div>
                  }
                >
                  {t.buttons.length === 0 ? (
                    <div className="text-[11px] italic text-muted-foreground">
                      {buttonsAreOptional(t, editTarget)
                        ? 'No buttons — open text / voice reply (thank you & tell us more).'
                        : 'No buttons yet.'}
                    </div>
                  ) : null}
                  <div className="space-y-1.5">
                    {t.buttons.map((b, i) => (
                      <div key={i} className="animate-fade-in grid grid-cols-[90px_1fr_auto] items-center gap-2">
                        <div className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground">
                          {b.type === 'quick_reply' ? <Reply className="h-3 w-3" /> : null}
                          {b.type === 'url' ? <Link2 className="h-3 w-3" /> : null}
                          {b.type === 'phone' ? <Phone className="h-3 w-3" /> : null}
                          {String(b.type).replace('_', ' ')}
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <Input
                            value={b.text}
                            onChange={(e) => {
                              const next = [...t.buttons]
                              next[i] = { ...b, text: e.target.value }
                              update('buttons', next)
                            }}
                            className="h-7 text-xs"
                            placeholder="Button text"
                          />
                          {b.type === 'url' ? (
                            <Input
                              value={b.url || ''}
                              onChange={(e) => {
                                const next = [...t.buttons]
                                next[i] = { ...b, url: e.target.value }
                                update('buttons', next)
                              }}
                              className="h-7 font-mono text-xs"
                              placeholder="https://…"
                            />
                          ) : null}
                          {b.type === 'phone' ? (
                            <Input
                              value={b.phone || ''}
                              onChange={(e) => {
                                const next = [...t.buttons]
                                next[i] = { ...b, phone: e.target.value }
                                update('buttons', next)
                              }}
                              className="h-7 font-mono text-xs"
                              placeholder="+1 555…"
                            />
                          ) : null}
                        </div>
                        <IconBtn
                          icon={Trash2}
                          label="Remove"
                          tone="danger"
                          onClick={() => update('buttons', t.buttons.filter((_, x) => x !== i))}
                        />
                      </div>
                    ))}
                  </div>
                </Section>

                <div className="flex items-center justify-between rounded-lg border bg-surface p-3">
                  <div>
                    <div className="text-xs font-medium">Template enabled</div>
                    <div className="text-[11px] text-muted-foreground">
                      Disabled templates cannot be sent from any workflow.
                    </div>
                  </div>
                  <Switch
                    checked={t.active && t.status !== 'disabled'}
                    onCheckedChange={(v) => {
                      update('active', v)
                      update('status', v ? 'approved' : 'disabled')
                    }}
                    className="data-[state=checked]:bg-success data-[state=unchecked]:bg-destructive"
                  />
                </div>

                <div className="grid grid-cols-3 gap-2 text-[11px]">
                  <Stat label="Used" value={Number(t.used || 0).toLocaleString()} />
                  <Stat label="Status" value={<StatusDot status={t.status} />} />
                  <Stat label="Updated" value={t.updated} />
                </div>

                {t.draft_not_live_on_meta ? (
                  <p className="text-[11px] text-amber-700 dark:text-amber-400">
                    DB draft is not live on WhatsApp yet — Sync to Meta and wait for approval.
                  </p>
                ) : null}

                {showUsage ? (
                  <div className="rounded-lg border bg-surface">
                    <button
                      type="button"
                      className="flex w-full items-center justify-between px-3 py-2 text-left"
                      onClick={() => setUsageOpen((v) => !v)}
                    >
                      <div className="flex items-center gap-1.5 text-xs font-semibold">
                        <Link2 className="h-3.5 w-3.5 text-muted-foreground" />
                        Survey type usage
                        <span className="font-normal text-muted-foreground">
                          ({surveyTypes.length} types)
                        </span>
                      </div>
                      <ChevronDown className={cn('h-4 w-4 text-muted-foreground transition', usageOpen && 'rotate-180')} />
                    </button>
                    {usageOpen ? (
                      <div className="space-y-2 border-t px-3 py-3">
                        <p className="text-[11px] text-muted-foreground">
                          Which survey types can use this template as standard/anonymous launch, and which defaults apply.
                        </p>
                        {surveyTypes.map((st) => (
                          <div key={st.survey_type_id} className="flex flex-wrap items-center gap-3 text-xs">
                            <strong className="min-w-[120px]">{st.name}</strong>
                            <label className="inline-flex items-center gap-1">
                              <input type="checkbox" checked={Boolean(st.usable_as_standard)} onChange={() => toggleSurveyType(st.survey_type_id, 'usable_as_standard')} /> Std
                            </label>
                            <label className="inline-flex items-center gap-1">
                              <input type="checkbox" checked={Boolean(st.usable_as_anonymous)} onChange={() => toggleSurveyType(st.survey_type_id, 'usable_as_anonymous')} disabled={!st.supports_anonymous} /> Anon
                            </label>
                            <label className="inline-flex items-center gap-1">
                              <input type="checkbox" checked={Boolean(st.is_default_standard)} onChange={() => toggleSurveyType(st.survey_type_id, 'is_default_standard')} /> Def std
                            </label>
                            <label className="inline-flex items-center gap-1">
                              <input type="checkbox" checked={Boolean(st.is_default_anonymous)} onChange={() => toggleSurveyType(st.survey_type_id, 'is_default_anonymous')} disabled={!st.supports_anonymous} /> Def anon
                            </label>
                          </div>
                        ))}
                        <Button size="sm" className="h-7 text-xs" onClick={() => void saveMappings()} disabled={saving}>
                          Save mappings
                        </Button>
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {editTarget?.systemMode ? (
                  <div className="rounded-lg border bg-surface p-3 text-[11px] text-muted-foreground">
                    System template scope — linked to the hidden system survey type. Use Save for content changes.
                  </div>
                ) : null}
              </div>

              <div className="hidden overflow-y-auto border-l bg-gradient-to-br from-surface-muted/60 to-surface p-4 lg:block">
                <div className="mb-3 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  <Globe className="h-3 w-3" /> Live preview · iPhone 17 Pro Max
                </div>
                <WaPhonePreview template={t} />
              </div>
            </div>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  )
}
