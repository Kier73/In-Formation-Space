import COEWireCheck

/-!
COE-012: the exact ASCII BYTES of original rational/sentinel/activation
tokens are independently decoded inside Lean. This deliberately avoids
Lean 4.24 String.splitOn and String.toInt?, whose operations are not
all kernel-reducible.

The external JSON envelope and extraction of ASCII token bytes remain
unverified Python. All numeric parsing, canonicalization, reduction,
signed fraction division and certificate mathematical admission happen
in reducible Lean functions, with by decide +kernel proof obligations.
-/

namespace COE012Wire
open COEWireCheck

abbrev Token := List Nat

/-- Parse canonical ASCII 0 or a nonempty decimal with no leading zeros.
ASCII '0' = 48, '1' = 49, '9' = 57. -/
def decimalDigit (c : Nat) : Option Nat :=
  if 48 ≤ c && c ≤ 57 then some (c - 48) else none

private def parseDigits (rest : Token) (acc : Nat) : Option Nat :=
  match rest with
  | [] => some acc
  | c :: cs => do
      let d ← decimalDigit c
      parseDigits cs (acc * 10 + d)

def parseUnsigned : Token → Option Nat
  | [48] => some 0
  | c :: cs =>
      if 49 ≤ c && c ≤ 57 then parseDigits cs (c - 48) else none
  | [] => none

def parseSigned : Token → Option Int
  | 45 :: xs => do
      let n ← parseUnsigned xs
      if n == 0 then none else some (-(Int.ofNat n))
  | xs => do
      let n ← parseUnsigned xs
      some (Int.ofNat n)

/-- Split raw ASCII on the slash byte, without any String runtime
operation. Lists of Nat and all recursive functions reduce in the
Lean kernel. -/
def splitSlash (bytes : Token) : List Token :=
  let rec go (remaining current : Token) (groups : List Token) : List Token :=
    match remaining with
    | [] => (current.reverse :: groups).reverse
    | 47 :: tail => go tail [] (current.reverse :: groups)
    | c :: tail => go tail (c :: current) groups
  go bytes [] []

/-- Accept exactly canonical integers, or reduced fractions with a
signed numerator and a positive non-unit denominator; reject -0 and
all leading-zero and non-ASCII spellings. -/
def parseRatToken (bytes : Token) : Option Rat :=
  match splitSlash bytes with
  | [numerator] => do
      let n ← parseSigned numerator
      some (n : Rat)
  | [numerator, denominator] => do
      let n ← parseSigned numerator
      let d ← parseUnsigned denominator
      if d ≤ 1 || n.natAbs.gcd d != 1 then none
      else some ((n : Rat) / (d : Rat))
  | _ => none

def decodeLeft (bytes : Token) : Option (Option Rat) :=
  if bytes == [45, 105, 110, 102] then some none
  else (parseRatToken bytes).map some

def decodeRight (bytes : Token) : Option (Option Rat) :=
  if bytes == [43, 105, 110, 102] then some none
  else (parseRatToken bytes).map some

def decodeActivation (bytes : Token) : Option Bool :=
  if bytes == [114, 101, 108, 117] then some true
  else if bytes == [108, 105, 110, 101, 97, 114] then some false
  else none

structure WireAffine where
  slope : Token
  offset : Token
  deriving Repr, DecidableEq

structure WireLayer where
  weights : List (List Token)
  bias : List Token
  activation : Token
  deriving Repr, DecidableEq

structure WireCell where
  left : Token
  right : Token
  affines : List WireAffine
  deriving Repr, DecidableEq

structure WireCert where
  layers : List WireLayer
  cells : List WireCell
  deriving Repr, DecidableEq

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

def acceptWire (wire : WireCert) : Bool :=
  match decodeCert wire with
  | none => false
  | some cert => verify cert

theorem acceptWire_implies_verified (wire : WireCert)
    (h : acceptWire wire = true) :
    ∃ cert : Cert, decodeCert wire = some cert ∧ verify cert = true := by
  unfold acceptWire at h
  cases hdecode : decodeCert wire with
  | none => simp [hdecode] at h
  | some cert =>
      refine ⟨cert, ?_, ?_⟩
      · rfl
      · simpa [hdecode] using h

/-- Positive exact ASCII token examples, including negative rationals. -/
example : parseRatToken [45, 51, 47, 50] =
    some ((-3 : Rat) / 2) := by decide +kernel
example : parseRatToken [48] = some (0 : Rat) := by decide +kernel
example : parseRatToken [51, 47, 55] =
    some ((3 : Rat) / 7) := by decide +kernel
example : parseRatToken [45, 49, 50] = some (-12 : Rat) := by decide +kernel

/-- Negative test controls genuinely reduced by the Lean kernel. -/
example : parseRatToken [50, 47, 52] = none := by decide +kernel
example : parseRatToken [49, 47, 49] = none := by decide +kernel
example : parseRatToken [48, 47, 50] = none := by decide +kernel
example : parseRatToken [45, 48] = none := by decide +kernel
example : parseRatToken [48, 49] = none := by decide +kernel
example : parseRatToken [49, 47, 48] = none := by decide +kernel
example : parseRatToken [49, 47, 45, 50] = none := by decide +kernel
example : parseRatToken [49, 47, 48, 50] = none := by decide +kernel
example : parseRatToken [49, 47, 50, 47, 51] = none := by decide +kernel
example : parseRatToken [49, 101, 51] = none := by decide +kernel
example : parseRatToken [49, 46, 53] = none := by decide +kernel
example : parseRatToken [49, 41, 59, 35] = none := by decide +kernel
example : decodeLeft [43, 105, 110, 102] = none := by decide +kernel
example : decodeRight [45, 105, 110, 102] = none := by decide +kernel
example : decodeActivation [115, 105, 103, 109, 111, 105, 100] =
    none := by decide +kernel

/-- A nontrivial exact rational line, expressed entirely as raw ASCII
source token bytes before Lean decodes its rational values. -/
def rationalLineWire : WireCert :=
  { layers := [
      { weights := [[[45, 51, 47, 50]]], bias := [[48]],
        activation := [108, 105, 110, 101, 97, 114] }]
    cells := [
      { left := [45, 105, 110, 102], right := [43, 105, 110, 102],
        affines := [
          { slope := [45, 51, 47, 50], offset := [48] }] }] }

theorem rationalLineWireAccepted : acceptWire rationalLineWire = true := by
  decide +kernel

#print axioms COE012Wire.rationalLineWireAccepted
#print axioms COE012Wire.acceptWire_implies_verified

end COE012Wire
