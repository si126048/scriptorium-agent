from scriptorium.research.citations import sanitize_citations
from scriptorium.research.methods import Citation, Finding, MethodResult


def test_auto_mode_keeps_exact_citations_and_drops_the_rest():
    readable = [{'id': 's1', 'text': '自由不是脱离制度条件的选择。', 'source_offset': 10, 'version_id': 'v1'}]
    result = MethodResult(
        summary='材料把自由放在制度条件里讨论。',
        outcome='difference_only',
        findings=[Finding(
            title='制度条件',
            text='自由不是脱离条件的选择。',
            claim_type='interpretation',
            citations=[
                Citation(segment_id='s1', exact_quote='脱离制度条件'),
                Citation(segment_id='s1', exact_quote='材料里没有这句话'),
                Citation(segment_id='outside', exact_quote='自由'),
            ],
        )],
    )

    corrections, dropped = sanitize_citations(result, readable)

    assert len(corrections) == 1
    assert corrections[0]['start'] == 14 and corrections[0]['end'] == 20
    assert result.findings[0].citations[0].start_codepoint == 4
    assert [item['reason'] for item in dropped] == [
        'CITATION_EXACT_QUOTE_NOT_FOUND', 'CITATION_OUTSIDE_READ_SCOPE']


def test_auto_mode_keeps_a_result_when_every_citation_is_invalid():
    result = MethodResult(
        summary='解释保留，但引文全部无法定位。',
        outcome='undetermined',
        findings=[Finding(title='未定位', text='待补证。', claim_type='inference',
                          citations=[Citation(segment_id='s1', exact_quote='不存在')])],
    )
    corrections, dropped = sanitize_citations(result, [{'id': 's1', 'text': '原文', 'source_offset': 0,
                                                        'version_id': 'v1'}])
    assert corrections == []
    assert result.findings[0].citations == []
    assert dropped[0]['reason'] == 'CITATION_EXACT_QUOTE_NOT_FOUND'
