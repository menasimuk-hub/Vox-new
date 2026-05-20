/** WhatsApp survey preview — theme from whatsapp_survey_all.html */

import { getWaPlaceholders, getWaSenderLabel } from './clientContext.js'

export const WA_QUESTION_META = {
  intro: { icon: 'ti-robot', label: 'Welcome' },
  closing: { icon: 'ti-circle-check', label: 'Complete' },
  rating: { icon: 'ti-star', label: 'Star Rating' },
  nps: { icon: 'ti-chart-bar', label: 'NPS Score' },
  likert: { icon: 'ti-adjustments-horizontal', label: 'Likert Scale' },
  slider: { icon: 'ti-adjustments', label: 'Slider' },
  buttons: { icon: 'ti-help-circle', label: 'Yes / No' },
  single_choice: { icon: 'ti-circle-dot', label: 'Single Choice' },
  multi: { icon: 'ti-checkbox', label: 'Multiple Choice' },
  true_false: { icon: 'ti-toggle-right', label: 'True / False' },
  text: { icon: 'ti-message', label: 'Open Text' },
  long_text: { icon: 'ti-file-text', label: 'Long Text' },
  contact: { icon: 'ti-address-book', label: 'Contact' },
  emoji: { icon: 'ti-mood-smile', label: 'Emoji Reaction' },
  thumbs: { icon: 'ti-thumb-up', label: 'Thumbs' },
  image_choice: { icon: 'ti-photo', label: 'Image Choice' },
  ranking: { icon: 'ti-list-numbers', label: 'Ranking' },
  priority: { icon: 'ti-star', label: 'Priority' },
  date: { icon: 'ti-calendar', label: 'Date' },
  time_slot: { icon: 'ti-clock', label: 'Time Slot' },
}

const LIKERT_DEFAULT = ['Strongly Disagree', 'Disagree', 'Neutral', 'Agree', 'Strongly Agree']

