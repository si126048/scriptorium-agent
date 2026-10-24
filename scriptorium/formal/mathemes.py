"""Lacanian formal notation: mathemes, discourse algebra, RSI topology."""

from __future__ import annotations

MATHEME_ALPHABET: dict[str, dict[str, str]] = {
    "subject": {
        "$": "split subject (sujet barré)",
        "a": "objet petit a — cause of desire",
        "A": "the Other (Autre)",
    },
    "signifier": {
        "S1": "master signifier (unary trait)",
        "S2": "knowledge chain (battery of signifiers)",
        "S": "signifier (general)",
        "s": "signified (signifié)",
    },
    "operation": {
        "◇": "fantasy frame: $ ◇ a",
        "/": "bar — repression / impossibility",
        "→": "metonymic displacement",
        "∩": "metaphoric condensation",
    },
    "jouissance": {
        "J": "jouissance (general)",
        "JΦ": "phallic jouissance",
        "JA": "jouissance of the Other",
        "j": "surplus jouissance (plus-de-jouir)",
    },
    "topology": {
        "(S,I,R)_B": "Borromean knot — three registers interlocked",
        "S3": "sinthome — fourth ring binding S,I,R",
        "Torus": "toroidal surface of signifier chain",
        "Möbius": "Möbius strip — inside/outside undifferentiated",
    },
}

DISCOURSE_ALGEBRA: dict[str, dict[str, str | list[str]]] = {
    "master": {
        "symbol": "D_m",
        "structure": "[S₁→S₂ / $→a]",
        "agent": "S₁",
        "other": "S₂",
        "truth": "$",
        "product": "a",
        "logic": "S₁ commands S2; $ divided by unconscious; a produced as waste",
        "markers": ["authority", "mastery", "command", "founding gesture"],
    },
    "university": {
        "symbol": "D_u",
        "structure": "[S₂→a / S₁→$]",
        "agent": "S₂",
        "other": "a",
        "truth": "S₁",
        "product": "$",
        "logic": "knowledge S2 claims neutrality; hides S1 authority; produces divided subjects",
        "markers": ["neutrality", "expertise", "bureaucracy", "objectified knowledge"],
    },
    "hysteric": {
        "symbol": "D_h",
        "structure": "[$→S₁ / a→S₂]",
        "agent": "$",
        "other": "S₁",
        "truth": "a",
        "product": "S₂",
        "logic": "divided $ addresses S1; driven by a; produces new knowledge S2",
        "markers": ["questioning", "dissatisfaction", "symptom as address", "demand for truth"],
    },
    "analyst": {
        "symbol": "D_a",
        "structure": "[a→$ / S₂→S₁]",
        "agent": "a",
        "other": "$",
        "truth": "S₂",
        "product": "S₁",
        "logic": "analyst occupies a; provokes $; from S2 knowledge; new S1 emerges",
        "markers": ["silence", "scansion", "interpretation", "fall of the subject"],
    },
}

REGISTER_TAXONOMY: dict[str, dict[str, list[str]]] = {
    "S": {
        "name": "Symbolic",
        "domain": "law, language, structure, naming, kinship",
        "markers": [
            "rule terms", "naming relations", "kinship terms",
            "temporal markers", "conditional structures", "law references",
        ],
        "topology": "signifier chain S→S along the Torus",
    },
    "I": {
        "name": "Imaginary",
        "domain": "identification, rivalry, image, ego, mirror",
        "markers": [
            "similes", "metaphors of identity", "competition",
            "self-reference", "body image", "idealization",
        ],
        "topology": "specular relation on the Möbius surface",
    },
    "R": {
        "name": "Real",
        "domain": "trauma, impossibility, gap, body-without-language",
        "markers": [
            "grammar collapse", "neologisms", "body sensations",
            "repetition compulsion", "silence", "unspeakable",
        ],
        "topology": "hole in the Borromean knot — resists symbolization",
    },
}

