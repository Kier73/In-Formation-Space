import COECellSoundness

/-! COE-006: rational affine root-exclusion lemmas. -/
namespace COERationalRoot

/-- Exact rational affine preactivation, using the same m*x+b convention as COE-002. -/
def affine (m b x : Rat) : Rat := m * x + b

/-- Excluding an exact root from an open cell places it on one side of its endpoints. -/
theorem excluded_root_outside (left right root : Rat)
    (h : ¬ (left < root ∧ root < right)) :
    root ≤ left ∨ right ≤ root := by
  by_cases hl : root ≤ left
  · exact Or.inl hl
  · have hleft : left < root := (Rat.not_le).mp hl
    have hnr : ¬ root < right := by
      intro hr
      exact h ⟨hleft, hr⟩
    exact Or.inr ((Rat.not_lt).mp hnr)

/-- Positive slope implies strictly increasing affine output. -/
theorem increasing (m b x y : Rat) (hm : 0 < m) (hxy : x < y) :
    affine m b x < affine m b y := by
  unfold affine
  exact (Rat.add_lt_add_right (c := b)).mpr ((Rat.mul_lt_mul_left hm).mpr hxy)

/-- Negative slope implies strictly decreasing affine output. -/
theorem decreasing (m b x y : Rat) (hm : m < 0) (hxy : x < y) :
    affine m b y < affine m b x := by
  have hpositive : 0 < -m := by simpa using (Rat.neg_lt_neg hm)
  have hmul : (-m) * x < (-m) * y := (Rat.mul_lt_mul_left hpositive).mpr hxy
  have hflip : -((-m) * y) < -((-m) * x) := Rat.neg_lt_neg hmul
  have hreverse : m * y < m * x := by simpa [Rat.neg_mul] using hflip
  unfold affine
  exact (Rat.add_lt_add_right (c := b)).mpr hreverse

/-- If an affine function has a certified exact zero at root, and that root
    lies outside an open rational interval, its positive-branch decision is
    constant on that entire interval. Works for all three slope signs. -/
theorem sign_stable_of_excluded_root
    (m b left right root probe x : Rat)
    (hroot : affine m b root = 0)
    (hexcluded : ¬ (left < root ∧ root < right))
    (hprobe : left < probe ∧ probe < right)
    (hx : left < x ∧ x < right) :
    decide (0 < affine m b probe) = decide (0 < affine m b x) := by
  have hside := excluded_root_outside left right root hexcluded
  by_cases hmpos : 0 < m
  · rcases hside with hleft | hright
    · have hrprobe : root < probe := lt_of_le_of_lt hleft hprobe.1
      have hrx : root < x := lt_of_le_of_lt hleft hx.1
      have hprobePos : 0 < affine m b probe := by
        have h := increasing m b root probe hmpos hrprobe
        simpa [hroot] using h
      have hxPos : 0 < affine m b x := by
        have h := increasing m b root x hmpos hrx
        simpa [hroot] using h
      simp [hprobePos, hxPos]
    · have hprobeRoot : probe < root := lt_of_lt_of_le hprobe.2 hright
      have hxRoot : x < root := lt_of_lt_of_le hx.2 hright
      have hprobeNeg : affine m b probe < 0 := by
        have h := increasing m b probe root hmpos hprobeRoot
        simpa [hroot] using h
      have hxNeg : affine m b x < 0 := by
        have h := increasing m b x root hmpos hxRoot
        simpa [hroot] using h
      have hp : ¬0 < affine m b probe := fun h =>
        ((Rat.not_le).mpr hprobeNeg) (Rat.le_of_lt h)
      have hq : ¬0 < affine m b x := fun h =>
        ((Rat.not_le).mpr hxNeg) (Rat.le_of_lt h)
      simp [hp, hq]
  · by_cases hmneg : m < 0
    · rcases hside with hleft | hright
      · have hrprobe : root < probe := lt_of_le_of_lt hleft hprobe.1
        have hrx : root < x := lt_of_le_of_lt hleft hx.1
        have hprobeNeg : affine m b probe < 0 := by
          have h := decreasing m b root probe hmneg hrprobe
          simpa [hroot] using h
        have hxNeg : affine m b x < 0 := by
          have h := decreasing m b root x hmneg hrx
          simpa [hroot] using h
        have hp : ¬0 < affine m b probe := fun h =>
          ((Rat.not_le).mpr hprobeNeg) (Rat.le_of_lt h)
        have hq : ¬0 < affine m b x := fun h =>
          ((Rat.not_le).mpr hxNeg) (Rat.le_of_lt h)
        simp [hp, hq]
      · have hprobeRoot : probe < root := lt_of_lt_of_le hprobe.2 hright
        have hxRoot : x < root := lt_of_lt_of_le hx.2 hright
        have hprobePos : 0 < affine m b probe := by
          have h := decreasing m b probe root hmneg hprobeRoot
          simpa [hroot] using h
        have hxPos : 0 < affine m b x := by
          have h := decreasing m b x root hmneg hxRoot
          simpa [hroot] using h
        simp [hprobePos, hxPos]
    · have hm_le : m ≤ 0 := (Rat.not_lt).mp hmpos
      have hzero_le : 0 ≤ m := (Rat.not_lt).mp hmneg
      have hmzero : m = 0 := Rat.le_antisymm hm_le hzero_le
      simp [affine, hmzero]

/-- Even at the exact zero, the branch selected from *any* interior probe
    agrees with a pointwise ReLU. This handles a root on either endpoint. -/
theorem selected_at_root_zero (m b root probe : Rat)
    (hroot : affine m b root = 0) :
    COECellSoundness.selected (fun z : Rat => decide (0 < z)) 0
        (affine m b) probe root = 0 := by
  simp [COECellSoundness.selected, hroot]

#print axioms COERationalRoot.excluded_root_outside
#print axioms COERationalRoot.increasing
#print axioms COERationalRoot.decreasing
#print axioms COERationalRoot.sign_stable_of_excluded_root
#print axioms COERationalRoot.selected_at_root_zero
end COERationalRoot
