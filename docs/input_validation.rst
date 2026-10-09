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

Bus temperature inputs
----------------------

Bus HVAC uses ``ambient_temperature`` in degrees Celsius. A scalar applies to
every month; a sequence supplies twelve values in January--December order.
The cabin assumption is fixed at 20 degrees Celsius: ``indoor_temperature`` may
be the scalar ``20`` or twelve monthly values all equal to ``20``. Other values
raise ``ValueError`` before bus sizing because the empirical HVAC curve does
not model cabin-setpoint changes. Direct ``EnergyConsumptionModel`` callers
follow the same restriction, which is also checked when calculating HVAC loads.
See :ref:`cabin-temperature-limitation` for scope and migration details.

HVAC demand still varies with outside temperature. Ambient-temperature overrides
are validated and preserved. Passenger cars, trucks and two-wheelers use annual
thermal-demand inputs and reject temperature overrides.

When ``ambient_temperature`` is omitted, the model reads the first city row for
the selected country in ``data/monthly_avg_temp.csv``. This is a city proxy,
not a national driving-weighted climate. Missing countries raise ``ValueError``
and require an explicit local monthly profile or scalar. The former automatic
Swiss substitution has been removed. Decimal temperatures are preserved.
See :ref:`temperature-fallback-checks` for scope and verification.

Fuel blends
-----------

``fuel_blend`` overrides only the fuel categories supplied. All other fuels
needed by the selected powertrains retain their defaults. Petrol, diesel and
methane use country- and year-specific biofuel shares. Hydrogen uses 100%
natural-gas steam methane reforming in every country and year, as a documented
fallback assumption; see :ref:`default-hydrogen-supply`.
``None`` or an empty dictionary uses defaults for every selected fuel.
For example, the diesel override below also works in a comparison containing
petrol, methane and hydrogen vehicles: those fuels retain their default blends.
Previously, any nonempty override replaced the entire configuration, so omitted
categories could cause ``KeyError`` during ``set_all()``.

Default biofuel fractions are interpolated or extrapolated from the bundled
country data with bounds of 0--100%. The former universal 30% cap has been
removed, preserving supplied biomethane shares above that threshold. See
:ref:`default-biofuel-shares` for the affected defaults and completed-run checks.

Each supplied fuel category must have a primary component with a known fuel
``type`` and a ``share``. Shares must be finite numbers between zero and one.
They may be scalars, one-element sequences, or one-dimensional sequences with
one entry per model year, in the order of ``array.year``. Scalars and
one-element sequences are expanded to all years.

Both primary and secondary fuel types must belong to the supplied category's
``all`` list in ``data/fuel/default_fuels.yaml``. This includes components with a
zero share. A known hydrogen fuel under ``diesel`` or ``petrol``, for example,
raises ``ValueError`` during model construction, identifying the category,
component and incompatible type. Earlier versions accepted that mismatch and
could combine a conventional combustion vehicle model with hydrogen supply and
zero tailpipe CO2. Valid fossil, biofuel and synthetic routes remain available
within their respective categories.

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

Each supplied category replaces its default as a whole. An omitted secondary
component is completed with the default secondary fuel and the complementary
share, rather than retaining the country's default share. If both components
are provided, their shares must sum to one for every year (absolute tolerance
``1e-7``). The caller's dictionary is preserved. Unsupported categories, unknown
fuel types, incompatible categories, malformed shapes, and invalid shares raise
contextual ``ValueError`` exceptions.

Optional fuel-property overrides are also validated at construction:

.. list-table:: Component properties
   :header-rows: 1
   :widths: 25 35 40

   * - Key
     - Unit
     - Allowed values
   * - ``lhv``
     - MJ/kg fuel
     - Finite and strictly positive
   * - ``density``
     - kg/L
     - Finite and strictly positive
   * - ``CO2``
     - kg CO2/kg fuel burned
     - Finite and nonnegative
   * - ``biogenic share``
     - Fraction of combustion CO2
     - Finite and within [0, 1]

These properties accept numbers, one-element sequences, or one-dimensional
sequences with one value per model year, in ``array.year`` order. Year sequences
are normalized for numerical calculations without changing caller data. Booleans,
numeric strings, nonfinite values, invalid bounds and incorrect shapes raise
``ValueError`` naming the fuel category, component and property. Both components
are checked, including those with a zero blend share. Omitted properties continue
to use the selected fuel's catalog values.

Blend density uses mass fractions and additive component volumes:
``rho_mix = 1 / sum(w_i / rho_i)``, where ``w_i`` is a component's mass share
and ``rho_i`` its density in kg/L. Lower heating value remains mass-weighted
in MJ/kg. Thus reported fuel litres equal the sum of component masses divided
by their respective densities. This approximation does not represent volume
contraction or expansion during mixing, or temperature-dependent densities.
Petrol-station volume percentages must be converted to mass shares before
being supplied as ``share``; see :ref:`fuel-blend-density`.

For example, ``biogenic share=1.5`` is invalid: the fraction must be at most one.
Previously this could produce negative fossil tailpipe CO2 and still complete
LCIA. Negative ``CO2`` factors are now rejected as well; zero remains valid,
including for hydrogen.

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
electric bicycles, and multi-year fuel blends. Partial fuel overrides are checked
through completed model, inventory and LCIA runs for all four families, including
unchanged defaults for omitted fuel categories, suppliers, fuel mass balance and
fossil/non-fossil tailpipe CO2. Static exports use one value sample; multi-sample
inventories are tested through LCIA. Fuel-property regressions cover scalar and
year-specific overrides, reordered years, both components, and preserved fuel
supplies and tailpipe carbon through Brightway export.
Independent component-volume checks also cover reported fuel litres; they do
not reuse the model's blend-density calculation as their reference.

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
