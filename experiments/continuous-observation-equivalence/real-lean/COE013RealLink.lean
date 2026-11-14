import COE012RealLink
import COE013Json

/-!
COE-013: existentially recover a mathematically certified real-valued
piecewise neural observation directly from a parsed *original JSON byte*
representation.

The JSON parser is wholly executable, kernel-reducible Lean. Its only
external input is the original file's embedded ASCII byte list.
The actual SHA-256 digest equality of the file's bytes and embedded
header values remains a separate independent Python/Go trust domain.
-/

namespace COE013RealLink
open COEWireCheck COE012Wire COE013Json COE011Coverage COE010Network COE010Real

/-- Complete composition: when Lean accepts the canonical JSON bytes,
    the certificate's ACTUAL affine-cell atlas agrees with the independently
    compiled source neural network at EVERY real coordinate. -/
theorem acceptedJSONAllReal (raw : Bytes) (index : Nat) (x : ℝ)
    (h : acceptBytes raw = true) :
    ∃ (env : Envelope) (cert : Cert),
      parseEnvelope raw = some env ∧
      decodeCert env.wire = some cert ∧
      piecewiseReal cert index x =
        evalReal (component cert.layers index) x := by
  obtain ⟨env, cert, hparsed, hdecoded, hverified⟩ :=
    acceptBytes_implies_verified raw h
  exact ⟨env, cert, hparsed, hdecoded,
    piecewiseReal_eq_network cert index x hverified⟩

/-- The piecewise atlas recovered from the JSON byte input is globally
    continuous on the entire real line. -/
theorem acceptedJSONContinuous (raw : Bytes) (index : Nat)
    (h : acceptBytes raw = true) :
    ∃ (env : Envelope) (cert : Cert),
      parseEnvelope raw = some env ∧
      decodeCert env.wire = some cert ∧
      Continuous (piecewiseReal cert index) := by
  obtain ⟨env, cert, hparsed, hdecoded, hverified⟩ :=
    acceptBytes_implies_verified raw h
  exact ⟨env, cert, hparsed, hdecoded,
    continuous_piecewiseReal cert index hverified⟩

#print axioms COE013RealLink.acceptedJSONAllReal
#print axioms COE013RealLink.acceptedJSONContinuous
end COE013RealLink
