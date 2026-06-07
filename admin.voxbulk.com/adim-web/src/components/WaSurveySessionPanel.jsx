import React from 'react'
import { deliveryOkBadge, waSessionStatusPill } from '../lib/waSurveyOps'

function fmtWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

function DeliveryBlock({ delivery }) {
  if (!delivery || Object.keys(delivery).length === 0) {
    return <div className="muted">No outcome delivery recorded yet.</div>
  }
  const badge = deliveryOkBadge(delivery)
  return (
    <div className="waSurveySessionDelivery">
      <span className={badge.className}>{badge.label}</span>
      <div className="waSurveySessionDeliveryGrid">
        <div><span className="waSurveySessionLabel">Template</span> {delivery.template_name || delivery.template_id || '—'}</div>
        <div><span className="waSurveySessionLabel">Sent</span> {fmtWhen(delivery.sent_at)}</div>
        {delivery.used_text_fallback ? <div className="note">Used text fallback</div> : null}
        {delivery.template_send_failed ? <div className="note">Template send failed</div> : null}
        {delivery.error ? <div className="note">Error: {delivery.error}</div> : null}
      </div>
    </div>
  )
}

async function retryVoiceNote(jobId) {
  const res = await fetch(`/admin/wa-survey/voice-notes/${jobId}/retry`, { method: 'POST', credentials: 'include' })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || body.message || 'Retry failed')
  }
  return res.json()
}

export default function WaSurveySessionPanel({ data, compact = false, onRefresh }) {
  if (!data?.session) return <div className="muted">No WhatsApp survey session for this contact.</div>

  const {
    session,
    answers = [],
    voice_notes: voiceNotes = [],
    decisions = [],
    picker_debug: pickerDebug = [],
    branch_path: branchPath = [],
  } = data
  const delivery = session.outcome_delivery || {}

  return (
    <div className={`waSurveySessionPanel${compact ? ' is-compact' : ''}`}>
      <div className="waSurveySessionHead">
        <div>
          <strong>WA session</strong>
          <div className="muted" style={{ fontSize: '12px' }}>
            {session.id} · {session.flow_mode || 'linear'} · step {session.current_step ?? '—'}
            {session.current_node_key ? ` · ${session.current_node_key}` : ''}
          </div>
        </div>
        <span className={waSessionStatusPill(session.status)}>{session.status || 'unknown'}</span>
      </div>

      <div className="waSurveySessionMetaGrid">
        <div><span className="waSurveySessionLabel">Outcome</span> {session.outcome_key || '—'}</div>
        <div><span className="waSurveySessionLabel">Picker calls</span> {session.picker_invocation_count ?? 0}</div>
        <div><span className="waSurveySessionLabel">Question visits</span> {session.question_visits ?? 0}</div>
        <div><span className="waSurveySessionLabel">Started</span> {fmtWhen(session.started_at)}</div>
        <div><span className="waSurveySessionLabel">Completed</span> {fmtWhen(session.completed_at)}</div>
      </div>

      <div className="waSurveySessionSection">
        <div className="waSurveySessionSectionTitle">Outcome delivery</div>
        <DeliveryBlock delivery={delivery} />
      </div>

      {!compact && voiceNotes.length ? (
        <div className="waSurveySessionSection">
          <div className="waSurveySessionSectionTitle">Voice notes ({voiceNotes.length})</div>
          <div className="tableWrap">
            <table className="table waSurveySessionTable">
              <thead>
                <tr>
                  <th>Step</th>
                  <th>Transcript</th>
                  <th>Source</th>
                  <th>Language</th>
                  <th>Status</th>
                  <th>Audio</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {voiceNotes.map((vn) => (
                  <tr key={vn.id}>
                    <td>{vn.step_index ?? '—'}</td>
                    <td>{vn.answer_text || '—'}</td>
                    <td>{vn.answer_source || 'voice_note'}</td>
                    <td>{vn.detected_language || '—'}</td>
                    <td>{vn.transcription_status || '—'}</td>
                    <td>
                      {vn.audio_file_path && vn.admin_audio_path ? (
                        <a href={vn.admin_audio_path} target="_blank" rel="noreferrer">Download</a>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      {vn.transcription_status === 'failed' ? (
                        <button
                          type="button"
                          className="btn btn-sm"
                          onClick={async () => {
                            try {
                              await retryVoiceNote(vn.id)
                              if (onRefresh) onRefresh()
                            } catch (err) {
                              window.alert(err.message || 'Retry failed')
                            }
                          }}
                        >
                          Retry
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {!compact && branchPath.length ? (
        <div className="waSurveySessionSection">
          <div className="waSurveySessionSectionTitle">Branch path</div>
          <ul className="waSurveySessionList">
            {branchPath.map((b, i) => (
              <li key={`${b.rule_key}-${i}`}>
                <code>{b.rule_key || '—'}</code> → {b.to_role || b.decision_kind}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {!compact && pickerDebug.length ? (
        <div className="waSurveySessionSection">
          <div className="waSurveySessionSectionTitle">AI picker</div>
          <ul className="waSurveySessionList">
            {pickerDebug.map((d) => (
              <li key={d.sequence}>
                {d.decision_kind}: {d.rule_key || '—'} — {d.reason || '—'}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {!compact && answers.length ? (
        <div className="waSurveySessionSection">
          <div className="waSurveySessionSectionTitle">Answers ({answers.length})</div>
          <div className="tableWrap">
            <table className="table waSurveySessionTable">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Role</th>
                  <th>Reply</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {answers.map((a) => (
                  <tr key={a.sequence}>
                    <td>{a.sequence}</td>
                    <td>{a.step_role || a.node_key || '—'}</td>
                    <td>{a.normalized_value || a.raw_value || '—'}</td>
                    <td>{fmtWhen(a.answered_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {!compact && decisions.length && !pickerDebug.length && !branchPath.length ? (
        <div className="waSurveySessionSection">
          <div className="waSurveySessionSectionTitle">Decisions ({decisions.length})</div>
          <ul className="waSurveySessionList">
            {decisions.slice(0, 12).map((d) => (
              <li key={d.sequence}>
                {d.decision_kind}: {d.rule_key || '—'}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
