Small FCEV truck motor calibration
==================================

14 October 2026. The user approved documented motor-only proxies of 57 kW
for the 3.5 t FCEV and 129 kW for the 7.5 t FCEV. The updated truck workbook
is installed in Premise. This step follows the
`electrical-supply correction <../premise_vehicle_fcev_dc_20261014/report.html>`_.

Diagnosis and scientific boundary
---------------------------------

The preceding 2020 Regional-delivery designs had shaft ratings of 51.207 and
93.990 kW, below peak shaft demands of 53.958 and 107.196 kW. The ratings came
from generic power-to-curb-mass factors of 25 and 24 W/kg, respectively. Their
metadata names car2db, but does not identify a validated FCEV motor. The
inherited calculation explicitly uses curb mass; this was not a mistaken
conversion of gross mass or fuel-cell electrical input.

An independent reconstruction from speed, acceleration, rolling resistance,
aerodynamic drag and gradient reproduces the shared wheel/shaft traces and
power deficits. The Regional-delivery peaks occur near 51 km/h while
accelerating at about 0.63 m/s2 on 5.2--5.4% grades. Motor/inverter and
fuel-cell losses affect upstream energy and electrical supply, not the
mechanical motor rating. Electrical auxiliaries bypass the traction motor.
``carculator_utils`` already respects these boundaries and preserves unmet
driving-cycle energy demand. Its equations required no correction. Four
additional regression cases protect this separation.

Approved references
-------------------

* `Renault, Master Z.E., 1 July 2020
  <https://www.renaultgroup.com/magazine/energies-et-motorisations/master-z-e/>`_
  documents a 57 kW motor. The related Master Z.E. Hydrogen was announced
  for 2020, but this step uses the documented electric-van motor only. It
  does not copy the hydrogen range extender or claim complete vehicle
  equivalence.
* `Daimler, FUSO eCanter, 31 March 2020
  <https://www.daimlertruck.com/newsroom/pressemitteilung/hello-dublin-der-fuso-ecanter-liefert-post-in-irland-45975414>`_
  documents a 129 kW maximum motor rating for the 7.49 t electric truck.
  Transferring this motor to the 7.5 t FCEV is an explicit powertrain proxy.

Neither reference validates the model's traction-buffer cell capability,
fuel-cell dynamics, complete-vehicle mass, or continuous operation at peak
motor output. The motor ratings are supported; those other assumptions
remain separate.

Implementation and observed changes
-----------------------------------

``carculator_truck`` accepts a ``rated power`` input in kW. A positive value
fixes shaft power independently of curb mass. Explicit constructor power
overrides take priority; zero or an absent parameter preserves the existing
mass-based calculation. The two approved ratings are supplied in the 2020
defaults and retained at the later native milestones, without assuming motor
downsizing. Other sizes and powertrains retain their previous defaults.

The existing bounded sizing loop propagates motor, inverter and fuel-cell
changes through mass, storage and consumption. The original electrical
fuel-cell/battery fractions and energy-sized truck buffers are retained.
No additional Premise runtime calculation is introduced.

.. list-table:: 2020 Regional delivery, default payload, Swiss climate
   :header-rows: 1

   * - Quantity
     - 3.5 t, before → updated
     - 7.5 t, before → updated
   * - Motor shaft rating, kW
     - 51.207 → 57.000
     - 93.990 → 129.000
   * - Peak shaft demand after mass feedback, kW
     - 53.958 → 54.077
     - 107.196 → 108.037
   * - Gross fuel-cell stack, kW
     - 13.556 → 15.037
     - 24.731 → 33.678
   * - Buffer electrical requirement, kW
     - 47.153 → 52.302
     - 86.022 → 117.142
   * - Nominal traction battery, kWh
     - 32.7266 → 32.7342
     - 39.1216 → 39.1766
   * - Complete battery pack, kg
     - 194.801 → 194.846
     - 232.867 → 233.194
   * - Curb mass, kg
     - 2048.290 → 2055.096
     - 3916.266 → 3963.278
   * - Hydrogen energy, kJ/vehicle-km
     - 1908.986 → 1910.124
     - 2868.242 → 2876.484

Hydrogen consumption rises 0.0596% and 0.2873%, respectively. Payload and the
400 km baseline design range are preserved. Both corrected motors meet the
selected Regional-delivery trace in native 2020 and 2050 checks. The unchanged
40 t control gives identical results. The separate 3.5 t Long-haul case still
needs 67.75 kW against its 57 kW rating; this calibration does not establish
feasibility for every cycle or payload. Long haul is not the selected Premise
template duty cycle.

Premise propagation and validation
----------------------------------

