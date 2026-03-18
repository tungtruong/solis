import { useMemo, useState } from 'react'
import './App.css'

const STATUS_META = {
  cho_duyet: { label: 'Cho duyet', className: 'status-cho_duyet' },
  da_post: { label: 'Da post', className: 'status-da_post' },
  dang_xu_ly: { label: 'Dang xu ly', className: 'status-dang_xu_ly' },
}

const CATEGORY_RULES = [
  {
    label: 'Chi phi Marketing',
    direction: 'expense',
    keywords: ['quang cao', 'marketing', 'zalo', 'facebook', 'google ads'],
    debit: '6427 - Chi phi Marketing',
    credit: '112 - Tien gui ngan hang',
  },
  {
    label: 'Chi phi Van phong',
    direction: 'expense',
    keywords: ['van phong', 'muc in', 'may in', 'thiet bi', 'office'],
    debit: '6423 - Chi phi van phong',
    credit: '112 - Tien gui ngan hang',
  },
  {
    label: 'Chi phi Nhan su',
    direction: 'expense',
    keywords: ['luong', 'nhan su', 'bao hiem', 'phu cap'],
    debit: '6421 - Chi phi nhan su',
    credit: '334 - Phai tra nguoi lao dong',
  },
  {
    label: 'Doanh thu Dich vu',
    direction: 'income',
    keywords: ['thu tien', 'doanh thu', 'khach hang thanh toan', 'ban hang'],
    debit: '112 - Tien gui ngan hang',
    credit: '511 - Doanh thu dich vu',
  },
  {
    label: 'Thu hoi Cong no',
    direction: 'income',
    keywords: ['thu no', 'thu hoi cong no', 'cong no'],
    debit: '112 - Tien gui ngan hang',
    credit: '131 - Phai thu khach hang',
  },
]

const INITIAL_DOSSIERS = [
  {
    id: 'HS-0001',
    title: 'Chi phi quang cao thang 3',
    code: 'TT133-0001',
    partner: 'Cong ty Truyen thong Sao Xanh',
    amount: 3000000,
    date: '2026-03-17',
    status: 'cho_duyet',
    category: 'Chi phi Marketing',
    confidence: 0.89,
    documents: [
      { name: 'hoa_don_ads_03_2026.pdf', size: 251000, uploadedAt: '2026-03-17T09:10:00Z' },
    ],
    reasoning: [
      'Phat hien tu khoa quang cao va zalo trong mo ta.',
      'Khoan muc duoc de xuat theo huong chi phi marketing.',
      'Cho ke toan xac nhan buoc post but toan.',
    ],
    events: [
      {
        id: 'EV-1',
        type: 'user',
        title: 'Nguoi dung gui mo ta',
        body: 'Chi 3 trieu quang cao Zalo thang 3',
        time: '09:05',
      },
      {
        id: 'EV-2',
        type: 'ai',
        title: 'AI de xuat but toan',
        body: 'No 6427 / Co 112 so tien 3,000,000 VND. Do tin cay 89%.',
        time: '09:06',
      },
    ],
  },
  {
    id: 'HS-0002',
    title: 'Thu tien khach hang du an A',
    code: 'TT133-0002',
    partner: 'Cong ty Co phan GreenPath',
    amount: 12500000,
    date: '2026-03-16',
    status: 'da_post',
    category: 'Doanh thu Dich vu',
    confidence: 0.94,
    documents: [],
    reasoning: ['Giao dich da post vao he thong va cap nhat metric doanh thu.'],
    events: [
      {
        id: 'EV-3',
        type: 'result',
        title: 'But toan da post',
        body: 'No 112 / Co 511 so tien 12,500,000 VND.',
        time: '10:20',
      },
    ],
  },
]

function todayISO() {
  return new Date().toISOString().slice(0, 10)
}

function pad2(value) {
  return String(value).padStart(2, '0')
}

function formatDateVi(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return `${pad2(date.getDate())}/${pad2(date.getMonth() + 1)}/${date.getFullYear()}`
}

