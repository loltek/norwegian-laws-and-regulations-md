#!/usr/bin/env python3
"""Convert the Lovdata HTML/XML dumps in ./src to readable Markdown in ./forskrifter.

Filenames are built from the document's Lovdata date code plus a slug of its
short title, e.g. for-2004-12-01-1558-bokforingsforskriften.md.

The converter is deliberately strict: unknown tags, classes, list types or
table constructs abort the run so they can be inspected instead of being
silently mangled.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag
from markdownify import MarkdownConverter, re_line_with_content

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
DST = ROOT / "forskrifter"
INDEX_PATH = DST / "index.json"
DATASET_PATH = DST / "dataset.json"
OTHER_INDEX = ROOT / "lover" / "index.json"
SOURCE_URL = (
    "https://api.lovdata.no/v1/publicData/get/"
    "gjeldende-sentrale-forskrifter.tar.bz2"
)

LABELS = [
    ("titleShort", "Korttittel"),
    ("legacyID", "Datokode"),
    ("dokid", "DokumentID"),
    ("ministry", "Departement"),
    ("subunit", "Etat"),
    ("basedOn", "Hjemmel"),
    ("publishedIn", "Publisert i"),
    ("dateOfPublication", "Kunngjort"),
    ("dateInForce", "I kraft fra"),
    ("lastChangeInForce", "Siste endring i kraft"),
    ("lastChangedBy", "Sist endret ved"),
    ("legalArea", "Rettsområde"),
    ("eeaReferences", "EU/EØS-henvisning"),
    ("changesToDocuments", "Endrer"),
    ("appliesTo", "Gjelder for"),
    ("lastupdated", "Siste rettelse"),
    ("miscInformation", "Merknad"),
]

METADATA_CLASSES = {
    "legacyID", "dokid", "ministry", "dateInForce", "lastChangeInForce",
    "lastChangedBy", "legalArea", "lastupdated", "titleShort", "title",
    "miscInformation", "refid", "eli", "table-of-contents",
    "dateOfPublication", "changesToDocuments", "eeaReferences", "appliesTo",
    "basedOn", "subunit", "publishedIn", "a11yStatus", "note",
}

HEADER_CLASS_TAGS = {
    "documentHeader": {"header"},
    "data-document-key-info": {"dl"},
    "tocTopUl": {"ul"},
    "tocSubUl": {"ul"},
}
for _name in METADATA_CLASSES:
    HEADER_CLASS_TAGS[_name] = {"dt", "dd"}

HEADER_TAGS = {
    "header", "dl", "dt", "dd", "ul", "li", "a", "br", "i", "strong", "sub",
    "span",
}

BODY_CLASS_TAGS = {
    "documentBody": {"main"},
    "section": {"section"},
    "legalArticle": {"article"},
    "legalP": {"article"},
    "listArticle": {"article"},
    "defaultP": {"article"},
    "numberedLegalP": {"article"},
    "changesToParent": {"article"},
    "futureLegalArticle": {"article"},
    "footnoteLegalP": {"article"},
    "marginIdArticle": {"article"},
    "centeredP": {"article"},
    "leddfortsettelse": {"p"},
    "change": {"article"},
    "document-change": {"article"},
    "indent": {"div"},
    "legalArticleHeader": {"h2", "h3", "h4", "h5", "h6", "div"},
    "legalArticleValue": {"span"},
    "legalArticleTitle": {"span"},
    "futureLegalArticleHeader": {"span"},
    "futuretitle": {"span"},
    "miscHeadline": {"span"},
    "data-marginOriginalId": {"span"},
    "defaultList": {"ol", "ul"},
    "footnotereference": {"sup"},
    "startGroup": {"tr"},
    "latexBlock": {"div"},
    "latexInline": {"span"},
    "data-pronounced-line": {"span"},
    "underline": {"span"},
    "letterspacing": {"span"},
    "box": {"div"},
    "consolidationElement": {"li"},
    "footnoteDefaultP": {"article"},
}

FOOTER_CLASS_TAGS = {
    "footnotes": {"footer"},
    "footnote": {"article"},
    "footnoteLabel": {"span"},
    "footnoteLegalP": {"article"},
    "footnoteDefaultP": {"article"},
    "legalP": {"article"},
    "listArticle": {"article"},
    "defaultList": {"ul", "ol"},
    "startGroup": {"tr"},
    "underline": {"span"},
    "footnotereference": {"sup"},
    "leddfortsettelse": {"p"},
}

BODY_TAGS = {
    "main", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article",
    "div", "p", "span", "ol", "ul", "li", "a", "sup", "sub", "br", "i",
    "strong", "table", "thead", "tbody", "tr", "th", "td", "caption", "img",
    "small", "blockquote", "figure", "figcaption", "s",
}

FOOTER_TAGS = {
    "footer", "article", "span", "a", "br", "i", "ul", "li", "ol",
    "table", "thead", "tbody", "tr", "th", "td", "caption", "p", "strong",
    "sup", "sub",
}

ORDERED_LIST_TYPES = {"1", "a", "A", "i", "I"}

# Nynorsk and Sami language variants are out of scope.
EXCLUDED_LANGUAGES = {"nn", "se", "sme", "sma", "smj", "smn", "sms"}


class ConversionError(Exception):
    pass


def fail(path: Path, message: str, element: Tag | None = None) -> None:
    if element is not None:
        snippet = " ".join(str(element).split())
        message = f"{message}: {snippet[:200]}"
    raise ConversionError(f"{path.name}: {message}")


def validate_classes(path: Path, element: Tag, allowed: dict[str, set[str]]) -> None:
    for name in element.get("class", []):
        tags = allowed.get(name)
        if tags is None:
            fail(path, f"unknown class {name!r}", element)
        if element.name not in tags:
            fail(path, f"class {name!r} on unexpected <{element.name}>", element)


def excluded_language(soup: BeautifulSoup) -> bool:
    html_tag = soup.find("html")
    lang = (html_tag.get("lang") if html_tag else "") or ""
    base = re.split(r"[-_]", lang.lower(), maxsplit=1)[0]
    return base in EXCLUDED_LANGUAGES


def footnote_number_map(main: Tag) -> dict[str, str]:
    """Map visible footnote labels to unique counters where unambiguous."""
    counters: dict[str, set[str]] = {}
    for note in main.select("footer.footnotes article.footnote"):
        name = note.get("data-name")
        counter = note.get("data-unique-footnote-counter")
        if name and counter:
            counters.setdefault(name, set()).add(counter)
    return {
        name: next(iter(values))
        for name, values in counters.items()
        if len(values) == 1
    }


def validate_document(path: Path, soup: BeautifulSoup) -> None:
    headers = soup.find_all("header")
    if len(headers) != 1:
        fail(path, f"expected exactly one <header>, found {len(headers)}")
    header = headers[0]
    if header.get("class") != ["documentHeader"]:
        fail(path, f"unexpected header class {header.get('class')!r}", header)

    mains = soup.find_all("main")
    if len(mains) != 1:
        fail(path, f"expected exactly one <main>, found {len(mains)}")
    main = mains[0]
    if main.get("class") != ["documentBody"]:
        fail(path, f"unexpected main class {main.get('class')!r}", main)

    # --- metadata header -------------------------------------------------
    for child in header.find_all(True):
        if child.name not in HEADER_TAGS:
            fail(path, f"unknown header tag <{child.name}>", child)
        validate_classes(path, child, HEADER_CLASS_TAGS)

    dl = header.find("dl", recursive=False)
    if dl is None or len(header.find_all("dl", recursive=False)) != 1:
        fail(path, "expected exactly one metadata <dl> directly under <header>")
    if dl.get("class") != ["data-document-key-info"]:
        fail(path, f"unexpected metadata <dl> class {dl.get('class')!r}", dl)

    children = [child for child in dl.children if isinstance(child, Tag)]
    if len(children) % 2:
        fail(path, "metadata <dl> has an odd number of dt/dd children")
    for index in range(0, len(children), 2):
        dt, dd = children[index], children[index + 1]
        if dt.name != "dt" or dd.name != "dd":
            fail(path, "metadata <dl> does not alternate dt/dd", dt)
        if dt.get("class") != dd.get("class"):
            fail(path, "metadata dt/dd classes do not match", dt)

    for name in ("title", "dokid", "legacyID"):
        if len(dl.select(f"dd.{name}")) != 1:
            fail(path, f"expected exactly one dd.{name}")

    # --- document body ---------------------------------------------------
    h1s = main.find_all("h1")
    if len(h1s) != 1 or h1s[0].parent is not main:
        fail(path, "expected exactly one <h1> directly under <main>")

    for element in main.find_all(True):
        in_footer = element.name == "footer" or element.find_parent("footer") is not None
        if in_footer:
            if element.name not in FOOTER_TAGS:
                fail(path, f"unknown footnote tag <{element.name}>", element)
            validate_classes(path, element, FOOTER_CLASS_TAGS)
        else:
            if element.name not in BODY_TAGS:
                fail(path, f"unknown body tag <{element.name}>", element)
            validate_classes(path, element, BODY_CLASS_TAGS)
        if element.name == "footer" and element.find_parent("footer") is not None:
            fail(path, "nested <footer>", element)
        if element.name in {"td", "th"}:
            for attribute in ("rowspan", "colspan"):
                if element.get(attribute) is None:
                    continue
                try:
                    span = int(element[attribute])
                except (TypeError, ValueError):
                    fail(
                        path,
                        f"invalid {attribute} {element[attribute]!r}",
                        element,
                    )
                if span < 1:
                    fail(path, f"invalid {attribute} {span}", element)

    for ol in main.find_all("ol"):
        if ol.get("type") not in ORDERED_LIST_TYPES:
            fail(path, f"unknown ordered-list type {ol.get('type')!r}", ol)

    for img in main.find_all("img"):
        if not img.get("src"):
            fail(path, "<img> without src", img)

    # --- footnotes -------------------------------------------------------
    refs = main.select("sup.footnotereference")
    notes = main.select("footer.footnotes article.footnote")
    number_map = footnote_number_map(main)
    ref_numbers = []
    for ref in refs:
        number = ref.get("data-unique-footnote-counter")
        if not number:
            value = ref.get("data-footnotereferencevalue")
            number = number_map.get(value) if value else None
            if not number and value and not value.isdigit():
                # Symbolic markers such as * or *** sometimes have no note.
                continue
        if not number:
            fail(path, "footnote reference without resolvable number", ref)
        ref_numbers.append(number)
    note_numbers = []
    for note in notes:
        number = note.get("data-unique-footnote-counter")
        if not number:
            fail(path, "footnote without unique counter", note)
        note_numbers.append(number)
        if note.find("span", class_="footnoteLabel") is None:
            fail(path, "footnote without label", note)
    if len(note_numbers) != len(set(note_numbers)):
        fail(path, "duplicate footnote unique counters")
    missing = set(ref_numbers) - set(note_numbers)
    if missing:
        fail(path, f"footnote references without notes: {sorted(missing)}")


def text_of(node: Tag | None) -> str:
    """Plain text of a metadata <dd>, keeping list items separated."""
    if node is None:
        return ""
    items = [
        li for li in node.find_all("li")
        if li.find_parent("li") is None
    ]
    if items:
        value = "; ".join(li.get_text(" ", strip=True) for li in items)
    else:
        value = node.get_text(" ", strip=True)
    return tidy(value)


def date_of(value: str) -> str | None:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", value.strip())
    return match.group(1) if match else None


def tidy(value: str) -> str:
    """Collapse whitespace and remove the gaps left by stripped inline tags."""
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s+([,.;:])", r"\1", value)
    value = re.sub(r"\(\s+", "(", value)
    value = re.sub(r"\s+\)", ")", value)
    return value


def pretty_refs(value: str) -> str:
    """Turn Lovdata IDs like lov/2026-06-19-45 into readable references."""
    pattern = re.compile(r"\b(lov|forskrift)/(\d{4})-(\d{2})-(\d{2})-(\d+)")

    def replace(match: re.Match) -> str:
        kind, year, month, day, number = match.groups()
        return f"{kind} {day}.{month}.{year} nr. {number}"

    return pattern.sub(replace, value)


def doc_key(value: str) -> str | None:
    """Return a Lovdata document key such as forskrift/2004-12-01-1558."""
    match = re.match(r"^(?:https://lovdata\.no/)?(lov|forskrift)/([^/]+)", value)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}"


def load_targets(paths: list[Path], own_dir: str) -> dict[str, str]:
    targets = {}
    for path in paths:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in data.get("documents", []):
            key = doc_key(item.get("source_url", ""))
            if not key:
                continue
            targets[key] = os.path.relpath(item["path"], own_dir)
    return targets


def slugify(value: str) -> str:
    value = value.replace("–", "-").replace("—", "-")
    value = value.replace("æ", "ae").replace("Æ", "Ae")
    value = value.replace("ø", "o").replace("Ø", "O")
    value = value.replace("å", "aa").replace("Å", "Aa")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).lower()
    return re.sub(r"-+", "-", value).strip("-")


TRAILING_STOPWORDS = {
    "for", "og", "i", "av", "til", "paa", "med", "som", "den", "det",
    "en", "et", "om", "ved", "fra", "mot", "uten", "etter", "over",
    "under", "mellom", "samt",
}


def shorten(value: str, limit: int = 100) -> str:
    if len(value) <= limit:
        return value
    value = value[:limit]
    while "-" in value:
        head, tail = value.rsplit("-", 1)
        previous = head.rsplit("-", 1)[-1] if "-" in head else ""
        if len(tail) == 1 or tail in TRAILING_STOPWORDS:
            value = head
        elif len(tail) <= 2 and previous in TRAILING_STOPWORDS:
            value = head
        else:
            break
    return value.strip("-")


def output_name(soup: BeautifulSoup, source: Path) -> str:
    legacy = text_of(soup.select_one("dd.legacyID")) or source.stem
    short = text_of(soup.select_one("dd.titleShort"))
    title = text_of(soup.select_one("dd.title"))

    # Drop a trailing abbreviation such as "Domstolloven – dl".
    short = re.sub(r"\s+[–-]\s+\S{1,12}$", "", short).strip()

    name = shorten(slugify(short or title)) or "forskrift"
    return f"{slugify(legacy)}-{name}.md"


def roman(number: int) -> str:
    values = [
        (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
        (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
        (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
    ]
    out = []
    for value, numeral in values:
        while number >= value:
            out.append(numeral)
            number -= value
    return "".join(out)


class LawConverter(MarkdownConverter):
    def __init__(
        self,
        *args,
        base_url: str = "",
        local_targets: dict[str, str] | None = None,
        cross_targets: dict[str, str] | None = None,
        **kwargs,
    ):
        self.base_url = base_url.rstrip("/")
        self.local_targets = local_targets or {}
        self.cross_targets = cross_targets or {}
        super().__init__(*args, **kwargs)

    def convert_a(self, el, text, parent_tags):
        text = text or ""
        if not text.strip():
            return text

        href = (el.get("href") or "").strip()
        if not href:
            return text

        key = doc_key(href)
        if href.startswith("#"):
            if not self.base_url:
                return text
            url = self.base_url + href
        elif href.startswith(("http://", "https://", "mailto:")):
            url = href
        elif key in self.local_targets:
            url = self.local_targets[key]
        elif key in self.cross_targets:
            url = self.cross_targets[key]
        else:
            url = "https://lovdata.no/" + href.lstrip("/")

        escaped = text.replace("[", r"\[").replace("]", r"\]")
        return f"[{escaped}]({url})"

    def convert_img(self, el, text, parent_tags):
        src = el.get("src", "")
        if src.startswith(("http://", "https://", "/")):
            url = src
        else:
            url = "https://lovdata.no/" + src.lstrip("./")
        alt = el.get("alt", "")
        return f"![{alt}]({url})"

    def convert_li(self, el, text, parent_tags):
        text = (text or "").strip()
        if not text:
            return "\n"

        parent = el.parent
        if parent is not None and parent.name == "ol":
            start = parent.get("start")
            start = int(start) if start and str(start).isnumeric() else 1
            number = start + len(el.find_previous_siblings("li"))

            kind = parent.get("type", "1")
            if kind == "a":
                marker = chr(ord("a") + number - 1)
            elif kind == "A":
                marker = chr(ord("A") + number - 1)
            elif kind == "i":
                marker = roman(number)
            elif kind == "I":
                marker = roman(number).upper()
            else:
                marker = str(number)
            bullet = marker + ". "
        else:
            depth = -1
            node = el
            while node:
                if node.name == "ul":
                    depth += 1
                node = node.parent
            bullets = self.options["bullets"]
            bullet = bullets[depth % len(bullets)] + " "

        width = len(bullet)
        indent = " " * width
        text = re_line_with_content.sub(
            lambda m: indent + m.group(1) if m.group(1) else "", text
        )
        text = bullet + text[width:]
        return "%s\n" % text


def escape_literal_tags(text: str) -> str:
    """Escape tag-like text such as <Opphevet> so Markdown shows it."""
    return re.sub(
        r"<(/?[A-Za-z][^>]*)>",
        lambda match: "\\<" + match.group(1) + "\\>",
        text,
    )


def bold_paragraph(soup: BeautifulSoup, element: Tag) -> None:
    paragraph = soup.new_tag("p")
    strong = soup.new_tag("strong")
    for child in list(element.contents):
        strong.append(child.extract())
    paragraph.append(strong)
    element.replace_with(paragraph)


def render_footnotes(main: Tag, converter: LawConverter) -> list[str]:
    notes = []
    for footer in main.find_all("footer", class_="footnotes"):
        for note in footer.find_all("article", class_="footnote"):
            label = note.find("span", class_="footnoteLabel")
            number = note.get("data-unique-footnote-counter")
            if label is not None:
                label.decompose()
            for wrapper in note.find_all("article", class_="listArticle"):
                wrapper.unwrap()
            for paragraph in note.find_all(
                "article",
                class_=["footnoteLegalP", "legalP", "footnoteDefaultP"],
            ):
                paragraph.name = "p"
            body = converter.convert_soup(note).strip()
            body = re.sub(r"\n{3,}", "\n\n", body)
            body = escape_literal_tags(body)
            notes.append(f"**{number}.** {body}")
        footer.decompose()
    return notes


def normalize_tables(main: Tag, soup: BeautifulSoup) -> None:
    """Expand rowspan/colspan into a rectangular Markdown-friendly grid."""
    for table in main.find_all("table"):
        rows = [
            row for row in table.find_all("tr")
            if row.find_parent("table") is table
        ]
        if not rows:
            continue

        grid: dict[tuple[int, int], tuple[Tag, bool]] = {}
        occupied: set[tuple[int, int]] = set()
        max_columns = 0

        for row_index, row in enumerate(rows):
            column = 0
            for cell in row.find_all(["td", "th"], recursive=False):
                while (row_index, column) in occupied:
                    column += 1
                rowspan = int(cell.get("rowspan", 1) or 1)
                colspan = int(cell.get("colspan", 1) or 1)
                for r in range(row_index, row_index + rowspan):
                    for c in range(column, column + colspan):
                        occupied.add((r, c))
                        grid[(r, c)] = (cell, (r, c) == (row_index, column))
                column += colspan
                max_columns = max(max_columns, column)

        for row_index, row in enumerate(rows):
            for child in list(row.contents):
                child.extract()
            for column in range(max_columns):
                entry = grid.get((row_index, column))
                if entry is None:
                    row.append(soup.new_tag("td"))
                    continue
                cell, origin = entry
                new_cell = soup.new_tag(cell.name)
                for name, value in cell.attrs.items():
                    if name not in {"rowspan", "colspan"}:
                        new_cell[name] = value
                if origin:
                    for child in list(cell.contents):
                        new_cell.append(child.extract())
                row.append(new_cell)


def prepare_body(main: Tag, soup: BeautifulSoup, converter: LawConverter) -> list[str]:
    # Footnote references -> [n], using the document-wide counter.
    number_map = footnote_number_map(main)
    for sup in main.select("sup.footnotereference"):
        number = sup.get("data-unique-footnote-counter")
        if not number:
            value = sup.get("data-footnotereferencevalue")
            number = number_map.get(value) if value else None
            if not number:
                number = value
        if not number:
            raise ConversionError("footnote reference without resolvable number")
        sup.replace_with(NavigableString(f"[{number}]"))

    notes = render_footnotes(main, converter)

    # The title is rendered from metadata, so avoid printing it twice.
    for h1 in main.find_all("h1"):
        h1.decompose()

    # Rename semantic containers to tags markdownify treats as blocks.
    for article in main.find_all("article"):
        article.name = "div"
    for section in main.find_all("section"):
        section.name = "div"
    for figure in main.find_all("figure"):
        figure.name = "div"
    for caption in main.find_all("figcaption"):
        caption.name = "p"
    for small in main.find_all("small"):
        small.name = "span"

    normalize_tables(main, soup)

    # Headings that are represented as spans/divs rather than h2-h6.
    for element in list(main.select(
        "span.futureLegalArticleHeader, span.futuretitle, "
        "span.miscHeadline, div.legalArticleHeader"
    )):
        bold_paragraph(soup, element)

    for div in main.find_all("div"):
        if div is None or div.parent is None:
            continue
        classes = set(div.get("class", []))

        if "listArticle" in classes:
            div.unwrap()
            continue

        if "changesToParent" in classes:
            div.name = "p"
            em = soup.new_tag("em")
            for child in list(div.contents):
                em.append(child.extract())
            div.append(em)
            continue

        if "indent" in classes or "box" in classes:
            div.name = "blockquote"
            continue

        if "centeredP" in classes or "footnoteLegalP" in classes:
            div.name = "p"
            continue

        if "marginIdArticle" in classes:
            marker = div.find("span", class_="data-marginOriginalId")
            if marker is not None:
                strong = soup.new_tag("strong")
                strong.string = marker.get_text(" ", strip=True)
                marker.replace_with(strong)

    return notes


def convert_file(
    path: Path,
    local_targets: dict[str, str] | None = None,
    cross_targets: dict[str, str] | None = None,
) -> tuple[str, str, dict] | None:
    raw = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(raw, "lxml")
    if excluded_language(soup):
        return None
    validate_document(path, soup)

    title = text_of(soup.select_one("dd.title"))
    name = output_name(soup, path)
    meta = []
    seen = set()
    for key, label in LABELS:
        node = soup.select_one(f"dd.{key}")
        if key == "basedOn" and node is not None:
            value = "; ".join(
                link.get("href", "") for link in node.find_all("a")
            )
        else:
            value = text_of(node)
        if key != "dokid":
            value = pretty_refs(value)
        if key == "titleShort" and value == title:
            continue
        if value and (key, value) not in seen:
            meta.append(f"- **{label}:** {value}")
            seen.add((key, value))

    dokid = text_of(soup.select_one("dd.dokid"))
    source_url = None
    if dokid:
        source_url = "https://lovdata.no/" + re.sub(
            r"^(?:NL|SF)/", "", dokid
        )
        meta.append(f"- **Kilde:** <{source_url}>")

    based_on_node = soup.select_one("dd.basedOn")
    based_on = [
        link.get("href", "")
        for link in (based_on_node.find_all("a") if based_on_node else [])
    ]
    record = {
        "type": "regulation",
        "title": title,
        "slug": Path(name).stem,
        "category": path.parent.name,
        "date_code": text_of(soup.select_one("dd.legacyID")),
        "ministry": text_of(soup.select_one("dd.ministry")),
        "legal_area": text_of(soup.select_one("dd.legalArea")),
        "based_on": based_on,
        "last_updated": (
            date_of(text_of(soup.select_one("dd.lastChangeInForce")))
            or date_of(text_of(soup.select_one("dd.lastupdated")))
        ),
        "source_url": source_url,
    }

    main = soup.find("main")
    if main is None:  # guarded by validate_document, kept for type checkers
        raise ConversionError(f"{path.name}: no <main> element")

    converter = LawConverter(
        heading_style="ATX",
        bullets="-",
        escape_underscores=False,
        escape_asterisks=False,
        base_url=source_url or "",
        local_targets=local_targets,
        cross_targets=cross_targets,
    )
    notes = prepare_body(main, soup, converter)

    body = converter.convert_soup(main)
    body = html.unescape(body)
    body = escape_literal_tags(body)
    body = body.replace("\u00a0", " ")
    lines = []
    for line in body.splitlines():
        hard_break = line.endswith("  ")
        lines.append(line.rstrip() + ("  " if hard_break else ""))
    body = "\n".join(lines)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    parts = [f"# {title}", "", *meta, "", body]
    if notes:
        parts += ["", "## Fotnoter", "", "\n\n".join(notes)]
    markdown = "\n".join(parts).rstrip() + "\n"

    return name, markdown, record


def write_json(path: Path, data: dict) -> bool:
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return True


def build_dataset(
    document_count: int, files: list[Path], content_changed: bool
) -> dict:
    path = DATASET_PATH
    old = {}
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))

    source_b3sum = (
        os.environ.get("SOURCE_B3SUM") or old.get("source_b3sum", "")
    )
    converter_b3sum = (
        os.environ.get("CONVERTER_B3SUM") or old.get("converter_b3sum", "")
    )
    source_changed = bool(
        source_b3sum and source_b3sum != old.get("source_b3sum")
    )

    generated_at = old.get("generated_at")
    if content_changed or source_changed or not generated_at:
        generated_at = datetime.now(timezone.utc).replace(
            microsecond=0
        ).isoformat().replace("+00:00", "Z")

    return {
        "source_url": os.environ.get("SOURCE_URL", SOURCE_URL),
        "source_b3sum": source_b3sum,
        "converter_b3sum": converter_b3sum,
        "generated_at": generated_at,
        "document_count": document_count,
        "source_file_count": len(files),
        "excluded_languages": sorted(EXCLUDED_LANGUAGES),
        "format_version": 1,
    }


STATE_PATH = ROOT / ".convert-state.json"
RECORDS_PATH = ROOT / ".convert-records.jsonl"


def source_key(path: Path) -> str:
    return path.relative_to(SRC).as_posix()


def resolve_source(files: list[Path], value: str) -> Path:
    target = Path(value)
    for path in files:
        if path == target or path.name == value or source_key(path) == value:
            return path
    raise ConversionError(f"{value}: source file not found")


def load_records() -> dict[str, dict]:
    records = {}
    if not RECORDS_PATH.exists():
        return records
    for line in RECORDS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records[record["path"]] = record
    return records


def append_record(record: dict) -> None:
    with RECORDS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        )


def write_output(name: str, markdown: str) -> bool:
    destination = DST / name
    changed = (
        not destination.exists()
        or destination.read_text(encoding="utf-8") != markdown
    )
    destination.write_text(markdown, encoding="utf-8")
    return changed


def write_index_and_dataset(
    records: dict[str, dict], files: list[Path], content_changed: bool
) -> None:
    index = {
        "count": len(records),
        "documents": sorted(records.values(), key=lambda item: item["path"]),
    }
    if write_json(INDEX_PATH, index):
        content_changed = True
    write_json(
        DATASET_PATH,
        build_dataset(len(records), files, content_changed),
    )


def remove_stale(outputs: set[str]) -> bool:
    stale = [path for path in DST.glob("*.md") if path.name not in outputs]
    for path in stale:
        path.unlink()
    if stale:
        print(f"Removed {len(stale)} stale output file(s)")
    return bool(stale)


def run_full(
    files: list[Path],
    local_targets: dict[str, str],
    cross_targets: dict[str, str],
) -> None:
    outputs: dict[str, str] = {}
    sources: dict[str, Path] = {}
    records: dict[str, dict] = {}
    skipped: list[Path] = []

    # Convert everything first so a validation error leaves the previous
    # output directory untouched.
    for path in files:
        result = convert_file(path, local_targets, cross_targets)
        if result is None:
            skipped.append(path)
            continue
        name, markdown, record = result
        if name in outputs:
            raise ConversionError(
                f"filename collision: {name} ({sources[name]} and {path})"
            )
        outputs[name] = markdown
        sources[name] = path
        record["path"] = f"forskrifter/{name}"
        records[record["path"]] = record

    DST.mkdir(exist_ok=True)
    content_changed = False
    for name, markdown in outputs.items():
        if write_output(name, markdown):
            content_changed = True

    if remove_stale(set(outputs)):
        content_changed = True

    write_index_and_dataset(records, files, content_changed)
    STATE_PATH.unlink(missing_ok=True)
    RECORDS_PATH.unlink(missing_ok=True)

    print(f"Converted {len(outputs)} of {len(files)} files into {DST}")
    if skipped:
        print(f"Skipped {len(skipped)} nynorsk/Sami file(s)")


def run_incremental(
    files: list[Path],
    start: int,
    resume: bool,
    local_targets: dict[str, str],
    cross_targets: dict[str, str],
) -> None:
    DST.mkdir(exist_ok=True)
    if resume:
        records = load_records()
        state = {}
        if STATE_PATH.exists():
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    else:
        records = {}
        state = {}
        RECORDS_PATH.unlink(missing_ok=True)
        STATE_PATH.unlink(missing_ok=True)

    skipped = set(state.get("skipped", []))
    content_changed = False

    for path in files[start:]:
        key = source_key(path)
        write_json(STATE_PATH, {
            "next": key,
            "total": len(files),
            "skipped": sorted(skipped),
        })

        result = convert_file(path, local_targets, cross_targets)
        if result is None:
            skipped.add(key)
            continue

        name, markdown, record = result
        record["path"] = f"forskrifter/{name}"
        if write_output(name, markdown):
            content_changed = True
        append_record(record)
        records[record["path"]] = record

    completed = len(records) + len(skipped)
    if completed == len(files):
        outputs = {Path(item["path"]).name for item in records.values()}
        if remove_stale(outputs):
            content_changed = True
        write_index_and_dataset(records, files, content_changed)
        STATE_PATH.unlink(missing_ok=True)
        RECORDS_PATH.unlink(missing_ok=True)
        print(f"Converted {len(records)} of {len(files)} files into {DST}")
        if skipped:
            print(f"Skipped {len(skipped)} nynorsk/Sami file(s)")
    else:
        print(
            f"Incremental run stopped at {completed} of {len(files)} files; "
            "index.json and dataset.json were not updated."
        )
        print(f"Resume with: {Path(__file__).name} --resume")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--resume",
        action="store_true",
        help="continue from the last .convert-state.json checkpoint",
    )
    group.add_argument(
        "--start",
        metavar="FILE",
        help="start conversion at this source file",
    )
    group.add_argument(
        "--only",
        metavar="FILE",
        help="convert only this source file",
    )
    args = parser.parse_args()

    files = sorted(SRC.rglob("*.xml"))
    if not files:
        raise ConversionError(f"no XML files found under {SRC}")

    local_targets = load_targets([INDEX_PATH, OTHER_INDEX], DST.name)
    cross_targets: dict[str, str] = {}

    if args.only:
        path = resolve_source(files, args.only)
        result = convert_file(path, local_targets, cross_targets)
        if result is None:
            print(f"Skipped {source_key(path)}")
            return
        name, markdown, _ = result
        DST.mkdir(exist_ok=True)
        write_output(name, markdown)
        print(f"Converted {source_key(path)} -> {DST / name}")
        return

    if args.start:
        start = files.index(resolve_source(files, args.start))
        run_incremental(
            files, start, False, local_targets, cross_targets
        )
        return

    if args.resume:
        start = 0
        state = {}
        if STATE_PATH.exists():
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            next_key = state.get("next")
            if state.get("total") not in (None, len(files)):
                print("Source file list changed; ignoring checkpoint.")
                state = {}
                next_key = None
            if next_key:
                for index, path in enumerate(files):
                    if source_key(path) == next_key:
                        start = index
                        break
                else:
                    print("Checkpoint file no longer exists; starting over.")
                    state = {}
        run_incremental(
            files, start, bool(state or start), local_targets, cross_targets
        )
        return

    run_full(files, local_targets, cross_targets)


if __name__ == "__main__":
    main()
