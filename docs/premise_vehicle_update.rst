Premise vehicle inventory update: audit and reproduction strategy
=================================================================

Hybrid deterioration lookup, 14 October 2026
-------------------------------------------

HEV/PHEV hot-exhaust ageing now selects the same petrol/diesel engine alias as
hot-factor lookup. Previously the literal hybrid label gave unity. The existing
endpoint coefficients and vehicle-lifetime averaging formula are retained as
an explicitly documented hybrid ageing proxy; cold starts and evaporation are
unaffected and PHEV mode emissions are weighted once.

Only CO/NOx in 32 car services and NOx in 16 truck services change. Production,
energy use, batteries and identities are preserved. The 40 t diesel HEV's
NOx rises 63.82%, from 1.710 to 2.802 g/km. This follows the retained ageing
formula but does not validate the underlying truck factor whose derivation
is unavailable. No regulatory clipping is applied. See
``results/premise_vehicle_deterioration_20261014/report.rst``.

The 38 shared emissions/provenance checks and 181 focused Premise tests pass.
Full 2020/2050 builds have zero errors and unchanged warning identities;
coefficient changes are confined to 104 car and 16 truck operating services
per year. Fuel/carbon, battery/payload and Brightway metadata checks pass.

FCEV power and pack accounting, 14 October 2026
----------------------------------------------

The power buffer now supplies the complement of the net fuel-cell share of
vehicle power. The fuel-cell rating includes its own consumption and must not
be multiplied by the complementary share. Complete car pack mass now equals
cell mass divided by the declared cell fraction. Starter-battery sizing also
preserves FCEV traction power in trucks and buses.

The 2020 Medium car buffer changes from 3.366 to 3.928 kWh and 18.232 to
23.380 kg; the coupled mass correction increases hydrogen demand by 0.175%.
The 40 t truck retains 71.101 kWh and 423.219 kg, with 218.016 kW now recorded
instead of zero. Eight car services and eight production templates change
coefficients; all truck coefficients and all vehicle identities are preserved.
Power requirements and limitations are recorded in dataset comments and
baseline provenance. See ``results/premise_vehicle_fcev_20261014/report.rst``.

Full 2020/2050 REMIND SSP2-NPi builds pass with zero validation errors and
unchanged warning identities. Numerical changes are confined to 88 FCEV car
activities per year after regionalization. Fuel-energy/carbon, pack allocation,
scenario battery/payload and Brightway metadata checks pass; the focused suites
pass 93 model/adapter checks and 184 Premise tests.

The heavy-vehicle buffer remains an energy-based assumption, 20 kWh plus 6%
of hydrogen chemical energy. The truck's inherited lead-acid specific-power
input is not a valid verification of its lithium-ion traction pack. This fix
closes the model's nominal power and mass accounting; it does not independently
validate cell peak power, motor/inverter peak losses or sustained power delivery.
Buses inherit the shared correction, but their Premise workbook is not refreshed.

Truck HEV traction storage, 13 October 2026
---------------------------------------------

Truck HEVs now have finite high-power traction buffers, separate from their
lead-acid starters. Power/energy sizing is coupled to vehicle mass and fuel
use; curtailed regeneration receives neither fuel nor brake-wear credit.
The seven 2020 nominal packs are 3.75--13.01 kWh. The 40 t case uses 9.96 kWh,
196 kg and 0.623 additional lifetime packs. Generic LFP cycle life and
chemistry-specific prices remain documented proxies.

The user retained Premise's MIX capacity market despite its physical
mass/chemistry mismatch. Initial and replacement nominal kWh are supplied
once, and the market includes manufacture and disposal. Comments disclose
the A123 2014 cell source, 25-degree-C conditioning assumption, engineering
SOC window, price proxy and mass mismatch. All vehicle identities are preserved.

Only nine HEV services and seven production recipes change materially. Full
2020/2050 REMIND SSP2-NPi builds pass with no new validation errors or warning
identities; fuel-carbon and hydrogen checks also pass. HEVs remain RER
templates connected to EUR scenario fuel markets, with unchanged 2020 fuel
quantities in 2050 because they have no separate IAM efficiency mapping.
Future hardware resizing and the PHEV cycling decision remain open.
See ``results/premise_truck_hev_storage_20261013/report.rst``.
The final installed-family qualification passes 1768 tests plus wheel/sdist
resource and offline model/LCIA checks; 70 focused Premise tests also pass.
The model correction is ``fb0106e`` and the Premise inventory update is
``9372892``.

