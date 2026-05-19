import { useEffect, useState } from 'react'
import App from './App.jsx'
import { apiFetch, getAccessToken, logoutDashboard, redirectToSignIn } from './lib/api.js'

export default function AuthGate() {
  const [state, setState] = useState({ status: 'loading', session: null, error: '' })

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      const token = getAccessToken()
      if (!token) {
        redirectToSignIn()
        return
      }

      try {
        const [profile, org, onboarding, subscription] = await Promise.all([
          apiFetch('/auth/me'),
          apiFetch('/organisations/me').catch(() => null),
          apiFetch('/onboarding/status').catch(() => null),
          apiFetch('/billing/subscription').catch(() => null),
        ])
        if (cancelled) return
        setState({
          status: 'ready',
          error: '',
          session: {
            profile,
            org,
            onboarding,
            subscription,
          },
        })
      } catch (e) {
        if (cancelled) return
        if (e?.status === 401) {
          logoutDashboard()
          return
        }
        setState({
          status: 'error',
          error: e?.message || 'Could not verify your session.',
          session: null,
        })
      }
    }

    bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  if (state.status === 'loading') {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <h2>Loading your dashboard…</h2>
          <p className="muted">Checking your VoxBulk session.</p>
        </div>
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <h2>Session error</h2>
          <p className="muted">{state.error}</p>
          <div className="auth-actions">
            <button type="button" className="btn primary" onClick={() => redirectToSignIn()}>
              Go to sign in
            </button>
            <button type="button" className="btn soft" onClick={() => logoutDashboard()}>
              Log out
            </button>
          </div>
        </div>
      </div>
    )
  }

  return <App session={state.session} />
}
