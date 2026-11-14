import COE013RealLink
import COE014Provenance

/-!
COE-014 composition: source bytes are accepted only after Lean has:
  1. parsed the entire canonical JSON envelope (COE-013),
  2. decoded and certified its exact mathematical content (COE-012/011),
  3. computed a pure-Lean SHA-256 digest of the original nested network
     JSON bytes and compared it to the file's network_sha256,
  4. checked that digest against the verifier-owned five-fixture manifest.

This is mathematical *integrity under a pinned hash policy*, not an
unforgeable digital signature or attestation by an external host.
-/
namespace COE014RealLink
open COE012Wire COE013Json COE014SHA256 COE014Provenance
open COE011Coverage COE010Network COE010Real COEWireCheck

/-- Any original canonical JSON byte stream accepted by the *strengthened*
SHA-256 provenance checker has an independently computed matched hash,
is pinned by the receiver, and its actual cell atlas equals the source
network at EVERY real input. -/
theorem pinnedSourceAllReal (raw : Bytes) (index : Nat) (x : ℝ)
    (h : acceptPinnedBytes raw = true) :
    ∃ (env : Envelope) (cert : Cert),
      parseEnvelope raw = some env ∧
      digestHex env.networkRaw = some env.networkSHA ∧
      isPinnedNetwork env.networkSHA = true ∧
      decodeCert env.wire = some cert ∧
      piecewiseReal cert index x =
        evalReal (component cert.layers index) x := by
  obtain ⟨env, cert, hp, hh, hpin, hdecoded, hverified⟩ :=
    pinned_bytes_witness raw h
  exact ⟨env, cert, hp, hh, hpin, hdecoded,
    piecewiseReal_eq_network cert index x hverified⟩

/-- The hash-pinned, byte-decoded piecewise real observer is continuous. -/
theorem pinnedSourceContinuous (raw : Bytes) (index : Nat)
    (h : acceptPinnedBytes raw = true) :
    ∃ (env : Envelope) (cert : Cert),
      parseEnvelope raw = some env ∧
      digestHex env.networkRaw = some env.networkSHA ∧
      isPinnedNetwork env.networkSHA = true ∧
      decodeCert env.wire = some cert ∧
      Continuous (piecewiseReal cert index) := by
  obtain ⟨env, cert, hp, hh, hpin, hdecoded, hverified⟩ :=
    pinned_bytes_witness raw h
  exact ⟨env, cert, hp, hh, hpin, hdecoded,
    continuous_piecewiseReal cert index hverified⟩

#print axioms COE014RealLink.pinnedSourceAllReal
#print axioms COE014RealLink.pinnedSourceContinuous

end COE014RealLink