PHEV replacement accounting, 13 October 2026
--------------------------------------------

Car PHEVs now use the approved 200,000 vehicle-km battery distance life and
existing 18-year calendar limit. Both driving-mode costs and final assembly
retain one physical pack's replacement count. The default 2020 cars still have
zero replacements and unchanged inventory coefficients.

Truck electric lifetime use is now weighted before subtracting the initial
pack and clipping the replacement count. Under the existing net-energy
approximation, the seven Regional-delivery PHEVs now require zero replacements.
This approximation excludes regenerative cycling and has no separate calendar
limit; the wider cycling question remains open with the hybrid-storage review.
The modelled physical packs are unchanged. The 40 t lifetime purchase changes
from 102.324451 to 77.323265 kWh. Names and operating inventories are preserved.

The report and verified 2020/2050 builds are recorded in
``results/premise_vehicle_replacements_20261013/report.rst``. The five-package
installed-artifact check passes 1,748 tests plus wheel/sdist resource checks and
offline model/LCIA smoke tests. These results verify the current net-energy
arithmetic, not an unimplemented regenerative-cycling model.

PHEV capacity correction, 13 October 2026
----------------------------------------

The shared model now retains the full electric-mode pack capacity when combining
PHEV modes. Previously it preserved pack mass while usage-weighting stored
energy. The regenerated Medium car therefore purchases 30.576 kWh instead of
23.895 kWh. All 16 car PHEV production templates are corrected. Trucks now use
the same model capacity directly, replacing the adapter's mass-derived workaround;
their installed battery purchases are unchanged apart from floating-point rounding.

The range calculation uses usable capacity (nominal kWh times depth of discharge).
Car and truck purchase costs price the full pack before financing. Fuel demand,
charging demand, emissions, physical masses and replacement counts are unchanged.
Premise continues to purchase initial and replacement capacity through its kWh
markets, which already include battery end of life. Replacement-count accounting
and future range-preserving sizing remain separate open tasks.

The supporting report is
``results/premise_vehicle_phev_20261013/report.rst``. Earlier audit findings below
describe their recorded baseline, not the corrected PHEV capacity.

Audit date: 12 October 2026. The initial strategy and feasibility audit below
is retained as a record of the original four workbooks. Passenger-car
implementation followed this audit; see the implementation section at the end.
Raw diagnostic exports remain separate from the adapted replacement inventory.

Agreed scope
------------

Regenerate **2020 vehicles**, with EURO-6 cars, EURO-VI buses/trucks and
EURO-5 two-wheelers, plus electric and human-powered vehicles. Exclude older
EURO classes. The two-wheeler model has no EURO-VI factors.

The user selected the following boundaries:

* Premise supplies the regional scenario fuel blends and electricity.
* Retain premise's battery-capacity markets, supplying updated capacities and
  replacement counts from carculator.
* Retain unsupported vehicle types through explicitly documented proxies;
  scientific corrections to these proxies must be reviewed.
* Retain the tram separately; it is outside carculator_two_wheeler.
* Keep custom noise flows in a companion audit file, outside premise imports.

This supersedes the initial possibility of retaining historical vintages.
It retains **180 transport services** and excludes 176 historical services.
All 86 services selected by the existing four IAM mapping files remain in scope.
These are workbook-level name-filter counts across IAM models, not a claim
that every IAM scenario contains all 86 technologies.

Files and import path
---------------------

All four files are in ``../premise/premise/data/additional_inventories/``.

.. list-table:: Parsed workbook contents
   :header-rows: 1
   :widths: 28 12 12 12 12 24

   * - Workbook
     - Activities
     - Transport services
     - Selected for update
     - IAM-mapped services
     - Transport unit and geography
   * - ``lci-pass_cars.xlsx``
     - 405
     - 202
     - 74
     - 35
     - vehicle-km; RER
   * - ``lci-buses.xlsx``
     - 151
     - 72
     - 36
     - 7
     - person-km; RER
   * - ``lci-trucks.xlsx``
     - 120
     - 52
     - 52
     - 38
     - tonne-km; RER
   * - ``lci-two_wheelers.xlsx``
     - 68
     - 30
     - 18, including tram
     - 6
     - 29 vehicle-km services and one tram person-km service; CH

