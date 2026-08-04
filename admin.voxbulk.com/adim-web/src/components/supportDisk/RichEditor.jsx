import React, { useEffect, useRef, useState } from 'react'
import { Bold, Code2, Heading2, Italic, Link2, List, ListOrdered, Quote, Underline } from 'lucide-react'
import { Button } from './Button'

export default function RichEditor({ value = '', onChange, placeholder = 'Write the content…' }) {
  const editor = useRef(null)
  const [source, setSource] = useState(false)
  useEffect(() => { if (!source && editor.current && editor.current.innerHTML !== value) editor.current.innerHTML = value }, [value, source])
  const cmd = (name, arg) => { editor.current?.focus(); document.execCommand(name, false, arg); onChange?.(editor.current?.innerHTML || '') }
  const tools = [[Bold, 'Bold', 'bold'], [Italic, 'Italic', 'italic'], [Underline, 'Underline', 'underline'], [Heading2, 'Heading', 'formatBlock', '<h2>'], [Quote, 'Quote', 'formatBlock', '<blockquote>'], [List, 'Bulleted list', 'insertUnorderedList'], [ListOrdered, 'Numbered list', 'insertOrderedList']]
  return <div className="overflow-hidden rounded-lg border border-border bg-surface">
    <div className="flex items-center gap-0.5 border-b border-border bg-surface-subtle p-1">{tools.map(([Icon, label, name, arg]) => <Button key={label} type="button" variant="ghost" size="icon" className="size-7" title={label} disabled={source} onClick={() => cmd(name, arg)}><Icon /></Button>)}
      <Button type="button" variant="ghost" size="sm" disabled={source} onClick={() => { const url = window.prompt('Link URL'); if (url) cmd('createLink', url) }}><Link2 /> Link</Button>
      <Button type="button" variant={source ? 'secondary' : 'ghost'} size="sm" className="ml-auto" onClick={() => setSource(!source)}><Code2 /> {source ? 'Visual' : 'HTML'}</Button>
    </div>
    {source ? <textarea value={value} onChange={(e) => onChange?.(e.target.value)} className="min-h-64 w-full resize-y bg-surface p-3 font-mono text-xs outline-none" /> : <div ref={editor} contentEditable suppressContentEditableWarning data-placeholder={placeholder} onInput={() => onChange?.(editor.current?.innerHTML || '')} className="kb-prose min-h-64 p-3 text-sm outline-none empty:before:text-muted-foreground empty:before:content-[attr(data-placeholder)]" />}
  </div>
}
