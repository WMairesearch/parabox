import Mathlib

/-!
Statement from Formal Conjectures `1b567c2f96e2aa86328094c4b9ca57f72a0d886e`, `FormalConjectures/Wikipedia/BealConjecture.lean`.
The editable regions are the only bytes the participant may change.
-/


namespace Task

def bealConjecture : Prop := ∀ {A B C x y z : ℕ},
    A ≠ 0 → B ≠ 0 → C ≠ 0 → 2 < x → 2 < y → 2 < z →
    A ^ x + B ^ y = C ^ z → 1 < Finset.gcd {A, B, C} id

-- EDITABLE START
-- EDITABLE END

theorem beal_conjecture : bealConjecture := by
  -- EDITABLE START
  sorry
  -- EDITABLE END

end Task

