import COE011Fixtures

/-!
Deliberately invalid seam: this certificate has an exact identity source
network and both output-affine claims are correct in their respective
cells, but the first ends at 0 and the second begins at 1. The gap
violates the original contiguous-cover requirements.

This false claim MUST be rejected by kernel reduction, not by a syntax
error, missing import, or an untrusted test runner's assertion.
-/

namespace COE011Invalid
open COEWireCheck

def gappedSplit : Cert :=
  { layers := [
      { weights := [[(1 : Rat)]], bias := [0], relu := false }]
    cells := [
      { left := none, right := some 0,
        output := [{ slope := 1, offset := 0 }] },
      { left := some 1, right := none,
        output := [{ slope := 1, offset := 0 }] }] }

theorem false_continuous_cover : verify gappedSplit = true := by
  decide +kernel

end COE011Invalid
