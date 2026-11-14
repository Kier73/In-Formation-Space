import COE011Atlas

/-!
COE-011: an explicit real-valued piecewise interpreter built from the
original certificate's ordered list of claimed affine activation cells.

The first matching closed cell is selected, so a shared boundary has
deterministic *first-cell* behavior. The CI theorem proves it does not
matter which valid cell was selected: all cells that contain the real
input agree with the independently constructed continuous source network.
-/

namespace COE011Coverage
open COEWireCheck COE008Evaluation COE011Atlas COE010Real COE010Network

/-- Follow the actual verified rational endpoint chain as a chain of
closed REAL intervals. The argument works for an arbitrary real x and
does not assume that x is rational or computably comparable to a cutpoint. -/
private theorem linkedCoversRealFrom (first : Cell) (rest : List Cell)
    (x : ℝ) (hstart : aboveReal first x)
    (hlinks : joinedChain (first :: rest) = true)
    (hlast : lastUnbounded (first :: rest) = true) :
    ∃ c : Cell, c ∈ first :: rest ∧ inRealCell c x := by
  induction rest generalizing first with
  | nil =>
      have hend : first.right = none := by
        simpa [lastUnbounded] using hlast
      refine ⟨first, by simp, ?_⟩
      exact ⟨hstart, by simp [belowReal, hend]⟩
  | cons next tail ih =>
      by_cases hbelow : belowReal first x
      · exact ⟨first, by simp, ⟨hstart, hbelow⟩⟩
      · obtain ⟨t, hright, ht⟩ :
            ∃ t : Rat, first.right = some t ∧ (t : ℝ) < x := by
          cases hrt : first.right with
          | none =>
              have hb : belowReal first x := by
                simp [belowReal, hrt]
              exact False.elim (hbelow hb)
          | some t =>
              have hnot : ¬ x ≤ (t : ℝ) := by
                simpa [belowReal, hrt] using hbelow
              exact ⟨t, rfl, lt_of_not_ge hnot⟩
        have hpair : joinVerified first next = true ∧
              joinedChain (next :: tail) = true := by
          change (joinVerified first next &&
            joinedChain (next :: tail)) = true at hlinks
          simpa only [Bool.and_eq_true] using hlinks
        have hj : joinVerified first next = true := hpair.1
        have hnextLeft : next.left = some t := by
          cases hn : next.left with
          | none =>
              simp [joinVerified, hright, hn] at hj
          | some val =>
              simp [joinVerified, hright, hn] at hj
              have heq : t = val := hj.1
              simpa [hn, heq]
        have hnextStart : aboveReal next x := by
          simpa [aboveReal, hnextLeft] using (le_of_lt ht)
        have hnextEnd : lastUnbounded (next :: tail) = true := by
          change lastUnbounded (next :: tail) = true at hlast
          exact hlast
        obtain ⟨c, hmem, hin⟩ :=
          ih next hnextStart hpair.2 hnextEnd
        exact ⟨c, by simp [hmem], hin⟩

/-- The actual accepted *typed* certificate covers every real coordinate
with at least one declared closed activation cell. This is a theorem
about the verifier's exact rational endpoints, not an unverified density
analogy or extrapolation. -/
theorem verifiedRealCover (cert : Cert) (x : ℝ)
    (hverify : verify cert = true) :
    ∃ c : Cell, c ∈ cert.cells ∧ inRealCell c x := by
  have hc : coverVerified cert.cells = true := by
    simp only [verify, Bool.and_eq_true] at hverify
    grind
  cases hcells : cert.cells with
  | nil =>
      simp [coverVerified, hcells] at hc
  | cons first rest =>
      have hc' : coverVerified (first :: rest) = true := by
        simpa [hcells] using hc
      have hparts :
          (decide (first.left = none) &&
          lastUnbounded (first :: rest) &&
          (first :: rest).all intervalProper &&
          joinedChain (first :: rest)) = true := by
        simpa only [coverVerified] using hc'
      simp only [Bool.and_eq_true] at hparts
      have hleft : first.left = none := by
        have hh : decide (first.left = none) = true := hparts.1.1.1
        simpa using hh
      have hstart : aboveReal first x := by
        simp [aboveReal, hleft]
      obtain ⟨c, hmem, hin⟩ :=
        linkedCoversRealFrom first rest x hstart hparts.2 hparts.1.1.2
      exact ⟨c, by simpa [hcells] using hmem, hin⟩

/-- An ordered, first-matching-cell selection procedure over the
certificate's **actual cell list**. It uses exact real comparisons, so
the mathematical semantics are noncomputable, but choice of cell is
fully specified for shared endpoints. -/
noncomputable def firstRealCell : List Cell → ℝ → Option Cell
  | [], _ => none
  | c :: rest, x => by
      classical
      exact if inRealCell c x then some c else firstRealCell rest x

