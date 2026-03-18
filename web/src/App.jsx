import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Bell,
  Bot,
  ChevronDown,
  ChevronRight,
  Cpu,
  FileCheck2,
  FileText,
  HelpCircle,
  LayoutDashboard,
  MessageSquare,
  Paperclip,
  Plus,
  Search,
  Settings,
  SlidersHorizontal,
  UserCircle2,
  X,
} from 'lucide-react'
import './App.css'

const CASE_PAGE_SIZE = 20

const initialCaseItems = []
const defaultStatusOptions = [{ value: 'tat_ca', label: 'Tất cả' }]

function formatFieldLabel(value) {
  return String(value || '')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/^./, (char) => char.toUpperCase())
}

function collectRows(value, prefix = '') {
  const rows = []
  if (value == null) {
    rows.push({ label: prefix || 'Giá trị', value: '-' })
    return rows
  }

  if (Array.isArray(value)) {
    if (!value.length) {
      rows.push({ label: prefix || 'Danh sách', value: '-' })
      return rows
    }
    if (value.every((item) => typeof item !== 'object' || item === null)) {
      rows.push({ label: prefix || 'Danh sách', value: value.join(', ') })
      return rows
    }
    value.forEach((item, idx) => {
      rows.push(...collectRows(item, `${prefix} #${idx + 1}`.trim()))
    })
    return rows
  }

  if (typeof value === 'object') {
    Object.entries(value).forEach(([key, child]) => {
      const label = prefix ? `${prefix} / ${formatFieldLabel(key)}` : formatFieldLabel(key)
      rows.push(...collectRows(child, label))
    })
    return rows
  }

  rows.push({ label: prefix || 'Giá trị', value: String(value) })
  return rows
}

function parseJsonToSections(rawText) {
  const payload = JSON.parse(rawText)
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return [{ title: 'Dữ liệu JSON', rows: collectRows(payload, 'Giá trị') }]
  }

  const sections = Object.entries(payload).map(([key, value]) => ({
    title: formatFieldLabel(key),
    rows: collectRows(value),
  }))

  return sections.length ? sections : [{ title: 'Dữ liệu JSON', rows: [{ label: 'Giá trị', value: '-' }] }]
}

function parseXmlToSections(rawText) {
  const normalizedText = String(rawText || '').replace(/^\uFEFF/, '').trim()
  const parser = new DOMParser()
  let doc = parser.parseFromString(normalizedText, 'application/xml')
  let parserError = doc.querySelector('parsererror')
  if (parserError) {
    const firstTag = normalizedText.indexOf('<')
    const lastTag = normalizedText.lastIndexOf('>')
    if (firstTag >= 0 && lastTag > firstTag) {
      const sliced = normalizedText.slice(firstTag, lastTag + 1)
      doc = parser.parseFromString(sliced, 'application/xml')
      parserError = doc.querySelector('parsererror')
    }
  }
  if (parserError) {
    throw new Error('Không đọc được nội dung XML')
  }

  const root = doc.documentElement
  if (!root) {
    return [{ title: 'Dữ liệu XML', rows: [{ label: 'Giá trị', value: '-' }] }]
  }

  function flattenNodeToRows(node, pathPrefix = '') {
    const rows = []
    const children = Array.from(node.children || [])
    const nodeLabel = formatFieldLabel(node.tagName)
    const currentPath = pathPrefix || nodeLabel

    Array.from(node.attributes || []).forEach((attr) => {
      rows.push({
        label: `${currentPath} / @${String(attr.name || '').trim()}`,
        value: String(attr.value || '').trim() || '-',
      })
    })

    if (!children.length) {
      const value = String(node.textContent || '').trim()
      rows.push({
        label: currentPath,
        value: value || '-',
      })
      return rows
    }

    children.forEach((child) => {
      const childLabel = formatFieldLabel(child.tagName)
      const nextPath = pathPrefix ? `${pathPrefix} / ${childLabel}` : childLabel
      rows.push(...flattenNodeToRows(child, nextPath))
    })

    return rows
  }

  const sectionNodes = Array.from(root.children || [])
  if (!sectionNodes.length) {
    return [{
      title: formatFieldLabel(root.tagName || 'XML'),
      rows: [{ label: formatFieldLabel(root.tagName || 'Giá trị'), value: String(root.textContent || '').trim() || '-' }],
    }]
  }

  const sections = sectionNodes.map((sectionNode) => {
    const rows = flattenNodeToRows(sectionNode)

    return {
      title: formatFieldLabel(sectionNode.tagName),
      rows: rows.length ? rows : [{ label: 'Giá trị', value: '-' }],
    }
  })

  return sections.length ? sections : [{ title: formatFieldLabel(root.tagName), rows: [{ label: 'Giá trị', value: '-' }] }]
}

function parseDocRtfToSections(rawText) {
  const rowChunks = rawText.split('\\row')
  const rows = []

  rowChunks.forEach((chunk) => {
    const matches = [...chunk.matchAll(/\\intbl\s*([^\\]+?)\\cell/g)]
    if (!matches.length) return

    const cells = matches
      .map((match) => String(match[1] || '').trim())
      .filter(Boolean)
      .map((cell) => cell.replace(/\s+/g, ' '))

    if (cells.length) {
      rows.push(cells)
    }
  })

  if (!rows.length) {
    return [{ title: 'Nội dung DOC', rows: [{ label: 'Dữ liệu', value: 'Không đọc được bảng trong file DOC' }] }]
  }

  const header = rows[0]
  const dataRows = rows.slice(1)
  const normalizedRows = dataRows.map((cells, idx) => ({
    label: cells[0] || `Dòng ${idx + 1}`,
    value: cells.slice(1).join(' | ') || '-',
  }))

  return [
    {
      title: `Bảng DOC (${header.join(' | ')})`,
      rows: normalizedRows.length ? normalizedRows : [{ label: 'Dữ liệu', value: '-' }],
    },
  ]
}

function TypingText({ text, speed = 8, onComplete, animate = true }) {
  const [visibleText, setVisibleText] = useState('')
  const completedRef = useRef(false)
  const onCompleteRef = useRef(onComplete)

  useEffect(() => {
    onCompleteRef.current = onComplete
  }, [onComplete])

  useEffect(() => {
    const source = String(text || '')
    if (!source) {
      setVisibleText('')
      if (!completedRef.current && typeof onCompleteRef.current === 'function') {
        completedRef.current = true
        onCompleteRef.current()
      }
      return undefined
    }

    if (!animate) {
      setVisibleText(source)
      if (!completedRef.current && typeof onCompleteRef.current === 'function') {
        completedRef.current = true
        onCompleteRef.current()
      }
      return undefined
    }

    if (completedRef.current) {
      setVisibleText(source)
      return undefined
    }

    setVisibleText('')

    let index = 0
    const timer = window.setInterval(() => {
      index += 1
      setVisibleText(source.slice(0, index))
      if (index >= source.length) {
        window.clearInterval(timer)
        if (!completedRef.current && typeof onCompleteRef.current === 'function') {
          completedRef.current = true
          onCompleteRef.current()
        }
      }
    }, speed)

    return () => {
      window.clearInterval(timer)
    }
  }, [text, speed, animate])

  return <span>{visibleText}</span>
}

function normalizeCaseItem(raw, fallbackIndex = 0) {
  if (!raw || typeof raw !== 'object') return null
  const id = raw.id || raw.case_id || `case-fallback-${fallbackIndex}`
  const status = raw.status || 'moi'
  const statusLabelMap = {
    moi: 'Mới',
    dang_xu_ly: 'Đang xử lý',
    cho_xac_nhan: 'Chờ khách hàng xác nhận',
    cho_duyet: 'Chờ duyệt',
    hoan_tat: 'Hoàn tất',
  }

  return {
    id,
    code: raw.code || String(id).toUpperCase(),
    title: raw.title || 'Hồ sơ kế toán',
    partner: raw.partner || raw.counterparty_name || 'Đối tác',
    amount: raw.amount || '0 VND',
    updatedAt: raw.updatedAt || raw.event_date || 'Vừa xong',
    status,
    statusLabel: raw.statusLabel || statusLabelMap[status] || 'Mới',
    timeline: Array.isArray(raw.timeline) ? raw.timeline : [],
    evidence: Array.isArray(raw.evidence) ? raw.evidence : [],
    reasoning: Array.isArray(raw.reasoning) ? raw.reasoning : [],
    pendingPosting:
      raw.pendingPosting && typeof raw.pendingPosting === 'object'
        ? raw.pendingPosting
        : raw.pending_posting && typeof raw.pending_posting === 'object'
          ? raw.pending_posting
          : null,
  }
}

function toSortableTimestamp(dateValue) {
  const numeric = Date.parse(String(dateValue || ''))
  return Number.isNaN(numeric) ? 0 : numeric
}

function formatCurrency(value) {
  const amount = Number(value || 0)
  return `${amount.toLocaleString('vi-VN')} VND`
}

