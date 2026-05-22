import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch, apiUpload } from '../lib/api'
import TelnyxPromptPreview from '../components/TelnyxPromptPreview'

const DEFAULT_DESCRIPTION =
  'You are a senior sales closer for VOXBULK. At the very start say once: "This call is recorded for quality — see voxbulk.com for privacy." Then confirm the agreed callback time, reference their website enquiry, understand budget and timeline, handle objections, and secure a demo or clear next step. Keep every turn short.'

export default function LeadSalesSettings() {
  const promptRef = useRef(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [importingKb, setImportingKb] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [msg, setMsg] = useState('')
  const [telnyxAssistantId, setTelnyxAssistantId] = useState('')
  const [description, setDescription] = useState(DEFAULT_DESCRIPTION)
  const [systemPrompt, setSystemPrompt] = useState('')
  const [telnyxGreeting, setTelnyxGreeting] = useState('')
  const [kbFiles, setKbFiles] = useState([])
  const [selectedKbIds, setSelectedKbIds] = useState([])
  const [callingHourStart, setCallingHourStart] = useState(9)
  const [callingHourEnd, setCallingHourEnd] = useState(18)
  const [callingDays, setCallingDays] = useState('1,2,3,4,5')
  const [salesAutomationEnabled, setSalesAutomationEnabled] = useState(true)
  const [salesFollowupDays, setSalesFollowupDays] = useState(7)
  const [salesTemplateSubscriptionId, setSalesTemplateSubscriptionId] = useState('')
  const [salesTemplateSurveyId, setSalesTemplateSurveyId] = useState('')
  const [salesTemplateInterviewId, setSalesTemplateInterviewId] = useState('')
  const [offerTemplates, setOfferTemplates] = useState([])
  const [kbPreview, setKbPreview] = useState(null)
  const [loadingKbId, setLoadingKbId] = useState('')
  const [deletingKbId, setDeletingKbId] = useState('')

  const selectedKb = useMemo(
    () => kbFiles.filter((f) => selectedKbIds.includes(f.id)),
    [kbFiles, selectedKbIds],
  )

  const load = async () => {
    setLoading(true)
    setMsg('')
    try {
      const data = await apiFetch('/admin/frontpage/lead-sales/settings')
      const s = data?.settings || {}
      const files = data?.kb_files || []
      const allowedIds = new Set(files.map((f) => f.id))
      setKbFiles(files)
      setTelnyxAssistantId(s.telnyx_assistant_id || '')
      setDescription(s.prompt_description || DEFAULT_DESCRIPTION)
      setSystemPrompt(s.system_prompt || '')
      setTelnyxGreeting(s.telnyx_greeting || '')
      setSelectedKbIds((s.kb_file_ids || []).filter((id) => allowedIds.has(id)))
      setCallingHourStart(s.calling_hour_start ?? 9)
      setCallingHourEnd(s.calling_hour_end ?? 18)
      setCallingDays(s.calling_days || '1,2,3,4,5')
      setSalesAutomationEnabled(s.sales_automation_enabled !== false)
      setSalesFollowupDays(s.sales_followup_days ?? 7)
      setSalesTemplateSubscriptionId(s.sales_template_subscription_id || '')
      setSalesTemplateSurveyId(s.sales_template_survey_id || '')
      setSalesTemplateInterviewId(s.sales_template_interview_id || '')
    } catch (e) {
      setMsg(e?.message || 'Could not load sales settings')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    ;(async () => {
      try {
        const tplData = await apiFetch('/admin/frontpage/lead-sales/offer-templates')
        setOfferTemplates(Array.isArray(tplData?.templates) ? tplData.templates : [])
      } catch {
        setOfferTemplates([])
      }
    })()
  }, [])

  const toggleKb = (fileId) => {
    setSelectedKbIds((prev) => (prev.includes(fileId) ? prev.filter((id) => id !== fileId) : [...prev, fileId]))
  }

  const uploadKb = async (e) => {
    const picked = Array.from(e.target.files || [])
    e.target.value = ''
    if (!picked.length) return

    const files = picked.filter((f) => f.name.toLowerCase().endsWith('.md'))
    const skipped = picked.length - files.length
    if (!files.length) {
      setMsg('Only .md markdown files are allowed.')
      return
    }

    setUploading(true)
    setMsg('')
    const newIds = []
    const uploadedNames = []
    const failed = []

    try {
      for (const file of files) {
        try {
          const form = new FormData()
          form.append('file', file)
          const uploaded = await apiUpload('/admin/knowledge-base/upload?scope=sales', form)
          const newId = uploaded?.file?.id
          if (newId) newIds.push(newId)
          uploadedNames.push(file.name)
        } catch (err) {
          failed.push(`${file.name}: ${err?.message || 'failed'}`)
        }
      }
      await load()
      if (newIds.length) {
        setSelectedKbIds((prev) => [...new Set([...prev, ...newIds])])
      }
      if (failed.length && uploadedNames.length) {
        setMsg(`Uploaded ${uploadedNames.length} file(s). Failed: ${failed.join('; ')}`)
      } else if (failed.length) {
        setMsg(`Upload failed: ${failed.join('; ')}`)
      } else {
        const skipNote = skipped ? ` (${skipped} non-.md skipped)` : ''
        setMsg(`Uploaded ${uploadedNames.length} file(s)${skipNote}: ${uploadedNames.join(', ')}`)
      }
    } finally {
      setUploading(false)
    }
  }

  const viewKbFile = async (file) => {
    setLoadingKbId(file.id)
    try {
      const data = await apiFetch(`/admin/knowledge-base/${file.id}?scope=sales`)
      setKbPreview({
        id: file.id,
        name: file.original_filename,
        content: String(data?.file?.content || '').trim() || '(empty)',
      })
    } catch (err) {
      setMsg(err?.message || 'Could not load file')
    } finally {
      setLoadingKbId('')
    }
  }

  const deleteKb = async (file) => {
    if (!window.confirm(`Delete "${file.original_filename}"? This removes it from Adam's sales library only.`)) return
    setDeletingKbId(file.id)
    setMsg('')
    try {
      const result = await apiFetch(`/admin/knowledge-base/${file.id}`, { method: 'DELETE' })
      setSelectedKbIds((prev) => prev.filter((id) => id !== file.id))
      if (kbPreview?.id === file.id) setKbPreview(null)
      await load()
      if (result?.telnyx_sync_warning) {
        setMsg(`Deleted ${file.original_filename}. Telnyx resync warning: ${result.telnyx_sync_warning}`)
      } else if (result?.telnyx_synced) {
        setMsg(`Deleted ${file.original_filename}. Adam's Telnyx assistant was resynced without that file. Regenerate per-lead scripts on open tasks if needed.`)
      } else {
        setMsg(`Deleted ${file.original_filename}. KB cache updated. Set Telnyx sales assistant ID and save to enable auto-resync on delete.`)
      }
    } catch (err) {
      setMsg(err?.message || 'Delete failed')
    } finally {
      setDeletingKbId('')
    }
  }

  const importKbPrompt = async () => {
    if (!selectedKbIds.length) {
      setMsg('Select at least one .md file (e.g. adam_prompt.md), then Use KB as prompt.')
      return
    }
    setImportingKb(true)
    setMsg('')
    try {
      const result = await apiFetch('/admin/frontpage/lead-sales/import-kb-prompt', {
        method: 'POST',
        body: JSON.stringify({ kb_file_ids: selectedKbIds }),
      })
      const prompt = String(result?.system_prompt || '').trim()
      if (!prompt) {
        setMsg('Import returned empty.')
        return
      }
      setSystemPrompt(prompt)
      setMsg(
        `Loaded ${(result?.kb_files_used || []).join(', ') || 'KB'} verbatim (${result?.prompt_chars || prompt.length} chars). Save settings when ready.`,
      )
    } catch (err) {
      setMsg(err?.message || 'Import failed')
    } finally {
      setImportingKb(false)
    }
  }

  const generatePrompt = async () => {
    const desc = description.trim()
    if (desc.length < 10) {
      setMsg('Add a description of what the sales agent should do (at least 10 characters).')
      return
    }
    if (!selectedKbIds.length) {
      setMsg('Select at least one knowledge base file, then generate.')
      return
    }
    setGenerating(true)
    setMsg('')
    try {
      const result = await apiFetch('/admin/frontpage/lead-sales/generate-prompt', {
        method: 'POST',
        body: JSON.stringify({
          description: desc,
          kb_file_ids: selectedKbIds,
          rewrite: true,
        }),
      })
      if (result?.skipped) {
        setMsg('Generate skipped — a master script already exists. Edit it below or clear it, then generate again.')
        return
      }
      const prompt = String(result?.system_prompt || '').trim()
      if (!prompt) {
        setMsg('No prompt returned. Check Integrations → DeepSeek.')
        return
      }
      setSystemPrompt(prompt)
      setMsg(
        `Master sales script generated (${result?.prompt_chars || prompt.length} chars) using KB: ${(result?.kb_files_used || []).join(', ') || selectedKb.length + ' file(s)'}. Save settings, then each new lead gets a customised script.`,
      )
      promptRef.current?.scrollIntoView({ behavior: 'smooth' })
    } catch (err) {
      setMsg(err?.message || 'Generate failed')
    } finally {
      setGenerating(false)
    }
  }

  const saveSettings = async () => {
    if (!telnyxAssistantId.trim()) {
      setMsg('Enter Telnyx sales assistant ID before saving.')
      return
    }
    if (!systemPrompt.trim()) {
      setMsg('Generate or paste the master sales script before saving.')
      return
    }
    setSaving(true)
    setMsg('')
    try {
      const result = await apiFetch('/admin/frontpage/lead-sales/settings', {
        method: 'PUT',
        body: JSON.stringify({
          telnyx_assistant_id: telnyxAssistantId.trim(),
          prompt_description: description,
          system_prompt: systemPrompt,
          telnyx_greeting: telnyxGreeting,
          kb_file_ids: selectedKbIds,
          calling_hour_start: Number(callingHourStart),
          calling_hour_end: Number(callingHourEnd),
          calling_days: callingDays,
          sales_automation_enabled: salesAutomationEnabled,
          sales_followup_days: Number(salesFollowupDays) || 7,
          sales_template_subscription_id: salesTemplateSubscriptionId || null,
          sales_template_survey_id: salesTemplateSurveyId || null,
          sales_template_interview_id: salesTemplateInterviewId || null,
        }),
      })
      if (result?.telnyx_sync_warning) {
        setMsg(`Saved. Telnyx resync warning: ${result.telnyx_sync_warning}`)
      } else if (result?.telnyx_synced) {
        setMsg('Saved. Adam master script + sales KB synced to Telnyx.')
      } else {
        setMsg('Sales settings saved. Set Telnyx sales assistant ID to enable auto-resync.')
      }
    } catch (err) {
      setMsg(err?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <p className='muted' style={{ padding: 24 }}>Loading sales setup…</p>
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <Link to='/marketing/lead-sales' className='muted' style={{ fontSize: 13 }}>
            ← Back to lead sales
          </Link>
          <h1 style={{ marginTop: 8 }}>Lead sales setup</h1>
          <p className='muted'>
            Configure the <strong>master sales script</strong> and Telnyx assistant. When a lead requests a callback, the
            system builds a <strong>per-lead prompt</strong> from this script + their intake data, then places the outbound
            call.
          </p>
        </div>
        <div className='actions'>
          <button type='button' className='btn soft' onClick={load}>
            Refresh
          </button>
          <button type='button' className='btn primary' onClick={saveSettings} disabled={saving}>
            {saving ? 'Saving…' : 'Save settings'}
          </button>
        </div>
      </div>

      {msg ? (
        <div className={`note ${/fail|error|enter|generate/i.test(msg) ? 'noteWarn' : ''}`} style={{ marginBottom: 16 }}>
          {msg}
        </div>
      ) : null}

      <section className='card'>
        <div className='cardHead'>
          <h3>Telnyx sales assistant</h3>
        </div>
        <div className='cardBody'>
          <label className='frontpageField'>
            <span className='label'>Assistant ID (separate from website intake)</span>
            <input
              className='input'
              value={telnyxAssistantId}
              onChange={(e) => setTelnyxAssistantId(e.target.value)}
              placeholder='assistant-…'
            />
          </label>
          <div className='grid two' style={{ marginTop: 12, gap: 12 }}>
            <label className='frontpageField'>
              <span className='label'>Calling hours start</span>
              <input className='input' type='number' min={0} max={23} value={callingHourStart} onChange={(e) => setCallingHourStart(e.target.value)} />
            </label>
            <label className='frontpageField'>
              <span className='label'>Calling hours end</span>
              <input className='input' type='number' min={1} max={24} value={callingHourEnd} onChange={(e) => setCallingHourEnd(e.target.value)} />
            </label>
          </div>
          <label className='frontpageField' style={{ marginTop: 12 }}>
            <span className='label'>Calling days (1=Mon … 7=Sun)</span>
            <input className='input' value={callingDays} onChange={(e) => setCallingDays(e.target.value)} />
          </label>
        </div>
      </section>

      <section className='card' style={{ marginTop: 18 }}>
        <div className='cardHead'>
          <h3>WhatsApp sales automation</h3>
          <span className='pill p-cyan'>{salesAutomationEnabled ? 'Enabled' : 'Off'}</span>
        </div>
        <div className='cardBody'>
          <p className='muted' style={{ marginTop: 0 }}>
            After each sales call: interested leads get the offer automatically; others get an opt-in WhatsApp
            (reply <strong>SEND OFFER</strong>). If they do not sign up, a follow-up sends after the delay below.
            DeepSeek replies when they ask for help on WhatsApp.
          </p>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <input
              type='checkbox'
              checked={salesAutomationEnabled}
              onChange={(e) => setSalesAutomationEnabled(e.target.checked)}
            />
            <span><strong>Enable post-call WhatsApp automation</strong></span>
          </label>
          <p className='muted' style={{ marginTop: 0, marginBottom: 12 }}>
            After each call, AI chooses subscription / survey / interview. Map each path to a template below.
            Manage template amounts under <Link to='/marketing/lead-sales/offer-templates'>Offer templates</Link>.
          </p>
          <div className='salesTplMapGrid'>
            {[
              ['subscription', 'When AI picks subscription', salesTemplateSubscriptionId, setSalesTemplateSubscriptionId],
              ['survey', 'When AI picks survey', salesTemplateSurveyId, setSalesTemplateSurveyId],
              ['interview', 'When AI picks interview', salesTemplateInterviewId, setSalesTemplateInterviewId],
            ].map(([cat, label, value, setter]) => (
              <label key={cat} className='frontpageField'>
                <span className='label'>{label}</span>
                <select className='input inputCompact' value={value} onChange={(e) => setter(e.target.value)}>
                  <option value=''>— Select template —</option>
                  {offerTemplates.filter((t) => t.is_active).map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <label className='frontpageField' style={{ marginTop: 14, maxWidth: 220 }}>
            <span className='label'>No-signup follow-up (days)</span>
            <input className='input inputCompact' type='number' min={1} max={30} value={salesFollowupDays} onChange={(e) => setSalesFollowupDays(e.target.value)} />
          </label>
          <p className='muted' style={{ marginBottom: 0 }}>
            Edit message templates under <Link to='/settings/email?tab=whatsapp'>Settings → WhatsApp templates</Link>
            {' '}(<code>sales_opt_in</code>, <code>sales_offer_followup</code>).
          </p>
        </div>
      </section>

      <div className='grid two frontpageConfigureRow' style={{ marginTop: 18 }}>
        <section className='card'>
          <div className='cardHead'>
            <h3>Adam knowledge base (sales only)</h3>
            <span className='pill p-cyan'>{selectedKb.length} selected</span>
          </div>
          <div className='cardBody'>
            <label className='btn soft' style={{ cursor: 'pointer', display: 'inline-flex' }}>
              {uploading ? 'Uploading…' : 'Upload .md (one or many)'}
              <input type='file' accept='.md,text/markdown' multiple hidden onChange={uploadKb} disabled={uploading} />
            </label>
            <p className='muted' style={{ marginTop: 0, marginBottom: 10 }}>
              Files here are <strong>only for Adam (outbound sales)</strong>. Jode (website lead agent) has a separate library under Front page call leads — uploads do not cross over.
            </p>
            {!kbFiles.length ? (
              <p className='muted'>No KB files yet.</p>
            ) : (
              <div className='tableWrap frontpageKbTable' style={{ marginTop: 10 }}>
                <table className='table'>
                  <thead>
                    <tr>
                      <th style={{ width: 36 }} />
                      <th>File</th>
                      <th style={{ width: 148 }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {kbFiles.map((file) => (
                      <tr key={file.id}>
                        <td>
                          <input type='checkbox' checked={selectedKbIds.includes(file.id)} onChange={() => toggleKb(file.id)} />
                        </td>
                        <td className='frontpageKbFilename'>{file.original_filename}</td>
                        <td className='frontpageKbActions'>
                          <div className='actions' style={{ gap: 6 }}>
                            <button
                              type='button'
                              className='btn soft'
                              style={{ padding: '4px 8px', fontSize: 12 }}
                              disabled={loadingKbId === file.id}
                              onClick={() => viewKbFile(file)}
                            >
                              {loadingKbId === file.id ? '…' : 'View'}
                            </button>
                            <button
                              type='button'
                              className='btn soft'
                              style={{ padding: '4px 8px', fontSize: 12 }}
                              disabled={deletingKbId === file.id}
                              onClick={() => deleteKb(file)}
                            >
                              {deletingKbId === file.id ? '…' : 'Delete'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {kbPreview ? (
              <pre className='frontpageKbPreview' style={{ marginTop: 12 }}>
                <strong>{kbPreview.name}</strong>
                {'\n'}
                {kbPreview.content}
              </pre>
            ) : null}
          </div>
        </section>

        <section ref={promptRef} className='card frontpagePromptCard'>
          <div className='cardHead'>
            <h3>Master sales script</h3>
            <span className='pill p-cyan'>{systemPrompt.length ? `${systemPrompt.length} chars` : 'Not set'}</span>
          </div>
          <div className='cardBody frontpagePromptFull'>
            <label className='label'>What should the sales agent do on callbacks?</label>
            <textarea className='input frontpageDescTextarea' rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
            <p className='muted' style={{ marginTop: 8 }}>
              <strong>Use KB as prompt</strong> copies your .md exactly. <strong>Generate with AI</strong> rewrites ticked files — untick call_flow.md / sarah_prompt.md unless you want Sarah/Alex in the script.
            </p>
            <div className='actions' style={{ marginTop: 10, flexWrap: 'wrap', gap: 8 }}>
              <button type='button' className='btn primary' onClick={importKbPrompt} disabled={importingKb}>
                {importingKb ? 'Loading…' : 'Use KB as prompt'}
              </button>
              <button type='button' className='btn soft' onClick={generatePrompt} disabled={generating}>
                {generating ? 'Generating…' : 'Generate with AI (rewrite)'}
              </button>
            </div>
            <label className='label' style={{ marginTop: 14 }}>
              Master script (saved text is used for outbound calls; per-lead scripts are built from this)
            </label>
            <textarea
              className='frontpagePromptTextarea'
              rows={16}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder='Generate master script with AI using KB files above'
            />
            {telnyxAssistantId.trim() ? (
              <>
                <label className='label' style={{ marginTop: 14 }}>
                  Opening greeting (Telnyx — first line Adam speaks)
                </label>
                <textarea
                  className='input frontpageDescTextarea'
                  rows={3}
                  value={telnyxGreeting}
                  onChange={(e) => setTelnyxGreeting(e.target.value)}
                  placeholder='Hi {{first_name}}, this is Adam from VoxBulk following up on your website enquiry. Is now a good time?'
                />
              </>
            ) : null}
            {telnyxAssistantId.trim() ? (
              <TelnyxPromptPreview
                previewUrl='/admin/frontpage/lead-sales/settings/telnyx-preview'
                resyncUrl='/admin/frontpage/lead-sales/settings/resync-telnyx'
                pullGreetingUrl='/admin/frontpage/lead-sales/settings/pull-telnyx-greeting'
                onPullGreeting={(g) => setTelnyxGreeting(g || '')}
                onResyncDone={(result) => {
                  if (result?.telnyx_sync_warning) setMsg(`Telnyx resync warning: ${result.telnyx_sync_warning}`)
                  else if (result?.telnyx_synced) setMsg(`Telnyx synced (${result.synced_instructions_chars || '?'} instruction chars).`)
                }}
              />
            ) : null}
          </div>
        </section>
      </div>

      <section className='card' style={{ marginTop: 18 }}>
        <div className='cardBody'>
          <h3 style={{ marginTop: 0 }}>How it works</h3>
          <ol className='muted' style={{ margin: 0, paddingLeft: 20 }}>
            <li>Visitor completes <Link to='/marketing/frontpage-call-leads'>Talk to us</Link> and requests a sales callback.</li>
            <li>A row appears in <Link to='/marketing/lead-sources'>Lead sources</Link>.</li>
            <li>If assistant ID is set, a task is created in <Link to='/marketing/lead-sales'>Lead sales</Link>.</li>
            <li>DeepSeek writes a <strong>per-lead prompt</strong> from your master script + lead transcript/data.</li>
            <li>Scheduler or <strong>Run</strong> dials via Telnyx at the scheduled time (within calling hours).</li>
          </ol>
        </div>
      </section>
    </>
  )
}
