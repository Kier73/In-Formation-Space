import COEWireCheck

/-!
COE-008: connect the *actual* COEWireCheck rootExcluded Boolean guard to
the previously proved rational root-exclusion sign theorem. Unlike a
closed fixture, these results quantify over an arbitrary rational point.
-/

namespace COE008Soundness
open COEWireCheck

/-- Open interval membership is convex, including unbounded endpoints. -/
private theorem between_inside (cell : Cell) (p q root : Rat)
    (hp : inside cell p = true)
    (hq : inside cell q = true)
    (hpr : p < root) (hrq : root < q) :
    inside cell root = true := by
  cases cell with
  | mk lo hi output =>
    cases lo <;> cases hi <;>
    simp [inside] at *
    all_goals grind

/-- A nonzero preactivation's declared root is checked both for the exact
    zero equation and for exclusion from this cell's open interior. -/
private theorem root_guard_facts (cell : Cell) (a : Affine)
    (h : rootExcluded cell a = true) (hm : a.slope ≠ 0) :
    evaluateAt a (-a.offset / a.slope) = 0 ∧
    inside cell (-a.offset / a.slope) = false := by
  simp [rootExcluded, hm] at h
  grind

/-- Root-exclusion guarded by the actual executable Boolean verifier
    implies the sign decision is constant between any two interior
    rational points, including one-sided unbounded cells. -/
theorem root_guard_implies_sign_stable (cell : Cell) (a : Affine)
    (p x : Rat)
    (hroot : rootExcluded cell a = true)
    (hp : inside cell p = true)
    (hx : inside cell x = true) :
    decide (0 < evaluateAt a p) = decide (0 < evaluateAt a x) := by
  by_cases hz : a.slope = 0
  · simp [evaluateAt, hz]
  · obtain ⟨hzero, hrnot⟩ := root_guard_facts cell a hroot hz
    let r : Rat := -a.offset / a.slope
    have hnp : ¬ (p < r ∧ r < x) := by
      intro h
      have hr := between_inside cell p x r hp hx h.1 h.2
      have : inside cell r = false := hrnot
      grind
    have hnx : ¬ (x < r ∧ r < p) := by
      intro h
      have hr := between_inside cell x p r hx hp h.1 h.2
      have : inside cell r = false := hrnot
      grind
    have hpn : p ≠ r := by
      intro h
      subst p
      grind
    have hxn : x ≠ r := by
      intro h
      subst x
      grind
    have sameSide : (p < r ∧ x < r) ∨ (r < p ∧ r < x) := by
      grind
    rcases sameSide with ⟨hpr, hxr⟩ | ⟨hrp, hrx⟩
    · have hpa : p + x - r < p := by grind
      have hxa : p + x - r < x := by grind
      have hleft : ¬ (p + x - r < r ∧ r < r) := by simp
      have hsign := COERationalRoot.sign_stable_of_excluded_root
        a.slope a.offset (p + x - r) r r p x
        (by simpa [COERationalRoot.affine, evaluateAt, r] using hzero)
        hleft ⟨hpa, hpr⟩ ⟨hxa, hxr⟩
      simpa [COERationalRoot.affine, evaluateAt] using hsign
    · have hpb : p < p + x - r := by grind
      have hxb : x < p + x - r := by grind
      have hright : ¬ (r < r ∧ r < p + x - r) := by simp
      have hsign := COERationalRoot.sign_stable_of_excluded_root
        a.slope a.offset r (p + x - r) r p x
        (by simpa [COERationalRoot.affine, evaluateAt, r] using hzero)
        hright ⟨hrp, hpb⟩ ⟨hrx, hxb⟩
      simpa [COERationalRoot.affine, evaluateAt] using hsign

#print axioms COE008Soundness.root_guard_implies_sign_stable
end COE008Soundness
