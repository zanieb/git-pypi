from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def test_release_only_selects_main_push_artifacts() -> None:
    workflow = (WORKFLOWS / "release.yml").read_text()

    assert '[[ ! "$REQUESTED_COMMIT" =~ ^[0-9a-fA-F]{40}$ ]]' in workflow
    assert 'compare/"$COMMIT"...main' in workflow
    assert "ahead|identical" in workflow
    assert '-f head_sha="$COMMIT"' in workflow
    assert "-f event=push" in workflow
    assert "-f branch=main" in workflow
    assert '[ "$run_sha" != "$COMMIT" ]' in workflow
    assert '[ "$run_event" != "push" ]' in workflow
    assert '[ "$run_branch" != "main" ]' in workflow


def test_release_inputs_cannot_override_validated_outputs() -> None:
    workflow = (WORKFLOWS / "release.yml").read_text()

    assert "REQUESTED_BUILD: ${{ inputs.build }}" in workflow
    assert 'BUILD="$REQUESTED_BUILD"' in workflow
    assert '[[ ! "$BUILD" =~ ^[0-9]{8}$ ]]' in workflow
    assert 'BUILD="${{ inputs.build }}"' not in workflow


def test_wheel_sources_are_checked_out_from_explicit_commit() -> None:
    workflow = (WORKFLOWS / "build-wheels.yml").read_text()

    checkout_count = workflow.count("- uses: actions/checkout@")
    assert checkout_count == 3
    assert workflow.count("ref: ${{ inputs.commit }}") == checkout_count


def test_every_wheel_workflow_caller_passes_a_commit() -> None:
    callers = {
        "ci.yml": "commit: ${{ github.sha }}",
        "release.yml": "commit: ${{ needs.resolve-ci-run.outputs.commit }}",
    }

    for filename, expected_commit in callers.items():
        workflow = (WORKFLOWS / filename).read_text()
        assert "uses: ./.github/workflows/build-wheels.yml" in workflow
        assert expected_commit in workflow
