Methane leakage in vehicle inventories
======================================

Gas cars, buses and trucks use one shared calculation for the
``CNG pump-to-tank leakage`` parameter. Previously, buses and trucks increased
fuel purchases without adding the lost gas to direct emissions. Cars added the
loss entirely as fossil methane, including for non-fossil fuels. In addition,
the impact-result grouping omitted generic-air non-fossil methane.

Mass and carbon-origin accounting
---------------------------------

Let ``m`` be engine fuel in kg per vehicle-km, obtained from fuel consumption
times fuel density. The existing numerical convention is retained: ``r`` is
kg of additional gas lost per kg of engine fuel, not per kg purchased::

   lost = m * r
   purchased = m + lost
   purchased = engine fuel + fossil methane loss + non-fossil methane loss

Thus ``r=0.004`` adds 0.4% to fuel purchases. If a measured loss fraction ``f``
uses purchased fuel as its denominator, convert it first: ``r=f/(1-f)``.
The loss calculation treats the gas fuel as methane, retaining the existing
fuel approximation; it does not speciate impurities in natural gas.

The non-fossil fraction is the sum of each fuel component's mass share times
its ``biogenic share``. This respects explicit component overrides. For methane
synthesized with atmospheric CO2, that field is a non-fossil accounting flag,
not a claim of physical biogenic origin. Both fossil and non-fossil methane
enter ``direct - non-exhaust`` impacts and inventory exports.

Combustion CO2 remains based on engine fuel; leaked gas is not also burned.
HBEFA exhaust methane uses separate air compartments and is unchanged by this
repair. The shared method owns only the gas transport's fuel purchase and
generic-air methane-leakage rows. Calling it repeatedly does not multiply the
loss allowance or add duplicate emissions. Active gas vehicles require a finite,
nonnegative loss ratio; invalid inputs raise with sample, vehicle and year.

Supplier boundary and the 0.4% default
--------------------------------------

The corrected calculation represents **additional loss after the selected
supplier's output boundary**. Production, distribution and station emissions
already contained in that supplier must not be entered again in this parameter.
The upstream datasets are left unchanged: this patch cannot reliably separate
loss stages hidden inside pre-characterized background activities.

The additional-loss default is now **zero at all native years** in cars, buses
and trucks. This excludes an unqualified residual overlay beyond the delivered-fuel
supplier; it does not assert zero physical leakage. The historical 0.004 prior
and its uncertainty bounds are archived in each package. Its cited source is
`Speirs et al. (2020), Table 1
<https://strathprints.strath.ac.uk/87891/1/Speirs-etal-PE-2020-Natural-gas-fuel-and-greenhouse-gas-emissions-in-trucks-and-ships.pdf>`_.
That table combines delivery, station storage, vehicle tank and manual venting
losses, and includes LNG boil-off. It does **not** independently establish a
0.4% residual loss after a CNG supplier's output boundary, or validate its use
for passenger cars, buses or every gas supply route. The old parameter-record
comments describe that broader source boundary; they are not a specification
of which losses can safely be added to a particular inventory.

The bundled sewage-biomethane fuelling activity already includes station
methane emissions and a 2% extra production allowance for distribution. The
biological synthetic-methane delivery recipe inherits those delivery proxies.
Consequently, adding the historical 0.4% assumption did not establish absence
of overlap. The 2% production allowance is not an explicit 2% methane emission
and is not subtracted from the leakage parameter. Fossil-gas background factors
also do not expose a separable station-loss inventory here.

For a study, specify only a defensible residual loss after the selected
supplier. If the supplier already includes all relevant losses, set the
additional parameter to zero before constructing the model::

   array.loc[dict(parameter="CNG pump-to-tank leakage", powertrain="ICEV-g")] = 0

Zero disables only this additional loss, retaining upstream supplier emissions
and HBEFA exhaust emissions. No automatic upstream credit or removal of methane
emissions is applied. The default now follows this no-overlay boundary. A measured
post-supplier residual can still be supplied explicitly; route-specific leakage
measurement remains an evidence gap. The zero default is not an empirical
calibration, and studies needing whole-chain leakage sensitivity should vary
the appropriate upstream stages rather than add their total again here.

Verification
-------------

``tests/test_methane_leakage.py`` covers hand-calculated mass balances, two sizes,
reordered years and samples, zero leakage, invalid rates and origin fractions,
explicit origin overrides, unavailable vehicles, and repeat calls.

Completed model/LCIA regressions use Medium cars, 13m-city buses and 40t long-haul
trucks, gas/diesel/BEV powertrains, 2020/2025/2030, and two samples. They test
fossil gas, sewage biomethane, biological synthetic methane and mixtures, under
both ReCiPe and EF. Independent climate expectations use 29.8 kg CO2-eq/kg fossil
methane and 27 kg CO2-eq/kg non-fossil methane in the bundled climate categories.
They verify that only the intended gas-vehicle exchanges change and that the
upstream matrices, combustion CO2 and exhaust pollutants remain unchanged.
Repeated three-year Brightway exports preserve quantities and the original
inventory. No Brightway database is written.

Historical completed 2025 runs with 100% sewage biomethane and an explicit 0.004 loss ratio
give the following additional leakage. These are model results, not measurements.
Fossil leakage is zero in each case; the climate contribution shown uses the
bundled non-fossil methane factor of 27 kg CO2-eq/kg.

.. list-table:: Additional non-fossil leakage per vehicle-km
   :header-rows: 1

   * - Vehicle
     - Methane (g/km)
     - Climate contribution (g CO2-eq/km)
   * - Medium car
     - 0.171
     - 4.61
   * - 13m-city bus
     - 1.160
     - 31.31
   * - 40t long-haul truck
     - 0.986
     - 26.61

The earlier car inventory assigned its loss to fossil methane. The earlier
bus/truck inventories omitted this direct methane contribution entirely.

Run with matching sibling packages and export extras installed::

   CARCULATOR_REQUIRE_FAMILY=1 python -m pytest tests/test_methane_leakage.py tests/test_fuel_blend_inventory.py tests/test_biological_methane.py
