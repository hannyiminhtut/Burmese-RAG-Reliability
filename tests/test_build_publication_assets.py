from src.build_publication_assets import table_rows, verify_freezes


def test_all_source_freezes_verify():
    assert set(verify_freezes()) == {"experiment", "automated", "statistics", "error_analysis"}


def test_publication_tables_preserve_required_counts():
    import json
    from src.build_publication_assets import EXPERIMENT_FREEZE, AUTO_JSON, STATS_JSON, ERROR_JSON
    load=lambda p: json.loads(p.read_text(encoding="utf-8"))
    tables=table_rows(load(EXPERIMENT_FREEZE),load(AUTO_JSON),load(STATS_JSON),load(ERROR_JSON))
    assert len(tables)==7
    heldout=next(r for r in tables["table1_dataset_split.csv"] if r["Item"]=="Question variants")
    assert heldout["Held-out"]==222


def test_semantic_metrics_are_not_added_to_tables():
    import inspect
    from src import build_publication_assets
    source=inspect.getsource(build_publication_assets.table_rows).lower()
    assert "hallucination" not in source and "groundedness" not in source
