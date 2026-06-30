import React from 'react'
import { ChevronDown, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Textarea } from '@/components/ui/Textarea'
import { Switch } from '@/components/ui/Switch'
import { Pill } from '@/components/ui/Badge'

export const voiceAgentDefaults = {
  voice_label: '',
  voice_type_label: '',
  telnyx_assistant_id: '',
  base_role: '',
  service_survey_role: '',
  service_interview_role: '',
  service_lead_sales_role: '',
  service_appointment_role: '',
  opening_disclosure_template: '',
  retry_policy_notes: '',
  interruption_behavior_notes: '',
  voicemail_behavior: 'leave_message',
  opt_out_policy_notes: '',
  supports_survey: false,
  supports_interview: false,
  supports_lead_sales: false,
  supports_appointment: false,
  is_default_survey: false,
  is_default_interview: false,
  is_default_lead_sales: false,
  is_default_appointment: false,
  disclosure_for_survey: true,
  disclosure_for_interview: true,
  disclosure_for_appointment: true,
  disclosure_mandatory: true,
}

export function serviceBadges(agent) {
  const badges = []
  if (agent.supports_survey) badges.push('Survey')
  if (agent.supports_interview) badges.push('Interview')
  if (agent.supports_lead_sales) badges.push('Lead/Sales')
  if (agent.supports_appointment) badges.push('Appointments')
  if (agent.is_default_survey) badges.push('Default survey')
  if (agent.is_default_interview) badges.push('Default interview')
  if (agent.is_default_appointment) badges.push('Default appointments')
  return badges
}

