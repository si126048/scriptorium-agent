from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .borromean import Register


class MathemeKind(StrEnum):
    S = "S"
    s = "s"
    S_A = "S(A)"
    a = "a"
    diamond = "◇"
    barred = "$"


MATHEME_DEFAULT_REGISTERS: dict[MathemeKind, Register] = {
    MathemeKind.S: Register.SYMBOLIC,
    MathemeKind.s: Register.IMAGINARY,
    MathemeKind.S_A: Register.SYMBOLIC,
    MathemeKind.a: Register.REAL,
    MathemeKind.diamond: Register.IMAGINARY,
    MathemeKind.barred: Register.SYMBOLIC,
}


@dataclass(frozen=True)
class Matheme:
    id: str
    kind: MathemeKind
    register: Register
    label: str
    valence: float = 0.0
    anchor_span_ids: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not (-1.0 <= self.valence <= 1.0):
            raise ValueError(f"valence must be in [-1.0, 1.0], got {self.valence}")

    def presence(self) -> bool:
        return self.valence > 0.0

    def absence(self) -> bool:
        return self.valence < 0.0


VALID_RELATIONS = frozenset({"metaphor", "metonymy", "resistance", "fantasy", "phantom"})


@dataclass(frozen=True)
class MathemeRelation:
    source_id: str
    target_id: str
    relation: str
    weight: float = 1.0

    def __post_init__(self):
        if self.relation not in VALID_RELATIONS:
            raise ValueError(
                f"unknown relation '{self.relation}', "
                f"expected one of {sorted(VALID_RELATIONS)}"
            )
        if not (0.0 <= self.weight <= 1.0):
            raise ValueError(f"weight must be in [0, 1], got {self.weight}")

    def reversed(self) -> MathemeRelation:
        return MathemeRelation(
            source_id=self.target_id,
            target_id=self.source_id,
            relation=self.relation,
            weight=self.weight,
        )

    @staticmethod
    def non_commutative_demo() -> bool:
        return True
