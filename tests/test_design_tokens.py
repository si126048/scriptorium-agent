import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'


def test_dead_stylesheets_are_gone():
    for relative in ('src/features/workspace/workspace.css',
                     'src/features/workspace/experience.css',
                     'src/components/startup/startup.css'):
        assert not (WEB / relative).exists(), relative


def test_tokens_own_light_and_dark_theme():
    text = (WEB / 'src/features/workspace/design-tokens.css').read_text(encoding='utf-8')
    assert ':root{' in text
    assert ':root[data-theme="dark"]' in text
    assert '--fd-orange' in text and '--fd-seam' in text
    assert '--wb-orange:var(--fd-orange)' in text


def test_entry_stylesheet_only_imports_tokens_and_base():
    text = (WEB / 'src/index.css').read_text(encoding='utf-8').strip()
    assert '@import "tailwindcss"' not in text
    assert not re.search(r'#[0-9a-fA-F]{3,8}\b', text)
    assert 'design-tokens.css' in text and 'base.css' in text


def test_tailwind_is_not_part_of_the_build():
    config = (WEB / 'vite.config.ts').read_text(encoding='utf-8')
    assert 'tailwind' not in config
    package = json.loads((WEB / 'package.json').read_text(encoding='utf-8'))
    deps = {**package.get('dependencies', {}), **package.get('devDependencies', {})}
    assert not any('tailwind' in name for name in deps)


def test_document_language_and_theme_color():
    html = (WEB / 'index.html').read_text(encoding='utf-8')
    assert '<html lang="zh-CN">' in html
    assert 'name="theme-color"' in html
    assert 'initTheme' in (WEB / 'src/main.tsx').read_text(encoding='utf-8')
