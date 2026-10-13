Car and truck inventory remediation plan
========================================

Prepared 13 October 2026 from the `2020/2050 audit <report.html>`_ and its
`verification summary <verification_summary.json>`_. This is an implementation
plan; the corrections below have not been applied by writing this document.
Work proceeds one issue at a time, with a reviewable change and focused checks
before moving to the next. A successful database import is not scientific
sign-off.

Scope and decisions
-------------------

The immediate scope is the installed passenger-car and Regional-delivery truck
updates, their shared carculator machinery, and Premise transformations.
Buses and two-wheelers still use their original workbooks. Shared-code changes
must be checked against those models, but refreshing their inventories is a
subsequent exercise.

Keep the accepted 2020 model baseline, Swiss climate, 2020 emission classes,
default usage assumptions, the selected car catalogue and all 52 truck service
identities. Trucks use Regional delivery and a 400 km design range. Preserve
the approved energy-preserving gasoline/LPG proxies, Premise battery-capacity
markets, and the companion noise audit. Retain the car cold-start assumption
of 1.8 starts/day and the agreed HBEFA provenance wording. Preserve existing
service/production names, products, locations and units; do not reinstate the
historical car classes removed under the agreed scope.

Two additional decisions were confirmed for this plan:

* **Future vehicles retain their baseline range through consistent resizing.**
  This means 400 km for the selected trucks and the relevant baseline range
  for each car. Batteries, mass and affected inventories must change together.
* **LPG retains a documented fossil supply where the IAM has no LPG pathway.**
  Do not substitute a petrol or CNG scenario blend implicitly.

Premise continues to own scenario energy supply and efficiency projections.
The future resizing implementation must assign each improvement once and
distinguish physical battery assumptions from the upstream battery-market mix.
Any new unsupported assumption about hybrid architecture, battery technology
or fuel carbon origin must be resolved from evidence or brought back for review.

0. Freeze the comparison inputs
-------------------------------

Retain three identifiable states: the original inventories, the current
pre-remediation candidates, and each corrected candidate. Record hashes of
workbooks, sidecars, source revisions, IAM input and model parameters. Preserve
the existing Brightway databases and isolate experimental builds.

Acceptance: every later score can be tied to an exact inventory and Premise
implementation. Old and corrected inventories can be built with the same
Premise code. Store aggregate diagnostics and provenance in the repository;
keep the complete proprietary background inventory in the private workspace.

1. Repair the actual regional CNG supply chain
----------------------------------------------

**Confirmed defect.** The regional vehicle-grade market currently points to
RoW compression, which purchases World gas and electricity.

In Premise's gas transformation, regionalize the compression provider and
relink its gas and electricity inputs. Preserve pressure, compression demand,
losses and the documented mass/volume conversion. Keep gas-production and
vehicle leakage boundaries explicit. Inspect the provider chain beyond the
market name and handle mixed kg/m3 suppliers on a consistent basis.

Acceptance: cars and trucks in EUR, USA, IND, CHA and World reach the intended
regional gas and electricity chains in both 2020 and 2050. No unintended
RoW/World fallback remains where a regional supplier exists. Repeated
transformation does not duplicate compression activities or consumption.

Main code: ``premise/premise/fuels/biogas.py`` and its transformation helpers.

2. Make blend energy and carbon properties explicit
---------------------------------------------------

**Accounting gap requiring verification.** Current adapters preserve energy
using reference-fuel properties; the delivered market can contain fuels with
different heating values and carbon contents.

Trace the final supplier mix and derive delivered heating value, carbon
content and carbon origin on explicit mass, volume or energy bases. Adjust
purchased blend quantity to preserve the intended operating energy. Keep
compression electricity separate from fuel chemical energy. Document how
biogenic carbon, direct-air-capture carbon and recycled fossil carbon are
represented; an electrofuel label alone does not determine carbon origin.

Acceptance: independently calculated examples for pure fossil fuel, pure
biofuel and mixed petrol/diesel/gas markets preserve energy and yield the
expected carbon amounts. Unknown properties remain visible diagnostics.
Fuel-mass shares are not used directly as carbon shares. Document the
full-oxidation CO2 convention and any separate CO/CH4/NMVOC treatment; do not
claim elemental carbon closure without checking those flows.

Main code: Premise fuel-market properties, carbon helpers, and the two vehicle
generation adapters. This supplies the accounting contract for step 3.

3. Recalculate fossil/non-fossil CO2 after final vehicle linking
----------------------------------------------------------------

**Confirmed defect.** Regional clones inherit the EUR template's split even
when their actual fuel blend differs. The audit found 348 resolved mismatches;
unresolved gas/synthetic routes make this a lower bound.

