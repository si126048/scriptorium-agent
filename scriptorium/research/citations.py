"""Exact, auditable citation alignment. No fuzzy matching or Unicode normalization."""
from .service import ResearchError


def align(text, quote, start=None, end=None, prefix='', suffix=''):
    if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text) and text[start:end] == quote:
        return start, end, 'model_position_verified'
    matches, cursor = [], 0
    while quote and (found := text.find(quote, cursor)) >= 0:
        right = found + len(quote)
        if (not prefix or text[:found].endswith(prefix)) and (not suffix or text[right:].startswith(suffix)):
            matches.append((found, right))
        cursor = found + 1
    if len(matches) == 1:
        return *matches[0], 'unique_exact_quote' if not prefix and not suffix else 'context_disambiguated'
    raise ResearchError('CITATION_AMBIGUOUS' if matches else 'CITATION_EXACT_QUOTE_NOT_FOUND', 422)


def citation_objects(result):
    for finding in result.findings:
        yield from finding.citations
    if result.immanent:
        yield from result.immanent.citations
    if result.parallax:
        yield from result.parallax.citations


def validate_citations(result, readable):
    corrections = []
    for index, citation in enumerate(citation_objects(result)):
        source = next((s for s in readable if s['id'] == citation.segment_id), None)
        if source is None:
            raise ResearchError('CITATION_OUTSIDE_READ_SCOPE', 422)
        start, end, basis = align(source['text'], citation.exact_quote, citation.start_codepoint,
                                citation.end_codepoint, citation.prefix, citation.suffix)
        corrections.append({'index': index, 'segment_id': source['id'], 'basis': basis,
            'model_start': citation.start_codepoint, 'model_end': citation.end_codepoint,
            'start': start + source['source_offset'], 'end': end + source['source_offset'],
            'version_id': source['version_id']})
        citation.start_codepoint, citation.end_codepoint = start, end
    return corrections


def sanitize_citations(result, readable):
    """AUTO mode: keep exact citations, drop the rest and report what was dropped."""
    corrections, dropped = [], []

    def keep(citation):
        source = next((s for s in readable if s['id'] == citation.segment_id), None)
        if source is None:
            dropped.append({'segment_id': citation.segment_id, 'quote': citation.exact_quote,
                            'reason': 'CITATION_OUTSIDE_READ_SCOPE'})
            return False
        try:
            start, end, basis = align(source['text'], citation.exact_quote, citation.start_codepoint,
                                      citation.end_codepoint, citation.prefix, citation.suffix)
        except ResearchError as exc:
            dropped.append({'segment_id': citation.segment_id, 'quote': citation.exact_quote,
                            'reason': exc.code})
            return False
        corrections.append({'index': len(corrections), 'segment_id': source['id'], 'basis': basis,
                            'model_start': citation.start_codepoint, 'model_end': citation.end_codepoint,
                            'start': start + source['source_offset'], 'end': end + source['source_offset'],
                            'version_id': source['version_id']})
        citation.start_codepoint, citation.end_codepoint = start, end
        return True

    for finding in result.findings:
        finding.citations = [citation for citation in finding.citations if keep(citation)]
    if result.immanent:
        result.immanent.citations = [citation for citation in result.immanent.citations if keep(citation)]
    if result.parallax:
        result.parallax.citations = [citation for citation in result.parallax.citations if keep(citation)]
    return corrections, dropped
