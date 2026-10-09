.. _validity:

Shared-model validation
=======================

``carculator_utils`` provides shared physics, parameter handling and inventory
machinery; vehicle-specific calibration belongs to the four vehicle packages.
A passing software test and agreement with a measured vehicle answer different
questions. The current evidence review separates analytical conservation tests,
numerical convergence, fitted assumptions, held-out observations and screening
comparisons with imperfectly matched cycles or meter boundaries.

Current evidence
----------------

* :doc:`bev_target_range_issue` records the passenger-car range-sizing repair:
  battery mass and energy demand now converge together. Sixteen completed runs
  preserve the original reproduction and the repaired consistency checks.
  Capacity and pack-mass sweeps additionally verify both input directions
  through completed inventories across 96 vehicle/year/sample cells.
* :doc:`hot_emission_audit` records 132 completed vehicle cases and repairs to
  pollutant mapping, speciation, energy-boundary and deterioration accounting;
  all 34,518 scalar checks pass after repair.
* :doc:`energy_model_repairs` describes adopted accounting repairs and priors.
* :doc:`energy_measurements` records 40 model runs, 41 paired observations and
  77 exclusions. It distinguishes charging AC, battery-terminal DC and unknown
  electrical boundaries.
* :doc:`temporal_energy` preserves the 2025 anchors and checks 546 annual cases,
  including availability-masked historical cells. It is a temporal regression
  audit, not 546 independent empirical validations.
* :doc:`adac_cycle_comparison`, :doc:`truck_energy_diagnostics` and
  :doc:`petrol_car_energy_diagnostics` retain the vehicle-specific diagnostic
  evidence and limits. Two-wheelers have no new independent measured calibration
  in that catalog.

The analytical tests cover shaft/input energy, road load, regenerative recovery,
auxiliary losses, explicit overrides and battery boundaries.
:doc:`temporal_energy` retains the historical
audit runtime and inputs. Empirical residuals remain conditional on source quality
and matched test settings; no fixed error threshold substitutes for physics.

Sample identity checks
----------------------

The per-vehicle/sample electricity-supply repair and independent-versus-grouped
calculation checks are documented in :doc:`electricity_lifetime`.

``tests/test_sample_labels.py`` checks retained and reordered samples through
completed car, bus, truck and two-wheeler models and inventories in 2025/2030.
LCIA coordinates keep the actual sample labels, and reordering already completed
samples reorders their characterized results. Selecting sample 1 before sizing
gives the same physical outputs, inventory and impacts as relabelling that same
input draw to zero. Reordered sensitivity runs normalize to the named reference.

Repeated Brightway and SimaPro exports cover one retained numeric or named
sample, both years, and passenger-/tonne-kilometre normalization. Checks compare
Brightway energy inputs to consumption divided by load, verify vehicle comments,
and preserve the original arrays, indices and calculated impacts. SimaPro checks
parse the serialized CSV and compare each vehicle's comment with its Brightway
metadata, including manufacture year and the selected sample's parameters.
``tests/test_export.py`` additionally checks activity metadata precedence,
catalog fallback, missing sources, and file/string serialization of comments
containing semicolons, quotes, line breaks and Unicode.
These checks cover the exported CSV, not supplier linking or import into the
SimaPro application. Multi-sample exports remain unsupported and fail with
selection instructions. These are software consistency checks, not additional
empirical calibration.

Driving-cycle checks
--------------------

Use the shared public cycle loader rather than importing removed car modules.
For a one-second speed trace, metres/second summed over time gives metres;
divide by 1,000 to report kilometres::

   import numpy as np
   from carculator_utils.driving_cycles import get_standard_driving_cycle_and_gradient

   speed_kmh, gradient = get_standard_driving_cycle_and_gradient(
       "car", ["Medium"], "WLTC"
   )
   active = np.isfinite(speed_kmh[:, 0])
   velocity_ms = speed_kmh[active, 0] / 3.6
   distance_km = velocity_ms.sum() / 1000
   duration_seconds = len(velocity_ms)

Named cycles can contain storage padding; use their documented active-duration
contract, not the stored array length. Custom cycles include all supplied
samples, including terminal stops. Rate/grade provenance and power-feasibility
checks remain necessary for measured-route comparisons.

.. _cabin-temperature-limitation:

Bus cabin-temperature limitation
--------------------------------

