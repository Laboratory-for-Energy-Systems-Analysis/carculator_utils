2020 passenger-car PHEV pack recalibration
==========================================

14 October 2026. The approved capacity/mass references and explicit proxies
replace the previous generic 21.17--42.34 kWh packs. This report follows the
historical ``premise_car_phev_calibration_20261014`` audit. The accompanying
EF 3.1 comparison isolates this correction against the preceding
deterioration-corrected inventories; it is not the final comparison against
the original legacy vehicle workbooks.

Adopted pack assumptions
------------------------

.. csv-table:: Nominal capacity, complete pack mass and modelled electric range
   :header: "Class", "kWh", "kg", "Electric range, km", "Electric driving share"

   "Mini",8.8,120,56.5,0.293
   "Small",8.8,120,52.7,0.285
   "Lower medium",13,128.375,71.3,0.357
   "Medium",12,118.5,62.1,0.310
   "Large",12,118.5,57.1,0.294
   "Medium SUV",18.1,178.7375,85.1,0.413
   "Large SUV",24,226.8,95.5,0.439
   "Van",13.6,134.3,50.0,0.280

Petrol and diesel PHEVs share these class-specific assumptions. Mini/Small use
the Prius 8.8 kWh / 120 kg pack as an explicitly approved size proxy. Medium
uses BMW 330e 12 kWh / 118.5 kg, excluding mounting brackets. Lower medium
uses the Golf's 13 kWh nominal capacity; Large uses the 530e's 12 kWh;
Medium SUV uses the RAV4's 18.1 kWh; and Van uses the Tourneo Custom's
13.6 kWh. Their inferred masses use the 330e pack-level density. Large SUV
uses X5 24 kWh / 226.8 kg (500 lb), including mounting brackets. These
different source mass boundaries remain explicit. The unavailable Micro PHEV
inherits the Mini pack; no Micro PHEV is added to Premise's catalogue.

These are engineering and size proxies, not sales-weighted fleet averages or
replicas of complete manufacturer vehicles. In particular, the Tourneo's
series-hybrid architecture does not replace the model's powertrain. The RAV4
reference is a late-2020 vehicle. Other mode-specific components and control
assumptions remain those of carculator.

Manufacturer sources
--------------------

* `Toyota Prius Plug-in Hybrid release <https://newsroom.toyota.eu/toyota-prius-plug-in-hybrid/>`_:
  8.8 kWh and 120 kg.
* `BMW G20 PHEV technical training <https://bmwtechinfo.bmwgroup.com/tech_training_manual/ST1911%20G20%20PHEV%20Complete%20Vehicle.pdf>`_:
  SP41, 12 kWh nominal and 118.5 kg excluding retaining brackets.
* `Volkswagen 2020 Golf hybrid models <https://www.volkswagen-newsroom.com/en/golf-etsi-golf-ehybrid-and-golf-gte-international-media-drive-6336/the-new-golf-hybrid-models-6337>`_:
  13 kWh nominal.
* `BMW 530e battery update <https://www.press.bmwgroup.com/global/article/detail/T0299399EN/more-variety-more-electric-range-less-co2%3A-bmw-530e-sedan-with-the-latest-battery-cell-technology-and-also-with-optional-intelligent-all-wheel-drive>`_:
  12 kWh nominal.
* `Toyota RAV4 Plug-in Hybrid release <https://newsroom.toyota.eu/the-new-toyota-rav4-plug-in-hybrid/>`_:
  18.1 kWh.
* `BMW G05 PHEV technical training <https://bmwtechinfo.bmwgroup.com/tech_training_manual/ST2005%20G05%20PHEV%20Complete%20Vehicle.pdf>`_:
  SP44, 24 kWh nominal and 500 lb including retaining brackets.
* `Ford Transit and Tourneo Custom PHEV release <https://media.ford.com/content/fordmedia/feu/gb/en/news/2019/09/23/New-Ford-Transit-and-Tourneo-Custom-Plug-In-Hybrids-Deliver-Zero-Emission-Driving.html>`_:
  13.6 kWh.

The BMW tables were available through the search index of the original
manufacturer PDFs; the direct URLs returned 404 during this review. The
source-access limitation is recorded in the calibration manifest. Nominal
capacity is used throughout; manufacturer usable-capacity figures, including
market-dependent BMW values, are not substituted for nominal capacity.

