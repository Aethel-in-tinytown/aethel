"""Explicit provisioning of checksum-pinned, pickle-free English resources.

Runtime uses only the selected directory, never NLTK's downloader or search path.
Archives and their license/readme files remain alongside the extracted models.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

from . import config

NLTK_VERSION = "3.9.2"
DATA = Path(__file__).with_name("nlp_data")


class LanguageError(RuntimeError):
    """A selected backend cannot safely continue this life."""


def data_dir():
    return Path(
        os.environ.get("AETHEL_NLTK_DATA", Path(config.base_dir()) / "nltk_data")
    )


def lock():
    return json.loads((DATA / "resources.json").read_text(encoding="utf-8"))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(root):
    """Verify every runtime model byte against the shipped artifact lock."""
    fingerprints = {}
    for name, resource in lock()["resources"].items():
        for relative, expected in resource["files"].items():
            path = root / relative
            if (
                not path.is_file()
                or path.is_symlink()
                or digest(path.read_bytes()) != expected
            ):
                raise LanguageError(
                    f"Missing or mismatched NLTK resource: {path}. "
                    "Provision with python -m aethel_pkg.language_resources --download"
                )
        fingerprints[name] = resource["sha256"]
    return fingerprints


def provision(root, archives=None):
    """Install verified archives atomically; an offline archive directory is valid."""
    root = Path(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    if root.exists():
        raise LanguageError(
            f"Resource directory already exists: {root}; select a new directory"
        )
    with tempfile.TemporaryDirectory(prefix=".aethel-nltk-", dir=root.parent) as tmp:
        stage = Path(tmp) / "data"
        (stage / "archives").mkdir(parents=True)
        for name, resource in lock()["resources"].items():
            archive = stage / "archives" / (name + ".zip")
            if archives is None:
                with urllib.request.urlopen(resource["url"], timeout=60) as response:
                    archive.write_bytes(response.read())
            else:
                shutil.copyfile(Path(archives) / archive.name, archive)
            if digest(archive.read_bytes()) != resource["sha256"]:
                raise LanguageError(f"Archive checksum mismatch: {name}")
            with zipfile.ZipFile(archive) as source:
                for relative in resource["files"]:
                    member = relative.removeprefix(resource["subdir"] + "/")
                    target = stage / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(source.read(member))
        shutil.copytree(DATA / "licenses", stage / "licenses")
        verify(stage)
        stage.rename(root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--download", action="store_true", help="download pinned official archives"
    )
    source.add_argument(
        "--from-dir", type=Path, help="install from offline .zip archives"
    )
    parser.add_argument("--data-dir", type=Path, default=data_dir())
    args = parser.parse_args(argv)
    try:
        provision(args.data_dir, args.from_dir)
    except (LanguageError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"English NLTK resources provisioned in {args.data_dir}")


if __name__ == "__main__":
    main()
