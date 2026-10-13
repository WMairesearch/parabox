import Mathlib

/-!
Statement from Formal Conjectures `1b567c2f96e2aa86328094c4b9ca57f72a0d886e`, `FormalConjectures/Wikipedia/LegendreConjecture.lean`.
The editable regions are the only bytes the participant may change.
-/


open Nat

namespace Task

def IsPrime (p : ℕ) : Prop := Nat.Prime p

-- EDITABLE START
-- EDITABLE END

theorem legendre_conjecture :
    ∀ n ≥ 1, ∃ p ∈ Set.Ioo (n ^ 2) ((n + 1) ^ 2), IsPrime p := by
  -- EDITABLE START
  sorry
  -- EDITABLE END

end Task

