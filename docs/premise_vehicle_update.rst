Premise vehicle inventory campaign: completed
==============================================

The campaign was closed on 14 October 2026 at the user's request. Passenger-car
and truck inventories are updated, their model corrections are committed, and
the final 2020/2050 scenario checks pass. Earlier dated reports describe the
state at each step; their proposed follow-ups are not an active work queue.
The bus and two-wheeler Premise workbooks were not regenerated in this campaign.

Installed scope and assumptions
-------------------------------

The authoritative files are in the sibling Premise checkout under
``premise/data/additional_inventories/``:

* ``lci-pass_cars.xlsx``: 74 transport services, 73 vehicle-production recipes
  and 15 supporting components, all based on current 2020 car defaults.
* ``lci-trucks.xlsx``: 52 services, 42 vehicle-production recipes and 33 supporting
  components. All seven weight classes use Regional delivery and a 400 km
  baseline range, rather than exporting three driving cycles.
* ``lci-truck-legacy-components.xlsx``: 26 compatibility recipes on their original
  ecoinvent 3.7 import basis, for consumers outside the refreshed truck catalogue.

The refreshed workbooks target ecoinvent 3.12 cutoff. Selected service and
manufacturing identities are retained; older car EURO classes are excluded.
Cars use EURO-6 and trucks EURO-VI where relevant. Electric vehicles have no
EURO class. Both families use Swiss climate. Cars use WLTC, 12,000 km/year and
1.8 cold starts/hot soaks per day. The source model's general start-frequency
default remains 2.3/day. Truck load and mileage follow Regional-delivery defaults.

Each workbook has ``*.parameters.csv``, ``*.noise.csv`` and
``*.provenance.json`` companions. Comments and structured metadata retain model
name, publication, source hashes, baseline specifications and explicit proxy
boundaries. Custom noise stays in the companion audit and is omitted from
Premise imports. Shared component recipes keep their activity-specific sources.

Fuel, emissions and future scenarios
------------------------------------

Premise owns regional operating-fuel blends and electricity. Model fuel energy
is preserved when converting to its reference fuels; delivered CNG is
46.5 MJ/kg. CNG compression is regionalized before its market. The fuel module
updates fossil/non-fossil combustion CO2 from final linked suppliers and final
purchases. Hydrogen preparation uses the documented 30-bar inlet and 700-bar
tank, at 2.45062 kWh/kg, and scales with hydrogen consumption.

LPG cars retain CNG efficiency, manufacture and non-CO2 combustion factors;
unsupported gasoline/LPG trucks retain documented diesel/hybrid or CNG proxies.
Fuel conversions preserve energy. LPG excludes CNG pump-to-tank methane leakage
and retains explicitly fossil supply where the IAM has no LPG pathway.

Evaporative benzene is retained with residual NMVOC; exhaust-derived aldehydes
are not assigned to evaporation. Hybrid hot-exhaust deterioration follows the
corresponding petrol/diesel engine mapping. Premise emission diagnostics are
read-only: they do not clamp cold-start, evaporative or hot-exhaust amounts to
hot-reference factors or interpret those factors as EURO certification limits.
Fuel-derived CO2/SO2 and distance/start-related emissions retain separate drivers.

Future BEV/PHEV capacities preserve baseline range with simple arithmetic using
IAM energy-use changes. Physical pack mass follows the existing chemistry-density
projection, retaining calibrated PHEV density offsets. For BEV trucks, lighter
packs increase available payload at fixed utilization; production, energy and
other kilometre-based burdens are then divided by the updated cargo load.
There is no vehicle-model solver at Premise runtime. FCEV hardware and hydrogen
tanks retain their corrected 2020 design. Missing efficiency series retain the
existing fallback behavior; the approved REMIND Large Car/SUV fallback transfers
only a relative efficiency trend, not SUV fleet volumes.

Battery corrections and retained proxies
----------------------------------------

PHEVs carry one complete physical pack in both driving modes. Nominal capacity
is not weighted by electric use. Car packs use documented 2020 manufacturer
pairs or explicit size/density proxies (8.8--24 kWh), with 200,000 vehicle-km
and the existing 18-year replacement-life limit. Truck replacement counting
weights lifetime electric use before subtracting the initial pack; its net-energy
cycling approximation is retained.

Truck HEVs have power/energy-sized high-power buffers (3.75--13.01 kWh for the
2020 templates), separate from lead-acid starters. Costs, mass, consumption and
cycle use are coupled. Source cell ratings, generic LFP cycle life and chemistry
price proxies are documented.