Calculate tailpipe CO2 from the final linked supplier and final fuel quantity,
after regionalization and efficiency adjustment. Use the carbon properties
from step 2. Update the reclassification bookkeeping so scaling and repeated
updates cannot double-transfer CO2 or reuse a stale transfer amount.

Acceptance: all mapped vehicle regions pass in 2020 and 2050, including
non-European cases, pure fossil/pure non-fossil boundaries and mixed markets.
Transfers preserve total CO2 when only its classification changes; changes in
total CO2 caused by changed blend properties are explained separately. Both
CO2 flows remain nonnegative, and rerunning the transformation is idempotent.
Check PHEVs and forwarding activities as well as single-fuel vehicles.

Main code: ``premise/premise/fuels/carbon.py``, liquid/gas fuel transformations,
``premise/premise/transport.py`` and transformation sequencing.

4. Couple hydrogen compression electricity to hydrogen demand
-------------------------------------------------------------

**Confirmed defect.** The 40 t EUR FCEV's hydrogen demand falls 20% by 2050,
but its compression electricity remains unchanged.

Identify compression electricity explicitly and scale it with delivered
hydrogen, retaining its specific kWh/kg unless a separate, documented
compression-efficiency projection exists. Check whether upstream hydrogen
supply already includes the same preparation stage.

Acceptance: the intended kWh/kg ratio holds before and after transformation
for cars and trucks, with factors of one and below one. Compression is counted
once. Unrelated electricity exchanges are unaffected.

Main code: ``premise/premise/transport.py`` and hydrogen exchange metadata.

5. Correct PHEV physical capacity aggregation
---------------------------------------------

**Completed 13 October 2026.** The former 16.0--26.5% capacity deficit in all
16 car PHEV variants is corrected. The following records the original scope;
the execution record and PHEV report below describe the implemented checks.

Correct the shared PHEV aggregation contract: physical hardware belongs to
the vehicle, while mode-specific operation is weighted by usage. Trace the
truck override and other subclasses before changing inherited behavior.
Make both adapters consume the same coherent physical capacity, avoiding
separate patches that diverge. Reconcile battery manufacture, replacements
and end-of-life with Premise's capacity-market boundary.

Acceptance: nominal capacity agrees with cell mass times cell energy density;
pack mass and cell share agree. Test zero, intermediate and full electric
driving shares without deleting hardware from an unchanged architecture.
Operating energy still follows usage. The Medium car's current physical
30.576 kWh is a diagnostic reference, not a hard-coded replacement value.

Main code: ``carculator_utils/model.py:create_PHEV``, subclass overrides and
``dev/regenerate_premise_cars.py`` / ``dev/regenerate_premise_trucks.py``.

6. Derive PHEV replacement counts from actual battery use
---------------------------------------------------------

**Unresolved model question.** Truck pack capacity is already recovered from
physical mass, but replacement counts are still mode-averaged.

Trace lifetime battery throughput, electric driving share, usable capacity,
cycle life and any calendar-life limit. Establish whether usage weighting is
already present before aggregating modes. Correct the source calculation if
necessary and document the fractional-replacement convention.

Acceptance: independent throughput/lifetime examples reproduce the count;
electric driving share is applied once; limiting cases remain finite and
physically interpretable. Purchased lifetime capacity equals the initial pack
plus justified replacements, with disposal counted once. Do not correct the
count by an unexplained multiplication or division by the utility factor.

Main code: shared and truck battery-lifetime calculations and PHEV aggregation.

7. Resolve missing truck HEV traction storage
---------------------------------------------

**Source-model issue to resolve.** Seven native diesel hybrids and two
gasoline-hybrid proxies have zero energy-battery mass/capacity despite a
modelled fuel-economy benefit. The component inventory has no hidden pack.

Establish the intended hybrid architecture from model inputs and supporting
documentation. Size the buffer against electric power, recuperation and usable
energy requirements. Trace the distinction between starter/power batteries
and traction storage. Add the justified hardware consistently to mass,
operational calculations, replacements, manufacture and disposal. Seek a
modelling decision if the evidence cannot establish the architecture.

Acceptance: the hybrid can deliver its modelled electric power and recuperation
within battery constraints, with an explicit energy balance. Recalculate fuel
consumption after correcting mass and storage. A 400 km BEV range battery is
not the sizing rule for an HEV buffer. The nine affected services retain their
identities and documented proxy relationships.

Main code: ``carculator_truck/model.py:set_energy_stored_properties``, shared
power-battery logic, truck inventory assembly and the truck adapter.

8. Implement constant-range future sizing and review efficiency scaling
-----------------------------------------------------------------------

**Approved policy; coupled implementation required.** The audit found all
98 surviving production inventories retaining their 2020 battery quantities.
The EUR 40 t BEV therefore gains implied range from 400 to about 500 km when
electricity use falls 20%. The approved policy instead preserves baseline range.

