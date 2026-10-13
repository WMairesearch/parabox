import Mathlib

/-!
Statement from Formal Conjectures `1b567c2f96e2aa86328094c4b9ca57f72a0d886e`, `FormalConjectures/Wikipedia/TwinPrimes.lean`.
The editable regions are the only bytes the participant may change.
-/


open Nat

namespace Task

def IsPrime (p : ℕ) : Prop := Nat.Prime p

-- EDITABLE START
-- EDITABLE END

theorem twin_primes : {p : ℕ | IsPrime p ∧ IsPrime (p + 2)}.Infinite := by
  -- EDITABLE START
  sorry
  -- EDITABLE END

end Task

