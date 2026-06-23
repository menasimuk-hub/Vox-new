import React from 'react'
import { ResponsiveContainer, BarChart, Bar } from 'recharts'

export default function DashboardKpiSpark({ rows }) {
  return (
    <div className="dashKpiSpark">
      <ResponsiveContainer width="100%" height={32}>
        <BarChart data={rows}>
          <Bar dataKey="v" fill="var(--accent, #0891b2)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
