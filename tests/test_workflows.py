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
    assert "DISPATCH_SITEGRAPH_REF" in text
    assert "DISPATCH_SOURCE_REPO" in text
    assert "DISPATCH_SOURCE_RUN_ID" in text
    assert "repository_dispatch missing client_payload.sitegraph_ref" in text
    assert "repository_dispatch source_repo must be hicancan/njupt-site-graph" in text
    assert "repository_dispatch missing client_payload.source_run_id" in text
    assert "Validate sitegraph ref exists" in text
    assert "repos/hicancan/njupt-site-graph/commits/$SITEGRAPH_REF" in text
    assert "sitegraph_ref $SITEGRAPH_REF is not a commit visible in hicancan/njupt-site-graph" in text
    assert "python tools/ci/commit_generated_changes.py" in text
    assert "--add apps/web/public/generated/collections/njupt-public/" in text
    assert "git push" not in text


def test_collection_update_uses_configured_source_packages():
    workflow = Path(".github/workflows/update-collection-index.yml")
    text = workflow.read_text(encoding="utf-8")
    assert "NJUPT_SITEGRAPH_REPO: _sitegraph/njupt-site-graph" in text
    assert "--source-package \"$SITEGRAPH_JWC_INDEX\"" not in text
    assert "python -m njupt_search_indexer validate --skip-output" in text


def test_exam_update_uses_retrying_generated_commit_helper():
    workflow = Path(".github/workflows/update-exam-data.yml")
    assert workflow.exists()
    text = workflow.read_text(encoding="utf-8")
    assert "python tools/ci/commit_generated_changes.py" in text
    assert "--add apps/web/public/generated/exam/" in text
    assert "git push" not in text


def test_generated_commit_helper_retries_push_after_rebase():
    helper = Path("tools/ci/commit_generated_changes.py")
    assert helper.exists()
    text = helper.read_text(encoding="utf-8")
    assert 'git", "push", "origin", f"HEAD:{branch}"' in text
    assert 'git", "fetch", "origin", branch' in text
    assert 'git", "rebase", f"origin/{branch}"' in text
    assert "GITHUB_OUTPUT" in text
