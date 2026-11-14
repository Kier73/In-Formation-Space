import COE010Real

/-!
COE-010: source-network and *accepted certificate* integration.

- Build an expression per output of the actual COEWireCheck.Layer source model.
- Prove exact rational evaluation equals the independent COE008 network interpreter.
- Construct a continuous all-real realization of every output channel.
- Prove its rational restriction equals the observations established by COE009.
- Prove every continuous real realization extending those certified rational
  observations is the same function at EVERY real coordinate.

The finite certificate's JSON transport remains separately unverified.
-/

namespace COE010Network
open COE010Real COEWireCheck COE008Evaluation COE009Coverage

private def addExpr (acc : Expr) (pair : Rat × Expr) : Expr :=
  .sum acc (.scale pair.1 pair.2)

/-- Direct construction of a rational-weighted affine layer as an expression. -/
def linearRow (row : List Rat) (prev : List Expr) (bias : Rat) : Expr :=
  (row.zip prev).foldl addExpr (.literal bias)

/-- The expression-level compiler follows exactly the source layers'
    declared affine transforms and pointwise ReLU flags. -/
def compileLayer (layer : Layer) (prev : List Expr) : List Expr :=
  let pres := List.zipWith (fun row bias => linearRow row prev bias)
               layer.weights layer.bias
  if layer.relu then pres.map Expr.rectified else pres

def compileNetwork (layers : List Layer) : List Expr :=
  layers.foldl (fun prev layer => compileLayer layer prev) [Expr.input]

private theorem foldExprSound (pairs : List (Rat × Expr))
    (acc : Expr) (q : Rat) :
    evalRat (pairs.foldl addExpr acc) q =
    pairs.foldl (fun value pair => value + pair.1 * evalRat pair.2 q)
      (evalRat acc q) := by
  induction pairs generalizing acc with
  | nil => rfl
  | cons pair rest ih =>
      simp only [List.foldl_cons]
      rw [ih]
      rfl

private theorem zipExprMap (row : List Rat) (prev : List Expr) (q : Rat) :
    row.zip (prev.map (fun e => evalRat e q)) =
    (row.zip prev).map (fun p => (p.1, evalRat p.2 q)) := by
  induction row generalizing prev with
  | nil => simp
  | cons head tail ih =>
      cases prev with
      | nil => simp
      | cons value values => simp [ih]

/-- Compiling a source affine dot product and evaluating the resulting
    expression is equal to evaluating that dot product numerically. -/
theorem linearRowSound (row : List Rat) (prev : List Expr)
    (bias q : Rat) :
    evalRat (linearRow row prev bias) q =
      evalRow row (prev.map (fun e => evalRat e q)) bias := by
  unfold linearRow evalRow
  rw [foldExprSound]
  rw [zipExprMap]
  simp only [List.foldl_map, evalRat]

private theorem presSound (layer : Layer) (prev : List Expr) (q : Rat) :
    (List.zipWith (fun row bias => linearRow row prev bias)
       layer.weights layer.bias).map (fun e => evalRat e q) =
    List.zipWith (fun row bias =>
      evalRow row (prev.map (fun e => evalRat e q)) bias)
      layer.weights layer.bias := by
  cases layer with
  | mk weights bias relu =>
      induction weights generalizing bias with
      | nil => cases bias <;> rfl
      | cons row rows ih =>
          cases bias with
          | nil => rfl
          | cons value values =>
              simp [List.zipWith, linearRowSound, ih]

private theorem maxZeroRat (v : Rat) :
    max 0 v = (if 0 < v then v else 0) := by
  by_cases hv : 0 < v
  · simp [hv, max_eq_right (Rat.le_of_lt hv)]
  · have hle : v ≤ 0 := (Rat.not_lt).mp hv
    simp [hv, max_eq_left hle]

/-- The expression compiler refines direct numeric source interpretation
    for an arbitrary layer and exact rational input. -/
theorem compileLayerSound (layer : Layer) (prev : List Expr) (q : Rat) :
    (compileLayer layer prev).map (fun e => evalRat e q) =
      evalLayer layer (prev.map (fun e => evalRat e q)) := by
  let pres := List.zipWith (fun row bias => linearRow row prev bias)
               layer.weights layer.bias
  have hpre := presSound layer prev q
  cases hmode : layer.relu with
  | false =>
      simpa [compileLayer, evalLayer, pres, hmode] using hpre
  | true =>
      calc
        (compileLayer layer prev).map (fun e => evalRat e q) =
          (pres.map Expr.rectified).map (fun e => evalRat e q) := by
            simp [compileLayer, pres, hmode]
        _ = (pres.map (fun e => evalRat e q)).map
              (fun v => if 0 < v then v else 0) := by
              simp only [List.map_map, evalRat]
              congr 1
              funext e
              exact maxZeroRat (evalRat e q)
        _ = evalLayer layer (prev.map (fun e => evalRat e q)) := by
              rw [hpre]
              simp [evalLayer, hmode]

