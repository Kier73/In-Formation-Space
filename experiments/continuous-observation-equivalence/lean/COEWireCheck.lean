import COERationalRoot

/-!
COE-007: an independent, bounded exact-rational certificate checker in Lean.

GeneratedCertificateProofs.lean supplies only literal network/cell data.
This module checks network dimensions, full ordered rational interval
coverage, continuity of claimed output at every finite join, exact
symbolic affine propagation, and exclusion of every interior ReLU root.

Closed certificate facts are checked with Lean's by decide in generated proofs,
meaning their exact-rational Boolean calculation is kernel-reduced.
This module does not parse JSON itself, prove the translator correct, or
replace standalone Python/Go full-profile source/authenticity checks.
-/

namespace COEWireCheck

structure Affine where
  slope : Rat
  offset : Rat
  deriving Repr, DecidableEq

structure Layer where
  weights : List (List Rat)
  bias : List Rat
  relu : Bool
  deriving Repr

structure Cell where
  left : Option Rat
  right : Option Rat
  output : List Affine
  deriving Repr

structure Cert where
  layers : List Layer
  cells : List Cell
  deriving Repr

def at (a : Affine) (x : Rat) : Rat := a.slope * x + a.offset

def inside (c : Cell) (x : Rat) : Bool :=
  (match c.left with
   | none => true
   | some left => decide (left < x)) &&
  (match c.right with
   | none => true
   | some right => decide (x < right))

def intervalProper (c : Cell) : Bool :=
  match c.left, c.right with
  | some l, some r => decide (l < r)
  | _, _ => true

def probe (c : Cell) : Rat :=
  match c.left, c.right with
  | none, none => 0
  | none, some r => r - 1
  | some l, none => l + 1
  | some l, some r => (l + r) / 2

def zeroAffine : Affine := ⟨0, 0⟩

def weighted (row : List Rat) (prev : List Affine) (bias : Rat) : Affine :=
  (row.zip prev).foldl
    (fun acc pair =>
      ⟨acc.slope + pair.1 * pair.2.slope,
       acc.offset + pair.1 * pair.2.offset⟩)
    ⟨0, bias⟩

/-- The root equation is checked after calculating the root in Lean.
    No fractional root is accepted merely because the translator asserted it. -/
def rootExcluded (c : Cell) (pre : Affine) : Bool :=
  if pre.slope = 0 then true
  else
    let root := -pre.offset / pre.slope
    decide (at pre root = 0) && !(inside c root)

/-- The output affine law and root checks are recomputed from layer weights.
    The claimed output and the previous layer's active forms are not used
    to derive each other. -/
def advance (cell : Cell) (state : Bool × List Affine) (layer : Layer) :
    Bool × List Affine :=
  let previous := state.2
  let shape :=
    !layer.weights.isEmpty &&
    decide (layer.bias.length = layer.weights.length) &&
    layer.weights.all (fun row => decide (row.length = previous.length))
  let pres := List.zipWith (fun row bias => weighted row previous bias)
               layer.weights layer.bias
  let rootsOK := if layer.relu then pres.all (rootExcluded cell) else true
  let p := probe cell
  let next := if layer.relu
              then pres.map (fun a => if 0 < at a p then a else zeroAffine)
              else pres
  (state.1 && shape && rootsOK, next)

def cellVerified (layers : List Layer) (cell : Cell) : Bool :=
  let result := layers.foldl (advance cell) (true, [⟨1, 0⟩])
  result.1 &&
    !cell.output.isEmpty &&
    decide (result.2 = cell.output)

/-- Neighboring open cells must meet without a hole, overlap, or jump in
    the output projection. The actual network is continuous because it
    only composes affine transformations and ReLUs. -/
def joinVerified (first second : Cell) : Bool :=
  match first.right, second.left with
  | some x, some y =>
      decide (x = y) &&
      decide (first.output.map (fun a => at a x) =
              second.output.map (fun a => at a x))
  | _, _ => false

def coverVerified (cells : List Cell) : Bool :=
  match cells with
  | [] => false
  | first :: _ =>
      decide (first.left = none) &&
      (match cells.reverse with
       | last :: _ => decide (last.right = none)
       | [] => false) &&
      cells.all intervalProper &&
      (cells.zip (cells.drop 1)).all
        (fun pair => joinVerified pair.1 pair.2)

/-- Full bounded rational-certificate check; malformed dimensions and
    gaps fail closed. A generated closed theorem uses kernel reduction. -/
def verify (cert : Cert) : Bool :=
  !cert.layers.isEmpty &&
  coverVerified cert.cells &&
  cert.cells.all (cellVerified cert.layers)

end COEWireCheck
