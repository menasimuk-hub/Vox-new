import React from 'react'
import { Link } from 'react-router-dom'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from 'recharts'

const n = (value) => Number(value || 0).toLocaleString()

export default function DashboardProductChart({ title, href, total, live, rows, accent }) {
  return (
    <Link to={href} className="dashProductCard dashProductCardLink">
      <div className="dashProductCardHead">
        <strong>{title}</strong>
        <span className="pill p-cyan">{n(live)} live</span>
      </div>
      <span className="dashProductCardSub">{n(total)} total campaigns</span>
      <div className="dashProductChart" style={{ '--dash-accent': accent }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 4, right: 0, left: -22, bottom: 0 }}>
            <XAxis dataKey="n" tick={{ fill: 'var(--t3)', fontSize: 9 }} axisLine={false} tickLine={false} />
            <YAxis hide allowDecimals={false} />
            <Tooltip contentStyle={{ fontSize: 11 }} />
            <Bar dataKey="v" radius={[4, 4, 0, 0]}>
              {rows.map((entry) => (
                <Cell key={entry.n} fill={entry.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Link>
  )
}
