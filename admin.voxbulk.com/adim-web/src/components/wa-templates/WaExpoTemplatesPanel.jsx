import React, { useCallback, useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Plus, RefreshCw, Save, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { cn } from '@/lib/utils'
import { apiFetch } from '../../lib/api'

/**
 * Admin → WA Templates → Expo
 * Local session-text question bank + industries (no Meta HSM push).
 * Layout matches Survey/Feedback cards → drill-in topics pattern.
 */
export default function WaExpoTemplatesPanel({ onError, onMessage }) {
  const [industries, setIndustries] = useState([])
  const [questions, setQuestions] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [view, setView] = useState('root') // 'root' | 'industry' | 'questions'
  const [selectedIndustryId, setSelectedIndustryId] = useState(null)
  const [addIndustryOpen, setAddIndustryOpen] = useState(false)
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

  const selectedIndustry = industries.find((r) => r.id === selectedIndustryId) || null

  const openIndustry = (ind) => {
    setSelectedIndustryId(ind.id)
    setView('industry')
  }

  const openQuestions = () => {
    setEditQ(null)
    setView('questions')
  }

  const backToRoot = () => {
    setView('root')
    setSelectedIndustryId(null)
    setEditQ(null)
  }

  const addIndustry = async () => {
    if (!industryForm.name.trim()) return
    setSaving(true)
    try {
      await apiFetch('/admin/expo/industries', {
        method: 'POST',
        body: JSON.stringify(industryForm),
      })
      setIndustryForm({ name: '', addon_question: '', description: '' })
      setAddIndustryOpen(false)
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

  const addIndustryModal = (
    <Modal
      open={addIndustryOpen}
      onOpenChange={setAddIndustryOpen}
      title="Add Expo industry"
      description="Local industry for the Expo wizard (not a Meta HSM template)."
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
          placeholder="Addon question (shown in wizard)"
          value={industryForm.addon_question}
          onChange={(e) => setIndustryForm((f) => ({ ...f, addon_question: e.target.value }))}
        />
      </div>
    </Modal>
  )

  if (view === 'industry' && selectedIndustry) {
    return (
      <div className="animate-fade-in">
        <div className="flex flex-wrap items-center gap-2 border-b bg-surface-muted/40 px-3 py-2">
          <Button variant="ghost" size="sm" className="-ml-2 h-7 gap-1 text-xs" onClick={backToRoot}>
            <ChevronLeft className="h-3.5 w-3.5" /> Industries
          </Button>
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
          <span className="text-sm font-medium">{selectedIndustry.name}</span>
          <span className="text-xs text-muted-foreground">· industry question</span>
          <span className="text-xs text-info">· local</span>
        </div>
        <div className="space-y-3 p-3">
          <div>
            <div className="text-sm font-medium">Industry question</div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Addon prompt shown in the Expo wizard for this industry. Sent as plain session text after QR.
            </p>
          </div>
          <textarea
            className="w-full rounded-md border px-3 py-2 text-sm"
            rows={3}
            placeholder="Industry question (shown in wizard)"
            value={selectedIndustry.addon_question || ''}
            onChange={(e) =>
              setIndustries((rows) =>
                rows.map((r) =>
                  r.id === selectedIndustry.id ? { ...r, addon_question: e.target.value } : r,
                ),
              )
            }
          />
          <Button
            type="button"
            size="sm"
            className="h-8 gap-1.5 text-xs"
            disabled={saving}
            onClick={() => void saveIndustryAddon(selectedIndustry)}
          >
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
            <ChevronLeft className="h-3.5 w-3.5" /> Industries
          </Button>
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
          <span className="text-sm font-medium">Qualifying questions</span>
          <span className="text-xs text-muted-foreground">· {questions.length} topics</span>
          <span className="text-xs text-info">· local</span>
        </div>
        <div className="space-y-3 p-3">
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
                  <th className="px-3 py-2">Products</th>
                  <th className="px-3 py-2 w-28" />
                </tr>
              </thead>
              <tbody>
                {questions.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-3 py-8 text-center text-xs text-muted-foreground">
                      No qualifying questions yet. Use Add question.
                    </td>
                  </tr>
                ) : (
                  questions.map((q) => (
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
                        <div className="text-[11px] text-muted-foreground">
                          {q.key}
                          {q.is_system ? (
                            <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
                              System
                            </span>
                          ) : null}
                        </div>
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
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            disabled={saving}
                            onClick={() => void deleteQuestion(q.id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))
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
            <p className="text-sm font-medium">Expo uses local session text — not Meta HSM templates.</p>
            <p className="mt-0.5 max-w-2xl text-[11px] text-muted-foreground">
              Manage industries and qualifying questions here. Exhibitors pick these in the Expo wizard; live booth
              chat sends them as plain WhatsApp / web text after the visitor opens the QR.
            </p>
          </div>
          <Button type="button" size="sm" variant="outline" className="h-8 gap-1.5 text-xs" onClick={() => void load()}>
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          <button
            type="button"
            onClick={openQuestions}
            className="inline-flex h-8 items-center justify-between gap-2 rounded-md border bg-background px-2.5 text-left text-xs font-medium shadow-sm transition hover:border-primary/40 hover:bg-accent/40"
          >
            <span className="truncate">Qualifying questions</span>
            <span
              className={cn(
                'rounded-full px-1.5 py-0.5 text-[10px] font-semibold',
                questions.length > 0 ? 'bg-success-soft text-success' : 'bg-surface-muted text-muted-foreground',
              )}
            >
              {questions.length}
            </span>
          </button>
        </div>
      </div>

      <div className="p-3">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">Choose an industry</div>
            <div className="text-xs text-muted-foreground">
              {industries.length} industries · Click an industry to edit its question
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">{industries.length} industries</span>
            <Button
              size="sm"
              variant="outline"
              className="h-8 gap-1.5 text-xs"
              onClick={() => setAddIndustryOpen(true)}
            >
              <Plus className="h-3.5 w-3.5" /> Add industry
            </Button>
          </div>
        </div>

        {!industries.length ? (
          <p className="py-8 text-center text-xs text-muted-foreground">No industries yet.</p>
        ) : (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
            {industries.map((ind, i) => {
              const hasQuestion = Boolean((ind.addon_question || '').trim())
              return (
                <button
                  key={ind.id}
                  type="button"
                  onClick={() => openIndustry(ind)}
                  className={cn(
                    'group relative flex items-center justify-between rounded-lg border px-3 py-2.5 text-left',
                    'border-info/40 bg-info-soft/20 transition-all hover:shadow-sm hover-scale',
                  )}
                  style={{ animation: `wa-hub-fade-in 0.25s ease-out ${i * 15}ms both` }}
                  title="Local Expo industry"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="h-2 w-2 shrink-0 rounded-full bg-info" />
                      <div className="truncate text-sm font-medium">{ind.name}</div>
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">
                      {hasQuestion ? '1 industry question' : 'No industry question'}
                    </div>
                    <div className="mt-0.5 text-[10px] text-muted-foreground">Local session text</div>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" />
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
