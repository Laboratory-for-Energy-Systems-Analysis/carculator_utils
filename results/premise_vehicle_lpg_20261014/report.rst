LPG vehicle fallback and coverage
=================================

The medium LPG car and four LPG trucks now explicitly record their actual
fuel supplier, approved CNG proxy and scenario-coverage limits. The previous
generic truck comment incorrectly implied regional scenario fuel supply for
these services. Their inventory quantities were already consistent with the
approved fossil LPG policy; this correction changes metadata and validation.

Supply and model boundary
-------------------------

In REMIND SSP2-NPi, all five RER services purchase ``market for liquefied
petroleum gas`` from **Europe without Switzerland**, in kilograms, in both
2020 and 2050. They retain the background supplier; they do not purchase an
EUR scenario LPG blend. There is no mapped REMIND LPG vehicle efficiency
trend. Their 2020 operating energy remains unchanged in 2050.

Fuel demand preserves the CNG proxy's modelled energy using the approved
LPG lower heating value of 45.5 MJ/kg. Tailpipe CO2 uses 0.0631 kg/MJ, or
2.87105 kg/kg LPG, with zero biogenic CO2 for this fossil fallback. This is
the existing full-oxidation convention, not a new elemental-carbon balance
including separately reported CO, methane and NMVOC.

CNG manufacture, including its tank, efficiency, maintenance and non-CO2
combustion factors remain documented proxies. The LPG services retain their
existing compressed-gas vehicle-production links. CNG pump-to-tank methane
leakage stays excluded, while combustion methane in the driving compartments
is retained. No new LPG engineering model or tank resizing is introduced.

.. list-table:: Identical operating quantities in 2020 and 2050
   :header-rows: 1

   * - Template
     - Service unit
     - LPG, kg/service
     - Energy, MJ/service
     - Fossil CO2, kg/service
   * - Medium car, EURO-6
     - vehicle-km
     - 0.04750842
     - 2.161633
     - 0.1363990
   * - 3.5 t truck
     - tonne-km
     - 0.10261253
     - 4.668870
     - 0.2946057
   * - 7.5 t truck
     - tonne-km
     - 0.06100262
     - 2.775619
     - 0.1751416
   * - 18 t truck
     - tonne-km
     - 0.06204491
     - 2.823043
     - 0.1781340
   * - 40 t truck
     - tonne-km
     - 0.03001565
     - 1.365712
     - 0.08617645

Conditional support for other models
------------------------------------

The fallback does not disable explicit LPG pathways in other IAMs. TIAM-UCL
already declares LPG vehicle efficiency mappings. Those mappings can still
apply their own recorded efficiency factor. Valid properties of a linked fuel
supplier take priority over the fossil fallback and determine energy and
fossil/non-fossil CO2. Fuel-blend coverage and vehicle-efficiency coverage are
reported separately; one does not establish the other.

Focused car and truck tests exercise TIAM-UCL mappings with an illustrative
0.8 energy multiplier and a mixed-origin supplier. These are regression
fixtures, not predictions of TIAM-UCL fuel composition or full TIAM-UCL builds.
The complete database builds in this step cover REMIND SSP2-NPi only.

Implementation and checks
-------------------------

The generation adapters attach ``vehicle lpg policy`` to the five service
templates. It records the 2020 fuel-energy baseline, functional unit, original
model, proxy boundaries and exact IAM technology. The installer adds these
records and corrects the comments in ``lci-pass_cars.xlsx`` and
``lci-trucks.xlsx``. All other workbook fields, exchange quantities and the
289 activity identities are preserved, verified by parsing both workbooks
before and after installation. Backups and hashes identify the previous files.

After final fuel linking, efficiency adjustment and the existing fuel-module
CO2 calculation, Premise records ``premise vehicle LPG supply`` and a matching
comment. It identifies the actual supplier and geography, delivered energy
basis, carbon origin, applied efficiency factor and mapping availability.
Repeating this metadata update leaves the record and comment unchanged.

Validation re-examines the current exchanges and suppliers. It rejects
accidental CNG substitution, wrong fuel units, missing suppliers, unsupported
energy changes, mismatched fossil/non-fossil CO2 and reintroduced CNG leakage.
It also prevents an LPG market name with a non-LPG product from qualifying
for the fuel module's fossil exception. Forwarding activities are excluded
from direct-fuel accounting. Existing fuel-module carbon logic is reused.

The expanded suite passes **314 tests**, including 23 new LPG cases and the
actual Brightway Excel importer. The cases cover compact exchanges, non-unit
reference production, repeatability, deliberately corrupted final exchanges,
supplier properties, conditional TIAM-UCL mappings and installed metadata.

Full builds use encrypted REMIND SSP2-NPi and ecoinvent 3.12 cutoff, compared
with the immediately preceding Large Car efficiency correction. Both report
zero validation errors. Warning identities and counts are unchanged: 401 in
2020 and 468 in 2050. The five LPG services and their vehicle-production
coefficients are exactly unchanged. The whole-inventory comparison finds no
coefficient differences beyond floating-point precision, using relative
tolerance 1e-12 and absolute tolerance 1e-18; the verification summary records
the small background differences explicitly. Activity identities, IAM files,
transport mappings and fuel-property definitions are preserved. No persistent
user Brightway database was written and no new LCIA comparison is needed for
this metadata-only inventory correction.

Reproducibility and remaining work
----------------------------------

``installation.json`` records the workbook and generator hashes.
``build_2020.json`` and ``build_2050.json`` record the complete build inputs,
source hashes and private inventory hashes. ``lpg_coverage.csv`` contains all
ten year/template checks. ``verification_summary.json`` and
``verification_sources.json`` record the independent inventory comparison,
tests and audit provenance. The private inventory and full validation dumps
are excluded from version control. Premise's implementation, regression tests,
documentation and workbook metadata are committed as ``7083f17``.

Reproduction uses Python 3.12 and the existing isolated source-database copy:

.. code-block:: bash

   /private/tmp/premise-metals-venv/bin/python dev/build_premise_vehicle_battery.py \
     --year 2050 --workspace /private/tmp/premise-vehicle-lpg-20261014 \
     --output results/premise_vehicle_lpg_20261014 \
     --inventory-installation results/premise_vehicle_lpg_20261014/installation.json
   /private/tmp/premise-metals-venv/bin/python dev/audit_premise_vehicle_lpg.py

Repeat the build command for 2020 in a fresh output/workspace before auditing;
the script refuses to overwrite a recorded build. The audit also needs the
private preceding Large Car builds. The metadata installer is for the recorded
pre-update workbook hashes and refuses to repeat an already recorded install.

The next planned issue is general dataset provenance: model/publication
references, source revisions, workbook headers and metadata persistence through
saved Brightway readback. Final physical plausibility and controlled old/new
EF 3.1 comparisons remain later steps. Fuel-tank resizing remains skipped at
the user's request.
