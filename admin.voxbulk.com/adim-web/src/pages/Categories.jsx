import React, { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Label } from '@/components/ui/Label'
import { Pill } from '@/components/ui/Badge'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableLoading,
  TableRow,
} from '@/components/ui/Table'

const PATCH_DEBOUNCE_MS = 550

function slugify(s) {
  return String(s || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
}

export default function Categories() {
  const [items, setItems] = useState(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const pendingPatchRef = useRef(new Map())
  const debounceTimersRef = useRef(new Map())

  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [description, setDescription] = useState('')

  const load = async () => {
    setError('')
    try {
      const rows = await apiFetch('/admin/categories')
      setItems(Array.isArray(rows) ? rows : [])
    } catch (e) {
      setItems([])
      setError(e?.message || 'Failed to load categories')
    }
  }

  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    return () => {
      for (const t of debounceTimersRef.current.values()) clearTimeout(t)
      debounceTimersRef.current.clear()
      pendingPatchRef.current.clear()
    }
  }, [])

  async function flushCategoryPatch(categoryId) {
    const timers = debounceTimersRef.current
    const pend = pendingPatchRef.current
    const tid = timers.get(categoryId)
    if (tid) {
      clearTimeout(tid)
      timers.delete(categoryId)
    }
    const payload = pend.get(categoryId)
    pend.delete(categoryId)
    if (!payload || typeof payload !== 'object' || Object.keys(payload).length === 0) return
    setSaving(true)
    setError('')
    try {
      await apiFetch(`/admin/categories/${categoryId}`, { method: 'PATCH', body: JSON.stringify(payload) })
      await load()
    } catch (e) {
      setError(e?.message || 'Save failed')
      await load()
    } finally {
      setSaving(false)
    }
  }

  function scheduleCategoryPatch(categoryId, fragment) {
    const pend = pendingPatchRef.current
    const timers = debounceTimersRef.current
    const prev = pend.get(categoryId) || {}
    pend.set(categoryId, { ...prev, ...fragment })
    const prevT = timers.get(categoryId)
    if (prevT) clearTimeout(prevT)
    const t = setTimeout(() => {
      timers.delete(categoryId)
      const payload = pend.get(categoryId)
      pend.delete(categoryId)
      if (!payload || Object.keys(payload).length === 0) return
      setSaving(true)
      setError('')
      apiFetch(`/admin/categories/${categoryId}`, { method: 'PATCH', body: JSON.stringify(payload) })
        .then(() => load())
        .catch(async (e) => {
          setError(e?.message || 'Save failed')
          await load()
        })
        .finally(() => setSaving(false))
    }, PATCH_DEBOUNCE_MS)
    timers.set(categoryId, t)
  }

  function updateCategoryField(categoryId, field, value) {
    setItems((list) =>
      Array.isArray(list) ? list.map((c) => (c.id === categoryId ? { ...c, [field]: value } : c)) : list
    )
    scheduleCategoryPatch(categoryId, { [field]: value })
  }

  const create = async () => {
    const n = name.trim()
    if (!n) {
      window.alert('Name is required.')
      return
    }
    const s = (slug || slugify(n)).trim()
    if (!s) {
      window.alert('Slug is required.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await apiFetch('/admin/categories', {
        method: 'POST',
        body: JSON.stringify({
          name: n,
          slug: s,
          description: description.trim() ? description.trim() : null,
        }),
      })
      setName('')
      setSlug('')
      setDescription('')
      await load()
    } catch (e) {
      setError(e?.message || 'Create failed')
    } finally {
      setSaving(false)
    }
  }

  const remove = async (id) => {
    if (!window.confirm('Delete this category? Organisations will be unassigned.')) return
    await flushCategoryPatch(id)
    setSaving(true)
    setError('')
    try {
      await apiFetch(`/admin/categories/${id}`, { method: 'DELETE' })
      await load()
    } catch (e) {
      setError(e?.message || 'Delete failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className='ds-scope space-y-4'>
      <div className='pageTop'>
        <div>
          <h1>Categories</h1>
          <p>Create and manage dashboard setup categories. Services API entries connect to these by slug.</p>
        </div>
        <div className='actions'>
          <Button variant='outline' size='sm' className='h-8' onClick={load} disabled={saving}>
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className='rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive'>
          {error}
        </div>
      )}

      <Panel
        title='New category'
        subtitle='Added globally and available to every organisation.'
        action={<Pill tone='info'>Global</Pill>}
      >
        <div className='grid gap-3 sm:grid-cols-2'>
          <div className='space-y-1'>
            <Label htmlFor='cat-new-name' className='text-[12px]'>
              Name
            </Label>
            <Input
              id='cat-new-name'
              className='h-8'
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder='Dental'
            />
          </div>
          <div className='space-y-1'>
            <Label htmlFor='cat-new-slug' className='text-[12px]'>
              Slug
            </Label>
            <Input
              id='cat-new-slug'
              className='h-8 font-mono'
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder='dental'
            />
            <div className='text-[11px] text-muted-foreground'>
              Used internally and by Services API category mapping. Leave blank to auto-generate from name.
            </div>
          </div>
          <div className='space-y-1 sm:col-span-2'>
            <Label htmlFor='cat-new-desc' className='text-[12px]'>
              Description (optional)
            </Label>
            <Textarea
              id='cat-new-desc'
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder='Notes about this category…'
            />
          </div>
        </div>
        <div className='mt-3 flex justify-end'>
          <Button type='button' size='sm' className='h-8' onClick={create} disabled={saving}>
            {saving ? 'Saving…' : 'Create category'}
          </Button>
        </div>
      </Panel>

      <Panel
        title='All categories'
        subtitle='Edits save after a short pause or when you leave a field.'
        action={<Pill tone='info'>{Array.isArray(items) ? `${items.length}` : '—'}</Pill>}
      >
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead className='w-[22%]'>Name</TableHead>
              <TableHead className='w-[20%]'>Slug</TableHead>
              <TableHead>Description</TableHead>
              <TableHead className='w-[15%]'>Created</TableHead>
              <TableHead className='w-[1%] text-right'>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!items && <TableLoading colSpan={5} />}
            {items &&
              items.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>
                    <Input
                      className='h-8'
                      aria-label={`Category name for ${c.slug || c.id}`}
                      value={c.name || ''}
                      onChange={(e) => updateCategoryField(c.id, 'name', e.target.value)}
                      onBlur={() => flushCategoryPatch(c.id)}
                      disabled={saving}
                    />
                  </TableCell>
                  <TableCell>
                    <Input
                      className='h-8 font-mono text-[12px]'
                      aria-label={`Slug for ${c.name || c.id}`}
                      value={c.slug || ''}
                      onChange={(e) => updateCategoryField(c.id, 'slug', e.target.value)}
                      onBlur={() => flushCategoryPatch(c.id)}
                      disabled={saving}
                    />
                  </TableCell>
                  <TableCell>
                    <Textarea
                      rows={2}
                      aria-label={`Description for ${c.name || c.slug}`}
                      value={c.description || ''}
                      onChange={(e) => updateCategoryField(c.id, 'description', e.target.value || null)}
                      onBlur={() => flushCategoryPatch(c.id)}
                      disabled={saving}
                      placeholder='Optional description…'
                    />
                  </TableCell>
                  <TableCell className='whitespace-nowrap text-[11px] text-muted-foreground'>
                    {c.created_at ? new Date(c.created_at).toLocaleString() : '—'}
                  </TableCell>
                  <TableCell className='text-right'>
                    <Button
                      type='button'
                      variant='outline'
                      size='sm'
                      className='h-7'
                      onClick={() => remove(c.id)}
                      disabled={saving}
                    >
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            {items && items.length === 0 && (
              <TableEmpty colSpan={5}>No categories yet.</TableEmpty>
            )}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
