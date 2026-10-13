import Mathlib

/-!
Statement from Formal Conjectures `1b567c2f96e2aa86328094c4b9ca57f72a0d886e`, `FormalConjectures/Wikipedia/SumOfThreeCubes.lean`.
The editable regions are the only bytes the participant may change.
-/


namespace Task

def IsSumOfThreeCubes (n : ℤ) : Prop :=
  ∃ x y z : ℤ, n = x ^ 3 + y ^ 3 + z ^ 3

-- EDITABLE START
-- EDITABLE END

theorem isSumOfThreeCubes_iff_mod_9 :
    ∀ n : ℤ, IsSumOfThreeCubes n ↔ ¬ (n ≡ 4 [ZMOD 9] ∨ n ≡ 5 [ZMOD 9]) := by
  -- EDITABLE START
  sorry
  -- EDITABLE END

end Task