export function escapeHtml(raw) {
  return String(raw || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function inferReplyType(text, options = []) {
  const q = String(text || '').toLowerCase()
  const opts = (options || []).map((o) => String(o).toLowerCase())
  if (/emoji|feel about|how do you feel/.test(q)) return 'emoji'
  if (/thumb|helpful|faq/.test(q)) return 'thumbs'
  if (/true or false|true\/false/.test(q)) return 'true_false'
  if (/select all|multiple|which features/.test(q)) return 'multi'
  if (/rank|order|importance/.test(q)) return 'ranking'
  if (/priority|star your top/.test(q)) return 'priority'
  if (/when would you prefer|time slot|follow-up call/.test(q)) return 'time_slot'
  if (/when did you|date|last use/.test(q)) return 'date'
  if (/email|phone|contact|follow up with you/.test(q)) return 'contact'
  if (/describe.*detail|long text|in detail/.test(q)) return 'long_text'
  if (/recommend|nps|0-10|0 to 10|not likely|very likely/.test(q)) return 'nps'
  if (/rate|scale|1-5|1 to 5|score|stars|experience|satisfied/.test(q)) return 'rating'
  if (/strongly disagree|likert|agree or disagree/.test(q)) return 'likert'
  if (/slider|0 =|100 =|out of 100/.test(q)) return 'slider'
  if (opts.length >= 9) return 'nps'
  if (opts.length > 2) return 'single_choice'
  if (opts.length === 2 && opts.includes('yes') && opts.includes('no')) return 'buttons'
  if (/^would you|^did you|^have you|^is |^are /.test(q)) return 'buttons'
  if (/improve|describe|tell us|what.*think|feedback/.test(q)) return 'text'
  return opts.length > 2 ? 'single_choice' : 'buttons'
}

export function defaultOptions(replyType) {
  switch (replyType) {
    case 'rating':
      return ['1', '2', '3', '4', '5']
    case 'nps':
      return Array.from({ length: 11 }, (_, i) => String(i))
    case 'likert':
      return [...LIKERT_DEFAULT]
    case 'emoji':
      return ['😞 Terrible', '😕 Meh', '😐 Okay', '😊 Good', '🤩 Amazing']
    case 'thumbs':
      return ['👍 Thumbs up', '👎 Thumbs down']
    case 'true_false':
      return ['True', 'False']
    case 'time_slot':
      return ['9:00 AM', '10:30 AM', '12:00 PM', '2:00 PM', '3:30 PM', '5:00 PM']
    case 'slider':
      return []
    case 'text':
    case 'long_text':
    case 'contact':
    case 'date':
      return []
    default:
      return ['Yes', 'No']
  }
}

export function normalizeQuestion(item, index) {
  if (typeof item === 'string') {
    const text = item.trim()
    const reply_type = inferReplyType(text)
    return { text, reply_type, options: defaultOptions(reply_type), index: index + 1 }
  }
  const text = String(item?.text || '').trim()
  const reply_type = String(item?.reply_type || inferReplyType(text, item?.options)).toLowerCase()
  const options = Array.isArray(item?.options) && item.options.length ? item.options.map(String) : defaultOptions(reply_type)
  return { text, reply_type, options, index: index + 1 }
}

export function parseScriptTextToFlow(scriptText) {
  const raw = String(scriptText || '').trim()
  if (!raw) return null

  let intro = ''
  let closing = ''
  let qBlock = ''

  const introMatch = raw.match(/INTRO\s*\r?\n([\s\S]*?)(?=\r?\n\s*QUESTIONS|\r?\n\s*CLOSING|$)/i)
  const qMatch = raw.match(/QUESTIONS\s*\r?\n([\s\S]*?)(?=\r?\n\s*CLOSING|$)/i)
  const closingMatch = raw.match(/CLOSING\s*\r?\n([\s\S]*)/i)

  if (introMatch) intro = introMatch[1].trim()
  if (qMatch) qBlock = qMatch[1].trim()
  if (closingMatch) closing = closingMatch[1].trim()

  const questions = []
  if (qBlock) {
    qBlock.split(/\r?\n/).forEach((line) => {
      const m = line.match(/^\s*\d+\.\s*(.+)$/)
      if (m) questions.push(normalizeQuestion(m[1].trim(), questions.length))
    })
  }

  if (!intro && !questions.length) {
    intro = raw
  }

  return {
    intro: intro || 'Hi {first_name}, please answer a few quick questions from {clinic_name}.',
    questions,
    closing: closing || 'Thank you for your feedback!',
  }
}

export function buildWaFlowFromPayload(payload = {}) {
  const wa = payload.whatsapp_flow
  if (wa?.intro && Array.isArray(wa.questions) && wa.questions.length) {
    return {
      intro: wa.intro,
      closing: wa.closing || payload.closing || 'Thank you!',
      questions: wa.questions.map((q, i) => normalizeQuestion(q, i)),
    }
  }

  const fromScript = parseScriptTextToFlow(payload.script_text)
  if (fromScript?.questions?.length) return fromScript

  const plainQs = (payload.questions || []).filter(Boolean)
  if (plainQs.length) {
    return {
      intro: payload.intro || wa?.intro || payload.whatsapp_intro || 'Hi {first_name}, quick survey from {clinic_name}.',
      closing: payload.closing || wa?.closing || 'Thank you for your feedback!',
      questions: plainQs.map((q, i) => normalizeQuestion(q, i)),
    }
  }

  if (fromScript?.intro) return fromScript

  return {
    intro: 'Generate a survey script first, then open preview.',
    questions: [],
    closing: 'Thank you!',
  }
}

export function personalizeWaText(text, sample) {
  const vars = sample || getWaPlaceholders()
  let out = String(text || '')
  Object.entries(vars).forEach(([key, value]) => {
    out = out.replaceAll(`{${key}}`, value)
  })
  return out
}

function formatStarAnswer(v) {
  const labels = ['', '😞 Poor', '😕 Fair', '😐 Okay', '😊 Good', '🤩 Excellent']
  return `${labels[v] || '⭐'} (${v}/5 ★)`
}

function formatNpsAnswer(v) {
  const n = Number(v)
  const emoji = n >= 9 ? '🤩' : n >= 7 ? '😊' : n >= 5 ? '😐' : '😕'
  return `${emoji} Score: ${n}/10`
}

function disableWaInteractive(root) {
  root?.querySelectorAll('button, input, textarea').forEach((el) => {
    el.disabled = true
  })
  root?.querySelectorAll('.wa-star-btn').forEach((el) => {
    el.style.pointerEvents = 'none'
  })
}

function appendSubmitBtn(parent, label, onClick) {
  const btn = document.createElement('button')
  btn.type = 'button'
  btn.className = 'wa-submit-btn'
  btn.textContent = label
  btn.addEventListener('click', onClick)
  parent.appendChild(btn)
  return btn
}

export function createWaPreviewRenderer(host, { onAnswer, onProgress }) {
  function appendUserBubble(text) {
    if (!host || !text) return
    const wrap = document.createElement('div')
    wrap.className = 'wa-msg-user'
    const bubble = document.createElement('div')
    bubble.className = 'wa-answer-bubble'
    bubble.innerHTML = `<div class="wa-answer-text">${escapeHtml(personalizeWaText(text))}</div><div class="wa-answer-time">You ✓✓</div>`
    wrap.appendChild(bubble)
    host.appendChild(wrap)
    host.scrollTop = host.scrollHeight
  }

  function appendBotMessage(question, { intro = false, closing = false, onPick = () => {} } = {}) {
    if (!host) return null
    const q = normalizeQuestion(question, (question?.index || 1) - 1)
    const text = q.text || (intro || closing ? String(question) : '')
    if (!text && !intro && !closing) return null

    const replyType = intro ? 'intro' : closing ? 'closing' : q.reply_type
    const meta = WA_QUESTION_META[replyType] || WA_QUESTION_META.buttons
    const opts = q.options?.length ? q.options : defaultOptions(replyType)

    const wrap = document.createElement('div')
    wrap.className = 'wa-msg-bot'

    const bubble = document.createElement('div')
    bubble.className = 'wa-survey-bubble'

    const label = document.createElement('div')
    label.className = 'wa-survey-bubble-label'
    label.innerHTML = `<i class="ti ${meta.icon}"></i> ${escapeHtml(getWaSenderLabel())}`

    const body = document.createElement('div')
    body.className = 'wa-survey-bubble-text'
    if (intro || closing) {
      body.textContent = personalizeWaText(text)
    } else {
      body.innerHTML = `<strong>${q.index}. ${meta.label}</strong> — ${escapeHtml(personalizeWaText(text))}`
    }

    const qArea = document.createElement('div')
    qArea.className = 'wa-q-area'

    const pick = (value) => {
      disableWaInteractive(wrap)
      onPick(value)
    }

    if (intro) {
      appendSubmitBtn(qArea, 'Start survey →', () => pick('Start survey'))
    } else if (closing) {
      /* no controls */
    } else if (replyType === 'rating') {
      const row = document.createElement('div')
      row.className = 'wa-star-row'
      const starLabel = document.createElement('div')
      starLabel.className = 'wa-star-label'
      ;['1', '2', '3', '4', '5'].forEach((v) => {
        const star = document.createElement('button')
        star.type = 'button'
        star.className = 'wa-star-btn'
        star.textContent = '★'
        star.addEventListener('click', () => {
          row.querySelectorAll('.wa-star-btn').forEach((s, i) => {
            s.classList.toggle('lit', i < Number(v))
            s.disabled = true
          })
          starLabel.textContent = formatStarAnswer(Number(v))
          pick(formatStarAnswer(Number(v)))
        })
        row.appendChild(star)
      })
      row.appendChild(starLabel)
      qArea.appendChild(row)
    } else if (replyType === 'nps') {
      const row = document.createElement('div')
      row.className = 'wa-nps-row'
      const values = opts.length >= 9 ? opts : Array.from({ length: 11 }, (_, i) => String(i))
      values.forEach((v) => {
        const btn = document.createElement('button')
        btn.type = 'button'
        btn.className = 'wa-nps-btn'
        btn.textContent = v
        btn.addEventListener('click', () => {
          row.querySelectorAll('.wa-nps-btn').forEach((b) => { b.disabled = true })
          btn.classList.add('sel')
          pick(formatNpsAnswer(v))
        })
        row.appendChild(btn)
      })
      const labels = document.createElement('div')
      labels.className = 'wa-nps-labels'
      labels.innerHTML = '<span>Not likely</span><span>Very likely</span>'
      qArea.appendChild(row)
      qArea.appendChild(labels)
    } else if (replyType === 'likert') {
      const row = document.createElement('div')
      row.className = 'wa-likert-row'
      opts.forEach((opt) => {
        const btn = document.createElement('button')
        btn.type = 'button'
        btn.className = 'wa-likert-btn'
        btn.textContent = opt
        btn.addEventListener('click', () => {
          row.querySelectorAll('.wa-likert-btn').forEach((b) => { b.disabled = true })
          btn.classList.add('sel')
          pick(`📊 ${opt}`)
        })
        row.appendChild(btn)
      })
      qArea.appendChild(row)
    } else if (replyType === 'slider') {
      const wrapSl = document.createElement('div')
      wrapSl.className = 'wa-slider-wrap'
      wrapSl.innerHTML = `
        <div class="wa-slider-row">
          <input type="range" min="0" max="100" value="50" class="wa-slider-input" />
          <div class="wa-slider-val">50</div>
        </div>
        <div class="wa-slider-labels"><span>0</span><span>50</span><span>100</span></div>`
      const input = wrapSl.querySelector('.wa-slider-input')
      const val = wrapSl.querySelector('.wa-slider-val')
      input.addEventListener('input', () => { val.textContent = input.value })
      appendSubmitBtn(wrapSl, 'Confirm →', () => {
        input.disabled = true
        pick(`🎚️ Score: ${input.value}/100`)
      })
      qArea.appendChild(wrapSl)
    } else if (replyType === 'buttons' && opts.length <= 2) {
      const row = document.createElement('div')
      row.className = 'wa-yn-row'
      const yesBtn = document.createElement('button')
      yesBtn.type = 'button'
      yesBtn.className = 'wa-yn-btn'
      yesBtn.innerHTML = '<i class="ti ti-check"></i> Yes'
      const noBtn = document.createElement('button')
      noBtn.type = 'button'
      noBtn.className = 'wa-yn-btn'
      noBtn.innerHTML = '<i class="ti ti-x"></i> No'
      const yesVal = opts.find((o) => /yes/i.test(o)) || 'Yes'
      const noVal = opts.find((o) => /no/i.test(o)) || 'No'
      yesBtn.addEventListener('click', () => {
        yesBtn.classList.add('sel-yes')
        yesBtn.disabled = true
        noBtn.disabled = true
        pick(`✅ ${yesVal}`)
      })
      noBtn.addEventListener('click', () => {
        noBtn.classList.add('sel-no')
        yesBtn.disabled = true
        noBtn.disabled = true
        pick(`❌ ${noVal}`)
      })
      row.appendChild(yesBtn)
      row.appendChild(noBtn)
      qArea.appendChild(row)
    } else if (replyType === 'true_false') {
      const row = document.createElement('div')
      row.className = 'wa-tf-row'
      ;[
        ['✅ True', 'sel-true'],
        ['❌ False', 'sel-false'],
      ].forEach(([txt, cls]) => {
        const btn = document.createElement('button')
        btn.type = 'button'
        btn.className = 'wa-tf-btn'
        btn.textContent = txt
        btn.addEventListener('click', () => {
          row.querySelectorAll('.wa-tf-btn').forEach((b) => { b.disabled = true })
          btn.classList.add(cls)
          pick(txt)
        })
        row.appendChild(btn)
      })
      qArea.appendChild(row)
    } else if (replyType === 'single_choice' || (opts.length > 2 && replyType === 'buttons')) {
      const list = document.createElement('div')
      list.className = 'wa-choices'
      opts.forEach((opt) => {
        const btn = document.createElement('button')
        btn.type = 'button'
        btn.className = 'wa-choice-btn'
        btn.innerHTML = `<span class="wa-choice-radio"></span>${escapeHtml(opt)}`
        btn.addEventListener('click', () => {
          list.querySelectorAll('.wa-choice-btn').forEach((b) => { b.disabled = true })
          btn.classList.add('sel')
          pick(`🔘 ${opt}`)
        })
        list.appendChild(btn)
      })
      qArea.appendChild(list)
    } else if (replyType === 'multi') {
      const list = document.createElement('div')
      list.className = 'wa-multi-choices'
      const selected = new Set()
      opts.forEach((opt) => {
        const btn = document.createElement('button')
        btn.type = 'button'
        btn.className = 'wa-multi-btn'
        btn.innerHTML = `<span class="wa-multi-check"></span>${escapeHtml(opt)}`
        btn.addEventListener('click', () => {
          btn.classList.toggle('sel')
          const chk = btn.querySelector('.wa-multi-check')
          if (btn.classList.contains('sel')) {
            selected.add(opt)
            chk.textContent = '✓'
          } else {
            selected.delete(opt)
            chk.textContent = ''
          }
        })
        list.appendChild(btn)
      })
      appendSubmitBtn(list, 'Confirm selection →', () => {
        if (!selected.size) return
        list.querySelectorAll('.wa-multi-btn').forEach((b) => { b.disabled = true })
        pick(`☑️ ${[...selected].join(', ')}`)
      })
      qArea.appendChild(list)
    } else if (replyType === 'emoji') {
      const row = document.createElement('div')
      row.className = 'wa-emoji-row'
      opts.forEach((opt) => {
        const btn = document.createElement('button')
        btn.type = 'button'
        btn.className = 'wa-emoji-btn'
        const parts = opt.split(' ')
        btn.innerHTML = `<span>${escapeHtml(parts[0] || opt)}</span><span>${escapeHtml(parts.slice(1).join(' ') || '')}</span>`
        btn.addEventListener('click', () => {
          row.querySelectorAll('.wa-emoji-btn').forEach((b) => { b.disabled = true })
          btn.classList.add('sel')
          pick(opt)
        })
        row.appendChild(btn)
      })
      qArea.appendChild(row)
    } else if (replyType === 'thumbs') {
      const row = document.createElement('div')
      row.className = 'wa-thumb-row'
      ;[
        ['👍', 'sel-up', '👍 Thumbs up'],
        ['👎', 'sel-down', '👎 Thumbs down'],
      ].forEach(([icon, cls, ans]) => {
        const btn = document.createElement('button')
        btn.type = 'button'
        btn.className = 'wa-thumb-btn'
        btn.textContent = icon
        btn.addEventListener('click', () => {
          row.querySelectorAll('.wa-thumb-btn').forEach((b) => { b.disabled = true })
          btn.classList.add(cls)
          pick(ans)
        })
        row.appendChild(btn)
      })
      qArea.appendChild(row)
    } else if (replyType === 'time_slot') {
      const row = document.createElement('div')
      row.className = 'wa-time-slots'
      opts.forEach((opt) => {
        const btn = document.createElement('button')
        btn.type = 'button'
        btn.className = 'wa-time-slot'
        btn.textContent = opt
        btn.addEventListener('click', () => {
          row.querySelectorAll('.wa-time-slot').forEach((b) => { b.disabled = true })
          btn.classList.add('sel')
          pick(`🕐 ${opt}`)
        })
        row.appendChild(btn)
      })
      qArea.appendChild(row)
    } else if (replyType === 'date') {
      const input = document.createElement('input')
      input.type = 'date'
      input.className = 'wa-date-input'
      qArea.appendChild(input)
      appendSubmitBtn(qArea, 'Confirm date →', () => {
        if (!input.value) return
        input.disabled = true
        const d = new Date(input.value)
        const fmt = d.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })
        pick(`📅 ${fmt}`)
      })
    } else if (replyType === 'long_text') {
      const ta = document.createElement('textarea')
      ta.className = 'wa-open-text'
      ta.rows = 4
      ta.placeholder = 'Share your detailed answer…'
      qArea.appendChild(ta)
      appendSubmitBtn(qArea, 'Send →', () => {
        const v = ta.value.trim()
        if (!v) return
        ta.readOnly = true
        pick(`💬 ${v.slice(0, 80)}${v.length > 80 ? '…' : ''}`)
      })
    } else if (replyType === 'contact') {
      const email = document.createElement('input')
      email.type = 'email'
      email.className = 'wa-contact-input'
      email.placeholder = '📧 Email address'
      const phone = document.createElement('input')
      phone.type = 'tel'
      phone.className = 'wa-contact-input'
      phone.placeholder = '📞 Phone number'
      qArea.appendChild(email)
      qArea.appendChild(phone)
      appendSubmitBtn(qArea, 'Submit details →', () => {
        const parts = []
        if (email.value.trim()) parts.push(`📧 ${email.value.trim()}`)
        if (phone.value.trim()) parts.push(`📞 ${phone.value.trim()}`)
        if (!parts.length) return
        email.readOnly = true
        phone.readOnly = true
        pick(parts.join(' · '))
      })
    } else if (replyType === 'text') {
      const ta = document.createElement('textarea')
      ta.className = 'wa-open-text'
      ta.rows = 3
      ta.placeholder = 'Type your answer here…'
      qArea.appendChild(ta)
      appendSubmitBtn(qArea, 'Send →', () => {
        const v = ta.value.trim() || 'Thanks'
        ta.readOnly = true
        pick(`💬 ${v}`)
      })
    } else {
      const row = document.createElement('div')
      row.className = 'wa-yn-row'
      opts.slice(0, 2).forEach((opt) => {
        const btn = document.createElement('button')
        btn.type = 'button'
        btn.className = 'wa-yn-btn'
        btn.textContent = opt
        btn.addEventListener('click', () => {
          row.querySelectorAll('.wa-yn-btn').forEach((b) => { b.disabled = true })
          btn.classList.add(/yes|true|👍/i.test(opt) ? 'sel-yes' : 'sel-no')
          pick(opt)
        })
        row.appendChild(btn)
      })
      qArea.appendChild(row)
    }

    const time = document.createElement('div')
    time.className = 'wa-survey-bubble-time'
    time.textContent = new Date().toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })

    bubble.appendChild(label)
    bubble.appendChild(body)
    if (!closing) bubble.appendChild(qArea)
    bubble.appendChild(time)
    wrap.appendChild(bubble)
    host.appendChild(wrap)
    host.scrollTop = host.scrollHeight

    onProgress?.()
    return wrap
  }

  return { appendUserBubble, appendBotMessage }
}
