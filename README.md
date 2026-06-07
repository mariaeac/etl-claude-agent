# etl-claude-agent

Schema-agnostic ETL pipeline that detects, cleans, and loads any CSV dropped into `data/raw/` into a local DuckDB database, then generates a per-run Markdown report.

---

## How it works

1. Drop a CSV file into `data/raw/`.
2. The pipeline reads the file and auto-detects its schema — no column names are hardcoded anywhere.
3. A set of universal quality rules is applied: column normalization, null filtering, type inference, date standardization, and Brazilian number format conversion.
4. The cleaned data is written to a DuckDB table named after the file (e.g. `vendas.csv` → table `vendas`) and exported to `data/processed/`.
5. A Markdown report is generated in `reports/` with row counts, per-column issues, final schema, and execution time.

Files already loaded into DuckDB are skipped on subsequent runs — only new files are processed.

---

## Stack

| Tool | Why |
|---|---|
| **Python** | Scripting and data wrangling |
| **pandas** | Schema inference, type coercion, and row-level transformations |
| **DuckDB** | Embedded analytical database — no server, single file, fast on columnar queries |
| **Claude Code** | Runs the pipeline as an agent: detects new files, triggers processing, reads reports, and summarizes findings |

---

## How to run

### Python directly

Process a single file:

```bash
python3 scripts/pipeline.py data/raw/myfile.csv
```

Process all new files in `data/raw/` at once:

```bash
python3 scripts/run_all.py
```

### Via Claude Code

Open the project in Claude Code and ask it to process new files:

```
tem arquivos novos em data/raw esperando ser processados. execute o pipeline para todos eles e resume o que foi encontrado.
```

Claude Code reads `CLAUDE.md`, detects which files haven't been loaded yet, runs the pipeline for each one, reads the generated reports, and returns a structured summary — no manual steps required.

---

## Example output

Run against `locode.csv` (UN/LOCODE — international port and logistics location codes):

```
==================================================
  Arquivo   : locode.csv
  Tabela    : locode
  Recebidas : 116213
  Descartadas: 29402
  Gravadas  : 86811
  Relatório : relatorio_locode_20260606.md
  Tempo     : 54.00s
==================================================
```

**What the pipeline found:**

- 29,402 rows discarded (25%) — inter-country separator lines in the LOCODE format, which have >30% null fields
- 3 columns flagged for high nulls: `change` (100%), `iata` (99%), `remarks` (99%) — kept but logged
- All 12 column names normalized to lowercase (e.g. `NameWoDiacritics` → `namewodiacritics`)
- No columns dropped

Generated report excerpt (`reports/relatorio_locode_20260606.md`):

```
| Métrica       | Valor  |
|---|---|
| Recebidas     | 116213 |
| Descartadas   | 29402  |
| Gravadas      | 86811  |

### `change` — AVISO: 100% de valores nulos (coluna mantida)
### `iata`   — AVISO: 99% de valores nulos (coluna mantida)
### `remarks` — AVISO: 99% de valores nulos (coluna mantida)
```

---

## Project structure

```
etl-claude-agent/
├── data/
│   ├── raw/           # Source CSVs — never modified or deleted by the pipeline
│   └── processed/     # Cleaned CSVs output by the pipeline
├── scripts/
│   ├── pipeline.py    # Core ETL logic: extract → transform → load → report
│   └── run_all.py     # Batch runner: processes all new CSVs in data/raw/
├── reports/           # Per-run Markdown reports (one per file per day)
├── CLAUDE.md          # Agent instructions and quality rules
└── etl.duckdb         # Local DuckDB database (auto-created on first run)
```
