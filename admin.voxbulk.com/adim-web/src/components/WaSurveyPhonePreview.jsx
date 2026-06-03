import React, { useMemo, useState } from 'react'

function substituteVars(text, values = []) {
  let out = String(text || '')
  values.forEach((value, index) => {
    out = out.replace(new RegExp(`\\{\\{${index + 1}\\}\\}`, 'g'), String(value))
  })
  return out
}

function FlowStep({ step, active, onSelect }) {
  return (
    <button
      type="button"
      className={`waSurveyFlowStep${active ? ' is-active' : ''}`}
      onClick={() => onSelect?.(step.step)}
    >
      <span className="waSurveyFlowStepNum">{step.step}</span>
      <span>
        <strong>{step.title}</strong>
        {step.body ? <span className="muted">{step.body}</span> : null}
      </span>
    </button>
  )
}

export default function WaSurveyPhonePreview({
  businessName = 'Your business',
  renderedBody = '',
  footer = '',
  buttons = [],
  flowSteps = [],
  disclaimer = '',
  templateName = '',
  approvalStatus = '',
  syncStatus = '',
}) {
  const [activeStep, setActiveStep] = useState(1)
  const steps = Array.isArray(flowSteps) && flowSteps.length ? flowSteps : [{ step: 1, title: 'Template message', body: renderedBody }]
  const current = steps.find((s) => s.step === activeStep) || steps[0]
  const showTemplateBubble = current?.kind === 'template_outbound' || activeStep === 1
  const bubbleBody = showTemplateBubble ? renderedBody : current?.body || renderedBody
  const bubbleButtons = showTemplateBubble ? buttons : []

  const metaLine = useMemo(() => {
    const parts = []
    if (templateName) parts.push(templateName)
    if (approvalStatus) parts.push(approvalStatus)
    if (syncStatus) parts.push(syncStatus.replace(/_/g, ' '))
    return parts.join(' · ')
  }, [templateName, approvalStatus, syncStatus])

  return (
    <div className="waSurveyPreviewWrap">
      <div className="waSurveyPreviewMeta">
        <span className="waSurveyPreviewLabel">WhatsApp mobile preview</span>
        {metaLine ? <span className="muted">{metaLine}</span> : null}
      </div>
      <div className="waPhonePortrait waPhonePortraitPro" aria-label="WhatsApp mobile preview">
        <div className="waPhoneBezel">
          <div className="waPhoneNotch" />
          <div className="waPhoneScreen">
            <div className="waPhoneStatusBar">
              <span>9:41</span>
              <span className="waPhoneStatusIcons">
                <i className="ti ti-wifi" />
                <i className="ti ti-battery-4" />
              </span>
            </div>
            <div className="waPhoneChatHeader">
              <span className="waPhoneBack">‹</span>
              <span className="waPhoneAvatar">{String(businessName || 'B').slice(0, 1)}</span>
              <div className="waPhoneContact">
                <strong>{businessName}</strong>
                <span>online</span>
              </div>
            </div>
            <div className="waPhoneChatBody">
              <div className="waBubbleOutbound">
                <p className="waBubbleText">{substituteVars(bubbleBody)}</p>
                {footer ? <p className="waBubbleFooter">{footer}</p> : null}
                {bubbleButtons?.length ? (
                  <div className="waBubbleButtons">
                    {bubbleButtons.map((btn) => (
                      <div key={btn.label} className="waBubbleButton">
                        {btn.label}
                      </div>
                    ))}
                  </div>
                ) : null}
                <p className="waBubbleTime">9:41 ✓✓</p>
              </div>
              {!showTemplateBubble && current?.kind === 'user_action' ? (
                <div className="waBubbleInbound">
                  <p className="waBubbleText">{current.description || 'Recipient tapped a button'}</p>
                </div>
              ) : null}
              {!showTemplateBubble && current?.kind === 'survey_question' ? (
                <div className="waBubbleOutbound">
                  <p className="waBubbleText">{current.body}</p>
                  <p className="waBubbleTime">9:42</p>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
      {steps.length > 1 ? (
        <div className="waSurveyFlowNav">
          <div className="waSurveyFlowTitle">Simulated survey flow</div>
          {steps.map((step) => (
            <FlowStep key={step.step} step={step} active={step.step === activeStep} onSelect={setActiveStep} />
          ))}
        </div>
      ) : null}
      {disclaimer ? <p className="fieldHint">{disclaimer}</p> : null}
    </div>
  )
}
