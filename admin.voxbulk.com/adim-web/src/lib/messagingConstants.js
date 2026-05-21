export const SYSTEM_EMAIL_META = {
  new_user: { title: 'New user', description: 'Welcome / account created' },
  forgot_password: { title: 'Forgot password', description: 'Password recovery message' },
  new_invoice: { title: 'New invoice', description: 'Invoice available' },
  payment_failed: { title: 'Cancel / failed payment', description: 'Payment could not be processed' },
  general_notification: { title: 'General activity', description: 'Notifications and activity' },
  sales_offer: { title: 'Sales offer link', description: 'Sent when sales agent shares signup promo link' },
  usage_warning: { title: 'Usage alert (80%)', description: 'Sent when calls, WhatsApp, or SMS reach 80% of included allowance' },
}

export const SYSTEM_WHATSAPP_META = {
  sales_offer: { title: 'Sales offer link', description: 'Sent when sales agent shares signup promo link via WhatsApp (subscription, survey, or interview)' },
  sales_opt_in: { title: 'Sales opt-in', description: 'Sent after call — customer replies SEND OFFER to get the link' },
  sales_offer_followup: { title: 'Sales 7-day follow-up', description: 'Sent if promo link was not used after follow-up days' },
  sales_offer_keyword_confirm: { title: 'Keyword offer confirm', description: 'Sent when customer replies SEND OFFER on WhatsApp' },
}

export const DEFAULT_WA_BODY_BY_KEY = {
  sales_offer: `Hi {{first_name}},

Great speaking with you. Here is your VOXBULK {{offer_line}}:
{{promo_name}}
{{offer_summary}}

Start here: {{signup_url}}

Open the link to create your account — your offer applies automatically.

— VOXBULK Sales`,
  sales_opt_in: `Hi {{first_name}},

Thanks for speaking with VOXBULK today.

If you'd like your trial offer later, reply **SEND OFFER** to this chat and we'll send your signup link.

Reply **STOP** anytime to opt out.

— VOXBULK Sales`,
  sales_offer_followup: `Hi {{first_name}},

We sent your VOXBULK {{offer_line}} link a few days ago — any trouble signing up?

Reply here if you need help, or open your link again:
{{signup_url}}

Reply **STOP** to opt out.

— VOXBULK Sales`,
  sales_offer_keyword_confirm: `Hi {{first_name}},

Here is your VOXBULK {{offer_line}}:
{{promo_name}}
{{offer_summary}}

Start here: {{signup_url}}

Open the link on your phone to create your account — your offer applies automatically.

Need help? Just reply to this message.

— VOXBULK Sales`,
}

export const DEFAULT_SUBJECT_BY_KEY = {
  new_user: 'Welcome to VOXBULK',
  forgot_password: 'Reset your password',
  new_invoice: 'New invoice',
  payment_failed: 'Payment issue',
  general_notification: 'Notification',
  sales_offer: 'Your VOXBULK offer is ready',
  usage_warning: 'VOXBULK usage alert',
}