The empirical HVAC model now explicitly supports only its existing 20-degree
Celsius cabin assumption. Changing ``indoor_temperature`` previously moved an
unchanged load between heating and cooling; the parameter did not adjust the
load to maintain a different cabin temperature. In a completed 2025 13m-city
depot-BEV check at 0 degrees Celsius outside, cabin settings of 15, 20 and 25
degrees all gave the same 121.25 kWh/100 km charging electricity. Such results
do not support comparisons of thermostat settings.

Omit ``indoor_temperature``, pass ``20``, or supply twelve monthly values all
equal to ``20``. Other settings now raise ``ValueError`` before sizing, including
when using ``EnergyConsumptionModel`` directly. The HVAC calculation also
checks later changes to that attribute. Existing studies with non-default
cabin settings need to reconsider that assumption; the model cannot quantify
their requested thermostat effect.

This restriction preserves the existing ambient-temperature curve and its
limitations. HVAC demand continues to vary with outside temperature, and
scalar/monthly ``ambient_temperature`` overrides remain supported. It introduces
neither a cabin heat-balance model nor new calibration data.

``tests/test_cabin_temperature.py`` checks early errors, direct energy-model
calls, later attribute changes and the existing heating/cooling loads. Completed
13m-city diesel, fuel-cell and depot-BEV runs cover reordered 2020/2025/2030
years, two load samples, country temperatures and ambient overrides. Default
and explicit all-20-degree settings agree through sizing, inventories and LCIA.

.. _temperature-fallback-checks:

Bus temperature fallback
------------------------

Bus HVAC reads the selected country's bundled monthly temperature series unless
``ambient_temperature`` is supplied explicitly. Missing countries use the
Swiss series with a printed notice. Previously, that fallback parsed the Swiss
decimal values as integers and raised ``ValueError`` on the first value,
``1.9``. The corrected lookup uses floating-point parsing on both paths.

The bundled table currently lacks ``BR``, ``US``, ``CA``, ``IN`` and ``AU``.
``tests/test_temperature_fallback.py`` covers these codes, an unknown-country
control, and positive/negative decimal temperatures. Completed 13m-city bus
checks in all five countries compare the default fallback with the same Swiss
temperatures supplied explicitly. They cover diesel, fuel-cell and depot BEV
powertrains, reordered 2025/2030 years and two passenger-load samples, through
vehicle sizing, fuel/charging exchanges and LCIA. Scalar and twelve-month
overrides bypass the country lookup and retain caller data.

This repair preserves the existing Swiss fallback, bundled climate data and
HVAC assumptions. It restores runnable cases; it does not establish that a
Swiss temperature series represents conditions in the requested country.
For location-specific work, use the temperature inputs described in
:doc:`input_validation`. The other vehicle families retain their separate
annual thermal-demand inputs.

.. _default-biofuel-shares:

Default biofuel shares
----------------------

Default blends now preserve the supplied fractions in the bundled country data.
The shared interpolation previously clipped every biofuel share to 30%, including
historical values and interpolation within the supplied years. The repair uses
0--100% bounds for bioethanol, biodiesel and biomethane, retaining the existing
linear interpolation/extrapolation and requested year order.

``data/fuel/share_bio_cng.csv`` supplies these fractions at both 2018 and 2050;
the corresponding interpolated 2025 defaults are therefore the same:

.. list-table:: Bundled biomethane mass shares
   :header-rows: 1

   * - Country
     - Supplied/repaired share
     - Previously applied
   * - Sweden
     - 91.211681%
     - 30%
   * - Norway
     - 38.2813676%
     - 30%
   * - Iceland
     - 100%
     - 30%

These are preserved model inputs, not newly collected measurements for 2025.
The repair does not update their historical sources or forecast assumptions.
Explicit user blends continue to override the relevant default fuel category.

Completed 2025 Swedish Medium gas-car runs give about 80 g fossil tailpipe
CO2/km under the old cap, versus 10 g/km with the supplied share. Energy demand
is identical. The change also affects the fossil/non-fossil split of additional
methane leakage and upstream fuel-production impacts; total climate results
must be recalculated for affected studies.

``tests/test_biofuel_shares.py`` checks the three countries, lower-share controls,
regional fallback, interpolation and extrapolation at both fraction bounds.
Completed model/LCIA cases cover Medium cars, 13m-city buses and 40t long-haul
trucks in all three countries, reordered 2020/2025/2030 years and two samples.
Independent expectations check component purchases, engine fuel, combustion
CO2 and methane leakage. Brightway exports of a retained sample preserve the
shares and both carbon origins, including Iceland's 100% biomethane blend.

.. _default-hydrogen-supply:

