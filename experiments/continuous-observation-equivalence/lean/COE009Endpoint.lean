import COE008Evaluation

/-!
COE-009: rational cell-boundary (endpoint) soundness.

An accepted ReLU root guard plus an interior probe is sufficient to
select a branch that agrees with direct ReLU evaluation even on finite
endpoints, where the activation may equal zero and its Boolean sign
can differ from the interior sign. No continuity axiom is assumed.
-/

namespace COE009Endpoint
open COEWireCheck COE008Evaluation

def closedInside (c : Cell) (x : Rat) : Bool :=
  (match c.left with
   | none => true
   | some left => decide (left ≤ x)) &&
  (match c.right with
   | none => true
   | some right => decide (x ≤ right))

theorem insideImpliesClosed (c : Cell) (x : Rat)
    (h : inside c x = true) : closedInside c x = true := by
  cases c with
  | mk l u out =>
    cases l <;> cases u <;>
    simp [inside, closedInside] at *
    all_goals grind

/-- When p is an interior point, q is in the closed cell, and r lies
    strictly beyond q but not beyond p (or vice versa), r is interior.
    This works for infinite outer endpoints as well. -/
theorem betweenInsideClosed (c : Cell) (p q r : Rat)
    (hp : inside c p = true)
    (hq : closedInside c q = true)
    (range : (q < r ∧ r ≤ p) ∨ (p ≤ r ∧ r < q)) :
    inside c r = true := by
  cases c with
  | mk l u out =>
    cases l <;> cases u <;>
    simp [inside, closedInside] at *
    all_goals grind

private theorem positiveSlopeReflect (a : Affine)
    (hm : 0 < a.slope) (u v : Rat)
    (h : evaluateAt a u ≤ evaluateAt a v) : u ≤ v := by
  by_cases hle : u ≤ v
  · exact hle
  · have hvu : v < u := (Rat.not_le).mp hle
    have hf := COERationalRoot.increasing a.slope a.offset v u hm hvu
    change evaluateAt a v < evaluateAt a u at hf
    grind

private theorem negativeSlopeReflect (a : Affine)
    (hm : a.slope < 0) (u v : Rat)
    (h : evaluateAt a u ≤ evaluateAt a v) : v ≤ u := by
  by_cases hle : v ≤ u
  · exact hle
  · have huv : u < v := (Rat.not_le).mp hle
    have hf := COERationalRoot.decreasing a.slope a.offset u v hm huv
    change evaluateAt a v < evaluateAt a u at hf
    grind

private theorem positiveSlopeStrict (a : Affine)
    (hm : 0 < a.slope) (u v : Rat)
    (h : evaluateAt a u < evaluateAt a v) : u < v := by
  have hle := positiveSlopeReflect a hm u v (Rat.le_of_lt h)
  have hne : u ≠ v := by intro h; subst v; grind
  exact Rat.lt_of_le_of_ne hle hne

private theorem negativeSlopeStrict (a : Affine)
    (hm : a.slope < 0) (u v : Rat)
    (h : evaluateAt a u < evaluateAt a v) : v < u := by
  have hle := negativeSlopeReflect a hm u v (Rat.le_of_lt h)
  have hne : v ≠ u := by intro h; subst u; grind
  exact Rat.lt_of_le_of_ne hle hne

private theorem rootGuardFacts (c : Cell) (a : Affine)
    (h : rootExcluded c a = true) (hm : a.slope ≠ 0) :
    evaluateAt a (-a.offset / a.slope) = 0 ∧
      inside c (-a.offset / a.slope) = false := by
  simp [rootExcluded, hm] at h
  grind

/-- A branch chosen by the *actual verifier* at an interior probe is
    pointwise correct at any rational point of the CLOSED cell, including
    a finite endpoint where the preactivation may be exactly zero. -/
theorem selectedAtClosed (c : Cell) (a : Affine) (p x : Rat)
    (hguard : rootExcluded c a = true)
    (hp : inside c p = true)
    (hx : closedInside c x = true) :
    evaluateAt (if 0 < evaluateAt a p then a else zeroAffine) x =
      (if 0 < evaluateAt a x then evaluateAt a x else 0) := by
  by_cases hmzero : a.slope = 0
  · have hsame : evaluateAt a p = evaluateAt a x := by
      simp [evaluateAt, hmzero]
    by_cases hpos : 0 < evaluateAt a p
    · have hxpos : 0 < evaluateAt a x := by simpa [← hsame] using hpos
      simp [hpos, hxpos]
    · have hxneg : ¬ 0 < evaluateAt a x := by simpa [← hsame] using hpos
      simp only [if_neg hpos, if_neg hxneg]
      change (0 : Rat) * x + 0 = 0
      grind
  · let r : Rat := -a.offset / a.slope
    obtain ⟨hrzero, hrout⟩ := rootGuardFacts c a hguard hmzero
    have rootNotInside : inside c r = false := hrout
    by_cases hpPos : 0 < evaluateAt a p
    · by_cases hxPos : 0 < evaluateAt a x
      · simp only [if_pos hpPos, if_pos hxPos]
      · by_cases hxZero : evaluateAt a x = 0
        · simp only [if_pos hpPos]
          simp [hxZero]
        · have hxNeg : evaluateAt a x < 0 := by grind
          have hrange : (x < r ∧ r ≤ p) ∨ (p ≤ r ∧ r < x) := by
            by_cases hmpos : 0 < a.slope
            · have hxr : x < r := positiveSlopeStrict a hmpos x r (by grind)
              have hrp : r < p := positiveSlopeStrict a hmpos r p (by grind)
              exact Or.inl ⟨hxr, Rat.le_of_lt hrp⟩
            · have hmneg : a.slope < 0 := by grind
              have hpr : p < r := negativeSlopeStrict a hmneg r p (by grind)
              have hrx : r < x := negativeSlopeStrict a hmneg x r (by grind)
              exact Or.inr ⟨Rat.le_of_lt hpr, hrx⟩
          have hin : inside c r = true :=
            betweenInsideClosed c p x r hp hx hrange
          grind
    · by_cases hxPos : 0 < evaluateAt a x
      · have hple : evaluateAt a p ≤ 0 := (Rat.not_lt).mp hpPos
        have hrange : (x < r ∧ r ≤ p) ∨ (p ≤ r ∧ r < x) := by
          by_cases hmpos : 0 < a.slope
          · have hpr : p ≤ r := positiveSlopeReflect a hmpos p r (by grind)
            have hrx : r < x := positiveSlopeStrict a hmpos r x (by grind)
            exact Or.inr ⟨hpr, hrx⟩
          · have hmneg : a.slope < 0 := by grind
            have hrp : r ≤ p := negativeSlopeReflect a hmneg p r (by grind)
            have hxr : x < r := negativeSlopeStrict a hmneg r x (by grind)
            exact Or.inl ⟨hxr, hrp⟩
        have hin : inside c r = true :=
          betweenInsideClosed c p x r hp hx hrange
        grind
      · simp only [if_neg hpPos, if_neg hxPos]
        simp [zeroAffine, evaluateAt]
        grind

#print axioms COE009Endpoint.selectedAtClosed
end COE009Endpoint
