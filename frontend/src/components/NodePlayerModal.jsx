import { useMemo, useState } from 'react'
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  HelpCircle,
  Layers,
  Lightbulb,
  ListOrdered,
  MoveRight,
  RotateCcw,
  Sparkles,
  Tag,
  X,
} from 'lucide-react'

function ActivityFrame({ title, children }) {
  return (
    <div className="rounded-2xl border border-slate-200/90 bg-slate-50/60 p-5 space-y-4">
      {title && (
        <p className="text-xs uppercase tracking-wider text-indigo-600 font-bold flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5" />
          {title}
        </p>
      )}
      {children}
    </div>
  )
}

// -----------------------------------------------------------------------------
// 1. MATCH THE FOLLOWING (matching_pairs) — Automatically scored
// -----------------------------------------------------------------------------
function MatchingPairsActivity({ activity, onResult }) {
  const pairs = activity.pairs || []
  const [selectedLeft, setSelectedLeft] = useState(null)
  const [matches, setMatches] = useState({}) // { left_id: right_id }
  const [submitted, setSubmitted] = useState(false)

  // Shuffle right items stably
  const rightItems = useMemo(() => {
    return [...pairs].sort((a, b) => (a.right_text > b.right_text ? 1 : -1))
  }, [pairs])

  const handleLeftClick = (pairId) => {
    if (submitted) return
    setSelectedLeft(pairId)
  }

  const handleRightClick = (rightPairId) => {
    if (submitted || !selectedLeft) return
    setMatches((prev) => ({
      ...prev,
      [selectedLeft]: rightPairId,
    }))
    setSelectedLeft(null)
  }

  const handleRemoveMatch = (leftId) => {
    if (submitted) return
    setMatches((prev) => {
      const next = { ...prev }
      delete next[leftId]
      return next
    })
  }

  const allMatched = pairs.length > 0 && Object.keys(matches).length === pairs.length
  const isCorrect = allMatched && pairs.every((p) => matches[p.pair_id] === p.pair_id)

  const handleCheck = () => {
    if (!allMatched) return
    setSubmitted(true)
    if (onResult) onResult(isCorrect)
  }

  const handleRetry = () => {
    setMatches({})
    setSelectedLeft(null)
    setSubmitted(false)
  }

  return (
    <ActivityFrame title={activity.instruction || 'Match the Following'}>
      <p className="text-sm text-slate-600">
        Select a term on the left, then click its corresponding definition or property on the right.
      </p>

      <div className="grid md:grid-cols-2 gap-4">
        {/* Left Column */}
        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Terms</p>
          {pairs.map((p) => {
            const matchedRightId = matches[p.pair_id]
            const matchedRight = pairs.find((item) => item.pair_id === matchedRightId)
            const isSelected = selectedLeft === p.pair_id

            return (
              <div
                key={p.pair_id}
                onClick={() => handleLeftClick(p.pair_id)}
                className={`p-3 rounded-xl border text-sm font-medium transition cursor-pointer flex items-center justify-between ${
                  isSelected
                    ? 'border-indigo-600 bg-indigo-50/70 text-indigo-900 ring-2 ring-indigo-500/20'
                    : matchedRightId
                    ? 'border-emerald-300 bg-emerald-50/40 text-slate-800'
                    : 'border-slate-200 bg-white hover:border-indigo-300 text-slate-700'
                }`}
              >
                <span>{p.left_text}</span>
                {matchedRightId && (
                  <span
                    onClick={(e) => {
                      e.stopPropagation()
                      handleRemoveMatch(p.pair_id)
                    }}
                    className="text-xs font-normal text-emerald-700 bg-emerald-100/70 px-2 py-0.5 rounded-full"
                  >
                    Matched ✓
                  </span>
                )}
              </div>
            )
          })}
        </div>

        {/* Right Column */}
        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Matches / Definitions</p>
          {rightItems.map((p) => {
            const isUsed = Object.values(matches).includes(p.pair_id)

            return (
              <div
                key={p.pair_id}
                onClick={() => handleRightClick(p.pair_id)}
                className={`p-3 rounded-xl border text-sm transition cursor-pointer ${
                  isUsed
                    ? 'border-emerald-300 bg-emerald-50/30 text-slate-600 opacity-60'
                    : selectedLeft
                    ? 'border-indigo-300 bg-white hover:bg-indigo-50/50 hover:border-indigo-500 text-slate-800 font-medium'
                    : 'border-slate-200 bg-white text-slate-700'
                }`}
              >
                {p.right_text}
              </div>
            )
          })}
        </div>
      </div>

      {!submitted ? (
        <button disabled={!allMatched} onClick={handleCheck} className="primary-button">
          Check Matches
        </button>
      ) : (
        <div className="space-y-3">
          <div className={isCorrect ? 'feedback-good' : 'feedback-bad'}>
            <p className="font-semibold">{isCorrect ? 'Perfect Match!' : 'Some pairings are incorrect.'}</p>
            <p className="mt-1 text-xs">
              {isCorrect
                ? 'All university examination terms correctly linked to their authentic definitions.'
                : 'Review the terms and meanings before retrying.'}
            </p>
          </div>
          {!isCorrect && (
            <button onClick={handleRetry} className="secondary-button text-xs py-1.5 flex items-center gap-1.5">
              <RotateCcw className="w-3.5 h-3.5" /> Try Again
            </button>
          )}
        </div>
      )}
    </ActivityFrame>
  )
}

