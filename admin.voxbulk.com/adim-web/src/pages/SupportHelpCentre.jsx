import React from 'react'
import { apiFetch } from '../lib/api'
import SupportDiskShell from '../components/supportDisk/SupportDiskShell'
import KnowledgeBase from '../components/supportDisk/KnowledgeBase'

export default function SupportHelpCentre() {
  const load = async () => {
    const [categories, items] = await Promise.all([apiFetch('/admin/support/kb/categories'), apiFetch('/admin/support/kb/articles')])
    return { categories: categories || [], items: items || [] }
  }
  return <SupportDiskShell title="Help Centre" subtitle="Organise and publish Support Disk articles">
    <KnowledgeBase title="Help Centre" kind="article" load={load}
      saveCategory={(x) => apiFetch(x.id ? `/admin/support/kb/categories/${x.id}` : '/admin/support/kb/categories', { method: x.id ? 'PUT' : 'POST', body: x })}
      saveItem={(x) => apiFetch(x.id ? `/admin/support/kb/articles/${x.id}` : '/admin/support/kb/articles', { method: x.id ? 'PUT' : 'POST', body: { ...x, category_id: Number(x.category_id) } })}
      deleteCategory={(id) => apiFetch(`/admin/support/kb/categories/${id}`, { method: 'DELETE' })}
      deleteItem={(id) => apiFetch(`/admin/support/kb/articles/${id}`, { method: 'DELETE' })} />
  </SupportDiskShell>
}