Default hydrogen supply
-----------------------

Without an explicit hydrogen blend, FCEV cars, buses and trucks use 100%
``hydrogen - smr - natural gas`` and 0% ``hydrogen - electrolysis - PEM``.
This follows the primary route in ``data/fuel/default_fuels.yaml`` for every
country and year. It is a fallback modelling assumption, with no implied
forecast or claim to represent a measured national hydrogen market. Studies
with known hydrogen sourcing should provide their own ``fuel_blend``.

Previously, an obsolete fuel-name condition caused hydrogen to use the petrol
bioethanol table. The resulting 2025 PEM-electrolysis shares were 1.1576289%
for Switzerland, 4.165197% for Germany and 20.1925897% for Brazil. These were
unrelated biofuel assumptions, with no hydrogen-specific justification.
The repair separates hydrogen defaults from all biofuel share tables.

Explicit hydrogen mixes remain supported. For example, this scalar primary-only
override supplies 100% PEM-electrolysis hydrogen in every selected model year:

.. code-block:: python

    fuel_blend = {
        "hydrogen": {
            "primary": {"type": "hydrogen - electrolysis - PEM", "share": 1.0}
        }
    }
    # Pass fuel_blend=fuel_blend to the vehicle model constructor.

For mixed routes, provide primary and secondary components with complementary
mass shares. Year-specific share sequences follow ``array.year`` order, as
described in :doc:`input_validation`. Overrides for other fuel categories
continue to leave the hydrogen default intact.

Changing the hydrogen supply route affects upstream inventories and impacts.
With the bundled physical fuel properties, vehicle hydrogen demand and driving
energy remain unchanged and direct fossil/non-fossil CO2 emissions remain zero.
The default's natural-gas production route still has upstream emissions.
Recalculate affected FCEV studies to apply the corrected supply assumption.

``tests/test_hydrogen_defaults.py`` checks country and regional defaults,
unknown-country handling, individual and reordered years, and independence
from biofuel tables. Completed model/LCIA checks cover Medium cars in Brazil,
13m-city buses in Switzerland and 40t long-haul trucks in Germany for
2020/2025/2030 and two load samples. Default, pure-electrolysis and explicit
year-varying supplies are checked against independent kg/kg component shares,
the 120 MJ/kg hydrogen heating value and zero direct CO2. Annual Brightway
exports of a retained sample preserve these exchanges and the source inventory.
These checks validate implementation of the supply assumption; they do not
validate national hydrogen production shares or upstream production datasets.

.. _sulfur-year-accounting:

Sulfur emissions by inventory year
----------------------------------

Fuel-based SO2 emissions use the sulfur concentration for each vehicle's
inventory year. Concentrations are kg elemental S/kg fuel; 1 ppm by mass is
``1e-6`` in these units. The molecular-mass conversion from S to SO2 is
``64 / 32``. Missing country codes retain the bundled European (RER) fallback
and its notice. Fuels without a sulfur-table entry retain the existing zero
assumption. The bundled concentrations and the assumption that biofuels use
the same concentration as their conventional fuel category are unchanged.

Previously the lookup summed sulfur concentrations across all selected years
and applied that scalar to every vehicle. Selecting 2020, 2025 and 2030, for
example, tripled Swiss diesel's applied concentration from 10 to 30 ppm,
and petrol's from 8 to 24 ppm. With differing concentrations, a historical
year could also inflate future-year emissions. Recalculate multi-year
inventories and exports to correct these SO2 exchanges and their LCIA effects.
That year-lookup repair retained the former stored-fuel/distance basis.

SO2 now uses the same burned fuel per kilometre as fuel purchases and CO2:
``fuel consumption`` (litres/km) times ``fuel density per kg`` (kg/litre),
times the annual sulfur fraction, times ``64 / 32``. Dividing stored fuel by
combined range is not equivalent for plug-in hybrids: their fuel consumption
already accounts for the share of distance driven electrically. The corrected
calculation applies that share once, through fuel consumption, and produces
zero fuel-based SO2 when no fuel is burned.

Completed default Swiss 2025 runs illustrate the correction. On WLTC, the
``Medium`` petrol PHEV previously emitted 0.143 mg SO2/km instead of the
fuel-balance expectation of 0.169 mg/km (15.0% low); the diesel PHEV emitted
0.170 instead of 0.198 mg/km (14.2% low). The ``40t`` diesel PHEV on the
``Long haul`` cycle emitted 4.151 instead of 4.181 mg/km (0.7% low).
These expectations use the existing fuel demand and bundled sulfur values,
not external emissions measurements. Recalculate affected PHEV inventories
and exports; vehicle energy use, fuel purchases and CO2 are unchanged by
this accounting correction.