CONCEPT_TO_MATHEME: dict[str, list[str]] = {
    "signifier": ["S", "S1"],
    "signified": ["s"],
    "repetition": ["S→S", "J"],
    "objet_a": ["a"],
    "objet_petit_a": ["a"],
    "split_subject": ["$"],
    "big_other": ["A"],
    "fantasy": ["$◇a"],
    "four_discourses": ["D_m", "D_u", "D_h", "D_a"],
    "master_discourse": ["D_m"],
    "university_discourse": ["D_u"],
    "hysteric_discourse": ["D_h"],
    "analyst_discourse": ["D_a"],
    "jouissance": ["J"],
    "surplus_jouissance": ["j"],
    "mirror_stage": ["I", "a"],
    "rsi_topology": ["(S,I,R)_B"],
    "sinthome": ["S3"],
    "point_de_capiton": ["S1∩S2"],
    "desire": ["$", "a", "$◇a"],
    "lack": ["/", "$"],
    "castration": ["/"],
    "name_of_father": ["S1", "A"],
    "foreclosure": ["/A"],
    "metaphor": ["∩"],
    "metonymy": ["→"],
    "phallic_function": ["JΦ"],
    "sexuation": ["JΦ", "JA"],
}

DELEUZE_ALPHABET: dict[str, dict[str, str]] = {
    "core": {
        "Ag": "assemblage (agencement) — heterogeneous connection of expressions and contents",
        "Rz": "rhizome — non-hierarchical, acentered connection principle",
        "Dm": "desiring-machine — productive connection, not lack",
        "BwO": "body without organs — intensity plane, de-organization",
    },
    "movement": {
        "Dt": "deterritorialization — decoding, escaping capture",
        "Rt": "reterritorialization — recoding, recapture, stabilization",
        "Lf": "line of flight — escape vector, creative rupture",
        "Bec": "becoming — non-imitative transformation process",
    },
    "ontology": {
        "Mul": "multiplicity — neither-one-nor-many collective logic",
        "Aff": "affect — capacity to affect and be affected",
        "Int": "intensity — differential force, threshold of transformation",
        "V↔A": "virtual ↔ actual — coexistence, not succession",
    },
    "scale": {
        "Mol": "molar — rigid, hierarchical, statistical aggregate",
        "mo": "molecular — fluid, micro-political, sub-individual",
    },
}

DELEUZE_REGISTER_TAXONOMY: dict[str, dict[str, str | list[str]]] = {
    "M": {
        "name": "Machine-connection",
        "domain": "heterogeneous elements connected, production, flow",
        "markers": [
            "linking verbs", "conjunctions", "technical terms",
            "infrastructure references", "body-machine metaphors",
        ],
    },
    "D": {
        "name": "Deterritorialization",
        "domain": "decoding, escaping, unmooring from fixed codes",
        "markers": [
            "boundary crossing", "code switching", "norm violation",
            "migration metaphors", "escape vocabulary",
        ],
    },
    "B": {
        "name": "Becoming",
        "domain": "transformation, non-imitative change, process",
        "markers": [
            "becoming-X expressions", "transformation verbs",
            "process language", "threshold descriptions",
        ],
    },
    "I": {
        "name": "Intensity/Affect",
        "domain": "emotional force, threshold, capacity to affect",
        "markers": [
            "emotional intensity markers", "sensory language",
            "exclamation", "rhythm shifts", "emphasis patterns",
        ],
    },
}

DELEUZE_OPERATIONS: dict[str, str] = {
    "×": "heterogeneous connection (Ag: element × element)",
    "↗": "deterritorialization vector (Dt↗)",
    "↘": "reterritorialization vector (Rt↘)",
    "∅": "de-stratification / empty BwO",
    "≡": "coding / fixation / capture",
}

CONCEPT_TO_MATHEME.update({
    "assemblage": ["Ag"],
    "rhizome": ["Rz"],
    "deterritorialization": ["Dt"],
    "reterritorialization": ["Rt"],
    "lines_of_flight": ["Lf"],
    "desiring_machine": ["Dm"],
    "body_without_organs": ["BwO"],
    "difference_and_repetition": ["Bec", "Mul"],
    "becoming": ["Bec"],
    "multiplicity": ["Mul"],
    "affect": ["Aff"],
    "virtual_actual": ["V↔A"],
    "schizoanalysis": ["Dm", "BwO", "Dt"],
    "socius": ["Mol", "≡"],
    "intensity": ["Int"],
})


