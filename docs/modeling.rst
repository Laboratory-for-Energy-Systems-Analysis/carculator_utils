.. _model:

Shared calculation methods
==========================

``carculator_utils`` supplies methods used by the four vehicle packages. It has
no standalone default vehicle. Each vehicle package provides input tables and
sizing rules; the shared code converts their calculated properties into energy,
emissions, inventories and impact scores. Start with :doc:`usage` for an example
and :doc:`interpretation` for definitions and units.

Inputs and uncertainty
----------------------

Parameter records identify a name, size, powertrain, year, amount and, where
applicable, an uncertainty distribution. ``static()`` uses central values;
``stochastic(n, seed=...)`` draws input samples. With the current array builder the seed controls parameter draws and separate
projected-cost streams for cars, buses and two-wheelers. Trucks use their sampled
cost records. Keep the array's auxiliary sample coordinates to preserve those
draws; older hand-built arrays need separate care. See :doc:`cost_uncertainty`.

``fill_xarray_from_input_parameters()`` returns coordinate mappings and a labelled
array with dimensions ``size, powertrain, parameter, year, value``. ``value``
identifies a sample. Select a small set of vehicles and years before expanding
an uncertainty study. Interpolation of a missing input does not supply evidence
for it: the completeness checks distinguish missing records from supplied zeroes.
See :doc:`input_validation`, :doc:`input_completeness` and :doc:`cost_uncertainty`.

Vehicle sizing and repeated runs
--------------------------------

Mass, energy consumption and battery capacity can depend on each other. Sizing
therefore repeats their calculation until the vehicle package's convergence
condition is met for each active vehicle, year and sample. The iteration count
is bounded. A nonfinite value or failure to converge raises an error identifying
the affected configuration; adding many vehicles together is not a valid way
to test convergence.

For a battery of nominal capacity :math:`C` in kWh and usable depth of discharge
:math:`u` between zero and one, a target range :math:`R` in km requires

.. math::

   C=\frac{R e}{u},

where :math:`e` is net stored-energy consumption in kWh/km. A heavier chemistry
can increase :math:`e`; sizing must recalculate it after changing battery mass.
Changing capacity or mass instead makes range an output. Vehicle-specific
precedence rules decide which input controls the calculation; see
:doc:`bev_target_range_issue` and the vehicle package's sizing guide.

A second ``set_all()`` call starts from saved inputs and incorporates explicitly
edited values, rather than treating the previous outputs as new assumptions.
See :doc:`repeated_runs` for selections, failures and plug-in-hybrid restrictions.
Use a fresh model when adding coordinates or defining an independent scenario.

Driving-cycle physics
---------------------

The model uses speed and road gradient at each time step. Force in newtons is
calculated from rolling resistance, aerodynamic drag, road slope and inertia:

.. math::

   F_{total}=m g C_{rr}\mathbf{1}_{v>0}
       +\tfrac12\rho C_d A_f v^2
       +m g\sin(\theta)\mathbf{1}_{v>0}+m a.

Here :math:`m` is driving mass in kg, :math:`v` speed in m/s, :math:`a`
acceleration in m/s², :math:`\rho` air density in kg/m³, and :math:`A_f` frontal
area in m². The coefficients :math:`C_{rr}` and :math:`C_d` are dimensionless.
The internal angle :math:`\theta` is in radians. User-supplied numeric gradient
profiles use degrees; bundled rise/run profiles are converted by arctangent.
The indicator :math:`\mathbf{1}_{v>0}` is zero when stopped.

Multiplying force by speed gives wheel power, in watts. Integrating power over
time gives energy; dividing by cycle distance gives energy per kilometre. Engine,
motor and transmission losses are applied at their respective power boundaries.
Negative wheel power represents braking or deceleration, part of which can be
recovered by electric propulsion within its power and efficiency limits.

Efficiency-map lookup is limited to its supported load range. This does not
mean that the requested driving power has been capped at the vehicle's rating.
Inspect power-limit diagnostics when a small motor is asked to follow an
aggressive cycle. A finite consumption result alone does not establish that the
vehicle could physically follow every second of that cycle.

Auxiliary loads consume energy over time, including stops. A constant 1 kW load
for an hour adds 1 kWh before the losses needed to supply it. Slow trips can
therefore have higher auxiliary energy per kilometre than fast trips.