``Inventory.get_sulfur_content(location, fuel)`` now returns a private
``xarray.DataArray`` with a ``year`` dimension in inventory order, including
for a single year. Direct callers can use ``.sel(year=2025).item()`` to obtain
one scalar. A zero concentration writes zero emissions and can clear a
previously populated SO2 exchange when recalculating.

``tests/test_sulfur_emissions.py`` checks distinct yearly concentrations,
zero endpoints, reordered years and dimensions, country fallback, multiple
sizes/samples and preservation of unrelated exchanges. Completed car, bus,
truck and two-wheeler models cover conventional engines, non-plug-in hybrids
and the supported petrol/diesel PHEVs, with BEV and methane controls.
Independent expectations compare fuel purchases against combustion energy
divided by heating value (weighted by combustion-driving share for PHEVs),
then multiply burned fuel mass by the bundled sulfur fraction and ``64 / 32``.
Additional completed PHEV runs check explicit electric-driving shares of 0%,
50% and 100%, including zero fuel and SO2 at the fully electric endpoint.
Single-year inventories are built from the same completed vehicles to isolate
inventory behavior from sizing. LCIA must remain finite, and annual exports
of a retained sample must preserve the SO2 exchanges and source inventory.
These are accounting checks, not new measurements of fuel sulfur content.

Run with the sibling packages and optional export dependencies::

   CARCULATOR_REQUIRE_FAMILY=1 python -m pytest tests/test_sulfur_emissions.py

.. _fuel-blend-density:

Fuel-blend density and volume checks
------------------------------------

Fuel-blend shares are mass fractions. The shared model calculates blend density
in kg/L as ``1 / sum(w_i / rho_i)``: one kg of blend contains ``w_i`` kg of each
component, occupying ``w_i / rho_i`` litres. This assumes additive component
volumes at the reference conditions of the supplied densities. It does not
model nonideal mixing contraction or expansion, nor temperature dependence;
these are accounting checks, not empirical validation of liquid mixtures.

Previously density was averaged arithmetically with mass shares. This
overestimated density and understated reported litres when component densities
differed. For a 50/50 diesel/biodiesel mass blend using the bundled 0.83 and
0.88 kg/L densities, the corrected density is approximately 0.854269 kg/L,
rather than 0.855 kg/L. Reported consumption in L/km increases by about 0.086%.
Pure fuels and blends with identical component densities retain their density.
The correction preserves heating values, driving energy and mass-based fuel
and combustion-CO2 accounting, apart from numerical rounding. It does not
change the calibrated vehicle-energy parameters.

``tests/test_fuel_density.py`` reconstructs known batches from component
volumes and densities, then checks their total mass using the model's blend
density. Cases cover every fuelled powertrain handled by the shared method,
pure-component endpoints, scalar and year-specific overrides, reordered years,
multiple sizes and sample labels, and caller-data preservation.
``tests/test_fuel_blend_inventory.py`` independently derives burned mass from
combustion energy and lower heating value, divides each component's mass by its
density, and checks the sum against reported fuel litres. Completed car, bus,
truck and two-wheeler runs include hybrids/PHEVs, three years, two load samples,
fuel suppliers, fossil/non-fossil CO2, finite LCIA results and annual exports.

Run the checks with the sibling packages and optional export dependencies::

   CARCULATOR_REQUIRE_FAMILY=1 python -m pytest tests/test_fuel_density.py tests/test_fuel_blend_inventory.py

Fuel-blend inventory checks
----------------------------

The biological synthetic-methane supplier repair and its completed car, bus and
truck checks are described separately in :doc:`biological_methane`. The audit
below covers blend propagation and predates that supplier correction.
The additional methane-loss mass balance, carbon-origin split, characterization
and boundary limitations are covered in :doc:`methane_leakage`.

``tests/test_fuel_blend_inventory.py`` completes parameter loading, vehicle
sizing, inventory construction and LCIA for all four vehicle families. It
uses Medium cars, 13m-city buses, 40t long-haul trucks and Motorcycle 11-35kW
two-wheelers. The 20 matrix runs cover 22 family/powertrain combinations,
three years (2020, 2025 and 2030), and two passenger-load samples: 660 vehicle/year/sample
cases across five blend configurations.