Implementation and retained assumptions
---------------------------------------

Only 72 effective input cells change: 2020 PHEV pack mass and effective
NMC-622 cell density. ``input_scope.json`` records the boundary. A retained
70% cell mass fraction determines the effective cell density needed to match
both sourced nominal capacity and whole-pack mass. That fraction, the NMC-622
chemistry proxy, the electric-mode 80% usable-energy window and the inherited
uncertainty bounds are modelling assumptions, not manufacturer measurements.
The retained mass and density bounds are respectively +/-20% and +/-5%.

The electric-mode pack is copied into combustion operation during bounded
mass sizing, including explicit capacity or chemistry overrides. Both modes
therefore carry one physical battery. Conflicting overrides raise an error.
The modes retain their own operating assumptions: combustion operation
sustains charge, with zero net battery depletion. Copying the electric-mode
discharge window as well would spuriously add battery range to combustion
mode and under-purchase fuel. The regression suite caught that intermediate
implementation; it was corrected before the final installation and builds.
No hot/cold emissions coefficients were changed to compensate.

The 1.8 starts/day, 12,000 km/year, Swiss climate and existing electric
utility-factor curve are retained. All calibrated packs have zero modelled
lifetime replacements under the approved 200,000 vehicle-km / 18-year limits.
The inventory still purchases nominal capacity times one plus replacements,
independent of the electric driving share.

Fuel and electricity are recalculated, not merely edited in the workbook.
For the Medium petrol PHEV, nominal capacity falls from 30.576 to 12 kWh,
pack mass from 182 to 118.5 kg, electric range from about 155 to 62 km, and
electric share from about 61% to 31%. Its fuel energy rises by 79.2%.
Across the 16 PHEVs, fuel energy rises by 51.5--165.1% and purchased electricity
falls by 32.7--61.2%. These changes follow the smaller electric range and
existing utility-factor relationship, together with corrected mode masses.
They must not be interpreted as a measured real-world fuel economy claim.

The regenerated workbook retains all 162 activity identities. Numerical
changes are confined to the 16 PHEV operating datasets and their 16 vehicle
production datasets. All other template coefficients are unchanged within
relative tolerance 1e-12 and absolute tolerance 1e-18. Comments and structured
metadata preserve model publications, source records, approved proxies and
the existing HBEFA attribution.

Premise battery markets and future years
----------------------------------------

The complete car and truck traction packs use
``market for battery capacity (MIX scenario)`` in kWh. Both original
kilogram-based lithium-ion manufacture and its separate disposal exchange
are removed; the capacity market covers manufacture and end of life. The
physical pack mass still controls vehicle sizing. Its mass and chemistry can
differ from the MIX market's upstream manufacturing recipe, an explicitly
retained boundary. The market's internal kilogram inputs are expected.

The existing bus workbook uses MIX and chemistry-specific LTO capacity
markets, and the two-wheeler workbook uses MIX. Those workbooks have not been
regenerated in this step. Trucks' separate lead-acid starter batteries remain
kilogram-based; charging-station storage is separate from vehicle traction.

Future capacity uses the existing constant-range arithmetic: ``C = C0 * f``,
where ``f`` is the IAM-adjusted electric energy ratio before service-load
normalization. For calibrated PHEVs, density follows the relative original-
chemistry trend: ``d = d0 * d_NMC622(year) / d_NMC622(2020)``. Mass is
``M = M0 * f * d0 / d``. NMC-622's 0.24 to 0.26 kWh/kg projection therefore
improves each calibrated density by 8.33% by 2050, without resetting it to
generic BEV density. This is a prospective modelling assumption. BEVs, trucks
and metadata without the new relative-trend flag retain their existing
projection behavior. No vehicle-model solve is added to Premise runtime.

In REMIND SSP2-NPi EUR, the Medium petrol PHEV changes from 12 kWh / 118.5 kg
in 2020 to 9.6 kWh / 87.51 kg in 2050, preserving its modelled 62.09 km
electric range. This combines a 20% electric-energy reduction with the
relative density improvement.

Verification
------------

