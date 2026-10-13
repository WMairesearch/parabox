import Mathlib

/-!
Statement from Formal Conjectures `1b567c2f96e2aa86328094c4b9ca57f72a0d886e`, `FormalConjectures/Wikipedia/GoldbachConjecture.lean`.
The editable regions are the only bytes the participant may change.
-/


open Nat

namespace Task

-- EDITABLE START
-- EDITABLE END

theorem goldbach :
    ∀ n : ℕ, 2 < n → Even n → ∃ p q, Prime p ∧ Prime q ∧ n = p + q := by
  -- EDITABLE START
  sorry
  -- EDITABLE END

end Task

