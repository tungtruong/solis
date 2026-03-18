import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

function routePath() {
  const raw = String(window.location.pathname || '/').replace(/\/+$/, '')
  return raw || '/'
}

function navigateTo(path) {
  if (window.location.pathname === path) return
  window.history.pushState({}, '', path)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

function PublicPage({ title, description, primary, secondary }) {
  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24 }}>
      <section
        style={{
          width: 'min(760px, 100%)',
          borderRadius: 24,
          padding: 28,
          background: 'rgba(255,255,255,0.9)',
          border: '1px solid #d7e4f5',
          boxShadow: '0 16px 40px rgba(16, 41, 82, 0.12)',
        }}
      >
        <p style={{ margin: '0 0 8px', fontWeight: 700, letterSpacing: 0.4, color: '#0f2f57' }}>Solis</p>
        <h1 style={{ margin: '0 0 10px', fontSize: 'clamp(28px, 3.4vw, 42px)', color: '#0b203d' }}>{title}</h1>
        <p style={{ margin: 0, color: '#304865', lineHeight: 1.6 }}>{description}</p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 22 }}>
          {primary ? (
            <button
              type="button"
              onClick={() => navigateTo(primary.href)}
              style={{
                border: 'none',
                borderRadius: 12,
                padding: '11px 16px',
                background: '#0f4fa8',
                color: '#fff',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              {primary.label}
            </button>
          ) : null}
          {secondary ? (
            <button
              type="button"
              onClick={() => navigateTo(secondary.href)}
              style={{
                border: '1px solid #9bb6d8',
                borderRadius: 12,
                padding: '11px 16px',
                background: '#fff',
                color: '#0f2f57',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {secondary.label}
            </button>
          ) : null}
        </div>
      </section>
    </main>
  )
}

function RootRouter() {
  const [path, setPath] = useState(routePath())

  useEffect(() => {
    const onPopState = () => setPath(routePath())
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  if (path === '/SolisAcc' || path.startsWith('/SolisAcc/')) {
    return <App />
  }

  if (path === '/login') {
    return (
      <PublicPage
        title="Đăng nhập Solis"
        description="Trang đăng nhập riêng đã sẵn route. Khi bạn muốn, mình sẽ nối thẳng form thật và xác thực backend."
        primary={{ label: 'Vào SolisAcc', href: '/SolisAcc' }}
        secondary={{ label: 'Về Landing', href: '/' }}
      />
    )
  }

  if (path === '/onboard') {
    return (
      <PublicPage
        title="Onboard doanh nghiệp"
        description="Trang onboard riêng đã sẵn route để bạn làm luồng khai báo ban đầu trước khi vào hệ kế toán."
        primary={{ label: 'Vào SolisAcc', href: '/SolisAcc' }}
        secondary={{ label: 'Về Landing', href: '/' }}
      />
    )
  }

  return (
    <PublicPage
      title="Landing Page Solis"
      description="Website chính ở route gốc. Phân hệ kế toán đã tách sang route con /SolisAcc theo đúng yêu cầu của bạn."
      primary={{ label: 'Đi tới /login', href: '/login' }}
      secondary={{ label: 'Mở SolisAcc', href: '/SolisAcc' }}
    />
  )
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <RootRouter />
  </StrictMode>,
)
