Hybrid hot-exhaust deterioration correction
===========================================

14 October 2026. This update follows the FCEV accounting correction and
isolates hybrid pollutant ageing. It is not the final old-versus-new vehicle
EF 3.1 comparison.

Finding and correction
----------------------

Hot-exhaust coefficients already map HEVs and PHEV combustion modes to their
petrol or diesel ICEV engine. The mileage-deterioration lookup instead selected
literal hybrid labels. Truck/bus tables have no hybrid rows; the car table
contains unity placeholders but no corresponding Euro-6 hybrid endpoint data.
Both paths consequently gave hybrids unity rather than the engine factor.

The lookup now uses the same engine aliases as hot-factor selection, then
restores the original powertrain labels before multiplication. Repeated
aliases do not collapse HEV/PHEV coordinates. Missing source factors retain
unity, and the absence of a two-wheeler table still means no correction.

No numerical coefficients or mileage assumptions change. For endpoint factor
``f``, vehicle lifetime ``L`` and reference mileage ``K``, the existing
lifetime-average multiplier remains ``1 + (max(f, 1) - 1) * L / (2*K)``.
``K`` is 200,000 km for cars and 890,000 km for trucks/buses. The formula
represents linear deterioration from unity, averaged over vehicle lifetime.
It retains linear extrapolation beyond the reference mileage.

This is a combustion-engine ageing proxy for hybrids. It is not a measured
hybrid-specific deterioration curve. The existing lifetime basis is vehicle
kilometres, with no new engine-on-distance or PHEV utility-factor adjustment.
PHEV combustion-mode emissions are weighted once when the final vehicle is
assembled. Cold-start and evaporative factors are added after hot-exhaust
deterioration and do not acquire this multiplier. Dataset comments disclose
these boundaries.

Observed effects
----------------

For the selected 2020 car class (model Euro 6.2), the hot multipliers are:

.. list-table:: Retained factors, newly selected for hybrids
   :header-rows: 1

   * - Engine proxy
     - CO
     - NOx
   * - Petrol car
     - 1.15
     - 1.15
   * - Diesel car
     - 1.20
     - 1.075

Petrol aggregate hydrocarbon diagnostics also acquire a 1.01 multiplier.
This aggregate is not exported as an additional biosphere flow; NMHC species,
PAH and formaldehyde inventories are unchanged. Total car CO/NOx increases are
smaller than the hot multipliers because cold starts are unchanged. For the
Medium petrol HEV, CO rises from 0.60706 to 0.64976 g/km (+7.03%) and NOx
from 0.03542 to 0.03875 g/km (+9.41%).

Truck NOx multipliers range from 1.24449 to 1.63820 with the existing size-
specific lifetimes. The 40 t diesel HEV rises from 1.71022 to 2.80169 g NOx/km
(+63.82%). The 40 t PHEV combustion mode rises from 1.67689 to 2.74708 g/km;
its final service retains the existing combustion-driving share. Approved
gasoline hybrid truck proxies inherit the corresponding diesel-engine
correction. Truck CO and all fuel inputs remain unchanged.

The large truck NOx increase is explained by the previously bypassed ageing
multiplier. It does **not** establish the validity of the underlying high
hot-emission coefficient. The original truck g/MJ derivation is unavailable,
as confirmed by the user. No guessed coefficient replacement, clipping or
compensating fuel-efficiency adjustment is applied.

Fresh generation changes only CO/NOx in 32 car services and NOx in 16 truck
services. All production recipes, other biosphere flows, fuel/electricity
inputs, battery specifications and vehicle identities are preserved. The
162-car and 127-truck activity catalogues remain unchanged. Bus model
calculations inherit the shared lookup correction; the Premise bus and
two-wheeler workbooks are not refreshed in this step.

Verification and reproducibility
--------------------------------

The 28 shared emissions tests pass, including independent numeric expectations,
mixed/reordered powertrain labels, multiple lifetimes and years, and a completed
four-family model/inventory/LCIA audit. Ten adapter-provenance tests also pass.
The native comparison independently reconstructs 3,753 emission values from
the raw endpoint tables and confirms unchanged physical specifications, fuel
use, cold starts and evaporation. The installed-workbook regression calculates
all affected service CO/NOx amounts independently from retained hot and
cold-start coefficients, mileage, fuel energy and PHEV mode shares.

The no-pollutant-clamping dispatch test had a stale transport stub lacking
``vehicle_type``, now required by the existing provenance/LPG hooks. The fixture
is completed without disabling these hooks or changing runtime code.

Source and model correction: ``060a7e9``. Premise inventory and regression
update: ``d0e0c70``. Fresh generation used
``dev/regenerate_premise_cars.py`` and ``dev/regenerate_premise_trucks.py`` with
matching Python 3.12 sources and no reused raw export. Installation identities,
coefficient boundaries and file hashes are recorded in ``installation.json``
and ``template_changes.csv``. Run
``dev/audit_premise_vehicle_deterioration.py`` to reproduce the model and
full-scenario comparison. Complete proprietary inventories remain private.

The focused Premise suite passes 181 tests. Full encrypted REMIND SSP2-NPi
builds with ecoinvent 3.12 cutoff retain 42,564 activities and 1,358,553 exchanges
in 2020, and 42,795 activities and 1,363,087 exchanges in 2050. Both builds
have zero validation errors; the 401 and 468 warning identities are unchanged.
In each year, changes are confined to 104 car and 16 truck operating services.
Every changed coefficient preserves the template's old/new ratio through
regionalization and the existing GAINS treatment. All other coefficients are
unchanged at relative tolerance 1e-12 and absolute tolerance 1e-18.

Per year, independent checks cover 726 operating services, 415 battery
allocations, 578 fuel-energy/carbon balances and 221 scenario battery designs.
There are no fuel-energy failures. Brightway readback preserves metadata for
965/1,186 activities in 2020/2050 and verifies 968 operating-energy links per
year; the existing climate-score smoke checks pass. These builds use isolated
Brightway copies and do not modify the user's persistent project.

The high truck NOx source-factor question, FCEV peak-power validation and car
PHEV capacity plausibility remain open scientific reviews. The final full
EF 3.1 comparison remains a later step after the agreed issue review.
