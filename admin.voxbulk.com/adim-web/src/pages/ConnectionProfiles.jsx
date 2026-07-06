import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'

const SERVICE_LABELS = {
  ai_interview: 'AI Interview',
  survey: 'Survey',
  customer_feedback: 'Customer feedback',
  booking: 'Booking',
  marketing: 'Marketing',
}

const emptyForm = () => ({
  name: '',
  channel: 'whatsapp',
  provider: 'telnyx',
  is_default: false,
  is_active: true,
  telnyx_messaging_profile_id: '',
  telnyx_number: '',
  telnyx_connection_id: '',
  telnyx_outbound_voice_profile_id: '',
  telnyx_api_key: '',
  meta_waba_id: '',
  meta_phone_number_id: '',
  meta_business_id: '',
  meta_whatsapp_from: '',
  meta_access_token: '',
  meta_app_secret: '',
  meta_webhook_verify_token: '',
  calling_number: '',
  label: '',
  services: {},
  org_ids: [],
})

export default function ConnectionProfiles() {
  const [tab, setTab] = useState('whatsapp')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [profiles, setProfiles] = useState([])
  const [webhookUrls, setWebhookUrls] = useState({})
  const [serviceCodes, setServiceCodes] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [form, setForm] = useState(emptyForm())
  const [testTo, setTestTo] = useState('')

  const channelProfiles = useMemo(
    () => profiles.filter((p) => p.channel === tab),
    [profiles, tab],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch('/admin/connection-profiles')
      setProfiles(Array.isArray(data?.profiles) ? data.profiles : [])
      setWebhookUrls(data?.webhook_urls || {})
      setServiceCodes(Array.isArray(data?.service_codes) ? data.service_codes : [])
    } catch (e) {
      setError(e?.message || 'Failed to load connection profiles')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const first = channelProfiles[0]
    if (!selectedId && first) {
      selectProfile(first)
    } else if (selectedId && !channelProfiles.some((p) => p.id === selectedId)) {
      setSelectedId('')
      setForm(emptyForm())
    }
  }, [channelProfiles, selectedId])

  const selectProfile = (profile) => {
    setSelectedId(profile.id)
    setForm({
      ...emptyForm(),
      ...profile,
      telnyx_api_key: '',
      meta_access_token: '',
      meta_app_secret: '',
      meta_webhook_verify_token: '',
      services: { ...(profile.services || {}) },
      org_ids: [...(profile.org_ids || [])],
    })
    setNotice('')
    setError('')
  }

  const updateField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const toggleService = (code) => {
    setForm((prev) => ({
      ...prev,
      services: { ...(prev.services || {}), [code]: !prev.services?.[code] },
    }))
  }

  const saveProfile = async () => {
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const payload = { ...form, channel: tab }
      const saved = selectedId
        ? await apiFetch(`/admin/connection-profiles/${encodeURIComponent(selectedId)}`, {
            method: 'PUT',
            body: JSON.stringify(payload),
          })
        : await apiFetch('/admin/connection-profiles', {
            method: 'POST',
            body: JSON.stringify(payload),
          })
      setNotice('Profile saved')
      await load()
      if (saved?.id) selectProfile(saved)
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const testProfile = async () => {
    if (!selectedId) return
    setTesting(true)
    setError('')
    setNotice('')
    try {
      const result = await apiFetch(`/admin/connection-profiles/${encodeURIComponent(selectedId)}/test`, {
        method: 'POST',
        body: JSON.stringify({ to_number: testTo || undefined }),
      })
      setNotice(result?.detail || (result?.ok ? 'Test passed' : 'Test failed'))
      await load()
    } catch (e) {
      setError(e?.message || 'Test failed')
    } finally {
      setTesting(false)
    }
  }

  const newProfile = () => {
    setSelectedId('')
    setForm({
      ...emptyForm(),
      channel: tab,
      provider: tab === 'calling' ? 'telnyx' : 'telnyx',
    })
  }

  const webhookUrl = tab === 'whatsapp' ? webhookUrls.telnyx_whatsapp : null

  return (
    <div className='page cp-page'>
      <div className='pageHeader'>
        <div>
          <h1>Connection Profiles</h1>
          <p className='muted'>WhatsApp and calling lines per org — platform API keys stay under Integrations.</p>
        </div>
        <div className='pageHeaderActions'>
          <button type='button' className='btn soft' onClick={load} disabled={loading}>Refresh</button>
          <button type='button' className='btn primary' onClick={newProfile}>New profile</button>
        </div>
      </div>

      {error ? <div className='alert danger'>{error}</div> : null}
      {notice ? <div className='alert success'>{notice}</div> : null}

      <div className='cp-tabs'>
        <button type='button' className={`cp-tab ${tab === 'whatsapp' ? 'active' : ''}`} onClick={() => setTab('whatsapp')}>WhatsApp</button>
        <button type='button' className={`cp-tab ${tab === 'calling' ? 'active' : ''}`} onClick={() => setTab('calling')}>Calling</button>
      </div>

      {webhookUrl ? (
        <div className='card cp-webhook-card'>
          <div className='cardBody'>
            <div className='cp-label'>Telnyx webhook URL (read-only)</div>
            <code>{webhookUrl}</code>
            {webhookUrls.meta_whatsapp ? (
              <>
                <div className='cp-label' style={{ marginTop: 12 }}>Meta webhook URL (read-only)</div>
                <code>{webhookUrls.meta_whatsapp}</code>
              </>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className='cp-layout'>
        <aside className='card cp-list'>
          <div className='cardHeader'>Profiles</div>
          <div className='cardBody cp-list-body'>
            {loading ? <div className='muted'>Loading…</div> : null}
            {!loading && channelProfiles.length === 0 ? <div className='muted'>No profiles yet.</div> : null}
            {channelProfiles.map((p) => (
              <button
                key={p.id}
                type='button'
                className={`cp-list-item ${selectedId === p.id ? 'active' : ''}`}
                onClick={() => selectProfile(p)}
              >
                <strong>{p.name}</strong>
                <span className='muted'>{p.provider}{p.is_default ? ' · default' : ''}</span>
                {p.last_test_status ? <span className='cp-test-badge'>{p.last_test_status}</span> : null}
              </button>
            ))}
          </div>
        </aside>

        <section className='card cp-editor'>
          <div className='cardHeader'>{selectedId ? 'Edit profile' : 'New profile'}</div>
          <div className='cardBody cp-form-grid'>
            <label>
              Name
              <input value={form.name || ''} onChange={(e) => updateField('name', e.target.value)} />
            </label>
            {tab === 'whatsapp' ? (
              <label>
                Provider
                <select value={form.provider || 'telnyx'} onChange={(e) => updateField('provider', e.target.value)}>
                  <option value='telnyx'>Telnyx</option>
                  <option value='meta'>Meta</option>
                </select>
              </label>
            ) : null}
            <label className='cp-check'>
              <input type='checkbox' checked={!!form.is_default} onChange={(e) => updateField('is_default', e.target.checked)} />
              Default profile
            </label>
            <label className='cp-check'>
              <input type='checkbox' checked={!!form.is_active} onChange={(e) => updateField('is_active', e.target.checked)} />
              Active
            </label>

            {(tab === 'whatsapp' && form.provider === 'telnyx') || tab === 'calling' ? (
              <>
                <label>
                  Telnyx API key {form.has_telnyx_api_key ? '(saved — leave blank to keep)' : ''}
                  <input type='password' value={form.telnyx_api_key || ''} onChange={(e) => updateField('telnyx_api_key', e.target.value)} autoComplete='new-password' />
                </label>
                {tab === 'whatsapp' ? (
                  <>
                    <label>
                      WhatsApp number
                      <input value={form.telnyx_number || ''} onChange={(e) => updateField('telnyx_number', e.target.value)} />
                    </label>
                    <label>
                      Messaging profile ID
                      <input value={form.telnyx_messaging_profile_id || ''} onChange={(e) => updateField('telnyx_messaging_profile_id', e.target.value)} />
                    </label>
                  </>
                ) : (
                  <>
                    <label>
                      Calling number
                      <input value={form.calling_number || ''} onChange={(e) => updateField('calling_number', e.target.value)} />
                    </label>
                    <label>
                      Label
                      <input value={form.label || ''} onChange={(e) => updateField('label', e.target.value)} />
                    </label>
                  </>
                )}
                <label>
                  Connection ID
                  <input value={form.telnyx_connection_id || ''} onChange={(e) => updateField('telnyx_connection_id', e.target.value)} />
                </label>
                <label>
                  Outbound voice profile ID
                  <input value={form.telnyx_outbound_voice_profile_id || ''} onChange={(e) => updateField('telnyx_outbound_voice_profile_id', e.target.value)} />
                </label>
              </>
            ) : null}

            {tab === 'whatsapp' && form.provider === 'meta' ? (
              <>
                <label>WABA ID<input value={form.meta_waba_id || ''} onChange={(e) => updateField('meta_waba_id', e.target.value)} /></label>
                <label>Phone number ID<input value={form.meta_phone_number_id || ''} onChange={(e) => updateField('meta_phone_number_id', e.target.value)} /></label>
                <label>Business ID<input value={form.meta_business_id || ''} onChange={(e) => updateField('meta_business_id', e.target.value)} /></label>
                <label>WhatsApp from<input value={form.meta_whatsapp_from || ''} onChange={(e) => updateField('meta_whatsapp_from', e.target.value)} /></label>
                <label>Access token {form.has_meta_access_token ? '(saved)' : ''}<input type='password' value={form.meta_access_token || ''} onChange={(e) => updateField('meta_access_token', e.target.value)} autoComplete='new-password' /></label>
                <label>App secret {form.has_meta_app_secret ? '(saved)' : ''}<input type='password' value={form.meta_app_secret || ''} onChange={(e) => updateField('meta_app_secret', e.target.value)} autoComplete='new-password' /></label>
                <label>Webhook verify token {form.has_meta_webhook_verify_token ? '(saved)' : ''}<input type='password' value={form.meta_webhook_verify_token || ''} onChange={(e) => updateField('meta_webhook_verify_token', e.target.value)} autoComplete='new-password' /></label>
              </>
            ) : null}

            {tab === 'whatsapp' ? (
              <div className='cp-services full'>
                <div className='cp-label'>Enabled services</div>
                <div className='cp-service-grid'>
                  {(serviceCodes.length ? serviceCodes : Object.keys(SERVICE_LABELS)).map((code) => (
                    <label key={code} className='cp-check'>
                      <input type='checkbox' checked={!!form.services?.[code]} onChange={() => toggleService(code)} />
                      {SERVICE_LABELS[code] || code}
                    </label>
                  ))}
                </div>
              </div>
            ) : null}

            {selectedId && form.last_test_at ? (
              <div className='cp-test-result full muted'>
                Last test: {form.last_test_status} — {form.last_test_detail}
              </div>
            ) : null}

            <div className='cp-actions full'>
              <input placeholder='Test to-number (optional)' value={testTo} onChange={(e) => setTestTo(e.target.value)} />
              <button type='button' className='btn soft' disabled={!selectedId || testing} onClick={testProfile}>
                {testing ? 'Testing…' : 'Test connection'}
              </button>
              <button type='button' className='btn primary' disabled={saving} onClick={saveProfile}>
                {saving ? 'Saving…' : 'Save profile'}
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
