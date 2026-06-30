import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../lib/waSurveyFeedback'
import { resolveTelnyxSyncLabel, telnyxSyncPillClass } from '../lib/waSurveyTelnyxSync'
import WaInterviewTemplateModal from '../components/WaInterviewTemplateModal'
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

function formatWhen(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export default function WaInterviewTemplates() {
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [templates, setTemplates] = useState([])
  const [editId, setEditId] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch('/admin/wa-interview/templates')
      setTemplates(Array.isArray(data?.templates) ? data.templates : [])
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load interview templates').message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const syncAll = async () => {
    setWorking('sync')
    setError('')
    setMsg('')
    try {
      const result = await apiFetch('/admin/wa-interview/sync', { method: 'POST', body: '{}' })
      if (result?.ok === false) {
        throw Object.assign(new Error(result.message || 'Telnyx sync failed'), { data: { detail: result } })
      }
      setMsg(formatActionSuccess(result, 'Synced from Telnyx').message)
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Telnyx sync failed').detailText)
    } finally {
      setWorking('')
    }
  }

  const toggleHidden = async (tpl) => {
    setWorking(`hide-${tpl.id}`)
    try {
      await apiFetch(`/admin/wa-interview/templates/${tpl.id}/set-active`, {
        method: 'POST',
        body: JSON.stringify({ active_for_interview: tpl.active_for_interview === false }),
      })
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not update visibility').message)
    } finally {
      setWorking('')
    }
  }

  const deleteTemplate = async (tpl) => {
    if (!window.confirm(`Delete “${tpl.display_name || tpl.name}”? This removes it from Telnyx when synced.`)) return
    setWorking(`delete-${tpl.id}`)
    try {
      const result = await apiFetch(`/admin/wa-interview/templates/${tpl.id}`, { method: 'DELETE' })
      setMsg(formatActionSuccess(result, 'Template deleted').message)
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not delete template').message)
    } finally {
      setWorking('')
    }
  }

  const pushTemplate = async (tpl) => {
    setWorking(`push-${tpl.id}`)
    try {
      const result = await apiFetch(`/admin/wa-interview/templates/${tpl.id}/push`, { method: 'POST', body: '{}' })
      setMsg(formatActionSuccess(result, 'Synced to Telnyx').message)
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Telnyx push failed').detailText)
    } finally {
      setWorking('')
    }
  }

  return (
    <div className="ds-scope pageShell space-y-4">
      <div className="pageTop">
        <div>
          <p className="muted" style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>Platform Settings</p>
          <h1>WA Interview templates</h1>
          <p className="muted">
            Manage WhatsApp templates used by the AI Interview flow — launch email notice, booking confirmation, cancel, and job closed.
          </p>
        </div>
        <div className="actions">
          <Button type="button" variant="outline" size="sm" className="h-8" asChild>
            <Link to="/settings/email">Email settings</Link>
          </Button>
          <Button type="button" size="sm" className="h-8" disabled={working === 'sync'} onClick={() => void syncAll()}>
            {working === 'sync' ? 'Syncing…' : 'Sync from Telnyx'}
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>
      ) : null}
      {msg ? (
        <div className="rounded-md border border-success/40 bg-success-soft px-3 py-2 text-sm text-success">{msg}</div>
      ) : null}

      <Panel title="Interview templates" subtitle="Launch notice, booking confirmation, cancel, and job-closed messages.">
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Template</TableHead>
              <TableHead>Telnyx name</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Visibility</TableHead>
              <TableHead>Updated</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableLoading colSpan={6} />
            ) : (
              templates.map((tpl) => (
                <TableRow key={tpl.id}>
                  <TableCell>
                    <strong className="font-medium">{tpl.display_name || tpl.name}</strong>
                    <div className="text-[11px] text-muted-foreground">{tpl.description || tpl.sales_template_key}</div>
                  </TableCell>
                  <TableCell><code className="text-[11px]">{tpl.name}</code></TableCell>
                  <TableCell>
                    <span className={telnyxSyncPillClass(resolveTelnyxSyncLabel(tpl))}>
                      {resolveTelnyxSyncLabel(tpl)}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Pill tone={tpl.active_for_interview === false ? 'neutral' : 'success'}>
                      {tpl.active_for_interview === false ? 'Hidden' : 'Active'}
                    </Pill>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-[11px] text-muted-foreground">{formatWhen(tpl.updated_at || tpl.last_pushed_at)}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button type="button" variant="outline" size="sm" className="h-7" onClick={() => setEditId(tpl.id)}>
                        Edit
                      </Button>
                      <Button type="button" variant="outline" size="sm" className="h-7" disabled={!!working} onClick={() => void toggleHidden(tpl)}>
                        {tpl.active_for_interview === false ? 'Show' : 'Hide'}
                      </Button>
                      <Button type="button" variant="outline" size="sm" className="h-7" disabled={!!working} onClick={() => void pushTemplate(tpl)}>
                        Sync
                      </Button>
                      <Button type="button" variant="ghost" size="sm" className="h-7 text-destructive hover:text-destructive" disabled={!!working} onClick={() => void deleteTemplate(tpl)}>
                        Delete
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
            {!loading && !templates.length ? <TableEmpty colSpan={6}>No interview templates yet.</TableEmpty> : null}
          </TableBody>
        </StripeTable>
      </Panel>

      <WaInterviewTemplateModal
        templateId={editId}
        open={Boolean(editId)}
        onClose={() => setEditId(null)}
        onSaved={() => void load()}
      />
    </div>
  )
}
