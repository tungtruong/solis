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

function isProfileComplete(profile) {
  if (!profile || typeof profile !== 'object') return false
  const requiredFields = [
    'company_name',
    'tax_code',
    'address',
    'fiscal_year_start',
    'tax_declaration_cycle',
    'default_bank_account',
    'accountant_email',
  ]
  return requiredFields.every((field) => String(profile[field] || '').trim().length > 0)
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
        </nav>
      </header>
      <main className="public-main">
        <section className="public-panel">
          <p className="public-eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          {showBackToLanding ? (
            <button type="button" className="public-link" onClick={() => onNavigate('/')}>
              Về trang chủ
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
        <nav className="public-nav" aria-label="Điều hướng landing">
          <button type="button" className="nav-primary" onClick={() => onNavigate('/login')}>Đăng nhập</button>
        </nav>
      </header>

      <main className="landing-main">
        <section className="landing-hero">
          <p className="public-eyebrow">Hệ sinh thái tài chính AI cho doanh nghiệp</p>
          <h1>
            Vận hành kế toán thời gian thực với
            <span> Solis</span>
          </h1>
          <p>
            Đây là landing page của website chính. Sau khi đăng nhập, hệ thống sẽ đưa bạn đến Onboard.
            Khi thông tin doanh nghiệp đã đầy đủ, bạn sẽ được chuyển vào trang SolisAcc.
          </p>
          <div className="landing-actions">
            <button type="button" className="cta-main" onClick={() => onNavigate('/login')}>
              Bắt đầu với Đăng nhập
            </button>
          </div>
        </section>

        <section className="landing-cards" aria-label="Giá trị nổi bật">
          <article>
            <h2>Auto posting có kiểm soát</h2>
            <p>Phân tích hóa đơn, map tài khoản theo TT133 và sinh bút toán để bạn phê duyệt nhanh.</p>
          </article>
          <article>
            <h2>Bảng điều khiển vận hành</h2>
            <p>Theo dõi case, chứng từ, báo cáo và trạng thái xử lý trên một giao diện thống nhất.</p>
          </article>
          <article>
            <h2>Sẵn sàng kết nối</h2>
            <p>Thống nhất login, onboard và workspace kế toán trên các route riêng để mở rộng về sau.</p>
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
        throw new Error(parseErrorMessage(payload, 'Đăng nhập thất bại'))
      }
      const nextSession = {
        token: String(payload.token || ''),
        email: String(payload.email || email || ''),
        hasCompanyProfile: Boolean(payload.has_company_profile),
      }
      setSession(nextSession)
      writeSession(nextSession)
      onNavigate('/onboard')
    } catch (submitError) {
      setError(submitError.message || 'Đăng nhập thất bại')
    } finally {
      setLoading(false)
    }
  }

  return (
    <PublicShell title="Đăng nhập Solis" eyebrow="Route /login" onNavigate={onNavigate}>
      <form className="public-form" onSubmit={handleSubmit}>
        <label>
          Email
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </label>
        <label>
          Mật khẩu
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={3} />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <button type="submit" className="cta-main" disabled={loading}>
          {loading ? 'Đang xử lý...' : 'Đăng nhập'}
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
          throw new Error(parseErrorMessage(payload, 'Không tải được hồ sơ công ty'))
        }
        if (!ignore && payload.exists && payload.profile) {
          const profile = payload.profile
          setForm((prev) => ({ ...prev, ...profile }))
          if (isProfileComplete(profile)) {
            const nextSession = { ...session, hasCompanyProfile: true }
            setSession(nextSession)
            writeSession(nextSession)
            onNavigate('/SolisAcc')
          }
        }
      } catch (loadError) {
        if (!ignore) setError(loadError.message || 'Không tải được hồ sơ công ty')
      } finally {
        if (!ignore) setLoadingProfile(false)
      }
    }
    loadProfile()
    return () => {
      ignore = true
    }
  }, [onNavigate, session, session.token, setSession])

  function updateField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!session.token) {
      setError('Bạn cần đăng nhập trước khi onboard')
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
        throw new Error(parseErrorMessage(payload, 'Lưu thông tin thất bại'))
      }
      const nextSession = { ...session, hasCompanyProfile: true }
      setSession(nextSession)
      writeSession(nextSession)
      setSuccess('Đã lưu hồ sơ công ty thành công')
      setTimeout(() => onNavigate('/SolisAcc'), 450)
    } catch (submitError) {
      setError(submitError.message || 'Lưu thông tin thất bại')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <PublicShell title="Onboard doanh nghiệp" eyebrow="Route /onboard" onNavigate={onNavigate}>
      <form className="public-form" onSubmit={handleSubmit}>
        <label>
          Tên công ty
          <input value={form.company_name} onChange={(event) => updateField('company_name', event.target.value)} required />
        </label>
        <label>
          Mã số thuế
          <input value={form.tax_code} onChange={(event) => updateField('tax_code', event.target.value)} required />
        </label>
        <label>
          Địa chỉ
          <input value={form.address} onChange={(event) => updateField('address', event.target.value)} required />
        </label>
        <label>
          Ngày bắt đầu năm tài chính
          <input type="date" value={form.fiscal_year_start} onChange={(event) => updateField('fiscal_year_start', event.target.value)} required />
        </label>
        <label>
          Chu kỳ kê khai
          <select value={form.tax_declaration_cycle} onChange={(event) => updateField('tax_declaration_cycle', event.target.value)}>
            <option value="thang">Tháng</option>
            <option value="quy">Quý</option>
          </select>
        </label>
        <label>
          Tài khoản ngân hàng mặc định
          <input value={form.default_bank_account} onChange={(event) => updateField('default_bank_account', event.target.value)} required />
        </label>
        <label>
          Email kế toán
          <input type="email" value={form.accountant_email} onChange={(event) => updateField('accountant_email', event.target.value)} required />
        </label>
        {loadingProfile ? <p className="form-note">Đang tải hồ sơ hiện có...</p> : null}
        {error ? <p className="form-error">{error}</p> : null}
        {success ? <p className="form-success">{success}</p> : null}
        <button type="submit" className="cta-main" disabled={submitting}>
          {submitting ? 'Đang lưu...' : 'Lưu và vào SolisAcc'}
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
    if (!session.token) {
      return <LoginPage onNavigate={navigate} session={session} setSession={setSession} />
    }
    if (!session.hasCompanyProfile) {
      return <OnboardPage onNavigate={navigate} session={session} setSession={setSession} />
    }
    return <App />
  }

  if (path === '/login') {
    return <LoginPage onNavigate={navigate} session={session} setSession={setSession} />
  }

  if (path === '/onboard') {
    if (!session.token) {
      return (
        <PublicShell title="Bạn chưa đăng nhập" eyebrow="Route /onboard" onNavigate={navigate}>
          <p>Vui lòng đăng nhập trước khi khai báo thông tin doanh nghiệp.</p>
          <div className="landing-actions">
            <button type="button" className="cta-main" onClick={() => navigate('/login')}>
              Đi đến đăng nhập
            </button>
          </div>
        </PublicShell>
      )
    }
    return <OnboardPage onNavigate={navigate} session={session} setSession={setSession} />
  }

  return <LandingPage onNavigate={navigate} onLogout={handleLogout} />
}
