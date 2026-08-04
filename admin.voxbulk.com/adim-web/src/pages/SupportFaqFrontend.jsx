import React from 'react'
import { apiFetch } from '../lib/api'
import SupportDiskShell from '../components/supportDisk/SupportDiskShell'
import KnowledgeBase from '../components/supportDisk/KnowledgeBase'

export function SupportFaqPage({ surface, title }) {
  const load = async () => {
    const [categories, items] = await Promise.all([apiFetch(`/admin/faq/categories?surface=${surface}`), apiFetch(`/admin/faq/items?surface=${surface}&limit=200`)])
    return { categories: categories || [], items: items || [] }
  }
  return <SupportDiskShell title={title} subtitle={`Published on the ${surface} surface`}>
    <KnowledgeBase title={title} kind="faq" load={load}
      saveCategory={(x) => apiFetch(x.id ? `/admin/faq/categories/${x.id}` : '/admin/faq/categories', { method: x.id ? 'PUT' : 'POST', body: { ...x, surface, slug: x.slug || null, sort_order: Number(x.sort_order || 0) } })}
      saveItem={(x) => apiFetch(x.id ? `/admin/faq/items/${x.id}` : '/admin/faq/items', { method: x.id ? 'PUT' : 'POST', body: { category_id: x.category_id ? Number(x.category_id) : null, question: x.title, answer: x.body, surface, is_published: x.state !== 'draft', is_featured: false, sort_order: Number(x.sort_order || 0) } })}
      deleteCategory={(id) => apiFetch(`/admin/faq/categories/${id}`, { method: 'DELETE' })}
      deleteItem={(id) => apiFetch(`/admin/faq/items/${id}`, { method: 'DELETE' })} />
  </SupportDiskShell>
}

export default function SupportFaqFrontend() {
  return <SupportFaqPage surface="frontend" title="FAQ (Frontend)" />
}