The workbooks contain 31,614 exchanges in total. A separate bw2io
``ExcelImporter`` extraction reproduced every activity and exchange count.
The audit found numeric finite exchange amounts and one production exchange
per activity. This is structural evidence, not supplier-linking certification.

``premise/new_database.py`` declares the paths at lines 298--301 and imports
all four as **ecoinvent 3.7** inventories in its default inventory list.
The active importer is ``DefaultInventory``, not the historical
``VariousVehicles`` class. It migrates suppliers, adds product/biosphere
links, checks units and removes duplicates. The order is two-wheelers,
trucks, buses, then cars.

``premise/transport.py`` subsequently regionalizes selected services,
applies IAM energy-efficiency changes, builds fleet markets and relinks
transport demand. Selection depends on the exact terminology in
``premise/iam_variables_mapping/transport_{passenger_cars,bus,road_freight,two_wheelers}.yaml``.
The relative efficiency reference is 2020 in
``BaseTransformation.find_iam_efficiency_change``.

What the existing inventories actually represent
------------------------------------------------

Cars
~~~~

Eight principal sizes span Mini through Van, including the SUV classes;
Micro appears only as a BEV. The old services include gasoline, diesel,
CNG, gasoline/diesel HEVs and PHEVs, BEVs and FCEVs. One Medium LPG service
uses the CNG vehicle-production activity as a proxy.

EURO-2, EURO-3, EURO-4, EURO-6ab and EURO-6 variants are stored as separate
activities, without an explicit manufacture year. EURO-6 services can link
to production activities named EURO-6d. Preserve each service's product
identity when adapting names; the standard can also occur in its product.
The selected set contains 57 EURO-6 services and 17 BEV/FCEV services.

For the Medium car, the workbook specifies 200,000 lifetime km and
12,000 km/year. Vehicle production is allocated at 5e-6 vehicles/km.
The BEV comment specifies 48 kWh and a 400 kg pack; its grid purchase is
0.229366 kWh/km. The gasoline service purchases 0.0546145 kg petrol/km.
These are useful reconstruction checks, not target values to force the
corrected model to reproduce.

Buses
~~~~~

Six classes map to the current model as follows:

.. list-table:: Bus size mapping
   :header-rows: 1

   * - Workbook label
     - Model coordinate
   * - 9m midibus
     - ``9m``
   * - 13m single deck urban bus
     - ``13m-city``
   * - 13m double deck urban bus
     - ``13m-city-double``
   * - 13m single deck coach bus
     - ``13m-coach``
   * - 13m double deck coach bus
     - ``13m-coach-double``
   * - 18m articulated urban bus
     - ``18m``

Diesel and CNG span EURO-III through VI; diesel hybrids use VI.
Electric services distinguish overnight charging, opportunity charging and
battery-equipped trolleybuses. LTO is explicit for the latter two strategies.
FCEVs cover all six sizes. Gasoline and LPG urban buses are manually adapted
diesel and CNG proxies, respectively. The selected set is 20 EURO-VI services
and 16 electric/FCEV services.

The 13m diesel urban bus carries 10 passengers and lasts 700,000 km.
Its vehicle exchange is 1 / (700,000 * 10) per passenger-km.
The overnight BEV has a 399 kWh capacity-market exchange in vehicle production;
its comment also reports 399 kWh, with no separate replacement multiplier
visible on that exchange. Its operating grid purchase is 0.210963 kWh/pkm.

The LPG proxy needs explicit correction review: it purchases
**0.308300 kg LPG/pkm**, versus 0.0295319 kg CNG/pkm in its source proxy,
while retaining the same 0.0788301 kg fossil CO2/pkm. This does not establish
the intended corrected LPG consumption. It demonstrates that copying the
old amount and emissions together is not a defensible regeneration rule.

Trucks
~~~~~~

All seven sizes are present: 3.5, 7.5, 18, 26, 32, 40 and 60 metric tonnes.
There are 42 native combinations of BEV, FCEV, diesel, CNG, diesel hybrid and
diesel PHEV, plus ten gasoline/LPG adaptations. Model coordinates use
``3.5t`` through ``60t``. Gasoline and gasoline-hybrid trucks lack native
powertrains; several old gasoline services use diesel production and the
same fuel mass as the diesel service. LPG services use CNG production.

