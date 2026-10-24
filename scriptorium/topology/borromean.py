from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Register(StrEnum):
    REAL = "R"
    SYMBOLIC = "S"
    IMAGINARY = "I"


@dataclass(frozen=True)
class UnknottingEvent:
    window_index: int
    detached_pair: tuple[Register, Register]
    stable_pair: tuple[Register, Register]
    severity: float

    @property
    def detached_jaccard(self) -> float:
        return self.severity


RSI_MARKERS: dict[Register, list[str]] = {
    Register.REAL: [
        "说不出", "无法形容", "崩溃", "身体", "疼痛", "窒息",
        "空白", "失语", "尖叫", "颤抖", "恶心", "黑屏",
        "新造词", "乱码", "语法崩解", "无法理解", "莫名其妙",
        "real", "trauma", "impossible",
    ],
    Register.SYMBOLIC: [
        "规则", "法则", "命名", "定义", "结构", "关系",
        "符号", "能指", "所指", "大他者", "秩序", "系统",
        "父亲", "法律", "语言", "逻辑", "因果", "分类",
        "symbolic", "law", "name", "structure",
    ],
    Register.IMAGINARY: [
        "像我", "镜像", "倒影", "认同", "比喻", "仿佛",
        "好像", "就像", "类似", "一样", "映照", "投射",
        "自恋", "理想", "完美", "形象", "外表", "模仿",
        "imaginary", "mirror", "image", "like",
    ],
}


@dataclass
class RegisterCoherenceMonitor:
    window_size: int = 10
    rsi_markers: dict[Register, list[str]] = field(
        default_factory=lambda: {k: list(v) for k, v in RSI_MARKERS.items()}
    )
    _windows: list[dict[Register, set[str]]] = field(default_factory=list)
    _unknotting_events: list[UnknottingEvent] = field(default_factory=list)

    def feed(self, text: str, register: Register | None = None) -> dict[Register, set[str]]:
        hits: dict[Register, set[str]] = {r: set() for r in Register}
        text_lower = text.lower()
        for reg, markers in self.rsi_markers.items():
            if register is not None and reg != register:
                continue
            for m in markers:
                if m.lower() in text_lower:
                    hits[reg].add(m)
        self._windows.append(hits)
        if len(self._windows) > self.window_size:
            self._windows.pop(0)
        self._check_unknotting(len(self._windows) - 1)
        return hits

    def coherence_scores(self) -> dict[tuple[Register, Register], float]:
        if len(self._windows) < 2:
            return {(Register.REAL, Register.SYMBOLIC): 0.0,
                    (Register.SYMBOLIC, Register.IMAGINARY): 0.0,
                    (Register.REAL, Register.IMAGINARY): 0.0}

        current = self._aggregate_recent(self._windows[-1])
        previous = self._aggregate_recent(self._windows[-2]) if len(self._windows) >= 2 else current

        pairs = [
            (Register.REAL, Register.SYMBOLIC),
            (Register.SYMBOLIC, Register.IMAGINARY),
            (Register.REAL, Register.IMAGINARY),
        ]
        scores = {}
        for a, b in pairs:
            scores[(a, b)] = self._jaccard(current[a] | current[b], previous[a] | previous[b])
        return scores

    def detect_unknotting(self) -> list[UnknottingEvent]:
        return list(self._unknotting_events)

    def _aggregate_recent(self, window: dict[Register, set[str]]) -> dict[Register, set[str]]:
        return {r: set(markers) for r, markers in window.items()}

    def _check_unknotting(self, index: int) -> None:
        if len(self._windows) < 3:
            return
        scores = self._pairwise_jaccard(self._windows[-1], self._windows[-3])
        pairs = [
            (Register.REAL, Register.SYMBOLIC),
            (Register.SYMBOLIC, Register.IMAGINARY),
            (Register.REAL, Register.IMAGINARY),
        ]
        vals = {p: scores[p] for p in pairs}
        sorted_pairs = sorted(vals.items(), key=lambda x: x[1])
        lowest_pair, lowest_val = sorted_pairs[0]
        stable_val = sorted_pairs[2][1]
        if stable_val > 0.3 and lowest_val < stable_val * 0.4:
            event = UnknottingEvent(
                window_index=index,
                detached_pair=lowest_pair,
                stable_pair=sorted_pairs[2][0],
                severity=1.0 - lowest_val,
            )
            self._unknotting_events.append(event)

    def _pairwise_jaccard(
        self, w1: dict[Register, set[str]], w2: dict[Register, set[str]]
    ) -> dict[tuple[Register, Register], float]:
        pairs = [
            (Register.REAL, Register.SYMBOLIC),
            (Register.SYMBOLIC, Register.IMAGINARY),
            (Register.REAL, Register.IMAGINARY),
        ]
        result = {}
        for a, b in pairs:
            union_a = w1[a] | w1[b]
            union_b = w2[a] | w2[b]
            result[(a, b)] = self._jaccard(union_a, union_b)
        return result

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a and not b:
            return 0.0
        return len(a & b) / len(a | b)
