import COE010Real

/-!
Negative control: the ReLU of a negative real input is not the input.
Lean must reject this false equality even though the expression is
exactly rational-affine followed by a permitted ReLU.
-/

namespace COE010Invalid

theorem false_relu_is_identity_on_negatives :
    COE010Real.evalReal (.rectified .input) (-1 : ℝ) = (-1 : ℝ) := by
  rfl

end COE010Invalid
