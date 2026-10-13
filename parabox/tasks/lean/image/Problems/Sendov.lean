import Mathlib

/-!
Statement from Formal Conjectures `1b567c2f96e2aa86328094c4b9ca57f72a0d886e`, `FormalConjectures/Wikipedia/Sendov.lean`.
The editable regions are the only bytes the participant may change.
-/


open Polynomial

namespace Task

def IsSendov (f : ℂ[X]) : Prop :=
  2 ≤ f.natDegree ∧ (f.rootSet ℂ ⊆ Metric.closedBall 0 1)

def SatisfiesSendovConjecture (n : ℕ) : Prop :=
  ∀ f : ℂ[X], IsSendov f → f.natDegree = n →
    ∀ z, z ∈ f.rootSet ℂ → Metric.infDist z (f.derivative.rootSet ℂ) ≤ 1

-- EDITABLE START
-- EDITABLE END

theorem sendov_conjecture (n : ℕ) (hn : 2 ≤ n) : SatisfiesSendovConjecture n := by
  -- EDITABLE START
  sorry
  -- EDITABLE END

end Task

