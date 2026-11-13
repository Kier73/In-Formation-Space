import COE009Evaluation

/-!
COE-009: total coverage of all rational inputs, including cutpoints.

The executable cover checker requires an unbounded first/last cell and
a chain of adjoining equal endpoints. An induction over that exact chain
proves that every rational x belongs to at least one closed cell. Coupled
with COE009Evaluation.verifiedCertificateClosedSound, this establishes a
total rational-domain semantic correctness statement for accepted certificates.
-/

namespace COE009Coverage
open COEWireCheck COE009Endpoint COE009Evaluation

/-- The structural link checker is definitionally the same adjacent-pair
    test as the original COE-007 List.zip implementation. -/
theorem joinedChainEquivalent (cells : List Cell) :
    joinedChain cells =
      (cells.zip (cells.drop 1)).all
        (fun pair => joinVerified pair.1 pair.2) := by
  induction cells with
  | nil => rfl
  | cons first rest ih =>
      cases rest with
      | nil => rfl
      | cons next tail =>
          simp [joinedChain, ih]

/-- The structural terminal sentinel agrees with the original
    reverse-head test of the final cell's +infinity endpoint. -/
theorem lastUnboundedEquivalent (cells : List Cell) :
    lastUnbounded cells =
      (match cells.reverse with
       | [] => false
       | last :: _ => decide (last.right = none)) := by
  induction cells with
  | nil => rfl
  | cons first rest ih =>
      cases rest with
      | nil => rfl
      | cons next tail =>
          change lastUnbounded (next :: tail) =
            (match (next :: tail).reverse ++ [first] with
             | [] => false
             | last :: _ => decide (last.right = none))
          rw [ih]
          cases hrev : (next :: tail).reverse with
          | nil =>
              have hh : (next :: tail).reverse ≠ [] := by simp
              exact False.elim (hh hrev)
          | cons last remaining =>
              simp [hrev]

private theorem joinedCoversFrom (first : Cell) (rest : List Cell) (x : Rat)
    (hstart : aboveLeft first x = true)
    (hlinks : joinedChain (first :: rest) = true)
    (hlast : lastUnbounded (first :: rest) = true) :
    ∃ cell : Cell, cell ∈ first :: rest ∧
      closedInside cell x = true := by
  induction rest generalizing first with
  | nil =>
      have hlastRight : first.right = none := by
        simpa [lastUnbounded] using hlast
      refine ⟨first, by simp, ?_⟩
      rw [closedInsideParts]
      simp [belowRight, hstart, hlastRight]
  | cons next tail ih =>
      by_cases hbelow : belowRight first x = true
      · refine ⟨first, by simp, ?_⟩
        rw [closedInsideParts]
        simp [hstart, hbelow]
      · obtain ⟨t, hright, ht⟩ : ∃ t : Rat,
            first.right = some t ∧ t < x := by
          cases hrt : first.right with
          | none =>
              have hb : belowRight first x = true := by
                simp [belowRight, hrt]
              exact False.elim (hbelow hb)
          | some t =>
              have ht : t < x := by
                apply (Rat.not_le).mp
                intro hle
                have hb : belowRight first x = true := by
                  simp [belowRight, hrt, hle]
                exact hbelow hb
              exact ⟨t, rfl, ht⟩
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
        have hnextStart : aboveLeft next x = true := by
          simp [aboveLeft, hnextLeft, Rat.le_of_lt ht]
        have hnextLinks : joinedChain (next :: tail) = true := hpair.2
        have hnextEnd : lastUnbounded (next :: tail) = true := by
          change lastUnbounded (next :: tail) = true at hlast
          exact hlast
        obtain ⟨c, hmem, hinside⟩ := ih next hnextStart
          hnextLinks hnextEnd
        exact ⟨c, by simp [hmem], hinside⟩

/-- An accepted executable covering-chain verifier assigns *every rational
    coordinate* to at least one declared closed interval. This includes
    all finite cutpoints. No enumeration or sampling over rational x. -/
theorem verifiedCoverCoversRationals (cert : Cert) (x : Rat)
    (hverify : verify cert = true) :
    ∃ cell : Cell, cell ∈ cert.cells ∧
      closedInside cell x = true := by
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
      have hstart : aboveLeft first x = true := by
        simp [aboveLeft, hleft]
      obtain ⟨cell, hmem, hin⟩ := joinedCoversFrom first rest x
        hstart hparts.2 hparts.1.1.2
      exact ⟨cell, by simpa [hcells] using hmem, hin⟩

/-- Full-domain rational meaning:
    any accepted certificate yields at every rational coordinate a claimed
    affine observation that is exactly equal to the original network's
    independently defined numeric evaluator. This includes the junctions
    between all adjacent cells. -/
theorem verifiedCertificateAllRationals (cert : Cert) (x : Rat)
    (hverify : verify cert = true) :
    ∃ cell : Cell,
      cell ∈ cert.cells ∧
      closedInside cell x = true ∧
      cell.output.map (fun a => evaluateAt a x) =
        COE008Evaluation.evalNetwork cert.layers x := by
  obtain ⟨cell, hmem, hclosed⟩ :=
    verifiedCoverCoversRationals cert x hverify
  exact ⟨cell, hmem, hclosed,
    verifiedCertificateClosedSound cert cell x hverify hmem hclosed⟩

#print axioms COE009Coverage.joinedChainEquivalent
#print axioms COE009Coverage.lastUnboundedEquivalent
#print axioms COE009Coverage.verifiedCoverCoversRationals
#print axioms COE009Coverage.verifiedCertificateAllRationals

end COE009Coverage
