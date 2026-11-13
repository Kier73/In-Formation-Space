import COE008Soundness

/-!
COE-008: semantic refinement from the accepted symbolic activation-cell
certificate to an independently defined, direct pointwise Rat evaluator.

The source evaluator takes the input coordinate, evaluates every weight row,
then applies ReLU. It uses no activation-cell data or selected symbolic atlas.
-/
namespace COE008Evaluation
open COEWireCheck COE008Soundness

/-- A direct numeric row dot product, independent of affine cell propagation. -/
def evalRow (row : List Rat) (input : List Rat) (bias : Rat) : Rat :=
  (row.zip input).foldl (fun value pair => value + pair.1 * pair.2) bias

/-- A pointwise layer interpreter independent of any certificate's cells. -/
def evalLayer (layer : Layer) (input : List Rat) : List Rat :=
  let pres := List.zipWith (fun row bias => evalRow row input bias)
    layer.weights layer.bias
  if layer.relu then pres.map (fun value => if 0 < value then value else 0)
  else pres

/-- Pointwise evaluation of the original network at an arbitrary rational x. -/
def evalNetwork (layers : List Layer) (x : Rat) : List Rat :=
  layers.foldl (fun values layer => evalLayer layer values) [x]

private def addAffine (acc : Affine) (p : Rat × Affine) : Affine :=
  ⟨acc.slope + p.1 * p.2.slope, acc.offset + p.1 * p.2.offset⟩

private theorem addAffineAt (acc : Affine) (p : Rat × Affine) (x : Rat) :
    evaluateAt (addAffine acc p) x =
      evaluateAt acc x + p.1 * evaluateAt p.2 x := by
  simp only [addAffine, evaluateAt]
  grind

private theorem affineFoldAt (pairs : List (Rat × Affine))
    (acc : Affine) (x : Rat) :
    evaluateAt (pairs.foldl addAffine acc) x =
      pairs.foldl (fun value pair => value + pair.1 * evaluateAt pair.2 x)
        (evaluateAt acc x) := by
  induction pairs generalizing acc with
  | nil => rfl
  | cons pair rest ih =>
      simp only [List.foldl_cons]
      rw [ih]
      rw [addAffineAt]

private theorem zipMap (row : List Rat) (prev : List Affine) (x : Rat) :
    row.zip (prev.map (fun a => evaluateAt a x)) =
    (row.zip prev).map (fun p => (p.1, evaluateAt p.2 x)) := by
  induction row generalizing prev with
  | nil => simp
  | cons head tail ih =>
      cases prev with
      | nil => simp
      | cons value values =>
          simp [ih]

/-- Every weighted symbolic affine preactivation evaluates to the same
    rational number as the direct row dot product at that coordinate. -/
theorem weightedAt (row : List Rat) (prev : List Affine)
    (bias x : Rat) :
    evaluateAt (weighted row prev bias) x =
      evalRow row (prev.map (fun a => evaluateAt a x)) bias := by
  unfold weighted evalRow
  change evaluateAt ((row.zip prev).foldl addAffine ⟨0, bias⟩) x = _
  rw [affineFoldAt]
  rw [zipMap]
  simp only [List.foldl_map]
  have hz : (0 : Rat) * x + bias = bias := by grind
  simp only [evaluateAt]
  rw [hz]

private theorem preactivationsAt (layer : Layer) (prev : List Affine)
    (x : Rat) :
    (List.zipWith (fun row bias => weighted row prev bias)
      layer.weights layer.bias).map (fun a => evaluateAt a x) =
    List.zipWith (fun row bias =>
      evalRow row (prev.map (fun a => evaluateAt a x)) bias)
      layer.weights layer.bias := by
  cases layer with
  | mk weights bias relu =>
      induction weights generalizing bias with
      | nil => cases bias <;> rfl
      | cons row rows ih =>
          cases bias with
          | nil => rfl
          | cons b bs =>
              simp [List.zipWith, weightedAt, ih]

