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
  if (typeof window === 'undefined') return { token: '', email: '', hasCompanyProfile: false }
  return {
    token: String(window.sessionStorage.getItem(STORAGE_TOKEN_KEY) || ''),
    email: String(window.sessionStorage.getItem(STORAGE_EMAIL_KEY) || ''),
    hasCompanyProfile: window.sessionStorage.getItem(STORAGE_HAS_PROFILE_KEY) === 'true',
  }
}

function writeSession(session) {
  window.sessionStorage.setItem(STORAGE_TOKEN_KEY, String(session.token || ''))
  window.sessionStorage.setItem(STORAGE_EMAIL_KEY, String(session.email || ''))
  window.sessionStorage.setItem(STORAGE_HAS_PROFILE_KEY, String(Boolean(session.hasCompanyProfile)))
}

function clearSession() {
  window.sessionStorage.removeItem(STORAGE_TOKEN_KEY)
  window.sessionStorage.removeItem(STORAGE_EMAIL_KEY)
  window.sessionStorage.removeItem(STORAGE_HAS_PROFILE_KEY)
}

function parseErrorMessage(payload, fallback) {
  if (!payload) return fallback
  if (typeof payload.code === 'string' && payload.code.trim()) return `${fallback} (${payload.code})`
  return fallback
}

