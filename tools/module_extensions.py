import re
from pathlib import Path


def _read_extensions():
	path = Path(__file__).resolve().parent.parent / "src" / "ft2_module_extensions.inc"
	extensions = []
	for line in path.read_text(encoding="utf-8").splitlines():
		match = re.fullmatch(r'"([a-z0-9]+)",', line.strip())
		if match is None:
			raise ValueError(f"Invalid module extension definition in {path}: {line!r}")
		extensions.append("." + match.group(1))
	if not extensions or len(set(extensions)) != len(extensions):
		raise ValueError(f"Empty or duplicate module extension definitions in {path}")
	return frozenset(extensions)


SUPPORTED_EXTENSIONS = _read_extensions()


def is_supported_module(path: Path) -> bool:
	suffix = path.suffix
	return suffix.isascii() and suffix.lower() in SUPPORTED_EXTENSIONS
