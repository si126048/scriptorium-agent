from pathlib import Path

import click

from .pipeline import extract, load_segments, save_result


@click.group()
def main():
    """TopoStyle command line tools."""

@main.command()
@click.argument("corpus", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--output", "output_dir", default="artifacts", type=click.Path(path_type=Path))
def extract_cmd(corpus: Path, output_dir: Path):
    """Extract embeddings, persistence diagrams and co-occurrence graph."""
    segments = load_segments(corpus)
    result = extract(segments)
    save_result(result, output_dir)
    click.echo(f"完成：{len(segments)} 个片段，H0-H{len(result.diagrams)-1}，输出 {output_dir}")

main.add_command(extract_cmd, "extract")

if __name__ == "__main__":
    main()
