import os
import re
import pytest

DOCS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
)

MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def _find_all_docs(docs_dir: str) -> list[str]:
    md_files: list[str] = []
    for root, _dirs, files in os.walk(docs_dir):
        for f in files:
            if f.endswith(".md"):
                md_files.append(os.path.join(root, f))
    return sorted(md_files)


def _extract_internal_links(content: str, file_path: str) -> list[tuple[str, str]]:
    # Strip fenced + inline code BEFORE extracting links: a markdown-link-shaped
    # token inside a CODE example (e.g. a JS `console.log(`[${t.title}](${t.url})`)`
    # snippet) is NOT a doc link — flagging it is a §11.4.1 FAIL-bluff, not a real
    # broken link. Real links live in prose, never inside code spans/fences.
    content = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
    content = re.sub(r"~~~.*?~~~", "", content, flags=re.DOTALL)
    content = re.sub(r"`[^`\n]*`", "", content)
    links = []
    for match in MD_LINK_RE.finditer(content):
        text, target = match.group(1), match.group(2)
        if target.startswith(("http://", "https://", "#", "mailto:", "ftp://")):
            continue
        links.append((text, target))
    return links


@pytest.mark.parametrize(
    "md_file",
    _find_all_docs(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "docs",
        )
    ),
    ids=lambda p: os.path.relpath(p, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
)
def test_internal_markdown_links_resolve(md_file):
    if not os.path.isdir(DOCS_DIR):
        pytest.skip("docs/ directory not found")  # SKIP-OK: #legacy-untriaged

    with open(md_file, encoding="utf-8") as fh:
        content = fh.read()

    links = _extract_internal_links(content, md_file)
    errors = []

    for text, target in links:
        anchor = ""
        link_target = target
        if "#" in target:
            link_target, anchor = target.split("#", 1)

        if not link_target:
            continue

        resolved = os.path.normpath(os.path.join(os.path.dirname(md_file), link_target))

        if not os.path.exists(resolved):
            errors.append(f"[{text}]({target}) → {resolved} does not exist")

    assert not errors, f"Broken links in {md_file}:\n" + "\n".join(errors)
