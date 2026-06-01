import React, { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch, resolveApiUrl } from '../lib/api'
import { readAdminAccessToken, readSharedAccessToken } from '../lib/sessionStorage'
import { downloadAdminCsv } from '../lib/csvDownload'

const TelnyxDualWaveform = lazy(() => import('../components/TelnyxDualWaveform'))

function initials(name, company) {
  const source = String(name || company || '?').trim()
  const parts = source.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return source.slice(0, 2).toUpperCase()
}

function pillClass(kind, value) {
  const map = {
    recommendation: {
      advance: 'leadPill leadPillAdvance',
      hold: 'leadPill leadPillHold',
      decline: 'leadPill leadPillDecline',
    },
    sentiment: {
      enthusiastic: 'leadPill leadPillEnthusiastic',
      neutral: 'leadPill leadPillNeutral',
      hesitant: 'leadPill leadPillHesitant',
    },
  }
  return map[kind]?.[value] || 'leadPill'
}

async function resolveAdminBearerToken() {
  if (typeof window === 'undefined') return ''
  return readAdminAccessToken() || readSharedAccessToken()
}

function formatTime(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return ''
  const total = Math.max(0, Math.floor(Number(seconds)))
  const mins = Math.floor(total / 60)
  const secs = total % 60
  return `${mins}:${String(secs).padStart(2, '0')}`
}

function formatSentAt(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString()
}

function providerLabel(lead) {
  const provider = String(lead?.voice_provider || '').toLowerCase()
  if (provider === 'telnyx') return 'Telnyx'
  if (provider === 'vapi') return 'Vapi'
  return 'provider'
}

function TranscriptThread({ messages, fallbackText, emptyLabel }) {
  if (messages?.length) {
    return (
      <div className='leadChatThread'>
        {messages.map((entry, index) => (
          <div
            key={`${entry.speaker}-${entry.sent_at || entry.seconds_from_start || index}-${index}`}
            className={`leadChatBubble ${entry.speaker === 'Agent' ? 'leadChatBubbleAgent' : 'leadChatBubbleUser'}`}
          >
            <div className='leadChatMeta'>
              <strong>{entry.speaker}</strong>
              {entry.seconds_from_start != null ? <span>{formatTime(entry.seconds_from_start)}</span> : null}
              {entry.seconds_from_start == null && entry.sent_at ? <span>{formatSentAt(entry.sent_at)}</span> : null}
            </div>
            <p>{entry.text}</p>
          </div>
        ))}
      </div>
    )
  }
  if (fallbackText) {
    return <pre className='leadTranscriptPre'>{fallbackText}</pre>
  }
  return (
    <p className='muted'>
      {`No transcript from ${emptyLabel || 'provider'} yet. Wait a minute after the call ends, then open again.`}
    </p>
  )
}

function LeadModal({ title, onClose, children, footer }) {
  return (
    <div className='modalOverlay' role='presentation' onClick={onClose}>
      <div
        className='leadModal'
        role='dialog'
        aria-modal='true'
        aria-labelledby='leadModalTitle'
        onClick={(e) => e.stopPropagation()}
      >
        <div className='leadModalHead'>
          <h3 id='leadModalTitle'>{title}</h3>
          <button type='button' className='btn soft' onClick={onClose} aria-label='Close'>
            ✕
          </button>
        </div>
        <div className='leadModalBody'>{children}</div>
        {footer ? <div className='leadModalFoot'>{footer}</div> : null}
      </div>
    </div>
  )
}