export const DEMO_HTML_BY_KEY = {
  new_user: `<!DOCTYPE html><html><body style="font-family:system-ui,sans-serif;max-width:560px;margin:24px auto;color:#0f172a;">
  <p>Hi <strong>{{user_email}}</strong>,</p>
  <p>Welcome to VOXBULK — your account is ready.</p>
  <p style="color:#64748b;font-size:13px;">This email uses HTML. Replace placeholders like <code>{{user_email}}</code>.</p>
</body></html>`,
  forgot_password: `<p>Hello,</p><p>We received a password reset for <strong>{{user_email}}</strong>.</p><p>If this was not you, ignore this email.</p>`,
  new_invoice: `<p>Hello,</p><p>New invoice <strong>#{{invoice_id}}</strong> — amount <strong>{{amount_gbp_pence}}</strong> pence ({{currency}}), status {{invoice_status}}.</p>`,
  payment_failed: `<p>Payment issue for <strong>{{user_email}}</strong>.</p><p>Amount due: <strong>{{amount}}</strong> · Invoice <strong>{{invoice_number}}</strong>.</p>`,
  general_notification: `<p>Hello {{user_name}},</p><p>{{message}}</p><p style="font-size:12px;color:#64748b;">Sent by VOXBULK notifications.</p>`,
  sales_offer: `<!DOCTYPE html><html><body style="font-family:system-ui,sans-serif;max-width:560px;margin:24px auto;color:#0f172a;line-height:1.6;">
  <p>Hi <strong>{{first_name}}</strong>,</p>
  <p>Thanks for speaking with us today. Your VOXBULK <strong>{{offer_line}}</strong> is ready:</p>
  <div style="margin:16px 0;padding:16px;border:1px solid #e2e8f0;border-radius:12px;background:#f8fafc;">
    <strong style="display:block;font-size:16px;color:#0f172a;">{{promo_name}}</strong>
    <span style="color:#64748b;font-size:14px;">{{offer_summary}}</span>
  </div>
  <p><a href="{{signup_url}}" style="display:inline-block;background:#00C896;color:#ffffff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">Start your account</a></p>
  <p style="word-break:break-all;font-size:13px;"><a href="{{signup_url}}" style="color:#00C896;">{{signup_url}}</a></p>
  <p>Your offer applies automatically when you sign up with this link.</p>
  <p style="font-size:12px;color:#64748b;">— VOXBULK Sales</p>
</body></html>`,
}

export const TEST_VARS_BY_KEY = {
  new_user: { user_email: 'test@example.com' },
  forgot_password: { user_email: 'test@example.com', reset_link: 'https://example.com/reset/demo-token' },
  new_invoice: {
    invoice_id: 'INV-1001',
    amount_gbp_pence: '4999',
    currency: 'GBP',
    invoice_status: 'open',
  },
  payment_failed: {
    user_email: 'test@example.com',
    amount: '£49.99',
    invoice_number: 'INV-1001',
  },
  general_notification: {
    user_name: 'Alex Demo',
    message: 'This is a test notification from the admin console.',
  },
  sales_offer: {
    first_name: 'Alex',
    offer_line: '20 free survey contacts',
    offer_summary: 'Includes 20 survey contacts after signup.',
    trial_line: '20 free survey contacts',
    promo_name: 'Promo · 20 survey contacts',
    plan_summary: 'Includes 20 survey contacts after signup.',
    signup_url: 'https://voxbulk.com/signin?promo=SURVEY20',
    plan_name: '',
    plan_price: '',
    trial_days: '0',
    survey_contacts_included: '20',
    interview_contacts_included: '0',
    calls_included: '0',
    whatsapp_included: '0',
    sms_included: '0',
  },
  usage_warning: {
    organisation_name: 'Northgate Dental',
    plan_code: 'dental_1',
    usage_summary: 'Calls 82%',
    usage_details_html: '<div><strong>Calls</strong>: 246 of 300 (82%)</div>',
    period_end: '30 Jun 2026',
    message: 'Usage alert: Calls 82%',
  },
}

export const DEFAULT_TEST_VARS = {
  user_email: 'test@example.com',
  user_name: 'Alex Demo',
  first_name: 'Alex',
  last_name: 'Demo',
  clinic_name: 'Demo Clinic',
  organisation_name: 'Demo Organisation',
  amount: '£49.99',
  invoice_number: 'INV-1001',
  invoice_id: 'INV-1001',
  amount_gbp_pence: '4999',
  currency: 'GBP',
  invoice_status: 'open',
  message: 'This is a test notification from the admin console.',
  code: '123456',
  date: '20 May 2026',
  time: '14:30',
  reset_link: 'https://example.com/reset/demo-token',
  reset_url: 'https://example.com/reset/demo-token',
  appointment_date: '21 May 2026',
  appointment_time: '10:30',
  patient_name: 'Jamie Demo',
  doctor_name: 'Dr. Smith',
}

