BEV target-range and chemistry sizing
=====================================

The passenger-car target-range sizing defect has been repaired. Battery mass,
vehicle mass, power and energy demand now converge together before replacements,
costs and emissions are calculated. Chemistry can therefore affect both energy
consumption and the capacity needed to reach a given range.

Repaired results
----------------

Sixteen complete ``CarModel.set_all()`` runs cover Medium BEVs on WLTC, four
chemistries, 2020 and 2025, and either default sizing or a 400 km target. With
the repair, the 2025 target-range runs give:

.. list-table:: Medium BEV, 2025, WLTC, 400 km target after repair
   :header-rows: 1

   * - Chemistry
     - Battery pack mass (kg)
     - Nominal capacity (kWh)
     - Battery energy (kWh/100 km)
     - Grid electricity (kWh/100 km)
   * - LFP
     - 559.3
     - 78.45
     - 15.69
     - 17.70
   * - NMC-111
     - 609.1
     - 79.48
     - 15.90
     - 17.93
   * - NMC-622
     - 436.1
     - 75.88
     - 15.18
     - 17.12
   * - NMC-811
     - 352.7
     - 74.15
     - 14.83
     - 16.73

All eight target-range runs, including 2020, remain at 400 km within a relative
tolerance of ``1e-5`` when energy is independently recalculated at the completed
vehicle's mass. The eight default runs without a target retain the recorded
baseline outputs. These are internal consistency checks, not independent
measurements of real vehicles.

Sizing and override rules
-------------------------

Nominal capacity is target distance multiplied by battery stored-energy demand,
divided by usable depth of discharge. Pack mass follows from cell energy density
and the cell fraction of pack mass. The mass and power calculation then feeds
back into cycle energy demand. Both driving mass and battery pack mass must
converge for every year and sample, with the existing bounded iteration limit.

Recuperation retains its input assumption throughout sizing; the cycle-average
transmission efficiency written by an energy calculation is not recycled as a
new input assumption. The shared range helper modifies only the selected BEVs,
preserving unrelated vehicles and their battery properties.

* A target range takes precedence over a capacity override for the same BEV,
  as before. Capacity overrides for other vehicles remain effective.
* Without a target range, the default pack-mass or explicit capacity workflow
  remains in use. Battery chemistry alone need not change consumption when
  total vehicle mass remains the same.
* A fixed curb mass can legitimately give equal consumption across chemistries:
  the glider adjustment absorbs battery mass differences. An explicit energy
  consumption override also remains fixed. Equal nominal capacity in these
  cases is expected when range and usable depth of discharge are equal.

The passenger-car regression tests exercise all four chemistries, two years,
two load samples, fixed mass and consumption, capacity precedence, mixed
powertrains, inactive targets and the iteration limit. Fresh fixed-capacity
runs independently recover the range-sized solution. Completed inventories
check grid electricity and chemistry-specific battery exchanges, and calculate
finite life cycle impacts.

The initial range-repair verification passed 485 Python 3.12 source-checkout tests
across all five packages
(322 shared, 61 car, 54 truck, 30 bus and 18 two-wheeler), with one existing
expected failure. Both shared and passenger-car Sphinx builds succeeded. This
is local verification, not a new installed-artifact or cross-platform CI report.

Capacity and pack-mass inputs
-----------------------------

The reverse sizing directions have also been checked on completed passenger-car
runs. For each of LFP, NMC-111, NMC-622 and NMC-811, the tests vary either nominal
capacity (40, 60 and 80 kWh) or the input ``energy battery mass`` (250, 400 and
550 kg). Each run covers 2020 and 2025, with static load and an additional
300 kg cargo sample: 24 model runs and 96 vehicle/year/sample cells. There is
no fixed target range, curb mass or consumption in these sweeps.

In every tested sequence, increasing capacity increases pack mass, driving mass,
energy consumption and range. Increasing pack mass increases nominal capacity,
driving mass, consumption and range. The range increase is less than proportional
to capacity because moving the heavier vehicle requires more energy per kilometre.
Recalculating energy at final mass confirms the reported range; battery component
mass balance and capacity accounting hold within numerical tolerance. All 24
completed inventories use the corresponding charging demand and chemistry-specific
pack mass, and produce finite life cycle impacts.

