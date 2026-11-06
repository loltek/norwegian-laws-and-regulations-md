# norwegian-laws-and-regulations-md

[![Update laws](https://github.com/loltek/norwegian-laws-and-regulations-md/actions/workflows/update-laws.yml/badge.svg?branch=main)](https://github.com/loltek/norwegian-laws-and-regulations-md/actions/workflows/update-laws.yml)
[![Update regulations](https://github.com/loltek/norwegian-laws-and-regulations-md/actions/workflows/update-regulations.yml/badge.svg?branch=main)](https://github.com/loltek/norwegian-laws-and-regulations-md/actions/workflows/update-regulations.yml)

**[Browse all current Norwegian laws →](https://github.com/loltek/norwegian-laws-and-regulations-md/tree/main/lover)**
**[Browse all current Norwegian regulations →](https://github.com/loltek/norwegian-laws-and-regulations-md/tree/main/forskrifter)**

Current Norwegian laws, regulations, and related central instruments as clean,
readable Markdown.

This repository combines Lovdata's **Lover** and **sentrale forskrifter**
datasets. The two datasets are kept separate: each has its own converter,
updater, index, and daily workflow. Only the repository is shared.

## What is included

### Laws (`lover/`)

- Current Norwegian laws (`gjeldende lover`), not historical or repealed laws
- Bokmål only; Nynorsk and Sami language variants are excluded
- Preserved structure: chapters, sections, paragraphs, lists, tables, and footnotes
- Metadata at the top of each file: short title, Lovdata date code, ministry,
  dates, legal area, and source URL
- Cross-references preserved as Markdown links

### Regulations (`forskrifter/`)

- Current central regulations (`sf`)
- Delegations (`del`), instructions (`ins`), and parliamentary decisions (`stv`)
  from the same Lovdata dataset
- Bokmål only; Nynorsk and Sami language variants are excluded
- Preserved structure: chapters, sections, paragraphs, lists, tables, figures,
  formulas, and footnotes
- Metadata at the top of each file, including ministry, legal basis
  (`Hjemmel`), publication, dates, and source URL
- Cross-references preserved as Markdown links

## File naming

Laws are named from the Lovdata date code and the law's short title:

```text
lover/lov-1915-08-13-5-domstolloven.md
lover/lov-1814-05-17-grunnloven-bokmaal.md
```

Regulations are named from the Lovdata date code and the document's short title:

```text
forskrifter/for-2004-12-01-1558-bokforingsforskriften.md
forskrifter/for-2009-12-15-1540-merverdiavgiftsforskriften.md
```

This keeps files sortable by date while still being recognizable.

## Layout

```text
lover/                         generated Markdown, one file per law
lover/index.json               machine-readable index of all laws
lover/dataset.json             law snapshot metadata
forskrifter/                   generated Markdown, one file per regulation
forskrifter/index.json         machine-readable index of all documents
forskrifter/dataset.json       regulation snapshot metadata
index.json                     manifest pointing at both datasets
llms.txt                       usage and coverage notes for LLM/RAG tools
tools/laws/                    law converter and updater
tools/regulations/             regulation converter and updater
tools/update.sh                run both updaters in parallel
.github/workflows/update-laws.yml
.github/workflows/update-regulations.yml
```

Each converter is deliberately strict. Unknown tags, classes, list types, table
constructs, or missing footnote targets abort the run instead of producing
silently broken Markdown.

## Regenerating

Install the Python dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

The updaters also need `b3sum` (Ubuntu: `sudo apt-get install b3sum`).

Download both datasets and regenerate everything:

```bash
tools/update.sh
```

Or update one dataset at a time:

```bash
tools/laws/update.sh
tools/regulations/update.sh
```

If you already have the extracted XML in `nl/` or `src/`, you can run a
converter directly:

```bash
python tools/laws/convert_to_markdown.py
python tools/regulations/convert_to_markdown.py
```

The regulations converter also supports `--resume` and `--only` for development:

```bash
python tools/regulations/convert_to_markdown.py --resume
python tools/regulations/convert_to_markdown.py --only sf/sf-20041201-1558.xml
```

Checkpoint files are ignored by git and are never used by CI.

Each updater downloads the source tarball, hashes it with BLAKE3 (`b3sum`), and
compares it with `source_b3sum` in the dataset's `dataset.json`. If the source
and converter are unchanged, it exits without extracting or regenerating
anything. Use `--force` to rebuild anyway:

```bash
tools/laws/update.sh --force
tools/regulations/update.sh --force
```

## For LLM and RAG use

Start with `index.json`, which points at the two dataset indexes:

- `lover/index.json` — one entry per law with title, date code, ministry,
  legal area, path, last change date, and source URL
- `forskrifter/index.json` — one entry per document with title, date code,
  category, ministry, legal area, legal basis (`based_on`), path, last change
  date, and source URL
- `lover/dataset.json` and `forskrifter/dataset.json` — snapshot date, counts,
  source URLs, and excluded languages
- `llms.txt` — short coverage and usage notes

Paths in both indexes are relative to the repository root, even though each
index lives in its dataset folder.

Suggested chunking: split on `##` for chapters and `###` for sections. Each
file starts with a metadata block and includes a `Kilde` URL.

## Link behavior

Links within a dataset point to the target Markdown file in the same folder.
Links across datasets use `../lover/...` or `../forskrifter/...`. Links to
external material (EU acts, preparatory works, legal areas, images) and exact
section links still point to Lovdata.

Exact section anchors within the Markdown files would be nice, but supporting
them correctly across all documents and cross-references is currently too much
effort. File-level links are deliberate.

## Sources

- Laws: <https://api.lovdata.no/v1/publicData/get/gjeldende-lover.tar.bz2>
- Regulations: <https://api.lovdata.no/v1/publicData/get/gjeldende-sentrale-forskrifter.tar.bz2>
- Lovdata: <https://lovdata.no/>

See each dataset's `dataset.json` for the current snapshot.

This project is not affiliated with or endorsed by Lovdata. Lovdata is the
authoritative source; these files are a convenience copy. See `NOTICE.md` for
source and licensing details.

## Status

Both workflows run daily at 03:17 UTC. If one fails, it opens an issue titled
`Automated law update failing since YYYY-MM-DD` or
`Automated regulation update failing since YYYY-MM-DD`, and closes it after the
next successful run. The badges above reflect the latest runs.

## License

The converters and repository tooling are licensed under the MIT License. The
legal texts are public legal information sourced from Lovdata; see `NOTICE.md`.

Nothing here is legal advice.
