import Mathlib

/-!
Statement from Formal Conjectures `1b567c2f96e2aa86328094c4b9ca57f72a0d886e`, `FormalConjectures/Wikipedia/ABC.lean`.
The editable regions are the only bytes the participant may change.
-/


namespace Task

def radical (n : ℕ) : ℕ := n.primeFactors.prod id

-- EDITABLE START
-- EDITABLE END

theorem abc (ε : ℝ) (hε : 0 < ε) :
    {(a, b, c) : ℕ × ℕ × ℕ | 0 < a ∧ 0 < b ∧ 0 < c ∧ ({a, b, c} : Set ℕ).Pairwise Nat.Coprime ∧
      a + b = c ∧ (radical (a * b * c) : ℝ) ^ (1 + ε) < c}.Finite := by
  -- EDITABLE START
  sorry
  -- EDITABLE END

end Task

