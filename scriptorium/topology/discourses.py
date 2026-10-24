from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TermKind(StrEnum):
    S1 = "S1"
    S2 = "S2"
    a = "a"
    barred = "$"


@dataclass(frozen=True)
class Discourse:
    agent: TermKind
    other: TermKind
    truth: TermKind
    production: TermKind

    def quarter_turn_cw(self) -> Discourse:
        return Discourse(
            agent=self.truth,
            other=self.agent,
            truth=self.production,
            production=self.other,
        )

    def orbit(self) -> list[Discourse]:
        result: list[Discourse] = [self]
        current = self
        for _ in range(3):
            current = current.quarter_turn_cw()
            result.append(current)
        return result

    def quarter_turn_ccw(self) -> Discourse:
        return Discourse(
            agent=self.other,
            other=self.production,
            truth=self.agent,
            production=self.truth,
        )

    @property
    def name(self) -> str:
        for n, d in _NAMED_DISCOURSES.items():
            if d == self:
                return n
        return f"Discourse({self.agent},{self.other},{self.truth},{self.production})"


MASTER = Discourse(TermKind.S1, TermKind.S2, TermKind.barred, TermKind.a)
UNIVERSITY = Discourse(TermKind.S2, TermKind.a, TermKind.S1, TermKind.barred)
HYSTERIC = Discourse(TermKind.barred, TermKind.S1, TermKind.a, TermKind.S2)
ANALYST = Discourse(TermKind.a, TermKind.barred, TermKind.S2, TermKind.S1)

_NAMED_DISCOURSES: dict[str, Discourse] = {
    "master": MASTER,
    "university": UNIVERSITY,
    "hysteric": HYSTERIC,
    "analyst": ANALYST,
}

DISCOURSE_ROTATION: list[Discourse] = [MASTER, HYSTERIC, ANALYST, UNIVERSITY]


def identify_discourse(agent: TermKind, other: TermKind,
                       truth: TermKind, production: TermKind) -> Discourse | None:
    candidate = Discourse(agent, other, truth, production)
    for d in _NAMED_DISCOURSES.values():
        if d == candidate:
            return d
    return None
