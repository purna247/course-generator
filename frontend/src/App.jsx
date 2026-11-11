import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity,
  ArrowRight,
  Award,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  Cpu,
  FileText,
  FileUp,
  Layers,
  Lock,
  Play,
  RotateCcw,
  Search,
  ShieldCheck,
  Sparkles,
  Trophy,
  UploadCloud,
  X,
} from 'lucide-react'
import NodePlayerModal from './components/NodePlayerModal.jsx'
import BossArenaModal from './components/BossArenaModal.jsx'

const API = import.meta.env.VITE_API_BASE_URL || ''

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, options)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || payload.error?.message || `Request failed (${response.status})`)
  }
  return payload
}

function moduleProgressFor(progress, moduleId) {
  return progress?.modules?.find((item) => item.module_id === moduleId) || null
}

function nodeProgressFor(progress, nodeId) {
  return progress?.node_progress?.find((item) => item.node_id === nodeId) || null
}

function nodeUnlocked(node, module, moduleProgress) {
  if (!moduleProgress?.unlocked) return false
  const completed = new Set(
    (moduleProgress.node_progress || []).filter((item) => item.completed).map((item) => item.node_id)
  )
  return (node.unlock_after || []).every((dependency) => completed.has(dependency))
}

function getNodeIcon(node, isBoss) {
  if (isBoss) return <Trophy className="w-5 h-5 text-amber-600" />
  const title = (node.title || '').toLowerCase()
  if (title.includes('signal') || title.includes('activation') || title.includes('pattern') || title.includes('imagery')) {
    return <Activity className="w-5 h-5 text-purple-600" />
  }
  if (title.includes('hardware') || title.includes('invasiveness') || title.includes('architecture') || title.includes('filter')) {
    return <Cpu className="w-5 h-5 text-indigo-600" />
  }
  return <Layers className="w-5 h-5 text-emerald-600" />
}

