"""Command line interface for Hermeneut.

The CLI is deliberately dependency-light so the complete Mock workflow works
without a web server or an API key.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from .db import Store
from .models import ConsentScope, Participant, Project, ReviewDecision, ReviewRequest
from .rag import ingest, search
from .workflow import Workflow

EXIT_USAGE = 2
EXIT_DOMAIN = 3


def _configure_console() -> None:
    """Keep Chinese output readable on Windows and redirected consoles."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


class CliError(RuntimeError):
    """A user-facing error with a stable exit code."""

    def __init__(self, message: str, code: int = EXIT_DOMAIN):
        super().__init__(message)
        self.code = code


def _json(value: Any, pretty: bool = False) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2 if pretty else None, default=str)


def _emit(value: Any, *, pretty: bool, output: str | None = None) -> None:
    text = _json(value, pretty)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text + "\n", encoding="utf-8")
        print(_json({"written": str(Path(output).resolve())}, pretty=False))
    else:
        print(text)


def _ensure_project(store: Store, project_id: str) -> Project:
    project = store.get_project(project_id)
    if project is None:
        project = store.create_project(Project(id=project_id))
    return project


def _source_for(store: Store, project_id: str, participant_id: str, source: str):
    docs = store.list_documents(project_id, participant_id)
    matches = [d for d in docs if d.id == source or d.origin == source or Path(d.origin).name == source]
    if not matches:
        raise CliError(f"source not found: {source}")
    if len(matches) > 1:
        raise CliError(f"source is ambiguous: {source}; use its document id")
    return matches[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hermeneut-agent",
        description="Adversarial multi-perspective discourse analysis toolkit.",
        epilog="常用流程：init → add-participant → add-source → analyze → review → export；主体画像使用 subject build。",
    )
    from . import __version__
    parser.add_argument("--version", action="version", version=f"hermeneut-agent {__version__}")
    parser.add_argument("--db", default=os.getenv("LACAN_DB_PATH", "./data/lacan.db"), help="SQLite path")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON output")
    parser.add_argument("--output", help="write the command result to a JSON file")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("interactive", aliases=["shell"], help="open the guided interactive terminal UI")

    p = sub.add_parser("init", help="create a local project")
    p.add_argument("--project", default="demo")

    p = sub.add_parser("ingest-theory", help="ingest a TXT, Markdown, or digital PDF theory source")
    p.add_argument("--path", required=True); p.add_argument("--project", default="demo")

    p = sub.add_parser("theory-search", aliases=["search"], help="search ingested theory sources")
    p.add_argument("query"); p.add_argument("--project", default="demo"); p.add_argument("--limit", type=int, default=5)

    p = sub.add_parser("add-participant", help="register an anonymised participant")
    p.add_argument("--id", required=True); p.add_argument("--project", default="demo"); p.add_argument("--consent", required=True)

    p = sub.add_parser("add-source", help="ingest an authorised participant source")
    p.add_argument("--participant", required=True); p.add_argument("--project", default="demo"); p.add_argument("--file", required=True)

    p = sub.add_parser("analyze", help="run the Evidence -> Interpreter -> Critic Mock workflow")
    p.add_argument("--participant", required=True); p.add_argument("--project", default="demo"); p.add_argument("--source", required=True)
    p.add_argument("--idempotency-key", default="cli-run"); p.add_argument("--mock", action="store_true", help="use the built-in provider")

    p = sub.add_parser("run-show", aliases=["status"], help="show a run, including audit events")
    p.add_argument("--run", required=True)

    p = sub.add_parser("review", help="approve, reject, or request revision")
    p.add_argument("--run", required=True); p.add_argument("--decision", choices=[x.value for x in ReviewDecision], required=True)
    p.add_argument("--reviewer", default="reviewer-1"); p.add_argument("--reason", default="")

    p = sub.add_parser("export", help="export an approved packet and typed graph")
    p.add_argument("--run", required=True); p.add_argument("--format", choices=["json"], default="json")

    p = sub.add_parser("withdraw", help="withdraw a participant and block future analysis")
    p.add_argument("--participant", required=True); p.add_argument("--project", default="demo")

    p = sub.add_parser("dialectical-analyze", help="run multi-perspective dialectical analysis")
    p.add_argument("--perspectives", required=True, help="comma-separated perspective IDs (e.g. lacan,deleuze)")
    p.add_argument("--participant", required=True); p.add_argument("--project", default="demo")
    p.add_argument("--source", required=True)
    p.add_argument("--idempotency-key", default="dialectical-run")
    p.add_argument("--report", action="store_true", help="generate Phase 4 comprehensive report")
    p.add_argument("--mock", action="store_true", help="use the built-in provider")

    p = sub.add_parser("doc-ingest", help="ingest a document into the PageIndex store")
    p.add_argument("--path", required=True); p.add_argument("--title", default=None)

    p = sub.add_parser("doc-search", help="search indexed documents")
    p.add_argument("query"); p.add_argument("--doc-id", default=None); p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("doc-outline", help="show document outline")
    p.add_argument("--doc-id", required=True)

    p = sub.add_parser("doc-verify", help="verify a quotation against source document")
    p.add_argument("--doc-id", required=True); p.add_argument("--quote", required=True); p.add_argument("--page", type=int, default=None)

    p = sub.add_parser("perspectives", help="list available theoretical perspectives")

    p = sub.add_parser("profile", help="generate versioned behavioral profile artifacts")
    p.add_argument("--participant", help=argparse.SUPPRESS)
    p.add_argument("--all", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--prompt", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--texts-dir", default="data/participant_texts", help=argparse.SUPPRESS)
    profile_sub = p.add_subparsers(dest="profile_command")
    pb = profile_sub.add_parser("build", help="build ProfileArtifact JSON")
    pb.add_argument("--participant")
    pb.add_argument("--all", action="store_true")
    pb.add_argument("--texts-dir", default="data/participant_texts")
    pb.add_argument("--config", help="JSON participant manifest")
    pb.add_argument("--cards-dir", help="write one JSON artifact per participant")
    pb.add_argument("--consent", help="JSON consent policy")
    ps = profile_sub.add_parser("show", help="show one profile artifact")
    ps.add_argument("--participant", required=True)
    ps.add_argument("--cards-dir", default="data/profile-cards")
    pe = profile_sub.add_parser("export", help="export one profile artifact")
    pe.add_argument("--participant", required=True)
    pe.add_argument("--texts-dir", default="data/participant_texts")
    pe.add_argument("--to", required=True, dest="artifact_path")
    pd = profile_sub.add_parser("delete", help="delete one derived profile artifact")
    pd.add_argument("--participant", required=True)
    pd.add_argument("--cards-dir", default="data/profile-cards")

    p = sub.add_parser("subject", help="build multi-source subject structure artifacts")
    subject_sub = p.add_subparsers(dest="subject_command", required=True)
    sb = subject_sub.add_parser("build", help="build a subject artifact from a sources manifest")
    sb.add_argument("--participant", required=True)
    sb.add_argument("--sources", required=True, help="JSON material sources manifest")
    sb.add_argument("--root", help="root directory containing source files")
    sb.add_argument("--cards-dir", default="data/subject-artifacts")
    sb.add_argument("--consent", help="JSON consent policy")
    sb.add_argument("--mock", action="store_true", help="use the offline structural candidate provider")
    sb.add_argument("--mode", choices=["full", "sample"], default="full")
    sb.add_argument("--batch-size", type=int, default=80)
    sb.add_argument("--with-relations", action="store_true", default=False)
    sb.add_argument("--aliases", help="JSON alias registry for directed interactions")
    ss = subject_sub.add_parser("show", help="show a subject artifact")
    ss.add_argument("--participant", required=True)
    ss.add_argument("--cards-dir", default="data/subject-artifacts")
    sr = subject_sub.add_parser("review", help="apply a JSON review file")
    sr.add_argument("--participant", required=True)
    sr.add_argument("--input", required=True)
    sr.add_argument("--cards-dir", default="data/subject-artifacts")
    se = subject_sub.add_parser("export", help="export a subject artifact")
    se.add_argument("--participant", required=True)
    se.add_argument("--cards-dir", default="data/subject-artifacts")
    se.add_argument("--to", required=True, dest="artifact_path")
    sd = subject_sub.add_parser("delete", help="delete a derived subject artifact")
    sd.add_argument("--participant", required=True)
    sd.add_argument("--cards-dir", default="data/subject-artifacts")
    for name, help_text in (("inspect-motifs", "inspect lexical and parody candidates"),
                            ("inspect-relations", "inspect directed interaction graph"),
                            ("show-batch-failures", "show failed analysis batches")):
        ip = subject_sub.add_parser(name, help=help_text)
        ip.add_argument("--participant", required=True)
        ip.add_argument("--cards-dir", default="data/subject-artifacts")
    return parser


