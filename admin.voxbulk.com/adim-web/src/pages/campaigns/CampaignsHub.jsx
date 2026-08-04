import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Building2, CheckCircle2, Megaphone } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { KpiCard } from '@/components/ui/KpiCard'
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

export default function CampaignsHub() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [orgs, setOrgs] = useState([])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await apiFetch('/admin/organisations?limit=500')
        if (cancelled) return
        setOrgs(Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : [])
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load organisations')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const enabledCount = useMemo(
    () => orgs.filter((o) => Boolean(o?.allowed_services?.campaigns || o?.enabled_services?.campaigns)).length,
    [orgs],
  )

  const allowedOrgs = useMemo(
    () => orgs.filter((o) => Boolean(o?.allowed_services?.campaigns)).slice(0, 50),
    [orgs],
  )

  return (
    <div className="ds-scope space-y-4">
      <div className="min-w-0">
        <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Campaigns</p>
        <h1 className="text-[15px] font-semibold leading-tight text-foreground">Broadcast campaigns hub</h1>
        <p className="text-[11px] leading-tight text-muted-foreground">
          Preview module — enable per org under Onboarding → Dashboard modules. Customer API coming soon.
        </p>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <KpiCard icon={Building2} label="Organisations" value={loading ? '…' : orgs.length} index={0} />
        <KpiCard
          icon={CheckCircle2}
          label="Campaigns enabled"
          value={loading ? '…' : enabledCount}
          tone="success"
          index={1}
        />
        <KpiCard icon={Megaphone} label="Status" value="UI scaffold v1" tone="info" index={2} />
      </div>

      <Panel title="Quick links" subtitle="Jump to related admin tools." icon={Megaphone}>
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm" variant="outline" className="h-8">
            <Link to="/onboarding/services">Dashboard modules</Link>
          </Button>
          <Button asChild size="sm" variant="outline" className="h-8">
            <Link to="/campaigns/templates">Template library (stub)</Link>
          </Button>
          <Button asChild size="sm" variant="outline" className="h-8">
            <Link to="/platform-services/surveys/wa-system-templates">WA system templates</Link>
          </Button>
        </div>
      </Panel>

      <Panel
        title="Organisations with campaigns access"
        subtitle="Orgs where Campaigns is allowed in onboarding services."
      >
        <StripeTable>
          <TableHeader>
            <TableRow>
              <TableHead>Organisation</TableHead>
              <TableHead>Allowed</TableHead>
              <TableHead>Visible</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && <TableLoading colSpan={3} />}
            {!loading && allowedOrgs.length === 0 && (
              <TableEmpty colSpan={3}>
                No organisations have broadcast campaigns enabled yet. Turn on Campaigns in onboarding services for a
                pilot customer.
              </TableEmpty>
            )}
            {!loading &&
              allowedOrgs.map((o) => (
                <TableRow key={o.id}>
                  <TableCell>
                    <Link
                      to={`/organisations/${encodeURIComponent(o.id)}`}
                      className="font-medium text-foreground underline-offset-2 hover:underline"
                    >
                      {o.name || o.display_name || o.id}
                    </Link>
                  </TableCell>
                  <TableCell>{o?.allowed_services?.campaigns ? 'Yes' : 'No'}</TableCell>
                  <TableCell>{o?.enabled_services?.campaigns ? 'Yes' : 'No'}</TableCell>
                </TableRow>
              ))}
          </TableBody>
        </StripeTable>
      </Panel>
    </div>
  )
}