**85 truck workbook activities explicitly say manufacture year 2050.**
Other comments omit the year. These are therefore not a consistent 2020
template collection. The agreed 2020 update changes this baseline explicitly,
separately from the effects of numerical and background corrections.

For the 40t truck, comments specify 13,800 kg payload, 710,000 lifetime km,
107,000 km/year and an 800 km range. Vehicle production is allocated at
1 / (710,000 * 13.8) per tonne-km. Its old BEV production activity purchases
1,069 kWh from ``market for battery capacity (MIX scenario)``.

All 52 truck transport activities have a production-exchange name that differs
from the activity name. Premise repairs production names in
``add_product_field_to_exchanges``; this is a workbook inconsistency rather
than proof that current imports fail. New workbooks should be internally
consistent without depending on that repair.

Two-wheelers and tram
~~~~~~~~~~~~~~~~~~~~~

This is a 2021 spreadsheet model, not simply a recent carculator export.
The Readme identifies Sacchi/Bauer, review by Cox, and a 2 November 2021
revision. Nineteen inventory sheets are imported; eight supporting sheets
are skipped. It contains 8,859 formulas. The 216 missing formula caches
occur outside the imported inventory sheets; imported exchange amounts
were numeric in the audited file. Reading/saving formulas with openpyxl
does not recalculate them.

The workbook explicitly uses 2006/EURO-3, 2016/EURO-4 and 2020/EURO-5 for
six petrol classes. Only the six 2020 petrol services remain in the update.
Electric bicycles, scooters, motorcycles and the conventional bicycle remain,
as does the separately maintained electric tram.

Map ``Motorbike`` to model ``Motorcycle`` size labels, ``Kick Scooter`` to
``Kick-scooter``, and the bicycle speed/cargo labels to the current bicycle
coordinates. The old electric Motorbike below 4 kW has **no direct native
equivalent**: ``Motorcycle <4kW`` does not exist and ``BEV / Moped <4kW``
is explicitly unavailable. Its replacement requires a reviewed proxy,
not an unlabelled coordinate substitution.

The 11--35 kW petrol motorcycle has 38,500 lifetime km in the workbook,
1.1 passengers and 2,405 km/year. Current 2020 defaults instead use
50,000 lifetime km. Such changes must be visible in the comparison report;
using the same size label does not preserve the same engineering assumptions.

Shared dependencies and incompatibilities
-----------------------------------------

The four workbooks reference 197 distinct supplier identities not defined
within this four-file collection. These include ordinary background suppliers
and other premise supplementary inventories; they are not 197 missing links.
Two auxiliary identities occur in more than one workbook: ``HDPE tank liner``
and ``EV charger, level 3, plugin, 200 kW``. Their audited recipes agree up
to rounding. Future corrected versions must have one owner, or equivalent
recipes, because import order and duplicate removal can otherwise retain an
older recipe.

The current export API defaults to **ecoinvent 3.12**, uses Brightpath,
and does not support 3.7. Legacy 3.9/3.10 routes are conditional. The current
source versions inspected and executed were:

.. list-table:: Local source snapshot
   :header-rows: 1

   * - Package
     - Version
     - Git revision
   * - carculator_utils
     - 1.3.7
     - ``9bafa0d25d``
   * - carculator
     - 1.9.7
     - ``ddcac198bb``
   * - carculator_bus
     - 0.1.2
     - ``010b8e7db5``
   * - carculator_truck
     - 0.5.2
     - ``6ec213d3de``
   * - carculator_two_wheeler
     - 0.1.1
     - ``a3c6e4959e``
   * - premise checkout
     - source snapshot
     - ``a7c19af525``

The new exports use names such as ``transport, car, gasoline, Medium`` and
``transport, bus, diesel, 13m-city``, without EURO suffixes. They do not match
the existing premise transport mappings. They also use internal
``fuel supply for ...`` and ``electricity supply for ...`` activities,
including carculator's country/year and lifetime assumptions. ``scenario='static'``
alone does not turn these into premise regional scenario markets.

