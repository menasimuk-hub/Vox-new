import React from 'react'

const invalidInputStyle = { borderColor: 'rgba(220,38,38,0.85)' }

function statusPill(summary) {
  if (!summary) return { cls: 'p-amber', text: 'Loading' }
  if (summary.error) return { cls: 'p-red', text: 'Auth / error' }
  if (!summary.exists) return { cls: 'p-amber', text: 'Not set' }
  if (!summary.is_enabled) return { cls: 'p-amber', text: 'Disabled' }
  if (summary.configured) return { cls: 'p-green', text: 'Configured' }
  return { cls: 'p-amber', text: 'Incomplete' }
}

function copyText(value) {
  const text = String(value || '')
  if (!text) return
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).catch(() => {})
  }
}

function joinMissingFields(x) {
  const arr = Array.isArray(x) ? x : []
  return arr.length ? arr.join(', ') : ''
}

function fmtTime(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return '—'
  }
}

function messageStatusClass(status) {
  const s = String(status || '').toLowerCase()
  if (s.includes('fail') || s.includes('error') || s.includes('undeliver')) return 'p-red'
  if (s === 'delivered' || s === 'read' || s === 'received') return 'p-green'
  if (s === 'queued' || s === 'sent' || s === 'sending') return 'p-amber'
  return 'p-cyan'
}

function waTemplateStatusPill(status) {
  const s = String(status || '').toUpperCase()
  if (s === 'APPROVED') return { cls: 'p-green', label: 'Approved' }
  if (s === 'REJECTED' || s === 'DELETED' || s === 'DISABLED') return { cls: 'p-red', label: s }
  if (s === 'PENDING' || s.includes('PENDING')) return { cls: 'p-amber', label: s }
  return { cls: 'p-cyan', label: s || 'Unknown' }
}

function Field({ label, hint, error, children }) {
  return (
    <div className='telnyxField'>
      <label className='label'>{label}</label>
      {children}
      {error ? <div className='muted telnyxFieldError'>{error}</div> : null}
      {hint ? <div className='muted telnyxFieldHint'>{hint}</div> : null}
    </div>
  )
}

function CopyInput({ label, value, onChange, hint }) {
  return (
    <Field label={label} hint={hint}>
      <div className='telnyxCopyRow'>
        <input className='input' value={String(value || '')} onChange={onChange} />
        <button type='button' className='btn soft' onClick={() => copyText(value)}>
          Copy
        </button>
      </div>
    </Field>
  )
}

