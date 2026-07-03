import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Layers } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { Button } from '@/components/ui/Button'

const SURVEY_CATEGORIES = [
  { kind: 'welcome', label: 'Welcome' },
  { kind: 'welcome', label: 'Anonymous survey welcome', anonymousOnly: true },
  { kind: 'thank_you', label: 'Thank you' },
  { kind: 'tell_us_more', label: 'Tell us more' },
  { kind: 'final_feedback', label: 'Closing question' },
  { kind: 'welcome', label: 'Quick anonymous survey', anonymousOnly: true },
]

const FEEDBACK_CATEGORIES = [
  { key: 'thank_you', label: 'Thank you' },
  { key: 'tell_us_more', label: 'Tell us more' },
  { key: 'marketing_opt_in', label: 'Opt in' },
  { key: 'open_question', label: 'Share your feedback' },
]

function isAnonymousTemplate(tpl) {
  const variant = String(tpl?.variant_type || '').toLowerCase()
  const privacy = String(tpl?.privacy_mode || '').toLowerCase()
  return variant === 'anonymous' || privacy === 'on'
}

function countForSurveyCategory(section, category) {
  const templates = Array.isArray(section?.templates) ? section.templates : []
  if (category.anonymousOnly) return templates.filter(isAnonymousTemplate).length
  if (category.kind === 'welcome') return templates.filter((t) => !isAnonymousTemplate(t)).length
  return templates.length
}

export default function WaTemplatesSystemSection({ product = 'survey', embedded = false }) {
  const [loading, setLoading] = useState(true)
  const [kinds, setKinds] = useState([])
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const path =
        product === 'feedback'
          ? '/admin/customer-feedback/system-templates'
          : '/admin/wa-survey/system-templates'
      const data = await apiFetch(path)
      setKinds(Array.isArray(data?.kinds) ? data.kinds : [])
    } catch (e) {
      setError(e?.message || 'Could not load system templates')
      setKinds([])
    } finally {
      setLoading(false)
    }
  }, [product])

  useEffect(() => {
    void load()
  }, [load])

  const kindMap = useMemo(() => {
    const map = {}
    for (const section of kinds) {
      const key = product === 'feedback' ? section.key : section.kind
      if (key) map[key] = section
    }
    return map
  }, [kinds, product])

  const manageHref =
    product === 'feedback' ? '/customer-feedback/system-templates' : '/settings/wa-survey/system-templates'

  const categories = product === 'feedback' ? FEEDBACK_CATEGORIES : SURVEY_CATEGORIES

  const totalCount = useMemo(() => kinds.reduce((sum, k) => sum + (k.count || 0), 0), [kinds])

  return (
    <div className={embedded ? 'border-b bg-surface-muted/20 p-3' : 'rounded-lg border bg-surface p-3'}>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Layers className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold">System templates</h3>
            <p className="mt-0.5 max-w-2xl text-[11px] text-muted-foreground">
              Shared {product === 'feedback' ? 'Customer Feedback' : 'Survey'} WhatsApp templates used across all
              industries.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {totalCount ? (
            <span className="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
              {totalCount} saved
            </span>
          ) : null}
          <Button type="button" variant="outline" size="sm" className="h-8 text-xs" asChild>
            <Link to={manageHref}>
              Manage
              <ChevronRight className="ml-1 h-3.5 w-3.5" />
            </Link>
          </Button>
        </div>
      </div>

      {error ? <p className="mb-2 text-[11px] text-destructive">{error}</p> : null}

      {loading ? (
        <p className="text-[11px] text-muted-foreground">Loading system template library…</p>
      ) : (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {categories.map((category) => {
            const sectionKey = product === 'feedback' ? category.key : category.kind
            const section = kindMap[sectionKey]
            const count =
              product === 'survey'
                ? countForSurveyCategory(section, category)
                : section?.count ?? (section?.templates || []).length
            const hash =
              product === 'survey'
                ? `#system-templates-${category.kind}`
                : `#cf-system-${category.key || category.kind}`
            return (
              <Link
                key={`${sectionKey}-${category.label}`}
                to={`${manageHref}${hash}`}
                className="rounded-lg border bg-surface px-2.5 py-2 transition hover:border-primary/40 hover:shadow-sm"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[11px] font-medium">{category.label}</span>
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                      count > 0 ? 'bg-success-soft text-success' : 'bg-surface-muted text-muted-foreground'
                    }`}
                  >
                    {count}
                  </span>
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