Buses calculate outside-temperature-dependent HVAC demand with a fixed 20°C cabin
assumption. Cars and trucks use annual thermal-demand inputs; two-wheelers do not model
cabin HVAC. All three reject temperature overrides. The outside-temperature profile, cabin assumption
and base auxiliary demand are separate inputs. See :doc:`input_validation`.

Electrical measurement boundaries
---------------------------------

Let :math:`D` be positive DC energy drawn at battery terminals and :math:`R`
regenerated DC energy returned there. With discharge and charge efficiencies
:math:`\eta_d` and :math:`\eta_c`, stored-energy depletion is

.. math::

   E_{stored}=D/\eta_d-R\eta_c.

Net terminal energy is :math:`D-R`, a different quantity. Grid charging also
includes charging and charger losses. ``TtW energy`` is kJ/km;
``battery_terminal_energy`` is kJ/km; ``electricity consumption`` is kWh/km.
For a BEV these correspond to stored energy, terminal DC and purchased charging
electricity respectively. Do not apply charging losses to the grid output again.
See :doc:`interpretation` and :doc:`energy_model_repairs`.

Fuel supply and direct emissions
--------------------------------

Fuel blend shares are **mass fractions**, not volume fractions. Lower heating
value is mass-weighted. With component mass fractions :math:`w_i` and densities
:math:`\rho_i`, the mixture density assumes additive component volumes:

.. math::

   \rho_{mix}=1\big/\sum_i w_i/\rho_i.

Each component retains its supplier, physical properties and fossil/non-fossil
CO2 accounting. Defaults apply to fuel categories omitted from an override.
An unsupported or unresolved supplier raises an error; the model does not
silently choose another fuel route. See :doc:`fuel_catalogue`,
:doc:`biological_methane` and :doc:`input_validation`.

Additional methane leakage defaults to zero. Upstream losses in the selected
supplier and exhaust methane remain included. A nonzero additional-loss input
requires evidence that it does not duplicate those losses; see
:doc:`methane_leakage`.

The default CO2 calculation assumes complete oxidation of fuel carbon, while
CO, methane and hydrocarbons are estimated separately. It therefore does not
close an elemental carbon balance exactly. ``carbon_balance()`` reports the
difference without changing the inventory. Explicit reconciliation requires
supported composition assumptions; see :doc:`carbon_accounting`.

Hot pollutant factors are translated into species and air compartments before
inventory assembly. Software tests check units, ordering, nonnegative quantities
and supplier/flow identity. They do not independently validate the empirical
emission factors. See :doc:`hot_emission_audit` for data lineage and limitations.
Wear and noise use separate calculations. Noise power contributions are added
in linear units before any logarithmic conversion; decibel levels are not added
directly.

From inventories to impact scores
---------------------------------

``A`` has dimensions ``sample, product, activity, year``. ``B`` has dimensions
``year, impact category, activity`` and stores precomputed background impact
coefficients and elementary-flow characterization factors. It is not a raw
biosphere-exchange matrix. The input index and the activity order of both arrays
must agree. For each sample and year, the calculation solves

.. math::

   A s=f,\qquad h=B s.

:math:`f` specifies final demand, :math:`s` gives activity amounts and
:math:`h` gives characterized impacts. Functional-unit conversion divides by
passenger count or cargo tonnes when requested. Costs have their own units and
must not be added to environmental indicators.

National electricity generation shares are averaged over each vehicle's own
operating lifetime. That choice is distinct from the background technology
scenario used for the impact coefficients. ``static`` selects static impact
coefficients; it does not freeze the national electricity mix. See
:doc:`electricity_lifetime`, :doc:`electricity_scenarios` and
:doc:`background_rebuild`.

Exports default to ecoinvent 3.12 cutoff. Export works on copies so it can preserve
the calculated inventory and results. A receiving LCA application still needs
compatible background providers and elementary-flow links; see
:doc:`inventory_export`.

Evidence and limitations
------------------------

:doc:`validation_examples` introduces the measured-energy comparisons and the
separate background-update comparison. :doc:`validity` records implementation
checks. Calibration of one input on one bus or one cycle does not validate every
vehicle that shares the input. Historic audit outputs remain dated snapshots,
not guarantees about all configurations of the current software.
