"""Repair broken data symlinks in a PyInstaller macOS .app bundle.

PyInstaller's macOS BUNDLE step splits the onedir output between
Contents/Frameworks (binaries) and Contents/Resources (pure data), leaving a
symlink in Frameworks pointing at Resources. For directories that are 100%
data with no compiled binary mixed in (observed with this app's own
static/templates dirs, and with pytz's zoneinfo data), PyInstaller sometimes
creates the Frameworks symlink but never materializes the Resources side —
leaving a dangling symlink and a runtime FileNotFoundError / missing-data
error the first time that path is touched.

The onedir COLLECT output (dist/FolioSenseAI/_internal/...) always has the
real files, since this bug is specific to the BUNDLE step, not COLLECT. This
script walks the .app for broken symlinks and heals each one by copying the
real file/directory from the onedir output. Run after `pyinstaller ...spec`
and before packaging the DMG.

Usage: python packaging/pyinstaller/fix_macos_bundle_symlinks.py <dist_dir>
"""

import shutil
import sys
from pathlib import Path


def _iter_broken_symlinks(root: Path):
    for path in root.rglob("*"):
        if path.is_symlink() and not path.exists():
            yield path


def main() -> int:
    dist_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist")
    app_bundles = list(dist_dir.glob("*.app"))
    if not app_bundles:
        print(f"No .app bundle found under {dist_dir}", file=sys.stderr)
        return 1
    app = app_bundles[0]
    resources = app / "Contents" / "Resources"

    # The onedir build (same PyInstaller run) is the known-good source: its
    # _internal/ directory holds every collected data file as a real file.
    onedir_internal = None
    for candidate in dist_dir.iterdir():
        internal = candidate / "_internal"
        if internal.is_dir():
            onedir_internal = internal
            break
    if onedir_internal is None:
        print("No onedir _internal/ output found alongside the .app bundle; "
              "cannot repair broken symlinks.", file=sys.stderr)
        return 1

    frameworks = app / "Contents" / "Frameworks"
    healed = []
    still_broken = []
    for link in _iter_broken_symlinks(app):
        # Case 1: Frameworks/<rel> -> ../Resources/<rel>, but Resources/<rel> was
        # never materialized. The onedir COLLECT output (same PyInstaller run)
        # always has the real file at _internal/<rel>.
        if "Frameworks" in link.parts:
            rel = link.relative_to(frameworks)
            source = onedir_internal / rel
            target = resources / rel
        else:
            # Case 2: a top-level convenience symlink elsewhere in the bundle
            # (observed for pyarrow's libarrow*.dylib under Resources/) whose
            # relative target was never materialized where it points, but the
            # real file exists elsewhere in the bundle (e.g. under Frameworks,
            # where binaries are correctly placed for code-signing). Resolve by
            # basename search rather than assuming a fixed direction.
            basename = link.name
            candidates = [p for p in frameworks.rglob(basename) if not p.is_symlink()]
            if not candidates:
                candidates = [p for p in onedir_internal.rglob(basename) if not p.is_symlink()]
            if not candidates:
                still_broken.append(link)
                continue
            source = candidates[0]
            target = link  # replace the symlink itself with a real copy in place

        if not source.exists():
            still_broken.append(link)
            continue
        if target != link:
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            link.unlink()
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
        healed.append(target.relative_to(app))

    for rel in healed:
        print(f"Healed broken symlink data: {rel}")

    remaining = list(_iter_broken_symlinks(app))
    if remaining:
        print(f"{len(remaining)} broken symlink(s) remain after repair:", file=sys.stderr)
        for link in remaining:
            print(f"  {link}", file=sys.stderr)
        return 1

    print(f"Healed {len(healed)} broken symlink(s); 0 remain.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