First establish the meaning and boundary of each IAM efficiency indicator.
Assign efficiency changes once: do not combine a native future carculator
efficiency improvement with the same Premise improvement. Define the target
energy/range constraints, then solve the coupled sizing problem with bounded
convergence. Calibrate consistently if mass feedback affects energy demand.

Propagate changes to nominal/usable capacity, pack mass, curb/driving mass,
payload feasibility, battery lifetime, vehicle manufacture and affected
operation/maintenance exchanges. Preserve each car's own design range and
the truck 400 km target. Distinguish combustion range from electric-only range
for PHEVs. Verify chemistry/density assumptions and compatibility with the
capacity-market representation; bring unsupported new assumptions for review.

Replace or retire the ineffective legacy truck-capacity override. Merely
matching ``lorry production`` to the old override would risk importing an
unrelated battery/range assumption. Ensure regional production suppliers
remain distinct when regional efficiency implies different hardware.

Also classify exchanges by physical driver: fuel-related exhaust, distance
and wear, start/soak events, and time/refrigerant losses. Remove blanket
efficiency scaling where its proportionality is unsupported. Preserve the
previous evaporation/PAH corrections and the agreed cold-start assumptions;
do not clip emissions to EURO limits to conceal a model discrepancy.

Acceptance: 2020 reproduces the corrected baseline; 2030/2050 retain design
range within solver tolerance, close mass/energy balances and respect payload
and power constraints. Year/region metadata report the actual resulting
hardware. Cases with no IAM efficiency signal are explicit. Focused tests show
which emissions scale and why, with no duplicate application of efficiency.

Main code: ``premise/premise/transport.py``, vehicle-model sizing and the
interface carrying baseline specifications into Premise transformations.

9. Implement and document the LPG fallback
------------------------------------------

**Policy approved.** The one LPG car and four LPG truck templates retain fossil
LPG supply where REMIND has no usable LPG pathway.

Make the fallback explicit in mappings, validation and comments. Preserve the
approved energy-preserving proxy conversion and remove CNG-specific leakage.
Use available geographic suppliers only where justified; do not imply a
scenario LPG blend or efficiency projection that the IAM does not provide.

Acceptance: all five services link, use LPG-specific energy/carbon properties
and report fossil combustion CO2 consistently. Metadata identify the actual
supplier geography and absence of a scenario-specific LPG blend. The fallback
remains visible in coverage reports rather than silently passing as full IAM
coverage.

10. Complete provenance and preserve dataset identity
-----------------------------------------------------

**Confirmed defects.** All 289 installed car/truck datasets lack structured
publication/source fields or DOI comments; 34 car service/production datasets
lack the model name. Truck writers also inherit a car database header.

Make the Excel writer accept an explicit database label and preserve supported
metadata fields. Add the original model, shared-library version and source
revision, appropriate publication/DOI, baseline year, climate, driving cycle,
usage assumptions, proxy decisions, regeneration date and noise boundary.
Distinguish model-publication references from sources for individual factors
and legacy components. Retain this approved wording on applicable car datasets:

    the original LCA model, carculator, uses emission factors for cold start,
    evaporative and running emissions from the HBEFA 5.1 emissions handbook.

For transformed datasets, separately record scenario, year, region, actual
fuel supplier, efficiency factor and resized specifications. Clearly label
raw 2020 specifications as baseline. Keep detailed parameters and noise in
the companion audits, with reproducible provenance linking them to the workbook.

Acceptance: Excel -> importer -> Premise -> saved Brightway readback retains
the intended metadata. Retained service/production identities and auxiliary
supplier links are unchanged; workbook database headers are correct. Legacy
components retain truthful original provenance rather than acquiring an
unrelated current-model citation.

11. Repeat physical and emissions plausibility checks
-----------------------------------------------------

Regenerate the candidates from corrected matching source checkouts. Do not
reuse a raw export produced before a model correction. Check the complete car
and truck grids for finite positive active-vehicle quantities, units, functional
units, lifetime allocation, fuel demand, battery energy/mass, payload and range.

Investigate the most demanding cases explicitly: the 3.5 t BEV's current
133.8 kWh / 796 kg pack, large-car batteries, all hybrids and hydrogen trucks.
Separate an internally feasible vehicle from a commercially representative
one. Compare outliers with documented model assumptions and suitable primary
technical evidence; ask before changing an accepted range or payload.

Repeat the EURO-class emissions screen using comparable test boundaries and
units. Retain cold-start versus hot-emission distinctions and describe the
limits of comparing inventory averages with regulatory tests. Check PAH,
evaporative speciation and the approved pollutant-normalization corrections
as regressions, including applicable shared-utils paths.

