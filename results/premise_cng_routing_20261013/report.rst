Regional CNG routing: correction and verification
=================================================

Step 1 of the vehicle remediation plan is complete. Premise now regionalizes
vehicle-grade compression before its market. Regional CNG consumers reach
regional high-pressure gas and compression electricity, with the source
inventory's physical quantities preserved.

What changed
------------

Previously the path was vehicle -> regional CNG market -> RoW compression ->
World gas/electricity. The corrected path is vehicle -> regional CNG market ->
regional compression -> regional gas/electricity. This applies to all consumers
of these suppliers, including cars and trucks.

The original geographic production and market activities now forward exactly
one kilogram of the same product to their IAM replacement. In the previous
REMIND builds, the original global market forwarded only 12/13 kg: the generic
helper divided across thirteen regions, then omitted World from its recipient
list. The CNG correction uses the World replacement directly where appropriate.
It does not alter the generic helper or unrelated sectors.

Compression retains 1.360544218 m3 of high-pressure gas and 0.361 kWh of
medium-voltage electricity per kg of vehicle-grade gas. Infrastructure demand
and direct methane/NMVOC/other hydrocarbon losses are retained. These are
preserved source coefficients, not a new independent validation of gas density,
heating value or carbon content. Those accounting questions are the next task.

Unit tests
----------

Nine new cases in ``premise/tests/test_vehicle_grade_gas.py`` cover:

* The complete market -> compression -> gas/electricity chain in six test
  regions, including World, for both 2020 and 2050.
* Preservation of gas-volume conversion, compression electricity,
  infrastructure and methane losses.
* One-kg forwarding from CH, RoW and GLO without duplicate compression.
* Idempotence of repeated regionalization, including the provider index.
* The public gas-update entry point, so bypassing the helper is detected.
* Graceful handling of inventories without vehicle-grade gas activities.

The nine cases pass; the combined fuel, transformation and passenger-car
integration selection passes **45 tests** under Python 3.12. Deliberately
restoring the former market-only behavior in a separate process makes six
cases fail. Omitting only the forwarding correction makes two cases fail.
These checks mutate methods in memory and leave the corrected source intact.

Full scenario checks
--------------------

Fresh full builds use REMIND SSP2-NPi, ecoinvent 3.12 cutoff, identical encrypted
IAM input and the unchanged installed vehicle workbooks. All 13 IAM-region
chains pass for both years, covering 78 car and 65 truck CNG links per year.
Vehicle operating quantities and direct emissions are unchanged by this fix.

.. list-table:: Full-build verification
   :header-rows: 1

   * - Year
     - Activities
     - New regional compression activities
     - Validation errors
     - Validation warnings
   * - 2020
     - 42,564
     - 13
     - 0
     - 401
   * - 2050
     - 42,574
     - 13
     - 0
     - 398

The 16 existing CNG market/production activities change in each year. No
activities are removed. Comparing the 2020 in-memory build against the earlier
saved/exported baseline also exposes four near-zero CO2 differences below
8e-15 kg and one biosphere-location metadata difference with unchanged heat
quantity. These are recorded separately rather than attributed to CNG routing.
The 2050 comparison has no changes outside the CNG activities.

The validation findings are unchanged in substance. One 2020 background coal
warning differs in its last displayed numerical digit; 2050 findings match.
Passing these checks does not resolve the later blend-carbon, hybrid-storage
or future-sizing findings.

The only changed Premise runtime source relative to the previous 2050 audit
is ``premise/fuels/biogas.py``. Unit tests and builds use Python 3.12; build
records also identify dependency versions, which differ from the earlier
Python 3.11 audit environment. Whole-inventory comparisons above check the
resulting scope explicitly. Full inventories remain in a private cloned
Brightway workspace and private pickle files. Existing saved comparison
databases have not been overwritten.

Evidence and reproduction
-------------------------

* `Regional supply-chain quantities <regional_chains.csv>`_
* `Vehicle supplier links <vehicle_links.csv>`_
* `Verification and comparison qualifications <verification.json>`_
* `Changed existing activities <changed_activities.csv>`_
* `Focused test log <tests.log>`_
* `Old-routing regression check <legacy_regression.json>`_
* `Forwarding regression check <forwarding_regression.json>`_
* `Validation comparison <validation_comparison.json>`_
* `2020 build provenance <build_2020.json>`_
* `2050 build provenance <build_2050.json>`_

The reproducible build and audit entry points are
``dev/build_premise_cng_routing.py`` and ``dev/audit_premise_cng_routing.py``
in carculator_utils. The build script requires an isolated Brightway directory
and refuses an existing completed build record. It reads the IAM key without
including it in the provenance output. Run the focused tests from Premise with:

.. code-block:: console

   python -m pytest tests/test_vehicle_grade_gas.py tests/test_fuels.py \
       tests/test_passenger_car_refresh.py tests/test_transformation.py -q

Next: establish the fuel markets' actual energy and carbon basis, then correct
the tailpipe split after final regional vehicle linking. The EF 3.1 comparison
will be rebuilt after the remaining numerical corrections.
