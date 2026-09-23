"""Guard release routing, upload permissions and tested artifact selection."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def workflow(name):
    # BaseLoader preserves the YAML 1.2 Actions key `on` as a string.
    return yaml.load((ROOT / name).read_text(), Loader=yaml.BaseLoader)


def test_release_requires_all_gates_and_is_tag_only():
    release = workflow("release.yml")
    assert release["on"] == {"push": {"tags": ["v*"]}}
    jobs = release["jobs"]
    assert jobs["publish"]["needs"] == ["tests", "security"]
    for job, filename in [("tests", "tests.yml"), ("security", "security.yml")]:
        assert jobs[job]["needs"] == "release-guard"
        assert jobs[job]["uses"] == f"./.github/workflows/{filename}"
        assert "workflow_call" in workflow(filename)["on"]
        assert workflow(filename)["on"]["push"] == {"branches": ["**"]}
    guard = jobs["release-guard"]["steps"][-1]["run"]
    assert "git merge-base --is-ancestor HEAD origin/master" in guard
    assert '^v[0-9]+\\.[0-9]+\\.[0-9]+$' in guard


def test_upload_is_isolated_and_uses_tested_artifact():
    release = workflow("release.yml")
    assert release["permissions"] == {"contents": "read"}
    publish = release["jobs"]["publish"]
    assert publish["permissions"] == {"id-token": "write"}
    assert publish["environment"]["name"] == "pypi"
    steps = publish["steps"]
    assert len(steps) == 2
    assert steps[0]["with"]["name"] == "release-dist"
    assert steps[0]["with"]["digest-mismatch"] == "error"
    assert steps[1]["with"]["skip-existing"] == "false"
    assert not {"password", "username"} & steps[1]["with"].keys()
    uploads = [s for s in workflow("tests.yml")["jobs"]["test"]["steps"]
               if s.get("with", {}).get("name") == "release-dist"]
    assert len(uploads) == 1
    assert "matrix.python == '3.13'" in uploads[0]["if"]
    assert uploads[0]["with"]["path"] == "dist/*"