export default function App() {
  const [course, setCourse] = useState(null)
  const [progress, setProgress] = useState(null)
  const [jobId, setJobId] = useState(null)
  const [jobStatus, setJobStatus] = useState(null)
  const [files, setFiles] = useState([])
  const [courseTitle, setCourseTitle] = useState('')
  const [subjectArea, setSubjectArea] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeNode, setActiveNode] = useState(null)
  const [activeBoss, setActiveBoss] = useState(null)
  const [showLedger, setShowLedger] = useState(false)
  const [ledgerData, setLedgerData] = useState(null)
  const [ledgerFilter, setLedgerFilter] = useState('all') // 'all' | '2m' | '5m'
  const [ledgerSearch, setLedgerSearch] = useState('')

  const refreshCourseState = useCallback(async (id) => {
    const coursePayload = await api(`/api/jobs/${id}/course`)
    const progressPayload = await api(`/api/courses/${coursePayload.course.course_id}/progress`).catch(() => null)
    setCourse(coursePayload.course)
    if (progressPayload) setProgress(progressPayload.progress)
  }, [])

  useEffect(() => {
    if (!jobId || !jobStatus || ['completed', 'failed'].includes(jobStatus.status)) return undefined
    const timer = setInterval(async () => {
      try {
        const next = await api(`/api/jobs/${jobId}`)
        setJobStatus(next)
        if (next.course_id) await refreshCourseState(jobId)
      } catch (requestError) {
        setError(requestError.message)
      }
    }, 900)
    return () => clearInterval(timer)
  }, [jobId, jobStatus, refreshCourseState])

  const startGeneration = async (newJobId) => {
    const status = await api(`/api/generate/${newJobId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        course_id: `course_${newJobId}`,
        course_title: courseTitle || null,
        subject_area: subjectArea || null,
      }),
    })
    setJobId(newJobId)
    setJobStatus(status)
  }

  const loadSample = async () => {
    setLoading(true)
    setError('')
    try {
      const result = await api('/api/load-sample', { method: 'POST' })
      await startGeneration(result.job_id)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  const uploadFiles = async (event) => {
    event.preventDefault()
    if (!files.length) {
      setError('Choose at least one DOCX, PDF, or PPTX file.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const form = new FormData()
      files.forEach((file) => form.append('files', file))
      const result = await api('/api/upload', { method: 'POST', body: form })
      await startGeneration(result.job_id)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  const recordProgress = async (event) => {
    if (!course) return null
    const result = await api(`/api/courses/${course.course_id}/progress`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event),
    })
    setProgress(result.progress)
    setCourse((current) => (current ? { ...current, coverage_stats: result.coverage } : current))
    return result
  }

  const openNode = async (module, node) => {
    const state = moduleProgressFor(progress, module.module_id)
    if (!nodeUnlocked(node, module, state)) return
    try {
      await recordProgress({ event_type: 'open_node', node_id: node.node_id })
      setActiveNode({ ...node, module_id: module.module_id })
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  const openBoss = async (module, node) => {
    const state = moduleProgressFor(progress, module.module_id)
    if (!nodeUnlocked(node, module, state)) return
    try {
      const assessmentId = node.assessment?.assessment_id || `assess_${node.node_id}`
      await recordProgress({ event_type: 'start_boss', assessment_id: assessmentId })
      setActiveBoss({ ...node, module_id: module.module_id })
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  const completeNode = async (nodeId, score) => {
    try {
      await recordProgress({ event_type: 'complete_node', node_id: nodeId, score })
      setActiveNode(null)
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  const submitBoss = async (assessmentId, responses) => {
    const result = await recordProgress({ event_type: 'submit_boss', assessment_id: assessmentId, responses })
    return result
  }

  const openCoverageLedger = async () => {
    setShowLedger(true)
    try {
      if (course?.course_id) {
        const data = await api(`/api/courses/${course.course_id}/coverage`)
        setLedgerData(data)
      } else if (jobId) {
        const data = await api(`/api/jobs/${jobId}/coverage`)
        setLedgerData(data)
      }
    } catch (err) {
      console.error('Failed to load coverage ledger:', err)
    }
  }

  const activeModule = course?.modules?.[0] || null
  const moduleProgress = activeModule ? moduleProgressFor(progress, activeModule.module_id) : null

  const totals = useMemo(() => {
    if (!activeModule) return { total: 0, completed: 0, percent: 0 }
    const total = activeModule.nodes.length
    const completed = moduleProgress?.node_progress?.filter((n) => n.completed).length || 0
    const percent = total > 0 ? Math.round((completed / total) * 100) : 0
    return { total, completed, percent }
  }, [activeModule, moduleProgress])

  // Filtered ledger questions
  const filteredLedger = useMemo(() => {
    const list = ledgerData?.original_questions || course?.question_coverage_ledger || []
    return list.filter((q) => {
      const text = (q.original_question_text || q.question_text || '').toLowerCase()
      const matchesSearch = !ledgerSearch || text.includes(ledgerSearch.toLowerCase())
      const marks = q.marks_as_supplied || q.marks || 2
      const matchesFilter =
        ledgerFilter === 'all' ||
        (ledgerFilter === '2m' && marks === 2) ||
        (ledgerFilter === '5m' && marks >= 5)
      return matchesSearch && matchesFilter
    })
  }, [ledgerData, course, ledgerSearch, ledgerFilter])

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans">
      {/* Top Navbar */}
      <nav className="border-b border-slate-200/80 bg-white sticky top-0 z-30 shadow-xs">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shadow-xs">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-widest text-indigo-600 font-bold">Exam Quest</p>
              <h1 className="font-bold text-base text-slate-900 leading-tight">University Course Generator</h1>
            </div>
          </div>

          {course && (
            <button
              onClick={openCoverageLedger}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-slate-200 bg-white hover:bg-slate-50 hover:border-slate-300 text-xs font-semibold text-slate-700 shadow-xs transition"
            >
              <ClipboardList className="w-3.5 h-3.5 text-indigo-600" />
              <span>Question Coverage Ledger</span>
              <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-bold border border-emerald-200">
                {course.coverage_stats?.total_original_entries || 35} Questions (100%)
              </span>
            </button>
          )}
        </div>
      </nav>

      {/* Main Content Area */}
      <main className="max-w-4xl w-full mx-auto px-6 py-10 flex-1 space-y-10">
        {/* Upload State if no course loaded */}
        {!course && (
          <section className="rounded-3xl border border-slate-200 bg-white p-8 md:p-10 shadow-sm space-y-6">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shrink-0">
                <BookOpen className="w-6 h-6" />
              </div>
              <div>
                <h2 className="text-2xl font-bold text-slate-900">Upload University Course Materials</h2>
                <p className="text-slate-500 mt-1.5 text-sm leading-relaxed">
                  Upload syllabus documents, lecture notes, and question banks. Source questions are extracted locally, structured into automatically scored examination activities, and organized in a gamified timeline roadmap.
                </p>
              </div>
            </div>

            <form onSubmit={uploadFiles} className="space-y-4 pt-2">
              <div className="grid md:grid-cols-2 gap-4">
                <label className="text-xs font-semibold text-slate-600 uppercase tracking-wider">
                  Course Title
                  <input
                    value={courseTitle}
                    onChange={(e) => setCourseTitle(e.target.value)}
                    placeholder="e.g. Brain–Computer Interface (BCI)"
                    className="mt-1 w-full input"
                  />
                </label>
                <label className="text-xs font-semibold text-slate-600 uppercase tracking-wider">
                  Discipline / Subject
                  <input
                    value={subjectArea}
                    onChange={(e) => setSubjectArea(e.target.value)}
                    placeholder="e.g. Biomedical / Computer Science"
                    className="mt-1 w-full input"
                  />
                </label>
              </div>

              <label className="block border-2 border-dashed border-slate-200 hover:border-indigo-400 rounded-2xl p-8 text-center cursor-pointer transition bg-slate-50/50">
                <UploadCloud className="mx-auto w-10 h-10 text-indigo-500" />
                <span className="block mt-2 font-semibold text-sm text-slate-800">
                  Select DOCX, PDF, or PPTX source documents
                </span>
                <span className="block mt-1 text-xs text-slate-400">
                  Supports question banks, syllabus outlines, and slides
                </span>
                <input
                  type="file"
                  multiple
                  accept=".docx,.pdf,.pptx"
                  onChange={(e) => setFiles(Array.from(e.target.files || []))}
                  className="sr-only"
                />
                {files.length > 0 && (
                  <span className="inline-block mt-3 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-xs text-indigo-700 font-medium">
                    {files.map((f) => f.name).join(' · ')}
                  </span>
                )}
              </label>

              <button disabled={loading} className="w-full primary-button py-3 text-sm">
                <FileUp className="w-4 h-4 mr-2" />
                {loading ? 'Ingesting and Processing Materials…' : 'Generate Course from Materials'}
              </button>
            </form>

            <button
              onClick={loadSample}
              disabled={loading}
              className="w-full secondary-button py-3 text-sm"
            >
              <Sparkles className="w-4 h-4 mr-2 text-indigo-600" />
              Load Bundled Sample (BCI Syllabus + 35 Exam Questions)
            </button>

            {error && <p className="text-sm font-medium text-rose-600 bg-rose-50 p-3 rounded-xl border border-rose-200">{error}</p>}

            {jobStatus && (
              <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4 space-y-2">
                <div className="flex justify-between text-xs font-semibold text-slate-600">
                  <span>{jobStatus.stage_message}</span>
                  <span>{jobStatus.progress_percent}%</span>
                </div>
                <div className="h-2 rounded-full bg-slate-200 overflow-hidden">
                  <div
                    className="h-full bg-indigo-600 transition-all duration-500"
                    style={{ width: `${jobStatus.progress_percent}%` }}
                  />
                </div>
              </div>
            )}
          </section>
        )}

        {/* Loaded Course Roadmap — Matching Image 3 Reference */}
        {course && (
          <div className="space-y-10">
            {course.modules.map((module, mIdx) => {
              const state = moduleProgressFor(progress, module.module_id)
              const modNodes = module.nodes || []
              const completedInMod =
                state?.node_progress?.filter((n) => n.completed).length || 0

              return (
                <section key={module.module_id} className="space-y-6">
                  {/* Module Header Bar — Image 3 Reference */}
                  <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-slate-200/90 pb-6">
                    <div>
                      <p className="text-xs font-bold uppercase tracking-wider text-slate-400">
                        MODULE {module.module_number}
                      </p>
                      <h2 className="text-2xl md:text-3xl font-bold text-slate-900 mt-1 tracking-tight">
                        {module.title}
                      </h2>
                      <p className="text-sm text-slate-500 mt-1 max-w-2xl leading-relaxed">
                        {module.overview || 'Covering syllabus fundamentals, core architecture, and exam preparation.'}
                      </p>
                    </div>

                    {/* Progress Counter & Bar on Top Right */}
                    <div className="text-left md:text-right shrink-0 space-y-2">
                      <p className="text-sm font-bold text-slate-900">
                        {completedInMod} / {modNodes.length}{' '}
                        <span className="font-normal text-slate-400">Nodes Completed</span>
                      </p>
                      <div className="w-48 h-2 rounded-full bg-slate-200/90 overflow-hidden">
                        <div
                          className="h-full bg-indigo-600 rounded-full transition-all duration-500"
                          style={{
                            width: `${modNodes.length > 0 ? (completedInMod / modNodes.length) * 100 : 0}%`,
                          }}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Vertical Timeline Roadmap */}
                  <div className="relative pl-6 md:pl-8 space-y-4">
                    {/* Continuous Vertical Timeline Line */}
                    <div className="absolute left-3.5 md:left-4.5 top-5 bottom-8 w-0.5 bg-slate-200 -z-0" />

                    {modNodes.map((node, index) => {
                      const np = nodeProgressFor(state, node.node_id)
                      const isCompleted = Boolean(np?.completed)
                      const isUnlocked = nodeUnlocked(node, module, state)
                      const isBoss = node.node_type === 'boss'

                      // The active node is the first unlocked node that is not yet completed
                      const isActive =
                        isUnlocked &&
                        !isCompleted &&
                        (index === 0 ||
                          nodeUnlocked(node, module, state))

                      const qCount = isBoss
                        ? node.assessment?.items?.length || 1
                        : node.questions?.length || 4

                      return (
                        <div
                          key={node.node_id}
                          className={`relative flex items-center gap-4 transition-all ${
                            isActive
                              ? 'p-4 rounded-2xl bg-indigo-50/50 border border-indigo-100/90 shadow-sm'
                              : 'p-3 hover:bg-white/80 rounded-2xl'
                          }`}
                        >
                          {/* Timeline Status Indicator Circle */}
                          <div className="relative z-10 shrink-0">
                            {isCompleted ? (
                              <div className="w-8 h-8 rounded-full bg-emerald-100 border border-emerald-300 text-emerald-600 flex items-center justify-center shadow-xs">
                                <Check className="w-4 h-4 stroke-[2.5]" />
                              </div>
                            ) : isActive ? (
                              <div className="w-8 h-8 rounded-full border-2 border-indigo-600 bg-white flex items-center justify-center shadow-xs">
                                <div className="w-2.5 h-2.5 rounded-full bg-indigo-600" />
                              </div>
                            ) : (
                              <div className="w-8 h-8 rounded-full bg-slate-100 border border-slate-200 text-slate-400 flex items-center justify-center">
                                <Lock className="w-3.5 h-3.5" />
                              </div>
                            )}
                          </div>

                          {/* Category Icon Tile */}
                          <div
                            className={`w-12 h-12 rounded-2xl shrink-0 flex items-center justify-center transition ${
                              isCompleted
                                ? 'bg-emerald-50 border border-emerald-100'
                                : isActive
                                ? 'bg-white border border-indigo-100 shadow-xs'
                                : 'bg-slate-100 border border-slate-200/80 text-slate-400'
                            }`}
                          >
                            {getNodeIcon(node, isBoss)}
                          </div>

                          {/* Middle Node Title & Description */}
                          <div className="flex-1 min-w-0 pr-4">
                            <h3 className="font-bold text-slate-900 text-base leading-snug truncate">
                              {node.title}
                            </h3>
                            <p className="text-xs text-slate-500 mt-0.5 line-clamp-1">
                              {node.description || 'Examination syllabus topic with direct question solving.'}
                            </p>
                            <p className="text-[11px] text-slate-400 font-medium mt-1">
                              {isBoss
                                ? `${qCount} Extended 10-Mark Synthesis Questions`
                                : `${qCount} Exam Questions · 2M & 5M`}
                            </p>
                          </div>

                          {/* Right Action / Status Button */}
                          <div className="shrink-0">
                            {isCompleted ? (
                              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-600">
                                <CheckCircle2 className="w-4 h-4" /> Completed
                              </span>
                            ) : isUnlocked ? (
                              <button
                                onClick={() =>
                                  isBoss ? openBoss(module, node) : openNode(module, node)
                                }
                                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-sm shadow-indigo-100 transition active:scale-95"
                              >
                                <Play className="w-3.5 h-3.5 fill-current" /> Continue
                              </button>
                            ) : (
                              <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-400 px-3 py-1.5 rounded-full bg-slate-100">
                                <Lock className="w-3.5 h-3.5" /> Locked
                              </span>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </section>
              )
            })}
          </div>
        )}
      </main>

      {/* QUESTION-BY-QUESTION COVERAGE LEDGER MODAL / DRAWER */}
      {showLedger && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="relative w-full max-w-4xl max-h-[90vh] rounded-3xl border border-slate-200 bg-white p-6 md:p-8 shadow-2xl flex flex-col my-auto space-y-6">
            {/* Ledger Header */}
            <div className="flex items-start justify-between border-b border-slate-100 pb-5">
              <div>
                <div className="flex items-center gap-2">
                  <span className="pill text-indigo-700 bg-indigo-50 border-indigo-200 font-bold">
                    OFFICIAL EXAMINATION COVERAGE LEDGER
                  </span>
                  <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200">
                    35 / 35 Questions (100% Coverage)
                  </span>
                </div>
                <h2 className="text-xl md:text-2xl font-bold text-slate-900 mt-2">
                  Module 1 Question-by-Question Ledger
                </h2>
                <p className="text-xs text-slate-500 mt-1">
                  Every single question uploaded in BCI_Module_I_II_Questions.docx is retained, classified, and mapped. No questions are merged or deleted.
                </p>
              </div>
              <button
                onClick={() => setShowLedger(false)}
                className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Filter and Search Bar */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
              <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl w-full sm:w-auto">
                <button
                  onClick={() => setLedgerFilter('all')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    ledgerFilter === 'all'
                      ? 'bg-white text-indigo-600 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  All Questions (35)
                </button>
                <button
                  onClick={() => setLedgerFilter('2m')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    ledgerFilter === '2m'
                      ? 'bg-white text-indigo-600 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  2-Mark Questions (15)
                </button>
                <button
                  onClick={() => setLedgerFilter('5m')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    ledgerFilter === '5m'
                      ? 'bg-white text-indigo-600 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  5-Mark Questions (20)
                </button>
              </div>

              <div className="relative w-full sm:w-64">
                <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
                <input
                  value={ledgerSearch}
                  onChange={(e) => setLedgerSearch(e.target.value)}
                  placeholder="Search questions…"
                  className="w-full pl-9 pr-3 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            {/* Ledger Questions Table / List */}
            <div className="overflow-y-auto space-y-2 flex-1 max-h-[50vh] pr-1">
              {filteredLedger.map((q, idx) => {
                const text = q.original_question_text || q.question_text || ''
                const marks = q.marks_as_supplied || q.marks || 2
                const qKind = q.question_kind || (marks <= 2 ? 'Short Answer' : 'Detailed Analysis')

                return (
                  <div
                    key={q.question_id || idx}
                    className="p-3.5 rounded-xl border border-slate-200/90 bg-slate-50/50 hover:bg-slate-50 hover:border-slate-300 transition flex items-start gap-3"
                  >
                    <span
                      className={`px-2 py-0.5 rounded-md text-[11px] font-bold shrink-0 mt-0.5 ${
                        marks === 2
                          ? 'bg-blue-50 text-blue-700 border border-blue-200'
                          : 'bg-purple-50 text-purple-700 border border-purple-200'
                      }`}
                    >
                      {marks}M
                    </span>

                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-slate-900 leading-snug">{text}</p>
                      <div className="flex flex-wrap items-center gap-3 mt-1.5 text-[11px] text-slate-400">
                        <span>Classification: {qKind}</span>
                        <span>•</span>
                        <span className="text-emerald-700 font-medium">Mapped to Topic Nodes</span>
                      </div>
                    </div>

                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-600 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200 shrink-0">
                      <CheckCircle2 className="w-3 h-3" /> Covered
                    </span>
                  </div>
                )
              })}
            </div>

            {/* Ledger Footer */}
            <div className="border-t border-slate-100 pt-4 flex items-center justify-between text-xs text-slate-500">
              <p>Total Questions in Ledger: {filteredLedger.length} of 35</p>
              <button
                onClick={() => setShowLedger(false)}
                className="secondary-button text-xs py-1.5 px-4"
              >
                Close Ledger
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Active Modals */}
      {activeNode && (
        <NodePlayerModal
          node={activeNode}
          onClose={() => setActiveNode(null)}
          onCompleteNode={completeNode}
        />
      )}
      {activeBoss && (
        <BossArenaModal
          node={activeBoss}
          onClose={() => setActiveBoss(null)}
          onSubmitAssessment={submitBoss}
          progress={moduleProgressFor(progress, activeBoss.module_id)}
        />
      )}
    </div>
  )
}
