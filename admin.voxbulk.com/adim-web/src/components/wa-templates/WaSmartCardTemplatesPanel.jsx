import React, { useCallback, useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Plus, RefreshCw, Save, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { cn } from '@/lib/utils'
import { apiFetch } from '../../lib/api'

/** Admin → WA Templates → Smart Card QR — industries, questions, mailbox IMAP/SMTP. */
export default function WaSmartCardTemplatesPanel({ onError, onMessage }) {
  const [industries, setIndustries] = useState([])
  const [questions, setQuestions] = useState([])
  const [mailbox, setMailbox] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [view, setView] = useState('root') // 'root' | 'industry' | 'questions' | 'mailbox'
  const [selectedIndustryId, setSelectedIndustryId] = useState(null)
  const [addIndustryOpen, setAddIndustryOpen] = useState(false)
  const [industryForm, setIndustryForm] = useState({ name: '', addon_question: '' })
  const [questionForm, setQuestionForm] = useState({ key: '', label: '', prompt: '', description: '' })
  const [editQ, setEditQ] = useState(null)
  const [testTo, setTestTo] = useState('')
  const [mailForm, setMailForm] = useState({
    mailbox_email: 'smartqr@voxbulk.com',
    from_name: 'VOXBULK Smart Card QR',
    smtp_username: '',
    smtp_host: '',
    smtp_port: '',
    password: '',
    is_enabled: true,
    imap_host: '',
    imap_port: 993,
    imap_use_ssl: true,
    imap_use_tls: false,
    imap_username: '',
    imap_password: '',
  })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [ind, qs, mb] = await Promise.all([
        apiFetch('/admin/smart-card/industries'),
        apiFetch('/admin/smart-card/questions'),
        apiFetch('/admin/smart-card/mailbox'),
      ])
      setIndustries(Array.isArray(ind?.items) ? ind.items : [])
      setQuestions(Array.isArray(qs?.items) ? qs.items : [])
      setMailbox(mb || null)
      setMailForm((prev) => ({
        ...prev,
        mailbox_email: mb?.mailbox_email || prev.mailbox_email,
        from_name: mb?.from_name || prev.from_name,
        smtp_username: mb?.smtp_username || '',
        smtp_host: mb?.smtp_host || '',
        smtp_port: mb?.smtp_port != null ? String(mb.smtp_port) : '',
        is_enabled: mb?.is_enabled !== false,
        imap_host: mb?.imap_host || '',
        imap_port: mb?.imap_port || 993,
        imap_use_ssl: mb?.imap_use_ssl !== false,
        imap_use_tls: Boolean(mb?.imap_use_tls),
        imap_username: mb?.imap_username || '',
        password: '',
        imap_password: '',
      }))
    } catch (e) {
      onError?.(e?.message || 'Could not load Smart Card QR settings')
    } finally {
      setLoading(false)
    }
  }, [onError])

  useEffect(() => {
    void load()
  }, [load])

  const selectedIndustry = industries.find((r) => r.id === selectedIndustryId) || null

  const openIndustry = (ind) => {
    setSelectedIndustryId(ind.id)
    setView('industry')
  }

  const openQuestions = () => {
    setEditQ(null)
    setView('questions')
  }

  const openMailbox = () => setView('mailbox')

  const backToRoot = () => {
    setView('root')
    setSelectedIndustryId(null)
    setEditQ(null)
  }

  const addIndustry = async () => {
    if (!industryForm.name.trim()) return
    setSaving(true)
    try {
      await apiFetch('/admin/smart-card/industries', {
        method: 'POST',
        body: JSON.stringify(industryForm),
      })
      setIndustryForm({ name: '', addon_question: '' })
      setAddIndustryOpen(false)
      onMessage?.('Industry saved')
      await load()
    } catch (e) {
      onError?.(e?.message || 'Could not save industry')
    } finally {
      setSaving(false)
    }
  }

  const saveIndustryAddon = async (ind) => {
    setSaving(true)
    try {
      await apiFetch(`/admin/smart-card/industries/${ind.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ addon_question: ind.addon_question || '' }),
      })
      onMessage?.('Industry question updated')
      await load()
    } catch (e) {
      onError?.(e?.message || 'Could not update industry')
    } finally {
      setSaving(false)
    }
  }

  const addQuestion = async () => {
    if (!questionForm.label.trim() || !questionForm.prompt.trim()) return
    setSaving(true)
    try {
      await apiFetch('/admin/smart-card/questions', {
        method: 'POST',
        body: JSON.stringify(questionForm),
      })
      setQuestionForm({ key: '', label: '', prompt: '', description: '' })
      onMessage?.('Question saved')
      await load()
    } catch (e) {
      onError?.(e?.message || 'Could not save question')
    } finally {
      setSaving(false)
    }
  }

  const saveQuestion = async () => {
    if (!editQ?.question_key && !editQ?.key) return
    const key = editQ.question_key || editQ.key
    setSaving(true)
    try {
      await apiFetch(`/admin/smart-card/questions/${encodeURIComponent(key)}`, {
        method: 'PATCH',
        body: JSON.stringify({
          label: editQ.label,
          prompt: editQ.prompt,
          description: editQ.description,
          is_active: editQ.is_active,
        }),
      })
      setEditQ(null)
      onMessage?.('Question updated')
      await load()
    } catch (e) {
      onError?.(e?.message || 'Could not update question')
    } finally {
      setSaving(false)
    }
  }

  const deleteQuestion = async (id) => {
    if (!window.confirm('Delete or deactivate this question?')) return
    setSaving(true)
    try {
      await apiFetch(`/admin/smart-card/questions/${encodeURIComponent(id)}`, { method: 'DELETE' })
      onMessage?.('Question removed')
      await load()
    } catch (e) {
      onError?.(e?.message || 'Could not delete question')
    } finally {
      setSaving(false)
    }
  }

  const saveMailbox = async () => {
    setSaving(true)
    try {
      const body = {
        ...mailForm,
        smtp_port: mailForm.smtp_port === '' ? null : Number(mailForm.smtp_port),
        imap_port: Number(mailForm.imap_port) || 993,
      }
      if (!body.password) delete body.password
      if (!body.imap_password) delete body.imap_password
      await apiFetch('/admin/smart-card/mailbox', {
        method: 'PUT',
        body: JSON.stringify(body),
      })
      onMessage?.('Mailbox saved')
      await load()
    } catch (e) {
      onError?.(e?.message || 'Mailbox save failed')
    } finally {
      setSaving(false)
    }
  }

  const testSend = async () => {
    if (!testTo.trim()) {
      onError?.('Enter a recipient email for test send')
      return
    }
    setSaving(true)
    try {
      const res = await apiFetch('/admin/smart-card/mailbox/test-send', {
        method: 'POST',
        body: JSON.stringify({ to_email: testTo.trim() }),
      })
      onMessage?.(res?.detail || 'Test send OK')
    } catch (e) {
      onError?.(e?.message || 'Test send failed')
    } finally {
      setSaving(false)
    }
  }

  const testImap = async () => {
    setSaving(true)
    try {
      const res = await apiFetch('/admin/smart-card/mailbox/test-imap', { method: 'POST', body: '{}' })
      onMessage?.(res?.detail || 'IMAP OK')
    } catch (e) {
      onError?.(e?.message || 'IMAP test failed')
    } finally {
      setSaving(false)
    }
  }

  const syncNow = async () => {
    setSaving(true)
    try {
      const res = await apiFetch('/admin/smart-card/mailbox/sync-now', { method: 'POST', body: '{}' })
      onMessage?.(res?.message || 'Sync complete')
      await load()
    } catch (e) {
      onError?.(e?.message || 'Sync failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading Smart Card QR…</div>
  }

  const addIndustryModal = (
    <Modal
      open={addIndustryOpen}
      onOpenChange={setAddIndustryOpen}
      title="Add Smart Card industry"
      description="Local industry for Smart Card QR (not a Meta HSM template)."
      footer={
        <>
          <Button type="button" variant="outline" size="sm" onClick={() => setAddIndustryOpen(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={saving || !industryForm.name.trim()}
            onClick={() => void addIndustry()}
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            Add industry
          </Button>
        </>
      }
    >
      <div className="grid gap-2">
        <input
          className="rounded-md border px-3 py-2 text-sm"
          placeholder="Industry name"
          value={industryForm.name}
          onChange={(e) => setIndustryForm((f) => ({ ...f, name: e.target.value }))}
        />
        <input
          className="rounded-md border px-3 py-2 text-sm"
          placeholder="Addon question"
          value={industryForm.addon_question}
          onChange={(e) => setIndustryForm((f) => ({ ...f, addon_question: e.target.value }))}
        />
      </div>
    </Modal>
  )

  if (view === 'mailbox') {
    return (
      <div className="animate-fade-in">
        <div className="flex flex-wrap items-center gap-2 border-b bg-surface-muted/40 px-3 py-2">
          <Button variant="ghost" size="sm" className="-ml-2 h-7 gap-1 text-xs" onClick={backToRoot}>
            <ChevronLeft className="h-3.5 w-3.5" /> Smart Card
          </Button>
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
          <span className="text-sm font-medium">Mailbox</span>
        </div>
        <div className="space-y-4 p-3">
          <div>
            <h4 className="text-sm font-medium">SMTP (smartqr@voxbulk.com)</h4>
            <p className="text-xs text-muted-foreground">
              Password set: {mailbox?.password_set ? 'yes' : 'no'}
              {mailbox?.smtp_host ? '' : ' · blank host uses platform SMTP with From override'}
            </p>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            <input
              className="rounded-md border px-3 py-2 text-sm"
              value={mailForm.mailbox_email}
              onChange={(e) => setMailForm({ ...mailForm, mailbox_email: e.target.value })}
              placeholder="mailbox email"
            />
            <input
              className="rounded-md border px-3 py-2 text-sm"
              value={mailForm.from_name}
              onChange={(e) => setMailForm({ ...mailForm, from_name: e.target.value })}
              placeholder="from name"
            />
            <input
              className="rounded-md border px-3 py-2 text-sm"
              value={mailForm.smtp_host}
              onChange={(e) => setMailForm({ ...mailForm, smtp_host: e.target.value })}
              placeholder="smtp host (optional)"
            />
            <input
              className="rounded-md border px-3 py-2 text-sm"
              value={mailForm.smtp_port}
              onChange={(e) => setMailForm({ ...mailForm, smtp_port: e.target.value })}
              placeholder="smtp port (optional)"
            />
            <input
              className="rounded-md border px-3 py-2 text-sm"
              value={mailForm.smtp_username}
              onChange={(e) => setMailForm({ ...mailForm, smtp_username: e.target.value })}
              placeholder="smtp username"
            />
            <input
              className="rounded-md border px-3 py-2 text-sm"
              type="password"
              value={mailForm.password}
              onChange={(e) => setMailForm({ ...mailForm, password: e.target.value })}
              placeholder="smtp password (leave blank to keep)"
            />
          </div>

          <div className="border-t pt-3">
            <h4 className="text-sm font-medium">IMAP (inbox → tickets)</h4>
            <p className="text-xs text-muted-foreground">
              IMAP password set: {mailbox?.imap_password_set ? 'yes' : 'no'}
              {mailbox?.imap_last_sync_at
                ? ` · last sync ${mailbox.imap_last_sync_at}`
                : ''}
            </p>
            {mailbox?.imap_last_sync_message ? (
              <p className="mt-1 text-[11px] text-muted-foreground">{mailbox.imap_last_sync_message}</p>
            ) : null}
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            <input
              className="rounded-md border px-3 py-2 text-sm"
              value={mailForm.imap_host}
              onChange={(e) => setMailForm({ ...mailForm, imap_host: e.target.value })}
              placeholder="imap host"
            />
            <input
              className="rounded-md border px-3 py-2 text-sm"
              value={mailForm.imap_port}
              onChange={(e) => setMailForm({ ...mailForm, imap_port: e.target.value })}
              placeholder="imap port"
            />
            <input
              className="rounded-md border px-3 py-2 text-sm"
              value={mailForm.imap_username}
              onChange={(e) => setMailForm({ ...mailForm, imap_username: e.target.value })}
              placeholder="imap username"
            />
            <input
              className="rounded-md border px-3 py-2 text-sm"
              type="password"
              value={mailForm.imap_password}
              onChange={(e) => setMailForm({ ...mailForm, imap_password: e.target.value })}
              placeholder="imap password (leave blank to keep)"
            />
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={mailForm.imap_use_ssl}
                onChange={(e) => setMailForm({ ...mailForm, imap_use_ssl: e.target.checked })}
              />
              IMAP SSL
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={mailForm.imap_use_tls}
                onChange={(e) => setMailForm({ ...mailForm, imap_use_tls: e.target.checked })}
              />
              IMAP STARTTLS
            </label>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={saving} onClick={() => void saveMailbox()}>
              <Save className="mr-1 size-4" /> Save mailbox
            </Button>
            <input
              className="min-w-[200px] flex-1 rounded-md border px-3 py-1.5 text-sm"
              value={testTo}
              onChange={(e) => setTestTo(e.target.value)}
              placeholder="test send to@"
            />
            <Button size="sm" variant="outline" disabled={saving} onClick={() => void testSend()}>
              Test send
            </Button>
            <Button size="sm" variant="outline" disabled={saving} onClick={() => void testImap()}>
              Test receive
            </Button>
            <Button size="sm" variant="outline" disabled={saving} onClick={() => void syncNow()}>
              Sync now
            </Button>
          </div>
        </div>
        {addIndustryModal}
      </div>
    )
  }

  if (view === 'industry' && selectedIndustry) {
    return (
      <div className="animate-fade-in">
        <div className="flex flex-wrap items-center gap-2 border-b bg-surface-muted/40 px-3 py-2">
          <Button variant="ghost" size="sm" className="-ml-2 h-7 gap-1 text-xs" onClick={backToRoot}>
            <ChevronLeft className="h-3.5 w-3.5" /> Industries
          </Button>
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
          <span className="text-sm font-medium">{selectedIndustry.name}</span>
        </div>
        <div className="space-y-3 p-3">
          <div className="text-sm font-medium">Industry question</div>
          <textarea
            className="w-full rounded-md border px-3 py-2 text-sm"
            rows={3}
            placeholder="Addon question"
            value={selectedIndustry.addon_question || ''}
            onChange={(e) =>
              setIndustries((rows) =>
                rows.map((r) =>
                  r.id === selectedIndustry.id ? { ...r, addon_question: e.target.value } : r,
                ),
              )
            }
          />
          <Button size="sm" className="h-8 gap-1.5 text-xs" disabled={saving} onClick={() => void saveIndustryAddon(selectedIndustry)}>
            <Save className="h-3.5 w-3.5" />
            Save
          </Button>
        </div>
        {addIndustryModal}
      </div>
    )
  }

  if (view === 'questions') {
    return (
      <div className="animate-fade-in">
        <div className="flex flex-wrap items-center gap-2 border-b bg-surface-muted/40 px-3 py-2">
          <Button variant="ghost" size="sm" className="-ml-2 h-7 gap-1 text-xs" onClick={backToRoot}>
            <ChevronLeft className="h-3.5 w-3.5" /> Smart Card
          </Button>
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
          <span className="text-sm font-medium">Questions</span>
          <span className="text-xs text-muted-foreground">· {questions.length}</span>
        </div>
        <div className="space-y-3 p-3">
          <div className="grid gap-2 sm:grid-cols-2">
            <input
              className="rounded-md border px-3 py-2 text-sm"
              placeholder="Label"
              value={questionForm.label}
              onChange={(e) => setQuestionForm((f) => ({ ...f, label: e.target.value }))}
            />
            <input
              className="rounded-md border px-3 py-2 text-sm"
              placeholder="Key (optional)"
              value={questionForm.key}
              onChange={(e) => setQuestionForm((f) => ({ ...f, key: e.target.value }))}
            />
            <textarea
              className="rounded-md border px-3 py-2 text-sm sm:col-span-2"
              rows={2}
              placeholder="Prompt"
              value={questionForm.prompt}
              onChange={(e) => setQuestionForm((f) => ({ ...f, prompt: e.target.value }))}
            />
          </div>
          <Button
            type="button"
            size="sm"
            className="h-8 gap-1.5 text-xs"
            disabled={saving || !questionForm.label.trim() || !questionForm.prompt.trim()}
            onClick={() => void addQuestion()}
          >
            <Plus className="h-3.5 w-3.5" />
            Add question
          </Button>

          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-left text-sm">
              <thead className="bg-surface-muted text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Label</th>
                  <th className="px-3 py-2">Prompt</th>
                  <th className="w-28 px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {questions.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-3 py-8 text-center text-xs text-muted-foreground">
                      No questions yet.
                    </td>
                  </tr>
                ) : (
                  questions.map((q) => {
                    const qKey = q.question_key || q.key
                    const editing = editQ && (editQ.question_key || editQ.key) === qKey
                    return (
                      <tr key={q.id || qKey} className="border-t align-top">
                        <td className="px-3 py-2">
                          {editing ? (
                            <input
                              className="w-full rounded border px-2 py-1"
                              value={editQ.label}
                              onChange={(e) => setEditQ((x) => ({ ...x, label: e.target.value }))}
                            />
                          ) : (
                            <span className="font-medium">{q.label}</span>
                          )}
                          <div className="text-[11px] text-muted-foreground">{qKey}</div>
                        </td>
                        <td className="px-3 py-2">
                          {editing ? (
                            <textarea
                              className="w-full rounded border px-2 py-1"
                              rows={2}
                              value={editQ.prompt}
                              onChange={(e) => setEditQ((x) => ({ ...x, prompt: e.target.value }))}
                            />
                          ) : (
                            <span className="text-muted-foreground">{q.prompt}</span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex gap-1">
                            {editing ? (
                              <Button type="button" size="sm" disabled={saving} onClick={() => void saveQuestion()}>
                                Save
                              </Button>
                            ) : (
                              <Button type="button" size="sm" variant="outline" onClick={() => setEditQ({ ...q })}>
                                Edit
                              </Button>
                            )}
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              disabled={saving}
                              onClick={() => void deleteQuestion(q.id || qKey)}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
        {addIndustryModal}
      </div>
    )
  }

  return (
    <div className="animate-fade-in">
      <div className="border-b px-3 py-3">
        <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-sm font-medium">Smart Card QR — local session text + mailbox</p>
            <p className="mt-0.5 max-w-2xl text-[11px] text-muted-foreground">
              Industries and questions for the Smart Card flow. Mailbox IMAP syncs inbound mail to support tickets.
            </p>
          </div>
          <Button type="button" size="sm" variant="outline" className="h-8 gap-1.5 text-xs" onClick={() => void load()}>
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
          <button
            type="button"
            onClick={openQuestions}
            className="inline-flex h-8 items-center justify-between gap-2 rounded-md border bg-background px-2.5 text-left text-xs font-medium shadow-sm transition hover:border-primary/40 hover:bg-accent/40"
          >
            <span className="truncate">Questions</span>
            <span
              className={cn(
                'rounded-full px-1.5 py-0.5 text-[10px] font-semibold',
                questions.length > 0 ? 'bg-success-soft text-success' : 'bg-surface-muted text-muted-foreground',
              )}
            >
              {questions.length}
            </span>
          </button>
          <button
            type="button"
            onClick={openMailbox}
            className="inline-flex h-8 items-center justify-between gap-2 rounded-md border bg-background px-2.5 text-left text-xs font-medium shadow-sm transition hover:border-primary/40 hover:bg-accent/40"
          >
            <span className="truncate">Mailbox</span>
            <span className="rounded-full bg-surface-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
              {mailbox?.imap_configured ? 'IMAP' : 'SMTP'}
            </span>
          </button>
        </div>
      </div>

      <div className="p-3">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">Industries</div>
            <div className="text-xs text-muted-foreground">{industries.length} · click to edit addon question</div>
          </div>
          <Button size="sm" variant="outline" className="h-8 gap-1.5 text-xs" onClick={() => setAddIndustryOpen(true)}>
            <Plus className="h-3.5 w-3.5" /> Add industry
          </Button>
        </div>

        {!industries.length ? (
          <p className="py-8 text-center text-xs text-muted-foreground">No industries yet. Run seed or add one.</p>
        ) : (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
            {industries.map((ind, i) => {
              const hasQuestion = Boolean((ind.addon_question || '').trim())
              return (
                <button
                  key={ind.id}
                  type="button"
                  onClick={() => openIndustry(ind)}
                  className="group relative flex items-center justify-between rounded-lg border border-info/40 bg-info-soft/20 px-3 py-2.5 text-left transition-all hover:shadow-sm"
                  style={{ animation: `wa-hub-fade-in 0.25s ease-out ${i * 15}ms both` }}
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{ind.name}</div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">
                      {hasQuestion ? '1 industry question' : 'No industry question'}
                    </div>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground group-hover:text-primary" />
                </button>
              )
            })}
          </div>
        )}
      </div>
      {addIndustryModal}
    </div>
  )
}
