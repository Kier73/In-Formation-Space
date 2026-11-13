import COE008Evaluation
import COE009Endpoint

/-!
COE-009: semantic meaning of accepted certificates at rational endpoints.

The direct numeric evaluator remains COE008Evaluation.evalNetwork.
We reuse its independently proved affine dot-product identities, and replace
the interior-only ReLU rule with COE009Endpoint.selectedAtClosed.
-/

namespace COE009Evaluation
open COEWireCheck COE008Evaluation COE009Endpoint

private theorem allRootGuardsClosed (cell : Cell) (as : List Affine)
    (p x : Rat) (hp : inside cell p = true)
    (hx : closedInside cell x = true)
    (hguard : as.all (rootExcluded cell) = true) :
    (as.map (fun a => if 0 < evaluateAt a p then a else zeroAffine)).map
        (fun a => evaluateAt a x) =
    (as.map (fun a =>
        if 0 < evaluateAt a x then evaluateAt a x else 0)) := by
  induction as with
  | nil => rfl
  | cons a rest ih =>
      simp only [List.all_cons, Bool.and_eq_true] at hguard
      have hbranch := selectedAtClosed cell a p x hguard.1 hp hx
      simp only [List.map_cons]
      rw [hbranch]
      exact congrArg (List.cons _) (ih hguard.2)

/-- A valid symbolic affine step yields the same numeric ReLU layer at
    all rational points of the *closed* cell, not just the interior. -/
theorem advanceClosedSound (cell : Cell) (state : Bool × List Affine)
    (layer : Layer) (x : Rat)
    (hp : inside cell (probe cell) = true)
    (hx : closedInside cell x = true)
    (hstep : (advance cell state layer).1 = true) :
    (advance cell state layer).2.map (fun a => evaluateAt a x) =
      evalLayer layer (state.2.map (fun a => evaluateAt a x)) := by
  let pre := List.zipWith (fun row bias => weighted row state.2 bias)
               layer.weights layer.bias
  have hpre := preactivationsAt layer state.2 x
  have hroot : (if layer.relu then pre.all (rootExcluded cell) else true) = true := by
    simp only [advance] at hstep
    grind
  cases hmode : layer.relu with
  | false =>
      simpa [advance, evalLayer, pre, hmode] using hpre
  | true =>
      have hguard : pre.all (rootExcluded cell) = true := by
        simpa [hmode] using hroot
      have hcorrect := allRootGuardsClosed cell pre (probe cell) x hp hx hguard
      calc
        (advance cell state layer).2.map (fun a => evaluateAt a x) =
          (pre.map (fun a =>
              if 0 < evaluateAt a (probe cell) then a else zeroAffine)).map
            (fun a => evaluateAt a x) := by
              simp [advance, pre, hmode]
        _ = pre.map (fun a =>
            if 0 < evaluateAt a x then evaluateAt a x else 0) := hcorrect
        _ = (pre.map (fun a => evaluateAt a x)).map
            (fun v => if 0 < v then v else 0) := by
              simp only [List.map_map]
              rfl
        _ = evalLayer layer (state.2.map (fun a => evaluateAt a x)) := by
              rw [hpre]
              simp [evalLayer, hmode]

/-- Successful affine propagation matches direct network evaluation
    throughout the cell's rational closure. -/
theorem foldClosedSound (cell : Cell) (layers : List Layer)
    (state : Bool × List Affine) (x : Rat)
    (hp : inside cell (probe cell) = true)
    (hx : closedInside cell x = true)
    (h : (layers.foldl (advance cell) state).1 = true) :
    (layers.foldl (advance cell) state).2.map
      (fun a => evaluateAt a x) =
    layers.foldl (fun values layer => evalLayer layer values)
      (state.2.map (fun a => evaluateAt a x)) := by
  induction layers generalizing state with
  | nil => rfl
  | cons layer rest ih =>
      simp only [List.foldl_cons] at h ⊢
      have hpfx : (advance cell state layer).1 = true :=
        foldSuccessPrefix cell rest (advance cell state layer) h
      rw [ih (advance cell state layer) h]
      rw [advanceClosedSound cell state layer x hp hx hpfx]

/-- Accepted output affine formulas agree with direct source evaluation
    at *all rational points in the closed cell*. -/
theorem verifiedCellClosedSound (layers : List Layer) (cell : Cell) (x : Rat)
    (hcell : cellVerified layers cell = true)
    (hx : closedInside cell x = true) :
    cell.output.map (fun a => evaluateAt a x) = evalNetwork layers x := by
  have hp : inside cell (probe cell) = true := by
    simp only [cellVerified, Bool.and_eq_true] at hcell
    grind
  have hflag : (layers.foldl (advance cell) (true, [⟨1, 0⟩])).1 = true := by
    simp only [cellVerified, Bool.and_eq_true] at hcell
    grind
  have hout : (layers.foldl (advance cell) (true, [⟨1, 0⟩])).2 =
      cell.output := by
    simp only [cellVerified, Bool.and_eq_true] at hcell
    grind
  have hnumeric := foldClosedSound cell layers (true, [⟨1, 0⟩]) x hp hx hflag
  have hinit : ([(⟨1, 0⟩ : Affine)]).map (fun a => evaluateAt a x) = [x] := by
    simp [evaluateAt]
    grind
  calc
    cell.output.map (fun a => evaluateAt a x) =
        (layers.foldl (advance cell) (true, [⟨1, 0⟩])).2.map
          (fun a => evaluateAt a x) := by rw [hout]
    _ = evalNetwork layers x := by
          simpa only [hinit, evalNetwork] using hnumeric

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

/-- Main universal COE-009 refinement: accepted certificates have correct
    network observations at any rational point in any certified CLOSED cell,
    including finite boundary cutpoints. -/
theorem verifiedCertificateClosedSound (cert : Cert) (cell : Cell) (x : Rat)
    (hverify : verify cert = true)
    (hmember : cell ∈ cert.cells)
    (hx : closedInside cell x = true) :
    cell.output.map (fun a => evaluateAt a x) =
      evalNetwork cert.layers x := by
  have hcells : cert.cells.all (cellVerified cert.layers) = true := by
    simp only [verify, Bool.and_eq_true] at hverify
    grind
  have hcell := allTrueMember (cellVerified cert.layers)
      cert.cells hcells cell hmember
  exact verifiedCellClosedSound cert.layers cell x hcell hx

#print axioms COE009Evaluation.advanceClosedSound
#print axioms COE009Evaluation.foldClosedSound
#print axioms COE009Evaluation.verifiedCertificateClosedSound

end COE009Evaluation
