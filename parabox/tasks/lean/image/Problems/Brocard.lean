import Mathlib

/-!
Statement from Formal Conjectures `1b567c2f96e2aa86328094c4b9ca57f72a0d886e`, `FormalConjectures/Wikipedia/BrocardConjecture.lean`.
The editable regions are the only bytes the participant may change.
-/


open Nat Finset

namespace Task

def IsPrime (p : ℕ) : Prop := Nat.Prime p

instance : DecidablePred IsPrime := fun n => by
  unfold IsPrime
  infer_instance

-- EDITABLE START
-- EDITABLE END

theorem brocard_conjecture (n : ℕ) (hn : 1 ≤ n) :
    4 ≤ ((Ioo ((n.nth IsPrime) ^ 2) (((n + 1).nth IsPrime) ^ 2)).filter IsPrime).card := by
  -- EDITABLE START
  sorry
  -- EDITABLE END

end Task