private theorem allRootGuardsSound (cell : Cell) (as : List Affine)
    (p x : Rat) (hp : inside cell p = true)
    (hx : inside cell x = true)
    (hguard : as.all (rootExcluded cell) = true) :
    (as.map (fun a => if 0 < evaluateAt a p then a else zeroAffine)).map
       (fun a => evaluateAt a x) =
    (as.map (fun a =>
       if 0 < evaluateAt a x then evaluateAt a x else 0)) := by
  induction as with
  | nil => rfl
  | cons a rest ih =>
      simp only [List.all_cons, Bool.and_eq_true] at hguard
      have hstable := root_guard_implies_sign_stable cell a p x hguard.1 hp hx
      have hbranch :
          evaluateAt (if 0 < evaluateAt a p then a else zeroAffine) x =
          (if 0 < evaluateAt a x then evaluateAt a x else 0) := by
        by_cases hpos : 0 < evaluateAt a p
        · by_cases hxpos : 0 < evaluateAt a x
          · simp only [if_pos hpos, if_pos hxpos]
          · have hf : False := by simpa [hpos, hxpos] using hstable
            exact False.elim hf
        · by_cases hxpos : 0 < evaluateAt a x
          · have hf : False := by simpa [hpos, hxpos] using hstable
            exact False.elim hf
          · simp only [if_neg hpos, if_neg hxpos]
            simp [zeroAffine, evaluateAt]
            grind
      simp only [List.map_cons]
      rw [hbranch]
      exact congrArg (List.cons _) (ih hguard.2)

/-- An accepted propagation step realizes the same pointwise numeric layer
    as the direct evaluator, at each rational point in that open cell. -/
theorem advanceSound (cell : Cell) (state : Bool × List Affine)
    (layer : Layer) (x : Rat)
    (hp : inside cell (probe cell) = true)
    (hx : inside cell x = true)
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
      have hcorrect := allRootGuardsSound cell pre (probe cell) x hp hx hguard
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

/-- Because every step can only preserve or clear the accumulated validity
    flag, a successful fold entails success of every prefix. -/
private theorem foldSuccessPrefix (cell : Cell)
    (layers : List Layer) (state : Bool × List Affine)
    (h : (layers.foldl (advance cell) state).1 = true) :
    state.1 = true := by
  induction layers generalizing state with
  | nil => simpa using h
  | cons layer rest ih =>
      simp only [List.foldl_cons] at h
      have hp := ih (advance cell state layer) h
      simp [advance, Bool.and_eq_true] at hp
      exact hp.1.1

/-- All symbolic affine expressions across a successful network propagation
    agree pointwise with direct numeric evaluation of the same source layers. -/
theorem foldSound (cell : Cell) (layers : List Layer)
    (state : Bool × List Affine) (x : Rat)
    (hp : inside cell (probe cell) = true)
    (hx : inside cell x = true)
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
      rw [advanceSound cell state layer x hp hx hpfx]


/-- An accepted certificate cell computes the same pointwise observation
    as the source network for *every rational input in its open interval*.
    Its numerical weights are evaluated by evalNetwork, not by the symbolic
    certificate evaluator. -/
theorem verifiedCellSound (layers : List Layer) (cell : Cell) (x : Rat)
    (hcell : cellVerified layers cell = true)
    (hx : inside cell x = true) :
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
  have hnumeric := foldSound cell layers (true, [⟨1, 0⟩]) x hp hx hflag
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

/-- This is the direct COE-008 refinement statement: an accepted
    COEWireCheck.verify certificate implies its declared affine observation
    agrees with direct network evaluation at *every rational interior point
    of every admitted activation cell*. The hypotheses are the verifier's
    Boolean result and membership, not an independent soundness assumption. -/
theorem verifiedCertificateSound (cert : Cert) (cell : Cell) (x : Rat)
    (hverify : verify cert = true)
    (hmember : cell ∈ cert.cells)
    (hx : inside cell x = true) :
    cell.output.map (fun a => evaluateAt a x) =
      evalNetwork cert.layers x := by
  have hcells : cert.cells.all (cellVerified cert.layers) = true := by
    simp only [verify, Bool.and_eq_true] at hverify
    grind
  have hcell := allTrueMember (cellVerified cert.layers)
      cert.cells hcells cell hmember
  exact verifiedCellSound cert.layers cell x hcell hx

#print axioms COE008Evaluation.weightedAt
#print axioms COE008Evaluation.advanceSound
#print axioms COE008Evaluation.foldSound
#print axioms COE008Evaluation.verifiedCertificateSound

end COE008Evaluation