def format_alphabet() -> str:
    lines = ["═══ MATHEME ALPHABET ═══"]
    for category, entries in MATHEME_ALPHABET.items():
        lines.append(f"\n── {category} ──")
        for symbol, meaning in entries.items():
            lines.append(f"  {symbol:8s} {meaning}")
    return "\n".join(lines)


def format_discourse_table() -> str:
    lines = ["═══ FOUR DISCOURSES (Lacan) ═══", ""]
    for dtype, info in DISCOURSE_ALGEBRA.items():
        lines.append(f"  {info['symbol']}  {info['structure']}")
        lines.append(f"       agent={info['agent']}  other={info['other']}  "
                      f"truth={info['truth']}  product={info['product']}")
        lines.append(f"       {info['logic']}")
        lines.append("")
    return "\n".join(lines)


def format_register_table() -> str:
    lines = ["═══ RSI REGISTERS ═══", ""]
    for reg, info in REGISTER_TAXONOMY.items():
        lines.append(f"  [{reg}] {info['name']}: {info['domain']}")
        lines.append(f"       markers: {', '.join(info['markers'][:4])}")
        lines.append(f"       topology: {info['topology']}")
        lines.append("")
    return "\n".join(lines)


def format_formal_schema(stage: str) -> str:
    if stage == "evidence":
        return "\n".join([
            format_alphabet(),
            "",
            format_register_table(),
            "═══ EVIDENCE SCHEMA ═══",
            "",
            "For each observation, assign:",
            "  register ∈ {S, I, R}",
            "  matheme_link ∈ MATHEME_ALPHABET keys",
            "  span_ids ⊆ available spans",
            "",
            'Output: {"observations": [{"id":"obs_N", "label":"...", "evidence_span_ids":[...], '
            '"register":"S|I|R", "register_markers":[...]}]}',
        ])
    if stage == "interpreter":
        return "\n".join([
            format_alphabet(),
            "",
            format_discourse_table(),
            format_register_table(),
            "═══ INTERPRETER SCHEMA ═══",
            "",
            "For each hypothesis:",
            "  concept_ids ⊆ MATHEME_ALPHABET keys ∪ CONCEPT_TO_MATHEME keys",
            "  discourse_type ∈ {D_m, D_u, D_h, D_a, null}",
            "  matheme_ids ⊆ MATHEME_ALPHABET symbol keys",
            "  points_de_capiton: [{id, signifier(S1), fixation_span_ids, duration, centrality}]",
            "  desire_residual: {demand_surface, need_object(null|a), residual_score∈[0,1]}",
            "",
            'Output: {"hypotheses": [{"id":"hyp_N", "concept_ids":[...], "support_ids":[...], '
            '"alternatives":[...], "counterexamples":[...], "status":"provisional", '
            '"theory_reference_ids":[...], "discourse_type":"D_m|D_u|D_h|D_a|null", '
            '"matheme_ids":[...], "points_de_capiton":[...], "desire_residual":{...}}]}',
        ])
    raise ValueError(f"Unknown formal stage: {stage}")


def format_deleuze_alphabet() -> str:
    lines = ["═══ DELEUZE ALPHABET ═══"]
    for category, entries in DELEUZE_ALPHABET.items():
        lines.append(f"\n── {category} ──")
        for symbol, meaning in entries.items():
            lines.append(f"  {symbol:6s} {meaning}")
    ops = "  ".join(f"{k}={v.split(' (')[0].split(' —')[0]}" for k, v in DELEUZE_OPERATIONS.items())
    lines.append(f"\n── ops ──\n  {ops}")
    return "\n".join(lines)


def format_deleuze_register() -> str:
    lines = ["═══ DELEUZE REGISTERS ═══", ""]
    for reg, info in DELEUZE_REGISTER_TAXONOMY.items():
        lines.append(f"  [{reg}] {info['name']}: {info['domain']}")
        lines.append(f"       markers: {', '.join(info['markers'][:3])}")
        lines.append("")
    return "\n".join(lines)