Acceptance: all material outliers are explained or fixed. A finite number,
an exact supplier link or a passed regulatory screen alone is insufficient.
Preserve companion noise records and exact names for the retained catalogue.

12. Rebuild, compare EF 3.1 and close the findings
--------------------------------------------------

Run focused tests after each correction. Shared-model changes also require
affected sibling tests and small deterministic real model/inventory cases,
including bus/two-wheeler smoke checks where inherited behavior changes.
Run full integration builds after coherent groups of changes and at completion.

The final controlled comparison uses REMIND SSP2-NPi, ecoinvent 3.12 cutoff
and both 2020 and 2050. It includes the complete retained RER catalogues and
EUR regionalized subsets; fuel, carbon and physical checks cover all mapped
regions. Add a 2030 sizing check and a second, fuel-transition-sensitive
pathway check to exercise the new contracts beyond the original two builds.

Build old and corrected inventories with the **same corrected Premise code**
for the inventory comparison. Separately quantify transformation-code effects
with fixed inventory inputs where compatible. Record any required baseline
compatibility adaptation. Where useful, retain intermediate car-only and
truck-only comparisons so their effects can be distinguished.

Calculate the 16 EF 3.1 headline categories without combining them into a
single weighted score. Report absolute and relative differences, manufacturing
and operation contributions, and the largest changes. For trucks, show per-vkm
and per-tkm results with their payloads. Trace RER forwarding suppliers so they
are not mistaken for untouched templates. Independently verify representative
matrix solves and saved-database readback. Each large unexplained change remains
an open finding, not an accepted consequence of updating the model.

Acceptance: zero unresolved validation errors; relevant warnings investigated;
all confirmed defects have focused regression checks; the revised workbooks,
sidecars, build hashes, paired scores and explanations agree. Keep the original
databases and an explicit rollback manifest. Record each finding as fixed,
justified, or awaiting a named modelling decision. Close the car/truck update
only once the remaining scientific questions are resolved.

Execution dependencies
----------------------

Steps 1 -> 2 -> 3 establish supplier and carbon consistency. Step 4 fixes the
independent hydrogen-energy defect. Steps 5 -> 6 -> 7 establish hybrid hardware
and lifetime accounting. These results feed step 8's future sizing. Step 9
applies the approved LPG exception; steps 10 -> 11 -> 12 produce a traceable,
validated release and LCIA comparison. Implementation remains sequential and
reviewable even where tasks are technically independent.

Step 1, the regional CNG provider chain, was completed on 13 October 2026.
The `correction report <../premise_cng_routing_20261013/report.html>`_ records
nine new regression cases, 45 passing focused tests, and full 2020/2050 checks
of all 13 regional chains.

Step 2, explicit fuel energy/carbon properties, was completed on the same day.
The `fuel-accounting report <../premise_fuel_basis_20261013/report.html>`_ records
288 passing tests, the approved 46.5 MJ/kg delivered-CNG correction, corrected
energy-equivalent fuel markets and full 2020/2050 builds with zero validation
errors. Each build passes 185 property checks and 147 CNG service-energy checks.
The source compression recipe is preserved; its upstream/delivered energy
boundary difference remains explicit.

Step 3, final regional tailpipe CO2 accounting, was completed on the same day.
The `vehicle-carbon report <../premise_vehicle_carbon_20261013/report.html>`_
records 342 passing tests and zero remaining mismatches across 495 direct-fuel
car/truck services in each full 2020/2050 build. The existing fuel reclassifier
is reused after final linking and efficiency scaling; transfer amounts now
scale consistently. Repeating this dedicated carbon update on each completed
inventory makes no changes. All numerical differences from step 2 are vehicle
CO2 exchanges; validation has zero errors and unchanged warning identities.
Step 4, hydrogen compression electricity, was subsequently completed.
The `hydrogen report <../premise_vehicle_hydrogen_20261013/report.html>`_
records the source boundary investigation and approved 30-to-700-bar
adaptation (2.450619 kWh/kg H2). Explicit metadata couple compression to final
hydrogen use and preserve other electricity. Both builds pass all 147 marked
hydrogen-vehicle checks; the expanded suite passes 365 tests. Numerical changes
are confined to vehicle compression electricity, with zero validation errors
and unchanged warning identities.

Step 5, PHEV physical-capacity aggregation, is now corrected. The shared model
retains one full pack at every driving share and calculates electric range from
usable capacity. Both car and truck cost models price the full installed pack;
capacity-market purchases increase for 16 car templates. The truck adapter
now consumes the corrected model field directly. See the
`PHEV report <../premise_vehicle_phev_20261013/report.html>`_.
The next task is the independent replacement-count review. Steps 6--12 remain open.