export default function TelnyxIntegration({
  activeSummary,
  activeConfig,
  activeDraft,
  activeEnabled,
  telnyxStatus,
  telnyxWebhookUrl,
  telnyxMessagingWebhookUrl,
  telnyxMediaStreamUrl,
  telnyxTestNumber,
  setTelnyxTestNumber,
  telnyxWaTemplateName,
  setTelnyxWaTemplateName,
  telnyxWaTemplateId,
  telnyxWaTemplates,
  telnyxWaSyncBusy,
  onSelectTelnyxWaTemplate,
  syncTelnyxWaTemplates,
  loadTelnyxWaTemplates,
  telnyxWaTemplateLang,
  setTelnyxWaTemplateLang,
  telnyxTestResult,
  telnyxSmsTestResult,
  telnyxZoomTestResult,
  telnyxInboundMessages,
  telnyxMessageDetailBusy,
  fetchTelnyxMessageDetail,
  telnyxActiveCallId,
  telnyxCallBusy,
  telnyxAccountNumbers,
  providerError,
  providerSaving,
  defaultWebhookBase,
  setProviderEnabled,
  setProviderField,
  setProviderDrafts,
  applyTelnyxFromNumber,
  saveIntegrationProvider,
  testTelnyx,
  testTelnyxCall,
  hangupTelnyxCall,
  testTelnyxSms,
  testTelnyxWhatsApp,
  testTelnyxZoom,
  loadTelnyxInboundMessages,
}) {
  const pill = statusPill(activeSummary)

  return (
    <div className='telnyxIntegrationPage'>
      <div className='card telnyxToolbar'>
        <div className='cardBody telnyxToolbarBody'>
          <div className='telnyxToolbarLeft'>
            <label className='telnyxEnableRow'>
              <input type='checkbox' checked={activeEnabled} onChange={(e) => setProviderEnabled('telnyx', e.target.checked)} />
              <span>Enable Telnyx (voice, SMS, WhatsApp)</span>
            </label>
            <span className={`pill ${pill.cls}`}>{pill.text}</span>
            {activeSummary?.missing_fields?.length ? (
              <span className='muted telnyxMissing'>Missing: {joinMissingFields(activeSummary.missing_fields)}</span>
            ) : null}
          </div>
          <div className='actions'>
            <button className='btn primary' onClick={() => saveIntegrationProvider('telnyx')} disabled={providerSaving}>
              {providerSaving ? 'Saving…' : 'Save settings'}
            </button>
            <button className='btn soft' onClick={testTelnyx} disabled={providerSaving || !activeSummary?.exists}>
              Test connection
            </button>
          </div>
        </div>
      </div>

      {providerError ? <div className='note telnyxErrorNote'>{providerError}</div> : null}
      {telnyxTestResult ? <div className='note'>{telnyxTestResult}</div> : null}

      <div className='telnyxGrid3'>
        <div className='card'>
          <div className='cardHead'>
            <h3>Account</h3>
            <span className='pill p-cyan'>API</span>
          </div>
          <div className='cardBody stack'>
            <Field
              label='Telnyx API key'
              error={telnyxStatus.errors.api_key}
              hint='Secret v2 key from Telnyx Portal → API Keys (starts with KEY).'
            >
              <input
                className='input'
                style={telnyxStatus.errors.api_key ? invalidInputStyle : undefined}
                type='password'
                value={String(activeDraft.api_key_draft || '')}
                onChange={(e) =>
                  setProviderDrafts((s) => ({
                    ...s,
                    telnyx: { ...(s.telnyx || {}), api_key_draft: e.target.value },
                  }))
                }
                placeholder={activeSummary?.secret_set?.api_key ? 'Paste new KEY… to replace' : 'KEYxxxxxxxx…'}
              />
            </Field>
            <Field label='Voice connection ID' error={telnyxStatus.errors.connection_id} hint='Call Control application ID (landline / voice calls only).'>
              <input
                className='input'
                style={telnyxStatus.errors.connection_id ? invalidInputStyle : undefined}
                value={String(activeConfig.connection_id || activeConfig.voice_api_application_id || '')}
                onChange={(e) => {
                  setProviderField('telnyx', 'connection_id', e.target.value)
                  setProviderField('telnyx', 'voice_api_application_id', e.target.value)
                }}
                placeholder='Call Control connection ID'
              />
            </Field>
            <Field label='Outbound voice profile ID (optional)'>
              <input
                className='input'
                value={String(activeConfig.outbound_voice_profile_id || '')}
                onChange={(e) => setProviderField('telnyx', 'outbound_voice_profile_id', e.target.value)}
              />
            </Field>
            <Field label='Default messaging org ID (optional)' hint='Org UUID for inbound logs; first org used if blank.'>
              <input
                className='input'
                value={String(activeConfig.messaging_org_id || activeConfig.default_messaging_org_id || '')}
                onChange={(e) => setProviderField('telnyx', 'messaging_org_id', e.target.value)}
              />
            </Field>
          </div>
        </div>

        <div className='card'>
          <div className='cardHead'>
            <h3>Phone numbers</h3>
            <span className='pill p-cyan'>3 separate lines</span>
          </div>
          <div className='cardBody stack'>
            <Field
              label='Voice / outbound calls (landline)'
              error={telnyxStatus.errors.default_outbound_number}
              hint='Telnyx → Call Control only. Used for test call and AI voice outbound.'
            >
              <input
                className='input'
                style={telnyxStatus.errors.default_outbound_number ? invalidInputStyle : undefined}
                value={String(activeConfig.default_outbound_number || activeConfig.from_phone_number || '')}
                onChange={(e) => {
                  setProviderField('telnyx', 'default_outbound_number', e.target.value)
                  setProviderField('telnyx', 'from_phone_number', e.target.value)
                }}
                placeholder='+4420… landline'
              />
            </Field>
            <Field label='SMS number (mobile)' hint='Telnyx → Messaging Profile. Outbound SMS + inbound SMS to this line.'>
              <input
                className='input'
                value={String(activeConfig.sms_from || '')}
                onChange={(e) => setProviderField('telnyx', 'sms_from', e.target.value)}
                placeholder='+447… mobile'
              />
            </Field>
            <Field label='WhatsApp number' hint='Telnyx → WhatsApp / Meta WABA. Can differ from SMS mobile.'>
              <input
                className='input'
                value={String(activeConfig.whatsapp_from || '')}
                onChange={(e) => setProviderField('telnyx', 'whatsapp_from', e.target.value)}
                placeholder='+447… WA line'
              />
            </Field>
            <Field label='SMS messaging profile ID' hint='UUID for the profile that owns your SMS mobile number.'>
              <input
                className='input'
                value={String(activeConfig.messaging_profile_id || '')}
                onChange={(e) => setProviderField('telnyx', 'messaging_profile_id', e.target.value)}
                placeholder='40000000-0000-0000-0000-000000000000'
              />
            </Field>
            <Field label='WhatsApp messaging profile ID (optional)' hint='Only if your WA number uses a different profile than SMS. Leave blank to auto-resolve from the WA number.'>
              <input
                className='input'
                value={String(activeConfig.whatsapp_messaging_profile_id || '')}
                onChange={(e) => setProviderField('telnyx', 'whatsapp_messaging_profile_id', e.target.value)}
                placeholder='Optional — same as SMS if one profile'
              />
            </Field>
            {telnyxAccountNumbers.length ? (
              <div className='note telnyxNumberPick'>
                <strong>Numbers on your Telnyx account</strong>
                <div className='telnyxNumberChips'>
                  {telnyxAccountNumbers.map((num) => (
                    <div key={num} className='telnyxNumberChipRow'>
                      <span className='muted telnyxNumberChipLabel'>{num}</span>
                      <button type='button' className='btn soft' onClick={() => applyTelnyxFromNumber(num, 'voice')}>
                        Voice
                      </button>
                      <button type='button' className='btn soft' onClick={() => applyTelnyxFromNumber(num, 'sms')}>
                        SMS
                      </button>
                      <button type='button' className='btn soft' onClick={() => applyTelnyxFromNumber(num, 'whatsapp')}>
                        WhatsApp
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <div className='card'>
          <div className='cardHead'>
            <h3>Webhooks</h3>
            <span className='pill p-cyan'>Public URLs</span>
          </div>
          <div className='cardBody stack'>
            <Field
              label='Webhook base URL'
              error={telnyxStatus.errors.webhook_base_url}
              hint='Production API host or ngrok https URL (no path). Run: ngrok http 8000'
            >
              <input
                className='input'
                style={telnyxStatus.errors.webhook_base_url ? invalidInputStyle : undefined}
                value={String(activeConfig.webhook_base_url || defaultWebhookBase)}
                onChange={(e) => setProviderField('telnyx', 'webhook_base_url', e.target.value)}
                placeholder='https://your-api-host.com'
              />
            </Field>
            <CopyInput label='Voice webhook (Call Control)' value={telnyxWebhookUrl} onChange={(e) => setProviderField('telnyx', 'voice_webhook_url', e.target.value)} />
            <CopyInput
              label='Messaging webhook (SMS + WhatsApp inbound)'
              value={telnyxMessagingWebhookUrl}
              onChange={(e) => setProviderField('telnyx', 'messaging_webhook_url', e.target.value)}
              hint='Paste into Telnyx Messaging Profile AND Messaging → WhatsApp → WABA webhook settings.'
            />
            <Field label='Status callback URL'>
              <input
                className='input'
                value={String(activeConfig.status_callback_url || `${defaultWebhookBase}/telnyx/webhooks/status`)}
                onChange={(e) => setProviderField('telnyx', 'status_callback_url', e.target.value)}
              />
            </Field>
            <Field label='Verified-number webhook URL'>
              <input
                className='input'
                value={String(activeConfig.verified_number_webhook_url || `${defaultWebhookBase}/telnyx/webhooks/verified-numbers`)}
                onChange={(e) => setProviderField('telnyx', 'verified_number_webhook_url', e.target.value)}
              />
            </Field>
            <Field label='Media stream WebSocket URL' hint={`After save: ${telnyxMediaStreamUrl}`}>
              <input
                className='input'
                value={String(activeConfig.media_stream_url || telnyxMediaStreamUrl)}
                onChange={(e) => setProviderField('telnyx', 'media_stream_url', e.target.value)}
              />
            </Field>
          </div>
        </div>
      </div>

      <div className='telnyxGrid2'>
        <div className='card'>
          <div className='cardHead'>
            <h3>Test outgoing</h3>
            <span className='pill p-cyan'>Your mobile</span>
          </div>
          <div className='cardBody stack'>
            <Field label='Destination number (E.164)' hint='Your personal mobile, e.g. +447700900123'>
              <input className='input' value={telnyxTestNumber} onChange={(e) => setTelnyxTestNumber(e.target.value)} placeholder='+447700900123' />
            </Field>
            <div className='telnyxTestBlock'>
              <div className='telnyxTestBlockTitle'>Voice</div>
              <div className='muted telnyxFieldHint'>Uses landline → your mobile</div>
              <div className='actions telnyxTestActions'>
                <button
                  type='button'
                  className='btn soft'
                  onClick={testTelnyxCall}
                  disabled={providerSaving || telnyxCallBusy || !activeSummary?.exists || !telnyxTestNumber.trim()}
                >
                  {telnyxCallBusy && !telnyxActiveCallId ? 'Calling…' : 'Test call'}
                </button>
                <button
                  type='button'
                  className='btn soft'
                  onClick={hangupTelnyxCall}
                  disabled={providerSaving || telnyxCallBusy || !activeSummary?.exists || !telnyxActiveCallId}
                >
                  Hang up
                </button>
              </div>
              {telnyxActiveCallId ? <div className='muted telnyxFieldHint'>Active call: {telnyxActiveCallId}</div> : null}
            </div>
            <div className='telnyxTestBlock'>
              <div className='telnyxTestBlockTitle'>SMS & WhatsApp</div>
              <div className='muted telnyxFieldHint'>Uses mobile SMS/WA numbers configured above</div>
              <div className='actions telnyxTestActions' style={{ marginBottom: 12 }}>
                <button
                  type='button'
                  className='btn soft'
                  onClick={syncTelnyxWaTemplates}
                  disabled={providerSaving || telnyxWaSyncBusy || !activeSummary?.exists}
                >
                  {telnyxWaSyncBusy ? 'Syncing…' : 'Sync WhatsApp templates'}
                </button>
                <button
                  type='button'
                  className='btn soft'
                  onClick={() => loadTelnyxWaTemplates(false)}
                  disabled={providerSaving || !activeSummary?.exists}
                >
                  Reload templates
                </button>
              </div>
              <div className='muted telnyxFieldHint' style={{ marginBottom: 10 }}>
                Sync pulls live templates from Telnyx and <strong>removes</strong> any cached rows that were deleted in Telnyx or Meta.
                Only <strong>Approved</strong> templates can be used for test sends.
              </div>
              {(telnyxWaTemplates || []).length > 0 ? (
                <div className='telnyxWaTemplateTableWrap' style={{ marginBottom: 14 }}>
                  <table className='table telnyxWaTemplateTable'>
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Language</th>
                        <th>Status</th>
                        <th>Synced</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(telnyxWaTemplates || []).map((t) => {
                        const pill = waTemplateStatusPill(t.status)
                        return (
                          <tr key={t.template_id || t.id || t.name}>
                            <td>
                              <strong>{t.name}</strong>
                              {t.sales_template_key ? (
                                <div className='muted' style={{ fontSize: 11 }}>
                                  sales: {t.sales_template_key}
                                </div>
                              ) : null}
                            </td>
                            <td>{t.language || '—'}</td>
                            <td>
                              <span className={`pill ${pill.cls}`}>{pill.label}</span>
                            </td>
                            <td className='muted' style={{ fontSize: 12 }}>
                              {fmtTime(t.synced_at)}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className='note' style={{ marginBottom: 12 }}>
                  No templates cached yet. Sync to refresh from Telnyx (stale deleted templates are cleared automatically).
                </div>
              )}
              <Field
                label='WhatsApp template (approved only)'
                hint='Pick an approved template for Test WhatsApp — uses template_id from Telnyx.'
              >
                <select
                  className='input'
                  value={telnyxWaTemplateId}
                  onChange={(e) => onSelectTelnyxWaTemplate(e.target.value)}
                >
                  <option value=''>— Select approved template —</option>
                  {(telnyxWaTemplates || [])
                    .filter((t) => String(t.status || '').toUpperCase() === 'APPROVED')
                    .map((t) => (
                      <option key={t.template_id || t.id} value={t.template_id || ''}>
                        {t.name} · {t.language}
                        {t.template_id ? ` · ${String(t.template_id).slice(0, 8)}…` : ''}
                      </option>
                    ))}
                </select>
              </Field>
              <Field
                label='Or template name / UUID (manual)'
                hint='Optional override. Prefer the synced dropdown above.'
              >
                <input
                  className='input'
                  value={telnyxWaTemplateName}
                  onChange={(e) => setTelnyxWaTemplateName(e.target.value)}
                  placeholder='voxbulk_sales_offer or UUID'
                />
              </Field>
              <Field label='Template language' hint='Auto-filled when you pick a synced template (your templates use en_US).'>
                <input
                  className='input'
                  value={telnyxWaTemplateLang}
                  onChange={(e) => setTelnyxWaTemplateLang(e.target.value)}
                  placeholder='en_US'
                />
              </Field>
              <div className='actions telnyxTestActions'>
                <button type='button' className='btn soft' onClick={testTelnyxSms} disabled={providerSaving || !activeSummary?.exists || !telnyxTestNumber.trim()}>
                  Test SMS
                </button>
                <button type='button' className='btn soft' onClick={testTelnyxWhatsApp} disabled={providerSaving || !activeSummary?.exists || !telnyxTestNumber.trim()}>
                  Test WhatsApp
                </button>
              </div>
            </div>
            {telnyxSmsTestResult ? <div className='note'>{telnyxSmsTestResult}</div> : null}
          </div>
        </div>

        <div className='card'>
          <div className='cardHead'>
            <h3>Zoom for AI interviews</h3>
          </div>
          <div className='cardBody'>
            <div className='stack' style={{ gap: 12 }}>
              <p className='muted' style={{ fontSize: 14, marginBottom: 6 }}>
                Test the Zoom connection configured in your Telnyx account. This verifies Zoom is properly set up for creating interview meetings.
              </p>
              <p className='muted' style={{ fontSize: 12, marginBottom: 6 }}>
                After interviews, point Telnyx Zoom webhooks to{' '}
                <code>{String(activeConfig.webhook_base_url || 'https://api.voxbulk.com').replace(/\/+$/, '')}/telnyx/webhooks/zoom</code>{' '}
                (or your API host + <code>/telnyx/webhooks/zoom</code>) so recordings and transcripts sync automatically.
              </p>
              <div className='actions telnyxTestActions'>
                <button type='button' className='btn soft' onClick={testTelnyxZoom} disabled={providerSaving}>
                  Test Zoom Connection
                </button>
              </div>
              {telnyxZoomTestResult ? <div className='note'>{telnyxZoomTestResult}</div> : null}
            </div>
          </div>
        </div>

        <div className='card'>
          <div className='cardHead'>
            <h3>Setup checklist</h3>
            <span className='pill p-cyan'>Telnyx portal</span>
          </div>
          <div className='cardBody'>
            <ol className='telnyxChecklist'>
              <li><strong>Landline</strong> → Call Control → voice webhook URL.</li>
              <li><strong>SMS mobile</strong> → Messaging Profile → messaging webhook URL.</li>
              <li><strong>WhatsApp number</strong> → Meta WABA in Telnyx → same messaging webhook + WABA webhooks.</li>
              <li>Save all three numbers here (they can be different lines).</li>
              <li>Save settings, then <strong>Test connection</strong>.</li>
            </ol>
          </div>
        </div>
      </div>

      <div className='card telnyxInboundCard'>
        <div className='cardHead'>
          <h3>Messages</h3>
          <div className='actions'>
            <button type='button' className='btn soft' onClick={loadTelnyxInboundMessages} disabled={providerSaving || !activeSummary?.exists}>
              Refresh
            </button>
          </div>
        </div>
        <div className='cardBody'>
          {telnyxInboundMessages.length ? (
            <div className='tableWrap'>
              <table className='table telnyxInboundTable'>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Direction</th>
                    <th>From</th>
                    <th>To</th>
                    <th>Message</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {telnyxInboundMessages.map((m) => (
                    <tr key={m.id}>
                      <td className='muted'>{fmtTime(m.created_at)}</td>
                      <td>
                        <span className={`pill ${String(m.direction || '').toLowerCase() === 'outbound' ? 'p-cyan' : 'p-green'}`}>
                          {m.direction || 'inbound'}
                        </span>
                      </td>
                      <td>{m.from_number || '—'}</td>
                      <td>{m.to_number || '—'}</td>
                      <td className='telnyxMessageBody'>
                        {String(m.body || '').trim() || '—'}
                        {m.delivery_error ? (
                          <div className='muted telnyxDeliveryError'>Delivery error: {m.delivery_error}</div>
                        ) : null}
                      </td>
                      <td>
                        <span className={`pill ${messageStatusClass(m.status)}`}>{m.status || 'received'}</span>
                      </td>
                      <td>
                        {m.external_message_id ? (
                          <button
                            type='button'
                            className='btn soft'
                            disabled={providerSaving || telnyxMessageDetailBusy === m.external_message_id}
                            onClick={() => fetchTelnyxMessageDetail(m.external_message_id)}
                          >
                            {telnyxMessageDetailBusy === m.external_message_id ? 'Loading…' : 'Telnyx detail'}
                          </button>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className='note telnyxEmptyInbound'>
              No messages yet. Run <strong>Test WhatsApp</strong> (pick a synced template for first contact), or text your business number from WhatsApp, then <strong>Refresh</strong>.
              Outbound tests appear here immediately; delivery errors update via webhook. Set the messaging webhook URL on both the <strong>Messaging Profile</strong> and <strong>WhatsApp → WABA</strong>.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
