import COE012Wire

/-!
Deliberately false wire admission. The incoming signed fraction is not in
lowest terms, even though its mathematical value would be -3/2. The
canonical wire parser must reject it without accepting a separately
supplied typed rational literal.
-/

namespace COE012WireInvalid
open COE012Wire

def unreduced : WireCert :=
  { layers := [
      { weights := [[[45, 54, 47, 52]]], bias := [[48]], activation := [108, 105, 110, 101, 97, 114] }]
    cells := [
      { left := [45, 105, 110, 102], right := [43, 105, 110, 102],
        affines := [{ slope := [45, 51, 47, 50], offset := [48] }] }] }

theorem false_unreduced_admission : acceptWire unreduced = true := by
  decide +kernel

end COE012WireInvalid
