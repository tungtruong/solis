import { useEffect, useMemo, useState } from 'react'
import './App.css'

const DEFAULT_EMAIL = 'demo@wssmeas.local'

const STATUS_META = {
  tat_ca: { label: 'Tất cả', className: 'status-tat_ca' },
  moi: { label: 'Mới', className: 'status-moi' },
  dang_xu_ly: { label: 'Đang xử lý', className: 'status-dang_xu_ly' },
  cho_xac_nhan: { label: 'Chờ khách hàng xác nhận', className: 'status-cho_xac_nhan' },
  cho_duyet: { label: 'Chờ duyệt', className: 'status-cho_duyet' },
  da_post: { label: 'Đã post', className: 'status-da_post' },
  hoan_tat: { label: 'Hoàn tất', className: 'status-hoan_tat' },
}

function pad2(value) {
  return String(value).padStart(2, '0')
}

function formatDateVi(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return String(iso || '-')
  return `${pad2(date.getDate())}/${pad2(date.getMonth() + 1)}/${date.getFullYear()}`
}

function formatDateTimeVi(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return String(iso || '-')
  return `${formatDateVi(iso)} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`
}

function formatClock(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '--:--'
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`
}

function formatCurrency(value) {
  const numeric = Number(value) || 0
  return `${new Intl.NumberFormat('vi-VN').format(Math.round(numeric))} đ`
}

function formatFileSize(bytes) {
  const value = Number(bytes) || 0
  if (!value) return 'N/A'
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(2)} MB`
  if (value >= 1024) return `${Math.round(value / 1024)} KB`
  return `${value} B`
}

function parseAmountAny(value) {
  if (typeof value === 'number') return value
  const text = String(value || '').trim()
  if (!text) return 0

  const normalized = text.toLowerCase()
  const trieuMatch = normalized.match(/(\d+(?:[.,]\d+)?)\s*triệu/)
  if (trieuMatch) {
    return Math.round(Number(trieuMatch[1].replace(',', '.')) * 1000000)
  }

  const allNumbers = normalized.match(/\d[\d.,]*/g)
  if (!allNumbers?.length) return 0
  const raw = allNumbers[allNumbers.length - 1]
  const compact = raw.replace(/[.,]/g, '')
  return Number(compact) || 0
}

function statusMeta(status, statusLabel = '') {
  const key = String(status || '').trim()
  const meta = STATUS_META[key]
  if (meta) return meta
  return {
    label: statusLabel || key || 'Đang xử lý',
    className: 'status-dang_xu_ly',
  }
}

function timelineKindToEventType(kind) {
  const value = String(kind || '').toLowerCase()
  if (value === 'user') return 'user'
  if (value === 'result') return 'result'
  return 'ai'
}

function normalizeCaseItem(item, index = 0) {
  if (!item || typeof item !== 'object') return null

  const id = String(item.id || item.case_id || `CASE-${index + 1}`)
  const timeline = Array.isArray(item.timeline) ? item.timeline : []
  const reasoning = Array.isArray(item.reasoning) ? item.reasoning : []
  const permanentEvidence = Array.isArray(item.evidence) ? item.evidence : []
  const stagedEvidence = Array.isArray(item.staged_evidence) ? item.staged_evidence : []

  const documents = [
    ...permanentEvidence.map((name) => ({
      name: String(name || 'Không rõ tệp'),
      size: 0,
      uploadedAt: item.updatedAt || item.createdAt || '',
      staged: false,
    })),
    ...stagedEvidence.map((file) => ({
      name: String(file?.name || 'Không rõ tệp'),
      size: 0,
      uploadedAt: item.updatedAt || item.createdAt || '',
      staged: true,
    })),
  ]

  const events = timeline.map((event, idx) => ({
    id: String(event?.id || `${id}-EV-${idx + 1}`),
    type: timelineKindToEventType(event?.kind || event?.role),
    title: String(event?.title || 'Cập nhật hồ sơ'),
    body: String(event?.body || ''),
    time: String(event?.time || formatClock(item.updatedAt || item.createdAt || '')),
    fields: Array.isArray(event?.table_rows)
      ? event.table_rows
          .map((row) => ({
            label: String(row?.label || 'Trường dữ liệu'),
            value: String(row?.value || '-'),
          }))
          .filter((row) => row.label)
      : [],
  }))

  const normalizedStatus = String(item.status || 'dang_xu_ly')
  const amountValue = parseAmountAny(item.amount)

  return {
    id,
    code: String(item.code || id),
    title: String(item.title || 'Hồ sơ kế toán'),
    partner: String(item.partner || 'Chưa rõ đối tác'),
    amountValue,
    amountText: item.amount ? String(item.amount) : formatCurrency(amountValue),
    date: String(item.updatedAt || item.createdAt || new Date().toISOString()),
    status: normalizedStatus,
    statusLabel: String(item.statusLabel || ''),
    confidence: Number(item?.pending_posting?.parse_meta?.confidence || 0),
    documents,
    reasoning,
    events,
    pendingPosting: item.pending_posting && typeof item.pending_posting === 'object' ? item.pending_posting : null,
  }
}