function isProfileComplete(profile) {
  if (!profile || typeof profile !== 'object') return false
  const requiredFields = [
    'company_name',
    'tax_code',
    'address',
    'legal_representative',
    'established_date',
    'accounting_software_start_date',
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
          <button type="button" className="nav-primary" onClick={() => onNavigate('/login')}>Đăng nhập</button>
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
            Sau khi đăng nhập, hệ thống sẽ chuyển bạn vào Onboard. Bạn có thể chọn công ty đã có hoặc tạo công ty mới.
            Khi thông tin đầy đủ, hệ thống mới vào SolisAcc.
          </p>
          <div className="landing-actions">
            <button type="button" className="cta-main" onClick={() => onNavigate('/login')}>
              Bắt đầu với Đăng nhập
            </button>
          </div>
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
        throw new Error(parseErrorMessage(payload, 'Đăng nhập không thành công. Vui lòng thử lại.'))
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
      setError(submitError.message || 'Đăng nhập không thành công. Vui lòng thử lại.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <PublicShell title="Đăng nhập Solis" eyebrow="Bảo mật cao" onNavigate={onNavigate}>
      <form className="public-form" onSubmit={handleSubmit} autoComplete="off">
        <label>
          Email
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="username" />
        </label>
        <label>
          Mật khẩu
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={3} autoComplete="current-password" />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <button type="submit" className="cta-main" disabled={loading}>
          {loading ? 'Đang xác thực...' : 'Đăng nhập'}
        </button>
      </form>
    </PublicShell>
  )
}

function OnboardPage({ onNavigate, session, setSession }) {
  const [companies, setCompanies] = useState([])
  const [loadingCompanies, setLoadingCompanies] = useState(false)
  const [lookingUpTax, setLookingUpTax] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [createMode, setCreateMode] = useState(false)
  const [form, setForm] = useState({
    company_id: '',
    tax_code: '',
    company_name: '',
    address: '',
    legal_representative: '',
    established_date: '',
    accounting_software_start_date: new Date().toISOString().slice(0, 10),
    fiscal_year_start: new Date().toISOString().slice(0, 10),
    tax_declaration_cycle: 'thang',
    default_bank_account: '',
    accountant_email: session.email || '',
  })

  useEffect(() => {
    if (!session.token) return
    let ignore = false
    async function loadCompanies() {
      setLoadingCompanies(true)
      setError('')
      try {
        const response = await fetch('/api/onboard/companies', {
          headers: { Authorization: `Bearer ${session.token}` },
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(parseErrorMessage(payload, 'Không tải được danh sách công ty'))
        }
        const items = Array.isArray(payload.items) ? payload.items : []
        if (!ignore) {
          setCompanies(items)
          if (!items.length) {
            setCreateMode(true)
          }
        }
      } catch (loadError) {
        if (!ignore) setError(loadError.message || 'Không tải được danh sách công ty')
      } finally {
        if (!ignore) setLoadingCompanies(false)
      }
    }
    loadCompanies()
    return () => {
      ignore = true
    }
  }, [session.token])

  function updateField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  async function selectExistingCompany(companyId) {
    if (!session.token) return
    setError('')
    setSuccess('')
    try {
      const response = await fetch('/api/onboard/select-company', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.token}`,
        },
        body: JSON.stringify({ company_id: companyId }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(parseErrorMessage(payload, 'Không thể chọn công ty'))
      }
      if (payload.profile && typeof payload.profile === 'object') {
        setForm((prev) => ({ ...prev, ...payload.profile }))
      }
      if (payload.is_complete) {
        const nextSession = { ...session, hasCompanyProfile: true }
        setSession(nextSession)
        writeSession(nextSession)
        onNavigate('/SolisAcc')
        return
      }
      setCreateMode(true)
      setSuccess('Đã chọn công ty. Vui lòng bổ sung thông tin còn thiếu để tiếp tục.')
    } catch (selectError) {
      setError(selectError.message || 'Không thể chọn công ty')
    }
  }

  async function lookupByTaxCode() {
    const tax = String(form.tax_code || '').trim()
    if (!tax) {
      setError('Vui lòng nhập mã số thuế trước khi tra cứu.')
      return
    }
    if (!session.token) {
      setError('Phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại.')
      return
    }
    setLookingUpTax(true)
    setError('')
    try {
      const query = new URLSearchParams({ tax_code: tax })
      const response = await fetch(`/api/onboard/company-lookup?${query.toString()}`, {
        headers: { Authorization: `Bearer ${session.token}` },
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(parseErrorMessage(payload, 'Không tra cứu được mã số thuế'))
      }
      const profile = payload.profile && typeof payload.profile === 'object' ? payload.profile : null
      if (!profile) {
        setSuccess('Không có dữ liệu tự động. Bạn có thể nhập thủ công.')
        return
      }
      setForm((prev) => ({
        ...prev,
        tax_code: String(profile.tax_code || prev.tax_code || ''),
        company_name: String(profile.company_name || prev.company_name || ''),
        address: String(profile.address || prev.address || ''),
        legal_representative: String(profile.legal_representative || prev.legal_representative || ''),
        established_date: String(profile.established_date || prev.established_date || ''),
        company_id: String(profile.company_id || prev.company_id || ''),
      }))
      setSuccess('Đã điền thông tin doanh nghiệp từ dữ liệu tra cứu.')
    } catch (lookupError) {
      setError(lookupError.message || 'Không tra cứu được mã số thuế')
    } finally {
      setLookingUpTax(false)
    }
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
      const response = await fetch('/api/onboard/companies', {
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
      const completed = Boolean(payload.is_complete) && isProfileComplete(payload.profile)
      const nextSession = { ...session, hasCompanyProfile: completed }
      setSession(nextSession)
      writeSession(nextSession)
      if (completed) {
        setSuccess('Đã lưu thông tin công ty. Đang chuyển vào SolisAcc...')
        setTimeout(() => onNavigate('/SolisAcc'), 400)
        return
      }
      setSuccess('Đã lưu nháp. Vui lòng hoàn thiện đầy đủ thông tin để vào SolisAcc.')
    } catch (submitError) {
      setError(submitError.message || 'Lưu thông tin thất bại')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <PublicShell title="Onboard doanh nghiệp" eyebrow="Bảo mật cao" onNavigate={onNavigate}>
      <p className="form-note">Bắt đầu từ mã số thuế để tra cứu thông tin pháp lý tự động.</p>

      {!createMode && companies.length > 0 ? (
        <div className="company-list-wrap">
          <h2 className="company-list-title">Chọn công ty đã có</h2>
          <div className="company-list">
            {companies.map((item) => (
              <article key={item.company_id} className="company-card">
                <p className="company-name">{item.company_name || 'Chưa có tên công ty'}</p>
                <p className="company-meta">MST: {item.tax_code || '-'}</p>
                <p className="company-meta">{item.address || 'Chưa có địa chỉ'}</p>
                <button type="button" className="cta-main" onClick={() => selectExistingCompany(item.company_id)}>
                  Dùng công ty này
                </button>
              </article>
            ))}
          </div>
          <button type="button" className="cta-sub cta-sub-solid" onClick={() => setCreateMode(true)}>
            Tạo công ty mới
          </button>
        </div>
      ) : null}

      {createMode ? (
        <form className="public-form" onSubmit={handleSubmit} autoComplete="off">
          <label>
            Mã số thuế
            <div className="inline-row">
              <input value={form.tax_code} onChange={(event) => updateField('tax_code', event.target.value)} required />
              <button type="button" className="cta-sub cta-sub-solid" onClick={lookupByTaxCode} disabled={lookingUpTax}>
                {lookingUpTax ? 'Đang tra cứu...' : 'Tra cứu MST'}
              </button>
            </div>
          </label>
          <label>
            Tên doanh nghiệp
            <input value={form.company_name} onChange={(event) => updateField('company_name', event.target.value)} required />
          </label>
          <label>
            Địa chỉ
            <input value={form.address} onChange={(event) => updateField('address', event.target.value)} required />
          </label>
          <label>
            Người đại diện pháp luật
            <input value={form.legal_representative} onChange={(event) => updateField('legal_representative', event.target.value)} required />
          </label>
          <label>
            Ngày thành lập
            <input type="date" value={form.established_date} onChange={(event) => updateField('established_date', event.target.value)} required />
          </label>
          <label>
            Ngày bắt đầu phần mềm kế toán
            <input type="date" value={form.accounting_software_start_date} onChange={(event) => updateField('accounting_software_start_date', event.target.value)} required />
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
          {loadingCompanies ? <p className="form-note">Đang tải danh sách công ty...</p> : null}
          {error ? <p className="form-error">{error}</p> : null}
          {success ? <p className="form-success">{success}</p> : null}
          <button type="submit" className="cta-main" disabled={submitting}>
            {submitting ? 'Đang lưu...' : 'Lưu thông tin và tiếp tục'}
          </button>
          {companies.length > 0 ? (
            <button type="button" className="cta-sub cta-sub-solid" onClick={() => setCreateMode(false)}>
              Quay lại danh sách công ty
            </button>
          ) : null}
        </form>
      ) : null}
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
      '/login': 'Solis | Đăng nhập',
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
        <PublicShell title="Bạn chưa đăng nhập" eyebrow="Bảo mật cao" onNavigate={navigate}>
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

  return <LandingPage onNavigate={navigate} />
}
