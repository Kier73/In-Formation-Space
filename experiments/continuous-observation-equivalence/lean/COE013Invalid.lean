import COE013Fixtures

/-!
COE-013 negative control. The malformed raw byte stream has a duplicate
atomic_cells key. The positive fixture theorem proves this stream decodes
to none, and this deliberately false denial of rejection MUST fail when
Lean checks it.
-/

namespace COE013Invalid
open COE013Json COE013Fixtures

theorem false_duplicate_key_acceptance :
    parseEnvelope duplicateKey ≠ none := by
  decide +kernel

end COE013Invalid