export default function LeadSources() {
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState('')
  const [leads, setLeads] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [modal, setModal] = useState(null)
  const [modalLoading, setModalLoading] = useState(false)
  const [modalError, setModalError] = useState('')
  const [modalLead, setModalLead] = useState(null)
  const [callMedia, setCallMedia] = useState(null)
  const [audioSrc, setAudioSrc] = useState('')
  const [audioLoading, setAudioLoading] = useState(false)
  const [isPlaying, setIsPlaying] = useState(false)
  const audioRef = useRef(null)
  const audioObjectUrlRef = useRef('')
  const telnyxWaveRef = useRef(null)
  const [telnyxRecordingUrl, setTelnyxRecordingUrl] = useState('')
  const [telnyxAuthToken, setTelnyxAuthToken] = useState('')
  const [creatingSalesTask, setCreatingSalesTask] = useState(false)
  const [syncingTelnyxId, setSyncingTelnyxId] = useState('')
  const [filterSales, setFilterSales] = useState('all')
  const [exporting, setExporting] = useState(false)

  const filteredLeads = useMemo(() => {
    if (filterSales === 'sales') {
      return leads.filter((row) => row.wants_sales_call || row.sales_task?.id)
    }
    if (filterSales === 'no_sales') {
      return leads.filter((row) => !row.wants_sales_call && !row.sales_task?.id)
    }
    return leads
  }, [leads, filterSales])

  const selected = useMemo(
    () => leads.find((row) => String(row.id) === String(selectedId)) || null,
    [leads, selectedId],
  )

  const mergeLead = (updated) => {
    if (!updated?.id) return
    setLeads((rows) => rows.map((row) => (String(row.id) === String(updated.id) ? { ...row, ...updated } : row)))
    setModalLead((current) => (current && String(current.id) === String(updated.id) ? { ...current, ...updated } : current))
  }

  const load = async () => {
    setLoading(true)
    setMsg('')
    try {
      const data = await apiFetch('/admin/frontpage/lead-sources')
      const rows = data?.leads || []
      setLeads(rows)
      if (!selectedId && rows[0]?.id) setSelectedId(rows[0].id)
    } catch (e) {
      const hint =
        e?.status === 404
          ? ' API route missing — run uvicorn from voxbulk.com/voxbulk-api (not Retover.ai).'
          : e?.status === 401 || e?.status === 403
            ? ' Sign in again as a platform admin (superadmin, technical, or marketing).'
            : ''
      setMsg(`${e?.message || 'Could not load lead sources'}${hint}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    return () => {
      if (audioObjectUrlRef.current) URL.revokeObjectURL(audioObjectUrlRef.current)
    }
  }, [])

  const fetchLeadMedia = async (leadId) => {
    const data = await apiFetch(`/admin/frontpage/lead-sources/${leadId}`)
    const lead = data?.lead
    const media = data?.vapi || data?.telnyx || null
    if (lead) mergeLead(lead)
    return { lead, media }
  }

  const isVapiLead = (lead) => String(lead?.voice_provider || '').toLowerCase() === 'vapi'
  const isTelnyxLead = (lead) => String(lead?.voice_provider || '').toLowerCase() === 'telnyx'
  const isRemoteMediaLead = (lead) => isVapiLead(lead) || isTelnyxLead(lead)

  const openTranscriptModal = async (lead) => {
    setModal({ type: 'transcript' })
    setModalLead(lead)
    setModalLoading(true)
    setModalError('')
    setCallMedia(null)
    try {
      const { lead: fresh, media } = await fetchLeadMedia(lead.id)
      const current = fresh || lead
      setModalLead(current)
      setCallMedia(media)
      if (
        isRemoteMediaLead(current)
        && media?.error
        && !media?.transcript
        && !(media?.messages || []).length
        && !current?.transcript_text
      ) {
        setModalError(media.error)
      }
    } catch (e) {
      setModalError(e?.message || 'Could not load transcript')
      setModalLead(lead)
    } finally {
      setModalLoading(false)
    }
  }

  const closeModal = () => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }
    if (audioObjectUrlRef.current) {
      URL.revokeObjectURL(audioObjectUrlRef.current)
      audioObjectUrlRef.current = ''
    }
    setAudioSrc('')
    setTelnyxRecordingUrl('')
    setTelnyxAuthToken('')
    setIsPlaying(false)
    setModal(null)
    setModalLead(null)
    setCallMedia(null)
    setModalError('')
    setModalLoading(false)
    setAudioLoading(false)
  }

  const resolveRecordingUrl = async (lead, media) => {
    const token = await resolveAdminBearerToken()

    if (isTelnyxLead(lead)) {
      const playPath =
        String(media?.recording_play_url || '').trim() ||
        `/admin/frontpage/lead-sources/${lead.id}/recording`
      return { url: resolveApiUrl(playPath), fromProvider: false, token, telnyxDual: true }
    }

    if (lead?.recording_url) {
      return { url: resolveApiUrl(lead.recording_url), fromProvider: false, token }
    }

    const direct = String(media?.recording_url || '').trim()
    if (direct.startsWith('http')) {
      return { url: direct, fromProvider: true }
    }
    throw new Error(media?.error || 'No recording available for this call')
  }

  const openAudioModal = async (lead) => {
    setModal({ type: 'audio' })
    setModalLead(lead)
    setModalError('')
    setAudioLoading(true)
    setAudioSrc('')
    setTelnyxRecordingUrl('')
    setTelnyxAuthToken('')
    setIsPlaying(false)
    setCallMedia(null)
    try {
      const { lead: fresh, media } = await fetchLeadMedia(lead.id)
      const current = fresh || lead
      setModalLead(current)
      setCallMedia(media)
      if (media?.error && isTelnyxLead(current) && !media?.recording_play_url) {
        setModalError(media.error)
        return
      }
      const { url, fromProvider, token, telnyxDual } = await resolveRecordingUrl(
        current,
        isRemoteMediaLead(current) ? media : null,
      )
      if (telnyxDual) {
        setTelnyxRecordingUrl(url)
        setTelnyxAuthToken(token || '')
        return
      }
      if (fromProvider) {
        setAudioSrc(url)
      } else {
        const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
        if (!res.ok) throw new Error('Could not load local recording')
        const blob = await res.blob()
        if (audioObjectUrlRef.current) URL.revokeObjectURL(audioObjectUrlRef.current)
        const objectUrl = URL.createObjectURL(blob)
        audioObjectUrlRef.current = objectUrl
        setAudioSrc(objectUrl)
      }
    } catch (e) {
      setModalError(e?.message || 'Playback failed')
    } finally {
      setAudioLoading(false)
    }
  }

  const playAudio = async () => {
    if (isTelnyxLead(modalLead) && telnyxRecordingUrl) {
      try {
        await telnyxWaveRef.current?.play()
        setIsPlaying(true)
      } catch (e) {
        setModalError(e?.message || 'Playback blocked by browser')
      }
      return
    }
    const audio = audioRef.current
    if (!audio || !audioSrc) return
    try {
      await audio.play()
      setIsPlaying(true)
    } catch (e) {
      setModalError(e?.message || 'Playback blocked by browser')
    }
  }

  const pauseAudio = () => {
    if (isTelnyxLead(modalLead) && telnyxRecordingUrl) {
      telnyxWaveRef.current?.pause()
      setIsPlaying(false)
      return
    }
    audioRef.current?.pause()
    setIsPlaying(false)
  }

  const createSalesTask = async (lead) => {
    if (!lead?.id) return
    setCreatingSalesTask(true)
    setMsg('')
    try {
      const data = await apiFetch(`/admin/frontpage/lead-sales/tasks/from-lead/${lead.id}`, { method: 'POST' })
      if (data?.task) mergeLead({ ...lead, sales_task: data.task })
      setMsg(
        data?.already_exists
          ? 'Sales task already exists — open Lead sales to edit.'
          : 'Sales task created — open Lead sales to review the prompt and schedule.',
      )
    } catch (e) {
      setMsg(e?.message || 'Could not create sales task')
    } finally {
      setCreatingSalesTask(false)
    }
  }

  const syncTelnyxLead = async (lead) => {
    if (!lead?.id || !isTelnyxLead(lead)) return
    setSyncingTelnyxId(lead.id)
    setMsg('')
    try {
      const data = await apiFetch(`/admin/frontpage/lead-sources/${lead.id}/sync-telnyx`, { method: 'POST' })
      if (data?.lead) mergeLead(data.lead)
      setMsg('Telnyx transcript and recording synced.')
    } catch (e) {
      setMsg(e?.message || 'Telnyx sync failed')
    } finally {
      setSyncingTelnyxId('')
    }
  }

  const exportCsv = async () => {
    setExporting(true)
    setMsg('')
    try {
      await downloadAdminCsv('/admin/frontpage/lead-sources/export', 'lead-sources.csv')
      setMsg('CSV exported.')
    } catch (e) {
      setMsg(e?.message || 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const stopAudio = () => {
    if (isTelnyxLead(modalLead) && telnyxRecordingUrl) {
      telnyxWaveRef.current?.stop()
      setIsPlaying(false)
      return
    }
    const audio = audioRef.current
    if (!audio) return
    audio.pause()
    audio.currentTime = 0
    setIsPlaying(false)
  }

  return (
    <div className='leadSourcesPage'>
      <div className='pageTop'>
        <div>
          <h1>Lead sources</h1>
          <p className='leadSourcesIntro'>Talk-to-us intake calls — transcript and recording from Vapi or Telnyx.</p>
        </div>
        <div className='actions'>
          <select className='input' style={{ width: 'auto', minWidth: 160 }} value={filterSales} onChange={(e) => setFilterSales(e.target.value)}>
            <option value='all'>All leads</option>
            <option value='sales'>Sales callback</option>
            <option value='no_sales'>No sales callback</option>
          </select>
          <button type='button' className='btn soft' onClick={exportCsv} disabled={exporting || loading}>
            {exporting ? 'Exporting…' : 'Export CSV'}
          </button>
          <button type='button' className='btn soft' onClick={load} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button>
          <Link className='btn soft' to='/marketing/lead-sales'>Lead sales</Link>
        </div>
      </div>

      {msg ? <div className='note' style={{ marginBottom: 16 }}>{msg}</div> : null}

      <section className='card leadSourcesCard'>
        <div className='cardBody' style={{ padding: 0 }}>
          <div className='leadSourcesTableWrap'>
            <table className='leadSourcesTable'>
              <thead>
                <tr>
                  <th className='col-lead'>Lead</th>
                  <th className='col-code'>Code</th>
                  <th className='col-duration'>Time</th>
                  <th className='col-interest'>Interest</th>
                  <th className='col-status'>Status</th>
                  <th className='col-sentiment'>Feel</th>
                  <th className='col-sales'>Sales</th>
                  <th className='col-call'>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredLeads.map((lead) => {
                  const active = String(lead.id) === String(selectedId)
                  const interest = lead.lead_data?.interest_summary || '—'
                  const canOpen = Boolean(lead.provider_call_id || lead.transcript_available || lead.recording_available)
                  return (
                    <tr key={lead.id} className={active ? 'isActive' : ''} onClick={() => setSelectedId(lead.id)}>
                      <td className='col-lead'>
                        <div className='leadIdentity'>
                          <span className='leadAvatar'>{initials(lead.contact_name, lead.company_name)}</span>
                          <span className='leadIdentityText'>
                            <span className='leadName'>{lead.contact_name || 'Unknown'}</span>
                            <span className='muted leadSub'>{lead.company_name || '—'}</span>
                          </span>
                        </div>
                      </td>
                      <td className='col-code'><code className='leadCode'>{lead.lead_code || '—'}</code></td>
                      <td className='col-duration'><span className='leadDuration'>{lead.duration_label || '—'}</span></td>
                      <td className='leadTask col-interest' title={interest}>{interest}</td>
                      <td className='col-status'><span className={pillClass('recommendation', lead.recommendation)}>{lead.recommendation || 'hold'}</span></td>
                      <td className='col-sentiment'><span className={pillClass('sentiment', lead.sentiment)}>{lead.sentiment || 'neutral'}</span></td>
                      <td className='col-sales' onClick={(e) => e.stopPropagation()}>
                        {lead.sales_task?.id ? (
                          <Link
                            className='leadPlayBtn leadPlayBtnLink'
                            to={`/marketing/lead-sales/${lead.sales_task.id}`}
                            title={lead.sales_task.outcome_label || lead.sales_task.status || 'Open sales task'}
                          >
                            {lead.sales_task.outcome_label || lead.sales_task.status || 'Open'}
                          </Link>
                        ) : lead.wants_sales_call ? (
                          <button
                            type='button'
                            className='leadPlayBtn'
                            disabled={creatingSalesTask}
                            onClick={() => createSalesTask(lead)}
                          >
                            + Task
                          </button>
                        ) : (
                          <span className='leadMutedDash'>—</span>
                        )}
                      </td>
                      <td className='col-call'>
                        <div className='leadCallActions' onClick={(e) => e.stopPropagation()}>
                          <button
                            type='button'
                            className='leadPlayBtn'
                            disabled={!canOpen}
                            title='View transcript'
                            onClick={() => openTranscriptModal(lead)}
                          >
                            Text
                          </button>
                          <button
                            type='button'
                            className='leadPlayBtn'
                            disabled={!canOpen}
                            title='Play recording'
                            onClick={() => openAudioModal(lead)}
                          >
                            Play
                          </button>
                          {isTelnyxLead(lead) ? (
                            <button
                              type='button'
                              className='leadPlayBtn leadPlayBtnSync'
                              disabled={syncingTelnyxId === lead.id}
                              title='Sync Telnyx transcript and recording'
                              onClick={() => syncTelnyxLead(lead)}
                            >
                              {syncingTelnyxId === lead.id ? '…' : 'Sync'}
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {!filteredLeads.length && !loading ? (
              <p className='muted' style={{ padding: 24 }}>No completed lead calls yet.</p>
            ) : null}
          </div>
        </div>
      </section>

      {selected ? (
        <section className='card' style={{ marginTop: 18 }}>
          <div className='cardHead'>
            <h3>{selected.lead_code}</h3>
            <span className='pill'>{selected.contact_name}</span>
          </div>
          <div className='cardBody' style={{ display: 'grid', gap: 16 }}>
            <div className='grid two'>
              <div>
                <span className='muted'>Email</span>
                <strong style={{ display: 'block' }}>{selected.email}</strong>
              </div>
              <div>
                <span className='muted'>Phone</span>
                <strong style={{ display: 'block' }}>{selected.phone || '—'}</strong>
              </div>
            </div>
            <div className='actions'>
              <button type='button' className='btn soft' onClick={() => openTranscriptModal(selected)}>View transcript</button>
              <button type='button' className='btn soft' onClick={() => openAudioModal(selected)}>Play recording</button>
              {selected.sales_task?.id ? (
                <Link className='btn soft' to={`/marketing/lead-sales/${selected.sales_task.id}`}>
                  Open sales task
                </Link>
              ) : (
                <button
                  type='button'
                  className='btn soft'
                  disabled={creatingSalesTask || selected.status !== 'completed'}
                  onClick={() => createSalesTask(selected)}
                >
                  {creatingSalesTask ? 'Creating…' : 'Create sales task'}
                </button>
              )}
              {isTelnyxLead(selected) ? (
                <button
                  type='button'
                  className='btn soft'
                  disabled={syncingTelnyxId === selected.id}
                  onClick={() => syncTelnyxLead(selected)}
                >
                  {syncingTelnyxId === selected.id ? 'Syncing…' : 'Sync Telnyx'}
                </button>
              ) : null}
              <Link className='btn soft' to='/marketing/lead-sales'>Lead sales</Link>
            </div>
            <div className='note'>
              <strong>Structured lead data</strong>
              <pre style={{ whiteSpace: 'pre-wrap', margin: '8px 0 0', fontFamily: 'ui-monospace, monospace', fontSize: 13 }}>
                {JSON.stringify(selected.lead_data || {}, null, 2)}
              </pre>
            </div>
          </div>
        </section>
      ) : null}

      {modal?.type === 'transcript' ? (
        <LeadModal title={modalLead ? `Transcript — ${modalLead.lead_code || modalLead.contact_name}` : 'Transcript'} onClose={closeModal}>
          {modalLoading ? (
            <p className='muted'>
              {isRemoteMediaLead(modalLead) ? `Loading transcript from ${providerLabel(modalLead)} API…` : 'Loading transcript…'}
            </p>
          ) : null}
          {modalError ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.35)', marginBottom: 12 }}>{modalError}</div> : null}
          {!modalLoading ? (
            <TranscriptThread
              messages={callMedia?.messages}
              fallbackText={callMedia?.transcript || modalLead?.transcript_text}
              emptyLabel={providerLabel(modalLead)}
            />
          ) : null}
        </LeadModal>
      ) : null}

      {modal?.type === 'audio' ? (
        <LeadModal
          title={modalLead ? `Recording — ${modalLead.lead_code || modalLead.contact_name}` : 'Recording'}
          onClose={closeModal}
          footer={
            <div className='leadAudioControls'>
              <button
                type='button'
                className='btn primary'
                onClick={playAudio}
                disabled={audioLoading || (!audioSrc && !telnyxRecordingUrl)}
              >
                {audioLoading ? 'Loading…' : isPlaying ? 'Playing' : 'Play'}
              </button>
              <button
                type='button'
                className='btn soft'
                onClick={pauseAudio}
                disabled={audioLoading || (!audioSrc && !telnyxRecordingUrl)}
              >
                Pause
              </button>
              <button
                type='button'
                className='btn soft'
                onClick={stopAudio}
                disabled={audioLoading || (!audioSrc && !telnyxRecordingUrl)}
              >
                Stop
              </button>
            </div>
          }
        >
          {modalError ? <div className='note' style={{ borderColor: 'rgba(220,38,38,0.35)', marginBottom: 12 }}>{modalError}</div> : null}
          {audioLoading && !audioSrc && !telnyxRecordingUrl ? (
            <p className='muted'>
              {isRemoteMediaLead(modalLead) ? `Loading recording from ${providerLabel(modalLead)} API…` : 'Loading recording…'}
            </p>
          ) : null}
          {isTelnyxLead(modalLead) && telnyxRecordingUrl ? (
            <>
              <p className='muted' style={{ fontSize: 12, marginBottom: 8 }}>
                Dual-channel recording from Telnyx API — green = user, blue = agent (same as Telnyx portal).
                {callMedia?.user_channel_rms != null ? (
                  <> Both channels verified.</>
                ) : null}
              </p>
              <Suspense fallback={<p className='muted'>Loading waveform…</p>}>
                <TelnyxDualWaveform
                  ref={telnyxWaveRef}
                  src={telnyxRecordingUrl}
                  authToken={telnyxAuthToken}
                  onPlayingChange={setIsPlaying}
                  onError={(message) => setModalError(message)}
                />
              </Suspense>
            </>
          ) : null}
          {!isTelnyxLead(modalLead) && audioSrc ? (
            <>
              <p className='muted' style={{ fontSize: 12, marginBottom: 8 }}>
                {modalLead?.recording_url
                  ? 'Playing local recording from the browser call.'
                  : `Playing from ${providerLabel(modalLead)} (hosted recording).`}
              </p>
              <audio
                ref={audioRef}
                className='leadAudioElement'
                src={audioSrc || undefined}
                controls
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onEnded={() => setIsPlaying(false)}
              />
            </>
          ) : null}
        </LeadModal>
      ) : null}
    </div>
  )
}
