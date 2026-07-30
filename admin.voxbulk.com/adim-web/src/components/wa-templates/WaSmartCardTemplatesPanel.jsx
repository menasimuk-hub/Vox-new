import React, { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Save } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { apiFetch } from '../../lib/api'

/** Admin → WA Templates → Smart Card QR — local question bank + mailbox. */
export default function WaSmartCardTemplatesPanel({ onError, onMessage }) {
  const [questions, setQuestions] = useState([])
  const [mailbox, setMailbox] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [edit, setEdit] = useState(null)
  const [mailForm, setMailForm] = useState({
    mailbox_email: 'smartqr@voxbulk.com',
    from_name: 'VOXBULK Smart Card QR',
    smtp_username: '',
    password: '',
    is_enabled: true,
  })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [qs, mb] = await Promise.all([
        apiFetch('/admin/smart-card/questions'),
        apiFetch('/admin/smart-card/mailbox'),
      ])
      setQuestions(Array.isArray(qs?.items) ? qs.items : [])
      setMailbox(mb || null)
      setMailForm((prev) => ({
        ...prev,
        mailbox_email: mb?.mailbox_email || prev.mailbox_email,
        from_name: mb?.from_name || prev.from_name,
        smtp_username: mb?.smtp_username || '',
        is_enabled: mb?.is_enabled !== false,
        password: '',
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

  const saveQuestion = async () => {
    if (!edit?.question_key) return
    setSaving(true)
    try {
      await apiFetch(`/admin/smart-card/questions/${encodeURIComponent(edit.question_key)}`, {
        method: 'PATCH',
        body: JSON.stringify({
          label: edit.label,
          prompt: edit.prompt,
          description: edit.description,
          is_active: edit.is_active,
        }),
      })
      onMessage?.('Question saved')
      setEdit(null)
      await load()
    } catch (e) {
      onError?.(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const saveMailbox = async () => {
    setSaving(true)
    try {
      await apiFetch('/admin/smart-card/mailbox', {
        method: 'PUT',
        body: JSON.stringify(mailForm),
      })
      onMessage?.('Mailbox saved')
      await load()
    } catch (e) {
      onError?.(e?.message || 'Mailbox save failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Smart Card QR</h3>
          <p className="text-sm text-muted-foreground">Session question text + smartqr@voxbulk.com SMTP</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void load()}>
          <RefreshCw className="mr-1 size-4" /> Refresh
        </Button>
      </div>

      <section className="space-y-3 rounded-xl border p-4">
        <h4 className="font-medium">Mailbox (smartqr@voxbulk.com)</h4>
        <p className="text-xs text-muted-foreground">
          Password set: {mailbox?.password_set ? 'yes' : 'no'}
        </p>
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
        <Button size="sm" disabled={saving} onClick={() => void saveMailbox()}>
          <Save className="mr-1 size-4" /> Save mailbox
        </Button>
      </section>

      <section className="space-y-3">
        <h4 className="font-medium">Questions</h4>
        <div className="space-y-2">
          {questions.map((q) => (
            <div key={q.question_key} className="rounded-lg border p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-medium">
                    {q.label} <span className="text-xs text-muted-foreground">({q.question_key})</span>
                  </p>
                  <p className="text-sm text-muted-foreground">{q.prompt}</p>
                </div>
                <Button size="sm" variant="outline" onClick={() => setEdit({ ...q })}>
                  Edit
                </Button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {edit ? (
        <section className="space-y-2 rounded-xl border p-4">
          <h4 className="font-medium">Edit {edit.question_key}</h4>
          <input
            className="w-full rounded-md border px-3 py-2 text-sm"
            value={edit.label || ''}
            onChange={(e) => setEdit({ ...edit, label: e.target.value })}
          />
          <textarea
            className="min-h-[100px] w-full rounded-md border px-3 py-2 text-sm"
            value={edit.prompt || ''}
            onChange={(e) => setEdit({ ...edit, prompt: e.target.value })}
          />
          <div className="flex gap-2">
            <Button size="sm" disabled={saving} onClick={() => void saveQuestion()}>
              Save
            </Button>
            <Button size="sm" variant="outline" onClick={() => setEdit(null)}>
              Cancel
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  )
}
