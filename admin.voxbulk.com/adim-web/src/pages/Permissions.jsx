import React from 'react'
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

const rows = [
  'Dashboard',
  'Organisations',
  'Onboarding',
  'Operations',
  'AI Marketing',
  'Integrations',
  'Billing & Finance',
  'Support',
  'AI / LLM Control',
  'Compliance',
  'Analytics',
  'Team & Roles',
  'Platform Settings',
  'Impersonation',
]

const data = {
  Superadmin: ['✓', '✓', '✓', '✓', '✓', '✓', '✓', '✓', '✓', '✓', '✓', '✓', '✓', '✓'],
  Accountant: ['View', 'View', '-', '-', '-', 'View', '✓', '-', '-', '-', 'View', '-', '-', '-'],
  Marketing: ['View', 'Limited', '-', '-', '✓', 'View', 'View', '-', '-', '-', 'View', '-', '-', '-'],
  Admin: ['View', '✓', '✓', '✓', '-', 'View', 'View', '✓', 'View', 'View', 'View', '-', '-', '-'],
}

export default function Permissions() {
  return (
    <div className='ds-scope space-y-4'>
      <div className='pageTop'>
        <div>
          <h1>Permissions</h1>
          <p>
            Role matrix for Superadmin, Accountant, Marketing, and Admin across every internal menu area, with
            impersonation restricted to Superadmin only.
          </p>
        </div>
        <div className='actions'>
          <Button variant='outline' size='sm' className='h-8'>
            Export matrix
          </Button>
          <Button variant='secondary' size='sm' className='h-8'>
            Role presets
          </Button>
          <Button size='sm' className='h-8'>
            Edit permissions
          </Button>
        </div>
      </div>

      <Panel
        title='Role access matrix'
        subtitle='Shared admin, role-based visibility'
        action={<Pill tone='info'>Shared admin</Pill>}
        bodyClassName='overflow-x-auto'
      >
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Section</TableHead>
              <TableHead>Superadmin</TableHead>
              <TableHead>Accountant</TableHead>
              <TableHead>Marketing</TableHead>
              <TableHead>Admin</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r, i) => (
              <TableRow key={r}>
                <TableCell>{r}</TableCell>
                <TableCell>
                  <span className='font-medium text-success'>{data.Superadmin[i]}</span>
                </TableCell>
                <TableCell>{data.Accountant[i]}</TableCell>
                <TableCell>{data.Marketing[i]}</TableCell>
                <TableCell>{data.Admin[i]}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
