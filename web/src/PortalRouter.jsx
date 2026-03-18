import { useEffect, useMemo, useState } from 'react'
import App from './App.jsx'
import './PortalRouter.css'

const STORAGE_TOKEN_KEY = 'solis.auth.token'
const STORAGE_EMAIL_KEY = 'solis.auth.email'
const STORAGE_HAS_PROFILE_KEY = 'solis.auth.hasCompanyProfile'

function normalizePathname(pathname) {
  const normalized = String(pathname || '/').replace(/\/+$/, '')
  return normalized || '/'
}

function currentPathname() {
  return normalizePathname(window.location.pathname)
}

function pushPath(pathname) {
  const normalized = normalizePathname(pathname)
  if (window.location.pathname === normalized) return
  window.history.pushState({}, '', normalized)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

function readSession() {
  if (typeof window === 'undefined') {
    return { token: '', email: '', hasCompanyProfile: false }
  }
  return {
    token: String(window.localStorage.getItem(STORAGE_TOKEN_KEY) || ''),
    email: String(window.localStorage.getItem(STORAGE_EMAIL_KEY) || ''),
    hasCompanyProfile: window.localStorage.getItem(STORAGE_HAS_PROFILE_KEY) === 'true',
  }
}

function writeSession(session) {
  window.localStorage.setItem(STORAGE_TOKEN_KEY, String(session.token || ''))
  window.localStorage.setItem(STORAGE_EMAIL_KEY, String(session.email || ''))
  window.localStorage.setItem(STORAGE_HAS_PROFILE_KEY, String(Boolean(session.hasCompanyProfile)))
}

function clearSession() {
  window.localStorage.removeItem(STORAGE_TOKEN_KEY)
  window.localStorage.removeItem(STORAGE_EMAIL_KEY)
  window.localStorage.removeItem(STORAGE_HAS_PROFILE_KEY)
}

function parseErrorMessage(payload, fallback) {
  if (!payload) return fallback
  if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail
  if (typeof payload.message === 'string' && payload.message.trim()) return payload.message
  return fallback
}

function PublicShell({ title, eyebrow, children, onNavigate, showBackToLanding = true }) {
  return (
    <div className="public-root">
      <div className="public-bg-orb public-bg-orb-a" aria-hidden="true" />
      <div className="public-bg-orb public-bg-orb-b" aria-hidden="true" />
      <header className="public-topbar">
        <button type="button" className="brand-chip" onClick={() => onNavigate('/')}>
          <span className="brand-logo">SO</span>
          <span className="brand-text">Solis</span>
        </button>
        <nav className="public-nav" aria-label="Điều hướng công khai">
          <button type="button" onClick={() => onNavigate('/login')}>Đăng nhập</button>
          <button type="button" onClick={() => onNavigate('/onboard')}>Onboard</button>
          <button type="button" className="nav-primary" onClick={() => onNavigate('/SolisAcc')}>SolisAcc</button>
        </nav>
      </header>
      <main className="public-main">
        <section className="public-panel">
          <p className="public-eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          {showBackToLanding ? (
            <button type="button" className="public-link" onClick={() => onNavigate('/')}>
              Ve trang chu
            </button>
          ) : null}
          {children}
        </section>
      </main>
    </div>
  )
}