Bus exports use ``passenger kilometer``, which is absent from the current
premise importer unit whitelist. The agreed adapter must use the existing
``person kilometer`` identity consistently in activities and exchanges.
Custom noise exchanges use ``joule``, also absent from that whitelist, and
need the agreed companion-file treatment. Retain their original amounts,
compartments, units and vehicle identities in that file; do not imply they
are included in premise LCIA.

Battery handling requires a coordinated change. The existing truck override
in ``Transport.create_vehicle_markets`` selects unit activities containing
both ``truck`` and ``battery electric``. None of the old workbook's BEV
production names, which start with ``lorry production``, match that selector.
The new raw name ``truck, battery electric, 40t`` does match, but the override
then expects a ``40 metric ton`` size label and kWh battery exchanges.
Raw carculator instead supplies **kg of battery multiplied by
(1 + replacement count)**. Changing only names can expose a size lookup
failure or a mass/capacity unit error. Do not infer successful old override
execution from the existence of the method.

Recent corrections the update should carry through
--------------------------------------------------

The coordinated changelogs and current source identify several changes that
matter directly to these inventories:

* Shared battery charging/discharging and hybrid energy accounting, converged
  mass/energy sizing, and corrected electricity purchases affect operation
  and component quantities. Corrected hot-emission translation must survive
  premise's subsequent pollutant processing.
* Truck battery/fuel-cell replacements are calculated after sizing. Depot
  chargers are allocated over lifetime and capacity-limited fleet throughput.
  Preserve those physical allocations when simplifying the exported graph.
* Buses no longer change hybridization automatically to meet energy targets.
  The updated auxiliary prior affects city-bus energy. Charger-equipped buses
  retain a minimum of one replacement energy battery: the diagnostic 2020
  overnight bus has 264.676 kWh initially and therefore **529.352 kWh of
  initial-plus-replacement capacity**, before adaptation to premise markets.
* Two-wheeler petrol efficiency and component/inventory alignment were
  corrected. Current 2020 data must be loaded from the updated package rather
  than inferred from the old spreadsheet's cached results.
* Additional delivered-CNG leakage defaults to zero; upstream emissions and
  exhaust methane remain separate. Do not restore the old unqualified 0.4%
  overlay while adapting fuels.
* The shared 3.12 background includes corrected hydrogen-tank recipes,
  an explicit NMC-532 chemistry migration and updated PV electricity
  coefficients. Duplicate handling must not reintroduce old component recipes.

Pure financing, cost-price and reproducibility corrections are useful but
do not by themselves imply changed physical exchanges. The numerical
comparison must distinguish those from inventory-relevant changes.

Reproduction strategy
---------------------

1. Freeze the evidence and generation manifest.
   Store workbook hashes, source revisions, dependency versions and the
   selected 180 service identities. The generated ``candidate_recipes.csv``
   contains all 356 original services with a selection flag; selected rows
   contain 165 native candidates, 14 proxy cases and one retained tram.
   Lock functional units and record input provenance, model year, cycle,
   climate, load, lifetime, range, battery chemistry and replacement policy.
   The diagnostic CH/default runs below are not approval of all those
   operating assumptions. Recover them from metadata where possible and
   obtain decisions for remaining material ambiguities.

2. Generate deterministic 2020 physical inventories.
   Use the matched Python 3.12 source family, ``inputs.static()``, one sample,
   the scoped array builder, model ``set_all()``, then the vehicle inventory.
   Use vkm for cars/two-wheelers, pkm for buses and tkm for trucks. Preserve
   labelled loads and retain PHEV component construction. Start with the
   tested representative cases, then qualify the selected scope. Export
   against 3.12 in a staging directory. Unavailable/infeasible cells must
   become explicit exceptions, never zero-impact replacement vehicles.

3. Apply a dedicated premise adapter.
   Rename services, vehicle production, reference products and every internal
   reference together, using the explicit manifest. Preserve legacy external
   identities where they select the agreed 2020 class. Apply the RER/CH
   template geography independently of physical climate inputs. Keep the
   transport--vehicle-production split, component supply, maintenance,
   end-of-life, abrasion, road and charging-infrastructure boundaries.
   Retain only reachable auxiliary activities; the auxiliary count need not
   remain 744 minus the old transport count.

