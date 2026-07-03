import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../../lib/api'
import { formatActionSuccess, formatWaSurveyError } from '../../lib/waSurveyFeedback'
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

function statusPill(status) {
  const s = String(status || 'draft').toLowerCase()
  if (['approved', 'synced', 'live'].includes(s)) return <Pill tone="success">Approved</Pill>
  if (s === 'submitted' || s === 'pending') return <Pill tone="warning">Pending</Pill>
  return <Pill tone="neutral">Draft</Pill>
}

export default function FeedbackSystemTemplates() {
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [kinds, setKinds] = useState([])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch('/admin/customer-feedback/system-templates')
      setKinds(Array.isArray(data?.kinds) ? data.kinds : [])
    } catch (e) {
      setError(formatWaSurveyError(e, 'Could not load system templates').message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const pushAll = async () => {
    setWorking('push-all')
    setError('')
    setMsg('')
    try {
      const result = await apiFetch('/admin/customer-feedback/system-templates/push-all', { method: 'POST' })
      setMsg(formatActionSuccess(result, 'Pushed system templates to Meta').message)
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Push to Meta failed').detailText)
    } finally {
      setWorking('')
    }
  }

  const pushOne = async (tpl) => {
    setWorking(`push-${tpl.id}`)
    try {
      const result = await apiFetch(`/admin/customer-feedback/system-templates/${tpl.id}/push`, { method: 'POST' })
      setMsg(formatActionSuccess(result, 'Pushed to Meta').message)
      await load()
    } catch (e) {
      setError(formatWaSurveyError(e, 'Push to Meta failed').detailText)
    } finally {
      setWorking('')
    }
  }

  return (
    <div className="ds-scope pageShell space-y-4">
      <div className="pageTop">
        <div>
          <p className="muted text-[11px] font-semibold uppercase tracking-wide">AI / LLM Control → WA Templates</p>
          <h1>Customer Feedback — system templates</h1>
          <p className="muted">
            Shared thank-you, tell-us-more, opt-in, and share-your-feedback templates used by every feedback industry.
          </p>
        </div>
        <div className="actions flex gap-2">
          <Button type="button" variant="outline" size="sm" className="h-8" asChild>
            <Link to="/ai/wa-templates?tab=feedback">Back to WA Templates hub</Link>
          </Button>
          <Button type="button" size="sm" className="h-8" disabled={working === 'push-all'} onClick={() => void pushAll()}>
            {working === 'push-all' ? 'Pushing…' : 'Push all to Meta'}
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>
      ) : null}
      {msg ? (
        <div className="rounded-md border border-success/40 bg-success-soft px-3 py-2 text-sm text-success">{msg}</div>
      ) : null}

      {loading ? (
        <Panel title="Loading…">
          <TableLoading colSpan={5} />
        </Panel>
      ) : (
        kinds.map((section) => (
          <div key={section.key} id={`cf-system-${section.key}`}>
            <Panel title={section.label} subtitle={`Template key: ${section.key}`}>
            <StripeTable>
              <TableHeader>
                <TableRow>
                  <TableHead>Language</TableHead>
                  <TableHead>Body</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(section.templates || []).map((tpl) => (
                  <TableRow key={tpl.id}>
                    <TableCell>{tpl.language || 'en_GB'}</TableCell>
                    <TableCell className="max-w-md truncate text-muted-foreground">{tpl.body_text || '—'}</TableCell>
                    <TableCell>{statusPill(tpl.telnyx_sync_status)}</TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-7"
                          disabled={!!working}
                          onClick={() => void pushOne(tpl)}
                        >
                          {working === `push-${tpl.id}` ? 'Pushing…' : 'Push to Meta'}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {!section.templates?.length ? (
                  <TableEmpty colSpan={4}>No templates for this kind yet — seed via Customer Feedback import.</TableEmpty>
                ) : null}
              </TableBody>
            </StripeTable>
            </Panel>
          </div>
        ))
      )}
    </div>
  )
}