All 127 truck activity identities are retained. Numerical workbook changes
are confined to two transport services and their two production activities.
Comments contain the motor references, proxy scope, retained electrical
fractions and limitations. Existing model/publication provenance is retained.
The parameter companion and structured metadata record the declared ratings.
Traction-battery purchases still use the MIX capacity market, including the
existing replacement counts.

Full REMIND SSP2-NPi builds use encrypted IAM data and ecoinvent 3.12 cutoff:

.. list-table:: Full build checks
   :header-rows: 1

   * - Year
     - Activities
     - Validation errors
     - Warnings
     - Activities with changed coefficients
   * - 2020
     - 42,564
     - 0
     - 401, unchanged identities
     - 28
   * - 2050
     - 42,795
     - 0
     - 468, unchanged identities
     - 28

The changed activities are the two RER production datasets and two operating
services in each of thirteen IAM regions. RER transport forwarders retain
their coefficients. All other inventory coefficients are unchanged at relative
tolerance 1e-12 and absolute tolerance 1e-18. Premise code, IAM inputs,
transport mappings, fuel properties and other workbooks are held constant.

Per year, checks cover 726 operating services, 415 battery allocations,
578 fuel-energy/carbon cases and 221 BEV/PHEV designs; 50 forwarders are
excluded from direct-service accounting. There are no fuel-energy failures.
The corrected FCEV motor/stack/buffer manufacturing coefficients remain
identical between 2020 and 2050, as required by the retained FCEV hardware
policy. Efficiency changes still affect operating fuel use.

The isolated Brightway exports preserve metadata exactly and pass readback
checks of 968 operating-energy links per year. Persistent user project data
are untouched. There are 94 passing model/input/component tests and 106
passing Premise tests. Both small FCEVs also produce finite, nonzero native
LCIA results for 2020 and 2050. Wheel and sdist resource/hash checks and
offline installed-model smoke tests pass; full installed test suites and
cross-platform CI were not run in this step.

Incremental EF 3.1 comparison
-----------------------------

The immediately preceding FCEV electrical-sizing database is compared with
this motor update at identical 2020 REMIND SSP2-NPi settings. The four services
are the two sizes in RER and EUR, each with a functional unit of one tonne-km.
All sixteen headline EF 3.1 indicators are included: 64 paired scores.
This is not the final original-legacy-versus-refreshed comparison.

.. list-table:: Relative score changes, identical for RER and EUR here
   :header-rows: 1

   * - Size
     - Climate change
     - Largest increase: acidification
     - Range across all sixteen indicators
   * - 3.5 t
     - +0.264%
     - +1.812%
     - +0.206% to +1.812%
   * - 7.5 t
     - +0.920%
     - +6.026%
     - +0.757% to +6.026%

An independent transposed-technosphere solve reproduces each selected LCIA
score and closes its direct-exchange contribution balance. Production is then
decomposed separately. Fuel-cell stack and balance-of-plant manufacturing
explain 91.98% and 88.84% of the acidification increases for 3.5 t and 7.5 t,
respectively. The larger net electrical requirement raises stack ratings under
the retained 20% fuel-cell / 80% battery allocation. This provides a direct
inventory explanation for the largest changes. Increased hydrogen purchases
account for only 0.28% and 0.47% of those acidification increases.

For climate change, stack and balance-of-plant manufacturing account for
65.37% and 54.85% of the increases; additional hydrogen contributes 11.27%
and 16.52%. The remaining changes include motor/inverter manufacture,
road demand and other mass-dependent inputs. No unexplained numerical change
was identified in this step. This does not independently validate the inherited
fuel-cell allocation or manufacturing inventory. Manufacturing subcomponents
explain the vehicle-production contribution and must not be added to that
parent contribution a second time.

Reproduction
------------

Scripts are in ``dev/``:
``audit_small_fcev_motors.py``, ``regenerate_premise_trucks.py``,
``install_premise_small_fcev_motors.py``,
``build_premise_small_fcev_motors.py --year 2020`` (and 2050),
``audit_premise_small_fcev_motors.py``,
``audit_premise_vehicle_plausibility.py``,
``verify_small_fcev_hardware.py``,
``save_premise_small_fcev_motors.py``,
``compare_premise_small_fcev_motors.py`` and
``explain_premise_small_fcev_motors.py``.

The model audit accepts ``--baseline-parameters`` to reproduce the preceding
mass-based designs after installation of the new defaults. Its case label
``installed_defaults`` denotes that preceding baseline. Private model exports,
full databases and execution logs are under
``/private/tmp/premise-small-fcev-motors-20261014``. Public artifacts here retain
source hashes, aggregate results and relevant exchange comparisons; no full
ecoinvent database is distributed.

Targeted implementation commits: truck ``4d28ac6``, shared tests/adapter
``402b066`` and Premise inventories ``d8dec84``.
