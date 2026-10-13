import Mathlib

/-!
Statement from Formal Conjectures `1b567c2f96e2aa86328094c4b9ca57f72a0d886e`, `FormalConjectures/Wikipedia/Schanuel.lean`.
The editable regions are the only bytes the participant may change.
-/


open scoped Real Complex
open IntermediateField

namespace Task

-- EDITABLE START
-- EDITABLE END

theorem schanuel_conjecture (n : ℕ) (z : Fin n → ℂ) (h : LinearIndependent ℚ z) :
    n ≤ Algebra.trdeg ℚ (adjoin ℚ (Set.range z ∪ Set.range (cexp ∘ z))) := by
  -- EDITABLE START
  sorry
  -- EDITABLE END

end Task