4. Give premise ownership of operational energy supply.
   Replace carculator's operational fuel/electricity supplier activities with
   the approved premise market boundary. Do not accidentally retain embedded
   Swiss lifetime electricity mixes, synthetic routes or country biofuel
   shares. Carry final grid purchases including charging losses. Express
   liquid fuels and hydrogen in kg and verify gas mass/volume conversion.
   Preserve useful-energy demand when changing blend LHV, and recompute
   fossil/biogenic carbon and relevant blend-sensitive emissions consistently.
   Generic market names alone do not establish a carbon split. Test the
   adapted service after regional relinking and scenario fuel updates.

5. Adapt battery demand explicitly in kWh.
   For the energy battery, carry total nominal capacity demand per vehicle
   as ``electric energy stored * (1 + battery lifetime replacements)``.
   Use premise's existing capacity-market ownership, retaining LTO-specific
   markets for opportunity/trolleybus cases and the reviewed chemistry/mix
   mapping for other vehicles. Remove the superseded kg production demand
   only after reconciling pack, cell, BMS, balance-of-pack and end-of-life
   coverage; keep power batteries separate. Avoid counting components or
   disposal twice. Record both initial capacity and replacement multiplier.
   Replace or constrain the old truck overwrite so it cannot discard
   replacement counts or overwrite kg exchanges. If future range-dependent
   capacity tables are retained, regenerate them from explicit range cases
   and validate mass, payload and energy consistency; the old table cannot
   serve as evidence for the new model.

6. Review the fourteen proxies and preserve the tram.
   The proxy set is one LPG car, gasoline/LPG buses, ten gasoline/LPG truck
   variants, and the electric Motorbike below 4 kW. Record the source model,
   engineering rationale and every changed exchange. Fuel substitution
   requires energy and carbon calculations rather than replacing a supplier
   name at unchanged mass. LPG tank construction and powertrain efficiency
   need an explicit judgement. Keep the tram and its dependency closure in
   a separate retained section; do not regenerate it using a two-wheeler model.

7. Integrate and validate before replacing workbooks.
   Change the four premise ``version_in`` declarations to 3.12 with the new
   workbooks. Migration to other supported ecoinvent versions and consequential
   databases needs independent exact-link tests; a 3.12 export is not proof
   of backward compatibility. Rebuild supplementary-inventory caches.
   Resolve common auxiliaries against all other premise inventories so that
   corrected tanks, chargers and batteries survive duplicate removal.

Validation gates
----------------

* Coverage: 180 intended services, explicit treatment of all proxy exceptions,
  no old EURO classes in the update, and continued coverage of all 86
  workbook-level IAM matches. Also test aliases per IAM model and region
  in actual scenario builds. Inspect any references to deleted historical
  production activities before removing their dependency closure.
* Structure: one matching production exchange; unique activity/product/location/
  unit identities; finite signed amounts; consistent units; exact biosphere
  and technosphere matches; no duplicate corrected auxiliary recipes.
* Physics: mass/payload/range feasibility, grid consumption including losses,
  fuel energy and carbon balances, battery capacity and replacement totals,
  charging infrastructure, and correct lifetime/load normalization.
* Scenario ownership: inspect changes before and after energy-efficiency
  adjustment, regional fuel/electricity linking and battery updates. Review
  premise's car consumption floor and car/truck pollutant normalization:
  they can modify the corrected foreground. In particular, current EURO
  substring handling and fuel-name matching warrant regression cases.
* Numerical attribution: separate vehicle-model/input changes, rebasing of
  old truck templates from 2050 to 2020, background 3.7-to-3.12 migration,
  and premise scenario transformations. Never treat a changed LCIA score
  across different backgrounds as a model-only effect.
* Import/build: first use bw2io extraction and a no-write premise build,
  then an isolated test database for written exchange/LCIA checks. Qualify
  a baseline and a future scenario, with BEV, combustion, gas, PHEV and FCEV
  examples. No production Brightway project is needed for generation itself.

Executed model and export checks
--------------------------------

Python 3.12.13 and NumPy 1.26.4 were used, with imports explicitly pointed
at the local source checkouts. Eight 2020 vehicles completed model sizing,
inventory construction, finite ReCiPe midpoint LCIA and actual Brightway
Excel serialization/readback: Medium car, 13m urban bus, 40t long-haul truck,
and 11--35 kW motorcycle, each with combustion and electric powertrains.
Vehicle lifetime/load allocation and grid-electricity normalization passed
independent arithmetic checks for all eight. Two additional 2050 truck
cases passed the same checks to distinguish vintage from model changes.

