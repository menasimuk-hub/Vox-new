import React from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Pill } from '@/components/ui/Badge'
import {
  StripeTable,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'

const MOCK_TEMPLATES = [
  { id: '1', name: 'Spring offer', status: 'approved', updated: '2 days ago', tone: 'success' },
  { id: '2', name: 'Refer a friend', status: 'pending', updated: '4 hours ago', tone: 'warning' },
]

export default function CampaignTemplates() {
  return (
    <div className="ds-scope space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Campaigns</p>
          <h1 className="text-[15px] font-semibold leading-tight text-foreground">Template library</h1>
          <p className="text-[11px] leading-tight text-muted-foreground">
            Stub table for broadcast templates. Manage live WhatsApp survey templates via existing admin tools until the
            campaigns API ships.
          </p>
        </div>
        <div className="ml-auto">
          <Button asChild size="sm" variant="outline" className="h-8">
            <Link to="/campaigns">Back to hub</Link>
          </Button>
        </div>
      </div>

      <Panel title="Templates" subtitle="Placeholder rows until the campaigns API is live.">
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Template</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {MOCK_TEMPLATES.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="font-medium">{row.name}</TableCell>
                <TableCell>
                  <Pill tone={row.tone}>{row.status}</Pill>
                </TableCell>
                <TableCell className="text-muted-foreground">{row.updated}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </StripeTable>
        <p className="mt-3 text-[12px] text-muted-foreground">
          Need production templates today? Use{' '}
          <Link
            to="/platform-services/surveys/wa-system-templates"
            className="font-medium text-foreground underline-offset-2 hover:underline"
          >
            WA system templates
          </Link>{' '}
          or organisation survey custom templates.
        </p>
      </Panel>
    </div>
  )
}
