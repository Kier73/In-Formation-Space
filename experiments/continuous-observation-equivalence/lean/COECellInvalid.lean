import COECellSoundness

/-!
Deliberately false negative control: if this compiles, the CI proof
gate is not enforcing Lean kernel rejection.
-/
namespace COECellInvalid

theorem false_claim : False := by
  exact False.elim

end COECellInvalid
