import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch, apiUpload } from '../lib/api'

const DEFAULT_DESCRIPTION =
  'You are a friendly British voice agent on our website Talk to us call. Greet the visitor by first name, learn their company and what they need, and answer from the knowledge base only. Once near the start say briefly: "This call is recorded for quality — privacy details are on voxbulk.com." Say that only once. You already have their mobile from the form: read it back once and ask if it is still correct — do not ask again unless they change it. Keep turns short. If they want a sales callback, ask once if they are happy to be called back on that number about this enquiry; only book if they clearly say yes. Agree callback time in their timezone (UK, Australia, or Canada) when relevant.'

export default function FrontpageCallLeads() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [importingKb, setImportingKb] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [deletingKbId, setDeletingKbId] = useState('')
  const [loadingKbId, setLoadingKbId] = useState('')
  const [msg, setMsg] = useState('')
  const [settings, setSettings] = useState(null)
  const [kbFiles, setKbFiles] = useState([])
  const [voiceProvider, setVoiceProvider] = useState('vapi')
  const [providerAgentId, setProviderAgentId] = useState('')
  const [description, setDescription] = useState(DEFAULT_DESCRIPTION)
  const [systemPrompt, setSystemPrompt] = useState('')
  const [selectedKbIds, setSelectedKbIds] = useState([])
  const [llmProvider, setLlmProvider] = useState('groq')
  const [kbPreview, setKbPreview] = useState(null)
  const [showPromptPreview, setShowPromptPreview] = useState(false)
  const [promptHighlight, setPromptHighlight] = useState(false)
  const systemPromptRef = useRef(null)

  const selectedKb = useMemo(
    () => kbFiles.filter((file) => selectedKbIds.includes(file.id)),
    [kbFiles, selectedKbIds],
  )

  const kbContextChars = settings?.kb_context_chars ?? 0

  const loadSettings = async () => {
    const data = await apiFetch('/admin/frontpage/talk-to-us')
    const s = data?.settings || {}
    const files = data?.kb_files || []
    const allowedIds = new Set(files.map((f) => f.id))
    setSettings(s)
    setVoiceProvider(s.voice_provider || 'vapi')
    setProviderAgentId(s.provider_agent_id || '')
    setDescription(s.prompt_description || DEFAULT_DESCRIPTION)
    setSystemPrompt(s.system_prompt || '')
    setSelectedKbIds((s.kb_file_ids || []).filter((id) => allowedIds.has(id)))
    setLlmProvider(s.llm_provider || 'groq')
    setKbFiles(files)
    if (s.system_prompt) setShowPromptPreview(true)
  }

  const load = async () => {
    setMsg('')
    setLoading(true)
    try {
      await loadSettings()
    } catch (e) {
      const hint = e?.status === 404
        ? ' API route missing — restart FastAPI (uvicorn) after pulling latest code.'
        : ''
      setMsg(`${e?.message || 'Could not load settings'}${hint}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const toggleKb = (fileId) => {
    setSelectedKbIds((prev) => (prev.includes(fileId) ? prev.filter((id) => id !== fileId) : [...prev, fileId]))
  }

  const viewKbFile = async (file) => {
    setLoadingKbId(file.id)
    setMsg('')
    try {
      const data = await apiFetch(`/admin/knowledge-base/${file.id}?scope=lead`)
      const content = String(data?.file?.content || '').trim()
      setKbPreview({
        id: file.id,
        name: file.original_filename,
        content: content || '(File is empty or could not be read.)',
      })
    } catch (e) {
      setMsg(e?.message || 'Could not load knowledge base file')
    } finally {
      setLoadingKbId('')
    }
  }

  const saveSettings = async () => {
    if (!providerAgentId.trim()) {
      setMsg(voiceProvider === 'telnyx' ? 'Enter your Telnyx assistant ID before saving.' : 'Enter your Vapi assistant ID before saving.')
      return
    }
    setSaving(true)
    setMsg('')
    try {
      const result = await apiFetch('/admin/frontpage/talk-to-us/settings', {
        method: 'PUT',
        body: JSON.stringify({
          voice_provider: voiceProvider,
          provider_agent_id: providerAgentId.trim(),
          prompt_description: description,
          system_prompt: systemPrompt,
          kb_file_ids: selectedKbIds,
          llm_provider: llmProvider,
        }),
      })
      setSettings(result?.settings || null)
      if (result?.telnyx_sync_warning) {
        setMsg(`Saved. Talk to us uses your prompt + KB. Telnyx sync warning: ${result.telnyx_sync_warning}`)
      } else if (result?.telnyx_synced) {
        setMsg('Saved. Jode prompt + lead KB synced to Telnyx. Test Talk to us on the website.')
      } else {
        setMsg('Saved. Jode uses lead KB only (Adam has a separate library under Sales setup). Test Talk to us on the site.')
      }
    } catch (e) {
      setMsg(e?.message || 'Could not save settings')
    } finally {
      setSaving(false)
    }
  }

  const importKbPrompt = async () => {
    if (!selectedKbIds.length) {
      setMsg('Tick one or more .md files (e.g. jode_prompt.md), then click Use KB as prompt.')
      return
    }
    setImportingKb(true)
    setMsg('')
    try {
      const result = await apiFetch('/admin/frontpage/talk-to-us/import-kb-prompt', {
        method: 'POST',
        body: JSON.stringify({ kb_file_ids: selectedKbIds }),
      })
      const prompt = String(result?.system_prompt || '').trim()
      if (!prompt) {
        setMsg('Import returned empty. Check the file has content.')
        return
      }
      setSystemPrompt(prompt)
      setShowPromptPreview(true)
      setMsg(
        `Loaded ${result?.kb_files_used?.join(', ') || 'KB'} verbatim into the system prompt (${result?.prompt_chars || prompt.length} chars). Edit if needed, then Save settings to push to Telnyx.`,
      )
    } catch (e) {
      setMsg(e?.message || 'Could not import KB as prompt')
    } finally {
      setImportingKb(false)
    }
  }

  const generatePrompt = async () => {
    const desc = description.trim()
    if (desc.length < 10) {
      setMsg('Add a short description of what the lead agent should do (at least 10 characters).')
      return
    }
    if (!selectedKbIds.length) {
      setMsg('Tick at least one knowledge base file above, then generate — the AI reads those files into the prompt.')
      return
    }
    setGenerating(true)
    setMsg('')
    setPromptHighlight(false)
    try {
      const result = await apiFetch('/admin/frontpage/talk-to-us/generate-prompt', {
        method: 'POST',
        body: JSON.stringify({
          description: desc,
          kb_file_ids: selectedKbIds,
          rewrite: true,
        }),
      })
      if (result?.skipped) {
        setMsg('Generate skipped — a prompt already exists. Edit it below or clear it, then generate again.')
        return
      }
      const prompt = String(result?.system_prompt || '').trim()
      if (!prompt) {
        setMsg('No prompt returned. Check Integrations → DeepSeek API key, then try again.')
        return
      }
      setSystemPrompt(prompt)
      setShowPromptPreview(true)
      setPromptHighlight(true)
      const kbNames = Array.isArray(result?.kb_files_used) ? result.kb_files_used.join(', ') : `${selectedKb.length} file(s)`
      setMsg(
        `Prompt generated (${result?.prompt_chars || prompt.length} chars) using KB: ${kbNames}. Review below, then Save settings.`,
      )
      window.setTimeout(() => {
        systemPromptRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        systemPromptRef.current?.focus()
        setPromptHighlight(false)
      }, 150)
    } catch (e) {
      const detail = e?.data?.detail
      setMsg(typeof detail === 'string' ? detail : e?.message || 'Could not generate prompt')
    } finally {
      setGenerating(false)
    }
  }

  const uploadKb = async (event) => {
    const picked = Array.from(event.target.files || [])
    event.target.value = ''
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
          const uploaded = await apiUpload('/admin/knowledge-base/upload?scope=lead', form)
          const newId = uploaded?.file?.id
          if (newId) newIds.push(newId)
          uploadedNames.push(file.name)
        } catch (e) {
          failed.push(`${file.name}: ${e?.message || 'failed'}`)
        }
      }
      await loadSettings()
      if (newIds.length) {
        setSelectedKbIds((prev) => [...new Set([...prev, ...newIds])])
      }
      if (failed.length && uploadedNames.length) {
        setMsg(`Uploaded ${uploadedNames.length} file(s): ${uploadedNames.join(', ')}. Failed: ${failed.join('; ')}`)
      } else if (failed.length) {
        setMsg(`Upload failed: ${failed.join('; ')}`)
      } else {
        const skipNote = skipped ? ` (${skipped} non-.md skipped)` : ''
        setMsg(
          `Uploaded ${uploadedNames.length} file(s)${skipNote}: ${uploadedNames.join(', ')}. Selected in the table — use Use KB as prompt or Generate with AI.`,
        )
      }
    } finally {
      setUploading(false)
    }
  }

  const deleteKb = async (file) => {
    if (!window.confirm(`Delete "${file.original_filename}"? This removes it from the website lead agent library.`)) return
    setDeletingKbId(file.id)
    setMsg('')
    try {
      const result = await apiFetch(`/admin/knowledge-base/${file.id}`, { method: 'DELETE' })
      setSelectedKbIds((prev) => prev.filter((id) => id !== file.id))
      if (kbPreview?.id === file.id) setKbPreview(null)
      await loadSettings()
      if (result?.telnyx_sync_warning) {
        setMsg(`Deleted ${file.original_filename}. Telnyx resync warning: ${result.telnyx_sync_warning}`)
      } else if (result?.telnyx_synced) {
        setMsg(`Deleted ${file.original_filename}. Jode's Telnyx assistant was resynced without that file.`)
      } else {
        setMsg(`Deleted ${file.original_filename}. KB cache updated.${voiceProvider === 'telnyx' ? ' Save settings if Telnyx did not resync.' : ''}`)
      }
    } catch (e) {
      setMsg(e?.message || 'Delete failed')
    } finally {
      setDeletingKbId('')
    }
  }

  return (
    <>
      <div className='pageTop'>
        <div>
          <h1>Front page call leads</h1>
          <p>Configure Talk to us: Vapi (WebRTC) or Telnyx (WebRTC — STT, LLM, and TTS on Telnyx; only your script is synced from here).</p>
        </div>
        <div className='actions'>
          <Link className='btn soft' to='/marketing/lead-sources'>Lead sources</Link>
          <Link className='btn soft' to='/marketing/lead-sales'>Lead sales</Link>
          <button className='btn soft' type='button' onClick={load} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button>
          <button className='btn primary' type='button' onClick={saveSettings} disabled={saving || loading}>{saving ? 'Saving…' : 'Save settings'}</button>
        </div>
      </div>

      {msg ? (
        <div className={`note ${/not found|failed|unterminated|warning|tick/i.test(msg) ? 'noteWarn' : ''}`} style={{ marginBottom: 16 }}>
          {msg}
        </div>
      ) : null}

      <div className='grid two frontpageConfigureRow'>
        <section className='card'>
          <div className='cardHead'>
            <h3>Voice provider</h3>
            <span className='pill p-cyan'>Configure</span>
          </div>
          <div className='cardBody'>
            <div className='frontpageVoiceRow'>
              <label className='frontpageField'>
                <span className='label'>Provider</span>
                <select className='input' value={voiceProvider} onChange={(e) => setVoiceProvider(e.target.value)}>
                  <option value='vapi'>Vapi (WebRTC)</option>
                  <option value='telnyx'>Telnyx (WebRTC — all voice on Telnyx)</option>
                </select>
              </label>
              <label className='frontpageField frontpageFieldGrow'>
                <span className='label'>{voiceProvider === 'telnyx' ? 'Telnyx assistant ID' : 'Vapi assistant ID'}</span>
                <input
                  className='input'
                  value={providerAgentId}
                  onChange={(e) => setProviderAgentId(e.target.value)}
                  placeholder={voiceProvider === 'telnyx' ? 'assistant-… or UUID' : 'asst_xxxxxxxx'}
                />
              </label>
            </div>
            <p className='muted frontpageVoiceHint'>
              {voiceProvider === 'telnyx'
                ? 'Live calls use the saved system prompt plus ticked lead KB files (Adam’s sales KB is separate). Save settings to sync to Telnyx.'
                : 'Integrations → Vapi: public key required. Each call uses the saved prompt plus lead KB files.'}
            </p>
          </div>
        </section>

        <section className='card'>
          <div className='cardHead'>
            <h3>Jode knowledge base (lead only)</h3>
            <span className='pill p-cyan'>{selectedKb.length} selected · {kbContextChars.toLocaleString()} chars cached</span>
          </div>
          <div className='cardBody'>
            <label className='btn soft' style={{ cursor: 'pointer', marginBottom: 10, display: 'inline-flex' }}>
              {uploading ? 'Uploading…' : 'Upload .md (one or many)'}
              <input type='file' accept='.md,text/markdown' multiple hidden onChange={uploadKb} disabled={uploading} />
            </label>
            <p className='muted' style={{ marginTop: 0, marginBottom: 10 }}>
              Files here are <strong>only for the website lead agent</strong> (Talk to us). Sales agent has its own library under Sales setup.
            </p>
            <p className='muted' style={{ marginTop: 0, marginBottom: 10 }}>
              <strong>Use KB as prompt</strong> copies your .md exactly (e.g. jode_prompt.md). <strong>Generate with AI</strong> writes a new summary and may mix names if several files are ticked (call_flow.md mentions Sarah/Alex). Only tick the files you want in that step.
            </p>
            {!kbFiles.length ? (
              <p className='muted' style={{ margin: 0 }}>No files yet.</p>
            ) : (
              <div className='tableWrap frontpageKbTable'>
                <table className='table'>
                  <thead>
                    <tr>
                      <th style={{ width: 36 }} />
                      <th>File</th>
                      <th style={{ width: 56 }}>KB</th>
                      <th style={{ width: 120 }} />
                    </tr>
                  </thead>
                  <tbody>
                    {kbFiles.map((file) => (
                      <tr key={file.id} className={selectedKbIds.includes(file.id) ? 'isSelected' : ''}>
                        <td>
                          <input
                            type='checkbox'
                            checked={selectedKbIds.includes(file.id)}
                            onChange={() => toggleKb(file.id)}
                            aria-label={`Use ${file.original_filename}`}
                          />
                        </td>
                        <td title={file.original_filename}>{file.original_filename}</td>
                        <td className='muted'>{Math.round((file.size_bytes || 0) / 1024)}</td>
                        <td>
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
              <div style={{ marginTop: 12 }}>
                <div className='actions' style={{ marginBottom: 8 }}>
                  <strong>{kbPreview.name}</strong>
                  <button type='button' className='btn soft' style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => setKbPreview(null)}>
                    Close
                  </button>
                </div>
                <pre className='frontpageKbPreview'>{kbPreview.content}</pre>
              </div>
            ) : null}
          </div>
        </section>
      </div>

      <section className='card frontpagePromptCard' style={{ marginTop: 18 }}>
        <div className='cardHead'>
          <h3>Lead agent prompt</h3>
          <span className='pill p-cyan'>{systemPrompt.length ? `${systemPrompt.length} chars` : 'Empty'}</span>
        </div>
        <div className='cardBody frontpagePromptFull'>
          <p className='muted' style={{ marginTop: 0 }}>
            Calls → <Link to='/marketing/lead-sources'>Lead sources</Link>
          </p>
          <label className='label'>What should the agent do?</label>
          <textarea className='input frontpageDescTextarea' rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
          <div className='actions' style={{ marginTop: 10, flexWrap: 'wrap', gap: 8 }}>
            <button type='button' className='btn primary' onClick={importKbPrompt} disabled={importingKb || loading}>
              {importingKb ? 'Loading…' : 'Use KB as prompt'}
            </button>
            <button type='button' className='btn soft' onClick={generatePrompt} disabled={generating || loading}>
              {generating ? 'Generating…' : 'Generate with AI (rewrite)'}
            </button>
            <button
              type='button'
              className='btn soft'
              disabled={!systemPrompt}
              onClick={() => {
                setShowPromptPreview(true)
                systemPromptRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                systemPromptRef.current?.focus()
              }}
            >
              View prompt
            </button>
          </div>
          <label className='label' style={{ marginTop: 14 }}>System prompt (editable)</label>
          {showPromptPreview && systemPrompt ? (
            <pre className='frontpagePromptPreview' aria-label='Generated prompt preview'>
              {systemPrompt}
            </pre>
          ) : null}
          <div className={`frontpageSystemPromptWindow${promptHighlight ? ' frontpagePromptWindowHighlight' : ''}`}>
            <textarea
              ref={systemPromptRef}
              className='frontpagePromptTextarea'
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={18}
              placeholder='Tick KB files, Generate prompt with AI — text appears here and in the preview above. Then Save settings.'
              spellCheck={false}
            />
          </div>
          {!systemPrompt && !generating ? (
            <p className='muted' style={{ marginTop: 8, marginBottom: 0 }}>
              Tick knowledge base files, click Generate prompt with AI, then Save settings.
            </p>
          ) : null}
        </div>
      </section>
    </>
  )
}