function LandingPage({ onNavigate }) {
  return (
    <div className="public-root">
      <div className="public-bg-orb public-bg-orb-a" aria-hidden="true" />
      <div className="public-bg-orb public-bg-orb-b" aria-hidden="true" />
      <header className="public-topbar">
        <button type="button" className="brand-chip" onClick={() => onNavigate('/')}>
          <span className="brand-logo">SO</span>
          <span className="brand-text">Solis</span>
        </button>
        <nav className="public-nav" aria-label="Dieu huong landing">
          <button type="button" onClick={() => onNavigate('/login')}>Dang nhap</button>
          <button type="button" onClick={() => onNavigate('/onboard')}>Onboard</button>
          <button type="button" className="nav-primary" onClick={() => onNavigate('/SolisAcc')}>Vao SolisAcc</button>
        </nav>
      </header>

      <main className="landing-main">
        <section className="landing-hero">
          <p className="public-eyebrow">He sinh thai tai chinh AI cho doanh nghiep</p>
          <h1>
            Van hanh ke toan thoi gian thuc voi
            <span> Solis</span>
          </h1>
          <p>
            Landing page nay la cua website chinh. Phan he ke toan duoc tach sang duong dan /SolisAcc.
            Ban co the vao /login de dang nhap va /onboard de khai bao doanh nghiep.
          </p>
          <div className="landing-actions">
            <button type="button" className="cta-main" onClick={() => onNavigate('/login')}>
              Bat dau voi dang nhap
            </button>
            <button type="button" className="cta-sub" onClick={() => onNavigate('/SolisAcc')}>
              Mo SolisAcc ngay
            </button>
          </div>
        </section>

        <section className="landing-cards" aria-label="Gia tri noi bat">
          <article>
            <h2>Auto posting co kiem soat</h2>
            <p>Phan tich hoa don, map tai khoan theo TT133 va sinh but toan de ban phe duyet nhanh.</p>
          </article>
          <article>
            <h2>Ban dieu khien van hanh</h2>
            <p>Theo doi case, chung tu, bao cao va trang thai xu ly tren mot giao dien thong nhat.</p>
          </article>
          <article>
            <h2>San sang ket noi</h2>
            <p>Thong nhat login, onboard va workspace ke toan tren cac route rieng de mo rong ve sau.</p>
          </article>
        </section>
      </main>
    </div>
  )
}

function LoginPage({ onNavigate, session, setSession }) {
  const [email, setEmail] = useState(session.email || 'demo@wssmeas.local')
  const [password, setPassword] = useState('123456')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/auth/login-demo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: String(email || '').trim(), password: String(password || '') }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(parseErrorMessage(payload, 'Dang nhap that bai'))
      }
      const nextSession = {
        token: String(payload.token || ''),
        email: String(payload.email || email || ''),
        hasCompanyProfile: Boolean(payload.has_company_profile),
      }
      setSession(nextSession)
      writeSession(nextSession)
      onNavigate(nextSession.hasCompanyProfile ? '/SolisAcc' : '/onboard')
    } catch (submitError) {
      setError(submitError.message || 'Dang nhap that bai')
    } finally {
      setLoading(false)
    }
  }

  return (
    <PublicShell title="Dang nhap Solis" eyebrow="Route /login" onNavigate={onNavigate}>
      <form className="public-form" onSubmit={handleSubmit}>
        <label>
          Email
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </label>
        <label>
          Mat khau
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={3} />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <button type="submit" className="cta-main" disabled={loading}>
          {loading ? 'Dang xu ly...' : 'Dang nhap'}
        </button>
      </form>
    </PublicShell>
  )
}