export function PlatformVoiceSettings({ settings, onChange, onSave, busy }) {
  const [open, setOpen] = React.useState(false)
  if (!settings) return null
  return (
    <div className='ds-scope'>
      <section className='rounded-lg border border-border bg-card text-card-foreground shadow-[0_1px_0_rgba(0,0,0,0.02)]'>
        <button
          type='button'
          onClick={() => setOpen((v) => !v)}
          className='flex w-full items-center gap-2 px-3 py-2 text-left'
        >
          <ShieldCheck size={14} className='text-info' />
          <span className='text-[13px] font-semibold tracking-tight'>Shared voice compliance</span>
          <Pill tone='info'>Survey + Interview</Pill>
          <ChevronDown
            size={15}
            className={`ml-auto text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`}
          />
        </button>
        {open ? (
          <div className='border-t border-border p-3'>
            <div className='grid gap-3 sm:grid-cols-2'>
              <Textarea
                rows={2}
                className='text-[12px]'
                value={settings.global_compliance_role || ''}
                onChange={(e) => onChange({ ...settings, global_compliance_role: e.target.value })}
                placeholder='Global compliance / disclosure role: AI disclosure, recording notice, opt-out…'
              />
              <Textarea
                rows={2}
                className='text-[12px]'
                value={settings.opening_disclosure_template || ''}
                onChange={(e) => onChange({ ...settings, opening_disclosure_template: e.target.value })}
                placeholder='Default opening disclosure: Hello, this is {agent_name} from {company_name}…'
              />
            </div>
            <div className='mt-2.5 flex flex-wrap items-center justify-between gap-2'>
              <div className='flex flex-wrap items-center gap-3 text-[11.5px]'>
                <label className='flex items-center gap-1.5'>
                  <Switch checked={Boolean(settings.disclosure_mandatory)} onCheckedChange={(v) => onChange({ ...settings, disclosure_mandatory: v })} />
                  <span>Mandatory</span>
                </label>
                <label className='flex items-center gap-1.5'>
                  <Switch checked={Boolean(settings.disclosure_for_survey)} onCheckedChange={(v) => onChange({ ...settings, disclosure_for_survey: v })} />
                  <span>Surveys</span>
                </label>
                <label className='flex items-center gap-1.5'>
                  <Switch checked={Boolean(settings.disclosure_for_interview)} onCheckedChange={(v) => onChange({ ...settings, disclosure_for_interview: v })} />
                  <span>Interviews</span>
                </label>
              </div>
              <Button type='button' size='sm' className='h-7' onClick={onSave} disabled={busy}>
                {busy ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  )
}

export function AgentVoiceFields({ draft, setField }) {
  return (
    <>
      <section className='card'>
        <div className='cardHead'>
          <h3>Voice identity & Telnyx</h3>
        </div>
        <div className='cardBody stack'>
          <div className='agentFieldGrid3'>
            <label>
              <span className='label'>Voice label (shown to users)</span>
              <input className='input' value={draft.voice_label || ''} onChange={(e) => setField('voice_label', e.target.value)} placeholder='Sophie' />
            </label>
            <label>
              <span className='label'>Voice type / gender label</span>
              <input className='input' value={draft.voice_type_label || ''} onChange={(e) => setField('voice_type_label', e.target.value)} placeholder='Female' />
            </label>
            <label>
              <span className='label'>Telnyx Assistant ID</span>
              <input className='input' value={draft.telnyx_assistant_id || ''} onChange={(e) => setField('telnyx_assistant_id', e.target.value)} placeholder='asst_...' />
            </label>
          </div>
          <p className='muted voiceAgentHelp'>Use the Telnyx assistant UUID from your Telnyx AI portal. Survey calls inject per-order instructions at runtime.</p>
        </div>
      </section>

      <section className='card'>
        <div className='cardHead'>
          <h3>Service availability</h3>
        </div>
        <div className='cardBody'>
          <div className='agentServiceToggles'>
            {[
              ['supports_survey', 'Survey', 'is_default_survey'],
              ['supports_interview', 'Interview', 'is_default_interview'],
              ['supports_lead_sales', 'Lead / Sales', 'is_default_lead_sales'],
            ].map(([key, label, defaultKey]) => (
              <div key={key} className='agentServiceToggleRow'>
                <label className='agentActiveToggle'>
                  <input type='checkbox' checked={Boolean(draft[key])} onChange={(e) => setField(key, e.target.checked)} />
                  <span>{label}</span>
                </label>
                <label className='agentActiveToggle agentDefaultToggle'>
                  <input type='checkbox' checked={Boolean(draft[defaultKey])} onChange={(e) => setField(defaultKey, e.target.checked)} disabled={!draft[key]} />
                  <span>Platform default</span>
                </label>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className='agentEditRow2'>
        <section className='card'>
          <div className='cardHead'><h3>Agent base role</h3></div>
          <div className='cardBody'>
            <textarea className='input agentPromptAreaSm' value={draft.base_role || ''} onChange={(e) => setField('base_role', e.target.value)} placeholder='Tone, pacing, interruption handling, objection handling...' />
          </div>
        </section>
        <section className='card'>
          <div className='cardHead'><h3>Service role overrides</h3></div>
          <div className='cardBody stack'>
            <label><span className='label'>Survey role</span><textarea className='input agentPromptAreaSm' value={draft.service_survey_role || ''} onChange={(e) => setField('service_survey_role', e.target.value)} /></label>
            <label><span className='label'>Interview role</span><textarea className='input agentPromptAreaSm' value={draft.service_interview_role || ''} onChange={(e) => setField('service_interview_role', e.target.value)} /></label>
            <label><span className='label'>Lead / Sales role</span><textarea className='input agentPromptAreaSm' value={draft.service_lead_sales_role || ''} onChange={(e) => setField('service_lead_sales_role', e.target.value)} /></label>
          </div>
        </section>
      </div>

      <section className='card'>
        <div className='cardHead'><h3>Opening disclosure override</h3></div>
        <div className='cardBody stack'>
          <textarea className='input' rows={3} value={draft.opening_disclosure_template || ''} onChange={(e) => setField('opening_disclosure_template', e.target.value)} placeholder='Optional per-agent template. Leave blank to use shared default.' />
          <div className='agentFieldGrid3'>
            <label className='agentActiveToggle'><input type='checkbox' checked={Boolean(draft.disclosure_for_survey)} onChange={(e) => setField('disclosure_for_survey', e.target.checked)} /><span>Survey calls</span></label>
            <label className='agentActiveToggle'><input type='checkbox' checked={Boolean(draft.disclosure_for_interview)} onChange={(e) => setField('disclosure_for_interview', e.target.checked)} /><span>Interview calls</span></label>
            <label className='agentActiveToggle'><input type='checkbox' checked={Boolean(draft.disclosure_mandatory)} onChange={(e) => setField('disclosure_mandatory', e.target.checked)} /><span>Mandatory</span></label>
          </div>
        </div>
      </section>

      <section className='card'>
        <div className='cardHead'><h3>Behavior settings</h3></div>
        <div className='cardBody stack'>
          <label><span className='label'>Retry policy notes</span><textarea className='input' rows={2} value={draft.retry_policy_notes || ''} onChange={(e) => setField('retry_policy_notes', e.target.value)} placeholder='e.g. Retry no-answer once after 1 hour.' /></label>
          <label><span className='label'>Interruption behavior</span><textarea className='input' rows={2} value={draft.interruption_behavior_notes || ''} onChange={(e) => setField('interruption_behavior_notes', e.target.value)} placeholder='If interrupted before disclosure, repeat opening clearly.' /></label>
          <label><span className='label'>Voicemail behavior</span>
            <select className='input' value={draft.voicemail_behavior || 'leave_message'} onChange={(e) => setField('voicemail_behavior', e.target.value)}>
              <option value='leave_message'>Leave brief message</option>
              <option value='hang_up'>Hang up</option>
              <option value='retry_later'>Mark for retry</option>
            </select>
          </label>
          <label><span className='label'>Opt-out / remove-me policy</span><textarea className='input' rows={2} value={draft.opt_out_policy_notes || ''} onChange={(e) => setField('opt_out_policy_notes', e.target.value)} placeholder='Acknowledge opt-out immediately and end the call.' /></label>
        </div>
      </section>
    </>
  )
}
