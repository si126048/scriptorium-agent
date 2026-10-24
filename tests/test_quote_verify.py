from scriptorium.documents.quote_verify import normalize_for_quote_match, verify_quote, locate_quote


def test_normalize_removes_hyphen_linebreak():
    assert normalize_for_quote_match('hel-\nlo') == 'hello'


def test_normalize_removes_soft_hyphen():
    assert normalize_for_quote_match('hel\u00adlo') == 'hello'


def test_normalize_nfkc():
    assert normalize_for_quote_match('café') == normalize_for_quote_match('café')


def test_normalize_strips_whitespace():
    assert normalize_for_quote_match('  hello   world  ') == 'helloworld'


def test_verify_quote_on_page():
    pages = ['first page text', 'second page has the quote', 'third page']
    result = verify_quote(pages, 'has the quote', page_hint=2)
    assert result is not None
    assert result['status'] == 'on_page'
    assert result['page'] == 2


def test_verify_quote_elsewhere():
    pages = ['first page text', 'second page has the quote', 'third page']
    result = verify_quote(pages, 'has the quote', page_hint=1)
    assert result is not None
    assert result['status'] == 'elsewhere'
    assert result['page'] == 2


def test_verify_quote_not_found():
    pages = ['first page text', 'second page text', 'third page']
    result = verify_quote(pages, 'nonexistent quote')
    assert result is None


def test_verify_quote_empty_quote():
    pages = ['some text']
    assert verify_quote(pages, '') is None


def test_verify_quote_no_hint_searches_all():
    pages = ['aaa', 'bbb', 'ccc target']
    result = verify_quote(pages, 'target')
    assert result is not None
    assert result['page'] == 3


def test_verify_quote_with_whitespace_differences():
    pages = ['The   quick   brown   fox']
    result = verify_quote(pages, 'The quick brown fox')
    assert result is not None
    assert result['status'] == 'on_page'


def test_verify_quote_with_linebreak_hyphen():
    pages = ['The concept of hel-\nlo world']
    result = verify_quote(pages, 'hello world')
    assert result is not None


def test_locate_quote_on_page():
    pages = ['aaa', 'bbb target']
    assert locate_quote(pages, 'target', page_hint=2) == 'on_page'


def test_locate_quote_elsewhere():
    pages = ['aaa', 'bbb target']
    assert locate_quote(pages, 'target', page_hint=1) == 'elsewhere'


def test_locate_quote_not_found():
    pages = ['aaa', 'bbb']
    assert locate_quote(pages, 'target') == 'not_found'


def test_verify_quote_page_count():
    pages = ['a', 'b', 'c']
    result = verify_quote(pages, 'a')
    assert result['page_count'] == 3


def test_verify_quote_invalid_page_hint():
    pages = ['aaa', 'bbb target']
    result = verify_quote(pages, 'target', page_hint=99)
    assert result is not None
    assert result['status'] == 'on_page'
    assert result['page'] == 2
