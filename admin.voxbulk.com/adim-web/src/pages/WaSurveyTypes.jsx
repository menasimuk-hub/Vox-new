import React, { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import WaSurveyIndustrySection from '../components/WaSurveyIndustrySection'

export default function WaSurveyTypes() {
  const location = useLocation()
  const [msg, setMsg] = useState('')

  useEffect(() => {
    if (location.state?.waSurveyMsg) {
      setMsg(String(location.state.waSurveyMsg))
      window.history.replaceState({}, document.title)
    }
  }, [location.state])

  return (
    <>
      <div className="pageTop">
        <div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
            Platform Settings
          </div>
          <h1>WA Survey</h1>
          <p className="pageLead">
            Operational overview of industries and WhatsApp templates. Manage industries, counts, and Telnyx-linked templates from here.
          </p>
        </div>
        <div className="pageTopActions">
          <Link className="btn" to="/settings/wa-survey/system-templates">
            <i className="ti ti-template" /> System templates
          </Link>
          <Link className="btn" to="/settings/wa-survey/simulator">
            <i className="ti ti-flask" /> Flow simulator
          </Link>
        </div>
      </div>

      {msg ? <div className="alert ok" style={{ marginBottom: 16 }}><strong>{msg}</strong></div> : null}

      <WaSurveyIndustrySection />
    </>
  )
}
