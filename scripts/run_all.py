import sys
import subprocess
from datetime import datetime
from pathlib import Path

import duckdb

RAW_DIR = Path("data/raw")
DB_PATH = Path("etl.duckdb")
PIPELINE = Path("scripts/pipeline.py")


def get_existing_tables() -> set:
    if not DB_PATH.exists():
        return set()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute("SHOW TABLES").fetchall()
        return {row[0] for row in rows}
    finally:
        con.close()


def main() -> None:
    if not RAW_DIR.exists():
        print(f"Diretório {RAW_DIR} não encontrado.")
        sys.exit(1)

    csv_files = sorted(RAW_DIR.glob("*.csv"))
    if not csv_files:
        print(f"Nenhum arquivo .csv encontrado em {RAW_DIR}.")
        sys.exit(0)

    existing = get_existing_tables()
    pending = [f for f in csv_files if f.stem not in existing]
    already = len(csv_files) - len(pending)

    print(f"CSVs encontrados : {len(csv_files)}")
    print(f"Já existem no DB : {already}")
    print(f"A processar      : {len(pending)}")

    if not pending:
        print("\nNenhum arquivo novo para processar. Banco já está atualizado.")
        sys.exit(0)

    print()
    processed = 0
    failed = 0

    for csv_path in pending:
        index = processed + failed + 1
        print(f"[{index}/{len(pending)}] {csv_path.name}")
        result = subprocess.run(
            [sys.executable, str(PIPELINE), str(csv_path)]
        )
        if result.returncode == 0:
            processed += 1
        else:
            print(f"  ERRO: exit code {result.returncode}")
            failed += 1
            failures_log = Path("reports/failures.log")
            failures_log.parent.mkdir(parents=True, exist_ok=True)
            with failures_log.open("a", encoding="utf-8") as f:
                f.write(
                    f"{datetime.now().isoformat(timespec='seconds')} | "
                    f"{csv_path.name} | exit_code={result.returncode}\n"
                )

    print(f"\n{'='*50}")
    print(f"  Encontrados  : {len(csv_files)}")
    print(f"  Já existiam  : {already}")
    print(f"  Processados  : {processed}")
    if failed:
        print(f"  Com erro     : {failed}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