function formatDateTimeVi(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return `${formatDateVi(iso)} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`
}

function formatCurrency(value) {
  return `${new Intl.NumberFormat('vi-VN').format(Math.round(Number(value) || 0))} d`
}

function formatFileSize(bytes) {
  const value = Number(bytes) || 0
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(2)} MB`
  if (value >= 1024) return `${Math.round(value / 1024)} KB`
  return `${value} B`
}

function inferRule(text) {
  const normalized = String(text || '').toLowerCase()
  return CATEGORY_RULES.find((rule) => rule.keywords.some((keyword) => normalized.includes(keyword)))
}

function parseAmount(text) {
  const source = String(text || '').toLowerCase()
  const withTrieu = source.match(/(\d+(?:[.,]\d+)?)\s*trieu/)
  if (withTrieu) {
    return Math.round(Number(withTrieu[1].replace(',', '.')) * 1000000)
  }

  const raw = source.match(/\d[\d.,]*/)
  if (!raw) return 0
  const numeric = raw[0].replace(/[.,]/g, '')
  return Number(numeric) || 0
}

function App() {
  const [search, setSearch] = useState('')
  const [dossiers, setDossiers] = useState(INITIAL_DOSSIERS)
  const [selectedId, setSelectedId] = useState(INITIAL_DOSSIERS[0]?.id ?? null)
  const [chatInput, setChatInput] = useState('')
  const [toast, setToast] = useState('')

  const selected = useMemo(() => dossiers.find((item) => item.id === selectedId) || null, [dossiers, selectedId])

  const filteredDossiers = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return dossiers
    return dossiers.filter((item) => [item.title, item.code, item.partner].join(' ').toLowerCase().includes(q))
  }, [dossiers, search])

  const metrics = useMemo(() => {
    return dossiers.reduce(
      (acc, item) => {
        const rule = CATEGORY_RULES.find((value) => value.label === item.category)
        if (rule?.direction === 'expense') acc.expense += item.amount
        if (rule?.direction === 'income') acc.revenue += item.amount
        if (item.status === 'da_post') acc.posted += 1
        return acc
      },
      { expense: 0, revenue: 0, posted: 0 },
    )
  }, [dossiers])

  const pendingCount = useMemo(() => dossiers.filter((item) => item.status === 'cho_duyet').length, [dossiers])

  function showToast(message) {
    setToast(message)
    window.setTimeout(() => setToast(''), 2000)
  }

  function updateSelected(mutator) {
    if (!selected) return
    setDossiers((prev) => prev.map((item) => (item.id === selected.id ? mutator(item) : item)))
  }

  function handleNewDossier() {
    const index = dossiers.length + 1
    const id = `HS-${String(index).padStart(4, '0')}`
    const dossier = {
      id,
      title: `Ho so moi #${index}`,
      code: `TT133-${String(index).padStart(4, '0')}`,
      partner: 'Chua ro doi tac',
      amount: 0,
      date: todayISO(),
      status: 'dang_xu_ly',
      category: 'Chua phan loai',
      confidence: 0,
      documents: [],
      reasoning: ['Ho so vua khoi tao. Hay mo ta giao dich de AI de xuat but toan.'],
      events: [
        {
          id: `${id}-EV-1`,
          type: 'ai',
          title: 'Khoi tao ho so',
          body: 'Ban co the nhap: Chi 12 trieu thue van phong thang nay.',
          time: `${pad2(new Date().getHours())}:${pad2(new Date().getMinutes())}`,
        },
      ],
    }

    setDossiers((prev) => [dossier, ...prev])
    setSelectedId(id)
    showToast('Da tao ho so moi')
  }

  function handleChatSubmit(event) {
    event.preventDefault()
    if (!chatInput.trim() || !selected) return

    const userText = chatInput.trim()
    const now = new Date()
    const clock = `${pad2(now.getHours())}:${pad2(now.getMinutes())}`
    const amount = parseAmount(userText)
    const rule = inferRule(userText)
    const confidence = rule ? 0.86 : 0.62

    updateSelected((current) => {
      const nextStatus = confidence >= 0.8 ? 'cho_duyet' : 'dang_xu_ly'
      const aiBody = rule
        ? `De xuat: No ${rule.debit} / Co ${rule.credit} | So tien ${formatCurrency(amount)} | Do tin cay ${Math.round(confidence * 100)}%.`
        : `Can bo sung thong tin chung tu de xac dinh tai khoan. Do tin cay ${Math.round(confidence * 100)}%.`

      return {
        ...current,
        title: current.title.startsWith('Ho so moi') ? userText.slice(0, 42) : current.title,
        amount: amount || current.amount,
        status: nextStatus,
        category: rule?.label || current.category,
        confidence,
        reasoning: [
          rule
            ? `AI map giao dich vao nhom ${rule.label}.`
            : 'AI chua tim thay nhom giao dich phu hop voi confidence cao.',
          ...current.reasoning,
        ].slice(0, 8),
        events: [
          ...current.events,
          {
            id: `${current.id}-U-${Date.now()}`,
            type: 'user',
            title: 'Nguoi dung gui mo ta',
            body: userText,
            time: clock,
          },
          {
            id: `${current.id}-A-${Date.now() + 1}`,
            type: 'ai',
            title: 'AI de xuat but toan',
            body: aiBody,
            time: clock,
          },
        ],
      }
    })

    setChatInput('')
  }

  function handleUpload(event) {
    const files = Array.from(event.target.files || [])
    if (!files.length || !selected) return

    updateSelected((current) => ({
      ...current,
      documents: [
        ...files.map((file) => ({
          name: file.name,
          size: file.size,
          uploadedAt: new Date().toISOString(),
        })),
        ...current.documents,
      ],
      reasoning: ['Da nhan file chung tu. AI se uu tien du lieu OCR/file metadata.', ...current.reasoning].slice(0, 8),
    }))

    showToast(`Da tai len ${files.length} chung tu`)
    event.target.value = ''
  }

  return (
    <>
      <div className="bg-orb orb-1" />
      <div className="bg-orb orb-2" />
      <div className="bg-noise" />

      <div className="app-shell">
        <header className="topbar">
          <div className="brand-row">
            <div className="logo-tile">WS</div>
            <div className="brand-content">
              <p className="brand-name">AI Accounting Studio</p>
              <p className="breadcrumb">Ho so / Event-based Accounting / Chat-based Accounting</p>
            </div>
          </div>

          <div className="topbar-right">
            <div className="chip chip-alert">{pendingCount} giao dich cho</div>
            <div className="chip chip-ai">AI: Local mode</div>
            <div className="chip chip-user">ceo@company.local</div>
          </div>
        </header>

        <main className="workspace-grid">
          <aside className="panel panel-left">
            <button className="new-dossier-btn" type="button" onClick={handleNewDossier}>
              + Ho so moi
            </button>

            <label className="search-wrap">
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Tim theo ho so, doi tac, mo ta..."
              />
            </label>

            <div className="dossier-list">
              {filteredDossiers.length ? (
                filteredDossiers.map((item) => {
                  const status = STATUS_META[item.status] || STATUS_META.dang_xu_ly
                  return (
                    <article
                      key={item.id}
                      className={`dossier-card ${selectedId === item.id ? 'active' : ''}`}
                      onClick={() => setSelectedId(item.id)}
                    >
                      <div className="dossier-row">
                        <h3 className="dossier-title">{item.title}</h3>
                        <span className="dossier-date">{formatDateVi(item.date)}</span>
                      </div>
                      <p className="dossier-code">{item.code}</p>
                      <p className="dossier-partner">{item.partner}</p>
                      <div className="dossier-footer">
                        <p className="dossier-amount">{formatCurrency(item.amount)}</p>
                        <span className={`status-pill ${status.className}`}>{status.label}</span>
                      </div>
                    </article>
                  )
                })
              ) : (
                <p className="empty-state">Khong tim thay ho so phu hop.</p>
              )}
            </div>

            <footer className="left-footer">
              <p>Phan he AI Accounting</p>
              <p>CEO Mode</p>
            </footer>
          </aside>

          <section className="panel panel-center">
            <header className="panel-header">
              <div>
                <h1>{selected?.title || 'Dong su kien'}</h1>
                <p>
                  {selected
                    ? `${selected.code} | ${selected.partner} | ${(STATUS_META[selected.status] || STATUS_META.dang_xu_ly).label}`
                    : 'Chua co ho so duoc chon'}
                </p>
              </div>
              <div className="confidence-box">
                <span>AI Confidence</span>
                <strong>{selected?.confidence ? `${Math.round(selected.confidence * 100)}%` : '--%'}</strong>
              </div>
            </header>

            <section className="events-list">
              {selected?.events?.length ? (
                selected.events.map((eventItem) => (
                  <article key={eventItem.id} className={`event-card event-${eventItem.type}`}>
                    <header className="event-head">
                      <h3 className="event-title">{eventItem.title}</h3>
                      <span className="event-time">{eventItem.time}</span>
                    </header>
                    <p className="event-body">{eventItem.body}</p>
                  </article>
                ))
              ) : (
                <p className="empty-state">Hay mo ta giao dich dau tien de bat dau.</p>
              )}
            </section>

            <form className="chat-form" onSubmit={handleChatSubmit}>
              <label className="ghost-btn file-label">
                Upload chung tu
                <input type="file" hidden multiple onChange={handleUpload} />
              </label>
              <input
                type="text"
                value={chatInput}
                onChange={(event) => setChatInput(event.target.value)}
                placeholder='Mo ta giao dich, vi du: "Chi 3 trieu quang cao Zalo thang 3"'
              />
              <button className="primary-btn" type="submit">
                Gui
              </button>
            </form>
          </section>

          <aside className="panel panel-right">
            <section className="side-block">
              <h2>Chung tu</h2>
              <ul className="document-list">
                {selected?.documents?.length ? (
                  selected.documents.map((doc, index) => (
                    <li key={`${doc.name}-${index}`} className="document-item">
                      <span className="document-name">{doc.name}</span>
                      <span className="document-meta">
                        {formatFileSize(doc.size)} | {formatDateTimeVi(doc.uploadedAt)}
                      </span>
                    </li>
                  ))
                ) : (
                  <li className="empty-state">Chua co chung tu trong ho so nay.</li>
                )}
              </ul>
            </section>

            <section className="side-block">
              <h2>Ly giai cua AI</h2>
              <ul className="reasoning-list">
                {selected?.reasoning?.length ? (
                  selected.reasoning.map((reason, index) => (
                    <li key={`${reason.slice(0, 20)}-${index}`} className="reasoning-item">
                      {reason}
                    </li>
                  ))
                ) : (
                  <li className="empty-state">AI se hien thi ly giai tai day.</li>
                )}
              </ul>
            </section>

            <section className="side-block report-block">
              <h2>Bao cao nhanh</h2>
              <div className="metric-grid">
                <article className="metric">
                  <span>Chi phi da ghi nhan</span>
                  <strong>{formatCurrency(metrics.expense)}</strong>
                </article>
                <article className="metric">
                  <span>Doanh thu da ghi nhan</span>
                  <strong>{formatCurrency(metrics.revenue)}</strong>
                </article>
                <article className="metric">
                  <span>Tien thuan uoc tinh</span>
                  <strong>{formatCurrency(metrics.revenue - metrics.expense)}</strong>
                </article>
                <article className="metric">
                  <span>Ho so da post</span>
                  <strong>{metrics.posted}</strong>
                </article>
              </div>
              <button className="ghost-btn full-width" type="button" onClick={() => showToast('Da xuat tom tat bao cao')}>
                Xuat tom tat bao cao
              </button>
            </section>
          </aside>
        </main>
      </div>

      <div className={`toast ${toast ? 'show' : ''}`}>{toast}</div>
    </>
  )
}

export default App