function downloadBase64File(fileName, mimeType, contentBase64) {
  const binary = window.atob(String(contentBase64 || ''))
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  const blob = new Blob([bytes], { type: mimeType || 'application/octet-stream' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName || 'download.bin'
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

function App() {
  const gridRef = useRef(null)
  const docxPreviewRef = useRef(null)
  const moduleMenuRef = useRef(null)
  const statusFilterRef = useRef(null)
  const notificationRef = useRef(null)
  const attachmentInputRef = useRef(null)
  const [cases, setCases] = useState(initialCaseItems)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('tat_ca')
  const [isStatusFilterOpen, setIsStatusFilterOpen] = useState(false)
  const [isNotificationOpen, setIsNotificationOpen] = useState(false)
  const [activeCaseId, setActiveCaseId] = useState('')
  const [prompt, setPrompt] = useState('')
  const [attachedFiles, setAttachedFiles] = useState([])
  const [activeSection, setActiveSection] = useState('cases')
  const [isModuleMenuOpen, setIsModuleMenuOpen] = useState(false)
  const [isAdvancedMode, setIsAdvancedMode] = useState(false)
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false)
  const [previewFileName, setPreviewFileName] = useState('')
  const [structuredSections, setStructuredSections] = useState([])
  const [structuredLoading, setStructuredLoading] = useState(false)
  const [structuredError, setStructuredError] = useState('')
  const [docxLoading, setDocxLoading] = useState(false)
  const [docxError, setDocxError] = useState('')
  const [leftWidth, setLeftWidth] = useState(340)
  const [rightWidth, setRightWidth] = useState(330)
  const [dragSide, setDragSide] = useState(null)
  const [visibleCaseCount, setVisibleCaseCount] = useState(CASE_PAGE_SIZE)
  const [statusOptions, setStatusOptions] = useState(defaultStatusOptions)
  const [uiContent, setUiContent] = useState({})
  const [currentEmail, setCurrentEmail] = useState('')
  const [reportDetail, setReportDetail] = useState(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState('')
  const [reportTab, setReportTab] = useState('hieu_qua_kinh_doanh')
  const [reportPeriod, setReportPeriod] = useState('30_ngay')
  const [reportEntity, setReportEntity] = useState('toan_bo')
  const [reportTxnFilter, setReportTxnFilter] = useState('tat_ca')
  const [reportDrillTab, setReportDrillTab] = useState('giao_dich')
  const [dashboardQuery, setDashboardQuery] = useState('')
  const [compliancePeriod, setCompliancePeriod] = useState('2026-03')
  const [complianceReportId, setComplianceReportId] = useState('gtgt')
  const [complianceDetailTab, setComplianceDetailTab] = useState('preview')
  const [dashboardMeta, setDashboardMeta] = useState({ trends: {}, warnings: [], priorities: [] })
  const [complianceData, setComplianceData] = useState({ period_options: [], reports: [], issues: [], history: [], xml_preview: '' })
  const [serverPanels, setServerPanels] = useState({ reports_tips: [], compliance_checklist: [] })
  const [actionNotice, setActionNotice] = useState('')
  const [caseActionNotice, setCaseActionNotice] = useState('')
  const [isSendingCaseCommand, setIsSendingCaseCommand] = useState(false)
  const [timelineVisibleCount, setTimelineVisibleCount] = useState(0)
  const typedMessageKeysRef = useRef(new Set())

  const hasTypedKey = useCallback((key) => {
    if (!key) return false
    return typedMessageKeysRef.current.has(String(key))
  }, [])

  const markTypedKey = useCallback((key) => {
    if (!key) return
    typedMessageKeysRef.current.add(String(key))
  }, [])

  useEffect(() => {
    let cancelled = false

    const loader = async () => {
      const response = await fetch('/api/demo/cases')
      if (!response.ok) return
      const payload = await response.json()
      const items = Array.isArray(payload?.items) ? payload.items : []
      const normalized = items
        .map((item, idx) => normalizeCaseItem(item, idx))
        .filter(Boolean)
        .sort((left, right) => toSortableTimestamp(right.updatedAt) - toSortableTimestamp(left.updatedAt))

      const nextStatusOptions = Array.isArray(payload?.status_options)
        ? payload.status_options
            .filter((item) => item && typeof item === 'object' && item.value && item.label)
            .map((item) => ({ value: String(item.value), label: String(item.label) }))
        : defaultStatusOptions

      const nextUiContent = payload?.ui_content && typeof payload.ui_content === 'object' ? payload.ui_content : {}
      const nextDashboardMeta = payload?.dashboard_meta && typeof payload.dashboard_meta === 'object'
        ? payload.dashboard_meta
        : { trends: {}, warnings: [], priorities: [] }
      const nextServerPanels = payload?.server_panels && typeof payload.server_panels === 'object'
        ? payload.server_panels
        : { reports_tips: [], compliance_checklist: [] }

      if (!cancelled) {
        setStatusOptions(nextStatusOptions.length ? nextStatusOptions : defaultStatusOptions)
        setUiContent(nextUiContent)
        setDashboardMeta(nextDashboardMeta)
        setServerPanels(nextServerPanels)
        setCurrentEmail(String(payload?.email || ''))
      }

      if (!cancelled && normalized.length) {
        setCases(normalized)
        setActiveCaseId((prev) => (normalized.some((item) => item.id === prev) ? prev : normalized[0].id))
      }
    }

    loader().catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const statusFilterLabel = statusOptions.find((item) => item.value === statusFilter)?.label || 'Tất cả'

  const filteredCases = useMemo(() => {
    const search = query.trim().toLowerCase()
    return cases.filter((item) => {
      if (statusFilter !== 'tat_ca' && item.status !== statusFilter) return false
      if (!search) return true
      const haystack = `${item.title} ${item.code} ${item.partner}`.toLowerCase()
      return haystack.includes(search)
    })
  }, [cases, query, statusFilter])

  const visibleCases = useMemo(
    () => filteredCases.slice(0, Math.min(visibleCaseCount, filteredCases.length)),
    [filteredCases, visibleCaseCount],
  )

  const activeCase = filteredCases.find((item) => item.id === activeCaseId) || cases.find((item) => item.id === activeCaseId)
  const timeline = Array.isArray(activeCase?.timeline) ? activeCase.timeline : []
  const evidence = Array.isArray(activeCase?.evidence) ? activeCase.evidence : []
  const reasoning = Array.isArray(activeCase?.reasoning) ? activeCase.reasoning : []
  const pendingPosting = activeCase?.pendingPosting && typeof activeCase.pendingPosting === 'object' ? activeCase.pendingPosting : null
  const pendingEvent = pendingPosting?.event && typeof pendingPosting.event === 'object' ? pendingPosting.event : null
  const pendingAmount = Number(
    pendingEvent?.amount_total || pendingEvent?.total_amount || pendingEvent?.amount || pendingEvent?.untaxed_amount || 0,
  )
  const pendingParseRows = pendingEvent
    ? [
        { label: 'Nhà cung cấp', value: String(pendingEvent.counterparty_name || pendingEvent.seller_name || '-') },
        { label: 'Nội dung', value: String(pendingEvent.description || pendingEvent.goods_service_type || '-') },
        { label: 'Số hóa đơn', value: String(pendingEvent.invoice_no || pendingEvent.reference_no || '-') },
        { label: 'Số tiền', value: pendingAmount > 0 ? formatCurrency(pendingAmount) : '-' },
        { label: 'Nghiệp vụ', value: String(pendingPosting.event_type || pendingEvent.event_type || '-') },
      ]
    : []

  const timelineSignature = useMemo(
    () => timeline.map((event) => String(event?.id || '')).join('|'),
    [timeline],
  )

  useEffect(() => {
    if (!timeline.length) {
      setTimelineVisibleCount(0)
      return
    }

    const firstUntypedIndex = timeline.findIndex((event) => {
      const eventKey = `timeline:${activeCaseId || 'no_case'}:${String(event?.id || '')}`
      return !hasTypedKey(eventKey)
    })

    if (firstUntypedIndex === -1) {
      setTimelineVisibleCount(timeline.length)
      return
    }

    setTimelineVisibleCount(firstUntypedIndex + 1)
  }, [activeCaseId, timeline.length, timelineSignature, hasTypedKey])
  const unfinishedCases = useMemo(() => cases.filter((item) => item.status !== 'hoan_tat'), [cases])
  const previewFileUrl = previewFileName ? `/evidence/${previewFileName}` : ''
  const isPdfPreview = /\.pdf$/i.test(previewFileName)
  const isImagePreview = /\.(png|jpg|jpeg|gif|webp|svg)$/i.test(previewFileName)
  const isXmlPreview = /\.xml$/i.test(previewFileName)
  const isJsonPreview = /\.json$/i.test(previewFileName)
  const isDocPreview = /\.doc$/i.test(previewFileName)
  const isDocxPreview = /\.docx$/i.test(previewFileName)
  const officeViewerUrl = useMemo(() => {
    if (!previewFileName || (!isDocPreview && !isDocxPreview)) return ''
    if (typeof window === 'undefined') return ''
    const { protocol, hostname, origin } = window.location
    if (protocol !== 'https:' || hostname === 'localhost' || hostname === '127.0.0.1') return ''
    const absoluteDocUrl = `${origin}${previewFileUrl}`
    return `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(absoluteDocUrl)}`
  }, [previewFileName, previewFileUrl, isDocPreview, isDocxPreview])
  const isStructuredPreview = isXmlPreview || isJsonPreview || isDocPreview
  const isDocxPagePreview = isDocxPreview && !officeViewerUrl

  useEffect(() => {
    setVisibleCaseCount(CASE_PAGE_SIZE)
  }, [query, statusFilter])

  useEffect(() => {
    if (!previewFileName || !isStructuredPreview) {
      setStructuredSections([])
      setStructuredLoading(false)
      setStructuredError('')
      return
    }

    let cancelled = false
    setStructuredLoading(true)
    setStructuredError('')

    const loader = async () => {
      const response = await fetch(previewFileUrl)
      if (!response.ok) {
        throw new Error('Không tải được file để xem nhanh')
      }

      const rawText = await response.text()
      if (isXmlPreview) return parseXmlToSections(rawText)
      if (isJsonPreview) return parseJsonToSections(rawText)
      if (isDocPreview) return parseDocRtfToSections(rawText)
      return []
    }

    loader()
      .then((sections) => {
        if (!cancelled) {
          setStructuredSections(sections)
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setStructuredError(error.message || 'Không thể hiển thị dữ liệu dạng bảng')
          setStructuredSections([])
        }
      })
      .finally(() => {
        if (!cancelled) {
          setStructuredLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [previewFileName, previewFileUrl, isStructuredPreview, isXmlPreview, isJsonPreview, isDocPreview])

  useEffect(() => {
    if (!previewFileName || !isDocxPagePreview) {
      setDocxLoading(false)
      setDocxError('')
      if (docxPreviewRef.current) {
        docxPreviewRef.current.innerHTML = ''
      }
      return
    }

    let cancelled = false
    setDocxLoading(true)
    setDocxError('')

    const host = docxPreviewRef.current
    if (host) {
      host.innerHTML = ''
    }

    const loader = async () => {
      const response = await fetch(previewFileUrl)
      if (!response.ok) {
        throw new Error('Không tải được file DOCX để xem nhanh')
      }

      const buffer = await response.arrayBuffer()
      const { renderAsync } = await import('docx-preview')
      if (cancelled || !host) return

      await renderAsync(buffer, host, undefined, {
        inWrapper: true,
        breakPages: true,
        renderHeaders: true,
        renderFooters: true,
        renderFootnotes: true,
        useBase64URL: true,
      })
    }

    loader()
      .catch((error) => {
        if (!cancelled) {
          setDocxError(error.message || 'Không thể dựng tài liệu DOCX theo trang')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setDocxLoading(false)
        }
      })

    return () => {
      cancelled = true
      if (host) {
        host.innerHTML = ''
      }
    }
  }, [previewFileName, previewFileUrl, isDocxPagePreview])

  async function confirmDeleteActiveCase() {
    if (!activeCase) return
    try {
      const payload = await runUiAction('delete_case', '', activeCase.id)
      await reloadDemoCases('')
      setActiveSection('cases')
      setCaseActionNotice(payload?.message || 'Đã xóa hồ sơ')
    } catch (error) {
      setCaseActionNotice(error.message || 'Không xóa được hồ sơ')
    } finally {
      setIsDeleteModalOpen(false)
    }
  }

  function openPreview(name) {
    setPreviewFileName(name)
  }

  function closePreview() {
    setPreviewFileName('')
  }

  function openCaseFromNotification(caseId) {
    setActiveCaseId(caseId)
    setActiveSection('cases')
    setIsAdvancedMode(false)
    setIsNotificationOpen(false)
  }

  useEffect(() => {
    if (!previewFileName) return undefined

    function onKeyDown(event) {
      if (event.key === 'Escape') {
        closePreview()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [previewFileName])

  useEffect(() => {
    if (!isModuleMenuOpen) return undefined

    function onMouseDown(event) {
      if (moduleMenuRef.current && !moduleMenuRef.current.contains(event.target)) {
        setIsModuleMenuOpen(false)
      }
    }

    function onKeyDown(event) {
      if (event.key === 'Escape') {
        setIsModuleMenuOpen(false)
      }
    }

    document.addEventListener('mousedown', onMouseDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [isModuleMenuOpen])

  useEffect(() => {
    if (!isStatusFilterOpen) return undefined

    function onMouseDown(event) {
      if (statusFilterRef.current && !statusFilterRef.current.contains(event.target)) {
        setIsStatusFilterOpen(false)
      }
    }

    function onKeyDown(event) {
      if (event.key === 'Escape') {
        setIsStatusFilterOpen(false)
      }
    }

    document.addEventListener('mousedown', onMouseDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [isStatusFilterOpen])

  useEffect(() => {
    if (!isNotificationOpen) return undefined

    function onMouseDown(event) {
      if (notificationRef.current && !notificationRef.current.contains(event.target)) {
        setIsNotificationOpen(false)
      }
    }

    function onKeyDown(event) {
      if (event.key === 'Escape') {
        setIsNotificationOpen(false)
      }
    }

    document.addEventListener('mousedown', onMouseDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [isNotificationOpen])

  function handleSectionClick(section) {
    setActiveSection((prev) => (prev === section ? 'cases' : section))
  }

  function handleCaseListScroll(event) {
    const listEl = event.currentTarget
    const reachedBottom = listEl.scrollTop + listEl.clientHeight >= listEl.scrollHeight - 48
    if (!reachedBottom) return
    if (visibleCaseCount >= filteredCases.length) return

    setVisibleCaseCount((prev) => Math.min(prev + CASE_PAGE_SIZE, filteredCases.length))
  }

  function handleAttachFiles(event) {
    const fileList = Array.from(event.target.files || [])
    if (!fileList.length) return

    setAttachedFiles((prev) => {
      const existing = new Set(prev.map((file) => `${file.name}-${file.size}-${file.lastModified}`))
      const next = [...prev]
      fileList.forEach((file) => {
        const key = `${file.name}-${file.size}-${file.lastModified}`
        if (!existing.has(key)) {
          next.push(file)
          existing.add(key)
        }
      })
      return next
    })

    event.target.value = ''
  }

  function removeAttachedFile(targetFile) {
    setAttachedFiles((prev) => prev.filter((file) => file !== targetFile))
  }

  function handleModuleSelect(section) {
    setActiveSection(section)
    setIsModuleMenuOpen(false)
  }

  const sectionLabel =
    activeSection === 'dashboard'
      ? 'Bảng điều khiển'
      : activeSection === 'reports'
        ? 'Báo cáo'
        : activeSection === 'compliance'
          ? 'Tuân thủ & Kê khai'
        : activeSection === 'settings'
          ? 'Cài đặt'
          : activeCase?.title || 'Chưa chọn hồ sơ'
  const isCompactSidebar = ['dashboard', 'reports', 'compliance'].includes(activeSection)

  const sectionContent = activeSection !== 'cases' && uiContent && typeof uiContent === 'object' ? uiContent[activeSection] || {} : {}
  const sideCompanion = sectionContent?.companion || {
    title: `Màn phụ ${sectionLabel}`,
    subtitle: 'Đang tải dữ liệu cấu hình từ hệ thống.',
    highlights: [],
    actions: [],
  }
  const dashboardCards = Array.isArray(sectionContent?.cards) ? sectionContent.cards : []
  const detailRows = Array.isArray(sectionContent?.rows) ? sectionContent.rows : []
  const modeToggleConfig = sectionContent?.mode_toggle && typeof sectionContent.mode_toggle === 'object' ? sectionContent.mode_toggle : null
  const reportAsOfDate = useMemo(() => {
    const newestCaseDate = cases[0]?.updatedAt
    if (newestCaseDate && !Number.isNaN(Date.parse(newestCaseDate))) {
      return newestCaseDate
    }
    return new Date().toISOString().slice(0, 10)
  }, [cases])
  const reportRevenue = Number(reportDetail?.pl?.doanh_thu || 0)
  const reportCost = Number(reportDetail?.pl?.chi_phi || 0)
  const reportProfit = Number(reportDetail?.pl?.loi_nhuan_truoc_thue || 0)
  const reportCashNet = Number(reportDetail?.cf?.luu_chuyen_thuan || 0)
  const reportAssets = Number(reportDetail?.bs?.tong_tai_san || 0)
  const reportLiabilities = Number(reportDetail?.bs?.tong_no_phai_tra || 0)
  const reportEquity = Number(reportDetail?.bs?.von_chu_so_huu || 0)
  const reportCostRatioPct = reportRevenue > 0 ? (reportCost / reportRevenue) * 100 : 0
  const cashflowSeries = useMemo(() => {
    const rows = (reportDetail?.gl?.items || []).slice(-6)
    return rows.map((item, idx) => {
      const postings = Array.isArray(item.postings) ? item.postings : []
      const net = postings.reduce((sum, line) => {
        const account = String(line?.account || '')
        if (!account.startsWith('111') && !account.startsWith('112')) return sum
        const amount = Number(line?.amount || 0)
        return line?.side === 'Nợ' ? sum + amount : sum - amount
      }, 0)
      return {
        label: String(item.event_date || idx + 1).slice(5),
        value: net,
      }
    })
  }, [reportDetail])

  useEffect(() => {
    if (!['reports', 'dashboard', 'compliance'].includes(activeSection)) return undefined

    let cancelled = false
    setReportLoading(true)
    setReportError('')

    const loader = async () => {
      const params = new URLSearchParams({ as_of_date: reportAsOfDate })
      if (currentEmail) {
        params.set('email', currentEmail)
      }
      const response = await fetch(`/api/demo/reports/detailed?${params.toString()}`)
      if (!response.ok) {
        throw new Error('Không tải được báo cáo chi tiết')
      }
      return response.json()
    }

    loader()
      .then((payload) => {
        if (!cancelled) {
          setReportDetail(payload)
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setReportError(error.message || 'Không tải được báo cáo chi tiết')
          setReportDetail(null)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setReportLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [activeSection, currentEmail, reportAsOfDate])

  useEffect(() => {
    if (!['dashboard', 'compliance'].includes(activeSection)) return undefined

    let cancelled = false
    const loader = async () => {
      const params = new URLSearchParams({ period: compliancePeriod })
      if (currentEmail) params.set('email', currentEmail)
      const response = await fetch(`/api/demo/compliance?${params.toString()}`)
      if (!response.ok) {
        throw new Error('Không tải được dữ liệu tuân thủ kê khai')
      }
      return response.json()
    }

    loader()
      .then((payload) => {
        if (cancelled) return
        setComplianceData(payload)
        const reports = Array.isArray(payload?.reports) ? payload.reports : []
        if (reports.length && !reports.some((item) => String(item.report_id) === complianceReportId)) {
          setComplianceReportId(String(reports[0].report_id))
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setActionNotice(error.message || 'Không tải được dữ liệu tuân thủ kê khai')
        }
      })

    return () => {
      cancelled = true
    }
  }, [activeSection, currentEmail, compliancePeriod, complianceReportId])

  async function runUiAction(action, text = '', caseId = '') {
    const attachmentPayload = await Promise.all(
      attachedFiles.map(
        (file) =>
          new Promise((resolve) => {
            const reader = new FileReader()
            reader.onload = () => {
              resolve({
                name: file.name,
                mime_type: file.type || 'application/octet-stream',
                size: file.size,
                content_base64: typeof reader.result === 'string' ? reader.result : '',
              })
            }
            reader.onerror = () => {
              resolve({
                name: file.name,
                mime_type: file.type || 'application/octet-stream',
                size: file.size,
                content_base64: '',
              })
            }
            reader.readAsDataURL(file)
          }),
      ),
    )

    const response = await fetch('/api/demo/ui-action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: currentEmail || 'demo@wssmeas.local',
        action,
        text,
        case_id: caseId,
        attachments: action === 'case_command' ? attachmentPayload : [],
      }),
    })
    if (!response.ok) {
      let detail = ''
      try {
        const errorPayload = await response.json()
        detail = String(errorPayload?.detail || errorPayload?.message || '').trim()
      } catch {
        detail = ''
      }
      throw new Error(detail || 'Thao tác không thành công')
    }
    return response.json()
  }

  async function reloadDemoCases(preferredCaseId = '') {
    const params = new URLSearchParams()
    if (currentEmail) params.set('email', currentEmail)
    const response = await fetch(`/api/demo/cases?${params.toString()}`)
    if (!response.ok) return
    const payload = await response.json()
    const items = Array.isArray(payload?.items) ? payload.items : []
    const normalized = items
      .map((item, idx) => normalizeCaseItem(item, idx))
      .filter(Boolean)
      .sort((left, right) => toSortableTimestamp(right.updatedAt) - toSortableTimestamp(left.updatedAt))
    setCases(normalized)
    const nextActiveId = preferredCaseId && normalized.some((item) => item.id === preferredCaseId)
      ? preferredCaseId
      : normalized[0]?.id || ''
    setActiveCaseId(nextActiveId)
  }

  async function handleCreateNewCase() {
    try {
      const payload = await runUiAction('new_case')
      await reloadDemoCases(payload?.case?.id || '')
      setActiveSection('cases')
      setCaseActionNotice(payload?.message || 'Đã tạo hồ sơ mới')
    } catch (error) {
      setCaseActionNotice(error.message || 'Không tạo được hồ sơ mới')
    }
  }

  async function handleSendCaseCommand() {
    if (isSendingCaseCommand) return
    const text = prompt.trim()
    if (!text && attachedFiles.length === 0) {
      setCaseActionNotice('Vui lòng nhập nội dung hoặc đính kèm chứng từ trước khi gửi')
      return
    }
    setIsSendingCaseCommand(true)
    try {
      let targetCaseId = activeCaseId
      if (!targetCaseId) {
        const created = await runUiAction('new_case')
        targetCaseId = String(created?.case?.id || '')
      }
      if (!targetCaseId) {
        throw new Error('Không tạo được hồ sơ để nhận lệnh')
      }

      const payload = await runUiAction('case_command', text, targetCaseId)
      await reloadDemoCases(targetCaseId)
      setPrompt('')
      setAttachedFiles([])
      setCaseActionNotice(payload?.message || 'Đã gửi lệnh')
    } catch (error) {
      setCaseActionNotice(error.message || 'Không gửi được lệnh')
    } finally {
      setIsSendingCaseCommand(false)
    }
  }

  async function handlePostingConfirmation(agree) {
    if (!activeCaseId || isSendingCaseCommand) return
    setIsSendingCaseCommand(true)
    try {
      const commandText = agree ? 'Xác nhận và đồng ý post' : 'Không đồng ý post'
      const payload = await runUiAction('case_command', commandText, activeCaseId)
      await reloadDemoCases(activeCaseId)
      setCaseActionNotice(payload?.message || (agree ? 'Đã xác nhận post' : 'Đã từ chối post'))
    } catch (error) {
      setCaseActionNotice(error.message || 'Không xử lý được xác nhận')
    } finally {
      setIsSendingCaseCommand(false)
    }
  }

  async function handleDashboardAnalyze() {
    const text = dashboardQuery.trim()
    if (!text) {
      setActionNotice('Vui lòng nhập câu hỏi để phân tích')
      return
    }
    try {
      const payload = await runUiAction('dashboard_query', text)
      setActionNotice(payload?.message || 'Đã chạy phân tích')
    } catch (error) {
      setActionNotice(error.message || 'Không phân tích được dữ liệu')
    }
  }

  async function downloadComplianceFile(kind) {
    if (!complianceActiveReport) return
    const endpoint = kind === 'pdf' ? '/api/demo/compliance/export-pdf' : '/api/demo/compliance/export-xml'
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: currentEmail || 'demo@wssmeas.local',
        period: compliancePeriod,
        report_id: String(complianceActiveReport.report_id),
      }),
    })
    if (!response.ok) {
      throw new Error('Không xuất được file')
    }
    const payload = await response.json()
    downloadBase64File(payload.file_name, payload.mime_type, payload.content_base64)
    setActionNotice(`Đã tải file ${payload.file_name}`)
  }

  async function handleSubmitCompliance() {
    if (!complianceActiveReport) return
    const response = await fetch('/api/demo/compliance/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: currentEmail || 'demo@wssmeas.local',
        period: compliancePeriod,
        report_id: String(complianceActiveReport.report_id),
        submitted_by: currentEmail || 'demo@wssmeas.local',
      }),
    })
    if (!response.ok) {
      setActionNotice('Nộp điện tử thất bại')
      return
    }
    setActionNotice('Đã nộp báo cáo điện tử thành công')
    const params = new URLSearchParams({ period: compliancePeriod })
    if (currentEmail) params.set('email', currentEmail)
    const reload = await fetch(`/api/demo/compliance?${params.toString()}`)
    if (reload.ok) {
      const payload = await reload.json()
      setComplianceData(payload)
    }
  }

  function handleCompanionAction(actionLabel) {
    const label = String(actionLabel || '').toLowerCase()
    if (label.includes('báo cáo') || label.includes('dòng tiền') || label.includes('so sánh')) {
      setActiveSection('reports')
      return
    }
    if (label.includes('công nợ') || label.includes('chi phí')) {
      setActiveSection('reports')
      setReportDrillTab(label.includes('chi phí') ? 'chi_phi' : 'cong_no')
      return
    }
    if (label.includes('phân quyền') || label.includes('cài đặt') || label.includes('kiểm toán')) {
      setActiveSection('settings')
      return
    }
    setActionNotice(`Đã ghi nhận thao tác: ${actionLabel}`)
  }

  const cashValue = Math.max(reportCashNet, 0)
  const payableValue = Math.max(reportLiabilities, 0)
  const receivableValue = Math.max(reportAssets - reportLiabilities - reportEquity, 0)
  const burnRateValue = Math.max(reportCost / 3, 1)
  const runwayMonths = cashValue / burnRateValue
  const cashTrendPct = Number(dashboardMeta?.trends?.cash_pct || 0)
  const payableTrendPct = Number(dashboardMeta?.trends?.payable_pct || 0)
  const receivableTrendPct = Number(dashboardMeta?.trends?.receivable_pct || 0)
  const dashboardWarnings = Array.isArray(dashboardMeta?.warnings) ? dashboardMeta.warnings : []
  const dashboardPriorities = Array.isArray(dashboardMeta?.priorities) ? dashboardMeta.priorities : []
  const debtBalanceSeries = [
    { label: 'Phải trả', value: payableValue },
    { label: 'Phải thu', value: receivableValue },
  ]
  const normalizedFilingReports = Array.isArray(complianceData?.reports) ? complianceData.reports : []
  const complianceActiveReport = normalizedFilingReports.find((item) => String(item.report_id) === complianceReportId) || normalizedFilingReports[0]
  const filingIssues = Array.isArray(complianceData?.issues) ? complianceData.issues : []
  const filingHistory = Array.isArray(complianceData?.history) ? complianceData.history : []
  const dashboardComplianceAlert = normalizedFilingReports.find((item) => item.status === 'qua_han') || normalizedFilingReports.find((item) => item.status === 'chua_nop')

  useEffect(() => {
    if (!dragSide) return undefined

    function onMouseMove(event) {
      const grid = gridRef.current
      if (!grid) return

      const rect = grid.getBoundingClientRect()
      const handleWidth = 10
      const minCenter = 360
      const minLeft = 260
      const minRight = 260

      if (dragSide === 'left') {
        const maxLeft = Math.max(minLeft, rect.width - rightWidth - minCenter - handleWidth * 2)
        const nextLeft = Math.min(maxLeft, Math.max(minLeft, event.clientX - rect.left))
        setLeftWidth(nextLeft)
      }

      if (dragSide === 'right') {
        const maxRight = Math.max(minRight, rect.width - leftWidth - minCenter - handleWidth * 2)
        const nextRight = Math.min(maxRight, Math.max(minRight, rect.right - event.clientX))
        setRightWidth(nextRight)
      }
    }

    function onMouseUp() {
      setDragSide(null)
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
    return () => {
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }
  }, [dragSide, leftWidth, rightWidth])

  const gridStyle = {
    '--left-width': `${isCompactSidebar ? 86 : leftWidth}px`,
    '--right-width': `${rightWidth}px`,
  }

  return (
    <div className="app-shell">
      <header className="global-header">
        <div className="brand-block">
          <div className="logo-mark">WS</div>
          <div className="brand-name">WSSMEAS Tài chính AI</div>
        </div>

        <div className="breadcrumb">
          <span>Hồ sơ</span>
          <ChevronRight size={14} />
          <strong>{sectionLabel}</strong>
        </div>

        <div className="global-actions" ref={notificationRef}>
          <button
            type="button"
            className={isNotificationOpen ? 'icon-action notification-btn active' : 'icon-action notification-btn'}
            aria-label="Thông báo"
            onClick={() => setIsNotificationOpen((prev) => !prev)}
          >
            <Bell size={17} />
            {unfinishedCases.length ? <span className="notification-badge">{unfinishedCases.length}</span> : null}
          </button>
          {isNotificationOpen ? (
            <div className="notification-popover">
              <h4>Thông báo công việc dở dang</h4>
              {unfinishedCases.length ? (
                <ul className="notification-list-scroll">
                  {unfinishedCases.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        className="notification-item-btn"
                        onClick={() => openCaseFromNotification(item.id)}
                      >
                        Hồ sơ <strong>{item.code}</strong> đang {item.statusLabel.toLowerCase()}.
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>Hiện không còn hồ sơ dở dang.</p>
              )}
            </div>
          ) : null}
          <button type="button" className="icon-action" aria-label="Trợ giúp" onClick={() => setActiveSection('settings')}>
            <HelpCircle size={17} />
          </button>
          <button type="button" className="user-chip" onClick={() => setActiveSection('settings')}>
            <UserCircle2 size={18} />
            <span>{currentEmail || 'Đang tải người dùng'}</span>
          </button>
        </div>
      </header>

      <div className="workspace-grid" ref={gridRef} style={gridStyle}>
        {isAdvancedMode ? (
          <div className="advanced-workspace">
            <section className="advanced-panel advanced-left">
              <div className="advanced-actions">
                <button
                  type="button"
                  className="mode-toggle active"
                  onClick={() => {
                    setIsAdvancedMode(false)
                    setActiveSection('settings')
                  }}
                >
                  <Cpu size={16} />
                  <span>Thoát Advanced Mode</span>
                </button>
              </div>
              <div className="advanced-head">
                <h2>Trình soạn bút toán chuyên sâu</h2>
                <p>Thiết kế bút toán nhiều dòng, phân bổ kỳ và kiểm tra cân đối tức thì.</p>
              </div>
              <div className="advanced-block">
                <h3>Bút toán mẫu</h3>
                <p>Nợ 242: 70,000,000</p>
                <p>Nợ 1331: 7,000,000</p>
                <p>Có 331: 77,000,000</p>
              </div>
              <div className="advanced-block">
                <h3>Phân bổ tự động</h3>
                <p>Phân bổ TK 242 trong 6 kỳ, bắt đầu từ 04/2026.</p>
              </div>
            </section>

            <section className="advanced-panel advanced-center">
              <div className="advanced-head">
                <h2>Bảng điều phối nghiệp vụ nâng cao</h2>
                <p>Toàn bộ luồng từ nhận chứng từ -&gt; xác thực -&gt; hậu kiểm bút toán.</p>
              </div>
              <div className="advanced-timeline">
                <article>
                  <h3>Bước 1: Nhận chứng từ</h3>
                  <p>AI trích xuất dữ liệu hóa đơn, hợp đồng, điều khoản thanh toán.</p>
                </article>
                <article>
                  <h3>Bước 2: Tạo bút toán nhiều lớp</h3>
                  <p>Cho phép tách nghiệp vụ thành nhiều dòng theo trung tâm chi phí.</p>
                </article>
                <article>
                  <h3>Bước 3: Kiểm tra ràng buộc</h3>
                  <p>Kiểm tra cân đối Nợ-Có, giới hạn tài khoản và quy tắc thuế.</p>
                </article>
                <article>
                  <h3>Bước 4: Duyệt và ghi sổ</h3>
                  <p>Luồng duyệt 2 cấp trước khi ghi nhận vào sổ cái.</p>
                </article>
              </div>
            </section>

            <section className="advanced-panel advanced-right">
              <div className="advanced-head">
                <h2>Kiểm soát chuyên sâu</h2>
                <p>Giám sát sai lệch và tuân thủ theo chuẩn kế toán.</p>
              </div>
              <ul>
                <li>Cảnh báo lệch định khoản theo nhóm tài khoản nhạy cảm.</li>
                <li>Đối chiếu VAT đầu vào/đầu ra theo thời gian thực.</li>
                <li>Nhật ký thay đổi bút toán trước và sau duyệt.</li>
                <li>Kiểm tra chồng chéo chứng từ giữa các hồ sơ.</li>
              </ul>
            </section>
          </div>
        ) : (
          <>
            <aside className={['reports', 'dashboard', 'compliance'].includes(activeSection) ? 'left-sidebar reports-compact' : 'left-sidebar'}>
          {!['reports', 'dashboard', 'compliance'].includes(activeSection) ? <div className="sidebar-top">
            <button type="button" className="new-case-btn" onClick={handleCreateNewCase}>
              <Plus size={16} />
              <span>Hồ sơ mới</span>
            </button>

            <div className="search-wrap">
              <Search size={15} />
              <input
                type="text"
                placeholder="Tìm theo hồ sơ, hóa đơn, đối tác"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              <div className="search-filter-wrap" ref={statusFilterRef}>
                <button
                  type="button"
                  className={isStatusFilterOpen ? 'search-filter-icon-btn active' : 'search-filter-icon-btn'}
                  aria-label={`Lọc trạng thái: ${statusFilterLabel}`}
                  title={`Lọc trạng thái: ${statusFilterLabel}`}
                  onClick={() => setIsStatusFilterOpen((prev) => !prev)}
                >
                  <SlidersHorizontal size={14} />
                  {statusFilter !== 'tat_ca' ? <span className="filter-dot" /> : null}
                </button>

                {isStatusFilterOpen ? (
                  <div className="status-filter-popover">
                    {statusOptions.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        className={statusFilter === option.value ? 'status-filter-option active' : 'status-filter-option'}
                        onClick={() => {
                          setStatusFilter(option.value)
                          setIsStatusFilterOpen(false)
                        }}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          </div> : null}

          {!['reports', 'dashboard', 'compliance'].includes(activeSection) ? <div className="case-list" aria-label="Danh sách hồ sơ cuộn vô hạn" onScroll={handleCaseListScroll}>
            {filteredCases.length ? (
              visibleCases.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={item.id === activeCaseId ? 'case-item active' : 'case-item'}
                  onClick={() => {
                    setActiveCaseId(item.id)
                    setActiveSection('cases')
                  }}
                >
                  <div className="case-item-row">
                    <h3>{item.title}</h3>
                    <time>{item.updatedAt}</time>
                  </div>
                  <p>{item.code} - {item.partner}</p>
                  <div className="case-item-footer">
                    <div className="case-item-amount">{item.amount}</div>
                    <span className={`status-pill status-${item.status}`}>{item.statusLabel}</span>
                  </div>
                </button>
              ))
            ) : (
              <div className="empty-cases">Không có hồ sơ phù hợp bộ lọc.</div>
            )}
            {filteredCases.length > visibleCases.length ? (
              <div className="case-list-more-hint">Cuộn xuống để tải thêm hồ sơ ({visibleCases.length}/{filteredCases.length})</div>
            ) : null}
          </div> : null}

          <nav className="sidebar-bottom">
            {isCompactSidebar ? (
              <div className="compact-module-rail" aria-label="Điều hướng phân hệ nhanh">
                <button
                  type="button"
                  className={activeSection === 'cases' ? 'compact-module-btn active' : 'compact-module-btn'}
                  title="Hồ sơ"
                  aria-label="Hồ sơ"
                  onClick={() => handleModuleSelect('cases')}
                >
                  <MessageSquare size={17} />
                </button>
                <button
                  type="button"
                  className={activeSection === 'dashboard' ? 'compact-module-btn active' : 'compact-module-btn'}
                  title="Bảng điều khiển"
                  aria-label="Bảng điều khiển"
                  onClick={() => handleModuleSelect('dashboard')}
                >
                  <LayoutDashboard size={17} />
                </button>
                <button
                  type="button"
                  className={activeSection === 'reports' ? 'compact-module-btn active' : 'compact-module-btn'}
                  title="Báo cáo"
                  aria-label="Báo cáo"
                  onClick={() => handleModuleSelect('reports')}
                >
                  <FileText size={17} />
                </button>
                <button
                  type="button"
                  className={activeSection === 'compliance' ? 'compact-module-btn active' : 'compact-module-btn'}
                  title="Tuân thủ & Kê khai"
                  aria-label="Tuân thủ & Kê khai"
                  onClick={() => handleModuleSelect('compliance')}
                >
                  <FileCheck2 size={17} />
                </button>
                <button
                  type="button"
                  className={activeSection === 'settings' ? 'compact-module-btn active' : 'compact-module-btn'}
                  title="Cài đặt"
                  aria-label="Cài đặt"
                  onClick={() => handleModuleSelect('settings')}
                >
                  <Settings size={17} />
                </button>
              </div>
            ) : (
              <div className="module-menu-wrap" ref={moduleMenuRef}>
                <button
                  type="button"
                  className={isModuleMenuOpen ? 'bottom-nav-btn active' : 'bottom-nav-btn'}
                  onClick={() => setIsModuleMenuOpen((prev) => !prev)}
                >
                  <LayoutDashboard size={16} />
                  <span>Phân hệ</span>
                  <ChevronDown size={14} className={isModuleMenuOpen ? 'chevron-open' : ''} />
                </button>
                {isModuleMenuOpen ? (
                  <div className="module-menu-popover">
                    <div className="module-menu-list">
                      <button
                        type="button"
                        className={activeSection === 'dashboard' ? 'module-menu-btn active' : 'module-menu-btn'}
                        onClick={() => handleModuleSelect('dashboard')}
                      >
                        <LayoutDashboard size={15} />
                        <span>Bảng điều khiển</span>
                      </button>
                      <button
                        type="button"
                        className={activeSection === 'reports' ? 'module-menu-btn active' : 'module-menu-btn'}
                        onClick={() => handleModuleSelect('reports')}
                      >
                        <FileText size={15} />
                        <span>Báo cáo</span>
                      </button>
                      <button
                        type="button"
                        className={activeSection === 'compliance' ? 'module-menu-btn active' : 'module-menu-btn'}
                        onClick={() => handleModuleSelect('compliance')}
                      >
                        <FileCheck2 size={15} />
                        <span>Tuân thủ & Kê khai</span>
                      </button>
                      <button
                        type="button"
                        className={activeSection === 'settings' ? 'module-menu-btn active' : 'module-menu-btn'}
                        onClick={() => handleModuleSelect('settings')}
                      >
                        <Settings size={15} />
                        <span>Cài đặt</span>
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </nav>
        </aside>

        <div
          className={dragSide === 'left' ? 'resize-handle active' : 'resize-handle'}
          onMouseDown={() => setDragSide('left')}
          role="separator"
          aria-label="Thay đổi độ rộng thanh bên và dòng sự kiện"
        />

        <main className="timeline-panel">
          {activeSection === 'cases' ? (
            <>
              <div className="timeline-head">
                <h2>Dòng sự kiện</h2>
                <p>Luồng tường thuật từ phân tích AI đến các sự kiện kế toán có cấu trúc.</p>
              </div>

              {isAdvancedMode ? (
                <div className="advanced-banner">
                  Advanced Mode đang bật: cho phép hạch toán chuyên sâu, tùy chỉnh bút toán và kiểm soát chi tiết.
                </div>
              ) : null}

              <div className="timeline-stream scrollable-pane">
                {timeline.slice(0, timelineVisibleCount).map((event, index) => (
                  <article
                    key={event.id}
                    className={
                      event.role === 'user' || event.kind === 'user'
                        ? 'chat-row chat-row-user'
                        : 'chat-row chat-row-system'
                    }
                  >
                    <div className="chat-bubble">
                      <div className="chat-bubble-top">
                        <div className="chat-bubble-title">
                          {event.role === 'user' || event.kind === 'user' ? <MessageSquare size={16} /> : <Bot size={16} />}
                          <h3>{event.title}</h3>
                        </div>
                        <time>{event.time}</time>
                      </div>
                      <p className="chat-bubble-body">
                        <TypingText
                          text={event.body}
                          speed={8}
                          animate={!hasTypedKey(`timeline:${activeCaseId || 'no_case'}:${event.id}`)}
                          onComplete={() => {
                            const eventKey = `timeline:${activeCaseId || 'no_case'}:${event.id}`
                            markTypedKey(eventKey)
                            setTimelineVisibleCount((prev) => {
                              if (prev >= timeline.length) return prev
                              if (index !== prev - 1) return prev
                              return prev + 1
                            })
                          }}
                        />
                      </p>
                    </div>
                  </article>
                ))}
              </div>

              <div className="command-box">
                {pendingParseRows.length ? (
                  <section className="parse-summary-box">
                    <div className="parse-summary-head">
                      <h4>Thông tin parse hồ sơ</h4>
                      <span>Vui lòng khách hàng xác nhận trước khi post</span>
                    </div>
                    <table className="parse-summary-table">
                      <thead>
                        <tr>
                          <th>Trường dữ liệu</th>
                          <th>Giá trị</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pendingParseRows.map((row) => (
                          <tr key={row.label}>
                            <td>{row.label}</td>
                            <td>
                              <TypingText
                                text={row.value}
                                speed={6}
                                animate={!hasTypedKey(`parse:${activeCaseId || 'no_case'}:${row.label}:${row.value}`)}
                                onComplete={() => markTypedKey(`parse:${activeCaseId || 'no_case'}:${row.label}:${row.value}`)}
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>

                    <div className="confirm-post-actions">
                      <button
                        type="button"
                        className="confirm-post-btn"
                        onClick={() => handlePostingConfirmation(true)}
                        disabled={isSendingCaseCommand}
                      >
                        Xác nhận và đồng ý post
                      </button>
                      <button
                        type="button"
                        className="confirm-post-btn secondary"
                        onClick={() => handlePostingConfirmation(false)}
                        disabled={isSendingCaseCommand}
                      >
                        Chưa đồng ý post
                      </button>
                    </div>
                  </section>
                ) : null}

                {attachedFiles.length ? (
                  <div className="attached-files-row">
                    {attachedFiles.map((file) => (
                      <span key={`${file.name}-${file.size}-${file.lastModified}`} className="attached-file-chip">
                        <Paperclip size={12} />
                        <span>{file.name}</span>
                        <button
                          type="button"
                          className="attached-file-remove"
                          aria-label={`Bỏ file ${file.name}`}
                          onClick={() => removeAttachedFile(file)}
                        >
                          <X size={12} />
                        </button>
                      </span>
                    ))}
                  </div>
                ) : null}

                <div className="command-input-row">
                  <button
                    type="button"
                    className="attach-file-btn"
                    aria-label="Đính kèm file"
                    title="Đính kèm file"
                    onClick={() => attachmentInputRef.current?.click()}
                  >
                    <Paperclip size={15} />
                  </button>
                  <input
                    ref={attachmentInputRef}
                    type="file"
                    multiple
                    className="attachment-input-hidden"
                    onChange={handleAttachFiles}
                  />
                  <input
                    type="text"
                    placeholder={
                      isAdvancedMode
                        ? 'Lệnh nâng cao: "Tách bút toán 30/70, ghi nhận vào 242 và phân bổ 6 kỳ"'
                        : 'Hỏi AI hoặc ra lệnh: "Hạch toán khoản này vào chi phí trả trước"'
                    }
                    value={prompt}
                    onChange={(event) => setPrompt(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && !isSendingCaseCommand) {
                        event.preventDefault()
                        handleSendCaseCommand()
                      }
                    }}
                  />
                  <button type="button" onClick={handleSendCaseCommand} disabled={isSendingCaseCommand}>
                    {isSendingCaseCommand ? 'Đang gửi...' : 'Gửi'}
                  </button>
                </div>
                {caseActionNotice ? <p className="report-inline-note">{caseActionNotice}</p> : null}
              </div>
            </>
          ) : (
            <section className="detail-screen">
              <div className="detail-head">
                <h2>{sectionLabel}</h2>
                <p>Màn hình chi tiết cho phân hệ {sectionLabel.toLowerCase()}.</p>
              </div>
              {actionNotice ? <p className="report-inline-note">{actionNotice}</p> : null}

              {activeSection === 'dashboard' ? (
                <div className="dashboard-decision-layout">
                  <article className="detail-row dashboard-ai-query">
                    <h3>Hỏi AI để ra quyết định</h3>
                    <div className="report-chat-input">
                      <input
                        type="text"
                        value={dashboardQuery}
                        placeholder="Ví dụ: Tuần này nên ưu tiên thu hồi khoản nào?"
                        onChange={(event) => setDashboardQuery(event.target.value)}
                      />
                      <button type="button" onClick={handleDashboardAnalyze}>Phân tích</button>
                    </div>
                  </article>

                  <article className="detail-row dashboard-hero">
                    <div className="dashboard-hero-head">
                      <h3>Tình hình tài chính hôm nay</h3>
                      <span className="report-live-badge">Control Center</span>
                    </div>
                    <div className="dashboard-hero-metrics">
                      <div><span>Tiền mặt</span><strong className="metric-up">{formatCurrency(cashValue)} ↑ +{cashTrendPct}%</strong></div>
                      <div><span>Công nợ phải trả</span><strong className="metric-down">{formatCurrency(payableValue)} ↑ +{payableTrendPct}%</strong></div>
                      <div><span>Công nợ phải thu</span><strong className="metric-up">{formatCurrency(receivableValue)} ↓ {Math.abs(receivableTrendPct)}%</strong></div>
                    </div>
                    <div className="dashboard-hero-foot">
                      <p>Dự báo: Dòng tiền đủ vận hành khoảng <strong>{runwayMonths.toFixed(1)} tháng</strong></p>
                      <p>Khuyến nghị: Chốt lịch thanh toán nhà cung cấp trước 48 giờ.</p>
                    </div>
                  </article>

                  <article className="detail-row dashboard-kpi-row">
                    {[
                      { title: 'Tiền mặt', value: formatCurrency(cashValue), trend: `+${cashTrendPct}%`, tone: 'up' },
                      { title: 'Phải trả', value: formatCurrency(payableValue), trend: `+${payableTrendPct}%`, tone: 'down' },
                      { title: 'Phải thu', value: formatCurrency(receivableValue), trend: `${receivableTrendPct}%`, tone: 'up' },
                      { title: 'Burn rate', value: `${formatCurrency(burnRateValue)} / tháng`, trend: `${runwayMonths.toFixed(1)} tháng runway`, tone: 'warn' },
                    ].map((card) => (
                      <article className="kpi-smart-card" key={card.title}>
                        <h4>{card.title}</h4>
                        <strong>{card.value}</strong>
                        <p className={card.tone === 'down' ? 'metric-down' : card.tone === 'warn' ? 'metric-warn' : 'metric-up'}>{card.trend}</p>
                      </article>
                    ))}
                  </article>

                  <article className="detail-row dashboard-chart-row">
                    <div className="visual-grid">
                      <div className="visual-item">
                        <h4>Dòng tiền gần nhất</h4>
                        <div className="sparkline-bars">
                          {(cashflowSeries.length ? cashflowSeries : [{ label: '--', value: 0 }]).map((point) => (
                            <div key={`${point.label}-${point.value}`} className="sparkline-col" title={`${point.label}: ${formatCurrency(point.value)}`}>
                              <span
                                className={point.value >= 0 ? 'sparkline-bar up' : 'sparkline-bar down'}
                                style={{ height: `${Math.max(10, Math.min(72, Math.abs(point.value) / 1500000))}px` }}
                              />
                              <small>{point.label}</small>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="visual-item">
                        <h4>Doanh thu vs Chi phí</h4>
                        <div className="bar-duo">
                          <div className="bar-row"><span>Doanh thu</span><div className="bar-track"><div className="bar-fill revenue" style={{ width: `${Math.min(100, 35 + (reportRevenue > 0 ? 65 : 0))}%` }} /></div></div>
                          <div className="bar-row"><span>Chi phí</span><div className="bar-track"><div className="bar-fill cost" style={{ width: `${Math.min(100, Math.max(10, reportRevenue > 0 ? (reportCost / reportRevenue) * 100 : 10))}%` }} /></div></div>
                        </div>
                      </div>
                      <div className="visual-item">
                        <h4>Công nợ theo nhóm</h4>
                        <div className="bar-duo">
                          {debtBalanceSeries.map((point) => (
                            <div className="bar-row" key={point.label}>
                              <span>{point.label}</span>
                              <div className="bar-track">
                                <div className={point.label === 'Phải trả' ? 'bar-fill debt' : 'bar-fill receivable'} style={{ width: `${Math.max(12, Math.min(100, (point.value / Math.max(payableValue, receivableValue, 1)) * 100))}%` }} />
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </article>

                  <article className="detail-row dashboard-bottom-grid">
                    <section className="dashboard-alert-card">
                      <h3>Cảnh báo trọng yếu</h3>
                      <ul>
                        {dashboardWarnings.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </section>
                    <section className="dashboard-action-card">
                      <h3>Hành động đề xuất</h3>
                      <div className="action-buttons">
                        <button
                          type="button"
                          className="action-btn"
                          onClick={() => {
                            setReportTab('can_doi_ke_toan')
                            setReportDrillTab('cong_no')
                            setActiveSection('reports')
                          }}
                        >
                          Mở báo cáo công nợ
                        </button>
                        <button
                          type="button"
                          className="action-btn"
                          onClick={() => {
                            setReportTab('hieu_qua_kinh_doanh')
                            setReportDrillTab('chi_phi')
                            setActiveSection('reports')
                          }}
                        >
                          Mở báo cáo chi phí
                        </button>
                      </div>
                    </section>
                    {dashboardComplianceAlert ? (
                      <section className="dashboard-compliance-callout">
                        <h3>Nhắc nộp báo cáo</h3>
                        <p>
                          {dashboardComplianceAlert.status === 'qua_han' ? 'Quá hạn' : 'Sắp đến hạn'}: {dashboardComplianceAlert.name} - hạn {String(dashboardComplianceAlert.due_date || '').slice(8, 10)}/{String(dashboardComplianceAlert.due_date || '').slice(5, 7)}
                        </p>
                        <button
                          type="button"
                          className="action-btn"
                          onClick={() => {
                            setComplianceReportId(String(dashboardComplianceAlert.report_id))
                            setActiveSection('compliance')
                          }}
                        >
                          Nộp ngay
                        </button>
                      </section>
                    ) : null}
                  </article>
                </div>
              ) : null}

              {activeSection === 'reports' ? (
                <div className="detail-list report-analysis-layout">
                  <article className="detail-row report-filter-row">
                    <label>
                      Kỳ báo cáo
                      <select value={reportPeriod} onChange={(event) => setReportPeriod(event.target.value)}>
                        <option value="7_ngay">7 ngày</option>
                        <option value="30_ngay">30 ngày</option>
                        <option value="quy_nay">Quý này</option>
                        <option value="nam_nay">Năm nay</option>
                      </select>
                    </label>
                    <label>
                      Đơn vị
                      <select value={reportEntity} onChange={(event) => setReportEntity(event.target.value)}>
                        <option value="toan_bo">Toàn doanh nghiệp</option>
                        <option value="chi_nhanh_bac">Chi nhánh Bắc</option>
                        <option value="chi_nhanh_nam">Chi nhánh Nam</option>
                      </select>
                    </label>
                    <label>
                      Lọc giao dịch
                      <select value={reportTxnFilter} onChange={(event) => setReportTxnFilter(event.target.value)}>
                        <option value="tat_ca">Tất cả</option>
                        <option value="gia_tri_lon">Giá trị lớn</option>
                        <option value="rui_ro">Rủi ro cao</option>
                      </select>
                    </label>
                  </article>

                  <article className="detail-row">
                    <div className="report-tab-row">
                      {[
                        { key: 'hieu_qua_kinh_doanh', label: 'Hiệu quả kinh doanh' },
                        { key: 'can_doi_ke_toan', label: 'Sức khỏe tài chính' },
                        { key: 'dong_tien', label: 'Dòng tiền' },
                      ].map((tab) => (
                        <button
                          key={tab.key}
                          type="button"
                          className={reportTab === tab.key ? 'report-tab-btn active' : 'report-tab-btn'}
                          onClick={() => setReportTab(tab.key)}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>
                  </article>

                  <article className="detail-row report-summary-plain">
                    <div>
                      <span>Doanh thu</span>
                      <strong>{formatCurrency(reportRevenue)}</strong>
                    </div>
                    <div>
                      <span>Lợi nhuận</span>
                      <strong className={reportProfit >= 0 ? 'metric-up' : 'metric-down'}>{formatCurrency(reportProfit)}</strong>
                    </div>
                    <div>
                      <span>Dòng tiền thuần</span>
                      <strong className={reportCashNet >= 0 ? 'metric-up' : 'metric-down'}>{formatCurrency(reportCashNet)}</strong>
                    </div>
                  </article>

                  <article className="detail-row report-to-compliance">
                    <p>
                      Nguồn dữ liệu từ Reports đã sẵn sàng để đóng gói tờ khai. Ví dụ: lợi nhuận hiện tại {formatCurrency(reportProfit)} sẽ dùng để tính TNDN tạm tính.
                    </p>
                    <button
                      type="button"
                      className="action-btn"
                      onClick={() => {
                        setComplianceReportId('tndn')
                        setComplianceDetailTab('preview')
                        setActiveSection('compliance')
                      }}
                    >
                      Mở Tuân thủ & Kê khai
                    </button>
                  </article>

                  <article className="detail-row report-detail-card">
                    <div className="report-detail-head">
                      <h3>Bảng phân tích chính</h3>
                      <p>
                        {reportDetail?.tt133?.basis || 'Thông tư 133/2016/TT-BTC'} | Dữ liệu đến ngày {reportDetail?.as_of_date || reportAsOfDate}
                      </p>
                    </div>

                    {reportLoading ? <p className="report-inline-note">Đang tải dữ liệu báo cáo chi tiết...</p> : null}
                    {reportError ? <p className="report-inline-note report-error">{reportError}</p> : null}

                    {!reportLoading && !reportError && reportDetail ? (
                      <>
                        {reportTab === 'hieu_qua_kinh_doanh' ? (
                          <div className="report-table-wrap">
                            <table className="report-table report-table-compact">
                              <thead>
                                <tr>
                                  <th>Mã số</th>
                                  <th>Chỉ tiêu</th>
                                  <th>Số tiền</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(reportDetail.tt133?.pl_rows || []).map((row) => (
                                  <tr key={row.code}>
                                    <td>{row.code}</td>
                                    <td>{row.item}</td>
                                    <td>{formatCurrency(row.amount)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : null}

                        {reportTab === 'can_doi_ke_toan' ? (
                          <div className="report-table-wrap">
                            <table className="report-table report-table-compact">
                              <thead>
                                <tr>
                                  <th>Mã số</th>
                                  <th>Chỉ tiêu</th>
                                  <th>Số tiền</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(reportDetail.tt133?.bs_rows || []).map((row) => (
                                  <tr key={row.code}>
                                    <td>{row.code}</td>
                                    <td>{row.item}</td>
                                    <td>{formatCurrency(row.amount)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : null}

                        {reportTab === 'dong_tien' ? (
                          <div className="report-table-wrap">
                            <table className="report-table report-table-compact">
                              <thead>
                                <tr>
                                  <th>Mã số</th>
                                  <th>Chỉ tiêu</th>
                                  <th>Số tiền</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(reportDetail.tt133?.cf_rows || []).map((row) => (
                                  <tr key={row.code}>
                                    <td>{row.code}</td>
                                    <td>{row.item}</td>
                                    <td>{formatCurrency(row.amount)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : null}
                      </>
                    ) : null}
                  </article>

                  <article className="detail-row report-drill-row">
                    <div className="report-tab-row">
                      {[
                        { key: 'giao_dich', label: 'Giao dịch' },
                        { key: 'cong_no', label: 'Công nợ' },
                        { key: 'chi_phi', label: 'Chi phí' },
                      ].map((tab) => (
                        <button
                          key={tab.key}
                          type="button"
                          className={reportDrillTab === tab.key ? 'report-tab-btn active' : 'report-tab-btn'}
                          onClick={() => setReportDrillTab(tab.key)}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>
                    <div className="report-table-wrap">
                      <table className="report-table report-table-compact">
                        <thead>
                          <tr>
                            <th>Nhóm</th>
                            <th>Diễn giải</th>
                            <th>Giá trị</th>
                          </tr>
                        </thead>
                        <tbody>
                          {reportDrillTab === 'giao_dich' ? (reportDetail?.gl?.items || []).slice(-8).map((item) => (
                            <tr key={item.entry_id}>
                              <td>Giao dịch</td>
                              <td>{item.narration || item.entry_id}</td>
                              <td>{formatCurrency(item.debit_total)}</td>
                            </tr>
                          )) : null}
                          {reportDrillTab === 'cong_no' ? (
                            <>
                              <tr><td>Công nợ</td><td>Phải trả</td><td>{formatCurrency(payableValue)}</td></tr>
                              <tr><td>Công nợ</td><td>Phải thu</td><td>{formatCurrency(receivableValue)}</td></tr>
                            </>
                          ) : null}
                          {reportDrillTab === 'chi_phi' ? (
                            <>
                              <tr><td>Chi phí</td><td>Tổng chi phí kỳ</td><td>{formatCurrency(reportCost)}</td></tr>
                              <tr><td>Chi phí</td><td>Tỷ trọng chi phí / doanh thu</td><td>{reportCostRatioPct.toFixed(1)}%</td></tr>
                            </>
                          ) : null}
                        </tbody>
                      </table>
                    </div>
                  </article>
                </div>
              ) : null}

              {activeSection === 'compliance' ? (
                <div className="detail-list compliance-layout">
                  <article className="detail-row compliance-period-row">
                    <label>
                      Kỳ báo cáo
                      <select value={compliancePeriod} onChange={(event) => setCompliancePeriod(event.target.value)}>
                        {(Array.isArray(complianceData?.period_options) && complianceData.period_options.length
                          ? complianceData.period_options
                          : [{ value: compliancePeriod, label: compliancePeriod }]
                        ).map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </label>
                  </article>

                  <article className="detail-row compliance-list-row">
                    <h3>Danh sách báo cáo phải nộp</h3>
                    <div className="compliance-report-list">
                      {normalizedFilingReports.map((item) => {
                        const statusLabel = item.status === 'da_nop' ? 'Đã nộp' : item.status === 'qua_han' ? 'Quá hạn' : 'Chưa nộp'
                        return (
                          <button
                            key={item.report_id}
                            type="button"
                            className={String(item.report_id) === complianceReportId ? 'compliance-report-item active' : 'compliance-report-item'}
                            onClick={() => setComplianceReportId(String(item.report_id))}
                          >
                            <span className="compliance-report-name">{item.name}</span>
                            <span className={item.status === 'da_nop' ? 'status-pill status-hoan_tat' : item.status === 'qua_han' ? 'status-pill status-cho_duyet' : 'status-pill status-dang_xu_ly'}>
                              {statusLabel}
                            </span>
                            <span className="compliance-report-due">{item.status === 'da_nop' ? '✓ Đã nộp' : `Hạn: ${String(item.due_date || '').slice(8, 10)}/${String(item.due_date || '').slice(5, 7)}`}</span>
                          </button>
                        )
                      })}
                    </div>
                  </article>

                  <article className="detail-row compliance-detail-row">
                    <h3>Chi tiết báo cáo</h3>
                    <div className="report-tab-row">
                      {[
                        { key: 'preview', label: 'Preview' },
                        { key: 'xml', label: 'XML' },
                        { key: 'history', label: 'Lịch sử nộp' },
                      ].map((tab) => (
                        <button
                          key={tab.key}
                          type="button"
                          className={complianceDetailTab === tab.key ? 'report-tab-btn active' : 'report-tab-btn'}
                          onClick={() => setComplianceDetailTab(tab.key)}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>

                    {complianceDetailTab === 'preview' ? (
                      <div className="compliance-preview-box">
                        <p><strong>Biểu mẫu:</strong> {complianceActiveReport?.name || 'Báo cáo thuế'}</p>
                        <p><strong>Số liệu nguồn từ Reports:</strong> Doanh thu {formatCurrency(reportRevenue)} | Lợi nhuận {formatCurrency(reportProfit)}</p>
                        <p><strong>Số tạm tính:</strong> {formatCurrency(complianceActiveReport?.amount || 0)}</p>
                      </div>
                    ) : null}

                    {complianceDetailTab === 'xml' ? (
                      <div className="compliance-preview-box">
                        <pre>{complianceData?.xml_preview || ''}</pre>
                      </div>
                    ) : null}

                    {complianceDetailTab === 'history' ? (
                      <div className="report-table-wrap">
                        <table className="report-table report-table-compact">
                          <thead>
                            <tr>
                              <th>Mã</th>
                              <th>Báo cáo</th>
                              <th>Người nộp</th>
                              <th>Thời gian</th>
                              <th>File</th>
                            </tr>
                          </thead>
                          <tbody>
                            {filingHistory.map((item) => (
                              <tr key={item.history_id}>
                                <td>{item.history_id}</td>
                                <td>{item.report}</td>
                                <td>{item.submittedBy}</td>
                                <td>{item.submittedAt}</td>
                                <td>{item.fileName}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : null}

                    <div className="action-buttons">
                      <button type="button" className="action-btn" onClick={() => downloadComplianceFile('xml')}>Xuất XML</button>
                      <button type="button" className="action-btn" onClick={() => downloadComplianceFile('pdf')}>Tải PDF</button>
                      <button type="button" className="action-btn" onClick={handleSubmitCompliance}>Nộp điện tử</button>
                    </div>
                  </article>

                  <article className="detail-row compliance-check-row">
                    <h3>Auto-check lỗi trước khi nộp</h3>
                    <ul>
                      {filingIssues.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </article>
                </div>
              ) : null}

              {activeSection === 'settings' ? (
                <div className="detail-list">
                  {modeToggleConfig ? (
                    <article className="detail-row mode-setting-row">
                      <div className="mode-setting-title">
                        <h3>{modeToggleConfig.title || 'Chế độ kế toán nâng cao'}</h3>
                        <p>
                          {modeToggleConfig.text ||
                            'Cho phép hạch toán chuyên sâu với bút toán nhiều lớp, phân bổ tự động và kiểm soát ràng buộc nâng cao.'}
                        </p>
                      </div>
                      <button
                        type="button"
                        className={isAdvancedMode ? 'mode-toggle active' : 'mode-toggle'}
                        onClick={() => setIsAdvancedMode((prev) => !prev)}
                      >
                        <Cpu size={16} />
                        <span>
                          {isAdvancedMode
                            ? modeToggleConfig.cta_off || 'Tắt Advanced Mode'
                            : modeToggleConfig.cta_on || 'Bật Advanced Mode'}
                        </span>
                      </button>
                    </article>
                  ) : null}
                  {detailRows.map((row) => (
                    <article className="detail-row" key={`${row.title}-${row.text}`}>
                      <h3>{row.title}</h3>
                      <p>{row.text}</p>
                    </article>
                  ))}
                </div>
              ) : null}
            </section>
          )}
        </main>

        <div
          className={dragSide === 'right' ? 'resize-handle active' : 'resize-handle'}
          onMouseDown={() => setDragSide('right')}
          role="separator"
          aria-label="Thay đổi độ rộng dòng sự kiện và bảng thông minh"
        />

        <aside className={activeSection === 'cases' ? 'right-panel right-panel-cases' : 'right-panel'}>
          {activeSection === 'cases' ? (
            <>
              <section className="intel-block">
                <h2>Chứng từ</h2>
                <div className="evidence-list scrollable-pane">
                  {evidence.map((name) => (
                    <a
                      href="#"
                      key={name}
                      className="evidence-item"
                      onClick={(event) => {
                        event.preventDefault()
                        openPreview(name)
                      }}
                    >
                      <FileText size={15} />
                      <span>{name}</span>
                    </a>
                  ))}
                </div>
              </section>

              <section className="intel-block">
                <h2>Lý giải của AI</h2>
                <ul className="reasoning-list scrollable-pane">
                  {reasoning.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                  {isAdvancedMode ? <li>Đang hiển thị thêm lớp kiểm soát chuyên sâu cho kế toán viên.</li> : null}
                </ul>
              </section>

              <button
                type="button"
                className="delete-case-btn"
                onClick={() => setIsDeleteModalOpen(true)}
                disabled={!activeCase}
              >
                Xóa hồ sơ
              </button>
            </>
          ) : (
            <>
              <section className="intel-block">
                <h2>{sideCompanion.title}</h2>
                <p>{sideCompanion.subtitle}</p>
                <ul>
                  {sideCompanion.highlights.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>

              {activeSection === 'dashboard' ? (
                <section className="intel-block">
                  <h2>Ưu tiên hôm nay</h2>
                  <ol className="priority-list">
                    {dashboardPriorities.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ol>
                </section>
              ) : activeSection === 'reports' ? (
                <section className="intel-block">
                  <h2>Mẹo phân tích</h2>
                  <ul>
                    {(Array.isArray(serverPanels?.reports_tips) ? serverPanels.reports_tips : []).map((tip) => (
                      <li key={tip}>{tip}</li>
                    ))}
                  </ul>
                </section>
              ) : activeSection === 'compliance' ? (
                <section className="intel-block">
                  <h2>Checklist nộp báo cáo</h2>
                  <ul>
                    {(Array.isArray(serverPanels?.compliance_checklist) ? serverPanels.compliance_checklist : []).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </section>
              ) : (
                <section className="intel-block">
                  <h2>Thao tác nhanh</h2>
                  <div className="evidence-list">
                    {sideCompanion.actions.map((item) => (
                      <a
                        href="#"
                        key={item}
                        className="evidence-item"
                        onClick={(event) => {
                          event.preventDefault()
                          handleCompanionAction(item)
                        }}
                      >
                        <FileText size={15} />
                        <span>{item}</span>
                      </a>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
        </aside>
          </>
        )}
      </div>

      {isDeleteModalOpen && activeCase ? (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="delete-modal-title">
          <div className="modal-card">
            <h3 id="delete-modal-title">Xác nhận xóa hồ sơ</h3>
            <p>
              Bạn sắp xóa hồ sơ <strong>{activeCase.title}</strong>.
            </p>
            <p className="modal-warning">Hành động này không thể khôi phục.</p>
            <div className="modal-actions">
              <button type="button" className="modal-btn secondary" onClick={() => setIsDeleteModalOpen(false)}>
                Hủy
              </button>
              <button type="button" className="modal-btn danger" onClick={confirmDeleteActiveCase}>
                Xóa hồ sơ
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {previewFileName ? (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="preview-modal-title"
          onClick={closePreview}
        >
          <div className="modal-card preview-modal-card" onClick={(event) => event.stopPropagation()}>
            <h3 id="preview-modal-title">Xem nhanh chứng từ</h3>
            <p className="preview-file-name">{previewFileName}</p>
            <div className="preview-surface">
              {isPdfPreview ? (
                <object data={previewFileUrl} type="application/pdf" className="preview-object">
                  <div className="preview-file-meta">
                    <FileText size={22} />
                    <div>
                      <strong>{previewFileName}</strong>
                      <p>Trình duyệt không hỗ trợ PDF inline. Hãy mở ở tab mới.</p>
                    </div>
                  </div>
                </object>
              ) : null}

              {isImagePreview ? <img src={previewFileUrl} alt={previewFileName} className="preview-image" /> : null}

              {officeViewerUrl ? (
                <iframe
                  title="Xem tài liệu Microsoft Office"
                  className="preview-office-frame"
                  src={officeViewerUrl}
                />
              ) : null}

              {isDocxPagePreview ? (
                <div className="docx-preview-wrap">
                  {docxLoading ? <p>Đang dựng tài liệu DOCX theo từng trang...</p> : null}
                  {docxError ? <p>{docxError}</p> : null}
                  <div className="docx-preview-host" ref={docxPreviewRef} />
                </div>
              ) : null}

              {isStructuredPreview ? (
                <div className="structured-preview">
                  {isDocPreview && !officeViewerUrl ? (
                    <p>
                      File DOC đang được xem ở chế độ tương thích. Để hiển thị giống Microsoft theo từng trang, hãy dùng DOCX
                      hoặc mở trên môi trường HTTPS công khai để dùng trình xem Office.
                    </p>
                  ) : null}
                  {structuredLoading ? <p>Đang dựng bảng dữ liệu chuẩn...</p> : null}
                  {structuredError ? <p>{structuredError}</p> : null}
                  {!structuredLoading && !structuredError
                    ? structuredSections.map((section) => (
                        <section key={section.title} className="structured-section">
                          <h4>{section.title}</h4>
                          <table className="structured-table">
                            <thead>
                              <tr>
                                <th>Chỉ tiêu</th>
                                <th>Giá trị</th>
                              </tr>
                            </thead>
                            <tbody>
                              {section.rows.map((row) => (
                                <tr key={`${section.title}-${row.label}`}>
                                  <td>{row.label}</td>
                                  <td>{isXmlPreview ? <TypingText text={row.value} speed={6} /> : row.value}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </section>
                      ))
                    : null}
                </div>
              ) : null}

              {!isPdfPreview && !isImagePreview && !isStructuredPreview && !isDocxPagePreview && !officeViewerUrl ? (
                <div className="preview-file-meta">
                  <FileText size={22} />
                  <div>
                    <strong>{previewFileName}</strong>
                    <p>Định dạng này hiện xem nhanh ở mức thông tin cơ bản.</p>
                  </div>
                </div>
              ) : null}
            </div>
            <div className="modal-actions">
              <a href={previewFileUrl} className="modal-btn secondary" target="_blank" rel="noreferrer">
                Mở tab mới
              </a>
              <a href={previewFileUrl} className="modal-btn secondary" download={previewFileName}>
                Tải về
              </a>
              <button type="button" className="modal-btn secondary" onClick={closePreview}>
                Đóng
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default App