Thirty focused model/adapter tests pass, covering all approved packs,
multiple years/samples, overrides, repeated completion, fuel/grid energy
closure, capacity/replacement accounting and real model LCIA. The Premise
vehicle suite passes 299 tests with one passenger-car-specific skip for the
truck fixture. It covers installed capacities, source metadata, future
density/range, fuel-carbon alignment and independent hot/cold emissions.
One LPG test now allows floating-point round-trip precision between Excel
numbers and JSON metadata (relative tolerance 1e-14); LPG inventories are
unchanged.

The installed-artifact verifier passes for carculator_utils and carculator:
1,031 shared-library tests pass (363 sibling-dependent tests skipped because
the other vehicle packages are not installed in this isolated environment),
and all 88 car tests pass. Wheel/sdist resource hashes, dependency checks and
offline core-only model/LCIA checks pass. These are local macOS / Python 3.12
checks, not a claim about the full CI platform matrix. See ``verification.json``.

Full REMIND SSP2-NPi / ecoinvent 3.12 cutoff builds retain 42,564 activities
and 1,358,553 exchanges in 2020, and 42,795 activities and 1,363,087 exchanges
in 2050. Both have zero validation errors; the 401 and 468 warning identities
are unchanged from the immediately preceding update. Numerical changes are
confined to PHEVs: 88 services plus 16 production datasets in 2020, and
88 services plus 94 production datasets in 2050, including regional resized
production recipes. All other coefficients are unchanged at relative
tolerance 1e-12 and absolute tolerance 1e-18.

Independent checks cover 726 operating services, 415 battery allocations,
578 fuel-energy/carbon balances and 221 scenario battery designs per year,
with no fuel-energy failures. All 78 regional car PHEV designs per year
retain baseline electric range and the intended relative density trend.
Brightway readback confirms metadata for 965/1,186 activities in 2020/2050
and 968 operating-energy links per year. Private copies are used throughout;
the user's persistent Brightway project is unchanged.

Reproduction uses ``dev/regenerate_premise_cars.py``,
``dev/install_premise_vehicle_phev_calibration.py``,
``dev/build_premise_vehicle_battery.py`` for 2020 and 2050,
``dev/audit_premise_vehicle_plausibility.py``,
``dev/audit_premise_vehicle_phev_calibration.py`` and
``dev/compare_premise_phev_calibration.py``. The installation receipt and
generation sidecar retain source/artifact hashes. Proprietary full inventories
and Brightway copies remain in the private temporary workspace.

Model/data/tests commit: ``73c24ea`` (carculator). Premise runtime/inventory/
tests commit: ``b5ffa96``. The generation records pre-commit revisions plus
the exact changed source-file hashes; those hashes identify the executed
implementation.

Incremental EF 3.1 comparison
-----------------------------

The controlled 2020 comparison covers 16 RER PHEVs plus six EUR PHEVs across
16 EF 3.1 headline categories: 352 paired scores per vehicle-kilometre, without
weighting or normalization. RER forwarding activities can have the same score
as their EUR operating supplier; the labels do not imply independent regional
technologies. ``incremental_ef31.csv`` retains full method tuples and scores.

Climate impacts rise by 6.6--15.3%, while carcinogenic toxicity falls by
7.3--21.3%, non-carcinogenic toxicity by 10.6--25.4%, and metal/mineral
resource impacts by 5.2--12.2%. The Medium petrol PHEV in EUR changes from
0.24253 to 0.26999 kg CO2-eq/km (+11.3%). Smaller batteries reduce manufacture
and electricity use, while the lower electric driving share increases fuel
use. The largest category increases are land use (+34.9%) and marine
eutrophication (+26.7%) for the Large diesel PHEV; the largest reduction is
ionising radiation (-43.9%) for the Large petrol PHEV in EUR.

``dev/explain_premise_phev_calibration.py`` checks these four extreme cases
with independent transposed-matrix solves and exact exchange-contribution
closure (relative tolerance 2e-6). For the Large petrol PHEV, extra fossil
tailpipe CO2 (+0.06597 kg CO2-eq/km) and petrol supply (+0.02176) exceed the
reductions in electricity (-0.02976) and vehicle manufacture (-0.01840).
The diesel supply increase dominates the Large diesel PHEV's land-use and
marine-eutrophication changes. Reduced electricity supply dominates the
ionising-radiation decrease. Detailed signed contributions are in
``incremental_ef31_contributions.csv``. These large changes have identifiable
inventory causes; no additional unexplained variation is identified in these
four inspected cases. This does not validate the retained utility-factor
curve or all underlying background datasets independently.
