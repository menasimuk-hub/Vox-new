import React, { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ShoppingBag } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { loginRestaurant } from '@/lib/api'

export default function Login() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [email, setEmail] = useState(() => searchParams.get('email') || '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const onSubmit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await loginRestaurant(email.trim(), password)
      navigate('/')
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-background px-4">
      <Card className="w-full max-w-md shadow-[var(--shadow-soft)]">
        <CardHeader className="text-center">
          <div className="mx-auto mb-3 grid h-14 w-14 place-items-center rounded-2xl gradient-energy text-white shadow-[var(--shadow-glow)]">
            <ShoppingBag className="h-7 w-7" />
          </div>
          <CardTitle className="text-2xl font-black">Yallasay Restaurant</CardTitle>
          <p className="text-sm text-muted-foreground">Sign in to manage orders, menu & offers</p>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={onSubmit}>
            <div>
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </div>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            <Button type="submit" className="w-full gradient-energy text-white" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in'}
            </Button>
            <p className="text-center text-xs text-muted-foreground">
              <Link to="/showall" className="underline underline-offset-2">Demo restaurant directory</Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
