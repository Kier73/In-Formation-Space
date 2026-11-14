import COE014SHA256

/-!
COE-014: compute the SHA-256 of the exact nested network object as sliced
by COE-013 from ORIGINAL complete canonical JSON bytes, and compare with
both its original network_sha256 header AND a receiver-owned pinned manifest.

The five hardcoded digest values here are existing independent verifier
expected-network digests (verify_certificates.py), not copied from a
producer-supplied certificate. A hash pin is an integrity anchor chosen
by the verifier; this does NOT establish an external owner's digital
signature, host provenance, or resistance to a compromised manifest.
-/

namespace COE014Provenance
open COE013Json COE014SHA256 COE012Wire

/-- Receiver-controlled pins for the five COE model fixtures.
    The mapping and its review are part of the trust policy. -/
def pinnedNetworkHashes : List Bytes :=
  [[52, 99, 100, 98, 54, 102, 54, 55, 57, 48, 55, 100, 100, 53, 50, 56, 54, 99, 100, 57, 101, 102, 55, 98, 48, 55, 51, 55, 54, 49, 102, 101, 56, 55, 54, 101, 99, 54, 49, 48, 57, 48, 101, 100, 54, 100, 98, 57, 50, 100, 100, 54, 98, 54, 55, 54, 102, 99, 100, 97, 100, 48, 57, 100],
   [100, 102, 48, 55, 54, 101, 56, 57, 54, 98, 48, 98, 50, 99, 55, 54, 48, 97, 49, 102, 51, 102, 100, 55, 55, 51, 49, 102, 51, 51, 97, 50, 51, 55, 55, 99, 100, 56, 53, 48, 52, 53, 56, 97, 54, 98, 98, 53, 53, 49, 56, 98, 99, 56, 48, 101, 51, 54, 102, 98, 56, 53, 48, 56],
   [101, 101, 54, 99, 54, 51, 48, 101, 54, 52, 57, 55, 98, 101, 56, 51, 57, 54, 98, 101, 48, 49, 49, 56, 52, 97, 53, 53, 53, 99, 54, 99, 52, 50, 56, 55, 100, 48, 100, 53, 54, 102, 101, 100, 97, 98, 55, 54, 101, 53, 98, 48, 102, 51, 98, 99, 48, 56, 57, 99, 54, 51, 50, 102],
   [49, 57, 100, 52, 50, 98, 48, 52, 48, 50, 97, 99, 97, 99, 51, 57, 101, 50, 53, 53, 57, 50, 48, 56, 52, 50, 101, 55, 51, 97, 50, 56, 97, 51, 101, 51, 54, 52, 101, 57, 54, 50, 49, 49, 100, 99, 54, 50, 51, 102, 56, 99, 55, 49, 55, 101, 100, 49, 50, 56, 53, 53, 55, 49],
   [102, 54, 99, 52, 57, 49, 54, 102, 97, 53, 50, 99, 97, 48, 57, 54, 101, 98, 100, 55, 100, 101, 54, 53, 102, 48, 99, 100, 57, 101, 98, 55, 50, 50, 102, 100, 53, 56, 49, 98, 101, 48, 54, 53, 57, 49, 98, 57, 52, 102, 101, 53, 50, 51, 51, 50, 102, 100, 55, 49, 55, 101, 98, 49]]

def isPinnedNetwork (hash : Bytes) : Bool :=
  pinnedNetworkHashes.contains hash

/-- Independently calculated SHA-256 over exact bytes of the original
nested network object, not the untrusted header and not a Python-made
re-encoding. -/
def hashMatchesHeader (env : Envelope) : Bool :=
  digestHex env.networkRaw == some env.networkSHA

/-- New stricter gate: original canonical JSON shape, exact Lean-decoded
rational semantics, independent network SHA-256 header matching, and
receiver-side expected-hash membership. -/
def acceptPinnedBytes (raw : Bytes) : Bool :=
  match parseEnvelope raw with
  | none => false
  | some env => acceptWire env.wire &&
      hashMatchesHeader env && isPinnedNetwork env.networkSHA

/-- The checksum and manifest gate does not weaken the mathematical
semantics established for any already accepted COE-013 original bytes. -/
theorem pinned_implies_accepted (raw : Bytes)
    (h : acceptPinnedBytes raw = true) :
    acceptBytes raw = true := by
  unfold acceptPinnedBytes at h
  cases hp : parseEnvelope raw with
  | none =>
      simp [hp] at h
  | some env =>
      have hw : acceptWire env.wire = true := by
        simpa only [Bool.and_eq_true] using h |>.1.1
      simpa [acceptBytes, hp] using hw

/-- Crucial provenance contract: when this stronger gate accepts, Lean
has actually computed the network hash from the embedded JSON bytes,
verified that digest matches the file header, checked it against the
independent pinned manifest, AND admitted the precise typed certificate.
The conclusion does not ask the caller to supply any of those facts. -/
theorem pinned_bytes_witness (raw : Bytes)
    (h : acceptPinnedBytes raw = true) :
    ∃ (env : Envelope) (cert : COEWireCheck.Cert),
      parseEnvelope raw = some env ∧
      digestHex env.networkRaw = some env.networkSHA ∧
      isPinnedNetwork env.networkSHA = true ∧
      decodeCert env.wire = some cert ∧
      COEWireCheck.verify cert = true := by
  unfold acceptPinnedBytes at h
  cases hp : parseEnvelope raw with
  | none =>
      simp [hp] at h
  | some env =>
      have hparts : acceptWire env.wire = true ∧
          hashMatchesHeader env = true ∧
          isPinnedNetwork env.networkSHA = true := by
        simpa only [Bool.and_eq_true] using h
      obtain ⟨cert, hd, hv⟩ :=
        acceptWire_implies_verified env.wire hparts.1
      have hhash : digestHex env.networkRaw = some env.networkSHA := by
        simpa [hashMatchesHeader] using hparts.2.1
      exact ⟨env, cert, rfl, hhash, hparts.2.2, hd, hv⟩

#print axioms COE014Provenance.pinned_implies_accepted
#print axioms COE014Provenance.pinned_bytes_witness

end COE014Provenance