private theorem foldNetworkSound (layers : List Layer)
    (prev : List Expr) (q : Rat) :
    (layers.foldl (fun es layer => compileLayer layer es) prev).map
       (fun e => evalRat e q) =
    layers.foldl (fun values layer => evalLayer layer values)
       (prev.map (fun e => evalRat e q)) := by
  induction layers generalizing prev with
  | nil => rfl
  | cons layer rest ih =>
      simp only [List.foldl_cons]
      rw [ih]
      rw [compileLayerSound]

/-- Actual source network and compiled expressions agree at ALL rationals,
    including the rational activation cutpoints handled by COE-009. -/
theorem compileNetworkSound (layers : List Layer) (q : Rat) :
    (compileNetwork layers).map (fun e => evalRat e q) =
      evalNetwork layers q := by
  unfold compileNetwork evalNetwork
  rw [foldNetworkSound]
  simp [evalRat]

/-- A missing output channel denotes the constant zero function, making
    even malformed or zero-length source models total as expressions. -/
def component (layers : List Layer) (index : Nat) : Expr :=
  ((compileNetwork layers)[index]?).getD (.literal 0)

private theorem mappedComponent (es : List Expr) (index : Nat) (q : Rat) :
    evalRat (es[index]?.getD (.literal 0)) q =
      ((es.map (fun e => evalRat e q))[index]?).getD 0 := by
  induction es generalizing index with
  | nil => simp [evalRat]
  | cons first rest ih =>
      cases index with
      | zero => simp
      | succ k => simpa using ih k

/-- Every source-network output has a continuous real realization whose
    restriction to rational coordinates is EXACTLY the direct numeric source
    evaluator used by the prior certificate proof. -/
theorem componentAtRat (layers : List Layer) (index : Nat) (q : Rat) :
    evalReal (component layers index) (q : ℝ) =
      (((evalNetwork layers q)[index]?).getD 0 : ℝ) := by
  rw [evalReal_at_rat]
  rw [show evalRat (component layers index) q =
    ((evalNetwork layers q)[index]?).getD 0 by
      unfold component
      rw [mappedComponent]
      rw [compileNetworkSound]]

theorem componentContinuous (layers : List Layer) (index : Nat) :
    Continuous (evalReal (component layers index)) :=
  continuous_evalReal _

/-- Pick a covering witness from the theorem proved in COE-009.
    The certificate has no need to prescribe a unique cell at a shared
    endpoint, since all accepted neighboring cells agree there. -/
noncomputable def certifiedAtRat (cert : Cert)
    (hverify : verify cert = true) (q : Rat) : List Rat :=
  let cell := Classical.choose
    (verifiedCertificateAllRationals cert q hverify)
  cell.output.map (fun a => evaluateAt a q)

theorem certifiedAtRat_eq_network (cert : Cert)
    (hverify : verify cert = true) (q : Rat) :
    certifiedAtRat cert hverify q = evalNetwork cert.layers q := by
  exact (Classical.choose_spec
    (verifiedCertificateAllRationals cert q hverify)).2.2

/-- Main COE-010 result. For ANY accepted typed certificate, each output
    component has an existing continuous interpretation over ALL reals,
    and this continuous interpretation is uniquely determined by the
    certificate observations at EVERY rational q. The real interpretation
    is the explicitly compiled source neural network, not a postulated
    realization.

    Note: this theorem establishes unique continuous completion of the
    rational *observation*; it does not yet prove that an independently
    parsed real-valued piecewise certificate atlas is equal pointwise. -/
theorem acceptedCertificateHasUniqueRealMeaning
    (cert : Cert) (hverify : verify cert = true) (index : Nat) :
    ∃ f : ℝ → ℝ,
      Continuous f ∧
      (∀ q : Rat,
        f (q : ℝ) =
          (((certifiedAtRat cert hverify q)[index]?).getD 0 : ℝ)) ∧
      (∀ g : ℝ → ℝ, Continuous g →
        (∀ q : Rat,
          g (q : ℝ) =
            (((certifiedAtRat cert hverify q)[index]?).getD 0 : ℝ)) →
        g = f) := by
  refine ⟨evalReal (component cert.layers index),
    componentContinuous cert.layers index, ?_, ?_⟩
  · intro q
    rw [componentAtRat]
    rw [certifiedAtRat_eq_network]
  · intro g hg hrat
    apply equal_of_all_rational_agreement g
      (evalReal (component cert.layers index))
      hg (componentContinuous cert.layers index)
    intro q
    calc
      g (q : ℝ) =
          (((certifiedAtRat cert hverify q)[index]?).getD 0 : ℝ) := hrat q
      _ = (((evalNetwork cert.layers q)[index]?).getD 0 : ℝ) := by
        rw [certifiedAtRat_eq_network]
      _ = evalReal (component cert.layers index) (q : ℝ) :=
        (componentAtRat cert.layers index q).symm

#print axioms COE010Network.compileNetworkSound
#print axioms COE010Network.componentAtRat
#print axioms COE010Network.acceptedCertificateHasUniqueRealMeaning

end COE010Network
