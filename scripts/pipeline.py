import sys
import re
import time
import argparse
from pathlib import Path
from datetime import date, datetime
from typing import Optional

import pandas as pd
import duckdb

DB_PATH = Path("etl.duckdb")
REPORTS_DIR = Path(__file__).parent.parent / "reports"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

NULL_THRESHOLD = 0.30
HIGH_NULL_LOG_THRESHOLD = 0.80

BR_NUMBER_RE = re.compile(r"^\d{1,3}(\.\d{3})*(,\d+)?$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_col_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = name.strip("_")
    return name or "col"


def deduplicate_columns(cols: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result = []
    for col in cols:
        if col in seen:
            seen[col] += 1
            result.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 1
            result.append(col)
    return result


def try_parse_br_number(value: str) -> Optional[float]:
    """Convert Brazilian-formatted number strings like '1.234,56' to float."""
    s = value.strip()
    if BR_NUMBER_RE.match(s):
        return float(s.replace(".", "").replace(",", "."))
    return None


def try_parse_date(value: str) -> Optional[str]:
    formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y",
        "%d/%m/%y", "%Y/%m/%d", "%d.%m.%Y", "%B %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        return pd.to_datetime(value, infer_datetime_format=True).strftime("%Y-%m-%d")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract(csv_path: Path) -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

    raw_cols = list(df.columns)
    normalized = [normalize_col_name(c) for c in raw_cols]
    deduped = deduplicate_columns(normalized)

    rename_notes = []
    for orig, final in zip(raw_cols, deduped):
        if orig != final:
            rename_notes.append(f"  - '{orig}' → '{final}'")

    df.columns = deduped
    return df, rename_notes


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def transform(df: pd.DataFrame) -> tuple[pd.DataFrame, dict, int]:
    issues: dict[str, list[str]] = {col: [] for col in df.columns}
    rows_in = len(df)

    # Replace empty strings with NaN so null counting works
    df = df.replace("", pd.NA)

    # Discard rows with >30% nulls
    null_frac = df.isna().mean(axis=1)
    discarded_mask = null_frac > NULL_THRESHOLD
    discarded = int(discarded_mask.sum())
    if discarded:
        df = df[~discarded_mask].copy()

    # Log columns with >80% nulls (do NOT drop)
    for col in df.columns:
        col_null_frac = df[col].isna().mean()
        if col_null_frac > HIGH_NULL_LOG_THRESHOLD:
            issues[col].append(
                f"AVISO: {col_null_frac:.0%} de valores nulos (coluna mantida)"
            )

    # Column-by-column type inference and conversion
    for col in df.columns:
        series = df[col]
        non_null = series.dropna()

        if non_null.empty:
            continue

        # Strip whitespace from all string values
        df[col] = series.map(lambda v: v.strip() if isinstance(v, str) else v)
        non_null = df[col].dropna()

        # Try Brazilian number format first
        br_hits = non_null.map(lambda v: try_parse_br_number(v) is not None)
        if br_hits.all():
            df[col] = non_null.map(
                lambda v: try_parse_br_number(v) if pd.notna(v) else pd.NA
            )
            issues[col].append(f"Convertido de formato numérico BR para float")
            continue

        # Try plain numeric
        try:
            numeric = pd.to_numeric(non_null, errors="raise")
            df[col] = pd.to_numeric(df[col], errors="coerce")
            if numeric.apply(float.is_integer).all():
                df[col] = df[col].astype("Int64")
                issues[col].append("Inferido como inteiro")
            else:
                issues[col].append("Inferido como float")
            continue
        except (ValueError, TypeError):
            pass

        # Try date
        date_parsed = non_null.map(try_parse_date)
        if date_parsed.notna().all():
            df[col] = df[col].map(
                lambda v: try_parse_date(v) if pd.notna(v) else pd.NA
            )
            issues[col].append("Datas normalizadas para ISO 8601")
            continue

        # Keep as string — strip already applied above

    return df, issues, discarded


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load(df: pd.DataFrame, table_name: str) -> None:
    con = duckdb.connect(str(DB_PATH))
    try:
        con.register("_df_tmp", df)
        con.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        con.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM _df_tmp')
    finally:
        con.close()


def table_exists(table_name: str) -> bool:
    con = duckdb.connect(str(DB_PATH))
    try:
        result = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = ?",
            [table_name],
        ).fetchone()
        return result[0] > 0
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def build_report(
    table_name: str,
    csv_path: Path,
    df: pd.DataFrame,
    issues: dict[str, list[str]],
    rename_notes: list[str],
    rows_in: int,
    discarded: int,
    elapsed: float,
) -> str:
    rows_out = len(df)
    today = date.today().isoformat()

    schema_lines = []
    for col in df.columns:
        schema_lines.append(f"| {col} | {df[col].dtype} |")
    schema_table = "\n".join(schema_lines)

    issues_section = []
    for col, notes in issues.items():
        if notes:
            issues_section.append(f"\n### `{col}`")
            for note in notes:
                issues_section.append(f"- {note}")

    rename_section = ""
    if rename_notes:
        rename_section = "\n**Colunas renomeadas:**\n" + "\n".join(rename_notes)

    report = f"""# Relatório ETL — {table_name}

**Data:** {today}
**Arquivo fonte:** `{csv_path.name}`
**Tabela DuckDB:** `{table_name}`
**Tempo total:** {elapsed:.2f}s

---

## Contagem de linhas

| Métrica | Valor |
|---|---|
| Recebidas | {rows_in} |
| Descartadas (>30% nulos) | {discarded} |
| Processadas e gravadas | {rows_out} |

---

## Renomeação de colunas
{rename_section if rename_section else "_Nenhuma coluna foi renomeada._"}

---

## Problemas detectados e corrigidos por coluna
{"".join(issues_section) if issues_section else "_Nenhum problema detectado._"}

---

## Schema final (tabela `{table_name}`)

| Coluna | Tipo |
|---|---|
{schema_table}
"""
    return report.strip()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="ETL pipeline para arquivos CSV")
    parser.add_argument("csv_path", help="Caminho para o arquivo CSV")
    args = parser.parse_args()

    csv_path = Path(args.csv_path).resolve()
    if not csv_path.exists():
        print(f"Erro: arquivo não encontrado — {csv_path}")
        sys.exit(1)

    table_name = csv_path.stem

    if table_exists(table_name):
        print(
            f"Tabela '{table_name}' já existe no DuckDB. "
            "Remova-a manualmente para reprocessar."
        )
        sys.exit(0)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()

    print(f"[Extract] Lendo {csv_path.name} ...")
    df, rename_notes = extract(csv_path)
    rows_in = len(df)

    print(f"[Transform] {rows_in} linhas recebidas, aplicando regras de qualidade ...")
    df, issues, discarded = transform(df)

    print(f"[Load] Gravando tabela '{table_name}' no DuckDB ...")
    load(df, table_name)

    processed_path = PROCESSED_DIR / csv_path.name
    df.to_csv(processed_path, index=False)

    elapsed = time.perf_counter() - t0

    report_text = build_report(
        table_name, csv_path, df, issues, rename_notes,
        rows_in, discarded, elapsed,
    )

    today = date.today().strftime("%Y%m%d")
    report_path = REPORTS_DIR / f"relatorio_{table_name}_{today}.md"
    report_path.write_text(report_text, encoding="utf-8")

    rows_out = len(df)
    print(
        f"\n{'='*50}\n"
        f"  Arquivo   : {csv_path.name}\n"
        f"  Tabela    : {table_name}\n"
        f"  Recebidas : {rows_in}\n"
        f"  Descartadas: {discarded}\n"
        f"  Gravadas  : {rows_out}\n"
        f"  Relatório : {report_path.name}\n"
        f"  Tempo     : {elapsed:.2f}s\n"
        f"{'='*50}"
    )


if __name__ == "__main__":
    main()
