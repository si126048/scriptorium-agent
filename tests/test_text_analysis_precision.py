from scriptorium.behavioral.models import RelationshipClaim
from scriptorium.behavioral.text_analysis import (
    build_relation_graph, detect_transform_candidates, make_windows,
    stable_expression_candidates,
)


def _message(i, text, day='2026-01-01', sender='a'):
    return {
        'message_id': f'msg_{i}', 'source_id': 'chat', 'participant_id': 'p_a',
        'sender_id': sender, 'sender_raw': sender, 'timestamp': f'{day}T10:00:00',
        'raw_text': text, 'normalized_text': text, 'message_index': i,
        'char_start': i, 'char_end': i + len(text), 'mention_targets': [],
    }


def test_full_windows_cover_middle_and_tail_with_overlap():
    messages = [_message(i, f'm{i}', day=f'2026-01-{i + 1:02d}') for i in range(5)]
    windows = make_windows(messages, batch_size=2, overlap=1)
    assert {m.message_id for w in windows for m in w.messages} == {f'msg_{i}' for i in range(5)}
    assert len(windows) >= 3


def test_variant_keeps_raw_and_does_not_promote_single_meme():
    messages = [_message(0, '好！！'), _message(1, '临时梗')]
    annotations = detect_transform_candidates(messages)
    assert any(a.raw_form == '好！！' and a.canonical_form == '好！' for a in annotations)
    motifs = stable_expression_candidates(annotations, messages)
    assert all(item['stable'] is False for item in motifs)


def test_relation_claim_has_direction_and_graph_trace():
    claim = RelationshipClaim(
        claim_id='r1', actor_id='a', target_id='b', relation_type='support',
        text='候选支持', evidence_span_ids=['span_1'], confidence=.7,
    )
    assert claim.direction == 'directed'
    graph = build_relation_graph([])
    assert graph.directed_edges == []
