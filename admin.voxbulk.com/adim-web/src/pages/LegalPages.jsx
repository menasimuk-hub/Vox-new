import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { bundledLegalRows, fetchLegalPagesList } from '../lib/legalPagesApi'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
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

function fmtTime(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return '—'
  }
}

export default function LegalPages() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [offline, setOffline] = useState(false)
  const [rows, setRows] = useState([])

  const load = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const result = await fetchLegalPagesList()
      setRows(result.rows)
      setOffline(Boolean(result.offline))
      if (result.offline) {
        setError(
          'API legal routes are not live yet — showing bundled VoxLegal content. You can still edit each tab; saves go to your browser until the API is deployed.',
        )
      }
    } catch (e) {
      setOffline(true)
      setRows(bundledLegalRows())
      setError(
        `${e?.message || 'Could not load legal pages'}. Showing bundled content — you can edit locally until API deploy: cd voxbulk-api && alembic upgrade head && systemctl restart voxbulk-api`,
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className='ds-scope space-y-4'>
      <div className='pageTop'>
        <div>
          <h1>Legal pages</h1>
          <p>Edit each tab on the unified Legal & policies page. HTML you save here appears on voxbulk.com/legal-policies.</p>
        </div>
      </div>

      {error ? (
        <div
          className={
            offline
              ? 'rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-sm text-warning'
              : 'rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive'
          }
        >
          {error}
        </div>
      ) : null}

      <Panel
        title='Platform legal pages'
        subtitle='Public site tabs for Legal & policies.'
        action={<Pill tone={offline ? 'warning' : 'info'}>{offline ? 'Offline mode' : 'Public site'}</Pill>}
        bodyClassName='overflow-x-auto'
      >
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Page</TableHead>
              <TableHead>Public URL</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Last updated</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableLoading colSpan={5} />
            ) : rows.length === 0 ? (
              <TableEmpty colSpan={5}>No legal pages found.</TableEmpty>
            ) : (
              rows.map((row) => (
                <TableRow key={row.slug}>
                  <TableCell>
                    <div className='flex flex-col leading-tight'>
                      <strong className='font-medium'>{row.title}</strong>
                      <span className='text-[11px] text-muted-foreground'>{row.slug}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <a
                      href={`https://voxbulk.com/legal-policies?tab=${encodeURIComponent(row.slug)}`}
                      target='_blank'
                      rel='noreferrer'
                      className='text-primary hover:underline'
                    >
                      /legal-policies?tab={row.slug}
                    </a>
                  </TableCell>
                  <TableCell>
                    <Pill tone={row.is_published && !offline ? 'success' : 'warning'}>
                      {offline ? 'Bundled / local draft' : row.is_published ? 'Published' : 'Draft'}
                    </Pill>
                  </TableCell>
                  <TableCell className='text-muted-foreground'>{fmtTime(row.updated_at)}</TableCell>
                  <TableCell>
                    <Button
                      type='button'
                      variant='secondary'
                      size='sm'
                      className='h-8'
                      onClick={() => navigate(`/settings/legal/${encodeURIComponent(row.slug)}/edit`)}
                    >
                      Edit
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </StripeTable>
      </Panel>

      <div className='rounded-md border border-border bg-secondary/30 px-3 py-2 text-sm text-muted-foreground'>
        {offline ? (
          <>
            <strong className='text-foreground'>Offline editing:</strong> click Edit, change HTML, press Save — drafts
            stay in this browser. To publish on the live site without the API, update{' '}
            <code>voxbulk.com/frontend/src/data/legalDefaultBodies.json</code> on the server, then rebuild the public
            frontend.
          </>
        ) : (
          <>Paste HTML in the editor (headings, paragraphs, lists, tables). Each slug maps to a tab on the public Legal & policies page.</>
        )}
      </div>
    </div>
  )
}