A subsequent model-only screening covered all **165 selected native candidates**
(73 cars, 34 buses, 42 trucks and 16 two-wheelers). All completed with finite
reported screening quantities, positive energy demand and, for trucks,
positive payload; the model availability/compliance flags passed where those
flags are populated. Two-wheelers implement their availability policy directly
through energy masking rather than the unused legacy ``is_available`` input.
This screening does not replace inventory/export checks for the full grid,
or validation of the final cycle, climate and operating assumptions.

.. list-table:: Selected physical differences, not a controlled model-only comparison
   :header-rows: 1

   * - Quantity
     - Existing workbook
     - Current model diagnostic
   * - Medium BEV grid demand, kWh/vkm
     - 0.229366
     - 0.176111 (2020)
   * - Medium BEV pack capacity, kWh
     - 48, from comment
     - 67.2 (2020; same 400 kg pack mass)
   * - 13m overnight BEV grid demand, kWh/pkm
     - 0.210963
     - 0.127344 (2020; 10 passengers)
   * - 40t diesel TtW energy, MJ/vkm
     - 6.279, comment marked 2050
     - 8.398 (2050); 11.811 (2020)
   * - 40t BEV pack capacity, kWh
     - 1,069, comment marked 2050
     - 876.6 (2050); 1,256.5 (2020)
   * - Petrol 11--35 kW motorcycle lifetime, km
     - 38,500
     - 50,000 (2020)

The diagnostics use CH climate/default operation and default carculator fuel
recipes, before applying the approved premise adapter. They demonstrate
executable generation and substantive differences, not final replacement
amounts or controlled empirical validation. The four raw workbooks do not
pass premise's name/unit/noise contract unchanged. Exact destination linking,
complete proxy generation and a full premise scenario build have not been run.

Artifacts and rerunning
-----------------------

The audit artifacts are in ``results/premise_vehicle_audit_20261012/``:
``datasets.csv`` (metadata and workbook row numbers),
``candidate_recipes.csv`` (selected scope and model/proxy mappings),
``mapping_coverage.csv``, ``external_suppliers.csv``, ``summary.json``,
``checks.json``, ``provenance.json``, ``decisions.json`` and the parsed inventories.
``bw2io_extraction_check.json`` records the independent reader's counts.
Full native-scope screening is recorded in
``results/premise_vehicle_scope_20261012/feasibility.json``.

Raw exports and arithmetic checks are in
``results/premise_vehicle_probe_20261012/`` and
``results/premise_vehicle_probe_truck2050_20261012/``.
These are diagnostic artifacts and should not be copied into premise.

With a matching Python 3.12 environment, run from this repository root,
using new output directories::

   python dev/audit_premise_vehicle_workbooks.py \
       --premise ../premise --output /tmp/premise-vehicle-audit-new
   python dev/probe_premise_vehicle_regeneration.py \
       --year 2020 --output /tmp/premise-vehicle-probe-new
   python dev/probe_premise_vehicle_regeneration.py \
       --families truck --year 2050 --output /tmp/premise-truck2050-new
   python dev/probe_premise_vehicle_regeneration.py \
       --scope-manifest /tmp/premise-vehicle-audit-new/candidate_recipes.csv \
       --output /tmp/premise-vehicle-scope-new

No original workbook, model implementation, premise source or existing
Brightway project was changed by the initial audit.

Passenger-car implementation
----------------------------

The accepted car recipe uses the latest 2020 engineering and usage defaults,
Swiss climate, the default driving cycle, and the 74 selected service identities.
The generated workbook has 73 vehicle-production datasets (LPG shares its CNG
vehicle) and 15 reachable supporting component datasets. Historical EURO classes
are omitted. Supporting components have distinct car-specific names so that
earlier bus/truck imports cannot replace the corrected manufacturing recipes.

``dev/regenerate_premise_cars.py`` generates the workbook and companion noise
and parameter audits in ``results/premise_cars_2020_20261012/``. Fuel energy is
preserved when converting default model fuel consumption to premise's reference
fuels. The template records reference fossil CO2; premise owns the regional
fossil/biogenic split. Hydrogen retains default compression electricity
(2.616238 kWh/kg) with regional electricity. Battery mass purchases and disposal
are replaced together by nominal kWh times one plus lifetime replacements,
because premise's capacity markets include both manufacture and disposal.

