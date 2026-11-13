import COERationalRoot

/-!
A deliberate counterexample when the exact affine root lies *inside* the cell.
The coefficient is 1, the bias and root are 0, and the negative/positive
interior observations cannot share a ReLU branch. This module MUST fail.
-/

namespace COERootInvalid

theorem invalid_no_root_condition :
    decide (0 < COERationalRoot.affine 1 0 (-1 : Rat)) =
    decide (0 < COERationalRoot.affine 1 0 (1 : Rat)) := by
  rfl

end COERootInvalid
