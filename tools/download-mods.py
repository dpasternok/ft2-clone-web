#!/usr/bin/env python3

import html.parser
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from module_extensions import is_supported_module

SOURCE_URL = "https://mod.crh.ovh/mods/"
MAX_DIRECTORY_LISTING_SIZE = 4 * 1024 * 1024
MAX_DIRECTORY_COUNT = 10000
MAX_DIRECTORY_DEPTH = 32


class DirectoryIndex(html.parser.HTMLParser):
	def __init__(self):
		super().__init__()
		self.links = []
		self.title = ""
		self.in_title = False

	def handle_starttag(self, tag, attrs):
		if tag == "title":
			self.in_title = True
		elif tag == "a":
			self.links.extend(value for name, value in attrs if name == "href" and value)

	def handle_endtag(self, tag):
		if tag == "title":
			self.in_title = False

	def handle_data(self, data):
		if self.in_title:
			self.title += data


class NoRedirect(urllib.request.HTTPRedirectHandler):
	def redirect_request(self, req, fp, code, msg, headers, newurl):
		return None


def decode_child_name(raw_name):
	name = urllib.parse.unquote(raw_name)
	if not name or name in (".", "..") or any(char in name for char in ("/", "\\", "\x00")):
		return None
	if any(ord(char) < 32 for char in name):
		return None
	return name


def directory_contents(opener, directory_url):
	with opener.open(directory_url, timeout=30) as response:
		content = response.read(MAX_DIRECTORY_LISTING_SIZE + 1)
		if len(content) > MAX_DIRECTORY_LISTING_SIZE:
			raise ValueError(f"Module directory listing is too large: {directory_url}")

	index = DirectoryIndex()
	index.feed(content.decode("utf-8"))
	if not index.title.strip().startswith("Index of "):
		raise ValueError(f"Module directory did not return an Apache directory listing: {directory_url}")
	return index.links


def module_paths(source_url, opener):
	root = urllib.parse.urlsplit(source_url)
	root_path = root.path.rstrip("/") + "/"
	root_url = urllib.parse.urlunsplit((root.scheme, root.netloc, root_path, "", ""))
	modules = set()
	visited = set()
	pending = [()]

	while pending:
		directory = pending.pop()
		if directory in visited:
			continue
		visited.add(directory)
		if len(visited) > MAX_DIRECTORY_COUNT:
			raise ValueError("Module source contains too many directories")

		relative_directory = "/".join(urllib.parse.quote(part, safe="") for part in directory)
		directory_url = urllib.parse.urljoin(root_url, relative_directory + ("/" if directory else ""))
		url_parts = urllib.parse.urlsplit(directory_url)
		if (url_parts.scheme, url_parts.netloc) != (root.scheme, root.netloc) or not url_parts.path.startswith(root_path):
			raise ValueError("Module directory URL escaped its source root")

		for href in directory_contents(opener, directory_url):
			link = urllib.parse.urlsplit(href)
			if link.scheme or link.netloc or link.query or link.fragment or link.path.startswith("/"):
				continue

			is_directory = link.path.endswith("/")
			raw_name = link.path[:-1] if is_directory else link.path
			if not raw_name or "/" in raw_name:
				continue
			name = decode_child_name(raw_name)
			if name is None:
				continue

			relative_path = directory + (name,)
			if is_directory:
				if len(relative_path) > MAX_DIRECTORY_DEPTH:
					raise ValueError(f"Module source directory nesting exceeds {MAX_DIRECTORY_DEPTH} levels")
				pending.append(relative_path)
			elif is_supported_module(Path(name)):
				modules.add(relative_path)

	return sorted(modules, key=lambda parts: "/".join(parts).casefold())


def sync_library(source_url, output_dir):
	opener = urllib.request.build_opener(NoRedirect)
	paths = module_paths(source_url, opener)
	output_dir.parent.mkdir(parents=True, exist_ok=True)
	with tempfile.TemporaryDirectory(prefix=".mods-download-", dir=output_dir.parent) as temp:
		temp_dir = Path(temp)
		staging = temp_dir / "mods"
		staging.mkdir()
		for parts in paths:
			name = "/".join(parts)
			encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in parts)
			url = urllib.parse.urljoin(source_url.rstrip("/") + "/", encoded_path)
			with opener.open(url, timeout=30) as response:
				if response.headers.get_content_type() == "text/html":
					raise ValueError(f"Module request returned HTML: {name}")
				target = staging.joinpath(*parts)
				target.parent.mkdir(parents=True, exist_ok=True)
				with target.open("wb") as file:
					shutil.copyfileobj(response, file)
				length = response.headers.get("Content-Length")
				if length is not None and target.stat().st_size != int(length):
					raise ValueError(f"Incomplete module download: {name}")
			print(f"Downloaded {name}", flush=True)

		subprocess.run(
			[sys.executable, str(Path(__file__).with_name("generate-mods-index.py")), str(staging), str(staging / "index.json")],
			check=True,
		)

		previous = temp_dir / "previous"
		if output_dir.exists():
			output_dir.rename(previous)
		try:
			staging.rename(output_dir)
		except OSError:
			if previous.exists():
				previous.rename(output_dir)
			raise

	print(f"Downloaded {len(paths)} modules to {output_dir}")


def main():
	if len(sys.argv) != 2:
		raise SystemExit("Usage: download-mods.py <output-directory>")
	try:
		sync_library(SOURCE_URL, Path(sys.argv[1]))
	except (OSError, ValueError, UnicodeError, subprocess.CalledProcessError) as error:
		raise SystemExit(f"Could not download module library: {error}") from error


if __name__ == "__main__":
	main()
