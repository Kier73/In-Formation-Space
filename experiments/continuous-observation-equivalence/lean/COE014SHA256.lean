import COE013Json

/-!
COE-014: a pure Lean SHA-256 implementation over the EXACT original byte lists.

This is a separate mathematical implementation of the SHA-256 compression
and padding algorithm using 32-bit modular words, independently compared
against FIPS 180-4/NIST and Python/Go standard-library test vectors.
Its equations are readable Lean definitions; there is no foreign
cryptographic hash call, no native_decide, and no external proof axiom.

Important distinction: testing a pure Lean algorithm against authoritative
reference vectors is not itself a formal proof of cryptographic security or
a proof that SHA-256 is collision-resistant. A pinned digest is an integrity
claim under an independently trusted manifest, not a source signature.
-/

namespace COE014SHA256
open COE013Json

abbrev ByteList := List Nat
abbrev Word := UInt32

private def roundK : Array Word := #[0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]

private def initial : Array Word := #[
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
  0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]

def rightRotate (x : Word) (n : Nat) : Word :=
  (x >>> UInt32.ofNat n) ||| (x <<< UInt32.ofNat (32 - n))

def rightShift (x : Word) (n : Nat) : Word :=
  x >>> UInt32.ofNat n

private def bigSigma0 (x : Word) : Word :=
  rightRotate x 2 ^^^ rightRotate x 13 ^^^ rightRotate x 22

private def bigSigma1 (x : Word) : Word :=
  rightRotate x 6 ^^^ rightRotate x 11 ^^^ rightRotate x 25

private def smallSigma0 (x : Word) : Word :=
  rightRotate x 7 ^^^ rightRotate x 18 ^^^ rightShift x 3

private def smallSigma1 (x : Word) : Word :=
  rightRotate x 17 ^^^ rightRotate x 19 ^^^ rightShift x 10

private def choose (x y z : Word) : Word :=
  (x &&& y) ^^^ ((~~~x) &&& z)

private def majority (x y z : Word) : Word :=
  (x &&& y) ^^^ (x &&& z) ^^^ (y &&& z)

private def wordFrom (bytes : Array Nat) (offset : Nat) : Word :=
  (UInt32.ofNat (bytes[offset]?.getD 0) <<< 24) |||
  (UInt32.ofNat (bytes[offset+1]?.getD 0) <<< 16) |||
  (UInt32.ofNat (bytes[offset+2]?.getD 0) <<< 8) |||
   UInt32.ofNat (bytes[offset+3]?.getD 0)

/-- SHA-256, FIPS 180-4 section 6.2.2: 16 original 32-bit words,
then 48 schedule-extension words, followed by 64 compression rounds. -/
private def compress (state : Array Word) (bytes : Array Nat)
    (start : Nat) : Array Word := Id.run do
  let mut schedule : Array Word := #[]
  for i in [:16] do
    schedule := schedule.push (wordFrom bytes (start + i * 4))
  for i in [16:64] do
    let t := smallSigma1 (schedule[i-2]!) + schedule[i-7]! +
      smallSigma0 (schedule[i-15]!) + schedule[i-16]!
    schedule := schedule.push t
  let mut a := state[0]!
  let mut b := state[1]!
  let mut c := state[2]!
  let mut d := state[3]!
  let mut e := state[4]!
  let mut f := state[5]!
  let mut g := state[6]!
  let mut h := state[7]!
  for i in [:64] do
    let t1 := h + bigSigma1 e + choose e f g + roundK[i]! + schedule[i]!
    let t2 := bigSigma0 a + majority a b c
    h := g
    g := f
    f := e
    e := d + t1
    d := c
    c := b
    b := a
    a := t1 + t2
  return #[
    state[0]! + a, state[1]! + b, state[2]! + c, state[3]! + d,
    state[4]! + e, state[5]! + f, state[6]! + g, state[7]! + h]

private def lengthByte (bitLength : Nat) (i : Nat) : Nat :=
  (bitLength / (256 ^ (7-i))) % 256

/-- Standard SHA-256 Merkle-Damgård padding, with the required 64-bit
big-endian message length; reject non-byte input and overlong bit counts. -/
def pad (bytes : ByteList) : Option (Array Nat) := do
  if !(bytes.all (fun n => n < 256)) || bytes.length >= 2305843009213693952 then
    none
  else
    let afterMarker := bytes ++ [128]
    let count := (56 + 64 - (afterMarker.length % 64)) % 64
    let padded := afterMarker ++ List.replicate count 0 ++
      (List.range 8).map (lengthByte (bytes.length * 8))
    some padded.toArray

private def wordBytes (w : Word) : List Nat :=
  [w.toNat / 16777216 % 256, w.toNat / 65536 % 256,
   w.toNat / 256 % 256, w.toNat % 256]

/-- SHA-256 digest, as 32 original binary octets, over a List Nat. -/
def digest (bytes : ByteList) : Option ByteList := do
  let padded ← pad bytes
  let hashes := Id.run do
    let mut state := initial
    for i in [:padded.size / 64] do
      state := compress state padded (i * 64)
    return state
  some (hashes.toList.flatMap wordBytes)

/-- Canonical lowercase ASCII SHA-256 hex representation. -/
private def nibble (n : Nat) : Nat :=
  if n < 10 then n + 48 else n - 10 + 97

def hexEncode (bytes : ByteList) : ByteList :=
  bytes.flatMap (fun b => [nibble (b / 16), nibble (b % 16)])

def digestHex (bytes : ByteList) : Option ByteList :=
  (digest bytes).map hexEncode

/-- SHA-256 rejects raw input that is not a list of valid octets. -/
example : pad [256] = none := by decide +kernel
example : pad [0, 255] |>.isSome = true := by decide +kernel
example : (pad []).map Array.size = some 64 := by decide +kernel
example : (pad (List.replicate 56 0)).map Array.size = some 128 := by decide +kernel
example : hexEncode [0, 15, 16, 255] = [48,48,48,102,49,48,102,102] := by
  decide +kernel

end COE014SHA256
