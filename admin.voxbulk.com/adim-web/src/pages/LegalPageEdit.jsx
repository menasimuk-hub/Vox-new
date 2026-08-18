import React, { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { copyText, fetchLegalPage, saveLegalPage } from '../lib/legalPagesApi'
import { sanitizeCmsHtml } from '../lib/sanitizeHtml'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Textarea } from '@/components/ui/Textarea'

const DEFAULT_HTML = `<div class="page-header">
  <div class="page-tag">Legal document</div>
  <div class="page-title">Page title</div>
</div>
<div class="section">
  <div class="section-title">1. Section heading</div>
  <p>Your legal copy…</p>
</div>`

export default function LegalPageEdit() {
  const { slug } = useParams()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [offline, setOffline] = useState(false)
  const [apiBase, setApiBase] = useState(null)
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState('')
  const [draft, setDraft] = useState({
    slug: '',
    title: '',
    public_path: '',
    meta_description: '',
    body: '',
    is_published: true,
  })

  const load = useCallback(async () => {
    if (!slug) return
    setError('')
    setLoading(true)
    try {
      const result = await fetchLegalPage(slug)
      const row = result.row
      setDraft({
        slug: row.slug || slug,
        title: row.title || '',
        public_path: row.public_path || '/legal-policies',
        meta_description: row.meta_description || '',
        body: row.body || '',
        is_published: row.is_published !== false,
      })
      setOffline(Boolean(result.offline))
      setApiBase(result.apiBase)
      if (result.offline) {
        setFeedback('Loaded bundled / local draft content. Save stores in this browser until the API is live.')
      }
    } catch (e) {
      setError(e?.message || 'Could not load page')
    } finally {
      setLoading(false)
    }
  }, [slug])

  useEffect(() => {
    load()
  }, [load])

  const save = async () => {
    setSaving(true)
    setError('')
    setFeedback('')
    try {
      const payload = {
        title: draft.title.trim(),
        meta_description: draft.meta_description.trim() || null,
        body: draft.body,
        is_published: draft.is_published,
      }
      const result = await saveLegalPage(slug, payload, apiBase)
      setOffline(Boolean(result.offline))
      setApiBase(result.apiBase)
      if (result.offline) {
        setFeedback(
          'Saved in this browser only. To publish on voxbulk.com now: copy HTML → update voxbulk.com/frontend/src/data/legalDefaultBodies.json → rebuild public frontend.',
        )
      } else {
        setFeedback('Page saved to the database. Refresh voxbulk.com/legal-policies to see changes.')
      }
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const copyHtml = async () => {
    const ok = await copyText(draft.body || '')
    setFeedback(ok ? 'HTML copied to clipboard.' : 'Could not copy — select the HTML manually.')
  }

  const insertStarter = () => {
    setDraft((d) => ({ ...d, body: DEFAULT_HTML }))
  }

  return (
    <div className="ds-scope space-y-4">
      <div className="pageTop">
        <div>
          <div className="mb-1.5 text-xs text-muted-foreground">
            <Link to="/settings/legal" className="text-primary hover:underline">
              ← Back to legal pages
            </Link>
          </div>
          <h1>Edit · {draft.title || slug}</h1>
          <p>
            Public URL:{' '}
            <a
              href={`https://voxbulk.com/legal-policies?tab=${encodeURIComponent(draft.slug || slug || 'terms')}`}
              target="_blank"
              rel="noreferrer"
              className="text-primary hover:underline"
            >
              voxbulk.com/legal-policies?tab={draft.slug || slug}
            </a>
          </p>
        </div>
      </div>

      {offline ? (
        <div className="rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-sm text-warning">
          Offline mode — API save unavailable. Edits are stored in this browser; use Copy HTML to update the live site
          file.
        </div>
      ) : null}
      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <Panel
          title="HTML content"
          action={
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={Boolean(draft.is_published)}
                onChange={(e) => setDraft((d) => ({ ...d, is_published: e.target.checked }))}
              />
              <span className="text-xs text-muted-foreground">Published on public site</span>
            </label>
          }
          bodyClassName="space-y-4"
        >
          <div className="space-y-1.5">
            <Label className="text-[11px] text-muted-foreground">Page title</Label>
            <Input
              className="h-8"
              value={draft.title}
              onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-[11px] text-muted-foreground">Meta description (SEO)</Label>
            <Input
              className="h-8"
              value={draft.meta_description}
              onChange={(e) => setDraft((d) => ({ ...d, meta_description: e.target.value }))}
              placeholder="Short summary for search engines"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">HTML body</Label>
              <Textarea
                className="min-h-[320px] font-mono text-[12px]"
                value={draft.body}
                onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))}
                placeholder='<div class="page-header">…</div>'
              />
              <p className="m-0 text-[11px] text-muted-foreground">
                Use the same HTML classes as the live page: page-header, page-title, section, section-title, info-box,
                table-wrap, etc.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">
                <i className="ti ti-eye mr-1.5" />
                Live preview
              </Label>
              <div className="min-h-[320px] overflow-auto rounded-md border border-border bg-background p-3">
                {draft.body ? (
                  <div className="legalPreviewInner" dangerouslySetInnerHTML={{ __html: sanitizeCmsHtml(draft.body) }} />
                ) : (
                  <p className="m-0 text-sm text-muted-foreground">HTML preview appears here.</p>
                )}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button type="button" size="sm" className="h-8" onClick={save} disabled={saving || !draft.title.trim()}>
              <i className="ti ti-device-floppy" />
              {saving ? 'Saving…' : offline ? 'Save local draft' : 'Save page'}
            </Button>
            <Button type="button" variant="outline" size="sm" className="h-8" onClick={copyHtml}>
              Copy HTML
            </Button>
            <Button type="button" variant="outline" size="sm" className="h-8" onClick={insertStarter}>
              Insert starter HTML
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8"
              onClick={() =>
                window.open(
                  `https://voxbulk.com/legal-policies?tab=${encodeURIComponent(draft.slug || slug || 'terms')}`,
                  '_blank',
                  'noopener,noreferrer',
                )
              }
            >
              View public page
            </Button>
            {feedback ? <span className="self-center text-xs text-muted-foreground">{feedback}</span> : null}
          </div>
        </Panel>
      )}
    </div>
  )
}
