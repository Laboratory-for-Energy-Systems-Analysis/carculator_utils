2020 passenger-car PHEV battery calibration review
==================================================

14 October 2026. This is an investigation and a calibration decision record.
Model defaults, inventories and Brightway databases are unchanged. The latest
installed baseline remains the hybrid-deterioration update.

Finding
-------

The 2020 PHEV capacities are arithmetically consistent but poorly supported as
representative contemporary specifications. The model multiplies a pack mass
of 126--252 kg by a 0.7 cell fraction and 0.24 kWh/kg NMC-622 cell density:
the resulting nominal pack density is 168 Wh/kg. It retains that full capacity
in both final petrol and diesel PHEV inventories, as intended.

The source pack masses were already present in the inspected December 2023
revision ``bf2abf2`` and remain unchanged in the inspected 2024 revisions and
current source. They were not introduced by the recent accounting repairs.
The generic 2020 cell-density input is 0.20 kWh/kg, but the chemistry selection
deliberately replaces it with 0.24 kWh/kg. Reverting that selection alone would
only reduce capacity by one sixth, to 17.64--35.28 kWh; it would not resolve
the source-calibration concern and would change the established chemistry
contract.

.. csv-table:: Fresh model outputs, common to petrol and diesel PHEVs
   :header: "Size", "Nominal kWh", "Pack kg", "Electric range km", "Electric distance share"

   "Mini",21.168,126,135.70,0.549
   "Small",21.168,126,126.53,0.520
   "Lower medium",25.872,154,140.85,0.565
   "Medium",30.576,182,155.23,0.610
   "Large",42.336,252,194.19,0.732
   "Medium SUV",42.336,252,195.22,0.735
   "Large SUV",42.336,252,167.45,0.648
   "Van",42.336,252,152.08,0.600

Ranges are modelled electric-mode distances with an 80% usable-energy window,
the default car cycle and Swiss climate. They are not manufacturer test
results. Changing capacity changes the electric distance share selected by the
existing utility-factor relationship and therefore changes both electricity
and combustion-fuel purchases. The existing Premise future-year rule preserves
the baseline electric range; it cannot repair an inappropriate 2020 baseline.

Source checks
-------------

The input records cite Toyota manufacturer data and the ICCT September 2020
report, without a per-size derivation. The ICCT full-text endpoints returned
HTTP 403 during this review; the cited report was not independently verified
as a source of these pack masses. No missing derivation has been reconstructed
by assumption.

The following primary manufacturer examples establish useful benchmarks, but
not sales-weighted fleet averages or a complete segment calibration. Nominal
or gross capacities are compared with model nominal capacity; range and
weighted official fuel consumption are not used to infer battery capacity.

* `Toyota Prius Plug-in, 2017 generation <https://newsroom.toyota.eu/toyota-prius-plug-in-hybrid/>`_:
  8.8 kWh and 120 kg, equivalent to 73.33 Wh/kg at pack level. This is a
  contemporary reference, not a native Mini or Small segment vehicle.
* `Volkswagen Golf Mk8 eHybrid/GTE, 2020 <https://www.volkswagen-newsroom.com/en/golf-etsi-golf-ehybrid-and-golf-gte-international-media-drive-6336/the-new-golf-hybrid-models-6337>`_:
  13 kWh; the Lower medium template has 25.87 kWh.
* `BMW 330e, 2019 introduction <https://www.press.bmwgroup.com/global/article/detail/T0298940EN/sportier-and-more-efficient-than-ever-thanks-to-the-latest-bmw-edrive-technology%3A-the-new-bmw-330e-sedan-celebrates-its-market-launch?language=en>`_:
  12 kWh gross; the Medium template has 30.58 kWh.
* `BMW 530e, 2019 battery update <https://www.press.bmwgroup.com/global/article/detail/T0299399EN/more-variety-more-electric-range-less-co2%3A-bmw-530e-sedan-with-the-latest-battery-cell-technology-and-also-with-optional-intelligent-all-wheel-drive>`_:
  12 kWh gross; the Large template has 42.34 kWh.
* `Toyota RAV4 Plug-in, September 2020 <https://newsroom.toyota.eu/the-new-toyota-rav4-plug-in-hybrid/>`_:
  18.1 kWh; the Medium SUV template has 42.34 kWh. Its late-2020 introduction
  must be disclosed if used to represent a whole year.
