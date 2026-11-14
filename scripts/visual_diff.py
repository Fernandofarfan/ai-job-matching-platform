"""Compara dos carpetas de capturas (visual_snapshots.py) y marca las páginas que cambiaron.

    python scripts/visual_diff.py shots/base shots/head --diff shots/diff [--report-only]

Un píxel cuenta como distinto si algún canal cambia más que --tolerance (absorbe el antialiasing).
Una página cambió si el porcentaje de píxeles distintos supera --max-ratio, o si cambió su tamaño.
Sale con 1 si alguna cambió, salvo con --report-only. Deja una imagen con los cambios en rojo por página
y, en GitHub Actions, una tabla en el resumen del job.
"""
import argparse
import os
import sys
from pathlib import Path

from PIL import Image, ImageChops


def changed_ratio(before: Image.Image, after: Image.Image, tolerance: int) -> tuple[float, Image.Image]:
    """Fracción de píxeles distintos (0 a 1) y una máscara con esos píxeles. Las imágenes se comparan
    sobre el tamaño mayor: lo que sobra en una de las dos cuenta como distinto."""
    size = (max(before.width, after.width), max(before.height, after.height))
    canvas_a = Image.new('RGB', size, (255, 0, 255))
    canvas_b = Image.new('RGB', size, (0, 255, 0))
    canvas_a.paste(before.convert('RGB'))
    canvas_b.paste(after.convert('RGB'))
    diff = ImageChops.difference(canvas_a, canvas_b)
    bands = [band.point(lambda v: 255 if v > tolerance else 0) for band in diff.split()]
    mask = ImageChops.lighter(ImageChops.lighter(bands[0], bands[1]), bands[2])
    changed = mask.histogram()[255]
    return changed / (size[0] * size[1]), mask


def highlight(after: Image.Image, mask: Image.Image) -> Image.Image:
    """La captura nueva atenuada, con los píxeles distintos en rojo."""
    size = mask.size
    base = Image.new('RGB', size, (255, 255, 255))
    base.paste(after.convert('RGB'))
    faded = Image.blend(base, Image.new('RGB', size, (255, 255, 255)), 0.6)
    faded.paste(Image.new('RGB', size, (220, 0, 0)), mask=mask)
    return faded


def compare(base_dir: Path, head_dir: Path, diff_dir: Path | None, tolerance: int,
            max_ratio: float) -> list[tuple[str, str, float]]:
    """(captura, estado, % distinto) por página. Estados: 'igual', 'cambió', 'nueva', 'quitada'."""
    rows = []
    names = sorted({p.name for p in base_dir.glob('*.png')} | {p.name for p in head_dir.glob('*.png')})
    for name in names:
        before, after = base_dir / name, head_dir / name
        if not before.exists():
            rows.append((name, 'nueva', 100.0))
            continue
        if not after.exists():
            rows.append((name, 'quitada', 100.0))
            continue
        with Image.open(before) as a, Image.open(after) as b:
            ratio, mask = changed_ratio(a, b, tolerance)
            resized = a.size != b.size
            state = 'cambió' if resized or ratio > max_ratio else 'igual'
            if state == 'cambió' and diff_dir is not None:
                diff_dir.mkdir(parents=True, exist_ok=True)
                highlight(b, mask).save(diff_dir / name)
        rows.append((name, state, round(ratio * 100, 3)))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('base', type=Path)
    parser.add_argument('head', type=Path)
    parser.add_argument('--diff', type=Path)
    parser.add_argument('--tolerance', type=int, default=32)
    parser.add_argument('--max-ratio', type=float, default=0.002)
    parser.add_argument('--report-only', action='store_true')
    args = parser.parse_args()
    rows = compare(args.base, args.head, args.diff, args.tolerance, args.max_ratio)
    if not rows:
        sys.exit('No hay capturas para comparar')
    lines = ['| Página | Estado | % de píxeles distintos |', '|---|---|---|']
    lines += [f'| `{name}` | {state} | {ratio} |' for name, state, ratio in rows]
    report = '\n'.join(lines)
    print(report)
    summary = os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as f:
            f.write('## Comparación visual contra la rama base\n\n' + report + '\n')
    changed = [name for name, state, _ in rows if state != 'igual']
    if changed and not args.report_only:
        sys.exit(f'Cambiaron {len(changed)} páginas: {", ".join(changed)}. Si el cambio es buscado, '
                 "agregá la etiqueta 'cambio-visual' al PR y volvé a correr el job.")


if __name__ == '__main__':
    main()