.. list-table:: Medium BEV, NMC-811, 2025, WLTC, static load
   :header-rows: 1

   * - Input changed
     - Pack mass (kg)
     - Nominal capacity (kWh)
     - Range (km)
     - Grid electricity (kWh/100 km)
   * - Capacity: 40 kWh
     - 190.2
     - 40.00
     - 226.1
     - 15.97
   * - Capacity: 60 kWh
     - 285.4
     - 60.00
     - 329.9
     - 16.41
   * - Capacity: 80 kWh
     - 380.5
     - 80.00
     - 428.2
     - 16.86
   * - Pack mass: 250 kg
     - 250.0
     - 52.56
     - 291.9
     - 16.25
   * - Pack mass: 400 kg
     - 400.0
     - 84.10
     - 447.7
     - 16.95
   * - Pack mass: 550 kg
     - 550.0
     - 115.64
     - 591.1
     - 17.66

These input directions already propagated correctly for standalone BEVs. The
follow-up exposed and repaired a mixed-vehicle side effect: a capacity override
recalculated battery component masses for unrelated vehicles, altering an FCEV's
cell/pack split. Capacity and range overrides now share a helper that updates only
their selected cells. A regression reproduces the original failure and confirms
that other powertrains and unselected years retain their battery properties.

Use ``energy_storage["capacity"]`` to set nominal kWh. To set pack mass, change
``energy battery mass`` in the input array, in kg including balance of plant,
before constructing a fresh model. ``electric energy stored`` and ``battery cell
mass`` are derived outputs and should not be used as substitutes for these inputs.
A capacity override takes precedence over input pack mass; a target range takes
precedence over both. Fixed curb mass or consumption can intentionally suppress
the consumption response, as described above.

All results and input/source provenance are available in the
:download:`capacity and mass sweeps <_static/bev_battery_input_sweeps.json>`.
The regression cases are in ``carculator/tests/test_bev_target_range.py``.

After this follow-up, all five source-checkout suites passed: 323 shared,
72 passenger-car, 54 truck, 30 bus and 18 two-wheeler tests (497 total), plus
one existing expected failure. Shared and passenger-car documentation builds
also succeeded, with existing API/documentation warnings.

Original defect
---------------

Before repair, setting a common target range gave different battery masses but
the same energy consumption and required capacity across chemistries. The 2025
outputs were:

.. list-table:: Medium BEV, 2025, WLTC, 400 km target
   :header-rows: 1

   * - Chemistry
     - Battery pack mass (kg)
     - Nominal capacity (kWh)
     - Battery energy (kWh/100 km)
   * - LFP
     - 535.7
     - 75.13
     - 15.03
   * - NMC-111
     - 575.7
     - 75.13
     - 15.03
   * - NMC-622
     - 431.8
     - 75.13
     - 15.03
   * - NMC-811
     - 357.4
     - 75.13
     - 15.03

Grid electricity consumption was likewise identical, at 16.95 kWh/100 km.
Capacity equality is to floating-point rounding; energy consumption is exactly
equal in these runs. The same behaviour occurred for 2020.

Cause and consistency check
---------------------------

The original ``CarModel.set_all()`` converged vehicle mass and calculated energy demand
before applying ``override_range()``. The default pack mass is 400 kg for all
four chemistries in this scope, so the initial driving masses and energy demands
are equal. The range override then computes capacity from that already-calculated
energy demand and changes battery mass using chemistry-specific energy density
and cell/pack mass share. Vehicle mass is updated later, but energy demand is
not recalculated at that new mass.

Instrumentation confirms that all four 2025 energy calculations use a driving
mass of 1,896.24 kg. The final reported driving masses instead range from
1,853.60 kg for NMC-811 to 2,071.98 kg for NMC-111. Thus the reported 400 km
range is based on stale energy consumption.

Recalculating energy once at the final reported vehicle mass, without resizing
the battery, gives ranges of 386.50 km (LFP), 382.69 km (NMC-111), 396.75 km
(NMC-622) and 404.44 km (NMC-811). This is a diagnostic on a frozen vehicle,
not a converged sizing solution or a recommended workaround. The default runs
without a range override remain consistent to the sizing tolerance.

Reproduce
---------

With matching car and shared packages installed::

   python scripts/reproduce_bev_target_range.py --output /tmp/bev-range.json

The script records the mass actually passed to the driving-energy calculation,
completed model outputs and the frozen-vehicle recalculation, without modifying
the model implementation. Source hashes and all 16 runs are preserved in the
:download:`original results <_static/bev_target_range_reproduction.json>` and
:download:`repaired results <_static/bev_target_range_repaired.json>`.
