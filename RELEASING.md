# Releasing carculator_utils 1.3.7

Use Python 3.12 and the matching family release set:

| Package | Release version |
| --- | --- |
| `carculator_utils` | 1.3.7 |
| `carculator` | 1.9.7 |
| `carculator_truck` | 0.5.2 |
| `carculator_bus` | 0.1.2 |
| `carculator_two_wheeler` | 0.1.1 |


1. Review `CHANGELOG.md`, known limitations in `docs/validity.rst`, and the worktree.
   Preserve local notebooks and inventories; commit only the intended release files.
2. Check `carculator_utils/_version.py`, `conda/meta.yaml` and dependency metadata together.
   Sphinx reads the package version automatically. All vehicle packages require
   `carculator_utils>=1.3.7`, including the optional export extras.
3. Build and verify actual artifacts from this checkout (use a new output directory):

```bash
python scripts/verify_installation.py --repositories . --output /tmp/carculator_utils-release-check --run-tests
```

For the complete family, run from `carculator_utils`:

```bash
python scripts/verify_installation.py \
  --repositories . ../carculator ../carculator_truck ../carculator_bus ../carculator_two_wheeler \
  --output /tmp/carculator-family-release-check --run-tests --test-timeout 2400
```

The verifier builds wheels and sdists, rebuilds wheels from sdists, compares
packaged resource hashes, runs installed tests with export extras and checks
offline core-only model/LCIA runs. Keep `report.json`, test XML, dependency freezes
and artifact hashes with the release record. A local pass does not establish
that Linux, Windows or hosted CI passed. Confirm the release commit's CI separately.

Each repository's test suite has a 30-minute subprocess limit by default.
Use `--test-timeout SECONDS` to adjust it; the full family CI job uses 2400
seconds per suite within its existing 60-minute job limit. Build, installation
and smoke commands keep their 900-second limits. The installation log records
each command's limit, individual test names and the 20 slowest test durations,
so a timeout can be traced to the active suite and test. Splitting or profiling
expensive integration tests is preferable to repeatedly increasing the limit.

Electricity, emissions and IAM text resources have explicit LF checkout
attributes because their provenance records hash exact bytes. Normalize new or
regenerated resources to LF before computing their fingerprints; Git can
normalize CRLF on commit while leaving the local working file untouched. Hashes
from that working file would then disagree with a fresh checkout. Preserve the
attributes and verify the manifests from fresh checkouts with both
`core.autocrlf=false` and `core.autocrlf=true`:

```bash
python -m pytest tests/test_resource_checkouts.py tests/test_emission_provenance.py tests/test_iam_bundle.py
```

The checkout regression also verifies that an unprotected control file receives
Windows line endings. Binary matrices and scientific values are unchanged by
these text-file conventions; retain their exact-byte manifest checks.

4. Install `docs/docs_requirements.txt`, build with `python -m sphinx -b html docs docs/_build/html`,
   and run the README example. Check wheel/sdist metadata before publication:

```bash
python -m pip install twine
python -m twine check --strict /tmp/carculator-family-release-check/wheels/carculator_utils-1.3.7-py3-none-any.whl /tmp/carculator-family-release-check/wheels/carculator_utils-1.3.7.tar.gz
```

5. Publish `carculator_utils` **first** and confirm that 1.3.7 is available before
   publishing the four vehicle packages. The same ordering applies to conda.
   Replace `Unreleased` with the actual publication date in the changelog, commit
   the final release metadata, and verify the final artifacts. Create an annotated
   `v.1.3.7` tag on that reviewed commit, following existing tag conventions.
   Do not reuse an existing tag or upload a different build under the same version.
6. Publish the GitHub release for the reviewed tag. The `main.yml` workflow
   verifies installed artifacts on Linux, macOS, and Windows before uploading the
   exact verified wheel and sdist to PyPI using the existing `PYPI_TOKEN` secret.
   Tags `v.X.Y.Z` and `vX.Y.Z` are accepted; the tag, package version, and conda
   recipe version must match. Attach the verification record to the release.
7. The workflow also builds and tests the matching noarch conda package, then
   uploads it to the `romainsacchi` channel using `ANACONDA_CLOUD`. Required
   dependencies must already be available in the configured conda channels.

To publish an existing tag after this workflow reaches the default branch, run
**Actions → Installed artifacts and release publishing → Run workflow** on that
branch and enter the tag in `release_tag`. The workflow checks out and verifies
that tag before publishing; an empty input only verifies. Existing registry files
are skipped on reruns. Ordinary pushes and pull requests only run verification;
creating a tag alone does not publish. Publish its GitHub release instead.

Utils publication also requires the existing full vehicle-family verification
job to pass, using the tagged utils checkout.


The metadata and README examples target this release; older published
packages may not provide the documented APIs or 2025 defaults.


## Coordinated release on 2026-10-11

Publish utils before its consumers, confirming the new dependency is available
on PyPI and conda before publishing the vehicle packages. Do not reuse the
previous utils/car/truck/bus versions published on 2026-10-08.

This release includes the solar-PV and dry-mass hydrogen-tank updates committed
in utils revision `639151d8229872052d882428af1e2927d4aecb3b`.
The [preparation record](docs/_static/release_candidate_20261011.json) distinguishes
the earlier local artifact checks from the final release qualification. Those
earlier artifacts excluded these updates and must not be uploaded as this release.

Verify the final release commits on Linux, macOS and Windows and verify the
coordinated vehicle family before publishing. All five default branches must
contain the matching release metadata; CI uses these branches unless explicit
`CARCULATOR_*_REF` variables override them. Record resolved SHAs with the release.
Attach the final GitHub Actions verification records and artifact hashes.
Conda builds and publication must be checked separately from ordinary push CI.

## Historical verification record

On 2026-10-08, the five-package installed-artifact suites passed **497 tests**,
with one existing expected two-wheeler cost failure. Wheel and sdist-built
wheel resource checks, offline core-only model/LCIA runs, strict Twine metadata
checks, README execution and the documented inventory exports passed. All five
Sphinx sites built using the release wheels and their `docs` extras.

The [release verification record](docs/_static/release_verification.json)
contains versions, artifact hashes, test counts and qualifications. Builds were
local on macOS with Python 3.12; hosted CI and conda builds need separate
qualification. Existing documentation warnings are recorded. These checks
exercise packaging and software consistency; they do not establish physical
plausibility or replace the measurement evidence and limitations in [model validation](docs/validity.rst).

## Documentation-only changes

Pushes and pull requests limited to `docs/`, root Markdown files, or
`examples/` skip CI. Code, test, packaging and workflow changes still run
verification. Release and manual publishing triggers are unaffected.
