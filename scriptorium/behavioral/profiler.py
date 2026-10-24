"""Integrator: statistical extraction + scriptorium structure -> distillation cards."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .chat_parser import load_normalized_messages, load_participant_messages, read_text
from .extractor import (
    MessageExtractor,
    compute_signature_phrases,
    compute_unique_expressions,
)
from .inference import infer_claims
from .models import (
    BehavioralProfile,
    ConsentPolicy,
    DistillationCard,
    ProfileArtifact,
    SourceManifest,
    StructuralSummary,
)

PARTICIPANT_FILES = {
    "弋": "弋.txt",
    "竹川": "竹川.txt",
    "灯": "灯.txt",
    "mirror_magos": "mirror_magos.txt",
    "猫是三味线": "猫是三味线.txt",
}


class BehavioralProfiler:
    def __init__(
        self,
        texts_dir: str | Path,
        db_path: str | Path | None = None,
        participants: dict[str, str] | None = None,
        consent: dict | ConsentPolicy | None = None,
    ):
        self.texts_dir = Path(texts_dir)
        self.db_path = Path(db_path) if db_path else None
        self.participants = participants or dict(PARTICIPANT_FILES)
        self.consent = consent if isinstance(consent, ConsentPolicy) else ConsentPolicy.model_validate(consent or {})
        self._raw_profiles: dict[str, dict] = {}
        self._profiles: dict[str, BehavioralProfile] = {}

    def extract_all(self) -> dict[str, dict]:
        if self._raw_profiles:
            return self._raw_profiles

        extractors: dict[str, MessageExtractor] = {}
        for name, fname in self.participants.items():
            path = self.texts_dir / fname
            if not path.exists():
                continue
            msgs = load_participant_messages(path)
            ext = MessageExtractor()
            ext.feed_all(msgs)
            extractors[name] = ext
            self._raw_profiles[name] = ext.summarize()

        sig = compute_signature_phrases(self._raw_profiles, top_k=10)
        uniq = compute_unique_expressions(self._raw_profiles, top_k=10)

        for name, raw in self._raw_profiles.items():
            raw["signature_phrases"] = sig.get(name, [])
            raw["unique_expressions"] = uniq.get(name, [])

        return self._raw_profiles

    def profile(self, pseudonym: str) -> BehavioralProfile:
        if pseudonym in self._profiles:
            return self._profiles[pseudonym]

        raw = self.extract_all().get(pseudonym)
        if raw is None:
            raise KeyError(f"no data for participant '{pseudonym}'")

        p = BehavioralProfile(
            pseudonym=pseudonym,
            total_messages=raw["total_messages"],
            avg_msg_length=raw["avg_msg_length"],
            median_msg_length=raw["median_msg_length"],
            short_msg_ratio=raw["short_msg_ratio"],
            media_ratio=raw["media_ratio"],
            emoji_density=raw["emoji_density"],
            top_bigrams=raw["top_bigrams"],
            signature_phrases=raw["signature_phrases"],
            unique_expressions=raw["unique_expressions"],
            top_punctuation=raw["top_punctuation"],
            question_ratio=raw["question_ratio"],
            exclamation_ratio=raw["exclamation_ratio"],
            repeated_punct_ratio=raw["repeated_punct_ratio"],
            opening_patterns=raw["opening_patterns"][:5],
            closing_patterns=raw["closing_patterns"][:5],
            bracket_insertions=raw["bracket_insertions"][:10],
            modal_particles=raw["modal_particles"],
            onomatopoeia=raw["onomatopoeia"],
            mention_targets=raw["mention_targets"],
            quote_reply_ratio=raw["quote_reply_ratio"],
            pure_media_ratio=raw["pure_media_ratio"],
            style_tags=self._auto_tags(pseudonym, raw),
        )
        self._profiles[pseudonym] = p
        return p

    def profile_all(self) -> dict[str, BehavioralProfile]:
        self.extract_all()
        for name in self.participants:
            if name in self._raw_profiles:
                self.profile(name)
        return dict(self._profiles)

    def get_structural(self, pseudonym: str) -> StructuralSummary | None:
        if not self.db_path or not self.db_path.exists():
            return None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT data FROM runs WHERE participant_id = ? ORDER BY id DESC LIMIT 1",
                (pseudonym,),
            ).fetchall()
            conn.close()
        except Exception:
            return None

        if not rows:
            return None

        run_data = json.loads(rows[0]["data"])
        packet = run_data.get("packet") or {}
        hypotheses = packet.get("hypotheses", [])

        discourse_types = [h["discourse_type"] for h in hypotheses if h.get("discourse_type")]
        dominant = max(set(discourse_types), key=discourse_types.count) if discourse_types else ""

        capitons = []
        for h in hypotheses:
            for pdc in h.get("points_de_capiton", []):
                if pdc.get("signifier"):
                    capitons.append(pdc["signifier"])

        desire = ""
        for h in hypotheses:
            dr = h.get("desire_residual")
            if dr and dr.get("demand_surface"):
                desire = dr["demand_surface"]
                break

        hall_risk = ""
        for hr in packet.get("hallucination_reports", []):
            risk = hr.get("risk_level", "")
            if risk:
                hall_risk = risk
                break

        return StructuralSummary(
            discourse_trajectory=discourse_types[:20],
            dominant_discourse=dominant,
            capiton_signifiers=list(dict.fromkeys(capitons))[:10],
            desire_direction=desire,
            hallucination_risk=hall_risk,
        )

    def to_distillation_card(self, pseudonym: str) -> DistillationCard:
        prof = self.profile(pseudonym)
        raw = self._raw_profiles[pseudonym]
        structural = self.get_structural(pseudonym)

        behavioral = {
            "voice_summary": self._voice_summary(pseudonym, prof, raw),
            "total_messages": prof.total_messages,
            "avg_msg_length": prof.avg_msg_length,
            "median_msg_length": prof.median_msg_length,
            "short_msg_ratio": prof.short_msg_ratio,
            "pure_media_ratio": prof.pure_media_ratio,
            "emoji_density": prof.emoji_density,
            "signature_moves": self._signature_moves(pseudonym, prof, raw),
            "top_phrases": prof.signature_phrases[:8],
            "unique_expressions": prof.unique_expressions[:8],
            "punctuation_style": self._punct_style(prof, raw),
            "emoji_pattern": self._emoji_pattern(prof, raw),
            "sample_lines": self._sample_lines(pseudonym, raw),
            "bracket_samples": prof.bracket_insertions[:8],
            "modal_distribution": prof.modal_particles,
            "onomatopoeia": prof.onomatopoeia[:6],
            "mention_targets": prof.mention_targets,
            "self_ref": raw.get("self_ref_counts", {}),
            "jp_mix_ratio": raw.get("jp_kana_ratio", 0),
            "en_mix_ratio": raw.get("en_word_ratio", 0),
        }

        return DistillationCard(
            pseudonym=pseudonym,
            behavioral=behavioral,
            structural=structural,
        )

    def build_artifact(self, pseudonym: str, provider=None) -> ProfileArtifact:
        """Build a versioned, consent-checked artifact without exposing raw text."""
        if not self.consent.is_active():
            raise PermissionError('PROFILE_CONSENT_REQUIRED')
        card = self.to_distillation_card(pseudonym)
        fname = self.participants.get(pseudonym)
        if not fname:
            raise KeyError(f'no source configured for participant {pseudonym}')
        path = (self.texts_dir / fname).resolve()
        if not path.is_file() or self.texts_dir.resolve() not in path.parents:
            raise ValueError('SOURCE_PATH_OUTSIDE_TEXTS_DIR')
        content = read_text(path)
        digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
        messages = load_normalized_messages(path, path.stem)
        observed = dict(card.behavioral)
        observed.pop('sample_lines', None)
        claims = {'topics': [], 'episodes': [], 'relationships': [], 'inferred_traits': []}
        warnings = ['style observations are not personality diagnoses']
        if provider is not None:
            try:
                claims = infer_claims(provider, messages)
            except Exception as exc:
                warnings.append(f'inference_failed:{type(exc).__name__}')
        return ProfileArtifact(
            profile_id=f'profile_{pseudonym}',
            participant_id=pseudonym,
            pseudonym=pseudonym,
            schema_version='1.0',
            created_at=datetime.now(UTC).isoformat(),
            source_manifest=[SourceManifest(
                source_id=path.stem, path=str(path), checksum=digest,
                message_count=len(messages), format=path.suffix.lower().lstrip('.') or 'plain',
            )],
            consent=self.consent,
            observed_style=observed,
            topics=claims['topics'],
            episodes=claims['episodes'],
            relationships=claims['relationships'],
            inferred_traits=claims['inferred_traits'],
            generation_policy={
                'raw_text_in_prompt': False,
            },
            quality={
                'sample_size': len(messages),
                'coverage': 1.0 if messages else 0.0,
                'warnings': warnings,
            },
        )

    def build_artifacts_all(self) -> dict[str, ProfileArtifact]:
        return {name: self.build_artifact(name) for name in self.profile_all()}

    def delete_artifact(self, pseudonym: str, output_dir: str | Path) -> int:
        """Delete derived JSON for a participant; source files are never deleted here."""
        path = Path(output_dir).resolve() / f'{pseudonym}.json'
        if path.exists():
            path.unlink()
            return 1
        return 0

    def to_agent_prompt(self, pseudonym: str, card: DistillationCard | None = None) -> str:
        if card is None:
            card = self.to_distillation_card(pseudonym)

        b = card.behavioral
        prof = self._profiles.get(pseudonym)
        lines = [f'以下是参与者“{pseudonym}”的候选语言风格说明，仅用于创作模拟，不代表其真实人格或身份：', ""]

        lines.append("【基本风格】")
        lines.append(
            f"- 消息均长{b['avg_msg_length']}字，"
            f"中位数{b['median_msg_length']}字，"
            f"{b['short_msg_ratio']:.0%}的消息不超过5个字"
        )
        lines.append(f"- {b['voice_summary']}")
        if b.get("pure_media_ratio", 0) > 0.1:
            lines.append(f"- {b['pure_media_ratio']:.0%}的消息是纯图片/表情")
        lines.append("")

        lines.append("【标志性手法】")
        for move in b.get("signature_moves", []):
            lines.append(f"- {move}")
        if b.get("top_phrases"):
            lines.append(f"- 高频词/短语：{'、'.join(b['top_phrases'][:5])}")
        lines.append("")

        lines.append("【标点与emoji】")
        lines.append(f"- {b['punctuation_style']}")
        lines.append(f"- {b['emoji_pattern']}")
        lines.append("")

        if b.get("bracket_samples"):
            lines.append("【括号自白】")
            for bs in b["bracket_samples"][:5]:
                lines.append(f"- （{bs}）")
            lines.append("")

        if b.get("onomatopoeia"):
            lines.append(f"【拟声词】{'、'.join(b['onomatopoeia'][:5])}")
            lines.append("")

        if card.structural:
            s = card.structural
            if s.dominant_discourse or s.capiton_signifiers:
                lines.append("【可选结构假设（需人工复核）】")
                if s.dominant_discourse:
                    lines.append(f"- 主导话语类型：{s.dominant_discourse}")
                if s.capiton_signifiers:
                    lines.append(f"- 缝合点能指：{'、'.join(s.capiton_signifiers[:5])}")
                if s.desire_direction:
                    lines.append(f"- 欲望方向：{s.desire_direction}")
                lines.append("")

        lines.append("【不要做的事】")
        lines.append("- 不要发长段落（你很少超过50字）")
        if prof and prof.short_msg_ratio > 0.3:
            lines.append("- 不要连续发多条完整句子（你习惯碎片化发送）")
        if prof and prof.question_ratio > 0.3:
            lines.append("- 不要减少问号的使用（问号是你的标志）")
        if b.get("jp_mix_ratio", 0) > 0.05:
            lines.append("- 不要刻意避免日语混用")
        lines.append("- 不要用正式书面语")

        return "\n".join(lines)

    def to_distillation_cards_all(self) -> dict[str, DistillationCard]:
        self.profile_all()
        return {name: self.to_distillation_card(name) for name in self._profiles}

    # --- private helpers ---

    def _auto_tags(self, name: str, raw: dict) -> list[str]:
        tags = []
        if raw["avg_msg_length"] < 10:
            tags.append("极短句")
        elif raw["avg_msg_length"] < 20:
            tags.append("短句主导")
        elif raw["avg_msg_length"] > 40:
            tags.append("长文倾向")

        if raw["emoji_density"] > 1.0:
            tags.append("emoji密集")
        if raw["question_ratio"] > 0.35:
            tags.append("问号高频")
        if raw["exclamation_ratio"] > 0.3:
            tags.append("感叹号高频")
        if raw["repeated_punct_ratio"] > 0.15:
            tags.append("重复标点")
        if raw.get("bracket_insertions") and len(raw["bracket_insertions"]) > 5:
            tags.append("括号自解构")
        if raw["pure_media_ratio"] > 0.2:
            tags.append("图包选手")
        if raw.get("jp_kana_ratio", 0) > 0.05:
            tags.append("日语混入")
        if raw.get("en_word_ratio", 0) > 0.1:
            tags.append("英文混入")
        if raw.get("self_corrections", 0) > 5:
            tags.append("自我修正")
        if raw.get("quote_reply_ratio", 0) > 0.1:
            tags.append("引用回复达人")
        return tags

    def _voice_summary(self, name: str, prof: BehavioralProfile, raw: dict) -> str:
        parts = []
        if raw["short_msg_ratio"] > 0.4:
            parts.append("以极短句为主，碎片化发送")
        elif raw["short_msg_ratio"] > 0.25:
            parts.append("短句与中等长度消息交替")
        else:
            parts.append("消息偏长，倾向完整表达")

        if raw["emoji_density"] > 1.5:
            parts.append("emoji使用密集")
        elif raw["emoji_density"] > 0.5:
            parts.append("适度使用emoji")

        if raw.get("jp_kana_ratio", 0) > 0.08:
            parts.append("频繁混入日语")
        if raw.get("en_word_ratio", 0) > 0.12:
            parts.append("常夹杂英文")

        if raw.get("bracket_insertions") and len(raw["bracket_insertions"]) > 8:
            parts.append("习惯用括号进行自我解构或补充")

        if raw.get("self_corrections", 0) > 8:
            parts.append("经常自我修正")

        if raw.get("quote_reply_ratio", 0) > 0.15:
            parts.append("喜欢引用回复")

        top_modal = sorted(raw.get("modal_particles", {}).items(), key=lambda x: -x[1])
        if top_modal:
            top3 = "、".join(f"{m}({c})" for m, c in top_modal[:3])
            parts.append(f"语气词偏好：{top3}")

        return "；".join(parts) + "。" if parts else "风格均衡，无明显偏向。"

    def _signature_moves(self, name: str, prof: BehavioralProfile, raw: dict) -> list[str]:
        moves = []
        if raw.get("bracket_insertions"):
            samples = raw["bracket_insertions"][:3]
            moves.append(f"括号自我解构：{'、'.join(f'（{s}）' for s in samples)}")
        if prof.signature_phrases:
            moves.append(f"个人标志性表达：{'、'.join(prof.signature_phrases[:3])}")
        if prof.unique_expressions:
            moves.append(f"独有表达：{'、'.join(prof.unique_expressions[:3])}")
        if raw.get("onomatopoeia"):
            moves.append(f"拟声词：{'、'.join(raw['onomatopoeia'][:3])}")
        if raw.get("self_ref_counts"):
            refs = "、".join(f"{k}({v})" for k, v in raw["self_ref_counts"].items())
            moves.append(f"自称方式：{refs}")
        if raw.get("jp_kana_ratio", 0) > 0.05:
            moves.append("日语假名/词汇混入")
        if raw.get("en_word_ratio", 0) > 0.1:
            en_samples = raw.get("en_word_samples", [])[:5]
            if en_samples:
                moves.append(f"英文混入：{', '.join(en_samples)}")
        return moves

    def _punct_style(self, prof: BehavioralProfile, raw: dict) -> str:
        parts = []
        if prof.question_ratio > 0.3:
            parts.append(f"问号密度高({prof.question_ratio:.0%}消息含？)")
        if prof.exclamation_ratio > 0.25:
            parts.append(f"感叹号常用({prof.exclamation_ratio:.0%}消息含！)")
        if prof.repeated_punct_ratio > 0.1:
            parts.append(f"重复标点率{prof.repeated_punct_ratio:.0%}")

        top_p = sorted(raw.get("top_punctuation", {}).items(), key=lambda x: -x[1])
        if top_p:
            top3 = "、".join(f"{ch}({d:.2f}/100字)" for ch, d in top_p[:3])
            parts.append(f"标点密度top3：{top3}")

        return "；".join(parts) if parts else "标点使用均衡"

    def _emoji_pattern(self, prof: BehavioralProfile, raw: dict) -> str:
        density = prof.emoji_density
        ratio = raw.get("emoji_msg_ratio", 0)
        if density < 0.2:
            return "几乎不用emoji"
        if density < 0.8:
            return f"emoji密度{density:.1f}/条，{ratio:.0%}的消息含emoji"
        return f"emoji密度{density:.1f}/条，{ratio:.0%}的消息含emoji，是重要表达手段"

    def _sample_lines(self, name: str, raw: dict) -> list[str]:
        fname = self.participants.get(name)
        if not fname:
            return []
        path = self.texts_dir / fname
        if not path.exists():
            return []
        msgs = load_participant_messages(path)
        candidates = [
            m for m in msgs
            if 5 < len(m) < 50
            and not m.startswith("[")
            and not m.startswith("@")
        ]
        step = max(1, len(candidates) // 8)
        return candidates[::step][:6]
