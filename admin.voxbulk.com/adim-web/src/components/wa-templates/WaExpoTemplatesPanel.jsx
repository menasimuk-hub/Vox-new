import React, { useCallback, useEffect, useState } from 'react'
import { Plus, RefreshCw, Save, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { apiFetch } from '../../lib/api'

/**
 * Admin → WA Templates → Expo
 * Local session-text question bank + industries (no Meta HSM push).
 */
export default function WaExpoTemplatesPanel({ onError, onMessage }) {
  const [industries, setIndustries] = useState([])
  const [questions, setQuestions] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [industryForm, setIndustryForm] = useState({
    name: '',
    addon_question: '',
    description: '',
  })
  const [questionForm, setQuestionForm] = useState({
    key: '',
    label: '',
    prompt: '',
    description: '',
    matches_products: true,
  })
  const [editQ, setEditQ] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [ind, qs] = await Promise.all([
        apiFetch('/admin/expo/industries'),
        apiFetch('/admin/expo/questions'),
      ])
      setIndustries(Array.isArray(ind?.items) ? ind.items : [])
      setQuestions(Array.isArray(qs?.items) ? qs.items : [])
    } catch (e) {
      onError?.(e?.message || 'Could not load Expo templates')
    } finally {
      setLoading(false)
    }
  }, [onError])

  useEffect(() => {
    void load()
  }, [load])

  const addIndustry = async () => {
    if (!industryForm.name.trim()) return
    setSaving(true)
    try {
      await apiFetch('/admin/expo/industries', {
        method: 'POST',
        body: JSON.stringify(industryForm),
      })
      setIndustryForm({ name: '', addon_question: '', description: '' })
      onMessage?.('Expo industry saved (local)')
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
      await apiFetch(`/admin/expo/industries/${ind.id}`, {
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
      await apiFetch('/admin/expo/questions', {
        method: 'POST',
        body: JSON.stringify(questionForm),
      })
      setQuestionForm({
        key: '',
        label: '',
        prompt: '',
        description: '',
        matches_products: true,
      })
      onMessage?.('Expo question saved (local session text)')
      await load()
    } catch (e) {
      onError?.(e?.message || 'Could not save question')
    } finally {
      setSaving(false)
    }
  }

  const saveQuestion = async () => {
    if (!editQ?.id) return
    setSaving(true)
    try {
      await apiFetch(`/admin/expo/questions/${editQ.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          label: editQ.label,
          prompt: editQ.prompt,
          description: editQ.description,
          matches_products: editQ.matches_products,
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
    if (!window.confirm('Delete this Expo question from the local bank?')) return
    setSaving(true)
    try {
      await apiFetch(`/admin/expo/questions/${id}`, { method: 'DELETE' })
      onMessage?.('Question deleted')
      await load()
    } catch (e) {
      onError?.(e?.message || 'Could not delete question')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading Expo templates…</div>
  }

  return (
    <div className="space-y-6 p-4">
      <div className="rounded-xl border border-info/30 bg-info-soft/30 p-3 text-sm">
        <p className="font-medium">Expo uses local session text — not Meta HSM templates.</p>
        <p className="mt-1 text-muted-foreground">
          Manage industries and qualifying questions here. Exhibitors pick these in the Expo wizard; live booth
          chat sends them as plain WhatsApp / web text after the visitor opens the QR.
        </p>
        <Button type="button" size="sm" variant="outline" className="mt-2" onClick={() => void load()}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">Industries</h3>
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          <input
            className="rounded-md border px-3 py-2 text-sm"
            placeholder="Industry name"
            value={industryForm.name}
            onChange={(e) => setIndustryForm((f) => ({ ...f, name: e.target.value }))}
          />
          <input
            className="rounded-md border px-3 py-2 text-sm sm:col-span-2"
            placeholder="Addon question (shown in wizard)"
            value={industryForm.addon_question}
            onChange={(e) => setIndustryForm((f) => ({ ...f, addon_question: e.target.value }))}
          />
        </div>
        <Button type="button" size="sm" disabled={saving || !industryForm.name.trim()} onClick={() => void addIndustry()}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          Add industry
        </Button>
        <div className="overflow-hidden rounded-lg border">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-muted text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Industry question</th>
                <th className="px-3 py-2 w-24" />
              </tr>
            </thead>
            <tbody>
              {industries.map((ind) => (
                <tr key={ind.id} className="border-t">
                  <td className="px-3 py-2 font-medium">{ind.name}</td>
                  <td className="px-3 py-2">
                    <input
                      className="w-full rounded-md border px-2 py-1.5 text-sm"
                      value={ind.addon_question || ''}
                      onChange={(e) =>
                        setIndustries((rows) =>
                          rows.map((r) => (r.id === ind.id ? { ...r, addon_question: e.target.value } : r)),
                        )
                      }
                    />
                  </td>
                  <td className="px-3 py-2">
                    <Button type="button" size="sm" variant="outline" disabled={saving} onClick={() => void saveIndustryAddon(ind)}>
                      <Save className="h-3.5 w-3.5" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold">Qualifying questions (all Expo leads)</h3>
        <p className="text-xs text-muted-foreground">
          Include price list / catalogue prompts so they match wizard Step 4 products. Mark “Matches products”
          when the answer should trigger PDF / file delivery.
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          <input
            className="rounded-md border px-3 py-2 text-sm"
            placeholder="Label (e.g. Need price list)"
            value={questionForm.label}
            onChange={(e) => setQuestionForm((f) => ({ ...f, label: e.target.value }))}
          />
          <input
            className="rounded-md border px-3 py-2 text-sm"
            placeholder="Key (optional, auto from label)"
            value={questionForm.key}
            onChange={(e) => setQuestionForm((f) => ({ ...f, key: e.target.value }))}
          />
          <textarea
            className="rounded-md border px-3 py-2 text-sm sm:col-span-2"
            rows={2}
            placeholder="Prompt sent on WhatsApp / web"
            value={questionForm.prompt}
            onChange={(e) => setQuestionForm((f) => ({ ...f, prompt: e.target.value }))}
          />
          <input
            className="rounded-md border px-3 py-2 text-sm sm:col-span-2"
            placeholder="Description for exhibitors"
            value={questionForm.description}
            onChange={(e) => setQuestionForm((f) => ({ ...f, description: e.target.value }))}
          />
          <label className="flex items-center gap-2 text-sm sm:col-span-2">
            <input
              type="checkbox"
              checked={questionForm.matches_products}
              onChange={(e) => setQuestionForm((f) => ({ ...f, matches_products: e.target.checked }))}
            />
            Matches products (price / catalogue delivery)
          </label>
        </div>
        <Button
          type="button"
          size="sm"
          disabled={saving || !questionForm.label.trim() || !questionForm.prompt.trim()}
          onClick={() => void addQuestion()}
        >
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          Add question
        </Button>

        <div className="overflow-hidden rounded-lg border">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-muted text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Label</th>
                <th className="px-3 py-2">Prompt</th>
                <th className="px-3 py-2">Products</th>
                <th className="px-3 py-2 w-28" />
              </tr>
            </thead>
            <tbody>
              {questions.map((q) => (
                <tr key={q.id} className="border-t align-top">
                  <td className="px-3 py-2">
                    {editQ?.id === q.id ? (
                      <input
                        className="w-full rounded border px-2 py-1"
                        value={editQ.label}
                        onChange={(e) => setEditQ((x) => ({ ...x, label: e.target.value }))}
                      />
                    ) : (
                      <span className="font-medium">{q.label}</span>
                    )}
                    <div className="text-[11px] text-muted-foreground">{q.key}</div>
                  </td>
                  <td className="px-3 py-2">
                    {editQ?.id === q.id ? (
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
                    {editQ?.id === q.id ? (
                      <input
                        type="checkbox"
                        checked={Boolean(editQ.matches_products)}
                        onChange={(e) => setEditQ((x) => ({ ...x, matches_products: e.target.checked }))}
                      />
                    ) : q.matches_products ? (
                      'Yes'
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex gap-1">
                      {editQ?.id === q.id ? (
                        <Button type="button" size="sm" disabled={saving} onClick={() => void saveQuestion()}>
                          Save
                        </Button>
                      ) : (
                        <Button type="button" size="sm" variant="outline" onClick={() => setEditQ({ ...q })}>
                          Edit
                        </Button>
                      )}
                      <Button type="button" size="sm" variant="ghost" disabled={saving} onClick={() => void deleteQuestion(q.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
