"""Write the step-3 report from the completed final-link carbon audit."""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/premise_vehicle_carbon_20261013"


def main():
    summary = json.loads((OUT / "verification_summary.json").read_text())
    with (OUT / "vehicle_carbon_comparison.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    checks = []
    for year, record in summary.items():
        checks.append(
            f"   * - {year}\n"
            f"     - {record['checked_vehicles']}\n"
            f"     - {record['previous_mismatches']}\n"
            f"     - {record['remaining_mismatches']}\n"
            f"     - {record['validation_errors']} / {record['validation_warnings']}"
        )
    examples = []
    for row in rows:
        if row["year"] != "2050" or row["region"] not in ("EUR", "USA", "MEA"):
            continue
        if row["vehicle"] == "transport, freight, lorry, diesel, 40 metric ton":
            label = "40 t diesel truck"
        elif row["vehicle"] == (
            "transport, passenger car, compressed gas, Medium, EURO-6"
        ):
            label = "Medium CNG car"
        else:
            continue
        examples.append(
            f"   * - {label}, {row['region']}\n"
            f"     - {100 * float(row['old_non_fossil_share']):.5f}%\n"
            f"     - {100 * float(row['new_non_fossil_share']):.5f}%\n"
            f"     - {float(row['total_CO2_change_percent']):+.5f}%"
        )
    report = """Final linked vehicle fuel-carbon accounting: step 3
===================================================

Completed on 13 October 2026. The existing Premise fuel module already
reclassified CO2. This correction keeps that responsibility in the fuel module
and applies it at the correct points in the transformation sequence. Each
completed 2020/2050 build now passes **495 direct-fuel car/truck carbon checks**
with no remaining mismatch. The focused suite passes **342 tests**.

What was wrong
---------------

The liquid/gas transformations ran before vehicle regionalization. Regional
clones therefore inherited the template's CO2 split even after purchasing a
different region's fuel. The former calculation also used IAM energy shares
and reference carbon intensities, which do not fully describe the actual
supplier's carbon amounts. Finally, efficiency scaling changed exchange
amounts without scaling the recorded CO2 transfer amounts. A later
reclassification could reuse those stale quantities.

The preceding step supplied explicit energy and carbon properties for the
final fuel suppliers. This step uses those properties; it does not change
their recipes, the approved 46.5 MJ/kg CNG boundary or vehicle fuel purchases.

Implementation and accounting boundary
---------------------------------------

* ``premise/fuels/carbon.py`` owns the common vehicle calculation and reuses
  ``reclassify_fuel_co2``. The older liquid/gas calls still relink vehicles,
  but defer their exhaust calculation to this common routine.
* Fuel transformation calls the helper after final fuel linking and CNG
  property annotation. Transport calls it after regionalization, efficiency
  changes and final transport linking. Each fraction equals the sum of actual
  fuel purchases times the linked supplier's corresponding CO2 factor.
* The vehicle positive exhaust pool uses the agreed full-oxidation convention.
  Existing vehicle biogenic exhaust is replaced along with fossil exhaust,
  rather than retained as an extra source unrelated to the final fuel blend.
  Source air compartments are retained, with the existing documented fallback
  where an exact counterpart flow is unavailable.
* ``rescale_exchange`` scales stored transfer amounts with the exchange.
  Reclassification's internal amount setter opts out, since that operation
  must not rescale other fuel transfers. Failed target resolution is atomic
  for the vehicle update; repeat execution leaves corrected data unchanged.
* ``premise vehicle fuel CO2`` metadata record actual providers, units,
  quantities, oxidation factors, reference production and calculated amounts.
  Unknown carbon origins remain diagnostic. The approved fossil LPG exception
  uses 45.5 MJ/kg and 0.0631 kg CO2/MJ and records the actual supplier geography.
* Car/truck validation independently recomputes both fractions from current
  links. A correct total cannot hide an incorrect fossil/non-fossil split.

Industrial/CCS consumers retain the existing residual-emissions treatment.
Their capture inputs and negative credits are not replaced by the vehicle
full-oxidation calculation. CO, CH4, NMVOC and other pollutants are unchanged;
these checks do **not** establish elemental carbon closure. Atmospheric carbon
from DAC is represented as non-fossil, without implying biomass origin.
Capture-origin factors retain the assumptions documented in step 2.

Full scenario checks
--------------------

Both builds use REMIND SSP2-NPi and ecoinvent 3.12 cutoff, with the same current
Premise source, IAM files and vehicle workbooks. Each year is compared with its
saved step-2 build. There are 42,564 activities in 2020 and 42,574 in 2050.
The 495 checks per year comprise 273 passenger-car and 222 truck services
across 17 locations, including all 13 REMIND regions and retained original
geographies. This includes legacy background road services as well as refreshed
templates. It does not restore historical classes to the refreshed catalogue.
Forwarders and vehicles without direct supported combustion fuel are excluded
from the direct-fuel count.

.. list-table:: Final supplier-derived CO2 checks
   :header-rows: 1

   * - Year
     - Checked services
     - Prior mismatches
     - Remaining mismatches
     - Validation errors / warnings
{checks}

Mismatch counts use relative tolerance 1e-8 and absolute tolerance 1e-12 kg
for each CO2 fraction. Some differences are small; a mismatch count is not a
count of material LCIA changes. Warning identities and multiplicities match
the preceding builds exactly. These inherited warnings remain recorded and
are not claimed to be resolved by this correction.

The independent audit sums final quantities and provider factors, checks both
emission fractions and the transfer ledger, and verifies exact repeatability
of the dedicated CO2 updater on all 495 services in each completed inventory.
All activity identities are retained. Across the entire database, **the only
numerical exchange changes are car/truck CO2**. Fuel purchases, other pollutants,
manufacture and hardware are unchanged. The comparison tolerance outside CO2
is relative 1e-11 and absolute 1e-18. The repeatability claim covers this carbon
updater, not every sector's complete transformation or fleet-market creation.

Classification changes versus total changes
--------------------------------------------

The following 2050 examples separate changes in carbon origin from changes
in the total positive exhaust CO2 pool. Values are direct inventory emissions,
not EF 3.1 scores.

.. list-table:: Non-fossil fraction of direct CO2
   :header-rows: 1

   * - Vehicle and region
     - Before
     - Corrected
     - Total CO2 change
{examples}

For the MEA 40 t diesel truck, fossil CO2 changes from 0.0308948 to
0.0710593 kg/tkm, while non-fossil CO2 falls from 0.0401648 to
0.0000002540 kg/tkm. Its total and fuel input are unchanged. The previous
56.52% share came from the EUR template, whereas the actual MEA supplier is
almost entirely fossil. The USA CNG example similarly removes an inherited
European fraction; it does not increase the total carbon emitted.

Total positive CO2 changes range from -11.7005% to +5.03285% in 2020 and
-11.7134% to +5.06630% in 2050 across the full checked catalogue. Changes in
total are not described as mere reclassification. They reconcile original
exhaust amounts with the explicit final-fuel oxidation convention.

The largest decrease is a legacy Brazilian 16--32 t EURO 5 diesel service.
In 2020 it retained 0.009643284 kg/tkm of original biogenic exhaust in addition
to a new 0.009619499 kg/tkm tracked fuel transfer. Its recorded non-fossil
exhaust was consequently 0.019262783 kg/tkm, whereas its actual fuel purchase
implies 0.009638432 kg/tkm. The updated vehicle calculation replaces the whole
exhaust pool, eliminating this inherited extra amount. Total CO2 falls from
0.08873236 to 0.07835023 kg/tkm. Smaller changes in refreshed EUR templates
reflect fuel-specific oxidation factors rather than an assumed common factor
for every blend component. Per-service figures are in the comparison CSV.

Regression evidence
--------------------

The expanded focused suite passes **342 tests**, with three existing dependency
or deprecation warnings. Eighteen new cases cover regional suppliers, pure
fossil and pure non-fossil endpoints, compact exchanges, efficiency scaling,
mixed-fuel PHEVs, reference production, fossil LPG fallback, unresolved origin,
forwarders, atomic failure, uncertainty, validation and the transport entry
point for cars/trucks in 2020/2050. Existing industry/CCS tests remain green.

Two temporary runtime mutations demonstrate that the regressions are detected:
disabling the post-transport refresh fails all four regional integration cases;
disabling transfer scaling fails both scaling cases. Neither mutation was
written to the source tree. Logs are retained with this report.

Reproduction and retained artifacts
------------------------------------

The sibling Premise checkout contains the production fix and tests. From this
``carculator_utils`` checkout, with the documented Python 3.12 environment::

    python dev/build_premise_vehicle_carbon.py --year 2020
    python dev/build_premise_vehicle_carbon.py --year 2050
    python dev/audit_premise_vehicle_carbon.py
    python dev/report_premise_vehicle_carbon.py

The build script deliberately refuses to overwrite a completed build record.
It requires the private ecoinvent source project and authorized IAM access;
complete background inventories remain outside the repository. Persistent user
Brightway databases were not written. The aggregate artifacts are:

* ``build_2020.json`` / ``build_2050.json``: source, workbook, IAM and private
  inventory hashes, versions, execution time and validation counts.
* ``vehicle_carbon_comparison.csv``: all 990 before/after service checks.
* ``changed_CO2_exchanges.csv``: changed direct CO2 coefficients by compartment.
* ``transfer_bookkeeping.csv``: stored transfers and emitted non-fossil CO2.
* ``verification_summary.json`` and ``validation_*.json``: independent checks
  and complete validation reports.
* ``tests.log`` and ``mutation_*.log``: focused and regression-detection evidence.

This completes step 3 of the `remediation plan
<../premise_vehicle_2050_audit_20261013/remediation_plan.html>`_. Step 4 is the
coupling of hydrogen compression electricity to hydrogen demand. Hybrid
hardware, constant-range future sizing, complete provenance and the final
paired EF 3.1 comparison remain open. Earlier saved LCIA comparisons remain
historical and will be rebuilt with the same corrected code on both sides.
"""
    (OUT / "report.rst").write_text(
        report.format(checks="\n".join(checks), examples="\n".join(examples))
    )


if __name__ == "__main__":
    main()
