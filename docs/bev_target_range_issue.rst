BEV target-range and chemistry reproduction
===========================================

The reported issue is reproducible on the current passenger-car implementation:
setting a common target range gives different battery masses but the same energy
consumption and required capacity across chemistries. This is a sizing-order
defect; it has not been repaired by this reproduction.

Sixteen complete ``CarModel.set_all()`` runs cover Medium BEVs on WLTC, four
chemistries, 2020 and 2025, and either default sizing or a 400 km target. For
2025 with the target enabled, the outputs are:

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

Grid electricity consumption is likewise identical, at 16.95 kWh/100 km.
Capacity equality is to floating-point rounding; energy consumption is exactly
equal in these runs. The same behaviour occurs for 2020.

Cause and consistency check
---------------------------

``CarModel.set_all()`` converges vehicle mass and calculates energy demand
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

A repair needs to iterate vehicle mass, energy demand and range-driven battery
capacity together until each vehicle/sample converges, before calculating
downstream costs, replacements and emissions. Changing battery chemistry data
alone does not address the ordering defect.

Reproduce
---------

With matching car and shared packages installed::

   python scripts/reproduce_bev_target_range.py --output /tmp/bev-range.json

The script records the mass actually passed to the driving-energy calculation,
completed model outputs and the frozen-vehicle recalculation, without modifying
the model implementation. Source hashes and all 16 runs are preserved in the
:download:`recorded results <_static/bev_target_range_reproduction.json>`.
