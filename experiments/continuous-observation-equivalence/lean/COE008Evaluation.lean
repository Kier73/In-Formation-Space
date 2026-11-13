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
        · have hxpos : 0 < evaluateAt a x := by
            by_contra hxneg
            have : False := by simpa [hpos, hxneg] using hstable
            exact this
          simp [hpos, hxpos]
        · have hxneg : ¬ 0 < evaluateAt a x := by
            intro hxx
            have : False := by simpa [hpos, hxx] using hstable
            exact this
          simp [hpos, hxneg, zeroAffine, evaluateAt]
      simp only [List.map_cons]
      rw [hbranch, ih hguard.2]

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
      change (pre.map (fun a => evaluateAt a x)) =
        List.zipWith (fun row bias =>
          evalRow row (state.2.map (fun a => evaluateAt a x)) bias)
          layer.weights layer.bias
      exact hpre
  | true =>
      have hguard : pre.all (rootExcluded cell) = true := by
        simpa [hmode] using hroot
      have hcorrect := allRootGuardsSound cell pre (probe cell) x hp hx hguard
      change (pre.map (fun a => if 0 < evaluateAt a (probe cell) then a else zeroAffine)).map
          (fun a => evaluateAt a x) =
        (List.zipWith (fun row bias =>
          evalRow row (state.2.map (fun a => evaluateAt a x)) bias)
          layer.weights layer.bias).map (fun v => if 0 < v then v else 0)
      rw [hcorrect]
      simp only [List.map_map]
      rw [hpre]

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

end COE008Evaluation
