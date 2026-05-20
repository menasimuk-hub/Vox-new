import React from 'react'

/**
 * Template key is stored in DB (template_key) and used by outbound send logic.
 */
export function TemplateDbKeyField({ value, onChange, readOnly = false, isNew = false }) {
  return (
    <div className="templateDbKey">
      <label className="label">
        Database template key
        <span className="muted" style={{ fontWeight: 400, marginLeft: 6 }}>
          — saved in DB, used when sending messages
        </span>
      </label>
      {readOnly ? (
        <div className="templateKeyReadonly">
          <code>{value || '—'}</code>
        </div>
      ) : (
        <input
          className="input templateKeyInput"
          value={value}
          onChange={onChange}
          placeholder="e.g. welcome_email"
          spellCheck={false}
          autoComplete="off"
        />
      )}
      {isNew ? (
        <p className="fieldHint">Lowercase letters, numbers, underscores. Auto-filled from name — edit if needed.</p>
      ) : (
        <p className="fieldHint">This key is permanent after create. Reference it in code: <code>{value}</code></p>
      )}
    </div>
  )
}

export function TemplateMetaGrid({ children, className = '' }) {
  return <div className={`templateMetaGrid ${className}`.trim()}>{children}</div>
}
