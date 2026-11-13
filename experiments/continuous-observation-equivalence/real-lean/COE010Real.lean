import Mathlib
import COE009Coverage

/-!
COE-010: continuous real-number interpretations of finite exact-rational
affine/ReLU expression trees, and uniqueness of their real extensions.

Unlike a finite sample claim, agreement on *all rational coordinates*
determines a continuous function on every real coordinate. The remaining
bridge to COE009 is the explicit compilation from a certificate's original
network layers into these expressions (not an assumed axiom).

The imported COE009 modules are taken from the same repository's exact
source files by the CI job, not independently re-implemented copies.
-/

namespace COE010Real

/-- Pure expression syntax of the rational-affine and ReLU fragments
    supported by COE-009. No floating point or approximate arithmetic. -/
inductive Expr where
  | input
  | literal (value : Rat)
  | sum (lhs rhs : Expr)
  | scale (factor : Rat) (arg : Expr)
  | rectified (arg : Expr)
  deriving Repr

/-- Exact rational denotation. -/
def evalRat : Expr → Rat → Rat
  | .input, x => x
  | .literal value, _ => value
  | .sum a b, x => evalRat a x + evalRat b x
  | .scale factor arg, x => factor * evalRat arg x
  | .rectified arg, x => max 0 (evalRat arg x)

/-- The continuous real denotation, using exact embeddings of rational
    constants rather than a floating-point approximation. -/
def evalReal : Expr → ℝ → ℝ
  | .input, x => x
  | .literal value, _ => (value : ℝ)
  | .sum a b, x => evalReal a x + evalReal b x
  | .scale factor arg, x => (factor : ℝ) * evalReal arg x
  | .rectified arg, x => max 0 (evalReal arg x)

/-- Real interpretation restricted to rational arguments is exactly the
    canonical casting of rational interpretation. -/
theorem evalReal_at_rat (expr : Expr) (q : Rat) :
    evalReal expr (q : ℝ) = (evalRat expr q : ℝ) := by
  induction expr with
  | variable => rfl
  | literal value => rfl
  | sum lhs rhs ihl ihr =>
      simp only [evalReal, evalRat, ihl, ihr, Rat.cast_add]
  | scale factor arg ih =>
      simp only [evalReal, evalRat, ih, Rat.cast_mul]
  | rectified arg ih =>
      simp only [evalReal, evalRat, ih, Rat.cast_max, Rat.cast_zero]

/-- Every finite rational-affine/ReLU expression has a continuous real
    interpretation. This is an existence proof, not a continuity premise. -/
theorem continuous_evalReal (expr : Expr) : Continuous (evalReal expr) := by
  induction expr with
  | variable => simpa only [evalReal] using
      (continuous_id : Continuous (fun x : ℝ => x))
  | literal value => simpa only [evalReal] using
      (continuous_const : Continuous (fun _ : ℝ => (value : ℝ)))
  | sum lhs rhs ihl ihr =>
      simpa only [evalReal] using ihl.add ihr
  | scale factor arg ih =>
      simpa only [evalReal] using
        ((continuous_const : Continuous (fun _ : ℝ => (factor : ℝ))).mul ih)
  | rectified arg ih =>
      simpa only [evalReal] using
        ((continuous_const : Continuous (fun _ : ℝ => (0 : ℝ))).max ih)

/-- Two continuous real functions equal at every embedded rational are
    equal everywhere, since the rationals are dense in the real line.
    This is stronger than a finite-sample comparison. -/
theorem equal_of_all_rational_agreement (f g : ℝ → ℝ)
    (hf : Continuous f) (hg : Continuous g)
    (h : ∀ q : Rat, f (q : ℝ) = g (q : ℝ)) : f = g := by
  apply (Rat.denseRange_cast (𝕜 := ℝ)).equalizer hf hg
  funext q
  exact h q

/-- There is exactly one continuous extension of the exact rational
    evaluation of any finite rational-affine/ReLU expression. -/
theorem unique_continuous_real_extension (expr : Expr)
    (f : ℝ → ℝ) (hf : Continuous f)
    (h : ∀ q : Rat, f (q : ℝ) = (evalRat expr q : ℝ)) :
    f = evalReal expr := by
  apply equal_of_all_rational_agreement f (evalReal expr) hf
    (continuous_evalReal expr)
  intro q
  calc
    f (q : ℝ) = (evalRat expr q : ℝ) := h q
    _ = evalReal expr (q : ℝ) := (evalReal_at_rat expr q).symm

#print axioms COE010Real.evalReal_at_rat
#print axioms COE010Real.continuous_evalReal
#print axioms COE010Real.equal_of_all_rational_agreement
#print axioms COE010Real.unique_continuous_real_extension

end COE010Real