* `BMW X5 xDrive45e, February 2020 <https://www.press.bmwgroup.com/slovenia/article/detail/T0300315EN/electrifying-power-for-supreme-driving-pleasure-market-launch-of-the-new-bmw-x5-xdrive45e>`_:
  24 kWh gross; the Large SUV template has 42.34 kWh.
* `Ford Tourneo Custom PHEV, 2019 introduction <https://media.ford.com/content/fordmedia/feu/gb/en/news/2019/09/23/New-Ford-Transit-and-Tourneo-Custom-Plug-In-Hybrids-Deliver-Zero-Emission-Driving.html>`_:
  13.6 kWh; the passenger Van template has 42.34 kWh. This is a series hybrid,
  so using its battery as a proxy would not make the model a vehicle replica.

Mass must be calibrated together with capacity. For example, applying an
8.8 kWh override while retaining the present 168 Wh/kg pack density produces
52.38 kg, less than half the documented Prius pack mass. A capacity-only
correction would consequently introduce another physical discrepancy.

Driving-mode consistency
------------------------

The same nominal PHEV currently uses different packs in its electric and
combustion intermediates. The electric-mode pack is 126--252 kg; the
combustion-mode pack is 60--100 kg. For Medium, these are 182 kg/30.576 kWh and
80 kg/13.440 kWh respectively. Final assembly retains the full electric-mode
pack, but the mode-specific energy simulations and the utility-weighted curb
mass were calculated with different packs.

The battery term in the weighted mode masses is 29.76--60.76 kg below the
full pack retained in final assembly. This is a battery-component comparison,
not a complete corrected curb-mass estimate: other mode-specific components
also require a consistent accounting boundary. The review records this as
an additional implementation concern to resolve when applying the selected
pack calibration. It does not justify changing battery capacity independently
of mass and rerunning neither mode.

Calibration choice pending
--------------------------

The recommended approach is to establish capacity and pack mass together from
documented vehicles available around 2020, by size. Mini/Small and any missing
diesel-PHEV equivalents require explicit proxies. The examples above are
candidate anchors, not approved class averages or adopted parameter values.
Matched mass evidence is still needed for most examples. Documented gross
and usable capacity must remain separate, and absent mass data must not be
filled with an unlabelled BEV-density assumption.

A simpler alternative is the explicitly common Prius pack-density proxy:
retain the existing size-dependent pack masses and apply 8.8/120 kWh/kg.
This gives 9.24, 11.29, 13.35 and 18.48 kWh for the four mass groups.
At unchanged electric-mode energy demand the resulting ranges are 55.23--85.22
km. These are arithmetic sensitivities only. They are not completed model
runs, revised utility factors, evidence for all sizes, or a validation of the
existing pack masses. The capacity-and-mass choice has been sent to the user;
neither alternative has been installed.

Implementation after the choice should preserve one physical pack across
driving modes; recompute vehicle mass, energy, utility factor, costs and
replacement accounting; disclose any physical-pack/MIX-market mismatch; and
regenerate the car workbook and provenance. The agreed Premise future rule
remains simple and adds no model execution at runtime. Density projections
must represent relative improvements from the selected PHEV baseline, without
resetting it to an incompatible absolute BEV pack density.

Verification and reproduction
-----------------------------

The audit ran with Python 3.12.13, NumPy 1.26.4 and matching local car/shared
sources. All 16 petrol/diesel templates satisfy capacity = pack mass times
cell fraction times cell density, retain the full electric-mode capacity,
and agree with the installed parameter companions. This verifies accounting,
not source representativeness. Nine existing PHEV capacity/replacement tests
passed; no new test locks the questionable defaults in place.

Run from the shared repository with the matched model environment::

   python dev/audit_premise_car_phev_calibration.py \
     --output results/premise_car_phev_calibration_20261014
   PYTHONPATH=../carculator:../carculator_truck:. python -m pytest \
     tests/test_phev_capacity.py tests/test_phev_replacements.py -q

``current_specs.csv`` records the numerical audit and labelled sensitivity;
``manufacturer_benchmarks.csv`` records source URLs and comparison boundaries;
``input_records.json`` preserves the relevant parameter provenance;
``input_history.json`` records the inspected historical masses; and
``checks.json`` records input/script hashes and current verification status.
Full scenario builds and EF 3.1 comparisons were not repeated because no
model or inventory coefficients changed. Calibration and driving-mode mass
consistency remain open.
