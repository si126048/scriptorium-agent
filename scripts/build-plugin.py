"""Build a plugin-only wheel and portable installation bundle; never publish or install."""

import hashlib
import json
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    out = root / "output" / f"scriptorium-{version}"
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(root),
            "--no-deps",
            "--no-build-isolation",
            "--no-cache-dir",
            "-w",
            str(out),
        ],
        check=True,
    )
    wheel = out / f"scriptorium-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert all(
            n.startswith(("scriptorium/plugin/", "scriptorium-"))
            or n in {"scriptorium/__init__.py", "scriptorium/__main__.py"}
            for n in names
        )
        assert not any(n.endswith((".sqlite3", ".db", ".env")) for n in names)
    bundle = out / f"scriptorium-{version}-plugin.zip"
    source_files = [
        root / p for p in ["pyproject.toml", "README.md", "LICENSE", "LICENSE-MISAKA", "NOTICE"]
    ]
    source_files += list((root / "scriptorium").rglob("*.py"))
    sources = {p.relative_to(root).as_posix(): digest(p) for p in sorted(source_files)}
    source_digest = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(wheel, wheel.name)
        for p in [root / "README.md", root / "LICENSE", root / "LICENSE-MISAKA", root / "NOTICE"]:
            archive.write(p, p.name)
        for directory in ["integrations", "docs/assets"]:
            for p in sorted((root / directory).glob("*")):
                if p.is_file():
                    archive.write(p, p.relative_to(root).as_posix())
        for name in ["writing.md", "plugin-integration.md", "migration.md"]:
            p = root / "docs" / name
            archive.write(p, "docs/" + name)
        archive.writestr(
            "INSTALL.md",
            f"# Scriptorium {version}\n\n"
            f"Install: `python -m pip install {wheel.name}`\n\n"
            "Requires Python 3.12+; dependencies are downloaded by pip. This is not an offline bundle.\n\n"
            "Check: `python -m scriptorium doctor`\n\n"
            "Configure: `python -m scriptorium config --host codex --workspace /YOUR/RESEARCH`\n\n"
            "The workspace must exist. No materials are preloaded. Merge the generated fragment into your host configuration.\n",
        )
    manifest = {
        "version": version,
        "source_digest": source_digest,
        "sources": sources,
        "artifacts": [
            {"file": p.name, "bytes": p.stat().st_size, "sha256": digest(p)}
            for p in [wheel, bundle]
        ],
        "contains_user_materials": False,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(out), "artifacts": manifest["artifacts"]}))


if __name__ == "__main__":
    main()
