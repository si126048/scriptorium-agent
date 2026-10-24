import json
from pathlib import Path

import pytest

from scriptorium.behavioral import BehavioralProfiler, ConsentPolicy, SubjectProfiler
from scriptorium.behavioral.chat_parser import load_participant_messages, load_normalized_messages
from scriptorium.behavioral.config import load_participant_manifest
from scriptorium.behavioral.inference import infer_claims
from scriptorium.behavioral.materials import load_materials


def test_profile_artifact_has_manifest_and_no_raw_samples(tmp_path):
    (tmp_path / 'friend.txt').write_text('你好⏎\n哈哈！⏎\n', encoding='utf-8')
    profiler = BehavioralProfiler(tmp_path, participants={'friend': 'friend.txt'})
    artifact = profiler.build_artifact('friend')
    assert artifact.schema_version == '1.0'
    assert artifact.source_manifest[0].message_count == 2
    assert 'sample_lines' not in artifact.observed_style
    assert artifact.generation_policy['raw_text_in_prompt'] is False


def test_manifest_and_gb18030_input(tmp_path):
    source = tmp_path / 'friend.txt'
    source.write_bytes('你好\n'.encode('gb18030'))
    manifest = tmp_path / 'participants.json'
    manifest.write_text(json.dumps({'participants': [{'id': 'x', 'file': 'friend.txt'}]}), encoding='utf-8')
    assert load_participant_manifest(manifest) == {'x': 'friend.txt'}
    assert load_participant_messages(source) == ['你好']
    assert load_normalized_messages(source, 'source')[0]['message_id'].startswith('msg_')


class FakeInference:
    def generate_structured(self, *_args):
        return {'topics': [{'id': 'topic_1', 'text': '问候', 'evidence_span_ids': ['msg_bad'], 'confidence': 0.8, 'alternatives': ['礼貌用语']}], 'episodes': [], 'relationships': [], 'inferred_traits': []}


def test_inference_rejects_unknown_evidence():
    result = infer_claims(FakeInference(), [{'message_id': 'msg_ok', 'content': '你好'}])
    assert result['topics'] == []


def test_interview_materials_generate_stable_spans(tmp_path):
    interview = tmp_path / 'interview.json'
    interview.write_text(json.dumps({'turns': [
        {'question_id': 'A2', 'answer_text': '我通常先解释，再决定是否继续。', 'tags': ['misrecognition']},
    ]}, ensure_ascii=False), encoding='utf-8')
    manifest = tmp_path / 'sources.json'
    manifest.write_text(json.dumps({'sources': [{
        'source_id': 'interview_x', 'participant_id': 'p_x',
        'source_type': 'interview', 'path': 'interview.json', 'context': 'research'
    }]}), encoding='utf-8')
    sources, spans = load_materials(manifest)
    assert sources[0].source_type == 'interview'
    assert spans[0].question_id == 'A2'
    assert spans[0].span_id == load_materials(manifest)[1][0].span_id


class FakeStructuralProvider:
    def generate_structured(self, _system, payload, _model, _meta):
        return {'claims': [{
            'claim_id': 'claim_1', 'dimension': 'repeated_signifier',
            'text': '存在反复出现的解释性表达',
            'evidence_span_ids': [payload['allowed_span_ids'][0]],
            'source_types': ['interview'], 'confidence': 0.8,
            'alternatives': ['该表达可能只与本次访谈情境有关'],
        }]}


def test_subject_artifact_requires_evidence_and_review(tmp_path):
    interview = tmp_path / 'interview.json'
    interview.write_text(json.dumps({'turns': [{'question_id': 'A2', 'answer_text': '我先解释。'}]}, ensure_ascii=False), encoding='utf-8')
    manifest = tmp_path / 'sources.json'
    manifest.write_text(json.dumps({'sources': [{'source_id': 'i1', 'participant_id': 'p_x', 'source_type': 'interview', 'path': 'interview.json'}]}), encoding='utf-8')
    profiler = SubjectProfiler(manifest)
    artifact = profiler.build('p_x', provider=FakeStructuralProvider())
    assert artifact.structural_claims[0].status == 'candidate'
    assert artifact.generation_policy['subject_constraints'] == []
    reviewed = SubjectProfiler.apply_review(artifact, {'participant_id': 'p_x', 'decisions': [
        {'claim_id': 'claim_1', 'status': 'approved', 'reviewer_id': 'r1', 'reason': '复核通过'}
    ]})
    assert reviewed.review_state == 'approved'
    assert reviewed.generation_policy['subject_constraints'] == ['claim_1']
