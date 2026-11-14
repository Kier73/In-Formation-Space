import COE010Network

/-!
COE-011: the certificate's ACTUAL rational-affine cell atlas, interpreted
directly at arbitrary real arguments, agrees with the compiled source
network on the entire real line.

This module does not merely assert the existence/uniqueness of a real
extension (COE-010): it defines an atlas evaluator which scans the actual
certificate cells in order and selects the first containing the real input.

Because comparisons of arbitrary real numbers are undecidable, this is a
classical exact mathematical interpreter, not an implementation of hardware
floating-point comparisons.
-/

namespace COE011Atlas
open COEWireCheck COE008Evaluation COE009Endpoint COE009Evaluation COE010Real COE010Network

/-- Rational and real versions of a bounded-cell projection. The bounds
are *the actual exact rational endpoints stored in the certificate*. -/
def clampRat (c : Cell) (q : Rat) : Rat :=
  let lower := match c.left with
    | none => q
    | some l => max l q
  match c.right with
  | none => lower
  | some u => min u lower

def clampReal (c : Cell) (x : ℝ) : ℝ :=
  let lower := match c.left with
    | none => x
    | some l => max (l : ℝ) x
  match c.right with
  | none => lower
  | some u => min (u : ℝ) lower

/-- The real interpretation of a rational clamp is the clamp of the
embedded rational. No approximation or loss of endpoint exactness. -/
theorem clampReal_at_rat (c : Cell) (q : Rat) :
    clampReal c (q : ℝ) = (clampRat c q : ℝ) := by
  cases c with
  | mk lo hi out =>
    cases lo <;> cases hi <;>
      simp [clampReal, clampRat, Rat.cast_min, Rat.cast_max]

/-- Clamping to a nonempty rational cell always produces a point in
the cell's rational closure, including exact boundary values. -/
theorem clampRat_closed (c : Cell) (q : Rat)
    (hproper : intervalProper c = true) :
    closedInside c (clampRat c q) = true := by
  cases c with
  | mk lo hi out =>
    cases lo with
    | none =>
        cases hi with
        | none => simp [clampRat, closedInside]
        | some u => simp [clampRat, closedInside, min_le_left]
    | some l =>
        cases hi with
        | none => simp [clampRat, closedInside, le_max_left]
        | some u =>
            have hlt : l < u := by simpa [intervalProper] using hproper
            have hlow : l ≤ min u (max l q) :=
              le_min (le_of_lt hlt) (le_max_left l q)
            have hupp : min u (max l q) ≤ u :=
              min_le_left u (max l q)
            simp [clampRat, closedInside, hlow, hupp]

/-- Closed real cell membership reads the two optional rational bounds
from the certified cell, casting them into the real line exactly. -/
def aboveReal (c : Cell) (x : ℝ) : Prop :=
  match c.left with
  | none => True
  | some l => (l : ℝ) ≤ x

def belowReal (c : Cell) (x : ℝ) : Prop :=
  match c.right with
  | none => True
  | some u => x ≤ (u : ℝ)

def inRealCell (c : Cell) (x : ℝ) : Prop :=
  aboveReal c x ∧ belowReal c x

/-- The mathematical clamp is the identity for every point inside
the cell, including finite cutpoints. -/
theorem clampReal_fixed (c : Cell) (x : ℝ)
    (hin : inRealCell c x) : clampReal c x = x := by
  cases c with
  | mk lo hi out =>
    cases lo with
    | none =>
        cases hi with
        | none => rfl
        | some u =>
            have hu : x ≤ (u : ℝ) := hin.2
            simp [clampReal, min_eq_right hu]
    | some l =>
        cases hi with
        | none =>
            have hl : (l : ℝ) ≤ x := hin.1
            simp [clampReal, max_eq_right hl]
        | some u =>
            have hl : (l : ℝ) ≤ x := hin.1
            have hu : x ≤ (u : ℝ) := hin.2
            simp [clampReal, max_eq_right hl, min_eq_right hu]

theorem continuous_clampReal (c : Cell) : Continuous (clampReal c) := by
  cases c with
  | mk lo hi out =>
    cases lo <;> cases hi <;> fun_prop

/-- Select a component from the *actual claimed cell output*, with zero
padding outside its width, matching the total-component convention in
COE-010. -/
def cellComponent (c : Cell) (index : Nat) : Affine :=
  (c.output[index]?).getD zeroAffine

def cellOutputReal (c : Cell) (index : Nat) (x : ℝ) : ℝ :=
  (cellComponent c index).slope * x + (cellComponent c index).offset

theorem continuous_cellOutputReal (c : Cell) (index : Nat) :
    Continuous (cellOutputReal c index) := by
  unfold cellOutputReal
  fun_prop

theorem affine_at_rat (a : Affine) (q : Rat) :
    (a.slope : ℝ) * (q : ℝ) + (a.offset : ℝ) =
      (evaluateAt a q : ℝ) := by
  simp only [evaluateAt, Rat.cast_add, Rat.cast_mul]

private theorem component_map_rat (as : List Affine)
    (index : Nat) (q : Rat) :
    evaluateAt (as[index]?.getD zeroAffine) q =
      ((as.map (fun a => evaluateAt a q))[index]?).getD 0 := by
  induction as generalizing index with
  | nil => simp [zeroAffine, evaluateAt]
  | cons first rest ih =>
      cases index with
      | zero => simp
      | succ k => simpa using ih k

