import React from 'react'
import { ExternalLink } from 'lucide-react'
import SupportDiskShell from '../components/supportDisk/SupportDiskShell'
import KnowledgeBase from '../components/supportDisk/KnowledgeBase'
import { Button } from '../components/supportDisk/Button'
import { apiFetch } from '../lib/api'

const DASHBOARD_FAQ_URL = 'https://dashboard.voxbulk.com/account/support/faq'

export default function SupportFaqDashboard() {
  const surface = 'dashboard'
  const load = async () => {
    const [categories, items] = await Promise.all([
      apiFetch(`/admin/faq/categories?surface=${surface}`),
      apiFetch(`/admin/faq/items?surface=${surface}&limit=200`),
    ])
    return { categories: categories || [], items: items || [] }
  }
  return (
    <SupportDiskShell
      title="FAQ (User dashboard)"
      subtitle="Published on the dashboard surface"
      actions={
        <Button asChild variant="outline" size="sm" className="h-9 gap-1.5 text-xs">
          <a href={DASHBOARD_FAQ_URL} target="_blank" rel="noopener noreferrer">
            <ExternalLink className="size-3.5" />
            Open dashboard FAQ
          </a>
        </Button>
      }
    >
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
