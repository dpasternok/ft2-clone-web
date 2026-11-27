#!/usr/bin/env python3

import json
import shutil
import sys
import tempfile
from pathlib import Path

from module_extensions import is_supported_module


def generate_index(mods_dir: Path, output_file: Path) -> None:
	mods_dir.mkdir(parents=True, exist_ok=True)
	output_file.parent.mkdir(parents=True, exist_ok=True)

	mods = [
		{"name": path.relative_to(mods_dir).as_posix(), "size": path.stat().st_size}
		for path in sorted(mods_dir.rglob("*"), key=lambda item: item.relative_to(mods_dir).as_posix().casefold())
		if path.is_file() and not path.is_symlink() and is_supported_module(path)
	]
	output_file.write_text(
		json.dumps({"files": mods}, ensure_ascii=False, indent=2) + "\n",
		encoding="utf-8",
	)


def copy_library(source: Path, destination: Path) -> None:
	source.mkdir(parents=True, exist_ok=True)
	destination.parent.mkdir(parents=True, exist_ok=True)
	with tempfile.TemporaryDirectory(prefix=".mods-copy-", dir=destination.parent) as temp:
		staging = Path(temp) / "mods"
		staging.mkdir()
		for path in source.rglob("*"):
			if path.is_file() and not path.is_symlink() and is_supported_module(path):
				target = staging / path.relative_to(source)
				target.parent.mkdir(parents=True, exist_ok=True)
				shutil.copy2(path, target)

		generate_index(staging, staging / "index.json")
		previous = Path(temp) / "previous"
		if destination.exists():
			destination.rename(previous)
		try:
			staging.rename(destination)
		except OSError:
			if previous.exists():
				previous.rename(destination)
			raise


def main() -> None:
	if len(sys.argv) == 4 and sys.argv[1] == "--copy":
		copy_library(Path(sys.argv[2]), Path(sys.argv[3]))
	elif len(sys.argv) == 3:
		generate_index(Path(sys.argv[1]), Path(sys.argv[2]))
	else:
		raise SystemExit("Usage: generate-mods-index.py <mods-directory> <output-file> | --copy <mods-directory> <output-directory>")


if __name__ == "__main__":
	main()
