import React from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { getPartnerProvider } from '../lib/partnersCatalog'
import PartnersZohoPage from './PartnersZohoPage'
import PartnersProviderGenericPage from './PartnersProviderGenericPage'

/** Zoho gets a dedicated real admin console; other marketplaces keep the generic page. */
export default function PartnersProviderPage() {
  const { providerKey } = useParams()
  const provider = getPartnerProvider(providerKey)
  if (!provider) return <Navigate to='/partners/dashboard' replace />
  if (provider.key === 'zoho') return <PartnersZohoPage />
  return <PartnersProviderGenericPage />
}
