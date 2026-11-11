import { useMemo, useState } from 'react'
import { CheckCircle2, Lock, LockKeyhole, Send, Sparkles, Trophy, X } from 'lucide-react'

export default function BossArenaModal({ node, onClose, onSubmitAssessment, progress }) {
  const assessment = node.assessment || {
    assessment_id: `assess_${node.node_id}`,
    passing_score: 0.6,
  }

  // Ensure assessment items always exist from assessment.items or answer_blueprint
  const items = useMemo(() => {
    if (node.assessment?.items?.length) {
      return node.assessment.items
    }
    return [
      {
        assessment_item_id: `boss_item_${node.node_id}`,
        item_type: 'long_answer',
        prompt: node.answer_blueprint?.question_text || node.title,
        marks: node.answer_blueprint?.total_marks || 10,
        source_refs: node.source_refs || [],
      },
    ]
  }, [node])

  const [responses, setResponses] = useState(progress?.boss_progress?.responses || {})
  const [result, setResult] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const allAnswered =
    items.length > 0 &&
    items.every((item) => (responses[item.assessment_item_id] || '').trim().length > 0)

  const previous = progress?.boss_progress
  const blueprintUnlocked = Boolean(result?.blueprint_unlocked || previous?.blueprint_unlocked)

  const submit = async () => {
    if (!allAnswered || submitting) return
    setSubmitting(true)
    try {
      const assessmentId = assessment.assessment_id || `assess_${node.node_id}`
      const res = await onSubmitAssessment(assessmentId, responses)
      setResult(res)
    } catch (err) {
      console.error('Boss assessment submission error:', err)
    } finally {
      setSubmitting(false)
    }
  }

  const answeredCount = useMemo(
    () => items.filter((item) => (responses[item.assessment_item_id] || '').trim().length > 0).length,
    [items, responses]
  )

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
      <div className="w-full max-w-4xl max-h-[92vh] overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl flex flex-col my-auto">
        {/* Header */}
        <header className="p-6 border-b border-slate-100 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="pill text-amber-700 bg-amber-50 border-amber-200 font-bold flex items-center gap-1.5">
                <Trophy className="w-3.5 h-3.5 text-amber-600" />
                BOSS ARENA ASSESSMENT
              </span>
              <span className="text-xs font-semibold text-slate-500">
                {answeredCount}/{items.length} Required Items Answered
              </span>
            </div>
            <h2 className="text-xl md:text-2xl font-bold text-slate-900 mt-2">{node.title}</h2>
            <p className="text-xs text-slate-500 mt-1">
              Passing threshold: {Math.round((assessment?.passing_score || 0.6) * 100)}% · 10-Mark University Blueprint Gated
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        {/* Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          <div className="rounded-2xl border border-amber-200 bg-amber-50/50 p-4 text-xs md:text-sm text-amber-900 flex items-start gap-3">
            <Sparkles className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <p>
              This Boss Arena prepares you for extended 10-mark examination synthesis. Solve the structured assessment items below to unlock the authentic, mark-aligned examination answer blueprint.
            </p>
          </div>

          {items.map((item, index) => (
            <section
              key={item.assessment_item_id}
              className="rounded-2xl border border-slate-200 bg-slate-50/50 p-5 space-y-3"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">
                  Challenge Item {index + 1} {item.marks ? `· ${item.marks} Marks` : ''}
                </span>
                <span className="text-xs text-slate-400 uppercase tracking-wider">{item.item_type}</span>
              </div>

              <h3 className="font-semibold text-slate-900 text-base leading-relaxed">{item.prompt}</h3>

              {item.item_type === 'mcq' && item.activity?.options ? (
                <div className="space-y-2">
                  {item.activity.options.map((option) => (
                    <button
                      key={option.option_id}
                      onClick={() =>
                        setResponses((current) => ({
                          ...current,
                          [item.assessment_item_id]: option.option_id,
                        }))
                      }
                      className={`activity-option ${
                        responses[item.assessment_item_id] === option.option_id ? 'activity-selected' : ''
                      }`}
                    >
                      {option.text}
                    </button>
                  ))}
                </div>
              ) : (
                <textarea
                  value={responses[item.assessment_item_id] || ''}
                  onChange={(event) =>
                    setResponses((current) => ({
                      ...current,
                      [item.assessment_item_id]: event.target.value,
                    }))
                  }
                  rows={item.item_type === 'long_answer' ? 6 : 4}
                  className="w-full textarea text-sm"
                  placeholder="Outline your technical solution, architecture blocks, and key criteria grounded in course materials…"
                />
              )}

              {item.source_refs?.length > 0 && (
                <p className="text-xs text-slate-400">
                  Grounding:{' '}
                  {item.source_refs
                    .map((ref) => `${ref.document_name}${ref.page_number ? ` · p.${ref.page_number}` : ''}`)
                    .join(' | ')}
                </p>
              )}
            </section>
          ))}

          {result && (
            <section
              className={`rounded-2xl border p-5 ${
                result.blueprint_unlocked
                  ? 'border-emerald-300 bg-emerald-50 text-emerald-900'
                  : 'border-rose-300 bg-rose-50 text-rose-900'
              }`}
            >
              <div className="flex items-center gap-2 font-bold">
                {result.blueprint_unlocked ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                ) : (
                  <LockKeyhole className="w-5 h-5 text-rose-600" />
                )}
                {result.blueprint_unlocked ? 'Boss Assessment Passed!' : 'Assessment Not Passed'}
              </div>
              <p className="text-sm mt-1">
                Score:{' '}
                {Math.round(
                  (result.progress?.modules?.find((module) => module.module_id === node.module_id)
                    ?.boss_progress?.score || 0.8) * 100
                )}
                %.{' '}
                {result.blueprint_unlocked
                  ? 'Your authentic 10-mark examination answer blueprint is now unlocked below.'
                  : 'Review the lecture notes and refine your solution before resubmitting.'}
              </p>
            </section>
          )}

          {/* Unlocked Blueprint Section */}
          {blueprintUnlocked && node.answer_blueprint && (
            <section className="rounded-2xl border border-amber-300 bg-amber-50/70 p-6 space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-amber-100 border border-amber-300 flex items-center justify-center text-amber-700">
                  <Trophy className="w-5 h-5" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wider text-amber-800 font-bold">Examination Answer Blueprint</p>
                  <h3 className="font-bold text-lg text-slate-900">{node.answer_blueprint.title}</h3>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-white border border-amber-200">
                <p className="text-sm font-semibold text-slate-900">{node.answer_blueprint.question_text}</p>
                {node.answer_blueprint.introduction_guidance && (
                  <p className="text-xs text-slate-600 mt-2 leading-relaxed">{node.answer_blueprint.introduction_guidance}</p>
                )}
              </div>

              {node.answer_blueprint.sections?.map((section, sIdx) => (
                <div key={section.heading || sIdx} className="rounded-xl border border-amber-200 bg-white p-4 space-y-2">
                  <div className="flex justify-between items-center gap-3 border-b border-slate-100 pb-2">
                    <h4 className="font-bold text-sm text-slate-900">{section.heading}</h4>
                    {section.suggested_marks && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 font-bold">
                        {section.suggested_marks} marks
                      </span>
                    )}
                  </div>
                  <ul className="list-disc pl-5 text-xs text-slate-700 space-y-1">
                    {section.key_points.map((point, pIdx) => (
                      <li key={pIdx}>{point}</li>
                    ))}
                  </ul>
                </div>
              ))}

              {node.answer_blueprint.marking_note && (
                <p className="text-xs text-amber-800 italic pt-2 border-t border-amber-200">
                  Marking Scheme Guidance: {node.answer_blueprint.marking_note}
                </p>
              )}
            </section>
          )}
        </div>

        {/* Footer */}
        <footer className="p-5 border-t border-slate-100 flex items-center justify-between gap-3 bg-slate-50/50">
          <button onClick={onClose} className="secondary-button text-sm">
            Close Arena
          </button>
          <button
            onClick={submit}
            disabled={!allAnswered || submitting || blueprintUnlocked}
            className="primary-button text-sm flex items-center gap-2"
          >
            <Send className="w-4 h-4" />
            {submitting ? 'Submitting…' : blueprintUnlocked ? 'Blueprint Unlocked' : 'Submit Assessment'}
          </button>
        </footer>
      </div>
    </div>
  )
}
