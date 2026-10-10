Electricity supply over each vehicle's lifetime
===============================================

Default electricity mixes now use each vehicle and selected sample's own
operating lifetime. Previously, the inventory averaged lifetime kilometres
divided by annual kilometres across all vehicles and samples before calculating
one electricity mix. Adding another vehicle could therefore change an existing
vehicle's electricity supply and impacts without changing its physical inputs.

A controlled 2025 German Medium BEV example used 100,000 lifetime kilometres and
20,000 km/year. Adding a second sample with a 500,000 km lifetime changed the
first sample's climate impact from 0.28508 to 0.27085 kg CO2-eq/km before the
repair. The repaired calculation gives 0.28508 kg CO2-eq/km for that first sample
both alone and together. Mass, consumption and battery replacements are unchanged.
This demonstrates an accounting defect; these deliberately contrasting lifetimes
are not new default assumptions or calibration targets.

Calculation and compatibility
-----------------------------

* Lifetime is calculated separately for every size, powertrain, manufacturing
  year and sample. Active vehicles require a finite positive lifetime.
* Electricity shares are interpolated annually and averaged over the operating
  years. The existing whole-year convention is retained: fractional lifetime
  years are truncated. At least the manufacturing year's mix is used, including
  lifetimes below one year.
* Refreshed electricity scenarios average the complete operating lifetime,
  holding the final generation mix after 2070. Years before the first available
  background year use its first mix. ``electricity scenario="legacy"`` retains
  the previous convention of stopping the average at 2050. Inactive cells use
  a finite placeholder mix and do not contribute vehicle demand.
* An explicit ``background_configuration["custom electricity mix"]`` still
  overrides default lifetime averaging. Its year-by-technology array is applied
  to all selected vehicles and samples without modifying the supplied array.
  Shares retain the existing clipping and normalization convention; nonfinite
  mixes, zero totals and incorrect shapes raise error identifying the affected inputs.

The authoritative mixes are now available as a labelled array::

   inventory.electricity_mix.sel(
       combined_dim="Medium - BEV", year=2025, value=0
   )

Its dimensions are ``value, combined_dim, year, technology``. The older
``inventory.mix`` attribute remains a year-by-technology arithmetic summary for
reporting compatibility. That summary is not used to fill vehicle inventories.

Inventory, characterization and export
--------------------------------------

The change covers charging and electricity already substituted into fuel
production, including hydrogen and synthetic fuels. Vehicles needing different
mixes receive separate copies of the affected supply paths. Activities outside
those paths remain shared, as do vehicles with identical mixes. Additional
supplier names end with ``[for <size> - <powertrain>]``. Their non-electricity
exchanges, characterization factors and source metadata follow the originals.

Fuel-production electricity is identified by following nonzero inventory
exchanges upstream from the selected fuel, across all retained years and samples.
It is not identified from the numerical supply amounts returned by an LCA solve:
rounding can leave tiny residual amounts for completely disconnected activities.
Treating those residuals as links would incorrectly replace electricity in other
manufacturing processes, including batteries used in depot chargers. Such
manufacturing keeps its background electricity unless it is actually part of the
selected fuel's supply chain. Small but real exchanges are retained without an
arbitrary numerical cutoff.

LCIA solves the appropriate matrix for every selected sample and year instead
of reusing the first sample's upstream results. Export retains the corresponding
supply activities and electricity shares. SimaPro exchanges use the actual
exported product names for internal suppliers, including the additional supply
paths. Biomethane remains a fuel product even when its name mentions sewage
sludge. External supplier mappings are retained. Additional distinct supply paths
increase matrix size; use small selections of vehicles and years when exploring large vehicle grids.

The subsequent :doc:`electricity_scenarios` refresh supplies new historical and
projected generation mixes. The per-vehicle accounting repair described here
does not change generation factors, loss assumptions or vehicle calibration.
``static`` continues to select static background impact factors; it does not
freeze the separately supplied national electricity time series.

Verification
------------

``tests/test_lifetime_electricity.py`` checks analytical annual averages,
reordered sample labels, short lifetimes, the background horizon, unavailable
cells and explicit overrides. Completed car, bus, truck and two-wheeler runs in
2025/2030 compare individual samples with their results in a group. Additional
car cases cover multiple sizes, battery-electric, fuel-cell and methane vehicles,
and static/prospective backgrounds. Fuel-cell routing cases explicitly request
100% PEM-electrolysis hydrogen; the :ref:`default-hydrogen-supply` assumption
uses natural-gas reforming.

``tests/test_inventory_helpers.py`` also checks that electricity replacement
preserves unrelated activities, follows supply loops safely, retains very small
real exchanges, and finds fuel routes present only in later years or samples.
Truck charger tests compare the allocated LCIA contribution with an independent
matrix solve for both shared and differing operating-electricity mixes.

Repeated Brightway and SimaPro export checks inspect the separate electricity
markets and internal supplier links and preserve the original inventory and
LCIA results. CSV checks do not establish successful import into the SimaPro
application. This verification establishes numerical consistency, not empirical
validation of the bundled electricity forecasts.
