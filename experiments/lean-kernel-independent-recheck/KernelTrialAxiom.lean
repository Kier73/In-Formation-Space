import Init

namespace KernelTrial

axiom fakeProof : (1 : Nat) = 2

theorem axiomTrial : (1 : Nat) = 2 := fakeProof

#print axioms KernelTrial.axiomTrial

end KernelTrial
