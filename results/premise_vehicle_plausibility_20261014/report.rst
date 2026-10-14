Car/truck plausibility review and hybrid fuel-mapping correction
================================================================

The review found a genuine Premise fuel-mapping defect and several unresolved
model issues. The fuel mapping is corrected in this step. This is not an
unqualified sign-off of the vehicle specifications or emission factors.

Correction made
---------------

Five gasoline PHEV mappings (Mini, Small, Medium, Medium SUV and Van) selected
electricity alone. The Large mapping already included petrol. Consequently,
the IAM efficiency multiplier reduced electricity and the associated battery
capacity but left petrol unchanged. This was an omission in the mappings,
not a deliberate difference between electric and combustion-mode efficiency.

The five mappings now include ``petrol, low-sulfur``. The gasoline HEV mapping
also accepts petrol while retaining its gasoline alias; its original alias
could miss the actual provider. These six data edits use the existing runtime
algorithm. No vehicle solver, additional runtime scan or new calibration was
introduced. The fuel module's existing final-supplier CO2 refresh performs the
carbon correction after the fuel purchases change.

In the controlled 2050 REMIND SSP2-NPi build, 52 regional PHEV datasets had
missed a 20% petrol reduction. This correction therefore reduces their petrol,
fossil CO2 and non-fossil CO2 by 20% relative to the preceding build. Electricity,
physical battery specifications and other exchanges remain unchanged. The
2020 baseline is unchanged. The mapping also applies to other IAM models when
they provide a usable efficiency trend; it does not supply missing IAM data.

Scope and verification
----------------------

The 74 car and 52 truck service templates were regenerated from the matching
current source checkouts, without reusing raw exports. The fresh workbooks
reproduce the installed scientific exchange coefficients. Generation remains
2020, Swiss climate, 1.8 starts/day for cars, and Regional delivery with a
400 km design range for trucks. Names, fuel proxies, approved MIX battery
markets and noise companion boundaries remain as agreed.

The audit checks all 726 operating car/truck services in each complete 2020
and 2050 database, covering all scenario regions and retained templates. Fifty
forwarding activities are identified separately. Checks include positive and
finite quantities, vehicle allocation per lifetime distance and cargo, 415
battery allocations, 221 scenario battery designs, and 578 fuel-energy/carbon
balances per year. Fuel units come from the delivered supplier. The model's
gas consumption field is a volume: treating its large numerical value as kg/km
would be an error.

For future batteries, independently reconstructed range uses nominal capacity,
depth of discharge, charging losses, electric driving share and final grid
purchases per vehicle-km. BEV truck cargo uses the retained capacity utilization
and the remaining payload after battery mass changes. Fuel and hydrogen tanks
retain their baseline design, as requested. Non-CO2 comparisons account for
the GAINS module's separate pollutant projection; they do not attribute those
reductions to vehicle efficiency.

The regression reproduces the missing-PHEV-petrol failure before the mapping
change. Forty-two new cases cover the six gasoline PHEV classes and gasoline
HEV, both inventory representations, and efficiency multipliers 1, 0.8 and 1.2.
The focused Premise suite passes 209 tests. The existing shared emissions suite
passes 61 tests, including PAH identity, evaporation and pollutant integration.
These passing tests do not resolve the new scientific concerns below.

Both full builds use ecoinvent 3.12 cutoff and encrypted REMIND SSP2-NPi input,
and are written/read back in a private Brightway copy. The persistent user
project is untouched. See ``after/build_*.json``, ``after/saved_*.json``,
``after/accounting_summary.json`` and ``change_scope_summary.json`` for actual
completed-build counts and the numerical change boundary. No final old/new
EF 3.1 comparison is claimed here; that remains step 12.

Outstanding issues, in suggested order
--------------------------------------

1. Fuel-cell battery power and mass accounting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

All eight native FCEV car sizes report a 70% cell-mass share, but their actual
cell/pack mass ratio is 76.923%. The shared method calculates balance-of-pack
mass as ``cell_mass * (1 - cell_share)``. The stated share instead requires
``cell_mass / cell_share - cell_mass``. For the Medium car, 14.024 kg of cells
are combined into an 18.232 kg pack; a 70% share would require 20.035 kg before
any power-sizing correction.

The same method derives battery power from gross fuel-cell power multiplied by
the remaining share, instead of closing the stated total-power budget. For the
Medium car, net fuel-cell power is 104.218 kW and recorded battery power is
29.878 kW, against 138.958 kW total power. The electrical/mechanical boundary
must be made consistent before recalculating the pack.