export function buildEmailTestVariables(templateKey) {
  return {
    ...DEFAULT_TEST_VARS,
    ...(TEST_VARS_BY_KEY[templateKey] || {}),
  }
}

export const COMMON_PLACEHOLDERS = [
  '{{user_email}}',
  '{{amount}}',
  '{{invoice_number}}',
  '{{invoice_id}}',
  '{{amount_gbp_pence}}',
  '{{currency}}',
  '{{invoice_status}}',
  '{{user_name}}',
  '{{message}}',
  '{{first_name}}',
  '{{clinic_name}}',
  '{{code}}',
  '{{date}}',
  '{{time}}',
]

export const MESSAGING_TABS = [
  { id: 'email', label: 'Email templates', icon: 'ti-mail' },
  { id: 'whatsapp', label: 'WhatsApp templates', icon: 'ti-brand-whatsapp' },
  { id: 'sms', label: 'SMS templates', icon: 'ti-message' },
  { id: 'smtp', label: 'SMTP settings', icon: 'ti-server' },
]

export const DEFAULT_NEW_EMAIL_HTML = `<!DOCTYPE html><html><body style="font-family:system-ui,sans-serif;max-width:560px;margin:24px auto;color:#0f172a;">
  <p>Hello <strong>{{user_name}}</strong>,</p>
  <p>Your message here.</p>
  <p style="color:#64748b;font-size:13px;">Use placeholders like <code>{{user_email}}</code>.</p>
</body></html>`

/** Prefer saved DB content; fall back to legacy HTML defaults for system templates. */
export function mergeSystemEmailDraft(row) {
  const key = row?.template_key
  const meta = SYSTEM_EMAIL_META[key]
  const demo = DEMO_HTML_BY_KEY[key]
  const defaultSubject = DEFAULT_SUBJECT_BY_KEY[key]
  let body = String(row?.body || '').trim()
  if (demo && (!body || !/<[a-z][\s\S]*>/i.test(body))) {
    body = demo
  }
  return {
    template_key: key,
    title: String(row?.title || meta?.title || '').trim(),
    subject: String(row?.subject || defaultSubject || '').trim(),
    body,
    is_enabled: row?.is_enabled !== false,
  }
}

export function emailDisplayTitle(row) {
  const meta = SYSTEM_EMAIL_META[row?.template_key]
  return row?.title?.trim() || meta?.title || row?.template_key || 'Template'
}

export function emailDisplayDescription(row) {
  const meta = SYSTEM_EMAIL_META[row?.template_key]
  return meta?.description || 'Custom email template'
}

export function waDisplayTitle(row) {
  const meta = SYSTEM_WHATSAPP_META[row?.template_key]
  return row?.name?.trim() || meta?.title || row?.template_key || 'Template'
}

export function waDisplayDescription(row) {
  const meta = SYSTEM_WHATSAPP_META[row?.template_key]
  return meta?.description || 'Custom WhatsApp template'
}

export function smtpTestResultMessage(payload) {
  if (payload != null && typeof payload === 'object') {
    if (typeof payload.message === 'string' && payload.message.trim()) return payload.message.trim()
    if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail.trim()
    if (Array.isArray(payload.detail))
      return payload.detail.map((x) => (x && typeof x === 'object' && x.msg ? x.msg : JSON.stringify(x))).join('; ')
  }
  return 'Sent successfully.'
}

export function subjectPreview(subject) {
  const s = String(subject || '').trim()
  if (!s) return '—'
  return s.length > 48 ? `${s.slice(0, 48)}…` : s
}

export function bodyPreview(body, max = 56) {
  const s = String(body || '').replace(/\s+/g, ' ').trim()
  if (!s) return '—'
  return s.length > max ? `${s.slice(0, max)}…` : s
}

export function slugifyTemplateKey(name) {
  return String(name || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .replace(/_+/g, '_')
    .slice(0, 64)
}