LPG uses CNG efficiency, manufacture including its tank, maintenance, and
non-CO2 combustion factors. LPG-specific LHV and CO2 factors are used. Generic-air
pump-to-tank methane leakage is excluded; the current 2020 default leakage is
zero. This remains a documented proxy, not a native LPG model.

``dev/validate_premise_cars.py`` checks identities, selector coverage, lifetime,
battery and carbon arithmetic, and exact links to ecoinvent 3.12, the biosphere,
the generated foreground, or premise's battery-capacity markets. All 35 IAM
selectors retain exactly one candidate; all 5,289 non-production exchanges link.
The noise companion contains 1,776 exchanges excluded from the workbook.

The paired full-database experiment uses ``dev/build_premise_car_comparison.py``
and ``dev/compare_premise_car_ef31.py``: REMIND SSP2-NPi, 2020, ecoinvent 3.12
cutoff, encrypted IAM input, all default sectors, and identical uncertainty
settings. Both variants use the same car integration fixes: regional vehicle-grade
CNG markets and kg-based gas carbon reclassification; hydrogen compression is
included in FCEV energy scaling and is not checked against BEV traction bounds.
The unchanged Brightway source project was copied into a private temporary
workspace. Neither source ecoinvent nor the user's original project is modified.

The comparison folder contains full method tuples, activity keys, build hashes,
validation reports, scores per vehicle-kilometre, absolute and relative changes,
and a Medium-car climate figure. It covers the RER catalogue and EUR regionalized
subset. Regionalized RER activities can be forwarding activities in the full
premise database; their scores must not be interpreted as untouched raw templates.
No weighting or normalization combines the 16 EF 3.1 headline categories.

Regional-truck implementation, 13 October 2026
--------------------------------------------

The accepted truck recipe uses 2020 defaults and the ``Regional delivery``
cycle, with a 400 km design range, Swiss climate, and the cycle's default
payload and annual mileage. It retains all 52 service identities, with 42
production datasets and 33 qualified supporting components. A separate
26-dataset legacy-component workbook preserves suppliers used by other
vehicle families. The new workbook imports as ecoinvent 3.12; the legacy
components retain their ecoinvent 3.7 migration.

Nominal BEV capacities for the 3.5, 7.5, 18, 26, 32, 40 and 60 t sizes are
133.8, 203.2, 333.1, 405.6, 518.2, 550.9 and 725.2 kWh, respectively. All use
80% depth of discharge and zero modelled lifetime replacements. Physical
sizing uses NMC622; the upstream battery mix remains controlled by Premise's
capacity markets. PHEV nominal capacity is recovered from the full physical
pack mass because the shared model's reported capacity is weighted by electric
utility factor. The adapter retains model replacement counts; their PHEV
aggregation remains a separate issue for review.

The ten gasoline/LPG proxies preserve modelled fuel energy when converting
consumption to the target fuel. Their diesel/diesel-hybrid or CNG manufacture
and non-CO2 combustion factors remain documented proxies. LPG excludes
CNG-specific leakage. Operating fuel blends, electricity and fuel-carbon
reclassification remain with Premise. Noise is retained in a companion audit.

``dev/regenerate_premise_trucks.py`` and ``dev/validate_premise_trucks.py``
generate and check the workbook. The full controlled comparison and its
report are in ``results/premise_trucks_regional_20261013/``. Both databases use
REMIND SSP2-NPi 2020, ecoinvent 3.12 cutoff, and the same updated cars. The
comparison covers 52 RER and 20 EUR truck services across 16 EF 3.1 categories.
The 40 t EUR BEV climate score rises 31.8% per tkm but falls 1.6% per vkm when
each score is multiplied by its own payload: 13.8 t previously, 10.3 t now.
This comparison combines model-year, cycle, payload and recipe changes.

The full build has zero validation errors and 401 warnings. All 38 selectors,
3,429 non-production workbook links, 42 production battery quantities and
205 EUR non-CO2 checks pass. Independent solves reproduce all 1,152 paired
scores within 9.92e-8 relative difference. The metals suite passes 81 tests.
Changes to existing recipes are confined to truck services and manufacture;
the 33 qualified components are additions. The installation receipt records
the persistent database and installed file hashes, retaining the old baseline.
