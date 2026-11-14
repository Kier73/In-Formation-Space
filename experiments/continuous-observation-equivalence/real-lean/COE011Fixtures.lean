import COE011Coverage

/-!
COE-011 concrete controls for a two-cell identity network whose cells
share the exact rational endpoint 0. Exact certificate acceptance is
verified by kernel reduction; all-real meaning follows from the universal
theorem, not from numerical samples.
-/

namespace COE011Fixtures
open COEWireCheck COE011Coverage COE010Network COE010Real

def identitySplit : Cert :=
  { layers := [
      { weights := [[(1 : Rat)]], bias := [0], relu := false }]
    cells := [
      { left := none, right := some 0,
        output := [{ slope := 1, offset := 0 }] },
      { left := some 0, right := none,
        output := [{ slope := 1, offset := 0 }] }] }

/-- Both rational cell interiors, their shared cutpoint, output laws,
    and the total domain cover are checked from the typed certificate. -/
theorem identitySplitAccepted : verify identitySplit = true := by
  decide +kernel

/-- The actual first-matching-cell atlas realizes the source's
    continuous real interpretation at EVERY real coordinate. -/
theorem identitySplitReal (x : ℝ) :
    piecewiseReal identitySplit 0 x =
      evalReal (component identitySplit.layers 0) x :=
  piecewiseReal_eq_network identitySplit 0 x identitySplitAccepted

theorem identitySplitContinuous :
    Continuous (piecewiseReal identitySplit 0) :=
  continuous_piecewiseReal identitySplit 0 identitySplitAccepted

#print axioms COE011Fixtures.identitySplitAccepted
#print axioms COE011Fixtures.identitySplitReal
#print axioms COE011Fixtures.identitySplitContinuous

end COE011Fixtures
