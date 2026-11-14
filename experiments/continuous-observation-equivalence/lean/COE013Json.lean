import COE012Wire

/-!
COE-013: a standalone, bounded, structurally recursive parser for the
EXACT CANONICAL JSON BYTE ENVELOPE used by COE-002.

It consumes literal ASCII byte codes from the original file, validates
the complete field hierarchy and canonical ordering without delegating
JSON object/array structure to Python, and extracts COE012Wire.WireCert.
Numeric tokens are passed unchanged into COE-012's separately verified
exact rational decoder, then into the established verifier.

Scope:
* One deliberately restricted canonical ASCII JSON grammar for COE-002,
  not a claim to parse arbitrary JSON or escaped Unicode strings.
* SHA-256 fields must each contain 64 lowercase hex digits, but the SHA
  algorithm and the consistency of their values are not checked here.
  Independent Python/Go source and semantic hash checks still apply.
* Translating original file bytes into Nat literals is still an external
  source transport and must be independently compared to original hashes.
-/

namespace COE013Json
open COE012Wire

abbrev Bytes := List Nat
abbrev Reader (α : Type) := Bytes → Option (α × Bytes)

/-- Consume an exact sequence of literal ASCII bytes. -/
def expect : Bytes → Bytes → Option Bytes
  | [], rest => some rest
  | p :: ps, q :: qs =>
      if p == q then expect ps qs else none
  | _, _ => none

/-- Scan an unescaped canonical JSON token string. ASCII control bytes,
    quote-injection and backslash escape forms are excluded. Such escape
    forms are never emitted for COE-002's canonical token/schema strings. -/
private def quotedChars : Nat → Bytes → Bytes → Option (Bytes × Bytes)
  | 0, _, _ => none
  | _ + 1, [], _ => none
  | _ + 1, 34 :: rest, rev => some (rev.reverse, rest)
  | n + 1, c :: rest, rev =>
      if 32 ≤ c && c ≤ 126 && c != 92 then
        quotedChars n rest (c :: rev)
      else none

def quotedToken : Reader Bytes
  | 34 :: rest => quotedChars 128 rest []
  | _ => none

/-- A fuel bound makes even adversarial array nesting finite. -/
private def arrayItems {α : Type} (fuel : Nat) (read : Reader α)
    (input : Bytes) (acc : List α) : Option (List α × Bytes) :=
  match fuel with
  | 0 => none
  | n + 1 => do
      let (item, rest) ← read input
      match rest with
      | 44 :: tail => arrayItems n read tail (item :: acc)
      | 93 :: tail => some ((item :: acc).reverse, tail)
      | _ => none

def array {α : Type} (fuel : Nat) (read : Reader α) : Reader (List α)
  | 91 :: 93 :: rest => some ([], rest)
  | 91 :: rest => arrayItems fuel read rest []
  | _ => none

def affinePair : Reader WireAffine := fun input => do
  let rest ← expect [91] input
  let (slope, rest) ← quotedToken rest
  let rest ← expect [44] rest
  let (offset, rest) ← quotedToken rest
  let rest ← expect [93] rest
  some ({ slope := slope, offset := offset }, rest)

def cell : Reader WireCell := fun input => do
  let rest ← expect [123, 34, 97, 102, 102, 105, 110, 101, 115, 34, 58] input
  let (affines, rest) ← array 128 affinePair rest
  let rest ← expect [44, 34, 108, 101, 102, 116, 34, 58] rest
  let (left, rest) ← quotedToken rest
  let rest ← expect [44, 34, 114, 105, 103, 104, 116, 34, 58] rest
  let (right, rest) ← quotedToken rest
  let rest ← expect [125] rest
  some ({ left := left, right := right, affines := affines }, rest)

def row : Reader (List Bytes) := array 128 quotedToken

def layer : Reader WireLayer := fun input => do
  let rest ← expect [123, 34, 97, 99, 116, 105, 118, 97, 116, 105, 111, 110, 34, 58] input
  let (activation, rest) ← quotedToken rest
  let rest ← expect [44, 34, 98, 105, 97, 115, 34, 58] rest
  let (bias, rest) ← array 128 quotedToken rest
  let rest ← expect [44, 34, 119, 101, 105, 103, 104, 116, 115, 34, 58] rest
  let (weights, rest) ← array 128 row rest
  let rest ← expect [125] rest
  some ({ activation := activation, bias := bias, weights := weights }, rest)

/-- Parse a canonical 64-byte lowercase hex field without claiming to
    recalculate the cryptographic digest. -/
def isHexDigit (c : Nat) : Bool :=
  (48 ≤ c && c ≤ 57) || (97 ≤ c && c ≤ 102)

def isDigest (bs : Bytes) : Bool :=
  bs.length == 64 && bs.all isHexDigit

structure Envelope where
  wire : WireCert
  networkSHA : Bytes
  semanticAtlas : List WireCell
  semanticSHA : Bytes
  deriving Repr, DecidableEq

