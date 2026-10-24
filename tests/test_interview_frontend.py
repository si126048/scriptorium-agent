from pathlib import Path


def test_web_ui_contains_interview_surface_without_removing_existing_modules():
    html = (Path(__file__).parents[1] / 'scriptorium' / 'static' / 'index.html').read_text(encoding='utf-8')
    for marker in ('panel-interview', 'mode-interview', 'handleMainSend', 'interview-start', 'interview-reset', 'interview-complete', 'interview-withdraw'):
        assert marker in html
    for marker in ('panel-perspectives', 'panel-documents', 'panel-search', 'btn-analyze', 'btn-dialectical'):
        assert marker in html
    assert '/api/v1/interviews' in html
    assert 'scriptorium_conversation_messages' in html
    assert '清零当前访谈并重新开始' in html
    assert 'prefers-reduced-motion' in html
    assert '--paper: #f7f7f5' in html
