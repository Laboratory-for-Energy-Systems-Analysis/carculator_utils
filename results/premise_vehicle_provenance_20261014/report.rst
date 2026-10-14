Vehicle provenance and Brightway readback
=========================================

All 289 refreshed car/truck datasets now carry the original model, software
version, model publication and structured generation provenance. The 26 retained
legacy components recover their own original sources and remain explicitly
separate from the new model generation. This step changes metadata and database
headers; inventory identities and exchange quantities are preserved.

References and boundaries
--------------------------

The car model is referenced to Sacchi, Bauer, Cox and Mutel (2022),
`When, where and how can the electrification of passenger cars reduce greenhouse
gas emissions? <https://doi.org/10.1016/j.rser.2022.112475>`_, Renewable and
Sustainable Energy Reviews 162, 112475. The truck model is referenced to Sacchi,
Bauer and Cox (2021),
`Does Size Matter? <https://doi.org/10.1021/acs.est.0c07773>`_, Environmental
Science & Technology 55(8), 5224--5235. Titles and DOIs were checked against
the publishers and PSI publication records. These identify the model methods;
they do not imply that the recent corrections appeared in the original papers.

Software provenance identifies carculator 1.9.7, carculator_truck 0.5.2 and
carculator_utils 1.3.7, together with recorded repository revisions and actual
generation-source hashes. The hashes matter because a recorded HEAD alone
does not identify uncommitted scientific changes. The verified generation
artifacts are from 13 October 2026; this metadata update is dated 14 October.
No new physical vehicle calculation is claimed for this metadata patch.

The raw exports retained component references that the Excel writer dropped.
These references are restored for fuel cells, tanks, carbon fibre, Nafion,
truck components and charging equipment. The vehicle-model publication is
recorded separately. Where the exporter supplies no component-specific
reference, the metadata explicitly says so; no literature source is invented.
The retained legacy recipes recover their original source, description and
special remarks from the original truck-workbook audit, identified by hash.
They retain their ecoinvent 3.7 import basis and do not acquire a current-model
generation version or publication claim.

Metadata implementation
-------------------------

The adapter writer now accepts an explicit database label and preserves
source fields, structured metadata and exchange uncertainty fields. The
installed truck header is ``lci-trucks`` and the compatibility header is
``lci-truck-legacy-components``; the previous writer labelled both as
``lci-pass_cars``. These header corrections preserve activity names, reference
products, locations, units and auxiliary supplier links.

``vehicle inventory provenance`` records the generation model, source revisions,
source-file hashes, baseline identity and year, Swiss climate, driving cycle,
usage/specification parameters, proxy decisions and raw-artifact hashes. Cars
use WLTC and trucks Regional delivery. Vehicle-production recipes shared by a
native CNG service and an LPG proxy retain their native production identity;
the LPG conversion belongs to the service. The approved HBEFA wording is
retained on applicable combustion-car service and production datasets.

Original-model comment specifications are clearly labelled as 2020 baseline
values. The new ``premise vehicle provenance`` record separately identifies
the IAM, pathway, scenario year, actual region, reference production, final
operating fuel/electricity suppliers and amounts, efficiency adjustments and
scenario battery specifications. It is refreshed after final vehicle linking
and existing fuel-carbon accounting. Forwarding services do not claim direct
fuel inputs or a physical vehicle design. Baseline provenance is preserved
on regional clones, including future production activities.

The two ``*.provenance.json`` sidecars now identify the installed workbook
hashes and preserve earlier provenance records. Four shipped companion CSVs
retain the vehicle parameter tables and excluded noise audit, with matching
hashes. Scoped Git attributes preserve their exact bytes across checkouts.
The tracked CSV difference restores their generated CRLF line endings so that
Git checkout preserves those hashes; every parsed value is unchanged.
The full raw export is identified by hash and stays in the private audit;
no complete ecoinvent inventory is distributed in the report.

Verification
-------------

The focused Premise suite passes **328 tests**. Four adapter tests also pass
in both the current Premise environment and the supported carculator export
environment. Tests cover source preservation, structured Excel metadata,
explicit and filename-derived headers, uncertainty fields, immutable baseline
records, repeatable scenario updates, forwarding activities, shared CNG/LPG
production and truthful legacy/component attribution. Installed-workbook tests
check every dataset, its provenance sidecar and companion hashes.

Both car and truck adapters were rerun against the verified raw inventories
in a fresh private output directory. All three resulting workbooks reproduce
the installed activity identities and exchange coefficients exactly. The
metadata-only installer independently checks every existing exchange field
before replacing a workbook and keeps private backups.

Full builds and actual Brightway writes use encrypted REMIND SSP2-NPi,
ecoinvent 3.12 cutoff and a separate copy of the Brightway project. Readback
compares original-model metadata, source fields and scenario specifications
against the pre-export inventories and checks operating supplier links.

.. list-table:: Full-build and saved-database checks
   :header-rows: 1

   * - Check
     - 2020
     - 2050
   * - Activities in complete inventory
     - 42,564
     - 42,795
   * - Activities with verified saved provenance
     - 965
     - 1,186
   * - Saved operating-energy supplier checks
     - 968
     - 968
   * - Validation errors
     - 0
     - 0
   * - Validation warnings
     - 401, unchanged
     - 468, unchanged

The complete inventory comparison against the preceding LPG step uses relative
tolerance 1e-12 and absolute tolerance 1e-18 to distinguish machine rounding
from inventory changes. Activity identities, IAM files, transport mappings,
fuel-property definitions and validation warning identities are unchanged.
The verification summary records the comparison and any floating-point
differences explicitly.

EF 3.1 climate-change smoke calculations complete for the saved EUR Medium
BEV car and 40 t BEV truck in each year. Their scores are respectively
0.205518 kg CO2-eq/vehicle-km and 0.094124 kg CO2-eq/tonne-km in 2020;
0.069585 and 0.032825 in 2050. These checks establish that the written
databases remain calculable. They are not the final old/new vehicle comparison
or a new scientific validation of the vehicle assumptions.

Reproduction and next step
---------------------------

``installation.json`` records workbook, companion and adapter hashes.
``workbook_sources.csv`` lists each dataset's role and restored source.
``build_*.json`` records full build inputs; ``saved_*.json`` records Brightway
readback and smoke calculations. ``verification_summary.json`` and
``verification_sources.json`` identify the independent checks and test results.
The Premise implementation, workbooks and regression tests are committed as
``3a7e2d1``.

.. code-block:: bash

   /private/tmp/premise-metals-venv/bin/python dev/build_premise_vehicle_battery.py \
     --year 2050 --workspace /private/tmp/premise-vehicle-provenance-20261014 \
     --output results/premise_vehicle_provenance_20261014 \
     --inventory-installation results/premise_vehicle_lpg_20261014/installation.json \
     --inventory-installation results/premise_vehicle_provenance_20261014/installation.json \
     --write-brightway
   /private/tmp/premise-metals-venv/bin/python dev/audit_premise_vehicle_provenance.py

Repeat for 2020 using a fresh isolated workspace/output; completed build records
and existing databases are not overwritten. The audit needs the private
preceding LPG inventories and the adapter-check outputs. The 2020 LCIA audit
initially passed an Activity object to ``redo_lcia``; this Brightway version
requires the integer node ID. The audit was corrected and readback repeated
successfully without rebuilding or overwriting the saved database.

The next planned step is the complete physical/emissions plausibility review,
followed by the controlled old/new EF 3.1 comparison. The broader PHEV cycling
boundary remains recorded as an open modelling question. Fuel-tank resizing
remains skipped at the user's request.
