import React from 'react'
import { BatteryFull, ChevronLeft, Image as ImageIcon, Link2, Phone, Reply, Signal, Video, Wifi } from 'lucide-react'

export default function WaPhonePreview({ template }) {
  const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const variables = Array.isArray(template?.variables) ? template.variables : []
  const buttons = Array.isArray(template?.buttons) ? template.buttons : []
  const rendered = String(template?.body || '').replace(/\{\{(\d+)\}\}/g, (_, n) => {
    const v = variables[Number(n) - 1]
    return v ? `⟨${v}⟩` : `{{${n}}}`
  })

  return (
    <div className="sticky top-4 flex justify-center">
      <div className="relative" style={{ width: 300, height: 610 }}>
        <div className="absolute inset-0 rounded-[52px] bg-[#0b0b0c] p-[10px] shadow-2xl ring-1 ring-black/40">
          <div className="relative h-full w-full overflow-hidden rounded-[44px] bg-[#e5ddd5]">
            <div className="absolute left-1/2 top-2 z-20 h-6 w-24 -translate-x-1/2 rounded-full bg-black" />
            <div className="absolute inset-x-0 top-0 z-10 flex h-9 items-center justify-between px-6 text-[10px] font-semibold text-black/90">
              <span className="tabular-nums">{now}</span>
              <span className="flex items-center gap-1">
                <Signal className="h-3 w-3" />
                <Wifi className="h-3 w-3" />
                <BatteryFull className="h-3.5 w-3.5" />
              </span>
            </div>

            <div className="absolute inset-x-0 top-9 z-10 flex h-12 items-center gap-2 bg-[#075E54] px-3 text-white">
              <ChevronLeft className="h-4 w-4" />
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-white/20 text-[10px] font-bold">
                CO
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-semibold">Company Inc.</div>
                <div className="text-[10px] opacity-80">online</div>
              </div>
              <Video className="h-4 w-4" />
              <Phone className="h-4 w-4" />
            </div>

            <div
              className="absolute inset-x-0 bottom-10 top-[84px] overflow-y-auto px-3 py-3"
              style={{
                backgroundImage:
                  'radial-gradient(circle at 20% 20%, rgba(0,0,0,0.04) 1px, transparent 1px), radial-gradient(circle at 80% 60%, rgba(0,0,0,0.04) 1px, transparent 1px)',
                backgroundSize: '24px 24px, 32px 32px',
              }}
            >
              <div className="animate-scale-in max-w-[85%] rounded-lg rounded-tl-sm bg-white p-2 shadow-sm">
                {template?.header?.type === 'image' ? (
                  <div className="mb-1.5 flex h-24 items-center justify-center rounded bg-gradient-to-br from-slate-200 to-slate-300 text-slate-400">
                    <ImageIcon className="h-6 w-6" />
                  </div>
                ) : null}
                {template?.header?.type === 'text' && template.header.text ? (
                  <div className="mb-1 text-[12px] font-bold text-[#111b21]">{template.header.text}</div>
                ) : null}
                <div className="whitespace-pre-wrap text-[12.5px] leading-snug text-[#111b21]">
                  {rendered.split(/(\*[^*]+\*)/g).map((part, i) =>
                    part.startsWith('*') && part.endsWith('*') ? (
                      <strong key={i}>{part.slice(1, -1)}</strong>
                    ) : (
                      <span key={i}>{part}</span>
                    ),
                  )}
                </div>
                {template?.footer ? (
                  <div className="mt-1.5 text-[10.5px] text-[#667781]">{template.footer}</div>
                ) : null}
                <div className="mt-1 flex items-center justify-end gap-1 text-[9px] text-[#667781]">
                  {now}
                  <svg viewBox="0 0 16 15" className="h-2.5 w-2.5 fill-[#53bdeb]">
                    <path d="M15.01 3.316l-.478-.372a.365.365 0 00-.51.063L8.666 9.879a.32.32 0 01-.484.033l-.358-.325a.319.319 0 00-.484.032l-.378.483a.418.418 0 00.036.541l1.32 1.266c.143.14.361.125.484-.033l6.272-8.048a.366.366 0 00-.064-.512zm-4.1 0l-.478-.372a.365.365 0 00-.51.063L4.566 9.879a.32.32 0 01-.484.033L1.891 7.769a.366.366 0 00-.515.006l-.423.433a.364.364 0 00.006.514l3.258 3.185c.143.14.361.125.484-.033l6.272-8.048a.365.365 0 00-.063-.51z" />
                  </svg>
                </div>
              </div>

              {buttons.length > 0 ? (
                <div className="mt-1.5 max-w-[85%] space-y-0.5">
                  {buttons.map((b, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-center gap-1 rounded-lg bg-white py-1.5 text-center text-[12px] font-medium text-[#00a5f4] shadow-sm"
                      style={{ animation: `wa-hub-fade-in 0.3s ease-out ${100 + i * 60}ms both` }}
                    >
                      {b.type === 'quick_reply' || b.type === 'QUICK_REPLY' ? <Reply className="h-3 w-3" /> : null}
                      {b.type === 'url' || b.type === 'URL' ? <Link2 className="h-3 w-3" /> : null}
                      {b.type === 'phone' || b.type === 'PHONE_NUMBER' ? <Phone className="h-3 w-3" /> : null}
                      {b.text || 'Button'}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>

            <div className="absolute inset-x-0 bottom-0 flex h-10 items-center gap-1.5 bg-[#f0f2f5] px-2">
              <div className="h-7 flex-1 rounded-full bg-white" />
              <div className="h-7 w-7 rounded-full bg-[#075E54]" />
            </div>
            <div className="absolute bottom-1 left-1/2 h-1 w-24 -translate-x-1/2 rounded-full bg-black/40" />
          </div>
        </div>
      </div>
    </div>
  )
}
