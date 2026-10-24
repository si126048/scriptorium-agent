from scriptorium.documents.outline import build_text_tree


def test_no_structure_returns_none():
    pages = ['just some text', 'more text here', 'and more']
    assert build_text_tree(pages) is None


def test_chapter_headings():
    pages = [
        'CHAPTER I\n\nThe Beginning',
        'Some content here',
        'CHAPTER II\n\nThe Middle',
        'More content',
        'CHAPTER III\n\nThe End',
        'Final content',
    ]
    tree = build_text_tree(pages)
    assert tree is not None
    assert len(tree) >= 3
    assert tree[0]['title']
    assert tree[0]['start_index'] == 1


def test_book_and_chapter_nesting():
    pages = [
        'BOOK I\n\nContent',
        'CHAPTER I\n\nContent',
        'CHAPTER II\n\nContent',
        'BOOK II\n\nContent',
        'CHAPTER I\n\nContent',
        'CHAPTER II\n\nContent',
    ]
    tree = build_text_tree(pages)
    assert tree is not None
    assert len(tree) >= 2
    book1 = tree[0]
    assert 'BOOK' in book1['title'].upper() or 'I' in book1['title']
    assert 'nodes' in book1


def test_markdown_headings():
    pages = [
        '# Introduction\n\nSome text',
        '## Background\n\nMore text',
        '## Methods\n\nEven more',
        '# Results\n\nData here',
        '## Finding 1\n\nDetails',
        '# Conclusion\n\nFinal',
    ]
    tree = build_text_tree(pages, markdown=True)
    assert tree is not None
    assert len(tree) >= 3


def test_running_head_removed():
    pages = [
        'THE GREAT GATSBY',
        'Chapter 1 content',
        'THE GREAT GATSBY',
        'Chapter 2 content',
        'THE GREAT GATSBY',
        'Chapter 3 content',
        'THE GREAT GATSBY',
    ]
    tree = build_text_tree(pages)
    if tree:
        titles = [n['title'] for n in tree]
        assert 'THE GREAT GATSBY' not in titles or len([t for t in titles if 'GATSBY' in t]) <= 1


def test_fewer_than_min_nodes():
    pages = ['CHAPTER I\n\nOnly one chapter']
    assert build_text_tree(pages) is None


def test_mixed_languages():
    pages = [
        'LIVRE PREMIER\n\nContenu du livre',
        'CHAPITRE I\n\nContenu du chapitre',
        'CHAPITRE II\n\nSuite',
        'CHAPITRE III\n\nFin',
    ]
    tree = build_text_tree(pages)
    assert tree is not None


def test_node_structure():
    pages = [
        'CHAPTER I\n\nFirst',
        'Content A',
        'CHAPTER II\n\nSecond',
        'Content B',
        'CHAPTER III\n\nThird',
        'Content C',
    ]
    tree = build_text_tree(pages)
    assert tree is not None
    for node in tree:
        assert 'title' in node
        assert 'node_id' in node
        assert 'start_index' in node
        assert 'end_index' in node
        assert node['start_index'] >= 1
        assert node['end_index'] >= node['start_index']
