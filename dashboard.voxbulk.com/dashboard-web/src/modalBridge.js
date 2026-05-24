function esc(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function confirmDialog({ title, message, okLabel = 'Confirm', cancelLabel = 'Cancel', danger = false }) {
  return new Promise((resolve) => {
    if (typeof window.showConfirm !== 'function') {
      resolve(window.confirm(`${title}\n\n${message}`))
      return
    }
    const okBtn = document.getElementById('confirm-ok-btn')
    if (okBtn) {
      okBtn.classList.toggle('btnr', Boolean(danger))
      okBtn.classList.toggle('btng', !danger)
    }
    window.showConfirm(
      title,
      message,
      okLabel,
      () => resolve(true),
      () => resolve(false),
      cancelLabel,
    )
  })
}

function closePaymentModal() {
  document.getElementById('payment-overlay')?.classList.remove('show')
}

export function showSurveyPaymentModal({
  title = 'Pay for survey',
  amountLabel,
  breakdown = [],
  note = '',
  gocardlessAvailable = false,
  cashAvailable = true,
  promoAvailable = false,
  promoLabel = '',
}) {
  return new Promise((resolve) => {
    const overlay = document.getElementById('payment-overlay')
    if (!overlay) {
      resolve('cancel')
      return
    }

    document.getElementById('payment-title-text').textContent = title
    document.getElementById('payment-amount-text').textContent = amountLabel || '—'
    const breakdownHost = document.getElementById('payment-breakdown')
    if (breakdownHost) {
      breakdownHost.innerHTML = (breakdown.length ? breakdown : ['No breakdown available'])
        .map((line) => `<div class="payment-line">${esc(line)}</div>`)
        .join('')
    }
    const noteEl = document.getElementById('payment-note-text')
    if (noteEl) {
      noteEl.textContent = note || ''
      noteEl.style.display = note ? 'block' : 'none'
    }

    const gcBtn = document.getElementById('payment-gc-btn')
    const cashBtn = document.getElementById('payment-cash-btn')
    const promoBtn = document.getElementById('payment-promo-btn')
    if (gcBtn) gcBtn.style.display = gocardlessAvailable ? '' : 'none'
    if (cashBtn) cashBtn.style.display = cashAvailable ? '' : 'none'
    if (promoBtn) {
      promoBtn.style.display = promoAvailable ? '' : 'none'
      promoBtn.textContent = promoLabel || 'Use promo credits'
    }

    const finish = (choice) => {
      gcBtn?.removeEventListener('click', onGc)
      cashBtn?.removeEventListener('click', onCash)
      promoBtn?.removeEventListener('click', onPromo)
      cancelBtn?.removeEventListener('click', onCancel)
      overlay.removeEventListener('click', onBackdrop)
      closePaymentModal()
      resolve(choice)
    }
    const onGc = () => finish('gocardless')
    const onCash = () => finish('cash')
    const onPromo = () => finish('promo')
    const onCancel = () => finish('cancel')
    const onBackdrop = (e) => {
      if (e.target === overlay) finish('cancel')
    }

    gcBtn?.addEventListener('click', onGc)
    cashBtn?.addEventListener('click', onCash)
    promoBtn?.addEventListener('click', onPromo)
    const cancelBtn = document.getElementById('payment-cancel-btn')
    cancelBtn?.addEventListener('click', onCancel)
    overlay.addEventListener('click', onBackdrop)

    overlay.classList.add('show')
  })
}

export function showLaunchSummaryModal({ title = 'Confirm survey launch', lines = [] }) {
  const message = lines.filter(Boolean).join('\n')
  return confirmDialog({
    title,
    message,
    okLabel: 'Continue to payment',
    cancelLabel: 'Go back',
  })
}

export function initModalBridge() {
  window.confirmDialog = confirmDialog
  window.showSurveyPaymentModal = showSurveyPaymentModal
  window.showLaunchSummaryModal = showLaunchSummaryModal
}
