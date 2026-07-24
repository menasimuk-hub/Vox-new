import React from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { getPartnerProvider } from '../lib/partnersCatalog'
import PartnersZohoPage from './PartnersZohoPage'
import PartnersBreezyPage from './PartnersBreezyPage'
import PartnersProviderGenericPage from './PartnersProviderGenericPage'

export default function PartnersProviderPage() {
  const { providerKey } = useParams()
  const provider = getPartnerProvider(providerKey)
  if (!provider) return <Navigate to='/partners/dashboard' replace />
  if (provider.key === 'zoho') return <PartnersZohoPage />
  if (provider.key === 'breezy') return <PartnersBreezyPage />
  return <PartnersProviderGenericPage />
}
