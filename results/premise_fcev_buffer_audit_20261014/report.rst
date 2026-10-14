FCEV truck battery power-envelope audit
==========================================

Status: source review and current-template screening complete; reference-pack
adoption awaits the user's scientific-assumption decision. No model default,
inventory workbook or Premise database has been changed by this audit.

Finding
----------

The current FCEV truck calculation has no traction-pack charge-power limit.
The shared energy model limits regenerative mechanical power by motor rating,
then applies generator and battery efficiencies. The truck sizes its final
battery from the inherited ``20 kWh + 6% of stored hydrogen energy`` rule.
Neither step establishes that the battery can accept the resulting power.

The inherited 0.15 kW/kg input is documented as lead-acid starter-battery
specific power. It is not evidence for the lithium-ion traction pack. Changing
only that input would not resolve the issue: truck storage sizing overwrites
the temporary power-sized FCEV battery from the parent method.

A shared correction is appropriate for optional battery charging constraints
and their energy accounting. Truck-specific reference specifications and
final capacity/mass sizing belong in ``carculator_truck``. Premise would import
the recalculated baseline and metadata; it needs no new driving-cycle solver.

What the current trace requires
----------------------------------

All seven installed 2020 FCEV templates were rebuilt using current sibling
sources, Swiss climate and Regional delivery. Nominal capacity, pack mass,
buffer power and fuel energy agree with the installed parameter companion.
An independent wheel-to-shaft-to-DC identity also passes for every trace.

Discharge below is the minimum battery assistance when the fuel cell can
instantaneously deliver its maximum net power. Charge is regenerative DC
output after allowing simultaneous vehicle DC demand to use it directly.
These are requirements, not measured battery capabilities.

.. list-table:: Current batteries and cycle requirements
   :header-rows: 1
   :widths: 12 15 16 20 20

   * - Truck
     - Nominal kWh
     - Pack kg
     - Peak discharge kW
     - Peak net charge kW
   * - 3.5 t
     - 32.73
     - 194.85
     - 49.05
     - 37.38
   * - 7.5 t
     - 39.18
     - 233.19
     - 93.85
     - 76.09
   * - 18 t
     - 51.32
     - 305.48
     - 69.99
     - 167.96
   * - 26 t
     - 57.91
     - 344.68
     - 64.12
     - 236.17
   * - 32 t
     - 68.18
     - 405.82
     - 173.51
     - 206.92
   * - 40 t
     - 71.14
     - 423.48
     - 140.90
     - 256.79
   * - 60 t
     - 88.61
     - 527.46
     - 135.44
     - 369.64

Reference and its limitations
--------------------------------

The candidate reference is the AKASOL AKASYSTEM 15 OEM 37 PRC. The
`earlier manufacturer brochure
<https://bus-news.com/wp-content/uploads/sites/4/2020/07/AKASOL-Bus-Applications-Brochure.pdf>`_
documents the product by 2020, at 24.5 kWh and about 238 kg.
It gives configuration-dependent continuous and peak power ranges but no
separate charging limits.

The `May 2021 manufacturer sheet
<https://www.act-news.com/wp-content/uploads/2020/11/210525_LowRes_AK_Datenblatt_AKASystem_15-OEM-37-PRC_2021_2159x2794mm_EN.pdf>`_
provides a coherent pack specification: 25 kWh, 238 kg including the contactor
box, 50 kW continuous RMS discharge, 150 kW discharge for 10 seconds, 36 kW
continuous charging, and 86 kW charging for 10 seconds. Ratings depend on SOC,
temperature and integration. Applying this edition to 2020 requires an
explicit proxy decision. The sheet does not establish NMC-622 stoichiometry,
internal cell mass fraction or the recovery interval for repeated pulses.

The audit scales this complete reference by nominal kWh, without claiming an
integer-module vehicle design. It does not combine its power limits with the
current 168 Wh/kg pack mass. At unchanged capacity, its 105 Wh/kg pack basis
would imply 677 kg for the 40 t vehicle, compared with the current 423 kg.
This is an alternative design, not proof that all lighter packs are invalid.

Sensitivity results
----------------------

At the existing nominal capacities, the 26 t, 40 t and 60 t net charging peaks
exceed even this reference's 10-second charging ceiling. Every truck's rated
buffer requirement and cycle discharge peak is below its scaled 10-second
discharge ceiling. The 7.5 t and 32 t traces exceed the continuous RMS rating
for up to 6 and 18 consecutive seconds respectively. A full-cycle RMS value
cannot certify their pulse/recovery behaviour: the datasheet does not define
an averaging interval. No automatic discharge-capability pass is assigned.

A conservative sensitivity clips regeneration at the continuous charging
limit, after allowing direct use by concurrent DC loads. It holds vehicle
mass, stack, capacity and the existing round-trip energy convention fixed.
The resulting increase in calculated hydrogen energy use is:

.. list-table:: Charging-limit sensitivity, fixed vehicle
   :header-rows: 1
   :widths: 25 35

   * - Truck
     - Energy-use increase
   * - 3.5 t
     - 0.00%
   * - 7.5 t
     - 0.22%
   * - 18 t
     - 1.85%
   * - 26 t
     - 4.81%
   * - 32 t
     - 4.53%
   * - 40 t
     - 5.82%
   * - 60 t
     - 10.33%

These are screening sensitivities, not corrected vehicle predictions or LCIA
results. A production change must also converge mass, fuel storage, payload
and sizing, preserve the requested speed trace, and check power again at the
new mass. In particular, heavier small trucks must still meet the cycle with
their recently approved fixed motor ratings.

The existing optimistic usable-energy bound remains only a lower bound.
It has no FC ramp dynamics or finite FC-to-battery charge power. The FCEV
defaults specify no usable SOC window, so nominal capacity alone cannot
certify charge-sustaining operation. The present audit does not reopen the
separately skipped PHEV replacement/cycling review.

Implementation and regression scope after the proxy decision
---------------------------------------------------------------

* In utils, impose the selected pack charge limit at the DC boundary, before
  storage losses. Account for concurrent auxiliary use and dissipated braking
  explicitly. Preserve the requested propulsion demand; report a discharge
  shortfall rather than clipping away its energy.
* In trucks, keep power requirements separate from battery capabilities and
  apply a coherent pack energy/mass/power profile. Respect explicit capacity
  overrides, converge mass/storage/load, and check sustained demand without
  treating a 10-second rating as indefinitely available.
* Update regenerative fuel credits and brake-wear credits consistently. Cover
  zero regeneration, binding/nonbinding charge limits, mixed powertrains,
  conversion losses, invalid active-vehicle inputs, and native truck cycles
  with independent energy-balance regressions. Inspect car/bus inheritance
  before enabling any shared hook.
* Retain Premise's approved MIX capacity-market treatment, reporting any
  physical mass mismatch. Rebuild 2020/2050, verify fuel/carbon and capacity
  links, and rerun the incremental EF comparison if the vehicles change.

Reproduction and evidence
----------------------------

Run ``dev/audit_fcev_battery_envelope.py --output OUTPUT`` using Python 3.12
and the matching sibling sources. It verifies current installed parameters
and writes the screening table, complete private traces, reference and source
manifest. The public evidence accompanying this report is
``envelope_screen.csv``, ``reference.json`` and ``manifest.json``.

No broad model test run is claimed: only the seven real model builds and
their independent audit assertions were executed for this read-only step.
No source PDF is redistributed here. This remains separate from the final
legacy-versus-refreshed 2020 EF 3.1 comparison, which is still outstanding.