def execute(args: argparse.Namespace) -> Any:
    if args.command in {"interactive", "shell"}:
        from .interactive import run_interactive
        return run_interactive(args.db)
    if os.getenv('HERMENEUT_DATABASE_URL') and os.getenv('HERMENEUT_RUNTIME') != 'sqlite':
        from .research.runtime import open_store
        store = open_store(getattr(args, 'project', 'cli-session'), resource_id=getattr(args, 'run', None) or getattr(args, 'doc_id', None))
    else:
        store = Store(args.db)
    provider = None
    if getattr(args, 'mock', False):
        from .llm import FakeProvider
        provider = FakeProvider()
    elif os.environ.get("DASHSCOPE_API_KEY"):
        from .llm import QwenProvider
        provider = QwenProvider()
    elif os.getenv('HERMENEUT_DATABASE_URL') and os.getenv('HERMENEUT_RUNTIME') != 'sqlite':
        from .research.runtime import get_provider
        provider = get_provider()
    flow = Workflow(store, provider)
    cmd = args.command
    if cmd == "init":
        return _ensure_project(store, args.project).model_dump()
    if cmd == "ingest-theory":
        _ensure_project(store, args.project)
        return ingest(store, args.path, args.project).model_dump(exclude={"text"})
    if cmd in {"theory-search", "search"}:
        _ensure_project(store, args.project)
        return {"items": search(store, args.query, max(1, min(args.limit, 5)))}
    if cmd == "add-participant":
        _ensure_project(store, args.project)
        try:
            consent = ConsentScope.model_validate(json.loads(Path(args.consent).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise CliError(f"invalid consent file: {exc}") from exc
        return store.put_participant(Participant(id=args.id, project_id=args.project, pseudonym=args.id, consent_scope=consent)).model_dump()
    if cmd == "add-source":
        participant = store.get_participant(args.project, args.participant)
        if participant is None:
            raise CliError(f"participant not found: {args.participant}")
        if participant.withdrawn_at:
            raise CliError("PARTICIPANT_WITHDRAWN")
        return ingest(store, args.file, args.project, args.participant, participant.consent_scope).model_dump(exclude={"text"})
    if cmd == "analyze":
        participant = store.get_participant(args.project, args.participant)
        if participant is None:
            raise CliError(f"participant not found: {args.participant}")
        document = _source_for(store, args.project, args.participant, args.source)
        run = flow.run(args.project, args.participant, [document.id], args.idempotency_key)
        return {"run_id": run.id, "state": run.state}
    if cmd in {"run-show", "status"}:
        run = store.get_run(args.run)
        if run is None:
            raise CliError(f"run not found: {args.run}")
        return run.model_dump(mode="json")
    if cmd == "review":
        return flow.review(args.run, ReviewRequest(reviewer_id=args.reviewer, decision=args.decision, reason=args.reason)).model_dump(mode="json")
    if cmd == "export":
        return flow.export(args.run)
    if cmd == "withdraw":
        participant = store.withdraw(args.project, args.participant)
        if participant is None:
            raise CliError(f"participant not found: {args.participant}")
        return {"participant_id": args.participant, "state": "WITHDRAWAL_REQUESTED"}
    if cmd == "dialectical-analyze":
        from .dialectical import DialecticalWorkflow
        from .perspectives import PerspectiveRegistry
        participant = store.get_participant(args.project, args.participant)
        if participant is None:
            raise CliError(f"participant not found: {args.participant}")
        document = _source_for(store, args.project, args.participant, args.source)
        registry = PerspectiveRegistry()
        perspective_ids = [p.strip() for p in args.perspectives.split(',')]
        perspectives = registry.load_many(perspective_ids)
        dw = DialecticalWorkflow(store, provider, perspectives)
        result = dw.run(args.project, args.participant, [document.id], args.idempotency_key,
                        generate_report=args.report)
        return result.model_dump(mode='json')
    if cmd == "doc-ingest":
        if hasattr(store, 'service'):
            from .research.worker import run_one
            p = Path(args.path)
            j = store.service.import_material(store.project_id, store.principal, p.read_bytes(), p.name, __import__('uuid').uuid4().hex)
            run_one(store.service, j['id'])
            return {'doc_id': j['payload']['asset_id'], 'status': 'indexed'}
        from .documents import DocumentStore
        doc_store = DocumentStore(store.conn)
        doc_id, page_count = doc_store.ingest(args.path, title=args.title)
        return {"doc_id": doc_id, "page_count": page_count, "status": "indexed"}
    if cmd == "doc-search":
        if hasattr(store, 'service'):
            return {'items': store.search_materials(args.query, store.project_id, args.limit)}
        from .documents import DocumentStore
        doc_store = DocumentStore(store.conn)
        results = doc_store.search(args.query, doc_id=args.doc_id, limit=args.limit)
        return {"items": results}
    if cmd == "doc-outline":
        if hasattr(store, 'service'):
            result = store.service.get_segments(store.project_id, store.principal, args.doc_id)
            return {'doc_id': args.doc_id, 'outline': [{'id': s['xml_id'], 'page': s['page_label']} for s in result['segments']]}
        from .documents import DocumentStore
        doc_store = DocumentStore(store.conn)
        doc = doc_store.get_document(args.doc_id)
        if doc is None:
            raise CliError(f"document not found: {args.doc_id}")
        return {"doc_id": args.doc_id, "title": doc['title'], "outline": doc.get('outline')}
    if cmd == "doc-verify":
        if hasattr(store, 'service'):
            from .documents.quote_verify import verify_quote
            result = store.service.get_segments(store.project_id, store.principal, args.doc_id)
            return {'doc_id': args.doc_id, 'result': verify_quote([s['text'] for s in result['segments']], args.quote, args.page)}
        from .documents import DocumentStore
        from .documents.quote_verify import verify_quote
        doc_store = DocumentStore(store.conn)
        pages = doc_store.get_all_pages(args.doc_id)
        if not pages:
            raise CliError(f"document not found or empty: {args.doc_id}")
        result = verify_quote(pages, args.quote, args.page)
        return {"doc_id": args.doc_id, "result": result}
    if cmd == "perspectives":
        from .perspectives import list_perspectives
        return {"perspectives": [{"id": p.id, "name": p.name, "concepts": len(p.concept_inventory)} for p in list_perspectives()]}
    if cmd == "profile":
        from .behavioral import BehavioralProfiler
        profile_cmd = getattr(args, 'profile_command', None) or 'build'
        texts_dir = getattr(args, 'texts_dir', 'data/participant_texts')
        manifest = None
        if getattr(args, 'config', None):
            from .behavioral.config import load_participant_manifest
            manifest = load_participant_manifest(args.config)
        consent = None
        if getattr(args, 'consent', None):
            consent = json.loads(Path(args.consent).read_text(encoding='utf-8'))
        profiler = BehavioralProfiler(texts_dir, args.db, participants=manifest, consent=consent)
        if profile_cmd == 'build':
            names = list(profiler.participants) if getattr(args, 'all', False) else [getattr(args, 'participant', None)]
            if not names or names == [None]:
                raise CliError('specify --participant or --all', EXIT_USAGE)
            artifacts = {name: profiler.build_artifact(name, provider=provider) for name in names if name}
            cards_dir = getattr(args, 'cards_dir', None)
            if cards_dir:
                out_dir = Path(cards_dir); out_dir.mkdir(parents=True, exist_ok=True)
                for name, artifact in artifacts.items():
                    (out_dir / f'{name}.json').write_text(artifact.model_dump_json(indent=2), encoding='utf-8')
                return {'status': 'ok', 'artifacts': len(artifacts), 'cards_dir': str(out_dir)}
            return {name: artifact.model_dump(mode='json') for name, artifact in artifacts.items()}
        if profile_cmd == 'show':
            path = Path(args.cards_dir) / f'{args.participant}.json'
            if not path.is_file():
                raise CliError(f'profile artifact not found: {path}')
            return json.loads(path.read_text(encoding='utf-8'))
        if profile_cmd == 'export':
            artifact = profiler.build_artifact(args.participant, provider=provider)
            Path(args.artifact_path).parent.mkdir(parents=True, exist_ok=True)
            Path(args.artifact_path).write_text(artifact.model_dump_json(indent=2), encoding='utf-8')
            return {'status': 'ok', 'written': str(Path(args.artifact_path).resolve())}
        if profile_cmd == 'delete':
            return {'deleted': profiler.delete_artifact(args.participant, args.cards_dir)}
        raise CliError(f'unknown profile command: {profile_cmd}', EXIT_USAGE)
    if cmd == "subject":
        from .behavioral import SubjectProfiler
        subject_cmd = args.subject_command
        cards_dir = Path(args.cards_dir)
        artifact_path = cards_dir / f'{args.participant}.json'
        if subject_cmd == 'build':
            consent = None
            if getattr(args, 'consent', None):
                try:
                    consent = json.loads(Path(args.consent).read_text(encoding='utf-8'))
                except (OSError, json.JSONDecodeError) as exc:
                    raise CliError(f'invalid consent file: {exc}') from exc
            profiler = SubjectProfiler(args.sources, root=args.root, consent=consent)
            if args.batch_size <= 0:
                raise CliError('--batch-size must be positive', EXIT_USAGE)
            aliases = None
            if getattr(args, 'aliases', None):
                try:
                    payload = json.loads(Path(args.aliases).read_text(encoding='utf-8'))
                    aliases = {str(item['participant_id']): [str(x) for x in item.get('aliases', [])]
                               for item in payload.get('participants', [])}
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    raise CliError(f'invalid alias registry: {exc}', EXIT_USAGE) from exc
            artifact = profiler.build(args.participant, provider=provider,
                                     batch_size=args.batch_size,
                                     with_relations=args.with_relations,
                                     aliases=aliases)
            cards_dir.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(artifact.model_dump_json(indent=2), encoding='utf-8')
            return {'status': 'ok', 'participant': args.participant, 'written': str(artifact_path.resolve()),
                    'claims': len(artifact.structural_claims), 'spans': artifact.quality.get('sample_size', 0)}
        if not artifact_path.is_file():
            raise CliError(f'subject artifact not found: {artifact_path}')
        from .behavioral.models import ProfileArtifact
        try:
            artifact = ProfileArtifact.model_validate_json(artifact_path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise CliError(f'invalid subject artifact: {exc}') from exc
        if subject_cmd == 'show':
            return artifact.model_dump(mode='json')
        if subject_cmd == 'inspect-motifs':
            return {'lexical_motifs': artifact.lexical_motifs, 'parody_variants': [x.model_dump() for x in artifact.parody_variants]}
        if subject_cmd == 'inspect-relations':
            return {'interaction_events': [x.model_dump() for x in artifact.interaction_events],
                    'relationship_claims': [x.model_dump() for x in artifact.relationship_claims],
                    'relation_graph': artifact.relation_graph.model_dump()}
        if subject_cmd == 'show-batch-failures':
            return {'batches': [x for x in artifact.analysis_batches if x.get('status') == 'failed']}
        if subject_cmd == 'review':
            if not artifact.structural_claims:
                return {'status': 'ok', 'review_state': artifact.review_state,
                        'warning': 'no structural claims to review; run subject build with DASHSCOPE_API_KEY set'}
            try:
                review = json.loads(Path(args.input).read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as exc:
                raise CliError(f'invalid review file: {exc}') from exc
            artifact = SubjectProfiler.apply_review(artifact, review)
            artifact_path.write_text(artifact.model_dump_json(indent=2), encoding='utf-8')
            return {'status': 'ok', 'review_state': artifact.review_state, 'written': str(artifact_path.resolve())}
        if subject_cmd == 'export':
            Path(args.artifact_path).parent.mkdir(parents=True, exist_ok=True)
            Path(args.artifact_path).write_text(artifact.model_dump_json(indent=2), encoding='utf-8')
            return {'status': 'ok', 'written': str(Path(args.artifact_path).resolve())}
        if subject_cmd == 'delete':
            artifact_path.unlink()
            return {'deleted': 1, 'participant': args.participant}
        raise CliError(f'unknown subject command: {subject_cmd}', EXIT_USAGE)
    raise CliError(f"unknown command: {cmd}", EXIT_USAGE)


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    logging.basicConfig(level=os.environ.get('LACAN_LOG_LEVEL', 'WARNING'), format='%(levelname)s %(name)s: %(message)s')
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        result = execute(args)
        if isinstance(result, int):
            return result
        _emit(result, pretty=args.pretty, output=args.output)
        return 0
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    except (PermissionError, KeyError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DOMAIN


if __name__ == "__main__":
    raise SystemExit(main())
