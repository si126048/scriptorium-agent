"""Canonical editor JSON validation and deterministic Markdown projection."""
from .service import ResearchError

ALLOWED = {'doc', 'paragraph', 'heading', 'text', 'bulletList', 'orderedList', 'listItem',
           'blockquote', 'codeBlock', 'hardBreak', 'horizontalRule', 'citation', 'footnote', 'rawBlock'}


def validate_editor(node, depth=0):
    if not isinstance(node, dict) or node.get('type') not in ALLOWED or depth > 40:
        raise ResearchError('INVALID_EDITOR_DOCUMENT', 422)
    for mark in node.get('marks', []):
        if mark.get('type') not in {'bold', 'italic', 'strike', 'code', 'link'}:
            raise ResearchError('INVALID_EDITOR_MARK', 422)
        if mark.get('type') == 'link' and not str(mark.get('attrs', {}).get('href', '')).startswith(('https://', 'http://', '#')):
            raise ResearchError('UNSAFE_EDITOR_LINK', 422)
    for child in node.get('content', []):
        validate_editor(child, depth + 1)


def citation_ids(node):
    if not isinstance(node, dict):
        return []
    found = [node.get('attrs', {}).get('anchorId', '')] if node.get('type') == 'citation' else []
    return found + [aid for child in node.get('content', []) for aid in citation_ids(child)]


def markdown(node):
    typ = node.get('type')
    content = ''.join(markdown(n) for n in node.get('content', []))
    if typ == 'text':
        value = node.get('text', '')
        for mark in node.get('marks', []):
            value = {'bold': f'**{value}**', 'italic': f'*{value}*', 'strike': f'~~{value}~~',
                     'code': f'`{value}`'}.get(mark['type'], value)
        for mark in node.get('marks', []):
            if mark['type'] == 'link':
                value = '[' + value + '](' + mark['attrs']['href'] + ')'
        return value
    if typ == 'heading':
        return '#' * max(1, min(6, int(node.get('attrs', {}).get('level', 2)))) + ' ' + content + '\n\n'
    if typ == 'citation':
        return '[原文](#anchor-' + str(node.get('attrs', {}).get('anchorId', '')) + ')'
    if typ == 'footnote':
        return '[注：' + str(node.get('attrs', {}).get('text', '')) + ']'
    if typ == 'rawBlock':
        return str(node.get('attrs', {}).get('source', '')) + '\n\n'
    if typ == 'orderedList':
        start = node.get('attrs', {}).get('start', 1)
        return ''.join(f'{start + i}. {markdown(child).lstrip("- " ).strip()}\n'
                       for i, child in enumerate(node.get('content', []))) + '\n'
    if typ == 'listItem':
        return '- ' + content.strip() + '\n'
    if typ == 'blockquote':
        return '\n'.join('> ' + line for line in content.splitlines()) + '\n\n'
    if typ == 'codeBlock':
        return '```\n' + content + '\n```\n\n'
    if typ == 'hardBreak':
        return '\n'
    if typ == 'horizontalRule':
        return '\n---\n'
    return content + ('\n\n' if typ == 'paragraph' else '')