The configurations are country defaults, fossil/biofuel blends, selected
synthetic-fuel blends, two blend components sharing one supplier, and a scalar
primary-only specification with its automatically completed secondary fuel.
Explicit two-component blends use primary mass shares of 100%, 65% and 0% in successive
years; primary-only specifications use 65% in all three years. These
are accounting stress tests, not recommendations for engine fuel compatibility.
Hydrogen from natural-gas reforming and PEM electrolysis is included for fuel
cell vehicles; BEVs provide zero-fuel and zero-tailpipe-CO2 controls. Passenger
cars also include petrol/diesel hybrids and plug-in hybrids; buses include
diesel hybrids; trucks include diesel hybrids and plug-in hybrids.

Independent expectations check:

* burned fuel mass = combustion energy / blend lower heating value;
* PHEV combustion energy = combustion-mode energy times one minus the electric
  utility factor;
* fuel-market inputs equal component mass shares, summed when suppliers coincide;
* transport fuel purchases equal burned mass, with the existing pump-to-tank
  leakage allowance added for methane;
* fossil and non-fossil tailpipe CO2 equal burned mass times the corresponding
  share-weighted fuel carbon factors; and
* other fuel inputs are zero and completed impact results are finite.

The checks also verify that caller-supplied blend dictionaries are unchanged
and that their requested types and shares survive model construction. Twelve
additional runs export static inventories through the public Brightway 3.10
export API: 36 annual exports containing 99 fuel-supply datasets and 198
transport datasets. The exported component quantities must total one kg per kg
of blend, preserve zero/100% endpoints and merged suppliers, and match the
transport fuel and fossil/non-fossil CO2 exchanges. Export must leave the
original inventory matrix and supplier index unchanged. No Brightway database
is written. These export checks require the optional Brightway dependencies.

For example, a 65% petrol / 35% sugarbeet-ethanol mass blend exports 0.65 kg
petrol and 0.35 kg ethanol per kg of fuel supply. Using the bundled fuel
properties, each kg burned produces 2.041 kg fossil CO2 and 0.686 kg non-fossil
CO2; vehicle exchanges scale those factors by actual burned fuel per km.

All 32 matrix/export tests passed with no skips on the latest repaired runtime.
The :download:`verification summary <_static/fuel_blend_verification/summary.json>`
records the scope, command and source hashes.

The audit exposed and repaired two shared inventory defects. A second component
pointing to the same supplier overwrote the first component's exchange. PHEV
tailpipe CO2 used weighted tank mass divided by combined range instead of the
fuel consumption used by its supplier exchange. The latter understated fossil
CO2 by up to 18.4% for the tested default petrol PHEV cars and about 0.7% for
the tested default diesel PHEV trucks. Both fossil and non-fossil CO2 now use
the fuel-consumption mass basis. These corrections affect inventory accounting,
not driving-cycle fuel consumption or the calibrated energy parameters.

This verifies propagation of the bundled fuel specifications, not independent
validation of upstream production datasets, every synthetic-fuel carbon-source
classification, or every vehicle size. In particular, the existing
``biogenic_share`` field also serves as the non-fossil accounting flag for
some synthetic fuels; passing this test does not establish that captured CO2
is physically biogenic. CO2 follows the model's complete-oxidation convention;
this is not an elemental balance including separate CO, methane and hydrocarbon
emission models. Shares are mass fractions, not petrol-station volume blends.

Run the checks with all four sibling packages installed::

   CARCULATOR_REQUIRE_FAMILY=1 python -m pytest tests/test_fuel_blend_inventory.py

Reproducibility
---------------

The model-specific ``docs/validity.rst`` pages state what was calibrated, what
was merely compared, and which measurements are still missing. The shared
artifact index at ``docs/_static/energy_validation_2025/README.md`` distinguishes
current results from retained investigation history. Original inputs and
calibration metadata remain packaged with each vehicle model.

Seeded inputs now retain projected-cost draws across fresh model runs and sample
selections; see :doc:`cost_uncertainty`. This repair preserves the uncertainty
distributions and does not empirically validate the underlying cost assumptions.


Known limitations
-----------------

* The electrochemical synthetic-methane supplier is absent from the bundled inventory index and raises a visible mapping error.
* Generic NMVOC characterization is used for ethene where the bundled biosphere index has no exact flow; HBEFA source-version provenance remains incomplete.
* Legacy arrays without retained cost-factor coordinates cannot reproduce projected-cost draws from the original input seed. Rebuild inputs with the current array builder and use fresh models for independent runs.