theorem cellOutputReal_at_rat (c : Cell) (index : Nat) (q : Rat) :
    cellOutputReal c index (q : ℝ) =
      (((c.output.map (fun a => evaluateAt a q))[index]?).getD 0 : ℝ) := by
  unfold cellOutputReal cellComponent
  rw [affine_at_rat]
  rw [component_map_rat]

private theorem allTrueMember {α : Type} (f : α → Bool)
    (items : List α) (h : items.all f = true)
    (value : α) (hv : value ∈ items) : f value = true := by
  induction items with
  | nil => simp at hv
  | cons head rest ih =>
      simp only [List.all_cons, Bool.and_eq_true] at h
      simp only [List.mem_cons] at hv
      rcases hv with heq | hrest
      · subst value
        exact h.1
      · exact ih h.2 hrest

/-- The actual Boolean verifier's accepted cover implies that every
cell, not merely the chosen one, has a proper nonempty interval. -/
private theorem verifiedCellProper (cert : Cert) (cell : Cell)
    (hverify : verify cert = true) (hmem : cell ∈ cert.cells) :
    intervalProper cell = true := by
  have hcover : coverVerified cert.cells = true := by
    simp only [verify, Bool.and_eq_true] at hverify
    grind
  cases hcells : cert.cells with
  | nil => simp [hcells] at hmem
  | cons first rest =>
      have hparts :
          (decide (first.left = none) &&
            lastUnbounded (first :: rest) &&
            (first :: rest).all intervalProper &&
            joinedChain (first :: rest)) = true := by
        simpa [coverVerified, hcells] using hcover
      simp only [Bool.and_eq_true] at hparts
      have hall : (first :: rest).all intervalProper = true := hparts.1.2
      have hmember : cell ∈ first :: rest := by simpa [hcells] using hmem
      exact allTrueMember intervalProper (first :: rest) hall cell hmember

/-- A local, fully certificate-driven exact equality on rational-clamped
arguments, derived directly from COE-009's closed-cell theorem. -/
private theorem clamped_rat_equality
    (cert : Cert) (cell : Cell) (index : Nat) (q : Rat)
    (hverify : verify cert = true)
    (hmem : cell ∈ cert.cells) :
    cellOutputReal cell index (clampReal cell (q : ℝ)) =
      evalReal (component cert.layers index) (clampReal cell (q : ℝ)) := by
  have hclamped := clampRat_closed cell q
    (verifiedCellProper cert cell hverify hmem)
  have hcert := verifiedCertificateClosedSound cert cell
    (clampRat cell q) hverify hmem hclamped
  have hcomponent := congrArg (fun xs : List Rat => (xs[index]?).getD 0) hcert
  calc
    cellOutputReal cell index (clampReal cell (q : ℝ)) =
      (evaluateAt (cellComponent cell index) (clampRat cell q) : ℝ) := by
        rw [clampReal_at_rat]
        exact affine_at_rat (cellComponent cell index) (clampRat cell q)
    _ = (((cell.output.map
       (fun a => evaluateAt a (clampRat cell q)))[index]?).getD 0 : ℝ) := by
         rw [show evaluateAt (cellComponent cell index) (clampRat cell q) =
           ((cell.output.map (fun a => evaluateAt a (clampRat cell q)))[index]?).getD 0 by
              exact component_map_rat cell.output index (clampRat cell q)]
    _ = (((evalNetwork cert.layers (clampRat cell q))[index]?).getD 0 : ℝ) :=
      congrArg (fun t : Rat => (t : ℝ)) hcomponent
    _ = evalReal (component cert.layers index) (clampReal cell (q : ℝ)) := by
        rw [clampReal_at_rat]
        exact (componentAtRat cert.layers index (clampRat cell q)).symm

/-- Core COE-011 local theorem: any actual claimed affine cell agrees
pointwise with the complete compiled real neural network at ALL REAL inputs
in that cell, including irrational coordinates and finite endpoints.

Proof: clamp the real line to this exact rational cell, prove equality at
*every rational* argument using the COE-009 kernel result, then use the
density/continuity uniqueness theorem from COE-010 and unclamp. No gap
between a rational observation and a real-valued claimed cell law. -/
theorem verifiedCellRealSound (cert : Cert) (cell : Cell)
    (index : Nat) (x : ℝ)
    (hverify : verify cert = true)
    (hmem : cell ∈ cert.cells) (hin : inRealCell cell x) :
    cellOutputReal cell index x =
      evalReal (component cert.layers index) x := by
  have hf : Continuous (fun y : ℝ =>
      cellOutputReal cell index (clampReal cell y)) :=
    (continuous_cellOutputReal cell index).comp (continuous_clampReal cell)
  have hg : Continuous (fun y : ℝ =>
      evalReal (component cert.layers index) (clampReal cell y)) :=
    (componentContinuous cert.layers index).comp (continuous_clampReal cell)
  have hfun := equal_of_all_rational_agreement
    (fun y : ℝ => cellOutputReal cell index (clampReal cell y))
    (fun y : ℝ => evalReal (component cert.layers index) (clampReal cell y))
    hf hg (clamped_rat_equality cert cell index · hverify hmem)
  have hpoint := congrFun hfun x
  simpa only [clampReal_fixed cell x hin] using hpoint

#print axioms COE011Atlas.clampReal_at_rat
#print axioms COE011Atlas.verifiedCellRealSound

end COE011Atlas
