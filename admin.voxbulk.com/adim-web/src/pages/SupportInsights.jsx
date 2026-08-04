import React, { useEffect, useState } from 'react'
import { Clock, Smile, Ticket, Timer } from 'lucide-react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { apiFetch } from '../lib/api'
import SupportDiskShell from '../components/supportDisk/SupportDiskShell'

const axis = { stroke: 'var(--muted-foreground)', fontSize: 11, tickLine: false, axisLine: false }
function Panel({ title, subtitle, children }) { return <section className="rounded-xl border border-border bg-surface p-4 shadow-panel"><h3 className="text-sm font-bold">{title}</h3><p className="mb-3 text-xs text-muted-foreground">{subtitle}</p><div className="h-56"><ResponsiveContainer>{children}</ResponsiveContainer></div></section> }
export default function SupportInsights() {
  const [data, setData] = useState(null), [error, setError] = useState('')
  useEffect(() => { apiFetch('/admin/support/insights').then(setData).catch((e) => setError(e.message)) }, [])
  const kpis = data?.kpis || {}
  const cards = [['Avg. first reply', kpis.avg_first_reply || '—', Timer], ['Avg. resolution', kpis.avg_resolution || '—', Clock], ['Tickets this week', kpis.tickets_this_week ?? '—', Ticket], ['CSAT', kpis.csat || '—', Smile]]
  return <SupportDiskShell title="Insights" subtitle="Support Disk performance and customer satisfaction"><div className="h-full overflow-y-auto p-4 sm:p-6"><div className="mx-auto max-w-6xl space-y-4">{error ? <div className="rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error}</div> : null}<div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{cards.map(([label, value, Icon]) => <div key={label} className="rounded-xl border border-border bg-surface p-4 shadow-panel"><div className="flex items-center gap-2 text-muted-foreground"><Icon className="size-4" /><span className="text-xs">{label}</span></div><p className="mt-2 font-display text-2xl font-extrabold">{value}</p></div>)}</div><div className="grid gap-4 lg:grid-cols-2">
    <Panel title="Ticket volume" subtitle="Created vs resolved"><BarChart data={data?.volume_trend || []}><CartesianGrid vertical={false} stroke="var(--border)" /><XAxis dataKey="day" {...axis} /><YAxis {...axis} /><Tooltip /><Bar dataKey="created" fill="var(--primary)" /><Bar dataKey="resolved" fill="var(--status-resolved)" /></BarChart></Panel>
    <Panel title="Response times" subtitle="First reply and resolution"><LineChart data={data?.response_trend || []}><CartesianGrid vertical={false} stroke="var(--border)" /><XAxis dataKey="period" {...axis} /><YAxis {...axis} /><Tooltip /><Line dataKey="first_reply" stroke="var(--primary)" strokeWidth={2} /><Line dataKey="resolution" stroke="var(--status-pending)" strokeWidth={2} /></LineChart></Panel>
    <Panel title="Customer satisfaction" subtitle="CSAT trend"><AreaChart data={data?.csat_trend || []}><CartesianGrid vertical={false} stroke="var(--border)" /><XAxis dataKey="period" {...axis} /><YAxis {...axis} /><Tooltip /><Area dataKey="csat" stroke="var(--status-resolved)" fill="var(--status-resolved-bg)" /></AreaChart></Panel>
    <section className="rounded-xl border border-border bg-surface p-4 shadow-panel"><h3 className="text-sm font-bold">Agent performance</h3><table className="mt-3 w-full text-sm"><thead><tr className="border-b text-left text-xs text-muted-foreground"><th className="pb-2">Agent</th><th>Resolved</th><th>First reply</th><th>CSAT</th></tr></thead><tbody className="divide-y">{(data?.agents || []).map((a) => <tr key={a.email}><td className="py-2">{a.email}</td><td>{a.resolved}</td><td>{a.first_reply}</td><td>{a.csat}</td></tr>)}</tbody></table></section>
  </div></div></div></SupportDiskShell>
}
