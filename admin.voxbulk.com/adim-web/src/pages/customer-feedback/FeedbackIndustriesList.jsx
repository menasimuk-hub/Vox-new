import React, { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiFetch } from '../../lib/api'
import { Panel } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
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

export default function FeedbackIndustriesList() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [items, setItems] = useState([])

  const load = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const data = await apiFetch('/admin/customer-feedback/industries')
      setItems(data?.items || [])
    } catch (e) {
      setError(e?.message || 'Could not load industries')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const addIndustry = async () => {
    try {
      const data = await apiFetch('/admin/customer-feedback/industries', {
        method: 'POST',
        body: JSON.stringify({ name: 'New industry', slug: `industry-${Date.now()}`, is_active: true, sort_order: 100 }),
      })
      if (data?.item?.id) navigate(`/customer-feedback/industries/${data.item.id}`)
      else await load()
    } catch (e) {
      setError(e?.message || 'Could not create industry')
    }
  }

  return (
    <div className="ds-scope space-y-4">
      <div className="pageTop">
        <div>
          <h1>Industries</h1>
          <p>Manage feedback industries, survey types and template approval status.</p>
        </div>
        <div className="actions">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8"
            onClick={async () => {
              try {
                await apiFetch('/admin/customer-feedback/templates/import-md', { method: 'POST', body: JSON.stringify({}) })
                setMsg('Templates imported from MD.')
                await load()
              } catch (e) {
                setError(e?.message || 'Import failed')
              }
            }}
          >
            Import English templates
          </Button>
          <Button type="button" size="sm" className="h-8" onClick={addIndustry}>
            Add industry
          </Button>
          <Button type="button" variant="secondary" size="sm" className="h-8" asChild>
            <Link to="/customer-feedback/subscriptions">Hub</Link>
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>
      ) : null}
      {msg ? (
        <div className="rounded-md border border-success/40 bg-success-soft px-3 py-2 text-sm text-success">{msg}</div>
      ) : null}

      <Panel title="Industries" subtitle="Per-industry survey types and template counts.">
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Industry</TableHead>
              <TableHead>Slug</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Survey types</TableHead>
              <TableHead>Templates</TableHead>
              <TableHead>Approved</TableHead>
              <TableHead>Pending</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableLoading colSpan={8} />
            ) : (
              items.map((row) => (
                <TableRow key={row.id}>
                  <TableCell><strong className="font-medium">{row.name}</strong></TableCell>
                  <TableCell><code className="text-[11px]">{row.slug}</code></TableCell>
                  <TableCell><Pill tone={row.is_active ? 'success' : 'neutral'}>{row.is_active ? 'Active' : 'Inactive'}</Pill></TableCell>
                  <TableCell>{row.survey_type_count ?? '—'}</TableCell>
                  <TableCell>{row.template_count ?? '—'}</TableCell>
                  <TableCell>{row.approved_count ?? 0}</TableCell>
                  <TableCell>{row.pending_count ?? 0}</TableCell>
                  <TableCell className="text-right">
                    <Button type="button" variant="outline" size="sm" className="h-7" onClick={() => navigate(`/customer-feedback/industries/${row.id}`)}>
                      Edit
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
            {!loading && !items.length ? <TableEmpty colSpan={8}>No industries yet.</TableEmpty> : null}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