/-- Entire COE-002 canonical JSON field order. A misspelled key, extra
    key, wrong array nesting, duplicate, spacing or trailing garbage is
    not silently ignored. Only the complete expected shape can parse. -/
def document : Reader Envelope := fun input => do
  let rest ← expect [123, 34, 97, 116, 111, 109, 105, 99, 95, 99, 101, 108, 108, 115, 34, 58] input
  let (cells, rest) ← array 4096 cell rest
  let rest ← expect [44, 34, 110, 101, 116, 119, 111, 114, 107, 34, 58, 123, 34, 108, 97, 121, 101, 114, 115, 34, 58] rest
  let (layers, rest) ← array 64 layer rest
  let rest ← expect [125, 44, 34, 110, 101, 116, 119, 111, 114, 107, 95, 115, 104, 97, 50, 53, 54, 34, 58] rest
  let (networkSHA, rest) ← quotedToken rest
  if !isDigest networkSHA then none else
    let rest ← expect [44, 34, 115, 99, 104, 101, 109, 97, 34, 58, 34, 105, 110, 45, 102, 111, 114, 109, 97, 116, 105, 111, 110, 45, 115, 112, 97, 99, 101, 46, 99, 111, 101, 48, 48, 50, 46, 97, 99, 116, 105, 118, 97, 116, 105, 111, 110, 45, 99, 101, 108, 108, 45, 99, 101, 114, 116, 105, 102, 105, 99, 97, 116, 101, 47, 48, 46, 49, 34, 44, 34, 115, 101, 109, 97, 110, 116, 105, 99, 95, 97, 116, 108, 97, 115, 34, 58] rest
    let (semanticAtlas, rest) ← array 4096 cell rest
    let rest ← expect [44, 34, 115, 101, 109, 97, 110, 116, 105, 99, 95, 115, 104, 97, 50, 53, 54, 34, 58] rest
    let (semanticSHA, rest) ← quotedToken rest
    if !isDigest semanticSHA then none else
      let rest ← expect [125] rest
      some ({ wire := { layers := layers, cells := cells },
              networkSHA := networkSHA,
              semanticAtlas := semanticAtlas,
              semanticSHA := semanticSHA }, rest)

/-- A final single LF is obligatory and no trailing bytes are permitted. -/
def parseEnvelope (raw : Bytes) : Option Envelope := do
  let (envelope, remaining) ← document raw
  if remaining == [10] then some envelope else none

def acceptBytes (raw : Bytes) : Bool :=
  match parseEnvelope raw with
  | none => false
  | some env => acceptWire env.wire

/-- Positive admission proves original bytes were successfully parsed,
    and exact Lean decoding plus COEWireCheck accepted their meaning. -/
theorem acceptBytes_implies_verified (raw : Bytes)
    (h : acceptBytes raw = true) :
    ∃ (env : Envelope) (cert : COEWireCheck.Cert),
      parseEnvelope raw = some env ∧
      decodeCert env.wire = some cert ∧
      COEWireCheck.verify cert = true := by
  unfold acceptBytes at h
  cases hp : parseEnvelope raw with
  | none => simp [hp] at h
  | some env =>
      have hwire : acceptWire env.wire = true := by
        simpa [hp] using h
      obtain ⟨cert, hdecode, hverify⟩ :=
        acceptWire_implies_verified env.wire hwire
      exact ⟨env, cert, rfl, hdecode, hverify⟩

/-- Malformed envelope, unknown field, trailing LF and wrong digest
    grammar are checked by kernel reduction on small genuine byte arrays. -/
example : parseEnvelope [] = none := by decide +kernel
example : parseEnvelope [123, 34, 97, 116, 111, 109, 105, 99, 95, 99, 101, 108, 108, 115, 34, 58, 91, 93, 44, 34, 110, 101, 116, 119, 111, 114, 107, 34, 58, 123, 34, 108, 97, 121, 101, 114, 115, 34, 58, 91, 93, 125, 44, 34, 110, 101, 116, 119, 111, 114, 107, 95, 115, 104, 97, 50, 53, 54, 34, 58, 34, 120, 34, 125, 10] = none := by decide +kernel
example : parseEnvelope [123, 34, 97, 116, 111, 109, 105, 99, 95, 99, 101, 108, 108, 115, 34, 58, 91, 93, 44, 34, 97, 116, 111, 109, 105, 99, 95, 99, 101, 108, 108, 115, 34, 58, 91, 93, 125, 10] = none := by decide +kernel
example : parseEnvelope [123, 125, 10] = none := by decide +kernel
example : parseEnvelope [123, 34, 97, 116, 111, 109, 105, 99, 95, 99, 101, 108, 108, 115, 34, 58, 91, 93, 125] = none := by decide +kernel

#print axioms COE013Json.acceptBytes_implies_verified
end COE013Json
