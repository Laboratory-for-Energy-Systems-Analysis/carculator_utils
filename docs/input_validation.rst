Input validation and family verification
========================================

These contracts are shared by ``carculator``, ``carculator_truck``,
``carculator_bus``, and ``carculator_two_wheeler``.

Parameter records
-----------------

Vehicle input classes validate parameter records when they are loaded, before
sampling or building the model array. Invalid records raise ``ValueError`` with
the record identifier, parameter name when available, and offending field.

* Each record needs a nonempty ``name``, nonempty sequences of unique string
  labels in ``sizes`` and ``powertrain``, an integer ``year``, and an ``amount``.
* ``amount`` and any supplied ``loc``, ``minimum``, ``maximum``, ``scale``, or
  ``shape`` must be finite numbers. Booleans and numeric strings are rejected.
* ``minimum`` must not exceed ``maximum``.
* Triangular distributions (``uncertainty_type=5``) require explicit ``minimum``,
  ``loc`` and ``maximum`` values, with ``minimum < maximum`` and
  ``minimum <= loc <= maximum``. Here ``loc`` is the most likely value;
  ``amount`` remains the separate static input. A mode equal to either bound is
  valid. Use ``uncertainty_type=1`` for a deterministic value instead of a
  zero-width triangle. Errors identify the record, parameter, year, sizes and
  powertrains. Other distribution-specific requirements still apply on sampling.

Sampling precedes array scope selection, so every supplied record must define a
valid distribution, including future years outside the intended model scope.
The family regressions exercise complete packaged defaults before selecting
vehicles and years. The truck package documents its repaired cost bounds in
``docs/uncertainty_bounds.rst`` and ships their original records and 2020 anchors
in ``data/cost_uncertainty_provenance.json``.

Some bundled records overlap after expansion across sizes and powertrains.
Their existing first-record precedence is preserved. Authors can explicitly
audit new data for overlapping cells:

.. code-block:: python

    from carculator_utils.vehicle_input_parameters import (
        load_parameters,
        validate_parameters,
    )

    records = load_parameters("my_parameters.json")
    validate_parameters(records, check_duplicates=True)

This audit identifies the duplicated ``(name, size, powertrain, year)`` cell and
the two record identifiers. It does not rewrite data or resolve conflicts.

Fuel blends
-----------

Each supplied fuel category must have a primary component with a known fuel
``type`` and a ``share``. Shares must be finite numbers between zero and one.
They may be scalars, one-element sequences, or one-dimensional sequences with
one entry per model year, in the order of ``array.year``. Scalars and
one-element sequences are expanded to all years.

.. code-block:: python

    fuel_blend = {
        "diesel": {
            "primary": {"type": "diesel", "share": 0.8},
            "secondary": {
                "type": "diesel - biodiesel - cooking oil",
                "share": 0.2,
            },
        }
    }
    # Pass fuel_blend=fuel_blend to a vehicle model constructor.

An omitted secondary component is completed with the default secondary fuel and
the complementary share. If both components are provided, their shares must sum
to one for every year (absolute tolerance ``1e-7``). The caller's dictionary is
preserved. Unsupported categories, unknown fuel types, malformed shapes, and
invalid shares raise contextual ``ValueError`` exceptions.

When an inventory is constructed, selected suppliers must exist in the bundled
inventory index. An unresolved supplier raises ``KeyError`` naming the category,
component, fuel type, and supplier before the large inventory matrices are
allocated. A fuel specification alone does not guarantee a corresponding
inventory supplier; missing mappings require a justified data update.

Testing the vehicle family
--------------------------

The ``family`` pytest marker covers small real models from all four vehicle
packages: sizing and mass balance, coordinate and caller-data preservation,
sample-specific functional-unit normalization, and repeatable static exports
for multiple years. It also covers car PHEVs, bus charging modes, human and
electric bicycles, and multi-year fuel blends. Static exports use one value
sample; multi-sample inventories are tested through LCIA.

Install all sibling checkouts into a Python 3.12 environment:

.. code-block:: bash

    python -m pip install -e ".[test,excel,brightway]" \
      -e ../carculator -e ../carculator_truck \
      -e ../carculator_bus -e ../carculator_two_wheeler
    python -m pytest tests/test_vehicle_family.py

Absent sibling packages are skipped during an ordinary utils-only test run.
Set the environment variable ``CARCULATOR_REQUIRE_FAMILY=1`` to make missing
packages fail. The family CI job requires all four packages on Python 3.12
and runs the existing artifact verifier:

.. code-block:: bash

    python scripts/verify_installation.py \
      --repositories . ../carculator ../carculator_truck \
        ../carculator_bus ../carculator_two_wheeler \
      --output /tmp/carculator-family-verification --run-tests

The output directory must not already exist. The verifier builds wheels and
source distributions, checks bundled resource hashes, runs all suites against
installed wheels, and compares offline model results from wheel and rebuilt
source-distribution installations. Dependency installation requires network
access.

CI uses the candidate utils revision and the siblings' default branches.
Repository variables ``CARCULATOR_REF``, ``CARCULATOR_TRUCK_REF``,
``CARCULATOR_BUS_REF``, and ``CARCULATOR_TWO_WHEELER_REF`` can select branches,
tags, or commit hashes for coordinated compatibility checks. Existing
utils-only jobs retain the Linux, macOS, and Windows matrix.
