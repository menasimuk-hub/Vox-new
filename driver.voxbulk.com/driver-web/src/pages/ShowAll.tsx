import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Truck, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { fetchDemoDrivers } from '@/lib/api'

export default function ShowAll() {
  const [rows, setRows] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const data = await fetchDemoDrivers()
        if (alive) setRows(data.drivers || [])
      } catch (err) {
        if (alive) setError(err.message || 'Could not load demo drivers')
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  return (
    <div className="min-h-screen bg-background px-4 py-8">
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        <div className="flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-primary text-primary-foreground">
            <Truck className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-black">Yallasay Drivers — Demo Directory</h1>
            <p className="text-sm text-muted-foreground">Internal testing only. Password for all accounts: 123456</p>
          </div>
        </div>

        {loading ? <p className="text-sm text-muted-foreground">Loading…</p> : null}
        {error ? (
          <Card className="border-destructive/40">
            <CardContent className="pt-6 text-sm text-destructive">{error}</CardContent>
          </Card>
        ) : null}

        <div className="grid gap-4">
          {rows.map((row) => (
            <Card key={row.id}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <CardTitle className="text-lg">{row.name}</CardTitle>
                    <p className="text-sm text-muted-foreground">{row.login_email}</p>
                  </div>
                  <Badge variant={row.is_available ? 'default' : 'secondary'}>{row.status}</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <p><span className="text-muted-foreground">Phone:</span> {row.phone || '—'}</p>
                <p><span className="text-muted-foreground">Queued offers:</span> {row.queued_orders_count}</p>
                <p><span className="text-muted-foreground">Active deliveries:</span> {row.active_orders_count}</p>
                <Button asChild className="w-full">
                  <Link to={`/login?email=${encodeURIComponent(row.login_email)}`}>
                    Open login <ExternalLink className="ml-2 h-4 w-4" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>

        <Button variant="outline" asChild>
          <Link to="/login">Back to login</Link>
        </Button>
      </div>
    </div>
  )
}