function OnboardPage({ onNavigate, session, setSession }) {
  const [loadingProfile, setLoadingProfile] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [form, setForm] = useState({
    company_name: '',
    tax_code: '',
    address: '',
    fiscal_year_start: '2026-01-01',
    tax_declaration_cycle: 'thang',
    default_bank_account: '',
    accountant_email: session.email || '',
  })

  useEffect(() => {
    if (!session.token) return
    let ignore = false
    async function loadProfile() {
      setLoadingProfile(true)
      setError('')
      try {
        const response = await fetch('/api/company/profile', {
          headers: { Authorization: `Bearer ${session.token}` },
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(parseErrorMessage(payload, 'Khong tai duoc ho so cong ty'))
        }
        if (!ignore && payload.exists && payload.profile) {
          setForm((prev) => ({ ...prev, ...payload.profile }))
        }
      } catch (loadError) {
        if (!ignore) setError(loadError.message || 'Khong tai duoc ho so cong ty')
      } finally {
        if (!ignore) setLoadingProfile(false)
      }
    }
    loadProfile()
    return () => {
      ignore = true
    }
  }, [session.token])

  function updateField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!session.token) {
      setError('Ban can dang nhap truoc khi onboard')
      return
    }
    setSubmitting(true)
    setError('')
    setSuccess('')
    try {
      const response = await fetch('/api/company/profile', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.token}`,
        },
        body: JSON.stringify(form),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(parseErrorMessage(payload, 'Luu thong tin that bai'))
      }
      const nextSession = { ...session, hasCompanyProfile: true }
      setSession(nextSession)
      writeSession(nextSession)
      setSuccess('Da luu ho so cong ty thanh cong')
      setTimeout(() => onNavigate('/SolisAcc'), 450)
    } catch (submitError) {
      setError(submitError.message || 'Luu thong tin that bai')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <PublicShell title="Onboard doanh nghiep" eyebrow="Route /onboard" onNavigate={onNavigate}>
      <form className="public-form" onSubmit={handleSubmit}>
        <label>
          Ten cong ty
          <input value={form.company_name} onChange={(event) => updateField('company_name', event.target.value)} required />
        </label>
        <label>
          Ma so thue
          <input value={form.tax_code} onChange={(event) => updateField('tax_code', event.target.value)} required />
        </label>
        <label>
          Dia chi
          <input value={form.address} onChange={(event) => updateField('address', event.target.value)} required />
        </label>
        <label>
          Ngay bat dau nam tai chinh
          <input type="date" value={form.fiscal_year_start} onChange={(event) => updateField('fiscal_year_start', event.target.value)} required />
        </label>
        <label>
          Chu ky ke khai
          <select value={form.tax_declaration_cycle} onChange={(event) => updateField('tax_declaration_cycle', event.target.value)}>
            <option value="thang">Thang</option>
            <option value="quy">Quy</option>
          </select>
        </label>
        <label>
          Tai khoan ngan hang mac dinh
          <input value={form.default_bank_account} onChange={(event) => updateField('default_bank_account', event.target.value)} required />
        </label>
        <label>
          Email ke toan
          <input type="email" value={form.accountant_email} onChange={(event) => updateField('accountant_email', event.target.value)} required />
        </label>
        {loadingProfile ? <p className="form-note">Dang tai profile hien co...</p> : null}
        {error ? <p className="form-error">{error}</p> : null}
        {success ? <p className="form-success">{success}</p> : null}
        <button type="submit" className="cta-main" disabled={submitting}>
          {submitting ? 'Dang luu...' : 'Luu va vao SolisAcc'}
        </button>
      </form>
    </PublicShell>
  )
}

export default function PortalRouter() {
  const [path, setPath] = useState(currentPathname())
  const [session, setSession] = useState(readSession())

  useEffect(() => {
    const handlePopState = () => setPath(currentPathname())
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    const titleByPath = {
      '/': 'Solis',
      '/login': 'Solis | Login',
      '/onboard': 'Solis | Onboard',
    }
    const normalized = path.startsWith('/SolisAcc') ? '/SolisAcc' : path
    document.title = titleByPath[normalized] || 'Solis | SolisAcc'
  }, [path])

  const navigate = useMemo(
    () => (to) => {
      pushPath(to)
      setPath(currentPathname())
    },
    [],
  )

  function handleLogout() {
    clearSession()
    setSession({ token: '', email: '', hasCompanyProfile: false })
    navigate('/login')
  }

  if (path === '/SolisAcc' || path.startsWith('/SolisAcc/')) {
    return <App />
  }

  if (path === '/login') {
    return <LoginPage onNavigate={navigate} session={session} setSession={setSession} />
  }

  if (path === '/onboard') {
    if (!session.token) {
      return (
        <PublicShell title="Ban chua dang nhap" eyebrow="Route /onboard" onNavigate={navigate}>
          <p>Vui long dang nhap truoc khi khai bao thong tin doanh nghiep.</p>
          <div className="landing-actions">
            <button type="button" className="cta-main" onClick={() => navigate('/login')}>
              Di den login
            </button>
          </div>
        </PublicShell>
      )
    }
    return <OnboardPage onNavigate={navigate} session={session} setSession={setSession} />
  }

  return <LandingPage onNavigate={navigate} onLogout={handleLogout} />
}
