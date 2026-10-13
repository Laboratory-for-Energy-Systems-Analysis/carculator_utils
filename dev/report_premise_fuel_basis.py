"""Write the reviewable report for vehicle remediation step 2."""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/premise_fuel_basis_20261013"


def main():
    summary = json.loads((OUT / "verification_summary.json").read_text())
    rows = list(csv.DictReader((OUT / "market_energy_and_carbon.csv").open()))
    selected = [
        r
        for r in rows
        if r["region"] == "EUR"
        and r["name"]
        in (
            "market for petrol, low-sulfur",
            "market for diesel, low-sulfur",
            "market for natural gas, high pressure",
        )
    ]
    table = []
    for row in selected:
        family = (
            "gas"
            if "natural gas" in row["name"]
            else "petrol" if "petrol" in row["name"] else "diesel"
        )
        table.append(
            f"   * - {row['year']} {family}\n     - {float(row['old_supplier_energy_MJ']):.5f}\n     - {float(row['new_supplier_energy_MJ']):.5f}\n     - {float(row['old_energy_error_percent']):+.3f}%"
        )
    report = (
        """Vehicle fuel energy and carbon properties: step 2
================================================

Completed on 13 October 2026. The refreshed 2020 car/truck templates now use
**46.5 MJ/kg delivered CNG**, as approved by the user and documented by the
source ecoinvent vehicle-grade gas market. Eight car and seven truck service
inventories buy **2.15054% more CNG for unchanged model energy**. Exact dataset
identities, hardware, non-CNG exchanges, model parameters and noise are unchanged.
A parsed-workbook comparison verified every field; only those 15 fuel amounts
and their exchange comments differ. Workbook provenance records the correction
and identifies the frozen raw exports used to isolate it.

The existing compression recipe is preserved. It purchases about 1.360544 m3
of gas and 0.361 kWh per kg. At Premise's 36 MJ/m3 reference, the gas input is
48.97959 MJ/kg. This is an upstream boundary, not delivered heating value.
The 2.47959 MJ/kg difference from 46.5 is explicitly recorded, not assigned
entirely to measured methane losses. The earlier inference of 48.98 MJ/kg as
delivered fuel was superseded by the source documentation and the user's choice.

Corrected market construction
-----------------------------

The documentation promised energy-equivalent fuel markets, but the builder
normalized supplier quantities after conversion. Liquid-fuel callers did not
apply their differing LHVs; the gas caller also summed kg and m3 quantities.
The correction normalizes eligible IAM energy shares first, then purchases
``energy_share * reference_LHV / supplier_LHV``. Other sector market builders
retain their original default behavior through an explicit fuel-only option.

Petrol, diesel, kerosene, gas, hydrogen and scenario LPG markets now use this
energy-aware construction. Natural-gas markets use 36 MJ/m3; kg methane inputs
use 47.5 MJ/kg and the energy conversion 36/47.5, not a density conversion.
Electricity, transport, infrastructure and other ancillary market inputs remain
additional burdens. World markets aggregate reference-energy regional outputs.
Gas markets receive the explicit IAM blend, including marginal mixes where
applicable, while absolute production volumes still determine World weights.

The following EUR examples independently sum the actual mapped fuel purchases
at their packaged supplier LHVs. Quantities are MJ per reference kg for petrol
and diesel, and MJ per reference m3 for gas. These are inventory-energy
comparisons, not LCIA results.

.. list-table:: EUR fuel market energy before and after the correction
   :header-rows: 1

   * - Year / fuel
     - Before (MJ)
     - Corrected (MJ)
     - Previous error
"""
        + "\n".join(table)
        + """

Consumer purchases must not be corrected a second time for physical blend
LHV after this energy normalization. CNG is the separate reference correction:
the vehicle adapter changes 47.5 to the documented 46.5 MJ/kg while preserving
the raw model energy, range and hardware assumptions.

Carbon provenance and limits
----------------------------

Structured ``premise fuel properties`` metadata record units, supplier
quantities, delivered/reference energy, fossil/non-fossil oxidation potential,
unresolved carbon and source evidence. The CNG entries are calculated after
final fuel relinking, including all regional compression/market chains and
the original forwarding datasets. Captured-carbon credits and other carbon
pollutants are unchanged: this is a full-oxidation accounting convention,
not an elemental carbon closure.

Synthetic routes are traced through carbon-bearing intermediates, excluding
hydrogen, electricity and plant infrastructure. DAC carbon is atmospheric and
uses the non-fossil combustion category; that does not mean it is biomass.
Cement and municipal-waste CO2 retain the source inventories' explicit
non-fossil fractions of 6% and 61.3636%. These are inherited source assumptions,
not newly derived regional or future capture compositions. Coal-derived carbon
is fossil even when the supplier name emphasizes its hydrogen route. The
erroneous fossil-origin flags for coal methane and natural-gas-derived kerosene
were corrected. Unknown carbon remains explicit and produces a diagnostic;
none remained in the two tested scenario builds.

Verification
------------

* 288 focused fuel, transformation, vehicle and validation tests passed,
  including 21 new cases in ``tests/test_fuel_energy_basis.py``. Three test
  warnings concern requests dependencies and pythonjsonlogger/tableschema
  deprecations. They are recorded in ``tests.log``.
* The new cases exercise pure and mixed liquid fuels, mixed kg/m3 gas supply,
  blacklist normalization, World markets, consequential energy shares,
  carbon-source tracing, unknown origins, waste-treatment signs, delivered
  versus upstream CNG energy, actual installed workbook purchases and the
  required post-relink metadata ordering.
* A runtime mutation restoring the old quantity normalization caused six
  regression failures; the original source files were not modified by that
  check. See ``normalization_mutation.log`` and its companion script.
* Full REMIND SSP2-NPi, ecoinvent 3.12 cutoff builds for 2020 and 2050 used the
  same Python sources, fuel properties and workbook hashes. Each independently
  passes all 185 fuel-property energy checks, all 13 compression-region checks
  and 147 CNG service-energy checks. Supplier identities and compression
  coefficients are unchanged from the preceding routing correction.
* Both builds have zero validation errors and zero unresolved recorded carbon
  origins. Their 401/398 warning counts and warning identities match the
  preceding build. These existing warnings cover transport emission diagnostics,
  unavailable emission scopes, combustion CO2 plausibility and electricity
  efficiency; unchanged warning identities do not close those separate findings.

Complete background inventories are kept in the private workspace. Existing
user Brightway databases were not overwritten. ``workbook_installation.json``
records hashes and rollback copies; ``build_2020.json`` and ``build_2050.json``
record dependencies and exact inputs. The executed build-script snapshot retains
the bytes used for those runs; the development copy subsequently received only
formatting changes. Raw model data were reused because this step changes only
the adapter and Premise fuel accounting, not the vehicle models.

Remaining work
--------------

Step 3 applies these supplier properties to vehicle fossil/non-fossil tailpipe
CO2 after final regional linking and efficiency scaling, with idempotent
bookkeeping. That consumer correction is not certified by this step. The
remaining hydrogen, hybrid-hardware, future sizing, metadata and plausibility
items stay open. Recompute the controlled EF 3.1 comparisons after these
numerical corrections, using the same corrected Premise code for old and new
vehicle inventories. No new EF 3.1 scores are claimed here.

Artifacts
---------

* ``market_energy_and_carbon.csv``: actual supplier energy checks and carbon
  properties; old World rows express purchases at nominal regional output
  properties, while the EUR comparison above uses physical mapped fuel inputs.
* ``cng_compression_boundaries.csv``: unchanged coefficients and separate
  upstream/delivered energy per region.
* ``cng_vehicle_energy.csv``: preserved service-energy comparisons.
* ``carbon_origin_provenance.csv``: source-by-source carbon evidence.
* ``warning_counts.csv`` and ``verification_summary.json``: validation review.
"""
    )
    lines = report.splitlines()
    for i, line in enumerate(lines):
        if i and line and len(set(line)) == 1 and line[0] in "=-~":
            lines[i] = line[0] * len(lines[i - 1])
    (OUT / "report.rst").write_text("\n".join(lines) + "\n")
    plan = ROOT / "results/premise_vehicle_2050_audit_20261013/remediation_plan.rst"
    text = plan.read_text().replace(
        "nine new regression cases, 45 passing focused tests, and full 2020/2050 checks\nof all 13 regional chains. The next implementation tasks are blend properties\nand the final regional CO2 calculation. Steps 2--12 remain open.",
        "nine new regression cases, 45 passing focused tests, and full 2020/2050 checks\nof all 13 regional chains.\n\nStep 2, explicit fuel energy/carbon properties, was completed on the same day.\nThe `fuel-accounting report <../premise_fuel_basis_20261013/report.html>`_ records\n288 passing tests, the approved 46.5 MJ/kg delivered-CNG correction, corrected\nenergy-equivalent fuel markets and full 2020/2050 builds with zero validation\nerrors. Each build passes 185 property checks and 147 CNG service-energy checks.\nThe source compression recipe is preserved; its upstream/delivered energy\nboundary difference remains explicit. The next task is final regional tailpipe\nCO2 accounting. Steps 3--12 remain open.",
    )
    assert "Step 2, explicit fuel" in text
    plan.write_text(text)


if __name__ == "__main__":
    main()
