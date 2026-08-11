import React from 'react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'

/** Canonical Lead Sales list URL (optionally open a task in the shared detail modal). */
export function leadSalesListUrl(taskId) {
  const id = String(taskId || '').trim()
  if (id) return `/marketing/leads/tasks?task=${encodeURIComponent(id)}`
  return '/marketing/leads/tasks'
}

/** Full-page task editor (advanced dial / prompt / recording). */
export function leadSalesEditUrl(taskId) {
  const id = String(taskId || '').trim()
  if (!id) return '/marketing/leads/tasks'
  return `/marketing/lead-sales/${encodeURIComponent(id)}`
}

export const LEAD_PIPELINE_STAGES = [
  {
    id: 'demo',
    label: 'Demos',
    short: 'Qualify / demo',
    to: '/marketing/leads/demos',
    blurb: 'Magic-link AI demos — completed demos create a sales task',
  },
  {
    id: 'inbound',
    label: 'Inbound',
    short: 'Intake',
    to: '/marketing/leads/inbound',
    blurb: 'Talk-to-us website calls — transcript, recording, create sales task',
  },
  {
    id: 'sales',
    label: 'Sales tasks',
    short: 'Sell',
    to: '/marketing/leads/tasks',
    blurb: 'Consent-gated outbound calls — approve, dial, complete',
  },
  {
    id: 'offer',
    label: 'Offers',
    short: 'Offer',
    to: '/marketing/leads/offers',
    blurb: 'Post-call promo offers waiting to send',
  },
]

/**
 * Shared stage strip so Demos / Inbound / Sales / Offers feel like one pipeline.
 * @param {{ active: 'demo' | 'inbound' | 'sales' | 'offer', className?: string }} props
 */
export default function LeadSalesPipelineStrip({ active, className }) {
  const current = LEAD_PIPELINE_STAGES.find((s) => s.id === active) || LEAD_PIPELINE_STAGES[2]

  return (
    <div
      className={cn('leadPipelineStrip', className)}
      style={{
        marginBottom: 16,
        border: '1px solid var(--ds-border)',
        borderRadius: 10,
        background: 'var(--ds-surface-secondary, #f8fafc)',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 0,
          borderBottom: '1px solid var(--ds-border)',
        }}
      >
        {LEAD_PIPELINE_STAGES.map((stage, index) => {
          const isActive = stage.id === active
          return (
            <React.Fragment key={stage.id}>
              {index > 0 ? (
                <span
                  aria-hidden
                  style={{
                    alignSelf: 'center',
                    color: 'var(--ds-text-secondary)',
                    fontSize: 12,
                    padding: '0 2px',
                    opacity: 0.55,
                  }}
                >
                  →
                </span>
              ) : null}
              <Link
                to={stage.to}
                style={{
                  flex: '1 1 120px',
                  minWidth: 110,
                  padding: '10px 14px',
                  textDecoration: 'none',
                  color: isActive ? 'var(--ds-text-primary)' : 'var(--ds-text-secondary)',
                  background: isActive ? 'var(--ds-surface, #fff)' : 'transparent',
                  borderBottom: isActive ? '2px solid var(--ds-primary, #1e6fd9)' : '2px solid transparent',
                  fontWeight: isActive ? 600 : 450,
                  fontSize: 13,
                }}
              >
                <span style={{ display: 'block', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', opacity: 0.7 }}>
                  {index + 1}. {stage.short}
                </span>
                {stage.label}
              </Link>
            </React.Fragment>
          )
        })}
      </div>
      <p
        style={{
          margin: 0,
          padding: '8px 14px',
          fontSize: 12,
          color: 'var(--ds-text-secondary)',
          lineHeight: 1.45,
        }}
      >
        <strong style={{ color: 'var(--ds-text-primary)', fontWeight: 600 }}>{current.label}:</strong>{' '}
        {current.blurb}
      </p>
    </div>
  )
}
