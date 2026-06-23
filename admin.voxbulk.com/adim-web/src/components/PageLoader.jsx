import React from 'react'

export default function PageLoader({ label = 'Loading page…' }) {
  return (
    <div className="card" style={{ maxWidth: 520, margin: '32px auto' }}>
      <div className="cardBody muted">{label}</div>
    </div>
  )
}
