"""Install the local Consilium package; no network, credentials or replacement."""
import argparse
from pathlib import Path
import shutil

FILES = ('SKILL.md', 'README.md', 'README.ru.md', 'LICENSE', 'VERSION', '.gitignore')
DIRS = ('agents', 'assets', 'references', 'scripts')


def destination(platform, project=None, user_home=None):
    base = Path(project).expanduser().resolve() if project is not None else (
        Path(user_home).resolve() if user_home is not None else Path.home())
    return base / ('.claude' if platform == 'claude' else '.agents') / 'skills' / 'consilium'


def install(source, target):
    source, target = Path(source).resolve(), Path(target).absolute()
    if target.exists() or target.is_symlink():
        raise ValueError('Destination exists; preserve it before choosing an update location')
    if target == source or source in target.parents:
        raise ValueError('Destination must be outside the source package')
    entries = [source / name for name in FILES + DIRS]
    for entry in entries:
        if not entry.exists() or entry.is_symlink():
            raise ValueError('Package entry missing or symlinked: ' + entry.name)
        if entry.is_dir() and any(p.is_symlink() for p in entry.rglob('*')):
            raise ValueError('Package directories must not contain symlinks')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()  # Exclusive creation; an existing destination is never replaced.
    try:
        for entry in entries:
            if entry.is_dir():
                shutil.copytree(entry, target / entry.name,
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            else:
                shutil.copy2(entry, target / entry.name)
    except Exception:
        # Only this newly created directory is removed on a failed install.
        shutil.rmtree(target)
        raise
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', required=True, choices=('claude', 'codex'))
    parser.add_argument('--project', type=Path, help='Project root; otherwise install for the current user')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    target = destination(args.platform, args.project)
    if args.dry_run:
        print(target)
        return
    try:
        print(install(Path(__file__).resolve().parents[1], target))
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    main()
