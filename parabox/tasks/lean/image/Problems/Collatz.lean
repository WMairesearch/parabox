import Mathlib

/-!
Statement from Formal Conjectures `1b567c2f96e2aa86328094c4b9ca57f72a0d886e`, `FormalConjectures/Wikipedia/CollatzConjecture.lean`.
The editable regions are the only bytes the participant may change.
-/


open Nat

namespace Task

def collatzStep (n : ℕ) : ℕ :=
  if Even n then n / 2 else 3 * n + 1

-- EDITABLE START
-- EDITABLE END

theorem collatz_conjecture (n : ℕ) (hn : n > 0) : ∃ m, collatzStep^[m] n = 1 := by
  -- EDITABLE START
  sorry
  -- EDITABLE END

end Task

