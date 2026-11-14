import COE011Coverage
import COE012Wire

/-!
COE-012: semantic composition of the actual executable wire decoder,
the certificate verifier, and the all-real piecewise atlas proof of COE-011.

This theorem is not conditional on a Python-produced typed Rat object:
acceptWire starts from the Lean WireCert's original STRING TOKENS, decodes
those exact numbers and sentinels, and invokes COEWireCheck.verify.

Only the outer JSON-to-WireCert envelope translation remains unverified.
-/

namespace COE012RealLink
open COEWireCheck COE012Wire COE011Coverage COE010Network COE010Real

/-- Decoded and accepted original tokens denote a typed certificate whose
own piecewise affine atlas agrees with the complete compiled source network
at EVERY REAL coordinate. There is no trusted numerical conversion premise. -/
theorem acceptedWireAllReal (wire : WireCert) (index : Nat) (x : ℝ)
    (h : acceptWire wire = true) :
    ∃ cert : Cert,
      decodeCert wire = some cert ∧
      piecewiseReal cert index x =
        evalReal (component cert.layers index) x := by
  obtain ⟨cert, hdecoded, hverified⟩ :=
    acceptWire_implies_verified wire h
  exact ⟨cert, hdecoded,
    piecewiseReal_eq_network cert index x hverified⟩

/-- The decoded real piecewise model is continuous everywhere. -/
theorem acceptedWireContinuous (wire : WireCert) (index : Nat)
    (h : acceptWire wire = true) :
    ∃ cert : Cert,
      decodeCert wire = some cert ∧
      Continuous (piecewiseReal cert index) := by
  obtain ⟨cert, hdecoded, hverified⟩ :=
    acceptWire_implies_verified wire h
  exact ⟨cert, hdecoded,
    continuous_piecewiseReal cert index hverified⟩

/-- The nontrivial rational line fixture is an actual exact-decoding
proof input to the all-real mathematical semantics. -/
theorem fractionalWireAllReal (index : Nat) (x : ℝ) :
    ∃ cert : Cert,
      decodeCert rationalLineWire = some cert ∧
      piecewiseReal cert index x =
        evalReal (component cert.layers index) x :=
  acceptedWireAllReal rationalLineWire index x
    rationalLineWireAccepted

#print axioms COE012RealLink.acceptedWireAllReal
#print axioms COE012RealLink.acceptedWireContinuous
#print axioms COE012RealLink.fractionalWireAllReal

end COE012RealLink
