from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_static_fallback_is_a_build_notice_not_a_second_ui():
    """The old single-file console was removed; the fallback must only explain how to build."""
    html = (ROOT / 'scriptorium' / 'static' / 'index.html').read_text(encoding='utf-8')
    assert '前端资源尚未构建' in html
    assert 'npm --prefix web run build' in html
    assert 'compose.research.lite.yml' in html
    assert '/docs' in html
    assert len(html) < 5000
    assert 'panel-interview' not in html


def test_workspace_keeps_the_interview_surface():
    workspace = (ROOT / 'web/src/features/workspace/UnifiedWorkspace.tsx').read_text(encoding='utf-8')
    composer = (ROOT / 'web/src/features/workspace/components/ResearchComposer.tsx').read_text(encoding='utf-8')
    for marker in ("panel === 'interview'", "'pause'", "'resume'", "'complete'", "'reset'"):
        assert marker in workspace
    assert '研究问题或访谈回答' in composer
