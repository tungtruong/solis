import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Bell,
  Bot,
  ChevronDown,
  ChevronRight,
  Cpu,
  FileCheck2,
  FileText,
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
const STORAGE_TOKEN_KEY = 'solis.auth.token'
const STORAGE_COMPANY_ID_KEY = 'solis.auth.companyId'
const STORAGE_COMPANY_NAME_KEY = 'solis.auth.companyName'
const STORAGE_UI_LANG_KEY = 'solis.ui.lang'

const initialCaseItems = []
const defaultStatusOptions = [{ value: 'tat_ca', label: 'All' }]

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

function normalizeCaseItem(raw, fallbackIndex = 0, statusLabelMapInput = {}) {
  if (!raw || typeof raw !== 'object') return null
  const id = raw.id || raw.case_id || `case-fallback-${fallbackIndex}`
  const status = raw.status || 'moi'
  const statusLabelMap = {
    moi: 'New',
    dang_xu_ly: 'Processing',
    cho_xac_nhan: 'Pending customer confirmation',
    cho_duyet: 'Pending approval',
    hoan_tat: 'Completed',
    ...statusLabelMapInput,
  }

  const normalizeEvidenceEntry = (entry, fallbackStaged = false) => {
    if (typeof entry === 'string') {
      const name = String(entry).trim()
      if (!name) return null
      return {
        name,
        previewRef: name,
        isStaged: Boolean(fallbackStaged),
      }
    }
    if (!entry || typeof entry !== 'object') return null

    const name = String(entry.name || entry.display_name || entry.file_name || entry.stored_name || entry.preview_ref || '').trim()
    if (!name) return null
    const previewRef = String(entry.preview_ref || entry.ref || entry.stored_name || name).trim()
    const isStaged = Boolean(
      entry.is_staged ||
      entry.storage === 'staging' ||
      fallbackStaged ||
      previewRef.startsWith('stg__'),
    )
    return {
      name,
      previewRef,
      isStaged,
    }
  }

  const committedEvidence = Array.isArray(raw.evidence)
    ? raw.evidence.map((entry) => normalizeEvidenceEntry(entry, false)).filter(Boolean)
    : []

  const mergedEvidenceMap = new Map()
  committedEvidence.forEach((entry) => {
    const key = String(entry.previewRef || entry.name || '')
    if (!key || mergedEvidenceMap.has(key)) return
    mergedEvidenceMap.set(key, entry)
  })

  return {
    id,
    code: raw.code || String(id).toUpperCase(),
    title: raw.title || 'Accounting case',
    partner: raw.partner || raw.counterparty_name || 'Partner',
    amount: raw.amount || '0 VND',
    updatedAt: raw.updatedAt || raw.event_date || 'Just now',
    status,
    statusLabel: raw.statusLabel || statusLabelMap[status] || statusLabelMap.moi,
    timeline: Array.isArray(raw.timeline) ? raw.timeline : [],
    evidence: Array.from(mergedEvidenceMap.values()),
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

function formatDateByRule(dateValue) {
  const raw = String(dateValue || '').trim()
  if (!raw || raw === '-') return raw
  const tokenMatch = raw.match(/(\d{4}[\-/]\d{1,2}[\-/]\d{1,2}|\d{1,2}[\-/]\d{1,2}[\-/]\d{4}|\d{8})/)
  if (!tokenMatch) return raw
  const token = tokenMatch[1].replace(/\//g, '-')

  if (/^\d{8}$/.test(token)) {
    const yyyy = token.slice(0, 4)
    const mm = token.slice(4, 6)
    const dd = token.slice(6, 8)
    return `${dd}/${mm}/${yyyy}`
  }

  const parts = token.split('-')
  if (parts.length !== 3) return raw

  if (parts[0].length === 4) {
    const [yyyy, mm, dd] = parts
    return `${String(dd).padStart(2, '0')}/${String(mm).padStart(2, '0')}/${yyyy}`
  }

  const [dd, mm, yyyy] = parts
  return `${String(dd).padStart(2, '0')}/${String(mm).padStart(2, '0')}/${yyyy}`
}

function extractYearFromToken(value) {
  const text = String(value || '').trim()
  const matched = text.match(/(\d{4})/)
  if (!matched) return new Date().getFullYear()
  return Number(matched[1])
}

const openingBalanceFields = [
  { code: 'ct110', labelVi: 'Tổng tài sản', labelEn: 'Total assets' },
  { code: 'ct120', labelVi: 'Tiền và tương đương tiền', labelEn: 'Cash and equivalents' },
  { code: 'ct130', labelVi: 'Đầu tư tài chính ngắn hạn', labelEn: 'Short-term investments' },
  { code: 'ct140', labelVi: 'Các khoản phải thu', labelEn: 'Receivables' },
  { code: 'ct150', labelVi: 'Hàng tồn kho', labelEn: 'Inventories' },
  { code: 'ct160', labelVi: 'Tài sản khác', labelEn: 'Other assets' },
  { code: 'ct200', labelVi: 'Tổng cộng tài sản', labelEn: 'Total assets (sum)' },
  { code: 'ct300', labelVi: 'Nợ phải trả', labelEn: 'Liabilities' },
  { code: 'ct310', labelVi: 'Nợ ngắn hạn', labelEn: 'Short-term liabilities' },
  { code: 'ct320', labelVi: 'Nợ dài hạn', labelEn: 'Long-term liabilities' },
  { code: 'ct330', labelVi: 'Phải trả người bán', labelEn: 'Trade payables' },
  { code: 'ct340', labelVi: 'Thuế và khoản phải nộp', labelEn: 'Taxes payable' },
  { code: 'ct350', labelVi: 'Phải trả người lao động', labelEn: 'Payroll payables' },
  { code: 'ct360', labelVi: 'Phải trả khác', labelEn: 'Other payables' },
  { code: 'ct400', labelVi: 'Vốn chủ sở hữu', labelEn: 'Equity' },
  { code: 'ct411', labelVi: 'Vốn góp của chủ sở hữu', labelEn: 'Owner contributed capital' },
  { code: 'ct412', labelVi: 'Thặng dư vốn cổ phần', labelEn: 'Share premium' },
  { code: 'ct413', labelVi: 'Chênh lệch đánh giá lại', labelEn: 'Revaluation differences' },
  { code: 'ct414', labelVi: 'Quỹ đầu tư phát triển', labelEn: 'Development investment fund' },
  { code: 'ct415', labelVi: 'Quỹ khác', labelEn: 'Other funds' },
  { code: 'ct416', labelVi: 'Lợi nhuận sau thuế chưa phân phối', labelEn: 'Retained earnings' },
  { code: 'ct417', labelVi: 'Nguồn vốn khác', labelEn: 'Other equity sources' },
  { code: 'ct420', labelVi: 'Lợi nhuận sau thuế chưa phân phối', labelEn: 'Retained earnings (detail)' },
  { code: 'ct430', labelVi: 'Nguồn kinh phí và quỹ khác', labelEn: 'Funding and other funds' },
  { code: 'ct440', labelVi: 'Lợi ích cổ đông không kiểm soát', labelEn: 'Minority interests' },
  { code: 'ct500', labelVi: 'Tổng cộng nguồn vốn', labelEn: 'Total liabilities and equity' },
]

function normalizeComparableText(value) {
  const raw = String(value || '').trim().toLowerCase()
  if (!raw) return ''
  return raw
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]/g, '')
}

function normalizeParseSummaryRows(rows, options = {}) {
  if (!Array.isArray(rows) || !rows.length) return []

  const companyName = String(options.currentCompanyName || '').trim()
  const fallbackPartnerCandidates = Array.isArray(options.fallbackPartnerCandidates)
    ? options.fallbackPartnerCandidates
    : []
  const companyNameNorm = normalizeComparableText(companyName)

  const deniedLabels = new Set(['MST người bán', 'MST người mua', 'Vai trò hóa đơn'])
  const allowedOrder = [
    'Đối tác',
    'Nội dung',
    'MST đối tác',
    'Số hóa đơn',
    'Ngày hóa đơn',
    'Số tiền trước thuế',
    'Thuế VAT',
    'Số tiền sau thuế',
    'Số tiền',
  ]
  const normalizedByLabel = new Map()

  rows.forEach((row) => {
    const rawLabel = String(row?.label || '').trim()
    const rawValue = String(row?.value || '').trim()
    if (!rawLabel || deniedLabels.has(rawLabel)) return

    let normalizedLabel = rawLabel
    if (rawLabel === 'Nhà cung cấp') {
      normalizedLabel = 'Đối tác'
    } else if (rawLabel === 'Mã số thuế' || rawLabel === 'MST') {
      normalizedLabel = 'MST đối tác'
    } else if (rawLabel === 'Số tiền') {
      normalizedLabel = 'Số tiền sau thuế'
    }

    if (!allowedOrder.includes(normalizedLabel)) return
    if (normalizedLabel === 'MST đối tác' && (!rawValue || rawValue === '-')) return

    const normalizedValue = normalizedLabel === 'Ngày hóa đơn'
      ? (formatDateByRule(rawValue) || '-')
      : (rawValue || '-')

    const existing = normalizedByLabel.get(normalizedLabel)
    if (!existing || (existing === '-' && normalizedValue !== '-')) {
      normalizedByLabel.set(normalizedLabel, normalizedValue)
    }
  })

  return allowedOrder
    .filter((label) => normalizedByLabel.has(label))
    .map((label) => ({ label, value: normalizedByLabel.get(label) }))
    .map((row) => {
      if (row.label !== 'Đối tác') return row
      const partnerNorm = normalizeComparableText(row.value)
      const sameAsCompany = Boolean(companyNameNorm && partnerNorm && (
        companyNameNorm.includes(partnerNorm) || partnerNorm.includes(companyNameNorm)
      ))
      if (!sameAsCompany) return row

      const replacement = fallbackPartnerCandidates.find((candidate) => {
        const candidateText = String(candidate || '').trim()
        if (!candidateText) return false
        const candidateNorm = normalizeComparableText(candidateText)
        if (!candidateNorm) return false
        if (!companyNameNorm) return true
        return !(companyNameNorm.includes(candidateNorm) || candidateNorm.includes(companyNameNorm))
      })

      return {
        ...row,
        value: String(replacement || 'Đối tác'),
      }
    })
}

function formatReportNarration(value, fallback = '') {
  let text = String(value || '').trim()
  if (!text) {
    text = String(fallback || '').trim()
  }
  if (!text) return '-'

  text = text
    .replace(/\b(?:số\s*tiền|so\s*tien|trị\s*giá|tri\s*gia|giá\s*trị|gia\s*tri)\b\s*[:\-]?\s*[^,.;:!?]*/gi, '')
    .replace(/\b\d{1,3}(?:[\.\,\s]\d{3})+(?:\s*(?:đ|đồng|dong|vnd))?\b/gi, '')
    .replace(/\b\d+(?:[\.,]\d+)?\s*(?:tỷ|ty|triệu|trieu|nghìn|nghin|ngàn|ngan|k)\s*(?:đồng|dong)?\b/gi, '')
    .replace(/,\s+(?=[A-Za-zÀ-ỹ])/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .replace(/\s+([,.;:!?])/g, '$1')
    .trim()

  return text || String(fallback || '').trim() || '-'
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
  const userMenuRef = useRef(null)
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
  const [previewFileRef, setPreviewFileRef] = useState('')
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
  const [currentCompanyId, setCurrentCompanyId] = useState('')
  const [currentCompanyName, setCurrentCompanyName] = useState('')
  const [companyChoices, setCompanyChoices] = useState([])
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false)
  const [isCompanyEditOpen, setIsCompanyEditOpen] = useState(false)
  const [isCompanySaving, setIsCompanySaving] = useState(false)
  const [companyEditError, setCompanyEditError] = useState('')
  const [companyEditSuccess, setCompanyEditSuccess] = useState('')
  const [companyEditForm, setCompanyEditForm] = useState({
    company_id: '',
    company_name: '',
    tax_code: '',
    address: '',
    legal_representative: '',
    established_date: '',
    accounting_software_start_date: '',
    fiscal_year_start: '',
    tax_declaration_cycle: 'thang',
    default_bank_account: '',
    accountant_email: '',
  })
  const [reportDetail, setReportDetail] = useState(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState('')
  const [reportTab, setReportTab] = useState('hieu_qua_kinh_doanh')
  const [reportPeriod, setReportPeriod] = useState('30_ngay')
  const [reportEntity, setReportEntity] = useState('cong_ty_hien_tai')
  const [reportTxnFilter, setReportTxnFilter] = useState('tat_ca')
  const [reportDrillTab, setReportDrillTab] = useState('giao_dich')
  const [dashboardQuery, setDashboardQuery] = useState('')
  const [compliancePeriod, setCompliancePeriod] = useState('2026-03')
  const [complianceReportId, setComplianceReportId] = useState('gtgt')
  const [complianceDetailTab, setComplianceDetailTab] = useState('preview')
  const [openingBalanceYear, setOpeningBalanceYear] = useState(2026)
  const [openingBalanceLines, setOpeningBalanceLines] = useState({})
  const [openingBalanceSource, setOpeningBalanceSource] = useState('none')
  const [openingBalanceSourceYear, setOpeningBalanceSourceYear] = useState(null)
  const [openingBalanceLoading, setOpeningBalanceLoading] = useState(false)
  const [openingBalanceNotice, setOpeningBalanceNotice] = useState('')
  const [voucherTestFile, setVoucherTestFile] = useState(null)
  const [voucherTestLoading, setVoucherTestLoading] = useState(false)
  const [voucherTestNotice, setVoucherTestNotice] = useState('')
  const [voucherTestSummary, setVoucherTestSummary] = useState(null)
  const [voucherTestRows, setVoucherTestRows] = useState([])
  const [voucherTestPostResults, setVoucherTestPostResults] = useState([])
  const [dashboardMeta, setDashboardMeta] = useState({ trends: {}, warnings: [], priorities: [] })
  const [complianceData, setComplianceData] = useState({ period_options: [], reports: [], issues: [], history: [], xml_preview: '' })
  const [serverPanels, setServerPanels] = useState({ reports_tips: [], compliance_checklist: [] })
  const [actionNotice, setActionNotice] = useState('')
  const [caseActionNotice, setCaseActionNotice] = useState('')
  const [isSendingCaseCommand, setIsSendingCaseCommand] = useState(false)
  const [timelineVisibleCount, setTimelineVisibleCount] = useState(0)
  const [reportDrillColumnWidths, setReportDrillColumnWidths] = useState({
    first: 170,
    second: 520,
  })
  const [reportDrillResize, setReportDrillResize] = useState(null)
  const openingImportInputRef = useRef(null)
  const voucherTestInputRef = useRef(null)
  const [uiLang, setUiLang] = useState(() => {
    const stored = String(window.sessionStorage.getItem(STORAGE_UI_LANG_KEY) || 'vi').toLowerCase()
    return stored === 'en' ? 'en' : 'vi'
  })
  const typedMessageKeysRef = useRef(new Set())

  const tr = useCallback((vi, en) => (uiLang === 'en' ? en : vi), [uiLang])
  const localizeRuntimeText = useCallback((value) => {
    const text = String(value || '').trim()
    if (!text || uiLang !== 'en') return text

    return text
      .replace(/\bquá hạn\b/gi, 'overdue')
      .replace(/\bsắp đến hạn\b/gi, 'due soon')
      .replace(/\bhạn nộp\b/gi, 'due date')
      .replace(/\bbáo cáo\b/gi, 'report')
      .replace(/\bdòng tiền\b/gi, 'cashflow')
      .replace(/\bcông nợ phải trả\b/gi, 'accounts payable')
      .replace(/\bcông nợ phải thu\b/gi, 'accounts receivable')
      .replace(/\bcông nợ\b/gi, 'debt')
      .replace(/\bphải trả\b/gi, 'payables')
      .replace(/\bphải thu\b/gi, 'receivables')
      .replace(/\bdoanh thu\b/gi, 'revenue')
      .replace(/\bchi phí\b/gi, 'cost')
      .replace(/\blợi nhuận\b/gi, 'profit')
      .replace(/\bthuế\s*vat\b/gi, 'VAT')
      .replace(/\bchưa nộp\b/gi, 'not submitted')
      .replace(/\bđã nộp\b/gi, 'submitted')
      .replace(/\bkê khai\b/gi, 'filing')
      .replace(/\btuân thủ\b/gi, 'compliance')
      .replace(/\bhồ sơ\b/gi, 'case')
  }, [uiLang])
  const caseStatusLabelMap = useMemo(() => ({
    moi: tr('Mới', 'New'),
    dang_xu_ly: tr('Đang xử lý', 'Processing'),
    cho_xac_nhan: tr('Chờ khách hàng xác nhận', 'Pending customer confirmation'),
    cho_duyet: tr('Chờ duyệt', 'Pending approval'),
    hoan_tat: tr('Hoàn tất', 'Completed'),
  }), [tr])

  const toggleUiLang = useCallback(() => {
    setUiLang((prev) => {
      const next = prev === 'vi' ? 'en' : 'vi'
      window.sessionStorage.setItem(STORAGE_UI_LANG_KEY, next)
      return next
    })
  }, [])

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
      const params = new URLSearchParams()
      const initialEmail = String(window.sessionStorage.getItem('solis.auth.email') || '')
      const initialCompanyId = String(window.sessionStorage.getItem(STORAGE_COMPANY_ID_KEY) || '')
      if (initialEmail) params.set('email', initialEmail)
      if (initialCompanyId) params.set('company_id', initialCompanyId)
      const response = await fetch(`/api/demo/cases?${params.toString()}`)
      if (!response.ok) return
      const payload = await response.json()
      const sessionCompanyId = String(window.sessionStorage.getItem(STORAGE_COMPANY_ID_KEY) || '')
      const sessionCompanyName = String(window.sessionStorage.getItem(STORAGE_COMPANY_NAME_KEY) || '')
      const items = Array.isArray(payload?.items) ? payload.items : []
      const normalized = items
        .map((item, idx) => normalizeCaseItem(item, idx, caseStatusLabelMap))
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
        const payloadCompanyId = String(payload?.company?.company_id || sessionCompanyId || currentCompanyId || '')
        const payloadCompanyName = String(payload?.company?.company_name || sessionCompanyName || currentCompanyName || '')
        if (payloadCompanyId) {
          setCurrentCompanyId(payloadCompanyId)
          window.sessionStorage.setItem(STORAGE_COMPANY_ID_KEY, payloadCompanyId)
        }
        if (payloadCompanyName) {
          setCurrentCompanyName(payloadCompanyName)
          window.sessionStorage.setItem(STORAGE_COMPANY_NAME_KEY, payloadCompanyName)
        }
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
  }, [caseStatusLabelMap])

  useEffect(() => {
    const storedCompanyId = String(window.sessionStorage.getItem(STORAGE_COMPANY_ID_KEY) || '')
    const storedCompanyName = String(window.sessionStorage.getItem(STORAGE_COMPANY_NAME_KEY) || '')
    if (storedCompanyId) setCurrentCompanyId(storedCompanyId)
    if (storedCompanyName) setCurrentCompanyName(storedCompanyName)
  }, [])

  useEffect(() => {
    const onMouseDown = (event) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setIsUserMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [])

  useEffect(() => {
    const token = String(window.sessionStorage.getItem(STORAGE_TOKEN_KEY) || '')
    if (!token) return
    let cancelled = false

    const loadCompanyContext = async () => {
      try {
        const companiesResponse = await fetch('/api/onboard/companies', {
          headers: { Authorization: `Bearer ${token}` },
        })
        const companiesPayload = await companiesResponse.json().catch(() => ({}))
        if (cancelled || !companiesResponse.ok) return
        const items = Array.isArray(companiesPayload.items) ? companiesPayload.items : []
        setCompanyChoices(items)

        const resolvedCompanyId =
          String(window.sessionStorage.getItem(STORAGE_COMPANY_ID_KEY) || '') ||
          String(companiesPayload.default_company_id || '') ||
          String(items[0]?.company_id || '')

        const resolvedCompany =
          items.find((item) => String(item.company_id || '') === resolvedCompanyId) ||
          items[0] ||
          null

        if (resolvedCompany) {
          const nextCompanyId = String(resolvedCompany.company_id || '')
          const nextCompanyName = String(resolvedCompany.company_name || '')
          setCurrentCompanyId(nextCompanyId)
          setCurrentCompanyName(nextCompanyName)
          window.sessionStorage.setItem(STORAGE_COMPANY_ID_KEY, nextCompanyId)
          window.sessionStorage.setItem(STORAGE_COMPANY_NAME_KEY, nextCompanyName)
          setCompanyEditForm((prev) => ({ ...prev, ...resolvedCompany }))
        }
      } catch {
        // Keep existing context when onboarding API is unavailable.
      }
    }

    loadCompanyContext()
    return () => {
      cancelled = true
    }
  }, [currentEmail])

  const handleCompanyEditField = useCallback((field, value) => {
    setCompanyEditForm((prev) => ({ ...prev, [field]: value }))
  }, [])

  const openCompanyEditModal = useCallback(() => {
    setCompanyEditError('')
    setCompanyEditSuccess('')
    setIsCompanyEditOpen(true)
    setIsUserMenuOpen(false)
  }, [])

  const selectActiveCompany = useCallback(async (companyId) => {
    const normalizedCompanyId = String(companyId || '').trim()
    if (!normalizedCompanyId) return

    const token = String(window.sessionStorage.getItem(STORAGE_TOKEN_KEY) || '')
    if (!token) {
      setActionNotice(tr('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.', 'Session has expired. Please sign in again.'))
      return
    }

    try {
      const response = await fetch('/api/onboard/select-company', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ company_id: normalizedCompanyId }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || !payload?.selected) {
        throw new Error(tr('Không chọn được công ty', 'Could not switch company'))
      }

      const profile = payload?.profile && typeof payload.profile === 'object' ? payload.profile : {}
      const nextCompanyId = String(profile.company_id || normalizedCompanyId)
      const nextCompanyName = String(profile.company_name || nextCompanyId)
      setCurrentCompanyId(nextCompanyId)
      setCurrentCompanyName(nextCompanyName)
      window.sessionStorage.setItem(STORAGE_COMPANY_ID_KEY, nextCompanyId)
      window.sessionStorage.setItem(STORAGE_COMPANY_NAME_KEY, nextCompanyName)
      setCompanyEditForm((prev) => ({ ...prev, ...profile }))
      setIsUserMenuOpen(false)
      setActionNotice(`${tr('Đã chuyển sang công ty', 'Switched to company')}: ${nextCompanyName}`)
    } catch (error) {
      setActionNotice(error.message || tr('Không chọn được công ty', 'Could not switch company'))
    }
  }, [tr])

  const handleWorkspaceLogout = useCallback(() => {
    setIsUserMenuOpen(false)
    window.sessionStorage.setItem('solis.auth.hasCompanyProfile', 'false')
    window.sessionStorage.removeItem(STORAGE_COMPANY_ID_KEY)
    window.sessionStorage.removeItem(STORAGE_COMPANY_NAME_KEY)
    window.location.assign('/onboard')
  }, [])

  const saveCompanyEdit = useCallback(async () => {
    const token = String(window.sessionStorage.getItem(STORAGE_TOKEN_KEY) || '')
    if (!token) {
      setCompanyEditError(tr('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.', 'Session has expired. Please sign in again.'))
      return
    }

    setIsCompanySaving(true)
    setCompanyEditError('')
    setCompanyEditSuccess('')
    try {
      const payload = {
        company_id: String(companyEditForm.company_id || currentCompanyId || ''),
        tax_code: String(companyEditForm.tax_code || ''),
        company_name: String(companyEditForm.company_name || ''),
        address: String(companyEditForm.address || ''),
        legal_representative: String(companyEditForm.legal_representative || ''),
        established_date: String(companyEditForm.established_date || ''),
        accounting_software_start_date: String(companyEditForm.accounting_software_start_date || ''),
        fiscal_year_start: String(companyEditForm.fiscal_year_start || ''),
        tax_declaration_cycle: String(companyEditForm.tax_declaration_cycle || 'thang'),
        default_bank_account: String(companyEditForm.default_bank_account || ''),
        accountant_email: String(companyEditForm.accountant_email || currentEmail || ''),
      }

      const response = await fetch('/api/onboard/companies', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok || !result?.saved) {
        throw new Error(tr('Không thể cập nhật thông tin công ty.', 'Could not update company profile.'))
      }

      const nextName = String(result?.profile?.company_name || payload.company_name || '')
      const nextCompanyId = String(result?.profile?.company_id || payload.company_id || '')
      setCurrentCompanyName(nextName)
      setCurrentCompanyId(nextCompanyId)
      window.sessionStorage.setItem(STORAGE_COMPANY_NAME_KEY, nextName)
      window.sessionStorage.setItem(STORAGE_COMPANY_ID_KEY, nextCompanyId)
      setCompanyEditForm((prev) => ({ ...prev, ...result.profile }))
      setCompanyEditSuccess(tr('Đã cập nhật thông tin công ty.', 'Company profile updated.'))
    } catch (error) {
      setCompanyEditError(error.message || tr('Không thể cập nhật thông tin công ty.', 'Could not update company profile.'))
    } finally {
      setIsCompanySaving(false)
    }
  }, [companyEditForm, currentCompanyId, currentEmail, tr])

  const statusFilterLabel = statusOptions.find((item) => item.value === statusFilter)?.label || tr('Tất cả', 'All')

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
  const rawTimeline = Array.isArray(activeCase?.timeline) ? activeCase.timeline : []
  const timeline = rawTimeline.filter((event) => {
    const title = String(event?.title || '').trim().toLowerCase()
    const eventId = String(event?.id || '').trim().toLowerCase()
    const isLegacyParseEntry = title === 'thông tin parse hồ sơ' || title === 'thong tin parse ho so'
    const isExtractionEntry = title === 'thông tin trích xuất hồ sơ' || title === 'thong tin trich xuat ho so'
    const isParseTableId = eventId.includes('-parse-table-')
    return !(isLegacyParseEntry || isExtractionEntry || isParseTableId)
  })
  const evidence = Array.isArray(activeCase?.evidence) ? activeCase.evidence : []
  const reasoning = Array.isArray(activeCase?.reasoning) ? activeCase.reasoning : []
  const pendingPosting = activeCase?.pendingPosting && typeof activeCase.pendingPosting === 'object' ? activeCase.pendingPosting : null
  const pendingEvent = pendingPosting?.event && typeof pendingPosting.event === 'object' ? pendingPosting.event : null
  const pendingParseRowsFromServer = Array.isArray(pendingPosting?.parse_rows) ? pendingPosting.parse_rows : []
  const pendingInvoiceDate = String(
    pendingEvent?.issue_date || pendingEvent?.statement_date || pendingEvent?.event_date || '',
  ).trim()
  const pendingTotalAmount = Number(
    pendingEvent?.amount_total || pendingEvent?.total_amount || pendingEvent?.amount || 0,
  )
  let pendingUntaxedAmount = Number(
    pendingEvent?.amount_untaxed || pendingEvent?.untaxed_amount || 0,
  )
  let pendingVatAmount = Number(pendingEvent?.vat_amount || 0)
  if (pendingUntaxedAmount <= 0 && pendingTotalAmount > 0 && pendingVatAmount > 0 && pendingTotalAmount >= pendingVatAmount) {
    pendingUntaxedAmount = pendingTotalAmount - pendingVatAmount
  }
  if (pendingVatAmount <= 0 && pendingTotalAmount > 0 && pendingUntaxedAmount > 0 && pendingTotalAmount >= pendingUntaxedAmount) {
    pendingVatAmount = pendingTotalAmount - pendingUntaxedAmount
  }
  const pendingParseRows = pendingParseRowsFromServer.length
    ? normalizeParseSummaryRows(pendingParseRowsFromServer, {
        currentCompanyName,
        fallbackPartnerCandidates: [
          pendingEvent?.counterparty_name,
          pendingEvent?.seller_name,
          pendingEvent?.buyer_name,
          activeCase?.partner,
        ],
      })
    : pendingEvent
    ? normalizeParseSummaryRows([
        { label: 'Đối tác', value: String(pendingEvent.counterparty_name || pendingEvent.seller_name || '-') },
        { label: 'Nội dung', value: String(pendingEvent.description || pendingEvent.goods_service_type || '-') },
        { label: 'Số hóa đơn', value: String(pendingEvent.invoice_no || pendingEvent.reference_no || '-') },
        { label: 'Ngày hóa đơn', value: formatDateByRule(pendingInvoiceDate || '-') || '-' },
        { label: 'Số tiền trước thuế', value: pendingUntaxedAmount > 0 ? formatCurrency(pendingUntaxedAmount) : '-' },
        { label: 'Thuế VAT', value: pendingVatAmount > 0 ? formatCurrency(pendingVatAmount) : '-' },
        { label: 'Số tiền sau thuế', value: pendingTotalAmount > 0 ? formatCurrency(pendingTotalAmount) : '-' },
      ], {
        currentCompanyName,
        fallbackPartnerCandidates: [
          pendingEvent?.counterparty_name,
          pendingEvent?.seller_name,
          pendingEvent?.buyer_name,
          activeCase?.partner,
        ],
      })
    : []
  const shouldShowParseSummary = pendingParseRows.length > 0 && timelineVisibleCount >= timeline.length

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
  const previewFileUrl = useMemo(() => {
    if (!previewFileRef || !activeCaseId) return ''
    const params = new URLSearchParams()
    if (currentEmail) {
      params.set('email', currentEmail)
    }
    if (currentCompanyId) {
      params.set('company_id', currentCompanyId)
    }
    const query = params.toString()
    const basePath = `/api/demo/evidence/${encodeURIComponent(activeCaseId)}/${encodeURIComponent(previewFileRef)}`
    return query ? `${basePath}?${query}` : basePath
  }, [previewFileRef, activeCaseId, currentEmail, currentCompanyId])
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
        throw new Error(tr('Không tải được file để xem nhanh', 'Could not load file for quick preview'))
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
          setStructuredError(error.message || tr('Không thể hiển thị dữ liệu dạng bảng', 'Could not display structured table data'))
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
  }, [previewFileName, previewFileUrl, isStructuredPreview, isXmlPreview, isJsonPreview, isDocPreview, tr])

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
        throw new Error(tr('Không tải được file DOCX để xem nhanh', 'Could not load DOCX for quick preview'))
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
          setDocxError(error.message || tr('Không thể dựng tài liệu DOCX theo trang', 'Could not render DOCX page by page'))
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
  }, [previewFileName, previewFileUrl, isDocxPagePreview, tr])

  async function confirmDeleteActiveCase() {
    if (!activeCase) return
    try {
      const payload = await runUiAction('delete_case', '', activeCase.id)
      await reloadDemoCases('')
      setActiveSection('cases')
      setCaseActionNotice(payload?.message || tr('Đã xóa hồ sơ', 'Case deleted'))
    } catch (error) {
      setCaseActionNotice(error.message || tr('Không xóa được hồ sơ', 'Could not delete case'))
    } finally {
      setIsDeleteModalOpen(false)
    }
  }

  function openPreview(entry) {
    if (!entry) return
    const fileName = String(entry.name || '').trim()
    const fileRef = String(entry.previewRef || fileName).trim()
    if (!fileName || !fileRef) return
    setPreviewFileName(fileName)
    setPreviewFileRef(fileRef)
  }

  function closePreview() {
    setPreviewFileName('')
    setPreviewFileRef('')
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
      ? tr('Bảng điều khiển', 'Dashboard')
      : activeSection === 'reports'
        ? tr('Báo cáo', 'Reports')
        : activeSection === 'compliance'
          ? tr('Tuân thủ & Kê khai', 'Compliance & Filing')
        : activeSection === 'settings'
          ? tr('Cài đặt', 'Settings')
          : activeCase?.title || tr('Chưa chọn hồ sơ', 'No case selected')
  const isCompactSidebar = ['dashboard', 'reports', 'compliance'].includes(activeSection)

  const sectionContent = activeSection !== 'cases' && uiContent && typeof uiContent === 'object' ? uiContent[activeSection] || {} : {}
  const sideCompanion = sectionContent?.companion || {
    title: `${tr('Màn phụ', 'Side panel')} ${sectionLabel}`,
    subtitle: tr('Đang tải dữ liệu cấu hình từ hệ thống.', 'Loading configured panel data.'),
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
  const reportCompanyLabel = String(currentCompanyName || companyEditForm?.company_name || tr('Công ty hiện tại', 'Current company'))
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
        label: formatDateByRule(item.event_date || '') || String(idx + 1),
        value: net,
      }
    })
  }, [reportDetail])

  useEffect(() => {
    const nextYear = extractYearFromToken(compliancePeriod)
    if (nextYear !== openingBalanceYear) {
      setOpeningBalanceYear(nextYear)
    }
  }, [compliancePeriod, openingBalanceYear])

  useEffect(() => {
    if (activeSection !== 'compliance') return undefined

    let cancelled = false
    setOpeningBalanceLoading(true)

    const params = new URLSearchParams({ year: String(openingBalanceYear) })
    if (currentEmail) params.set('email', currentEmail)
    if (currentCompanyId) params.set('company_id', currentCompanyId)

    fetch(`/api/demo/opening-balances/annual?${params.toString()}`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(tr('Không tải được số dư đầu kỳ', 'Could not load opening balances'))
        }
        return response.json()
      })
      .then((payload) => {
        if (cancelled) return
        setOpeningBalanceLines(payload?.lines && typeof payload.lines === 'object' ? payload.lines : {})
        setOpeningBalanceSource(String(payload?.source || 'none'))
        setOpeningBalanceSourceYear(payload?.source_year ? Number(payload.source_year) : null)
      })
      .catch((error) => {
        if (cancelled) return
        setOpeningBalanceNotice(error.message || tr('Không tải được số dư đầu kỳ', 'Could not load opening balances'))
      })
      .finally(() => {
        if (!cancelled) {
          setOpeningBalanceLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [activeSection, openingBalanceYear, currentEmail, currentCompanyId, tr])

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
      if (currentCompanyId) {
        params.set('company_id', currentCompanyId)
      }
      params.set('report_period', reportPeriod)
      params.set('report_txn_filter', reportTxnFilter)
      const response = await fetch(`/api/demo/reports/detailed?${params.toString()}`)
      if (!response.ok) {
        throw new Error(tr('Không tải được báo cáo chi tiết', 'Could not load detailed report'))
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
          setReportError(error.message || tr('Không tải được báo cáo chi tiết', 'Could not load detailed report'))
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
  }, [activeSection, currentEmail, currentCompanyId, reportAsOfDate, reportPeriod, reportTxnFilter, tr])

  useEffect(() => {
    if (!['dashboard', 'compliance'].includes(activeSection)) return undefined

    let cancelled = false
    const loader = async () => {
      const params = new URLSearchParams({ period: compliancePeriod })
      if (currentEmail) params.set('email', currentEmail)
      if (currentCompanyId) params.set('company_id', currentCompanyId)
      if (complianceReportId) params.set('report_id', complianceReportId)
      const response = await fetch(`/api/demo/compliance?${params.toString()}`)
      if (!response.ok) {
        throw new Error(tr('Không tải được dữ liệu tuân thủ kê khai', 'Could not load compliance data'))
      }
      return response.json()
    }

    loader()
      .then((payload) => {
        if (cancelled) return
        setComplianceData(payload)
        const effectivePeriod = String(payload?.period || '').trim()
        if (effectivePeriod && effectivePeriod !== compliancePeriod) {
          setCompliancePeriod(effectivePeriod)
        }
        const reports = Array.isArray(payload?.reports) ? payload.reports : []
        if (reports.length && !reports.some((item) => String(item.report_id) === complianceReportId)) {
          setComplianceReportId(String(reports[0].report_id))
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setActionNotice(error.message || tr('Không tải được dữ liệu tuân thủ kê khai', 'Could not load compliance data'))
        }
      })

    return () => {
      cancelled = true
    }
  }, [activeSection, currentEmail, currentCompanyId, compliancePeriod, complianceReportId, tr])

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
        company_id: currentCompanyId || '',
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
      throw new Error(detail || tr('Thao tác không thành công', 'Action failed'))
    }
    return response.json()
  }

  async function reloadDemoCases(preferredCaseId = '') {
    const params = new URLSearchParams()
    if (currentEmail) params.set('email', currentEmail)
    if (currentCompanyId) params.set('company_id', currentCompanyId)
    const response = await fetch(`/api/demo/cases?${params.toString()}`)
    if (!response.ok) return
    const payload = await response.json()
    const items = Array.isArray(payload?.items) ? payload.items : []
    const normalized = items
      .map((item, idx) => normalizeCaseItem(item, idx, caseStatusLabelMap))
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
      setCaseActionNotice(payload?.message || tr('Đã tạo hồ sơ mới', 'New case created'))
    } catch (error) {
      setCaseActionNotice(error.message || tr('Không tạo được hồ sơ mới', 'Could not create new case'))
    }
  }

  async function handleSendCaseCommand() {
    if (isSendingCaseCommand) return
    const text = prompt.trim()
    if (!text && attachedFiles.length === 0) {
      setCaseActionNotice(tr('Vui lòng nhập nội dung hoặc đính kèm chứng từ trước khi gửi', 'Please enter a message or attach a document before sending'))
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
        throw new Error(tr('Không tạo được hồ sơ để nhận lệnh', 'Could not create a case to receive the command'))
      }

      const payload = await runUiAction('case_command', text, targetCaseId)
      await reloadDemoCases(targetCaseId)
      setPrompt('')
      setAttachedFiles([])
      setCaseActionNotice('')
    } catch (error) {
      setCaseActionNotice(error.message || tr('Không gửi được lệnh', 'Could not send the command'))
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
      setCaseActionNotice('')
    } catch (error) {
      setCaseActionNotice(error.message || tr('Không xử lý được xác nhận', 'Could not process confirmation'))
    } finally {
      setIsSendingCaseCommand(false)
    }
  }

  async function handleDashboardAnalyze() {
    const text = dashboardQuery.trim()
    if (!text) {
      setActionNotice(tr('Vui lòng nhập câu hỏi để phân tích', 'Please enter a question to analyze'))
      return
    }
    try {
      const payload = await runUiAction('dashboard_query', text)
      setActionNotice(payload?.message || tr('Đã chạy phân tích', 'Analysis completed'))
    } catch (error) {
      setActionNotice(error.message || tr('Không phân tích được dữ liệu', 'Could not analyze data'))
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
        company_id: currentCompanyId || '',
        period: compliancePeriod,
        report_id: String(complianceActiveReport.report_id),
      }),
    })
    if (!response.ok) {
      throw new Error(tr('Không xuất được file', 'Could not export file'))
    }
    const payload = await response.json()
    downloadBase64File(payload.file_name, payload.mime_type, payload.content_base64)
    setActionNotice(`${tr('Đã tải file', 'Downloaded file')} ${payload.file_name}`)
  }

  async function handleSubmitCompliance() {
    if (!complianceActiveReport) return
    const response = await fetch('/api/demo/compliance/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: currentEmail || 'demo@wssmeas.local',
        company_id: currentCompanyId || '',
        period: compliancePeriod,
        report_id: String(complianceActiveReport.report_id),
        submitted_by: currentEmail || 'demo@wssmeas.local',
      }),
    })
    if (!response.ok) {
      setActionNotice(tr('Nộp điện tử thất bại', 'Online submission failed'))
      return
    }
    setActionNotice(tr('Đã nộp báo cáo điện tử thành công', 'Online submission completed successfully'))
    const params = new URLSearchParams({ period: compliancePeriod })
    if (currentEmail) params.set('email', currentEmail)
    if (currentCompanyId) params.set('company_id', currentCompanyId)
    const reload = await fetch(`/api/demo/compliance?${params.toString()}`)
    if (reload.ok) {
      const payload = await reload.json()
      setComplianceData(payload)
    }
  }

  function updateOpeningLine(code, rawValue) {
    const normalizedCode = String(code || '').toLowerCase()
    const cleaned = String(rawValue || '').replace(/[^0-9-]/g, '')
    setOpeningBalanceLines((prev) => ({
      ...prev,
      [normalizedCode]: cleaned,
    }))
  }

  async function saveOpeningBalances() {
    setOpeningBalanceLoading(true)
    setOpeningBalanceNotice('')
    try {
      const response = await fetch('/api/demo/opening-balances/annual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: currentEmail || 'demo@wssmeas.local',
          company_id: currentCompanyId || '',
          year: Number(openingBalanceYear),
          lines: openingBalanceLines,
        }),
      })
      if (!response.ok) {
        throw new Error(tr('Không lưu được số dư đầu kỳ', 'Could not save opening balances'))
      }
      setOpeningBalanceSource('manual')
      setOpeningBalanceNotice(tr('Đã lưu số dư đầu kỳ theo năm', 'Saved annual opening balances'))
    } catch (error) {
      setOpeningBalanceNotice(error.message || tr('Không lưu được số dư đầu kỳ', 'Could not save opening balances'))
    } finally {
      setOpeningBalanceLoading(false)
    }
  }

  async function importOpeningBalancesFromXml(event) {
    const file = event?.target?.files?.[0]
    if (!file) return

    setOpeningBalanceLoading(true)
    setOpeningBalanceNotice('')
    try {
      const xmlText = await file.text()
      const response = await fetch('/api/demo/opening-balances/import-bctc-xml', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: currentEmail || 'demo@wssmeas.local',
          company_id: currentCompanyId || '',
          xml_text: xmlText,
        }),
      })
      if (!response.ok) {
        throw new Error(tr('Không import được XML BCTC', 'Could not import BCTC XML'))
      }
      const payload = await response.json()
      const targetYear = Number(payload?.target_year || openingBalanceYear)
      setOpeningBalanceYear(targetYear)
      setOpeningBalanceSource('carry_forward')
      setOpeningBalanceSourceYear(payload?.source_year ? Number(payload.source_year) : null)
      setOpeningBalanceLines(payload?.lines && typeof payload.lines === 'object' ? payload.lines : {})
      setOpeningBalanceNotice(
        tr('Đã import số cuối năm trước thành số đầu năm hiện tại', 'Imported previous-year closing balances as current-year opening balances'),
      )
    } catch (error) {
      setOpeningBalanceNotice(error.message || tr('Không import được XML BCTC', 'Could not import BCTC XML'))
    } finally {
      setOpeningBalanceLoading(false)
      if (event?.target) {
        event.target.value = ''
      }
    }
  }

  function handleVoucherTestFile(event) {
    const file = event?.target?.files?.[0]
    if (!file) return
    setVoucherTestFile(file)
    setVoucherTestNotice('')
    setVoucherTestSummary(null)
    setVoucherTestRows([])
    setVoucherTestPostResults([])
  }

  async function runVoucherSheetTest(autoPost = false) {
    if (!voucherTestFile) {
      setVoucherTestNotice(tr('Vui lòng chọn file bảng kê (.xlsx) trước khi test', 'Please choose an .xlsx voucher sheet before testing'))
      return
    }

    setVoucherTestLoading(true)
    setVoucherTestNotice('')
    try {
      const dataUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : '')
        reader.onerror = () => reject(new Error(tr('Không đọc được file Excel', 'Could not read Excel file')))
        reader.readAsDataURL(voucherTestFile)
      })

      const requestBody = {
        email: currentEmail || 'demo@wssmeas.local',
        company_id: currentCompanyId || '',
        file_name: voucherTestFile.name,
        content_base64: dataUrl,
        auto_post: Boolean(autoPost),
      }

      const postVoucherImport = async (url) => {
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(requestBody),
        })
        const payload = await response.json().catch(() => ({}))
        return { response, payload }
      }

      let { response, payload } = await postVoucherImport('/api/demo/voucher-test/import')
      if (response.status === 404) {
        const fallbackUrl = 'http://127.0.0.1:8000/api/demo/voucher-test/import'
        const fallbackResult = await postVoucherImport(fallbackUrl)
        response = fallbackResult.response
        payload = fallbackResult.payload
      }

      if (!response.ok) {
        throw new Error(String(payload?.detail || payload?.message || tr('Test bảng kê thất bại', 'Voucher test failed')))
      }

      setVoucherTestSummary({
        fileName: String(payload?.file_name || voucherTestFile.name || ''),
        convertedCount: Number(payload?.converted_count || 0),
        postedCount: Number(payload?.posted_count || 0),
        failedCount: Number(payload?.failed_count || 0),
        autoPost: Boolean(payload?.auto_post),
      })
      setVoucherTestRows(Array.isArray(payload?.preview_rows) ? payload.preview_rows : [])
      setVoucherTestPostResults(Array.isArray(payload?.post_results) ? payload.post_results : [])

      const issues = Array.isArray(payload?.issues) ? payload.issues.filter(Boolean) : []
      if (issues.length) {
        setVoucherTestNotice(issues.join('\n'))
      } else if (autoPost) {
        setVoucherTestNotice(
          tr(
            `Đã convert ${Number(payload?.converted_count || 0)} dòng và post ${Number(payload?.posted_count || 0)} dòng`,
            `Converted ${Number(payload?.converted_count || 0)} rows and posted ${Number(payload?.posted_count || 0)} rows`,
          ),
        )
      } else {
        setVoucherTestNotice(
          tr(
            `Đã convert ${Number(payload?.converted_count || 0)} dòng bảng kê`,
            `Converted ${Number(payload?.converted_count || 0)} voucher rows`,
          ),
        )
      }
    } catch (error) {
      setVoucherTestNotice(error.message || tr('Test bảng kê thất bại', 'Voucher test failed'))
    } finally {
      setVoucherTestLoading(false)
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
    setActionNotice(`${tr('Đã ghi nhận thao tác:', 'Action recorded:')} ${actionLabel}`)
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
    { key: 'payable', label: tr('Phải trả', 'Payables'), value: payableValue },
    { key: 'receivable', label: tr('Phải thu', 'Receivables'), value: receivableValue },
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

  useEffect(() => {
    if (!reportDrillResize) return undefined

    function onMouseMove(event) {
      const delta = event.clientX - reportDrillResize.startX
      const nextWidth = Math.max(120, Math.min(900, reportDrillResize.startWidth + delta))
      setReportDrillColumnWidths((prev) => ({
        ...prev,
        [reportDrillResize.column]: nextWidth,
      }))
    }

    function onMouseUp() {
      setReportDrillResize(null)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)

    return () => {
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [reportDrillResize])

  function startReportDrillResize(column, event) {
    const startWidth = Number(reportDrillColumnWidths[column] || 0)
    if (!startWidth) return
    event.preventDefault()
    setReportDrillResize({
      column,
      startX: event.clientX,
      startWidth,
    })
  }

  const gridStyle = {
    '--left-width': `${isCompactSidebar ? 86 : leftWidth}px`,
    '--right-width': `${rightWidth}px`,
  }

  return (
    <div className="app-shell">
      <header className="global-header">
        <div className="brand-block">
          <div className="logo-mark">SO</div>
          <div className="brand-name">{tr('Solis Tài chính AI', 'Solis Finance AI')}</div>
        </div>

        <div className="breadcrumb">
          <span>{tr('Hồ sơ', 'Cases')}</span>
          <ChevronRight size={14} />
          <strong>{sectionLabel}</strong>
        </div>

        <div className="global-actions" ref={notificationRef}>
          <button
            type="button"
            className="user-chip"
            aria-label={tr('Đổi ngôn ngữ', 'Switch language')}
            title={tr('Đổi ngôn ngữ', 'Switch language')}
            onClick={toggleUiLang}
          >
            <span>{uiLang === 'vi' ? 'VI' : 'EN'}</span>
          </button>
          <button
            type="button"
            className={isNotificationOpen ? 'icon-action notification-btn active' : 'icon-action notification-btn'}
            aria-label={tr('Thông báo', 'Notifications')}
            onClick={() => setIsNotificationOpen((prev) => !prev)}
          >
            <Bell size={17} />
            {unfinishedCases.length ? <span className="notification-badge">{unfinishedCases.length}</span> : null}
          </button>
          {isNotificationOpen ? (
            <div className="notification-popover">
              <h4>{tr('Thông báo công việc dở dang', 'Pending task notifications')}</h4>
              {unfinishedCases.length ? (
                <ul className="notification-list-scroll">
                  {unfinishedCases.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        className="notification-item-btn"
                        onClick={() => openCaseFromNotification(item.id)}
                      >
                        {tr('Hồ sơ', 'Case')} <strong>{item.code}</strong> {tr('đang', 'is')} {item.statusLabel.toLowerCase()}.
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>{tr('Hiện không còn hồ sơ dở dang.', 'No pending cases right now.')}</p>
              )}
            </div>
          ) : null}
          <div className="user-menu-wrap" ref={userMenuRef}>
            <button type="button" className="user-chip" onClick={() => setIsUserMenuOpen((prev) => !prev)}>
              <UserCircle2 size={18} />
              <span>{currentCompanyName || tr('Chưa chọn công ty', 'No company selected')}</span>
              <ChevronDown size={14} />
            </button>
            {isUserMenuOpen ? (
              <div className="user-menu-dropdown">
                <p className="user-menu-title">{currentCompanyName || tr('Công ty hiện tại', 'Current company')}</p>
                <p className="user-menu-subtitle">{currentEmail || tr('Đang tải tài khoản', 'Loading account')}</p>
                {companyChoices.length ? (
                  <>
                    <p className="user-menu-subtitle">{tr('Danh sách công ty', 'Company list')}</p>
                    {companyChoices.map((item) => {
                      const companyId = String(item?.company_id || '')
                      const companyName = String(item?.company_name || companyId || tr('Không rõ tên', 'Unnamed'))
                      const isActive = companyId && companyId === String(currentCompanyId || '')
                      return (
                        <button
                          key={companyId || companyName}
                          type="button"
                          className={isActive ? 'user-menu-btn active' : 'user-menu-btn'}
                          onClick={() => selectActiveCompany(companyId)}
                        >
                          {isActive ? `✓ ${companyName}` : companyName}
                        </button>
                      )
                    })}
                  </>
                ) : null}
                <button type="button" className="user-menu-btn" onClick={openCompanyEditModal}>
                  {tr('Sửa thông tin công ty', 'Edit company profile')}
                </button>
                <button
                  type="button"
                  className="user-menu-btn"
                  onClick={() => {
                    setActiveSection('settings')
                    setIsUserMenuOpen(false)
                  }}
                >
                  {tr('Cài đặt', 'Settings')}
                </button>
                <button type="button" className="user-menu-btn danger" onClick={handleWorkspaceLogout}>
                  {tr('Đăng xuất', 'Logout')}
                </button>
              </div>
            ) : null}
          </div>
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
                  <span>{tr('Thoát Advanced Mode', 'Exit Advanced Mode')}</span>
                </button>
              </div>
              <div className="advanced-head">
                <h2>{tr('Trình soạn bút toán chuyên sâu', 'Advanced journal composer')}</h2>
                <p>{tr('Thiết kế bút toán nhiều dòng, phân bổ kỳ và kiểm tra cân đối tức thì.', 'Design multi-line entries, period allocations, and instant balancing checks.')}</p>
              </div>
              <div className="advanced-block">
                <h3>{tr('Bút toán mẫu', 'Sample entries')}</h3>
                <p>{tr('Nợ', 'Debit')} 242: 70,000,000</p>
                <p>{tr('Nợ', 'Debit')} 1331: 7,000,000</p>
                <p>{tr('Có', 'Credit')} 331: 77,000,000</p>
              </div>
              <div className="advanced-block">
                <h3>{tr('Phân bổ tự động', 'Auto allocation')}</h3>
                <p>{tr('Phân bổ TK 242 trong 6 kỳ, bắt đầu từ 04/2026.', 'Allocate account 242 over 6 periods, starting from 04/2026.')}</p>
              </div>
            </section>

            <section className="advanced-panel advanced-center">
              <div className="advanced-head">
                <h2>{tr('Bảng điều phối nghiệp vụ nâng cao', 'Advanced workflow orchestrator')}</h2>
                <p>{tr('Toàn bộ luồng từ nhận chứng từ -&gt; xác thực -&gt; hậu kiểm bút toán.', 'End-to-end flow from receiving evidence -&gt; validation -&gt; posting quality checks.')}</p>
              </div>
              <div className="advanced-timeline">
                <article>
                  <h3>{tr('Bước 1: Nhận chứng từ', 'Step 1: Receive documents')}</h3>
                  <p>{tr('AI trích xuất dữ liệu hóa đơn, hợp đồng, điều khoản thanh toán.', 'AI extracts invoice, contract, and payment-term data.')}</p>
                </article>
                <article>
                  <h3>{tr('Bước 2: Tạo bút toán nhiều lớp', 'Step 2: Build layered entries')}</h3>
                  <p>{tr('Cho phép tách nghiệp vụ thành nhiều dòng theo trung tâm chi phí.', 'Split one business event into multiple lines by cost center.')}</p>
                </article>
                <article>
                  <h3>{tr('Bước 3: Kiểm tra ràng buộc', 'Step 3: Validate constraints')}</h3>
                  <p>{tr('Kiểm tra cân đối Nợ-Có, giới hạn tài khoản và quy tắc thuế.', 'Validate debit-credit balance, account limits, and tax rules.')}</p>
                </article>
                <article>
                  <h3>{tr('Bước 4: Duyệt và ghi sổ', 'Step 4: Approve and post')}</h3>
                  <p>{tr('Luồng duyệt 2 cấp trước khi ghi nhận vào sổ cái.', 'Use two-level approval before posting into the general ledger.')}</p>
                </article>
              </div>
            </section>

            <section className="advanced-panel advanced-right">
              <div className="advanced-head">
                <h2>{tr('Kiểm soát chuyên sâu', 'Advanced controls')}</h2>
                <p>{tr('Giám sát sai lệch và tuân thủ theo chuẩn kế toán.', 'Monitor deviations and accounting-rule compliance.')}</p>
              </div>
              <ul>
                <li>{tr('Cảnh báo lệch định khoản theo nhóm tài khoản nhạy cảm.', 'Alert abnormal postings in sensitive account groups.')}</li>
                <li>{tr('Đối chiếu VAT đầu vào/đầu ra theo thời gian thực.', 'Reconcile input/output VAT in real time.')}</li>
                <li>{tr('Nhật ký thay đổi bút toán trước và sau duyệt.', 'Track journal changes before and after approval.')}</li>
                <li>{tr('Kiểm tra chồng chéo chứng từ giữa các hồ sơ.', 'Detect overlapping documents across cases.')}</li>
              </ul>
            </section>
          </div>
        ) : (
          <>
            <aside className={['reports', 'dashboard', 'compliance'].includes(activeSection) ? 'left-sidebar reports-compact' : 'left-sidebar'}>
          {!['reports', 'dashboard', 'compliance'].includes(activeSection) ? <div className="sidebar-top">
            <button type="button" className="new-case-btn" onClick={handleCreateNewCase}>
              <Plus size={16} />
              <span>{tr('Hồ sơ mới', 'New case')}</span>
            </button>

            <div className="search-wrap">
              <Search size={15} />
              <input
                type="text"
                  placeholder={tr('Tìm theo hồ sơ, hóa đơn, đối tác', 'Search by case, invoice, partner')}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              <div className="search-filter-wrap" ref={statusFilterRef}>
                <button
                  type="button"
                  className={isStatusFilterOpen ? 'search-filter-icon-btn active' : 'search-filter-icon-btn'}
                  aria-label={`${tr('Lọc trạng thái', 'Filter status')}: ${statusFilterLabel}`}
                  title={`${tr('Lọc trạng thái', 'Filter status')}: ${statusFilterLabel}`}
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

          {!['reports', 'dashboard', 'compliance'].includes(activeSection) ? <div className="case-list" aria-label={tr('Danh sách hồ sơ cuộn vô hạn', 'Infinite scrolling case list')} onScroll={handleCaseListScroll}>
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
                    <time>{formatDateByRule(item.updatedAt) || item.updatedAt}</time>
                  </div>
                  <p>{item.code} - {item.partner}</p>
                  <div className="case-item-footer">
                    <div className="case-item-amount">{item.amount}</div>
                    <span className={`status-pill status-${item.status}`}>{item.statusLabel}</span>
                  </div>
                </button>
              ))
            ) : (
              <div className="empty-cases">{tr('Không có hồ sơ phù hợp bộ lọc.', 'No cases match the current filter.')}</div>
            )}
            {filteredCases.length > visibleCases.length ? (
              <div className="case-list-more-hint">{tr('Cuộn xuống để tải thêm hồ sơ', 'Scroll down to load more cases')} ({visibleCases.length}/{filteredCases.length})</div>
            ) : null}
          </div> : null}

          <nav className="sidebar-bottom">
            {isCompactSidebar ? (
              <div className="compact-module-rail" aria-label={tr('Điều hướng phân hệ nhanh', 'Quick module navigation')}>
                <button
                  type="button"
                  className={activeSection === 'cases' ? 'compact-module-btn active' : 'compact-module-btn'}
                  title={tr('Hồ sơ', 'Cases')}
                  aria-label={tr('Hồ sơ', 'Cases')}
                  onClick={() => handleModuleSelect('cases')}
                >
                  <MessageSquare size={17} />
                </button>
                <button
                  type="button"
                  className={activeSection === 'dashboard' ? 'compact-module-btn active' : 'compact-module-btn'}
                  title={tr('Bảng điều khiển', 'Dashboard')}
                  aria-label={tr('Bảng điều khiển', 'Dashboard')}
                  onClick={() => handleModuleSelect('dashboard')}
                >
                  <LayoutDashboard size={17} />
                </button>
                <button
                  type="button"
                  className={activeSection === 'reports' ? 'compact-module-btn active' : 'compact-module-btn'}
                  title={tr('Báo cáo', 'Reports')}
                  aria-label={tr('Báo cáo', 'Reports')}
                  onClick={() => handleModuleSelect('reports')}
                >
                  <FileText size={17} />
                </button>
                <button
                  type="button"
                  className={activeSection === 'compliance' ? 'compact-module-btn active' : 'compact-module-btn'}
                  title={tr('Tuân thủ & Kê khai', 'Compliance & Filing')}
                  aria-label={tr('Tuân thủ & Kê khai', 'Compliance & Filing')}
                  onClick={() => handleModuleSelect('compliance')}
                >
                  <FileCheck2 size={17} />
                </button>
                <button
                  type="button"
                  className={activeSection === 'settings' ? 'compact-module-btn active' : 'compact-module-btn'}
                  title={tr('Cài đặt', 'Settings')}
                  aria-label={tr('Cài đặt', 'Settings')}
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
                  <span>{tr('Phân hệ', 'Modules')}</span>
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
                        <span>{tr('Bảng điều khiển', 'Dashboard')}</span>
                      </button>
                      <button
                        type="button"
                        className={activeSection === 'reports' ? 'module-menu-btn active' : 'module-menu-btn'}
                        onClick={() => handleModuleSelect('reports')}
                      >
                        <FileText size={15} />
                        <span>{tr('Báo cáo', 'Reports')}</span>
                      </button>
                      <button
                        type="button"
                        className={activeSection === 'compliance' ? 'module-menu-btn active' : 'module-menu-btn'}
                        onClick={() => handleModuleSelect('compliance')}
                      >
                        <FileCheck2 size={15} />
                        <span>{tr('Tuân thủ & Kê khai', 'Compliance & Filing')}</span>
                      </button>
                      <button
                        type="button"
                        className={activeSection === 'settings' ? 'module-menu-btn active' : 'module-menu-btn'}
                        onClick={() => handleModuleSelect('settings')}
                      >
                        <Settings size={15} />
                        <span>{tr('Cài đặt', 'Settings')}</span>
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
          aria-label={tr('Thay đổi độ rộng thanh bên và dòng sự kiện', 'Resize sidebar and timeline')}
        />

        <main className="timeline-panel">
          {activeSection === 'cases' ? (
            <>
              <div className="timeline-head">
                <h2>{tr('Dòng sự kiện', 'Timeline')}</h2>
                <p>{tr('Luồng tường thuật từ phân tích AI đến các sự kiện kế toán có cấu trúc.', 'Narrative flow from AI analysis to structured accounting events.')}</p>
              </div>

              {isAdvancedMode ? (
                <div className="advanced-banner">
                  {tr('Advanced Mode đang bật: cho phép hạch toán chuyên sâu, tùy chỉnh bút toán và kiểm soát chi tiết.', 'Advanced Mode is on: enables deep posting workflows, configurable entries, and detailed controls.')}
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
                      {Array.isArray(event.table_rows) && event.table_rows.length ? (
                        <table className="chat-inline-table">
                          <thead>
                            <tr>
                              <th>{tr('Trường dữ liệu', 'Field')}</th>
                              <th>{tr('Giá trị', 'Value')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {event.table_rows.map((row) => (
                              <tr key={`${event.id}-${row.label}`}>
                                <td>{row.label}</td>
                                <td>{row.value}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>

              <div className="command-box">
                {shouldShowParseSummary ? (
                  <section className="parse-summary-box">
                    <div className="parse-summary-head">
                      <h4>{tr('Thông tin trích xuất hồ sơ', 'Extracted case information')}</h4>
                      <span>{tr('Vui lòng khách hàng xác nhận trước khi post', 'Please confirm before posting')}</span>
                    </div>
                    <table className="parse-summary-table">
                      <thead>
                        <tr>
                          <th>{tr('Trường dữ liệu', 'Field')}</th>
                          <th>{tr('Giá trị', 'Value')}</th>
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
                        {tr('Xác nhận và đồng ý post', 'Confirm and post')}
                      </button>
                      <button
                        type="button"
                        className="confirm-post-btn secondary"
                        onClick={() => handlePostingConfirmation(false)}
                        disabled={isSendingCaseCommand}
                      >
                        {tr('Chưa đồng ý post', 'Reject posting')}
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
                          aria-label={tr(`Bỏ file ${file.name}`, `Remove file ${file.name}`)}
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
                    aria-label={tr('Đính kèm file', 'Attach files')}
                    title={tr('Đính kèm file', 'Attach files')}
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
                        ? tr('Lệnh nâng cao: "Tách bút toán 30/70, ghi nhận vào 242 và phân bổ 6 kỳ"', 'Advanced command: "Split posting 30/70, book into 242 and amortize over 6 periods"')
                        : tr('Hỏi AI hoặc ra lệnh: "Hạch toán khoản này vào chi phí trả trước"', 'Ask AI or command: "Book this into prepaid expenses"')
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
                    {isSendingCaseCommand ? tr('Đang gửi...', 'Sending...') : tr('Gửi', 'Send')}
                  </button>
                </div>
                {caseActionNotice ? <p className="report-inline-note">{caseActionNotice}</p> : null}
              </div>
            </>
          ) : (
            <section className="detail-screen">
              <div className="detail-head">
                <h2>{sectionLabel}</h2>
                <p>{tr('Màn hình chi tiết cho phân hệ', 'Detailed view for')} {sectionLabel.toLowerCase()}.</p>
              </div>
              {actionNotice ? <p className="report-inline-note">{actionNotice}</p> : null}

              {activeSection === 'dashboard' ? (
                <div className="dashboard-decision-layout">
                  <article className="detail-row dashboard-ai-query">
                    <h3>{tr('Hỏi AI để ra quyết định', 'Ask AI for decisions')}</h3>
                    <div className="report-chat-input">
                      <input
                        type="text"
                        value={dashboardQuery}
                        placeholder={tr('Ví dụ: Tuần này nên ưu tiên thu hồi khoản nào?', 'Example: Which receivable should we prioritize this week?')}
                        onChange={(event) => setDashboardQuery(event.target.value)}
                      />
                      <button type="button" onClick={handleDashboardAnalyze}>{tr('Phân tích', 'Analyze')}</button>
                    </div>
                  </article>

                  <article className="detail-row dashboard-hero">
                    <div className="dashboard-hero-head">
                      <h3>{tr('Tình hình tài chính hôm nay', 'Financial snapshot today')}</h3>
                      <span className="report-live-badge">Control Center</span>
                    </div>
                    <div className="dashboard-hero-metrics">
                      <div><span>{tr('Tiền mặt', 'Cash')}</span><strong className="metric-up">{formatCurrency(cashValue)} ↑ +{cashTrendPct}%</strong></div>
                      <div><span>{tr('Công nợ phải trả', 'Accounts payable')}</span><strong className="metric-down">{formatCurrency(payableValue)} ↑ +{payableTrendPct}%</strong></div>
                      <div><span>{tr('Công nợ phải thu', 'Accounts receivable')}</span><strong className="metric-up">{formatCurrency(receivableValue)} ↓ {Math.abs(receivableTrendPct)}%</strong></div>
                    </div>
                    <div className="dashboard-hero-foot">
                      <p>{tr('Dự báo: Dòng tiền đủ vận hành khoảng', 'Forecast: cash runway about')} <strong>{runwayMonths.toFixed(1)} {tr('tháng', 'months')}</strong></p>
                      <p>{tr('Khuyến nghị: Chốt lịch thanh toán nhà cung cấp trước 48 giờ.', 'Recommendation: lock supplier payments at least 48 hours in advance.')}</p>
                    </div>
                  </article>

                  <article className="detail-row dashboard-kpi-row">
                    {[
                      { title: tr('Tiền mặt', 'Cash'), value: formatCurrency(cashValue), trend: `+${cashTrendPct}%`, tone: 'up' },
                      { title: tr('Phải trả', 'Payables'), value: formatCurrency(payableValue), trend: `+${payableTrendPct}%`, tone: 'down' },
                      { title: tr('Phải thu', 'Receivables'), value: formatCurrency(receivableValue), trend: `${receivableTrendPct}%`, tone: 'up' },
                      { title: 'Burn rate', value: `${formatCurrency(burnRateValue)} / ${tr('tháng', 'month')}`, trend: `${runwayMonths.toFixed(1)} ${tr('tháng runway', 'months runway')}`, tone: 'warn' },
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
                        <h4>{tr('Dòng tiền gần nhất', 'Recent cashflow')}</h4>
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
                        <h4>{tr('Doanh thu vs Chi phí', 'Revenue vs Cost')}</h4>
                        <div className="bar-duo">
                          <div className="bar-row"><span>{tr('Doanh thu', 'Revenue')}</span><div className="bar-track"><div className="bar-fill revenue" style={{ width: `${Math.min(100, 35 + (reportRevenue > 0 ? 65 : 0))}%` }} /></div></div>
                          <div className="bar-row"><span>{tr('Chi phí', 'Cost')}</span><div className="bar-track"><div className="bar-fill cost" style={{ width: `${Math.min(100, Math.max(10, reportRevenue > 0 ? (reportCost / reportRevenue) * 100 : 10))}%` }} /></div></div>
                        </div>
                      </div>
                      <div className="visual-item">
                        <h4>{tr('Công nợ theo nhóm', 'Debt by group')}</h4>
                        <div className="bar-duo">
                          {debtBalanceSeries.map((point) => (
                            <div className="bar-row" key={point.label}>
                              <span>{point.label}</span>
                              <div className="bar-track">
                                <div className={point.key === 'payable' ? 'bar-fill debt' : 'bar-fill receivable'} style={{ width: `${Math.max(12, Math.min(100, (point.value / Math.max(payableValue, receivableValue, 1)) * 100))}%` }} />
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </article>

                  <article className="detail-row dashboard-bottom-grid">
                    <section className="dashboard-alert-card">
                      <h3>{tr('Cảnh báo trọng yếu', 'Critical warnings')}</h3>
                      <ul>
                        {dashboardWarnings.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </section>
                    <section className="dashboard-action-card">
                      <h3>{tr('Hành động đề xuất', 'Suggested actions')}</h3>
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
                          {tr('Mở báo cáo công nợ', 'Open debt report')}
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
                          {tr('Mở báo cáo chi phí', 'Open cost report')}
                        </button>
                      </div>
                    </section>
                    {dashboardComplianceAlert ? (
                      <section className="dashboard-compliance-callout">
                        <h3>{tr('Nhắc nộp báo cáo', 'Submission reminder')}</h3>
                        <p>
                          {dashboardComplianceAlert.status === 'qua_han' ? tr('Quá hạn', 'Overdue') : tr('Sắp đến hạn', 'Due soon')}: {localizeRuntimeText(dashboardComplianceAlert.name)} - {tr('hạn', 'due')} {formatDateByRule(dashboardComplianceAlert.due_date || '-') || '-'}
                        </p>
                        <button
                          type="button"
                          className="action-btn"
                          onClick={() => {
                            setComplianceReportId(String(dashboardComplianceAlert.report_id))
                            setActiveSection('compliance')
                          }}
                        >
                          {tr('Nộp ngay', 'Submit now')}
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
                      {tr('Kỳ báo cáo', 'Reporting period')}
                      <select value={reportPeriod} onChange={(event) => setReportPeriod(event.target.value)}>
                        <option value="7_ngay">{tr('7 ngày', '7 days')}</option>
                        <option value="30_ngay">{tr('30 ngày', '30 days')}</option>
                        <option value="quy_nay">{tr('Quý này', 'This quarter')}</option>
                        <option value="nam_nay">{tr('Năm nay', 'This year')}</option>
                      </select>
                    </label>
                    <label>
                      {tr('Đơn vị', 'Entity')}
                      <select value={reportEntity} onChange={(event) => setReportEntity(event.target.value)} disabled>
                        <option value="cong_ty_hien_tai">{reportCompanyLabel}</option>
                      </select>
                    </label>
                    <label>
                      {tr('Lọc giao dịch', 'Transaction filter')}
                      <select value={reportTxnFilter} onChange={(event) => setReportTxnFilter(event.target.value)}>
                        <option value="tat_ca">{tr('Tất cả', 'All')}</option>
                        <option value="gia_tri_lon">{tr('Giá trị lớn', 'Large value')}</option>
                        <option value="rui_ro">{tr('Rủi ro cao', 'High risk')}</option>
                      </select>
                    </label>
                  </article>

                  <article className="detail-row">
                    <div className="report-tab-row">
                      {[
                        { key: 'hieu_qua_kinh_doanh', label: tr('Hiệu quả kinh doanh', 'Business performance') },
                        { key: 'can_doi_ke_toan', label: tr('Sức khỏe tài chính', 'Financial health') },
                        { key: 'dong_tien', label: tr('Dòng tiền', 'Cashflow') },
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
                      <span>{tr('Doanh thu', 'Revenue')}</span>
                      <strong>{formatCurrency(reportRevenue)}</strong>
                    </div>
                    <div>
                      <span>{tr('Lợi nhuận', 'Profit')}</span>
                      <strong className={reportProfit >= 0 ? 'metric-up' : 'metric-down'}>{formatCurrency(reportProfit)}</strong>
                    </div>
                    <div>
                      <span>{tr('Dòng tiền thuần', 'Net cashflow')}</span>
                      <strong className={reportCashNet >= 0 ? 'metric-up' : 'metric-down'}>{formatCurrency(reportCashNet)}</strong>
                    </div>
                  </article>

                  <article className="detail-row report-to-compliance">
                    <p>
                      {tr('Nguồn dữ liệu từ Reports đã sẵn sàng để đóng gói tờ khai. Ví dụ: lợi nhuận hiện tại', 'Reports data is ready for filing package. Example: current profit')} {formatCurrency(reportProfit)} {tr('sẽ dùng để tính TNDN tạm tính.', 'will be used to estimate CIT.')}
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
                      {tr('Mở Tuân thủ & Kê khai', 'Open Compliance & Filing')}
                    </button>
                  </article>

                  <article className="detail-row">
                    <p className="report-inline-note">
                      {tr('Đang hiển thị', 'Showing')} {Number(reportDetail?.gl?.total || 0)} {tr('giao dịch sau lọc cho kỳ', 'transactions after filtering for')} {reportPeriod.replace('_', ' ')} ({reportTxnFilter.replace('_', ' ')}).
                    </p>
                  </article>

                  <article className="detail-row report-detail-card">
                    <div className="report-detail-head">
                      <h3>{tr('Bảng phân tích chính', 'Main analysis table')}</h3>
                      <p>
                        {reportDetail?.tt133?.basis || 'Thông tư 133/2016/TT-BTC'} | {tr('Dữ liệu đến ngày', 'Data as of')} {formatDateByRule(reportDetail?.as_of_date || reportAsOfDate) || '-'}
                      </p>
                    </div>

                    {reportLoading ? <p className="report-inline-note">{tr('Đang tải dữ liệu báo cáo chi tiết...', 'Loading detailed report data...')}</p> : null}
                    {reportError ? <p className="report-inline-note report-error">{reportError}</p> : null}

                    {!reportLoading && !reportError && reportDetail ? (
                      <>
                        {reportTab === 'hieu_qua_kinh_doanh' ? (
                          <div className="report-table-wrap">
                            <table className="report-table report-table-compact">
                              <thead>
                                <tr>
                                  <th>{tr('Mã số', 'Code')}</th>
                                  <th>{tr('Chỉ tiêu', 'Item')}</th>
                                  <th>{tr('Số tiền', 'Amount')}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(reportDetail.tt133?.pl_rows || []).map((row) => (
                                  <tr key={row.code}>
                                    <td>{row.code}</td>
                                    <td>{localizeRuntimeText(row.item)}</td>
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
                                  <th>{tr('Mã số', 'Code')}</th>
                                  <th>{tr('Chỉ tiêu', 'Item')}</th>
                                  <th>{tr('Số tiền', 'Amount')}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(reportDetail.tt133?.bs_rows || []).map((row) => (
                                  <tr key={row.code}>
                                    <td>{row.code}</td>
                                    <td>{localizeRuntimeText(row.item)}</td>
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
                                  <th>{tr('Mã số', 'Code')}</th>
                                  <th>{tr('Chỉ tiêu', 'Item')}</th>
                                  <th>{tr('Số tiền', 'Amount')}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(reportDetail.tt133?.cf_rows || []).map((row) => (
                                  <tr key={row.code}>
                                    <td>{row.code}</td>
                                    <td>{localizeRuntimeText(row.item)}</td>
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
                        { key: 'giao_dich', label: tr('Giao dịch', 'Transactions') },
                        { key: 'cong_no', label: tr('Công nợ', 'Debt') },
                        { key: 'chi_phi', label: tr('Chi phí', 'Costs') },
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
                        <colgroup>
                          <col style={{ width: `${reportDrillColumnWidths.first}px` }} />
                          <col style={{ width: `${reportDrillColumnWidths.second}px` }} />
                          <col />
                        </colgroup>
                        <thead>
                          <tr>
                            <th className="report-resizable-th">
                              {reportDrillTab === 'giao_dich' ? tr('Ngày hồ sơ', 'Case date') : tr('Nhóm', 'Group')}
                              <button
                                type="button"
                                className="report-col-resize-grip"
                                aria-label={tr('Co giãn cột ngày hồ sơ', 'Resize case-date column')}
                                onMouseDown={(event) => startReportDrillResize('first', event)}
                              />
                            </th>
                            <th className="report-resizable-th">
                              {tr('Diễn giải', 'Narration')}
                              <button
                                type="button"
                                className="report-col-resize-grip"
                                aria-label={tr('Co giãn cột diễn giải', 'Resize narration column')}
                                onMouseDown={(event) => startReportDrillResize('second', event)}
                              />
                            </th>
                            <th>{tr('Giá trị', 'Value')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {reportDrillTab === 'giao_dich' ? (reportDetail?.gl?.items || []).slice(-8).map((item) => (
                            <tr key={item.entry_id}>
                              <td>{formatDateByRule(item.event_date || item.meta?.event_date || '-') || '-'}</td>
                              <td>{localizeRuntimeText(formatReportNarration(item.narration, item.entry_id))}</td>
                              <td>{formatCurrency(item.debit_total)}</td>
                            </tr>
                          )) : null}
                          {reportDrillTab === 'cong_no' ? (
                            <>
                              <tr><td>{tr('Công nợ', 'Debt')}</td><td>{tr('Phải trả', 'Payables')}</td><td>{formatCurrency(payableValue)}</td></tr>
                              <tr><td>{tr('Công nợ', 'Debt')}</td><td>{tr('Phải thu', 'Receivables')}</td><td>{formatCurrency(receivableValue)}</td></tr>
                            </>
                          ) : null}
                          {reportDrillTab === 'chi_phi' ? (
                            <>
                              <tr><td>{tr('Chi phí', 'Cost')}</td><td>{tr('Tổng chi phí kỳ', 'Total period cost')}</td><td>{formatCurrency(reportCost)}</td></tr>
                              <tr><td>{tr('Chi phí', 'Cost')}</td><td>{tr('Tỷ trọng chi phí / doanh thu', 'Cost to revenue ratio')}</td><td>{reportCostRatioPct.toFixed(1)}%</td></tr>
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
                      {tr('Kỳ báo cáo', 'Reporting period')}
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
                    <h3>{tr('Danh sách báo cáo phải nộp', 'Required reports')}</h3>
                    <div className="compliance-report-list">
                      {normalizedFilingReports.map((item) => {
                        const statusLabel = item.status === 'da_nop' ? tr('Đã nộp', 'Submitted') : item.status === 'qua_han' ? tr('Quá hạn', 'Overdue') : tr('Chưa nộp', 'Not submitted')
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
                            <span className="compliance-report-due">{item.status === 'da_nop' ? `✓ ${tr('Đã nộp', 'Submitted')}` : `${tr('Hạn', 'Due')}: ${formatDateByRule(item.due_date || '-') || '-'}`}</span>
                          </button>
                        )
                      })}
                    </div>
                  </article>

                  <article className="detail-row compliance-detail-row">
                    <h3>{tr('Chi tiết báo cáo', 'Report details')}</h3>
                    <div className="report-tab-row">
                      {[
                        { key: 'preview', label: 'Preview' },
                        { key: 'xml', label: 'XML' },
                        { key: 'opening', label: tr('Số dư đầu kỳ', 'Opening balances') },
                        { key: 'voucher_test', label: tr('Test bảng kê', 'Voucher test') },
                        { key: 'history', label: tr('Lịch sử nộp', 'Submission history') },
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
                        <p><strong>{tr('Biểu mẫu', 'Form')}:</strong> {complianceActiveReport?.name || tr('Báo cáo thuế', 'Tax report')}</p>
                        <p><strong>{tr('Căn cứ pháp lý', 'Legal basis')}:</strong> {complianceActiveReport?.legal_basis || complianceData?.vat_declaration?.legal_basis || '-'}</p>
                        <p><strong>{tr('Chu kỳ kê khai', 'Declaration cycle')}:</strong> {complianceData?.declaration_cycle_label || '-'}</p>
                        <p><strong>{tr('Số liệu nguồn từ Reports', 'Source data from Reports')}:</strong> {tr('Doanh thu', 'Revenue')} {formatCurrency(reportRevenue)} | {tr('Lợi nhuận', 'Profit')} {formatCurrency(reportProfit)}</p>
                        <p><strong>{tr('Số tạm tính', 'Estimated amount')}:</strong> {formatCurrency(complianceActiveReport?.amount || 0)}</p>
                      </div>
                    ) : null}

                    {complianceDetailTab === 'xml' ? (
                      <div className="compliance-preview-box">
                        <pre>{complianceData?.xml_preview || ''}</pre>
                      </div>
                    ) : null}

                    {complianceDetailTab === 'opening' ? (
                      <div className="compliance-preview-box opening-balance-box">
                        <div className="opening-balance-toolbar">
                          <label>
                            {tr('Năm đầu kỳ', 'Opening year')}
                            <input
                              type="number"
                              min="1900"
                              max="9999"
                              value={openingBalanceYear}
                              onChange={(event) => setOpeningBalanceYear(Number(event.target.value || new Date().getFullYear()))}
                            />
                          </label>
                          <div className="opening-balance-toolbar-actions">
                            <input
                              ref={openingImportInputRef}
                              type="file"
                              accept=".xml,text/xml,application/xml"
                              className="attachment-input-hidden"
                              onChange={importOpeningBalancesFromXml}
                            />
                            <button type="button" className="action-btn secondary" onClick={() => openingImportInputRef.current?.click()}>
                              {tr('Import XML BCTC năm trước', 'Import previous-year BCTC XML')}
                            </button>
                            <button type="button" className="action-btn" onClick={saveOpeningBalances} disabled={openingBalanceLoading}>
                              {openingBalanceLoading ? tr('Đang lưu...', 'Saving...') : tr('Lưu số dư đầu kỳ', 'Save opening balances')}
                            </button>
                          </div>
                        </div>

                        <p>
                          <strong>{tr('Nguồn dữ liệu', 'Data source')}:</strong>{' '}
                          {openingBalanceSource === 'manual'
                            ? tr('Nhập tay', 'Manual')
                            : openingBalanceSource === 'carry_forward'
                              ? tr('Kế thừa từ số cuối năm trước', 'Carried from previous-year closing balances')
                              : tr('Chưa có', 'Not set')}
                          {openingBalanceSourceYear ? ` (${tr('năm nguồn', 'source year')}: ${openingBalanceSourceYear})` : ''}
                        </p>
                        <p>{tr('Quy tắc: Số cuối kỳ năm N sẽ được dùng làm số đầu kỳ năm N+1.', 'Rule: year N closing balances are used as year N+1 opening balances.')}</p>

                        <div className="opening-balance-grid">
                          {openingBalanceFields.map((field) => (
                            <label key={field.code}>
                              <span>{uiLang === 'en' ? field.labelEn : field.labelVi} ({field.code.toUpperCase()})</span>
                              <input
                                type="text"
                                inputMode="numeric"
                                value={String(openingBalanceLines?.[field.code] ?? '')}
                                onChange={(event) => updateOpeningLine(field.code, event.target.value)}
                              />
                            </label>
                          ))}
                        </div>

                        {openingBalanceNotice ? <p className="report-inline-note">{openingBalanceNotice}</p> : null}
                      </div>
                    ) : null}

                    {complianceDetailTab === 'voucher_test' ? (
                      <div className="compliance-preview-box opening-balance-box">
                        <div className="opening-balance-toolbar">
                          <label>
                            {tr('File bảng kê chứng từ (.xlsx)', 'Voucher sheet file (.xlsx)')}
                            <input
                              ref={voucherTestInputRef}
                              type="file"
                              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                              onChange={handleVoucherTestFile}
                            />
                          </label>
                          <div className="opening-balance-toolbar-actions">
                            <button
                              type="button"
                              className="action-btn secondary"
                              onClick={() => runVoucherSheetTest(false)}
                              disabled={voucherTestLoading}
                            >
                              {voucherTestLoading ? tr('Đang xử lý...', 'Processing...') : tr('Test convert', 'Test convert')}
                            </button>
                            <button
                              type="button"
                              className="action-btn"
                              onClick={() => runVoucherSheetTest(true)}
                              disabled={voucherTestLoading}
                            >
                              {voucherTestLoading ? tr('Đang post...', 'Posting...') : tr('Test convert + post', 'Test convert + post')}
                            </button>
                          </div>
                        </div>

                        <p>
                          <strong>{tr('Lưu ý', 'Note')}:</strong>{' '}
                          {tr('Module test bảng kê không kiểm tra MST hóa đơn như luồng XML, dùng để kiểm thử map dòng chứng từ sang economic events.', 'Voucher test module does not enforce invoice tax-code check like XML flow; it is for testing row-to-economic-event mapping.')}
                        </p>
                        <p>
                          <strong>{tr('File đã chọn', 'Selected file')}:</strong> {voucherTestFile?.name || '-'}
                        </p>

                        {voucherTestSummary ? (
                          <p>
                            <strong>{tr('Kết quả', 'Result')}:</strong>{' '}
                            {tr('Convert', 'Converted')} {Number(voucherTestSummary.convertedCount || 0)} | {tr('Post thành công', 'Posted')} {Number(voucherTestSummary.postedCount || 0)} | {tr('Lỗi', 'Failed')} {Number(voucherTestSummary.failedCount || 0)}
                          </p>
                        ) : null}

                        {voucherTestRows.length ? (
                          <div className="report-table-wrap">
                            <table className="report-table report-table-compact">
                              <thead>
                                <tr>
                                  <th>{tr('Ngày', 'Date')}</th>
                                  <th>{tr('Số CT', 'Ref')}</th>
                                  <th>{tr('Đối tác', 'Counterparty')}</th>
                                  <th>{tr('Diễn giải', 'Description')}</th>
                                  <th>{tr('Loại event', 'Event type')}</th>
                                  <th>{tr('Số tiền', 'Amount')}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {voucherTestRows.slice(0, 50).map((row, idx) => (
                                  <tr key={`${idx}-${row.reference_no || row.description || 'row'}`}>
                                    <td>{row.event_date || '-'}</td>
                                    <td>{row.reference_no || '-'}</td>
                                    <td>{row.counterparty_name || '-'}</td>
                                    <td>{row.description || '-'}</td>
                                    <td>{row.event_type || '-'}</td>
                                    <td>{formatCurrency(Number(row.amount || 0))}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : null}

                        {voucherTestPostResults.length ? (
                          <div className="report-table-wrap">
                            <table className="report-table report-table-compact">
                              <thead>
                                <tr>
                                  <th>#</th>
                                  <th>{tr('Loại event', 'Event type')}</th>
                                  <th>{tr('Kết quả post', 'Post result')}</th>
                                  <th>{tr('Lý do', 'Reason')}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {voucherTestPostResults.map((row, idx) => (
                                  <tr key={`${idx}-${row.line_no || idx}`}>
                                    <td>{row.line_no || idx + 1}</td>
                                    <td>{row.event_type || '-'}</td>
                                    <td>{row.accepted ? tr('Thành công', 'Accepted') : tr('Thất bại', 'Rejected')}</td>
                                    <td>{row.reason || '-'}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : null}

                        {voucherTestNotice ? <p className="report-inline-note">{voucherTestNotice}</p> : null}
                      </div>
                    ) : null}

                    {complianceDetailTab === 'history' ? (
                      <div className="report-table-wrap">
                        <table className="report-table report-table-compact">
                          <thead>
                            <tr>
                              <th>{tr('Mã', 'Code')}</th>
                              <th>{tr('Báo cáo', 'Report')}</th>
                              <th>{tr('Người nộp', 'Submitted by')}</th>
                              <th>{tr('Thời gian', 'Time')}</th>
                              <th>{tr('File', 'File')}</th>
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
                      <button type="button" className="action-btn" onClick={() => downloadComplianceFile('xml')}>{tr('Xuất XML', 'Export XML')}</button>
                      <button type="button" className="action-btn" onClick={() => downloadComplianceFile('pdf')}>{tr('Tải PDF', 'Download PDF')}</button>
                      <button type="button" className="action-btn" onClick={handleSubmitCompliance}>{tr('Nộp điện tử', 'Submit online')}</button>
                    </div>
                  </article>

                  <article className="detail-row compliance-check-row">
                    <h3>{tr('Auto-check lỗi trước khi nộp', 'Auto-check before submit')}</h3>
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
                        <h3>{modeToggleConfig.title || tr('Chế độ kế toán nâng cao', 'Advanced accounting mode')}</h3>
                        <p>
                          {modeToggleConfig.text ||
                            tr('Cho phép hạch toán chuyên sâu với bút toán nhiều lớp, phân bổ tự động và kiểm soát ràng buộc nâng cao.', 'Enable deep posting with multi-layer journals, auto-allocation, and advanced constraints.')}
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
                            ? modeToggleConfig.cta_off || tr('Tắt Advanced Mode', 'Turn off Advanced Mode')
                            : modeToggleConfig.cta_on || tr('Bật Advanced Mode', 'Turn on Advanced Mode')}
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
          aria-label={tr('Thay đổi độ rộng dòng sự kiện và bảng thông minh', 'Resize timeline and smart panel')}
        />

        <aside className={activeSection === 'cases' ? 'right-panel right-panel-cases' : 'right-panel'}>
          {activeSection === 'cases' ? (
            <>
              <section className="intel-block">
                <h2>{tr('Chứng từ', 'Documents')}</h2>
                <div className="evidence-list scrollable-pane">
                  {evidence.map((name) => (
                    <a
                      href="#"
                      key={name.previewRef || name.name}
                      className="evidence-item"
                      onClick={(event) => {
                        event.preventDefault()
                        openPreview(name)
                      }}
                    >
                      <FileText size={15} />
                      <span>{name.name}</span>
                    </a>
                  ))}
                </div>
              </section>

              <section className="intel-block">
                <h2>{tr('Lý giải của AI', 'AI reasoning')}</h2>
                <ul className="reasoning-list scrollable-pane">
                  {reasoning.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                  {isAdvancedMode ? <li>{tr('Đang hiển thị thêm lớp kiểm soát chuyên sâu cho kế toán viên.', 'Showing additional advanced control layers for accountants.')}</li> : null}
                </ul>
              </section>

              <button
                type="button"
                className="delete-case-btn"
                onClick={() => setIsDeleteModalOpen(true)}
                disabled={!activeCase}
              >
                {tr('Xóa hồ sơ', 'Delete case')}
              </button>
            </>
          ) : (
            <>
              <section className="intel-block">
                <h2>{localizeRuntimeText(sideCompanion.title)}</h2>
                <p>{localizeRuntimeText(sideCompanion.subtitle)}</p>
                <ul>
                  {sideCompanion.highlights.map((item) => (
                    <li key={item}>{localizeRuntimeText(item)}</li>
                  ))}
                </ul>
              </section>

              {activeSection === 'dashboard' ? (
                <section className="intel-block">
                  <h2>{tr('Ưu tiên hôm nay', 'Today priorities')}</h2>
                  <ol className="priority-list">
                    {dashboardPriorities.map((item) => (
                      <li key={item}>{localizeRuntimeText(item)}</li>
                    ))}
                  </ol>
                </section>
              ) : activeSection === 'reports' ? (
                <section className="intel-block">
                  <h2>{tr('Mẹo phân tích', 'Analysis tips')}</h2>
                  <ul>
                    {(Array.isArray(serverPanels?.reports_tips) ? serverPanels.reports_tips : []).map((tip) => (
                      <li key={tip}>{localizeRuntimeText(tip)}</li>
                    ))}
                  </ul>
                </section>
              ) : activeSection === 'compliance' ? (
                <section className="intel-block">
                  <h2>{tr('Checklist nộp báo cáo', 'Submission checklist')}</h2>
                  <ul>
                    {(Array.isArray(serverPanels?.compliance_checklist) ? serverPanels.compliance_checklist : []).map((item) => (
                      <li key={item}>{localizeRuntimeText(item)}</li>
                    ))}
                  </ul>
                </section>
              ) : (
                <section className="intel-block">
                  <h2>{tr('Thao tác nhanh', 'Quick actions')}</h2>
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
                        <span>{localizeRuntimeText(item)}</span>
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
            <h3 id="delete-modal-title">{tr('Xác nhận xóa hồ sơ', 'Confirm case deletion')}</h3>
            <p>
              {tr('Bạn sắp xóa hồ sơ', 'You are about to delete case')} <strong>{activeCase.title}</strong>.
            </p>
            <p className="modal-warning">{tr('Hành động này không thể khôi phục.', 'This action cannot be undone.')}</p>
            <div className="modal-actions">
              <button type="button" className="modal-btn secondary" onClick={() => setIsDeleteModalOpen(false)}>
                {tr('Hủy', 'Cancel')}
              </button>
              <button type="button" className="modal-btn danger" onClick={confirmDeleteActiveCase}>
                {tr('Xóa hồ sơ', 'Delete case')}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {isCompanyEditOpen ? (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="company-edit-title">
          <div className="modal-card company-edit-modal">
            <h3 id="company-edit-title">{tr('Cập nhật thông tin công ty', 'Update company profile')}</h3>
            <div className="company-edit-form-grid">
              <label>
                {tr('Mã số thuế', 'Tax code')}
                <input value={companyEditForm.tax_code || ''} readOnly className="readonly-input" />
              </label>
              <label>
                {tr('Tên công ty', 'Company name')}
                <input
                  value={companyEditForm.company_name || ''}
                  onChange={(event) => handleCompanyEditField('company_name', event.target.value)}
                />
              </label>
              <label>
                {tr('Địa chỉ', 'Address')}
                <input value={companyEditForm.address || ''} onChange={(event) => handleCompanyEditField('address', event.target.value)} />
              </label>
              <label>
                {tr('Người đại diện pháp luật', 'Legal representative')}
                <input
                  value={companyEditForm.legal_representative || ''}
                  onChange={(event) => handleCompanyEditField('legal_representative', event.target.value)}
                />
              </label>
              <label>
                {tr('Ngày thành lập', 'Established date')}
                <input
                  type="date"
                  value={companyEditForm.established_date || ''}
                  onChange={(event) => handleCompanyEditField('established_date', event.target.value)}
                />
              </label>
              <label>
                {tr('Ngày bắt đầu phần mềm kế toán', 'Accounting software start date')}
                <input
                  type="date"
                  value={companyEditForm.accounting_software_start_date || ''}
                  onChange={(event) => handleCompanyEditField('accounting_software_start_date', event.target.value)}
                />
              </label>
              <label>
                {tr('Ngày bắt đầu năm tài chính', 'Fiscal year start date')}
                <input
                  type="date"
                  value={companyEditForm.fiscal_year_start || ''}
                  onChange={(event) => handleCompanyEditField('fiscal_year_start', event.target.value)}
                />
              </label>
              <label>
                {tr('Chu kỳ kê khai', 'Declaration cycle')}
                <select
                  value={companyEditForm.tax_declaration_cycle || 'thang'}
                  onChange={(event) => handleCompanyEditField('tax_declaration_cycle', event.target.value)}
                >
                  <option value="thang">{tr('Tháng', 'Month')}</option>
                  <option value="quy">{tr('Quý', 'Quarter')}</option>
                </select>
              </label>
              <label>
                {tr('Tài khoản ngân hàng mặc định', 'Default bank account')}
                <input
                  value={companyEditForm.default_bank_account || ''}
                  onChange={(event) => handleCompanyEditField('default_bank_account', event.target.value)}
                />
              </label>
              <label>
                {tr('Email kế toán', 'Accounting email')}
                <input
                  type="email"
                  value={companyEditForm.accountant_email || ''}
                  onChange={(event) => handleCompanyEditField('accountant_email', event.target.value)}
                />
              </label>
            </div>

            {companyEditError ? <p className="modal-warning">{companyEditError}</p> : null}
            {companyEditSuccess ? <p className="modal-success">{companyEditSuccess}</p> : null}

            <div className="modal-actions">
              <button type="button" className="modal-btn secondary" onClick={() => setIsCompanyEditOpen(false)}>
                {tr('Đóng', 'Close')}
              </button>
              <button type="button" className="modal-btn" onClick={saveCompanyEdit} disabled={isCompanySaving}>
                {isCompanySaving ? tr('Đang lưu...', 'Saving...') : tr('Lưu thay đổi', 'Save changes')}
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
            <h3 id="preview-modal-title">{tr('Xem nhanh chứng từ', 'Quick document preview')}</h3>
            <p className="preview-file-name">{previewFileName}</p>
            <div className="preview-surface">
              {isPdfPreview ? (
                <object data={previewFileUrl} type="application/pdf" className="preview-object">
                  <div className="preview-file-meta">
                    <FileText size={22} />
                    <div>
                      <strong>{previewFileName}</strong>
                      <p>{tr('Trình duyệt không hỗ trợ PDF inline. Hãy mở ở tab mới.', 'Browser does not support inline PDF. Please open in a new tab.')}</p>
                    </div>
                  </div>
                </object>
              ) : null}

              {isImagePreview ? <img src={previewFileUrl} alt={previewFileName} className="preview-image" /> : null}

              {officeViewerUrl ? (
                <iframe
                  title={tr('Xem tài liệu Microsoft Office', 'View Microsoft Office document')}
                  className="preview-office-frame"
                  src={officeViewerUrl}
                />
              ) : null}

              {isDocxPagePreview ? (
                <div className="docx-preview-wrap">
                  {docxLoading ? <p>{tr('Đang dựng tài liệu DOCX theo từng trang...', 'Rendering DOCX page by page...')}</p> : null}
                  {docxError ? <p>{docxError}</p> : null}
                  <div className="docx-preview-host" ref={docxPreviewRef} />
                </div>
              ) : null}

              {isStructuredPreview ? (
                <div className="structured-preview">
                  {isDocPreview && !officeViewerUrl ? (
                    <p>
                      {tr('File DOC đang được xem ở chế độ tương thích. Để hiển thị giống Microsoft theo từng trang, hãy dùng DOCX hoặc mở trên môi trường HTTPS công khai để dùng trình xem Office.', 'DOC is being viewed in compatibility mode. For Microsoft-like page rendering, use DOCX or open on a public HTTPS environment to use Office viewer.')}
                    </p>
                  ) : null}
                  {structuredLoading ? <p>{tr('Đang dựng bảng dữ liệu chuẩn...', 'Building structured data table...')}</p> : null}
                  {structuredError ? <p>{structuredError}</p> : null}
                  {!structuredLoading && !structuredError
                    ? structuredSections.map((section) => (
                        <section key={section.title} className="structured-section">
                          <h4>{section.title}</h4>
                          <table className="structured-table">
                            <thead>
                              <tr>
                                <th>{tr('Chỉ tiêu', 'Item')}</th>
                                <th>{tr('Giá trị', 'Value')}</th>
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
                    <p>{tr('Định dạng này hiện xem nhanh ở mức thông tin cơ bản.', 'This format is currently previewed at basic information level.')}</p>
                  </div>
                </div>
              ) : null}
            </div>
            <div className="modal-actions">
              <a href={previewFileUrl} className="modal-btn secondary" target="_blank" rel="noreferrer">
                {tr('Mở tab mới', 'Open in new tab')}
              </a>
              <a href={previewFileUrl} className="modal-btn secondary" download={previewFileName}>
                {tr('Tải về', 'Download')}
              </a>
              <button type="button" className="modal-btn secondary" onClick={closePreview}>
                {tr('Đóng', 'Close')}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default App