FCEV electrical sizing includes motor/inverter losses and auxiliaries, with
stack own consumption counted once. The 3.5/7.5 t truck motors use documented
57/129 kW proxies. Truck buffers use the approved AKASOL pack reference with
continuous charging/discharge checks and coupled mass/energy sizing; nominal
capacities are 32.86--95.57 kWh. Car buffers use the late-2020 Mirai paired
mass/energy/ten-second power reference; the Medium car is 1.60 kWh and 57.3 kg.
Car charging capability remains unverified and unconstrained.

All refreshed traction batteries purchase Premise capacity markets in nominal
kWh, including replacements and disposal. The user retained MIX markets even
where manufacturing mass/chemistry differs from the high-power physical pack.
A lower capacity-market burden is therefore not proof of a real manufacturing
improvement. No new SOC, electrothermal, fuel-cell ramp or ageing model is claimed.

Verification and campaign closure
---------------------------------

The final REMIND SSP2-NPi / ecoinvent 3.12 cutoff builds contain 42,564 activities
in 2020 and 42,795 in 2050, with zero validation errors. The 401/468 existing
warning identities are unchanged. Fuel-energy/carbon balances, battery allocation,
future hardware and saved metadata pass. Each exported database passes 968
operating-energy link checks. The final car-buffer step passed 161 focused tests
and wheel/sdist plus native-LCIA checks; these are not a claim of a new full
family test run at campaign closure.

Closeout verification passed 15 focused baseline/provenance/adapter tests and
four strict Sphinx HTML builds (utils, car, truck and Premise). Reusing the
retained native exports with the new baseline reader reproduced all 315
installed activities and 9,270 exchange coefficients within numerical comparison
tolerance. This checked the adapter change, not a fresh native-model or LCIA run.
The compact record is ``results/vehicle_campaign_closeout_20261014/verification.json``.

The last incremental EF 3.1 comparison covers eight RER and six EUR FCEV car
services across sixteen headline indicators (224 pairs). Climate changes are
+0.003--0.153%; the largest toxicity decrease is explained by the retained MIX
capacity proxy, with that interpretation limitation explicitly recorded.
The final truck-buffer report contains 192 incremental pairs. These are
step-specific comparisons. A complete original-legacy-versus-final catalogue
comparison was not completed and is not claimed by this closure.

Accepted limitations include unreconstructable truck hot-NOx coefficient
provenance, unverified car charging/continuous-output limits, high-power battery
manufacturing proxies, and the skipped PHEV cycling and future FCEV tank reviews.
The campaign closes with these documented limitations, rather than asserting
that all vehicles are independently validated or EURO-certified.

Final evidence is retained in ``results/premise_car_fcev_buffer_20261014/`` and
``results/premise_fcev_buffer_20261014/``. Other retained dated reports preserve
scientific decisions and earlier comparisons. ``results/README.rst`` describes
retention; removed one-off scripts and tracked tables remain available at the
pre-cleanup Git revision ``862bc96``. Private ecoinvent/Brightway working databases
are not repository artifacts and are not required for native model use.

Regeneration and maintenance
----------------------------

Keep matching Python 3.12 source checkouts of utils, carculator, carculator_truck
and Premise. The selected recipe manifest is tracked in
``results/premise_vehicle_audit_20261012/candidate_recipes.csv``. Original names
and compatibility recipes are recovered from pinned Premise Git history by
``dev/premise_vehicle_baseline.py``, with byte-hash verification. The sibling
Premise checkout must contain revision
``a7c19af5251532ccccbc3d36f88504c0bbd2cc46``; a shallow checkout may need fetching.
Disposable ``parsed_inventories.json`` and ``summary.json`` files are no longer
inputs to the maintained generators.

From ``carculator_utils``, with source packages on ``PYTHONPATH``::

   python dev/regenerate_premise_cars.py --output /tmp/cars-new
   python dev/regenerate_premise_trucks.py --output /tmp/trucks-new

Use fresh output directories. These commands write candidates without modifying
installed Premise inventories or Brightway projects. The ``--reuse-raw`` option
is only for adapter checks using an explicitly retained, matching model export.
The workbook validators and final verification scripts are listed in
``dev/README.rst``. Rebuild saved Premise databases to apply installed inventory
changes; existing databases do not update themselves. No new package version,
release tag or package publication is created by this campaign closeout.