// -----------------------------------------------------------------------------
// 2. CATEGORIZATION / DRAG & DROP / TAP-TO-SORT (classification) — Automatically scored
// -----------------------------------------------------------------------------
function ClassificationActivity({ activity, onResult }) {
  const categories = activity.categories || []
  const items = activity.items || []
  const [placements, setPlacements] = useState({}) // { item_id: category_id }
  const [selectedItem, setSelectedItem] = useState(null)
  const [submitted, setSubmitted] = useState(false)

  const handleItemSelect = (item) => {
    if (submitted) return
    setSelectedItem(item.item_id === selectedItem ? null : item.item_id)
  }

  const handlePlaceInCategory = (catId) => {
    if (submitted || !selectedItem) return
    setPlacements((prev) => ({
      ...prev,
      [selectedItem]: catId,
    }))
    setSelectedItem(null)
  }

  const handleRemovePlacement = (itemId) => {
    if (submitted) return
    setPlacements((prev) => {
      const next = { ...prev }
      delete next[itemId]
      return next
    })
  }

  const allPlaced = items.length > 0 && items.every((item) => !!placements[item.item_id])
  const isCorrect = allPlaced && items.every((item) => placements[item.item_id] === item.correct_category_id)

  const handleCheck = () => {
    if (!allPlaced) return
    setSubmitted(true)
    if (onResult) onResult(isCorrect)
  }

  const handleRetry = () => {
    setPlacements({})
    setSelectedItem(null)
    setSubmitted(false)
  }

  const unplacedItems = items.filter((item) => !placements[item.item_id])

  return (
    <ActivityFrame title={activity.instruction || 'Categorization & Classification'}>
      <p className="text-sm text-slate-600">
        Tap a statement below, then tap the corresponding category box to sort it.
      </p>

      {/* Target Categories */}
      <div className="grid md:grid-cols-2 gap-4">
        {categories.map((cat) => {
          const placedInThisCat = items.filter((item) => placements[item.item_id] === cat.category_id)

          return (
            <div
              key={cat.category_id}
              onClick={() => handlePlaceInCategory(cat.category_id)}
              className={`rounded-2xl border p-4 transition min-h-[140px] flex flex-col ${
                selectedItem
                  ? 'border-indigo-400 bg-indigo-50/30 hover:bg-indigo-50/70 cursor-pointer ring-2 ring-indigo-500/10'
                  : 'border-slate-200 bg-white'
              }`}
            >
              <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                <span className="font-bold text-slate-800 text-sm">{cat.label}</span>
                <span className="text-xs text-slate-400">{placedInThisCat.length} items</span>
              </div>
              {cat.description && <p className="text-xs text-slate-400 mt-1">{cat.description}</p>}

              <div className="mt-3 space-y-2 flex-1">
                {placedInThisCat.map((item) => (
                  <div
                    key={item.item_id}
                    onClick={(e) => {
                      e.stopPropagation()
                      handleRemovePlacement(item.item_id)
                    }}
                    className="p-2.5 rounded-xl border border-slate-200 bg-slate-50 text-xs font-medium text-slate-700 flex items-center justify-between hover:border-rose-300 hover:bg-rose-50 cursor-pointer group"
                  >
                    <span>{item.text}</span>
                    <X className="w-3.5 h-3.5 text-slate-400 group-hover:text-rose-600" />
                  </div>
                ))}
                {placedInThisCat.length === 0 && (
                  <p className="text-xs text-slate-400 text-center py-4 border border-dashed border-slate-200 rounded-xl">
                    {selectedItem ? 'Tap to place selected statement here' : 'Drop statements here'}
                  </p>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Unsorted Items Pool */}
      {unplacedItems.length > 0 && (
        <div className="space-y-2 pt-2">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Statements to Sort</p>
          <div className="flex flex-wrap gap-2">
            {unplacedItems.map((item) => {
              const isSelected = selectedItem === item.item_id
              return (
                <button
                  key={item.item_id}
                  onClick={() => handleItemSelect(item)}
                  className={`px-3.5 py-2 rounded-xl text-xs font-medium border text-left transition ${
                    isSelected
                      ? 'border-indigo-600 bg-indigo-600 text-white shadow-sm'
                      : 'border-slate-200 bg-white hover:border-indigo-300 text-slate-700 shadow-sm'
                  }`}
                >
                  {item.text}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {!submitted ? (
        <button disabled={!allPlaced} onClick={handleCheck} className="primary-button">
          Check Categorization
        </button>
      ) : (
        <div className="space-y-3">
          <div className={isCorrect ? 'feedback-good' : 'feedback-bad'}>
            <p className="font-semibold">{isCorrect ? 'Accurately Sorted!' : 'Some items are misclassified.'}</p>
            <p className="mt-1 text-xs">
              {isCorrect
                ? 'All technical characteristics accurately categorized under their respective paradigms.'
                : 'Review the differences and retry the sorting.'}
            </p>
          </div>
          {!isCorrect && (
            <button onClick={handleRetry} className="secondary-button text-xs py-1.5 flex items-center gap-1.5">
              <RotateCcw className="w-3.5 h-3.5" /> Try Again
            </button>
          )}
        </div>
      )}
    </ActivityFrame>
  )
}

// -----------------------------------------------------------------------------
// 3. ORDERING (ordering) — Automatically scored
// -----------------------------------------------------------------------------
function OrderingActivity({ activity, onResult }) {
  const initialItems = useMemo(() => activity.items || [], [activity])
  const [order, setOrder] = useState(() => initialItems.map((i) => i.item_id))
  const [submitted, setSubmitted] = useState(false)

  const moveItem = (index, direction) => {
    if (submitted) return
    const targetIndex = index + direction
    if (targetIndex < 0 || targetIndex >= order.length) return
    const next = [...order]
    const temp = next[index]
    next[index] = next[targetIndex]
    next[targetIndex] = temp
    setOrder(next)
  }

  const correctOrder = activity.correct_order || []
  const isCorrect = order.length === correctOrder.length && order.every((id, idx) => id === correctOrder[idx])

  const handleCheck = () => {
    setSubmitted(true)
    if (onResult) onResult(isCorrect)
  }

  const handleRetry = () => {
    setSubmitted(false)
  }

  return (
    <ActivityFrame title={activity.instruction || 'Arrange the Correct Sequence'}>
      <p className="text-sm text-slate-600">
        Use the up and down arrows to place each pipeline stage in the proper chronological sequence.
      </p>

      <div className="space-y-2">
        {order.map((itemId, index) => {
          const item = initialItems.find((i) => i.item_id === itemId)
          return (
            <div
              key={itemId}
              className="p-3.5 rounded-xl border border-slate-200 bg-white flex items-center justify-between gap-3 shadow-sm"
            >
              <div className="flex items-center gap-3">
                <span className="w-6 h-6 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 font-bold text-xs flex items-center justify-center">
                  {index + 1}
                </span>
                <div>
                  <p className="font-semibold text-slate-800 text-sm">{item?.label || itemId}</p>
                  {item?.detail && <p className="text-xs text-slate-500 mt-0.5">{item.detail}</p>}
                </div>
              </div>

              {!submitted && (
                <div className="flex items-center gap-1">
                  <button
                    disabled={index === 0}
                    onClick={() => moveItem(index, -1)}
                    className="p-1 rounded-lg border border-slate-200 hover:bg-slate-100 disabled:opacity-30"
                  >
                    <ChevronUp className="w-4 h-4 text-slate-600" />
                  </button>
                  <button
                    disabled={index === order.length - 1}
                    onClick={() => moveItem(index, 1)}
                    className="p-1 rounded-lg border border-slate-200 hover:bg-slate-100 disabled:opacity-30"
                  >
                    <ChevronDown className="w-4 h-4 text-slate-600" />
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {!submitted ? (
        <button onClick={handleCheck} className="primary-button">
          Check Sequence
        </button>
      ) : (
        <div className="space-y-3">
          <div className={isCorrect ? 'feedback-good' : 'feedback-bad'}>
            <p className="font-semibold">{isCorrect ? 'Sequence Correct!' : 'Sequence is not correct.'}</p>
            {activity.explanation && <p className="mt-1 text-xs">{activity.explanation}</p>}
          </div>
          {!isCorrect && (
            <button onClick={handleRetry} className="secondary-button text-xs py-1.5 flex items-center gap-1.5">
              <RotateCcw className="w-3.5 h-3.5" /> Try Again
            </button>
          )}
        </div>
      )}
    </ActivityFrame>
  )
}

// -----------------------------------------------------------------------------
// 4. FILL IN THE BLANKS (fill_blank) — Automatically scored
// -----------------------------------------------------------------------------
function FillBlankActivity({ activity, onResult }) {
  const [answers, setAnswers] = useState({})
  const [activeBlankId, setActiveBlankId] = useState(null)
  const [submitted, setSubmitted] = useState(false)

  const template = activity.template || activity.sentence || ''
  const tokens = useMemo(() => template.split(/(\[[^\]]+\]|\{\{[^}]+\}\})/g), [template])
  const blanks = activity.blanks || []

  const blankIds = useMemo(() => {
    return tokens
      .map((t) => {
        const m = t.match(/^\[([^\]]+)\]|^\{\{([^}]+)\}\}$/)
        return m ? m[1] || m[2] : null
      })
      .filter(Boolean)
  }, [tokens])

  const placedWords = Object.values(answers).filter(Boolean)
  const allFilled = blankIds.length > 0 && blankIds.every((id) => !!answers[id])

  const isCorrect = blanks.every((blank) =>
    (blank.accepted_answers || []).some(
      (ans) => ans.trim().toLowerCase() === (answers[blank.blank_id] || '').trim().toLowerCase()
    )
  )

  const handleTileClick = (word) => {
    if (submitted) return
    const targetId = activeBlankId || blankIds.find((id) => !answers[id])
    if (!targetId) return

    setAnswers((prev) => ({ ...prev, [targetId]: word }))
    const nextUnfilled = blankIds.find((id) => id !== targetId && !answers[id])
    setActiveBlankId(nextUnfilled || null)
  }

  const handleSlotClick = (blankId) => {
    if (submitted) return
    if (answers[blankId]) {
      setAnswers((prev) => {
        const next = { ...prev }
        delete next[blankId]
        return next
      })
    }
    setActiveBlankId(blankId)
  }

  const handleCheck = () => {
    if (!allFilled) return
    setSubmitted(true)
    if (onResult) onResult(isCorrect)
  }

  const handleRetry = () => {
    setAnswers({})
    setActiveBlankId(null)
    setSubmitted(false)
  }

  const wordBank = activity.word_bank || []

  return (
    <ActivityFrame title={activity.instruction || 'Fill in the Blanks'}>
      {/* Interactive Sentence Box */}
      <div className="p-5 rounded-2xl border border-slate-200 bg-white leading-loose text-base text-slate-800 shadow-sm">
        {tokens.map((token, index) => {
          const match = token.match(/^\[([^\]]+)\]|^\{\{([^}]+)\}\}$/)
          if (match) {
            const blankId = match[1] || match[2]
            const filledWord = answers[blankId]
            const isActive = activeBlankId === blankId
            const blankDef = blanks.find((b) => b.blank_id === blankId)
            const isSlotCorrect =
              submitted &&
              (blankDef?.accepted_answers || []).some(
                (ans) => ans.trim().toLowerCase() === (filledWord || '').trim().toLowerCase()
              )

            return (
              <span
                key={index}
                onClick={() => handleSlotClick(blankId)}
                className={`inline-flex items-center justify-center min-w-[90px] h-9 mx-1.5 px-3 rounded-xl border text-sm font-semibold transition cursor-pointer align-middle ${
                  submitted
                    ? isSlotCorrect
                      ? 'border-emerald-500 bg-emerald-50 text-emerald-900 ring-2 ring-emerald-500/20'
                      : 'border-rose-400 bg-rose-50 text-rose-900'
                    : filledWord
                    ? 'border-indigo-400 bg-indigo-50/70 text-indigo-900 ring-1 ring-indigo-500/20'
                    : isActive
                    ? 'border-indigo-600 bg-indigo-50/40 ring-2 ring-indigo-500/30 text-indigo-600'
                    : 'border-dashed border-slate-300 bg-slate-50 hover:border-indigo-400 text-slate-400'
                }`}
              >
                {filledWord || `[Slot ${blankId}]`}
              </span>
            )
          }
          return <span key={index}>{token}</span>
        })}
      </div>

      {/* Word Bank */}
      <div className="space-y-2">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Word Bank Tiles</p>
        <div className="flex flex-wrap gap-2">
          {wordBank.map((word, index) => {
            const isUsed = placedWords.includes(word)
            return (
              <button
                key={index}
                disabled={submitted || isUsed}
                onClick={() => handleTileClick(word)}
                className={`word-tile btn-tactile ${
                  isUsed ? 'opacity-30 cursor-not-allowed bg-slate-100 text-slate-400 border-dashed' : ''
                }`}
              >
                {word}
              </button>
            )
          })}
        </div>
      </div>

      {!submitted ? (
        <button disabled={!allFilled} onClick={handleCheck} className="primary-button">
          Check Answers
        </button>
      ) : (
        <div className="space-y-3">
          <div className={isCorrect ? 'feedback-good' : 'feedback-bad'}>
            <p className="font-semibold">{isCorrect ? 'All Blanks Correct!' : 'One or more words are incorrect.'}</p>
            {activity.explanation && <p className="mt-1 text-xs">{activity.explanation}</p>}
          </div>
          {!isCorrect && (
            <button onClick={handleRetry} className="secondary-button text-xs py-1.5 flex items-center gap-1.5">
              <RotateCcw className="w-3.5 h-3.5" /> Try Again
            </button>
          )}
        </div>
      )}
    </ActivityFrame>
  )
}

// -----------------------------------------------------------------------------
// 5. SELECT THE CORRECT EXAM POINTS (key_points_check) — Automatically scored
// -----------------------------------------------------------------------------
function KeyPointsCheckActivity({ activity, onResult }) {
  const options = activity.options || []
  const [selected, setSelected] = useState(new Set())
  const [submitted, setSubmitted] = useState(false)

  const toggleOption = (id) => {
    if (submitted) return
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const essentialIds = options.filter((o) => o.is_essential).map((o) => o.point_id)
  const isCorrect =
    essentialIds.every((id) => selected.has(id)) &&
    options.filter((o) => !o.is_essential).every((o) => !selected.has(o.point_id))

  const handleCheck = () => {
    if (selected.size === 0) return
    setSubmitted(true)
    if (onResult) onResult(isCorrect)
  }

  const handleRetry = () => {
    setSelected(new Set())
    setSubmitted(false)
  }

  return (
    <ActivityFrame title={activity.instruction || 'Select Essential Examination Rubric Points'}>
      <p className="text-sm font-semibold text-slate-800">{activity.question}</p>
      <p className="text-xs text-slate-500">
        Select all essential marking criteria required for full marks. Beware of non-technical or superficial distractors.
      </p>

      <div className="space-y-2">
        {options.map((option) => {
          const isChecked = selected.has(option.point_id)
          const showState = submitted
          const isEssential = option.is_essential

          return (
            <div
              key={option.point_id}
              onClick={() => toggleOption(option.point_id)}
              className={`p-3.5 rounded-xl border text-sm transition cursor-pointer flex items-start gap-3 shadow-sm ${
                showState
                  ? isEssential
                    ? isChecked
                      ? 'border-emerald-500 bg-emerald-50/70 text-emerald-900 ring-1 ring-emerald-500/20'
                      : 'border-amber-400 bg-amber-50/60 text-amber-900'
                    : isChecked
                    ? 'border-rose-400 bg-rose-50/70 text-rose-900'
                    : 'border-slate-200 bg-white text-slate-400'
                  : isChecked
                  ? 'border-indigo-600 bg-indigo-50/60 text-indigo-950 ring-1 ring-indigo-500/20'
                  : 'border-slate-200 bg-white hover:border-indigo-300 text-slate-700'
              }`}
            >
              <input
                type="checkbox"
                checked={isChecked}
                onChange={() => {}}
                disabled={submitted}
                className="mt-0.5 rounded text-indigo-600 focus:ring-indigo-500"
              />
              <div className="flex-1">
                <p className="font-medium">{option.text}</p>
                {showState && option.explanation && (
                  <p className="text-xs mt-1 text-slate-600 font-normal">{option.explanation}</p>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {!submitted ? (
        <button disabled={selected.size === 0} onClick={handleCheck} className="primary-button">
          Check Rubric Criteria
        </button>
      ) : (
        <div className="space-y-3">
          <div className={isCorrect ? 'feedback-good' : 'feedback-bad'}>
            <p className="font-semibold">{isCorrect ? 'Full Marks Criteria Selected!' : 'Criteria incomplete or distractor chosen.'}</p>
            {activity.explanation && <p className="mt-1 text-xs">{activity.explanation}</p>}
          </div>
          {!isCorrect && (
            <button onClick={handleRetry} className="secondary-button text-xs py-1.5 flex items-center gap-1.5">
              <RotateCcw className="w-3.5 h-3.5" /> Try Again
            </button>
          )}
        </div>
      )}
    </ActivityFrame>
  )
}

// -----------------------------------------------------------------------------
// 6. DIAGNOSTIC MCQ (mcq) — Automatically scored
// -----------------------------------------------------------------------------
function MCQActivity({ activity, onResult }) {
  const [selected, setSelected] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const isCorrect = selected === activity.correct_option_id

  const handleCheck = () => {
    if (!selected) return
    setSubmitted(true)
    if (onResult) onResult(isCorrect)
  }

  const handleRetry = () => {
    setSelected('')
    setSubmitted(false)
  }

  const selectedOpt = (activity.options || []).find((o) => o.option_id === selected)

  return (
    <ActivityFrame title={activity.instruction || 'Diagnostic MCQ'}>
      <p className="font-semibold text-slate-800 text-sm leading-relaxed">{activity.question}</p>
      <div className="space-y-2">
        {(activity.options || []).map((option) => (
          <button
            key={option.option_id}
            disabled={submitted}
            onClick={() => setSelected(option.option_id)}
            className={`activity-option ${selected === option.option_id ? 'activity-selected' : ''}`}
          >
            {option.text}
          </button>
        ))}
      </div>

      {!submitted ? (
        <button disabled={!selected} onClick={handleCheck} className="primary-button">
          Check Answer
        </button>
      ) : (
        <div className="space-y-3">
          <div className={isCorrect ? 'feedback-good' : 'feedback-bad'}>
            <p className="font-semibold">{isCorrect ? 'Correct!' : 'Incorrect.'}</p>
            <p className="mt-1 text-xs">{selectedOpt?.feedback || activity.explanation}</p>
            {selectedOpt?.misconception_tag && (
              <p className="mt-1 text-xs text-amber-700 font-medium">Concept gap: {selectedOpt.misconception_tag}</p>
            )}
          </div>
          {!isCorrect && (
            <button onClick={handleRetry} className="secondary-button text-xs py-1.5 flex items-center gap-1.5">
              <RotateCcw className="w-3.5 h-3.5" /> Try Again
            </button>
          )}
        </div>
      )}
    </ActivityFrame>
  )
}

// -----------------------------------------------------------------------------
// GENERIC JSON-DRIVEN ACTIVITY REGISTRY
// -----------------------------------------------------------------------------
function ActivityRenderer({ activity, onResult }) {
  if (!activity) return null

  switch (activity.type) {
    case 'matching_pairs':
      return <MatchingPairsActivity activity={activity} onResult={onResult} />
    case 'classification':
      return <ClassificationActivity activity={activity} onResult={onResult} />
    case 'ordering':
      return <OrderingActivity activity={activity} onResult={onResult} />
    case 'fill_blank':
      return <FillBlankActivity activity={activity} onResult={onResult} />
    case 'key_points_check':
      return <KeyPointsCheckActivity activity={activity} onResult={onResult} />
    case 'mcq':
      return <MCQActivity activity={activity} onResult={onResult} />
    default:
      // Fallback for short_answer or others: render as KeyPointsCheck or MCQ
      return <MCQActivity activity={{ ...activity, question: activity.question || activity.prompt || 'Exam Question' }} onResult={onResult} />
  }
}

// -----------------------------------------------------------------------------
// MAIN MODAL: TOPIC NODE QUESTION SOLVER (NO TEXTBOXES)
// -----------------------------------------------------------------------------
export default function NodePlayerModal({ node, onClose, onCompleteNode }) {
  const rawQuestions = node.questions || []
  const questions = useMemo(() => {
    if (rawQuestions.length > 0) return rawQuestions
    return [
      {
        question_id: 'q1',
        prompt: node.title,
        marks: 2,
        activity: {
          type: 'mcq',
          instruction: 'Diagnostic Assessment',
          question: `Which fundamental principle is central to ${node.title}?`,
          options: [
            { option_id: 'opt_1', text: 'Core signal acquisition and accurate physiological decoding' },
            { option_id: 'opt_2', text: 'Random variation without calibration' },
          ],
          correct_option_id: 'opt_1',
          explanation: 'University examinations test rigorous signal acquisition and processing.',
        },
      },
    ]
  }, [rawQuestions, node.title])

  const [currentIndex, setCurrentIndex] = useState(0)
  const [results, setResults] = useState({})
  const [showGapFiller, setShowGapFiller] = useState({})

  const currentQ = questions[currentIndex] || questions[0]
  const qId = currentQ.question_id || `q_${currentIndex}`
  const isCurrentSolved = results[qId] === true

  const handleResult = (passed) => {
    setResults((prev) => ({ ...prev, [qId]: passed }))
    if (!passed && currentQ.prerequisite_gap_filler) {
      setShowGapFiller((prev) => ({ ...prev, [qId]: true }))
    }
  }

  const handleGapFillerResult = (passed) => {
    if (passed) {
      // Allow student to retry the main question with confidence
    }
  }

  const solvedCount = Object.values(results).filter(Boolean).length
  const allSolved = questions.length > 0 && solvedCount === questions.length

  const handleComplete = () => {
    const score = questions.length > 0 ? solvedCount / questions.length : 1.0
    onCompleteNode(node.node_id, score)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-3xl rounded-3xl border border-slate-200 bg-white p-6 md:p-8 shadow-2xl space-y-6 my-auto">
        {/* Modal Header */}
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <span className="pill text-indigo-700 bg-indigo-50 border-indigo-200 font-bold">
                TOPIC NODE {node.order}
              </span>
              <span className="text-xs font-semibold text-slate-500">
                Question {currentIndex + 1} of {questions.length}
              </span>
            </div>
            <h2 className="text-xl md:text-2xl font-bold text-slate-900 mt-2">{node.title}</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Question Header Card */}
        <div className="p-4 rounded-2xl bg-indigo-50/50 border border-indigo-100 flex items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-600 text-white">
                Question {currentIndex + 1} · {currentQ.marks || 2} Marks
              </span>
              {isCurrentSolved && (
                <span className="text-xs font-semibold text-emerald-600 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Solved
                </span>
              )}
            </div>
            <p className="font-semibold text-slate-900 text-base md:text-lg mt-1">{currentQ.prompt}</p>
          </div>

          {!showGapFiller[qId] && currentQ.prerequisite_gap_filler && !isCurrentSolved && (
            <button
              onClick={() => setShowGapFiller((prev) => ({ ...prev, [qId]: true }))}
              className="secondary-button text-xs py-1.5 px-3 shrink-0 flex items-center gap-1.5"
            >
              <Lightbulb className="w-3.5 h-3.5 text-amber-500" />
              Need Help?
            </button>
          )}
        </div>

        {/* Primary Structured Activity (Zero Textboxes) */}
        <div className="space-y-4">
          <ActivityRenderer activity={currentQ.activity} onResult={handleResult} />
        </div>

        {/* Inline Prerequisite Gap-Filler (Activated on struggle or request) */}
        {showGapFiller[qId] && currentQ.prerequisite_gap_filler && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50/40 p-5 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-bold uppercase tracking-wider text-amber-800 flex items-center gap-1.5">
                <Lightbulb className="w-4 h-4 text-amber-600" />
                Inline Prerequisite Gap-Filler
              </p>
              <button
                onClick={() => setShowGapFiller((prev) => ({ ...prev, [qId]: false }))}
                className="text-xs text-amber-700 hover:text-amber-900"
              >
                Hide
              </button>
            </div>
            <p className="text-xs text-slate-600">
              Solve this foundational puzzle to bridge the conceptual gap before retrying the main exam question.
            </p>
            <ActivityRenderer
              activity={currentQ.prerequisite_gap_filler}
              onResult={handleGapFillerResult}
            />
          </div>
        )}

        {/* Modal Footer & Navigation */}
        <div className="flex items-center justify-between border-t border-slate-100 pt-5">
          <button
            disabled={currentIndex === 0}
            onClick={() => setCurrentIndex((prev) => prev - 1)}
            className="secondary-button text-sm py-2 px-4 flex items-center gap-1.5 disabled:opacity-40"
          >
            <ArrowLeft className="w-4 h-4" /> Previous Question
          </button>

          <div className="flex items-center gap-2">
            {currentIndex < questions.length - 1 ? (
              <button
                onClick={() => setCurrentIndex((prev) => prev + 1)}
                className="primary-button text-sm py-2 px-5 flex items-center gap-1.5"
              >
                Next Question <ArrowRight className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={handleComplete}
                className="inline-flex items-center gap-2 rounded-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-sm px-6 py-2.5 shadow-sm shadow-emerald-200"
              >
                <CheckCircle2 className="w-4 h-4" />
                Complete Topic Node ({solvedCount}/{questions.length})
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
