import Init

/-!
COE-005: kernel-checked logical rules used by exact activation-cell
certificates. This proves a branch-soundness rule *given* sign stability
and a complete-cover transfer rule. It does NOT formalize the byte parser,
root exclusion algorithm, SHA-256, or floating-point interpretation.
-/

namespace COECellSoundness

/-- A classifier for whether a value is in the active ReLU branch.
    No ordered-ring assumption is needed for this logical rule. -/
def rectified {α : Type} (positive : α → Bool) (zero : α) (value : α) : α :=
  if positive value then value else zero

/-- The affine constructor chooses one branch at a probe coordinate. -/
def selected {α : Type} (positive : α → Bool) (zero : α)
    (function : α → α) (probe : α) : α → α :=
  if positive (function probe) then function else fun _ => zero

/-- A branch chosen at a probe represents the pointwise rectified operation
    wherever the activation decision agrees. The checker must independently
    establish this decision stability over each claimed cell. -/
theorem selected_sound_of_stable_decision
    {α : Type} (positive : α → Bool) (zero : α)
    (function : α → α) (probe x : α)
    (stable : positive (function probe) = positive (function x)) :
    selected positive zero function probe x =
      rectified positive zero (function x) := by
  cases hp : positive (function probe) with
  | false =>
      have hx : positive (function x) = false := by
        calc
          positive (function x) = positive (function probe) := stable.symm
          _ = false := hp
      simp [selected, rectified, hp, hx]
  | true =>
      have hx : positive (function x) = true := by
        calc
          positive (function x) = positive (function probe) := stable.symm
          _ = true := hp
      simp [selected, rectified, hp, hx]

/-- If every coordinate belongs to a certified observation cell, and both
    realizations are proven to equal its stated observation, they agree on
    the complete declared coordinate type. In particular, this theorem is
    polymorphic in the coordinate type rather than enumerating samples. -/
theorem observation_equivalence_of_complete_cover
    {X Cell Y : Type}
    (cells : List Cell) (covers : Cell → X → Prop)
    (left right claimed : X → Y)
    (complete : ∀ x : X, ∃ cell : Cell, cell ∈ cells ∧ covers cell x)
    (left_sound : ∀ cell, cell ∈ cells → ∀ x, covers cell x → left x = claimed x)
    (right_sound : ∀ cell, cell ∈ cells → ∀ x, covers cell x → right x = claimed x) :
    ∀ x : X, left x = right x := by
  intro x
  obtain ⟨cell, member, within⟩ := complete x
  calc
    left x = claimed x := left_sound cell member x within
    _ = right x := (right_sound cell member x within).symm

#print axioms COECellSoundness.selected_sound_of_stable_decision
#print axioms COECellSoundness.observation_equivalence_of_complete_cover

end COECellSoundness
