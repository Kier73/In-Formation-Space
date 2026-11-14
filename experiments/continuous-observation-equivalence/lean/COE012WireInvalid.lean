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
      { weights := [["-6/4"]], bias := ["0"], activation := "linear" }]
    cells := [
      { left := "-inf", right := "+inf",
        affines := [{ slope := "-3/2", offset := "0" }] }] }

theorem false_unreduced_admission : acceptWire unreduced = true := by
  decide +kernel

end COE012WireInvalid
