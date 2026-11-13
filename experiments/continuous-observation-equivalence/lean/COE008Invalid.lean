import COE008Evaluation

/-!
Negative control: a forged constant output cannot be certified as the
identity network merely by claiming an affine observation. The test
intentionally submits a false closed theorem and must fail under Lean.
-/

namespace COE008Invalid
open COEWireCheck

def forged : Cert :=
  { layers :=
      [{ weights := [[(1 : Rat)]], bias := [0], relu := false }]
    cells :=
      [{ left := none, right := none,
         output := [{ slope := 0, offset := 1 }] }] }

theorem falsely_accepted : verify forged = true := by decide +kernel

end COE008Invalid
