import React, { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

/** Legacy route — industries management now lives on the main WA Survey page. */
export default function WaSurveyIndustries() {
  const navigate = useNavigate()
  useEffect(() => {
    navigate('/settings/wa-survey#wa-survey-industries', { replace: true })
  }, [navigate])
  return null
}
