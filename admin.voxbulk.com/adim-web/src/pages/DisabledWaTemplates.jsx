import React from 'react'
import { Link, Navigate } from 'react-router-dom'
import DisabledWaTemplatesPanel from '../components/DisabledWaTemplatesPanel'

export default function DisabledWaTemplates() {
  return <Navigate to="/ai/wa-templates?tab=disabled" replace />
}

export function DisabledWaTemplatesLegacyPage() {
  return (
    <div>
      <div className="breadcrumb" style={{ padding: '12px 24px 0', fontSize: 13 }}>
        <Link to="/settings/email">Platform Settings</Link>
        <span> / </span>
        <span style={{ fontWeight: 500, color: '#2e2a24' }}>Disabled WA Templates</span>
      </div>
      <DisabledWaTemplatesPanel embedded={false} />
    </div>
  )
}