async function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('Không thể đọc tệp đính kèm'))
    reader.onload = () => {
      const raw = String(reader.result || '')
      const base64 = raw.includes(',') ? raw.split(',')[1] : raw
      resolve(base64)
    }
    reader.readAsDataURL(file)
  })
}

function App() {
  const [search, setSearch] = useState('')
  const [dossiers, setDossiers] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [chatInput, setChatInput] = useState('')
  const [attachedFiles, setAttachedFiles] = useState([])
  const [toast, setToast] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [currentEmail, setCurrentEmail] = useState(DEFAULT_EMAIL)
  const [aiMode, setAiMode] = useState({ text: 'AI: đang kiểm tra...', modeClass: 'fallback' })

  const selected = useMemo(() => dossiers.find((item) => item.id === selectedId) || null, [dossiers, selectedId])

  const filteredDossiers = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return dossiers
    return dossiers.filter((item) => [item.title, item.code, item.partner].join(' ').toLowerCase().includes(q))
  }, [dossiers, search])

  const pendingCount = useMemo(
    () => dossiers.filter((item) => item.status === 'cho_duyet' || item.status === 'cho_xac_nhan').length,
    [dossiers],
  )

  const metrics = useMemo(() => {
    return dossiers.reduce(
      (acc, item) => {
        const amount = Number(item.amountValue) || 0
        const title = String(item.title || '').toLowerCase()
        const isIncome =
          title.includes('thu') ||
          title.includes('bán') ||
          title.includes('doanh thu') ||
          title.includes('khách hàng')

        if (isIncome) acc.revenue += amount
        else acc.expense += amount

        if (item.status === 'hoan_tat' || item.status === 'da_post') acc.posted += 1
        return acc
      },
      { expense: 0, revenue: 0, posted: 0 },
    )
  }, [dossiers])

  function showToast(message) {
    if (!message) return
    setToast(message)
    window.setTimeout(() => setToast(''), 2300)
  }

  async function checkHealth() {
    try {
      const response = await fetch('/api/health')
      if (!response.ok) throw new Error('offline')
      const payload = await response.json()
      if (payload?.ok) {
        setAiMode({ text: 'AI: Kết nối backend', modeClass: 'online' })
        return
      }
      setAiMode({ text: 'AI: Chế độ dự phòng', modeClass: 'fallback' })
    } catch {
      setAiMode({ text: 'AI: Mất kết nối backend', modeClass: 'fallback' })
    }
  }

  async function loadCases(preferredCaseId = '') {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ email: currentEmail || DEFAULT_EMAIL })
      const response = await fetch(`/api/demo/cases?${params.toString()}`)
      if (!response.ok) {
        throw new Error('Không tải được danh sách hồ sơ từ backend')
      }
      const payload = await response.json()
      const rawItems = Array.isArray(payload?.items) ? payload.items : []
      const normalized = rawItems.map((item, index) => normalizeCaseItem(item, index)).filter(Boolean)

      setDossiers(normalized)
      setCurrentEmail(String(payload?.email || currentEmail || DEFAULT_EMAIL))

      const nextSelectedId = preferredCaseId && normalized.some((item) => item.id === preferredCaseId)
        ? preferredCaseId
        : normalized.some((item) => item.id === selectedId)
          ? selectedId
          : normalized[0]?.id || ''

      setSelectedId(nextSelectedId)
    } catch (loadError) {
      setError(loadError?.message || 'Không thể tải dữ liệu hồ sơ.')
      setDossiers([])
      setSelectedId('')
    } finally {
      setLoading(false)
    }
  }

  async function runUiAction(action, text = '', caseId = '', files = []) {
    const attachmentPayload = await Promise.all(
      files.map(async (file) => ({
        name: file.name,
        mime_type: file.type || 'application/octet-stream',
        size: file.size || 0,
        content_base64: await fileToBase64(file),
      })),
    )

    const response = await fetch('/api/demo/ui-action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: currentEmail || DEFAULT_EMAIL,
        action,
        text,
        case_id: caseId,
        attachments: action === 'case_command' ? attachmentPayload : [],
      }),
    })

    if (!response.ok) {
      let detail = ''
      try {
        const payload = await response.json()
        detail = String(payload?.detail || payload?.message || '')
      } catch {
        detail = ''
      }
      throw new Error(detail || 'Thao tác không thành công')
    }

    return response.json()
  }

  useEffect(() => {
    checkHealth().catch(() => {})
    loadCases().catch(() => {})
  }, [])

  async function handleNewDossier() {
    setIsSending(true)
    try {
      const payload = await runUiAction('new_case')
      const caseId = String(payload?.case?.id || '')
      await loadCases(caseId)
      showToast(payload?.message || 'Đã tạo hồ sơ mới')
    } catch (actionError) {
      showToast(actionError?.message || 'Không tạo được hồ sơ mới')
    } finally {
      setIsSending(false)
    }
  }

  async function handleChatSubmit(event) {
    event.preventDefault()
    if (isSending) return

    const text = chatInput.trim()
    if (!text && attachedFiles.length === 0) {
      showToast('Vui lòng nhập nội dung hoặc đính kèm chứng từ trước khi gửi')
      return
    }

    setIsSending(true)
    try {
      let targetCaseId = selectedId
      if (!targetCaseId) {
        const created = await runUiAction('new_case')
        targetCaseId = String(created?.case?.id || '')
      }

      if (!targetCaseId) {
        throw new Error('Không tạo được hồ sơ để xử lý lệnh')
      }

      const payload = await runUiAction('case_command', text, targetCaseId, attachedFiles)
      await loadCases(targetCaseId)
      setChatInput('')
      setAttachedFiles([])
      showToast(payload?.message || 'Đã gửi lệnh xử lý hồ sơ')
    } catch (actionError) {
      showToast(actionError?.message || 'Không gửi được lệnh xử lý')
    } finally {
      setIsSending(false)
    }
  }

  async function handlePostingConfirmation(agree) {
    if (!selected?.id || isSending) return
    setIsSending(true)

    try {
      const commandText = agree ? 'Xác nhận và đồng ý post' : 'Không đồng ý post'
      const payload = await runUiAction('case_command', commandText, selected.id, [])
      await loadCases(selected.id)
      showToast(payload?.message || 'Đã cập nhật trạng thái xác nhận')
    } catch (actionError) {
      showToast(actionError?.message || 'Không xử lý được xác nhận')
    } finally {
      setIsSending(false)
    }
  }

  function onFileChange(event) {
    const files = Array.from(event.target.files || [])
    if (!files.length) return
    setAttachedFiles((prev) => [...prev, ...files])
    event.target.value = ''
  }

  function removeAttachedFile(index) {
    setAttachedFiles((prev) => prev.filter((_, idx) => idx !== index))
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
              <p className="breadcrumb">
                Hồ sơ <span>/</span> Event-based Accounting <span>/</span> Chat-based Accounting
              </p>
            </div>
          </div>

          <div className="topbar-right">
            <div className="chip chip-alert">{pendingCount} giao dịch chờ</div>
            <div className={`chip chip-ai ${aiMode.modeClass}`}>{aiMode.text}</div>
            <div className="chip chip-user">{currentEmail || DEFAULT_EMAIL}</div>
          </div>
        </header>

        <main className="workspace-grid">
          <aside className="panel panel-left">
            <button className="new-dossier-btn" type="button" onClick={handleNewDossier} disabled={isSending}>
              + Hồ sơ mới
            </button>

            <label className="search-wrap">
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Tìm theo hồ sơ, đối tác, mô tả..."
              />
            </label>

            <div className="dossier-list">
              {loading ? <p className="empty-state">Đang tải dữ liệu hồ sơ...</p> : null}
              {!loading && error ? <p className="empty-state">{error}</p> : null}
              {!loading && !error && !filteredDossiers.length ? (
                <p className="empty-state">Không tìm thấy hồ sơ phù hợp.</p>
              ) : null}

              {!loading && !error
                ? filteredDossiers.map((item) => {
                    const status = statusMeta(item.status, item.statusLabel)
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
                          <p className="dossier-amount">{item.amountText || formatCurrency(item.amountValue)}</p>
                          <span className={`status-pill ${status.className}`}>{status.label}</span>
                        </div>
                      </article>
                    )
                  })
                : null}
            </div>

            <footer className="left-footer">
              <p>Phân hệ AI Accounting</p>
              <p>CEO Mode</p>
            </footer>
          </aside>

          <section className="panel panel-center">
            <header className="panel-header">
              <div>
                <h1>{selected?.title || 'Dòng sự kiện'}</h1>
                <p>
                  {selected
                    ? `${selected.code} | ${selected.partner} | ${statusMeta(selected.status, selected.statusLabel).label}`
                    : 'Chưa có hồ sơ được chọn'}
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
                    {eventItem.body ? <p className="event-body">{eventItem.body}</p> : null}
                    {eventItem.fields?.length ? (
                      <table className="event-fields">
                        <thead>
                          <tr>
                            <th>Trường dữ liệu</th>
                            <th>Giá trị</th>
                          </tr>
                        </thead>
                        <tbody>
                          {eventItem.fields.map((field, idx) => (
                            <tr key={`${eventItem.id}-field-${idx}`}>
                              <td>{field.label}</td>
                              <td>{field.value}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : null}
                  </article>
                ))
              ) : (
                <p className="empty-state">Hãy mô tả giao dịch đầu tiên để bắt đầu.</p>
              )}
            </section>

            {selected?.status === 'cho_xac_nhan' && selected?.pendingPosting ? (
              <section className="posting-confirm-box">
                <p>
                  Hệ thống đang chờ khách hàng xác nhận trước khi post bút toán tự động cho hồ sơ này.
                </p>
                <div className="posting-actions">
                  <button
                    type="button"
                    className="ghost-btn"
                    onClick={() => handlePostingConfirmation(false)}
                    disabled={isSending}
                  >
                    Không đồng ý post
                  </button>
                  <button
                    type="button"
                    className="primary-btn"
                    onClick={() => handlePostingConfirmation(true)}
                    disabled={isSending}
                  >
                    Xác nhận và đồng ý post
                  </button>
                </div>
              </section>
            ) : null}

            <form className="chat-form" onSubmit={handleChatSubmit}>
              <label className="ghost-btn file-label">
                Upload chứng từ
                <input type="file" hidden multiple onChange={onFileChange} />
              </label>
              <input
                type="text"
                value={chatInput}
                onChange={(event) => setChatInput(event.target.value)}
                placeholder='Mô tả giao dịch, ví dụ: "Chi 3 triệu quảng cáo Zalo tháng 3"'
                disabled={isSending}
              />
              <button className="primary-btn" type="submit" disabled={isSending}>
                {isSending ? 'Đang gửi...' : 'Gửi'}
              </button>
            </form>

            {attachedFiles.length ? (
              <div className="attachment-pills">
                {attachedFiles.map((file, index) => (
                  <button
                    key={`${file.name}-${index}`}
                    type="button"
                    className="attachment-pill"
                    onClick={() => removeAttachedFile(index)}
                    title="Bấm để gỡ tệp khỏi danh sách gửi"
                  >
                    {file.name}
                  </button>
                ))}
              </div>
            ) : null}
          </section>

          <aside className="panel panel-right">
            <section className="side-block">
              <h2>Chứng từ</h2>
              <ul className="document-list">
                {selected?.documents?.length ? (
                  selected.documents.map((doc, index) => (
                    <li key={`${doc.name}-${index}`} className="document-item">
                      <span className="document-name">{doc.name}{doc.staged ? ' (chưa post)' : ''}</span>
                      <span className="document-meta">
                        {formatFileSize(doc.size)} | {formatDateTimeVi(doc.uploadedAt)}
                      </span>
                    </li>
                  ))
                ) : (
                  <li className="empty-state">Chưa có chứng từ trong hồ sơ này.</li>
                )}
              </ul>
            </section>

            <section className="side-block">
              <h2>Lý giải của AI</h2>
              <ul className="reasoning-list">
                {selected?.reasoning?.length ? (
                  selected.reasoning.map((reason, index) => (
                    <li key={`${reason.slice(0, 20)}-${index}`} className="reasoning-item">
                      {reason}
                    </li>
                  ))
                ) : (
                  <li className="empty-state">AI sẽ hiển thị lý giải tại đây.</li>
                )}
              </ul>
            </section>

            <section className="side-block report-block">
              <h2>Báo cáo nhanh</h2>
              <div className="metric-grid">
                <article className="metric">
                  <span>Chi phí đã ghi nhận</span>
                  <strong>{formatCurrency(metrics.expense)}</strong>
                </article>
                <article className="metric">
                  <span>Doanh thu đã ghi nhận</span>
                  <strong>{formatCurrency(metrics.revenue)}</strong>
                </article>
                <article className="metric">
                  <span>Tiền thuần ước tính</span>
                  <strong>{formatCurrency(metrics.revenue - metrics.expense)}</strong>
                </article>
                <article className="metric">
                  <span>Hồ sơ đã post</span>
                  <strong>{metrics.posted}</strong>
                </article>
              </div>
              <button className="ghost-btn full-width" type="button" onClick={() => showToast('Đã xuất tóm tắt báo cáo')}>
                Xuất tóm tắt báo cáo
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