All seven FCEV truck sizes finish with ``battery power = 0`` despite 32.72--88.56
kWh traction batteries. Their inherited cell-power-density input is 0.15 kW/kg,
described in the parameter source as a lead-acid starter-battery value. Truck
energy-pack sizing follows its separate rule, 20 kWh plus 6% of tank energy;
therefore zero recorded battery power does not mean no physical pack exists.
It does mean the exported specs do not establish a consistent traction-power
design. These are concrete accounting/parameter concerns, not a request to
resize future hydrogen tanks.

The truck capacities themselves are not automatically implausible: Hyundai's
2020 XCIENT specifications give a 73.2 kWh battery, 190 kW fuel-cell system and
350 kW motor for its particular design. This supports checking architecture
and power together rather than rejecting a large buffer by capacity alone.
`Hyundai's 2020 technical announcement <https://www.hyundai.news/uk/articles/press-releases/hyundai-today-delivered-the-first-seven-units-of-its-xcient-fuel-cell.html>`_.

2. Truck NOx factors and hybrid deterioration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The 40 t diesel template emits 3.21875 g NOx/vehicle-km at 12.4985 MJ fuel/km.
Its bundled hot coefficient is 0.157203 g/MJ and the lifetime-average
deterioration multiplier is about 1.638. Even without deterioration, converting
that coefficient to engine-work units would exceed 0.46 g/kWh at a hypothetical
100% conversion efficiency. The screen flags NOx for 21 native diesel/diesel-
hybrid/PHEV templates and six gasoline proxies. No other screened truck
pollutant exceeds its benchmark on this conservative fuel-energy lower bound.
Passing that lower-bound screen does not establish compliance either.

Euro VI regulates heavy-duty engine emissions in mg/kWh of engine work,
not mg/km or mg/kWh of fuel. WHTC and the model's Regional delivery cycle are
different tests. The 3.5 t class additionally needs its actual homologation
category before choosing a regulatory benchmark. The values are therefore
plausibility flags, not type-approval verdicts.
`Euro VI limit table <https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=oj%3AJOL_2014_047_R>`_.

High real-world emissions at low load are documented, but they do not establish
the validity of these particular coefficients. The JRC describes how earlier
Euro VI test exclusions affected low-load and urban operation; its 2020 tests
of other vehicles generally found NOx below the certification limit.
`JRC review of test boundaries <https://publications.jrc.ec.europa.eu/repository/bitstream/JRC117559/JRC117559_01.pdf>`_;
`JRC 2020 measurements <https://publications.jrc.ec.europa.eu/repository/handle/JRC122045>`_.

The available ``carculator_truck/dev/EFA_HOT_Subsegm_HGV.XLSX`` contains emission
rates, subsegments, speed and mileage, but no fuel-energy column. The notebook
fits speed polynomials and cannot reproduce the shipped g/MJ coefficients.
The user confirmed on 2026-10-14 that the original derivation is no longer
available. The conversion remains unverified; no guessed replacement or
regulatory clipping has been applied. Resolving it requires a new traceable
factor derivation or an explicitly selected alternative source/boundary.

A separate implementation concern is that deterioration-table lookup reindexes
the literal powertrain label. The tables contain ICEV labels; HEV and PHEV
combustion modes consequently receive unity rather than the corresponding
combustion-vehicle correction. Hot-factor lookup already uses the combustion
alias. That inconsistent treatment should be addressed with focused tests,
without using it to conceal the larger uncertainty in the truck factors.

3. Car PHEV capacity calibration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The default PHEV packs are 21.17--42.34 kWh. Their electric-mode ranges reach
about 194 km for Large cars, and Premise deliberately preserves those ranges
in 2050. Arithmetic consistency therefore does not establish a representative
2020 design.

The parameter mass sources cite Toyota and a 2020 ICCT report, while the model
combines those pack masses with chemistry-specific cell densities and a 70%
cell share. Toyota documents 8.8 kWh and 120 kg for the contemporary Prius
Plug-in; BMW documents 24 kWh and 67--87 km WLTP range for the X5 xDrive45e.
These examples are not fleet averages, but show why the 21--42 kWh defaults
need an explicit calibration review. No new mass, capacity or range target has
been substituted for the user's approved defaults.
`Toyota specifications <https://newsroom.toyota.eu/toyota-prius-plug-in-hybrid/>`_;
`BMW specifications <https://www.press.bmwgroup.com/slovenia/article/detail/T0300315EN/electrifying-power-for-supreme-driving-pleasure-market-launch-of-the-new-bmw-x5-xdrive45e>`_.

