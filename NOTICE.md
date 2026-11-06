# Source and data notice

## Sources

The Markdown files are generated from Lovdata's public datasets:

- Laws: <https://api.lovdata.no/v1/publicData/get/gjeldende-lover.tar.bz2>
- Regulations: <https://api.lovdata.no/v1/publicData/get/gjeldende-sentrale-forskrifter.tar.bz2>

The datasets contain current Norwegian laws (`gjeldende lover`), central
regulations (`sentrale forskrifter`), and related central instruments, and are
updated by Lovdata nightly.

## Scope

- `lover/` contains current laws. Lovdata's dataset excludes repealed laws,
  except where an old law still applies in a limited scope.
- `forskrifter/` contains the `sf`, `del`, `ins`, and `stv` categories from
  Lovdata's sentrale forskrifter dataset. Only current documents are included;
  the dataset excludes repealed documents, except where an older document still
  applies in a limited scope.
- Nynorsk (`lang="nn"`) and Sami language variants are excluded.
- Each document is converted from Lovdata's HTML/XML export to Markdown.

## Attribution and licensing

The texts are public legal information. Lovdata's name, logo, and trademarks
belong to Lovdata. This project is not affiliated with or endorsed by Lovdata.

The converters and repository tooling are licensed under the MIT License; see
`LICENSE`.

If you redistribute these files, keep this notice and the source URLs, and check
Lovdata's current terms for any additional conditions.

## Accuracy

Lovdata is the authoritative source. These files are a convenience copy and may
lag behind the latest published version. Nothing in this repository is legal
advice.
