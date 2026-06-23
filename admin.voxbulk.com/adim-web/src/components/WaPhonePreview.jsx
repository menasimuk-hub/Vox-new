import React from 'react'

export default function WaPhonePreview({ title = 'VoxBulk', body = '', buttons = [], compact = false }) {
  const btnList = (buttons || []).filter((b) => String(b?.text || b || '').trim())
  return (
    <div className={`waTplEd-phone ${compact ? 'waTplEd-phone--compact' : ''}`} aria-hidden="true">
      <div className="waTplEd-phone-notch" />
      <div className="waTplEd-phone-status">
        <div className="waTplEd-p-avatar">V</div>
        <div>
          <div className="waTplEd-p-name">{title}</div>
          <div className="waTplEd-p-online">online</div>
        </div>
      </div>
      <div className="waTplEd-phone-body">
        <div className="waTplEd-wa-bubble">
          <div className="waTplEd-wa-body">{body || 'Template preview'}</div>
          <div className="waTplEd-wa-ftr">WhatsApp · now</div>
        </div>
        {btnList.length ? (
          <div className="waTplEd-wa-btns">
            {btnList.map((b, i) => (
              <div key={i} className="waTplEd-wa-btn">{String(b.text || b).trim()}</div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}
