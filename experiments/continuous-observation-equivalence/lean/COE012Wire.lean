import COEWireCheck

/-!
COE-012: independently decode rational, activation and endpoint tokens
which arrive as plain strings from the certificate's original wire data.

The unverified Python envelope reader only transports raw string values and
array/object structure. In particular it does NOT supply or compute the
rational values, infinity sentinels, or activation Boolean flags accepted by
this parser. All arithmetic here takes place in exact Lean Rat.

Acceptance is a Boolean from the original kernel-checked verifier applied
to a decoded typed certificate. A separate Mathlib theorem connects this
acceptance directly to the all-real piecewise atlas interpretation.

NOT proved: an arbitrary external JSON text file is faithfully translated
into the corresponding WireCert string structure by the Python envelope.
-/

namespace COE012Wire
open COEWireCheck

/-- Accept only the canonical decimal printing of the parsed Int:
    rejects -0, +1, whitespace, leading zeros, and exotic numerals. -/
def parseIntToken (s : String) : Option Int := do
  let n ← s.toInt?
  if toString n == s then some n else none

/-- Exact rational wire grammar: canonical signed integer, or a
    reduced signed-integer/natural-positive-denominator fraction with
    denominator > 1. A ratio is computed by Lean, never supplied as an
    untrusted separate numerator/denominator arithmetic result. -/
def parseRatToken (s : String) : Option Rat :=
  match s.splitOn "/" with
  | [numerator] => do
      let n ← parseIntToken numerator
      some (n : Rat)
  | [numerator, denominator] => do
      let n ← parseIntToken numerator
      let d ← denominator.toNat?
      if d <= 1 || toString d != denominator ||
         n.natAbs.gcd d != 1 then
        none
      else
        some ((n : Rat) / (d : Rat))
  | _ => none

/-- Optional bounds are decided IN LEAN from the original sentinel
    token. Only the indicated direction of infinity is allowed. -/
def decodeLeft (s : String) : Option (Option Rat) :=
  if s == "-inf" then some none
  else (parseRatToken s).map some

def decodeRight (s : String) : Option (Option Rat) :=
  if s == "+inf" then some none
  else (parseRatToken s).map some

def decodeActivation (s : String) : Option Bool :=
  if s == "relu" then some true
  else if s == "linear" then some false
  else none

structure WireAffine where
  slope : String
  offset : String
  deriving Repr

structure WireLayer where
  weights : List (List String)
  bias : List String
  activation : String
  deriving Repr

structure WireCell where
  left : String
  right : String
  affines : List WireAffine
  deriving Repr

structure WireCert where
  layers : List WireLayer
  cells : List WireCell
  deriving Repr

def decodeAffine (a : WireAffine) : Option Affine := do
  let slope ← parseRatToken a.slope
  let offset ← parseRatToken a.offset
  some { slope := slope, offset := offset }

def decodeLayer (layer : WireLayer) : Option Layer := do
  let weights ← layer.weights.mapM (fun row => row.mapM parseRatToken)
  let bias ← layer.bias.mapM parseRatToken
  let relu ← decodeActivation layer.activation
  some { weights := weights, bias := bias, relu := relu }

def decodeCell (cell : WireCell) : Option Cell := do
  let left ← decodeLeft cell.left
  let right ← decodeRight cell.right
  let output ← cell.affines.mapM decodeAffine
  some { left := left, right := right, output := output }

def decodeCert (wire : WireCert) : Option Cert := do
  let layers ← wire.layers.mapM decodeLayer
  let cells ← wire.cells.mapM decodeCell
  some { layers := layers, cells := cells }

/-- Even a fully decoded wire claim is not admitted until the
    independent COEWireCheck Boolean verifier recomputes it. -/
def acceptWire (wire : WireCert) : Bool :=
  match decodeCert wire with
  | none => false
  | some cert => verify cert

/-- The accepted wire result contains an admitted TYPED certificate,
    not merely a successfully parsed rational array. -/
theorem acceptWire_implies_verified (wire : WireCert)
    (h : acceptWire wire = true) :
    ∃ cert : Cert, decodeCert wire = some cert ∧ verify cert = true := by
  unfold acceptWire at h
  cases hw : decodeCert wire with
  | none => simp [hw] at h
  | some cert =>
      exact ⟨cert, hw, by simpa [hw] using h⟩

/-- Exhaustive, exact positive token cases (including negative fraction). -/
example : parseRatToken "-3/2" = some ((-3 : Rat) / 2) := by decide +kernel
example : parseRatToken "0" = some (0 : Rat) := by decide +kernel
example : parseRatToken "3/7" = some ((3 : Rat) / 7) := by decide +kernel
example : parseRatToken "-12" = some (-12 : Rat) := by decide +kernel

/-- These are rejected by the decoder itself, not by untrusted Python. -/
example : parseRatToken "2/4" = none := by decide +kernel
example : parseRatToken "1/1" = none := by decide +kernel
example : parseRatToken "0/2" = none := by decide +kernel
example : parseRatToken "-0" = none := by decide +kernel
example : parseRatToken "01" = none := by decide +kernel
example : parseRatToken "1/0" = none := by decide +kernel
example : parseRatToken "1/-2" = none := by decide +kernel
example : parseRatToken "1/02" = none := by decide +kernel
example : parseRatToken "1/2/3" = none := by decide +kernel
example : parseRatToken "1e3" = none := by decide +kernel
example : parseRatToken "1.5" = none := by decide +kernel
example : parseRatToken "1);#eval 42" = none := by decide +kernel
example : decodeLeft "+inf" = none := by decide +kernel
example : decodeRight "-inf" = none := by decide +kernel
example : decodeActivation "sigmoid" = none := by decide +kernel

#print axioms COE012Wire.acceptWire_implies_verified

end COE012Wire
