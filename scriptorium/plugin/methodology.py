"""Explicit research and writing obligations, independent of any model provider."""

METHOD_CONTRACTS = {
    "situating": {
        "fields": [
            "text_position",
            "problem_relations",
            "concept_configuration",
            "discourse_sources",
            "practice_conditions",
            "reader_position",
        ],
        "requirements": ["各维度区分原文依据与背景推断。", "背景不足时保留空缺；允许竞争性构境。"],
    },
    "immanent_critique": {
        "fields": [
            "position",
            "own_criterion",
            "difficulty_type",
            "evidence",
            "retained",
            "negated",
            "changed",
            "stopping_reason",
        ],
        "requirements": [
            "区分事实错误、经验反例、外部批评和内在困难。",
            "只有按立场自身尺度成立的困难才进入转化；无有效转化时停止。",
        ],
    },
    "parallax": {
        "fields": [
            "observation_positions",
            "object_appearances",
            "excluded_differences",
            "gap_hypothesis",
            "rebuttal_conditions",
            "unresolved_remainder",
        ],
        "requirements": [
            "先排除术语、事实与时期差异；不同意见不自动构成视差。",
            "裂隙只是可反驳假说，不宣称最终不可化约，也不强制综合。",
        ],
    },
}

SECTIONS = {
    "research_note": [
        "问题与范围",
        "材料及其状态",
        "候选解释与依据",
        "反例和未决问题",
        "下一步核查",
    ],
    "argumentative_essay": [
        "明确立场",
        "概念辨析",
        "分论点与论据",
        "反方回应",
        "真实情境反思",
        "有条件的结论",
    ],
    "research_article": [
        "研究问题与范围",
        "文献位置",
        "材料与方法",
        "论证与证据",
        "异议和限制",
        "结论及核实书目",
    ],
    "literature_review": [
        "检索范围与覆盖限制",
        "实际读到的文献",
        "问题脉络和分歧",
        "比较与研究缺口",
        "待获取文献",
    ],
}


def writing_contract(genre: str) -> dict:
    if genre not in SECTIONS:
        raise ValueError("UNKNOWN_WRITING_GENRE")
    return {
        "genre": genre,
        "status": "planning_only_not_a_certified_manuscript",
        "sections": SECTIONS[genre],
        "argument_unit": [
            "claim",
            "claim_type",
            "source_evidence",
            "warrant",
            "counterposition",
            "qualification",
        ],
        "claim_types": [
            "textual_observation",
            "interpretive_reconstruction",
            "inference",
            "hypothesis",
            "personal_reflection",
        ],
        "citation_rules": [
            "原文事实、解释重构与自己的推论分别标明；精确定位不等于支持结论。",
            "作者归属与原文范围明确后才使用引文；须经 quote_verify，禁止伪造页码。",
            "书目、题目和模型常识不替代实际阅读；书目匹配不能作为作者原话。",
            "未取得正文时只列待查材料，不生成作者立场或假文献综述。",
        ],
        "experience_rules": [
            "个人经历必须来自用户明确提供的叙述。",
            "未提供时使用待填位置，或全篇明确标注为假设情境；不得以真实第一人称代写。",
        ],
        "style_rules": [
            "以问题、概念、论证与证据组织写作，避免鸡汤结论、无依据的普遍判断和理论名词堆砌。",
            "解释概念在当前论证中起什么作用；不要用理论家姓名替代论证。",
            "按任务选择文体；论说文不伪装成期刊论文，未读文献不伪装成研究综述。",
        ],
        "release_gate": [
            "逐条核查引文与作者归属",
            "标出未覆盖材料及仍需核实的判断",
            "确认反例/异议得到回应",
            "用户补充真实经历并审核后再形成定稿",
        ],
    }
