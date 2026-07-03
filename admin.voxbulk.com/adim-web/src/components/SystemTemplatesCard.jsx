import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Layers } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Pill } from '@/components/ui/Badge'

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
  if (category.anonymousOnly) {
    return templates.filter(isAnonymousTemplate).length
  }
  if (category.kind === 'welcome') {
    return templates.filter((t) => !isAnonymousTemplate(t)).length
  }
  return templates.length
}

export default function SystemTemplatesCard({ product = 'survey' }) {
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

  const totalCount = useMemo(() => {
    if (product === 'feedback') {
      return kinds.reduce((sum, k) => sum + (k.count || 0), 0)
    }
    return kinds.reduce((sum, k) => sum + (k.count || 0), 0)
  }, [kinds, product])

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="rounded-md bg-primary/10 p-2 text-primary">
            <Layers size={18} />
          </div>
          <div>
            <h3 className="text-sm font-semibold">System templates</h3>
            <p className="mt-0.5 max-w-2xl text-[12px] text-muted-foreground">
              Shared {product === 'feedback' ? 'Customer Feedback' : 'Survey'} WhatsApp templates used across all
              industries — welcome, thank-you, opt-in, tell-us-more, closing questions, and anonymous variants.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {totalCount ? <Pill tone="neutral">{totalCount} saved</Pill> : null}
          <Button type="button" variant="outline" size="sm" className="h-8" asChild>
            <Link to={manageHref}>
              Manage system templates
              <ChevronRight size={14} className="ml-1" />
            </Link>
          </Button>
        </div>
      </div>

      {error ? <p className="mb-2 text-[12px] text-destructive">{error}</p> : null}

      {loading ? (
        <p className="text-[12px] text-muted-foreground">Loading system template library…</p>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
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
                className="rounded-md border border-border/80 bg-muted/20 px-3 py-2 transition hover:border-primary/40 hover:bg-muted/40"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[12px] font-medium">{category.label}</span>
                  <Pill tone={count > 0 ? 'success' : 'neutral'}>{count}</Pill>
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