private theorem firstRealCell_valid (cells : List Cell) (x : ℝ)
    (hex : ∃ c : Cell, c ∈ cells ∧ inRealCell c x) :
    ∃ c : Cell,
      firstRealCell cells x = some c ∧
      c ∈ cells ∧ inRealCell c x := by
  classical
  induction cells with
  | nil =>
      obtain ⟨c, hmem, _⟩ := hex
      simp at hmem
  | cons first rest ih =>
      by_cases hfirst : inRealCell first x
      · exact ⟨first, by simp [firstRealCell, hfirst], by simp, hfirst⟩
      · have hrest : ∃ c : Cell, c ∈ rest ∧ inRealCell c x := by
          obtain ⟨c, hmem, hin⟩ := hex
          simp only [List.mem_cons] at hmem
          rcases hmem with heq | hmem
          · subst c
            exact False.elim (hfirst hin)
          · exact ⟨c, hmem, hin⟩
        obtain ⟨c, hfind, hmem, hin⟩ := ih hrest
        exact ⟨c, by simp [firstRealCell, hfirst, hfind],
          by simp [hmem], hin⟩

/-- An actual piecewise interpreter: scan the original cell list,
choose the first closed interval containing x, and evaluate that cell's
declared affine expression. At a malformed/no-cover input the result
defaults to 0; correctness is only claimed when verify cert = true. -/
noncomputable def piecewiseReal (cert : Cert) (index : Nat) (x : ℝ) : ℝ :=
  match firstRealCell cert.cells x with
  | some c => cellOutputReal c index x
  | none => 0

/-- All admissible cells whose intervals overlap agree in *their own*
real-valued affine outputs, even at exact cutpoints. -/
theorem overlappingCellsAgree (cert : Cert) (first second : Cell)
    (index : Nat) (x : ℝ) (hverify : verify cert = true)
    (hfirst : first ∈ cert.cells) (hsecond : second ∈ cert.cells)
    (hxfirst : inRealCell first x) (hxsecond : inRealCell second x) :
    cellOutputReal first index x = cellOutputReal second index x := by
  calc
    cellOutputReal first index x =
      evalReal (component cert.layers index) x :=
        verifiedCellRealSound cert first index x hverify hfirst hxfirst
    _ = cellOutputReal second index x :=
      (verifiedCellRealSound cert second index x hverify hsecond hxsecond).symm

/-- Main COE-011 realization result. The function is built from the
retained certificate's actual cell atlas, and for EVERY real coordinate
its piecewise affine evaluation equals the independently compiled full
neural network's continuous real-valued evaluation. -/
theorem piecewiseReal_eq_network (cert : Cert) (index : Nat) (x : ℝ)
    (hverify : verify cert = true) :
    piecewiseReal cert index x =
      evalReal (component cert.layers index) x := by
  obtain ⟨cell, hmem, hin⟩ :=
    verifiedRealCover cert x hverify
  obtain ⟨chosen, hfind, hmem', hin'⟩ :=
    firstRealCell_valid cert.cells x ⟨cell, hmem, hin⟩
  have hsound := verifiedCellRealSound cert chosen index x
    hverify hmem' hin'
  simpa [piecewiseReal, hfind] using hsound

/-- The directly interpreted piecewise atlas is globally continuous
on ℝ. This is proved from its semantic equality to the source neural
network, not assumed or inferred merely from its syntactic construction. -/
theorem continuous_piecewiseReal (cert : Cert) (index : Nat)
    (hverify : verify cert = true) :
    Continuous (piecewiseReal cert index) := by
  have hfun : piecewiseReal cert index =
      evalReal (component cert.layers index) := by
    funext x
    exact piecewiseReal_eq_network cert index x hverify
  rw [hfun]
  exact componentContinuous cert.layers index

/-- At each rational coordinate, the real piecewise atlas coincides with
the original certificate observations established by COE-009. -/
theorem piecewiseReal_at_rational (cert : Cert) (index : Nat)
    (hverify : verify cert = true) (q : Rat) :
    piecewiseReal cert index (q : ℝ) =
      (((certifiedAtRat cert hverify q)[index]?).getD 0 : ℝ) := by
  calc
    piecewiseReal cert index (q : ℝ) =
        evalReal (component cert.layers index) (q : ℝ) :=
      piecewiseReal_eq_network cert index (q : ℝ) hverify
    _ = (((evalNetwork cert.layers q)[index]?).getD 0 : ℝ) :=
      componentAtRat cert.layers index q
    _ = (((certifiedAtRat cert hverify q)[index]?).getD 0 : ℝ) := by
      rw [certifiedAtRat_eq_network]

#print axioms COE011Coverage.verifiedRealCover
#print axioms COE011Coverage.overlappingCellsAgree
#print axioms COE011Coverage.piecewiseReal_eq_network
#print axioms COE011Coverage.continuous_piecewiseReal
#print axioms COE011Coverage.piecewiseReal_at_rational

end COE011Coverage