4. Long-range small BEV truck representativeness
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The 3.5 t BEV has 133.804 kWh nominal capacity, a 796.450 kg pack, 2459.401 kg
curb mass, 750 kg cargo, a 75 kg driver and 3284.401 kg driving mass. It fits
the gross-mass constraint with 215.599 kg remaining and uses 30.190 kWh/100 km
at the grid. The capacity follows the agreed 400 km range and 80% depth of
discharge. It is not an unexplained numerical explosion.

It is nevertheless a demanding counterfactual for 2020. Fiat's August 2020
E-Ducato offering used 47 or 79 kWh packs with different ranges and operating
conditions. The agreed range should therefore be described as a common design
requirement, not a claim that this was a typical commercially sold 2020 van.
`Fiat 2020 announcement <https://www.media.stellantis.com/uk-en/fiat-professional/press/fiat-professional-confirms-pricing-and-specification-of-fiat-e-ducato-for-uk-market>`_.

The EUR 2050 accounting gives 107.043 kWh, 588.148 kg pack mass and 911.793 kg
cargo at the same utilization and 400 km range. This remains a simple IAM
accounting construction, without a driving-cycle re-simulation.

Other reviewed boundaries
-------------------------

Car BEVs span 10.08--110.88 kWh and 7.92--25.50 kWh/100 km at the grid. The
largest packs are demanding but in the same order of magnitude as premium
vehicles available around 2020; Audi's first e-tron had a 95 kWh pack of about
700 kg. This comparison is not a validation of every model size.
`Audi technical specifications <https://www.audi-mediacenter.com/system/production/uploaded_files/13470/file/8b75eb8e68ef933faa9eea2518c934c0f68e5c5e/en_Press_Information_Audi_e-tron_WorldPremiere.pdf>`_.

Native hydrogen consumption is 0.684--1.236 kg/100 km for cars and
1.590--8.570 kg/100 km across the seven truck sizes. Truck BEV grid consumption
is 30.19--163.63 kWh/100 km. The review found no factor-of-100 or gas-volume/mass
error in the imported energy purchases. It does not independently validate every
physical-model efficiency assumption.

The car exhaust screen covers 57 combustion/proxy templates. CO, exhaust PM
and the relevant hydrocarbon benchmarks show no exceedance. Gasoline Large SUV
NOx is 64.60 mg/km against a 60 mg/km M-category benchmark; gasoline Van is
61.72 mg/km under that same provisional classification. Their hot-only values
are below 60 mg/km; lifetime-average cold starts explain the excess. No clipping
is justified from this comparison alone. Brake, tyre and road wear are outside
the exhaust-PM benchmark, and particle number is not represented by PM mass.
`Euro 6 limit table <https://eur-lex.europa.eu/legal-content/en/TXT/?uri=CELEX%3A32012R0459>`_.

The approved high-power truck HEV MIX-market mass mismatch remains documented.
The broader PHEV gross-versus-net battery-cycling question remains open. Buses
and two-wheelers have not been refreshed in this work. The next concrete model
correction should address FCEV battery power and mass accounting; the final
controlled EF 3.1 comparison follows resolution of the remaining agreed issues.

Reproduction
------------

Scripts are in ``dev/`` of this repository:

* ``regenerate_premise_cars.py`` and ``regenerate_premise_trucks.py``: fresh
  exports using the matched carculator Python 3.12 environment.
* ``probe_premise_vehicle_plausibility.py``: physical parameters and separated
  hot/cold/evaporative emissions from fresh models.
* ``screen_premise_vehicle_plausibility.py``: explicit regulatory screening
  boundaries; no coefficients are modified.
* ``build_premise_vehicle_battery.py``: complete isolated 2020/2050 builds with
  the existing LPG and provenance installation manifests.
* ``audit_premise_vehicle_plausibility.py``: complete catalogue accounting.
* ``verify_premise_hybrid_fuel_mapping.py``: whole-database numerical diff and
  restriction of changes to the previously failing petrol/CO2 exchanges.

The ``before`` directory contains the audit of the preceding provenance builds;
``after`` contains the corrected builds and checks. Raw model exports and
licensed full inventories remain in the private temporary workspace identified
by the build manifests. No licensed database contents are committed.
