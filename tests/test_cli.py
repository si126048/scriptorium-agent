import json
from scriptorium.cli import main

def test_cli_workflow(tmp_path, capsys):
    db = str(tmp_path / "cli.db")
    theory = tmp_path / "theory.md"; theory.write_text("Repetition changes meaning.", encoding="utf-8")
    story = tmp_path / "story.txt"; story.write_text("A door. A door again.", encoding="utf-8")
    consent = tmp_path / "consent.json"; consent.write_text(json.dumps({"research_analysis": True, "generation": True}), encoding="utf-8")
    assert main(["--db", db, "init", "--project", "p"]) == 0
    assert main(["--db", db, "ingest-theory", "--project", "p", "--path", str(theory)]) == 0
    assert main(["--db", db, "add-participant", "--project", "p", "--id", "A", "--consent", str(consent)]) == 0
    assert main(["--db", db, "add-source", "--project", "p", "--participant", "A", "--file", str(story)]) == 0
    assert main(["--db", db, "analyze", "--project", "p", "--participant", "A", "--source", "story.txt"]) == 0
    run_id = json.loads(capsys.readouterr().out.splitlines()[-1])["run_id"]
    assert main(["--db", db, "review", "--run", run_id, "--decision", "approve"]) == 0
    output = tmp_path / "export.json"
    assert main(["--db", db, "--output", str(output), "export", "--run", run_id]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["graph"]["edges"]

def test_cli_rejects_missing_source(tmp_path, capsys):
    db = str(tmp_path / "cli.db")
    main(["--db", db, "init", "--project", "p"])
    assert main(["--db", db, "analyze", "--project", "p", "--participant", "A", "--source", "missing"]) == 3
    assert "participant not found" in capsys.readouterr().err
