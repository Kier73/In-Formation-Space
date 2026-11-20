"""TCN-001 -> TCN-002 conceptual adapter without widening evidence authority.

Admits a preexisting *qualified* TCN-001 quadratic discovery as a relative
phase state.  It does NOT prove that a user-declared future schedule was
observed, or that an external computation is physically running.
"""
from __future__ import annotations

from dataclasses import dataclass
from transfer import Ground, Ray, _mm, ray_from_matrix


@dataclass(frozen=True)
class InitialPhaseWitness:
    p: int
    a: int
    b: int
    discovery_sha256: str

    @classmethod
    def from_tcn001(cls, fitted):
        if (getattr(fitted,'decision',None) != 'qualified'
                or any(type(getattr(fitted,key,None)) is not int for key in ('p','a','b'))
                or type(getattr(fitted,'observed_digest',None)) is not str
                or len(fitted.observed_digest) != 64
                or any(c not in '0123456789abcdef' for c in fitted.observed_digest)):
            raise ValueError('qualified TCN-001 discovery with evidence digest required')
        # The relative initial phasor is exp(2pi*i*(a*x*x+b*x)/p):
        # D_a F|b> (the fitted c is absolute gauge and is not carried).
        Ground(fitted.p, (fitted.a,))
        return cls(fitted.p, fitted.a, fitted.b, fitted.observed_digest)

    def continue_hypothetically(self, pattern: tuple[int,...], steps: int, *,
                                assume_future_schedule: bool=False):
        """After initial phase wave, add steps of D_a F; future schedule opt-in.

        Returns ray and a scoped evidence note.  The discovery hash binds
        the TCN-001 observation; future phases are user-declared premises.
        """
        if type(steps) is not int or steps < 0:
            raise ValueError('nonnegative future step required')
        if steps > 0 and assume_future_schedule is not True:
            raise ValueError('future schedule not independently observed: explicit hypothesis opt-in required')
        ground = Ground(self.p, pattern)
        future, products = ground.advance_matrix(steps)
        initial, _ = Ground(self.p,(self.a,)).advance_matrix(1)
        all_steps = _mm(future, initial, self.p)
        ray = ray_from_matrix(self.p, all_steps, self.b)
        note = {'discovery_sha256':self.discovery_sha256,
                'discovery_scope':'TCN-001 finite partial-observation validation',
                'future_schedule_assumed':steps > 0,
                'future_steps_decimal':str(steps),
                'global_phase':'unobserved',
                'symplectic_matrix_products': products+1}
        return ray, note
