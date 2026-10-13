namespace Task

def IsZero (n : Nat) : Prop := n = 0

-- EDITABLE START
-- EDITABLE END

theorem toy (n : Nat) (h : IsZero n) : IsZero n := by
  -- EDITABLE START
  exact h
  -- EDITABLE END

end Task
