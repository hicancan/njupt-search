from pathlib import Path


def test_collection_update_is_triggered_by_sitegraph_dispatch():
    workflow = Path(".github/workflows/update-collection-index.yml")
    assert workflow.exists()
    text = workflow.read_text(encoding="utf-8")
    assert "repository_dispatch:" in text
    assert "sitegraph-data-updated" in text
    assert "cron: '30 */6 * * *'" not in text
    assert "github.event.client_payload.sitegraph_ref" in text
    assert "ref: ${{ env.SITEGRAPH_REF }}" in text


def test_collection_update_uses_configured_source_packages():
    workflow = Path(".github/workflows/update-collection-index.yml")
    text = workflow.read_text(encoding="utf-8")
    assert "NJUPT_SITEGRAPH_REPO: _sitegraph/njupt-site-graph" in text
    assert "--source-package \"$SITEGRAPH_JWC_INDEX\"" not in text
    assert "python -m njupt_search_indexer validate --skip-output" in text
