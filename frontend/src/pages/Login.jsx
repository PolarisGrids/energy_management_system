import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Zap, Eye, EyeOff } from 'lucide-react'
import useAuthStore from '@/stores/authStore'

export default function Login() {
  const [form, setForm] = useState({ username: '', password: '' })
  const [showPw, setShowPw] = useState(false)
  const { login, loading, error } = useAuthStore()
  const navigate = useNavigate()

  const submit = async (e) => {
    e.preventDefault()
    const ok = await login(form.username, form.password)
    if (ok) navigate('/')
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0A0F1E] relative overflow-hidden">
      {/* Background effects */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/3 left-1/4 w-[600px] h-[600px] rounded-full power-blur"
          style={{ background: 'radial-gradient(circle, #0A3690 0%, transparent 70%)' }} />
        <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] rounded-full power-blur"
          style={{ background: 'radial-gradient(circle, #02C9A8 0%, transparent 70%)' }} />
      </div>

      <div className="relative w-full max-w-md px-6">
        {/* Logo */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
            style={{ background: 'linear-gradient(45deg, #11ABBE, #3C63FF)' }}>
            <Zap size={32} className="text-white" />
          </div>
          <h1 className="font-black text-white" style={{ fontSize: 36 }}>POLARIS</h1>
          <p className="text-sky-blue font-medium mt-1">Smart Metering Operations Centre</p>
          <p className="text-white/40 mt-1" style={{ fontSize: 13 }}>Eskom Tender E2136DXLP</p>
        </div>

        {/* Card */}
        <div className="glass-card p-8">
          <h2 className="text-white font-bold text-xl mb-6">Sign in to SMOC</h2>

          <form onSubmit={submit} className="flex flex-col gap-4">
            <div>
              <label className="block text-accent-blue mb-2" style={{ fontSize: 12, fontWeight: 700 }}>
                USERNAME
              </label>
              <input
                type="text"
                autoComplete="username"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                className="w-full px-4 py-3 rounded-lg bg-white/5 border text-white placeholder-white/30 outline-none transition-all"
                style={{ borderColor: 'rgba(171,199,255,0.2)', fontSize: 14 }}
                onFocus={(e) => (e.target.style.borderColor = '#02C9A8')}
                onBlur={(e) => (e.target.style.borderColor = 'rgba(171,199,255,0.2)')}
                placeholder="e.g. operator"
                required
              />
            </div>

            <div>
              <label className="block text-accent-blue mb-2" style={{ fontSize: 12, fontWeight: 700 }}>
                PASSWORD
              </label>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  className="w-full px-4 py-3 pr-12 rounded-lg bg-white/5 border text-white placeholder-white/30 outline-none transition-all"
                  style={{ borderColor: 'rgba(171,199,255,0.2)', fontSize: 14 }}
                  onFocus={(e) => (e.target.style.borderColor = '#02C9A8')}
                  onBlur={(e) => (e.target.style.borderColor = 'rgba(171,199,255,0.2)')}
                  placeholder="Password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/70"
                >
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {error && (
              <div className="px-4 py-3 rounded-lg bg-status-critical/10 border border-status-critical/30 text-status-critical" style={{ fontSize: 13 }}>
                {error}
              </div>
            )}

            <button type="submit" disabled={loading} className="btn-primary mt-2 disabled:opacity-60 disabled:cursor-not-allowed">
              {loading ? 'Signing in…' : 'Sign In'}
            </button>
          </form>

        </div>
      </div>
    </div>
  )
}
