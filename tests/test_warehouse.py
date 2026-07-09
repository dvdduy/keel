from pathlib import Path
from keel.adapters.warehouse.duckdb_warehouse import DuckDbWarehouse

FIXTURE = Path(__file__).parent / "fixtures" / "orders.csv"


def test_ingest_csv_materializes_raw_table(tmp_path):
    wh = DuckDbWarehouse(str(tmp_path / "w.duckdb"))
    try:
        rows = wh.ingest_csv("raw.orders", FIXTURE)
        assert rows == 3
        assert wh.row_count("raw.orders") == 3
    finally:
        wh.close()
