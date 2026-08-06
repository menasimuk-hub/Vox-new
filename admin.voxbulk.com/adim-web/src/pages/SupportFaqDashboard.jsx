import React, { useRef, useState } from 'react'
import { ExternalLink, Upload } from 'lucide-react'
import SupportDiskShell from '../components/supportDisk/SupportDiskShell'
import KnowledgeBase from '../components/supportDisk/KnowledgeBase'
import { Button } from '../components/supportDisk/Button'
import { apiFetch } from '../lib/api'

const DASHBOARD_FAQ_URL = 'https://dashboard.voxbulk.com/account/support/faq'

export default function SupportFaqDashboard() {
  const surface = 'dashboard'
  const fileRef = useRef(null)
  const [bulkMsg, setBulkMsg] = useState('')
  const [forceOverwrite, setForceOverwrite] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = async () => {
    const [categories, items] = await Promise.all([
      apiFetch(`/admin/faq/categories?surface=${surface}`),
      apiFetch(`/admin/faq/items?surface=${surface}&limit=200`),
    ])
    return { categories: categories || [], items: items || [] }
  }

  const uploadCsv = async (file) => {
    if (!file) return
    setBusy(true)
    setBulkMsg('')
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await apiFetch(`/admin/faq/items/bulk?force=${forceOverwrite ? 'true' : 'false'}`, {
        method: 'POST',
        body: form,
      })
      setBulkMsg(`CSV import: created ${res.created || 0}, updated ${res.updated || 0}, skipped ${res.skipped || 0}`)
    } catch (e) {
      setBulkMsg(e.message || 'CSV import failed')
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <SupportDiskShell
      title="FAQ (User dashboard)"
      subtitle="Published on the dashboard surface · usage stats power Ask AI"
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <input type="checkbox" checked={forceOverwrite} onChange={(e) => setForceOverwrite(e.target.checked)} />
            Force overwrite
          </label>
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => uploadCsv(e.target.files?.[0])}
          />
          <Button
            variant="outline"
            size="sm"
            className="h-9 gap-1.5 text-xs"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
          >
            <Upload className="size-3.5" />
            CSV bulk
          </Button>
          <Button asChild variant="outline" size="sm" className="h-9 gap-1.5 text-xs">
            <a href="/support/ask-ai-insights">Ask AI insights</a>
          </Button>
          <Button asChild variant="outline" size="sm" className="h-9 gap-1.5 text-xs">
            <a href={DASHBOARD_FAQ_URL} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="size-3.5" />
              Open dashboard FAQ
            </a>
          </Button>
        </div>
      }
    >
      {bulkMsg ? <div className="mx-4 mt-3 rounded-lg border border-border bg-surface p-2 text-xs text-muted-foreground sm:mx-6">{bulkMsg}</div> : null}
      <KnowledgeBase
        title="FAQ (User dashboard)"
        kind="faq"
        load={load}
        saveCategory={(x) =>
          apiFetch(x.id ? `/admin/faq/categories/${x.id}` : '/admin/faq/categories', {
            method: x.id ? 'PUT' : 'POST',
            body: { ...x, surface, slug: x.slug || null, sort_order: Number(x.sort_order || 0) },
          })
        }
        saveItem={(x) =>
          apiFetch(x.id ? `/admin/faq/items/${x.id}` : '/admin/faq/items', {
            method: x.id ? 'PUT' : 'POST',
            body: {
              category_id: x.category_id ? Number(x.category_id) : null,
              question: x.title,
              answer: x.body,
              surface,
              is_published: x.state !== 'draft',
              is_featured: false,
              sort_order: Number(x.sort_order || 0),
              linked_service: x.linked_service || null,
              linked_provider: x.linked_provider || null,
            },
          })
        }
        deleteCategory={(id) => apiFetch(`/admin/faq/categories/${id}`, { method: 'DELETE' })}
        deleteItem={(id) => apiFetch(`/admin/faq/items/${id}`, { method: 'DELETE' })}
      />
    </SupportDiskShell>
  )
}
