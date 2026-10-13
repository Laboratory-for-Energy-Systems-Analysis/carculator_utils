Vehicle energy efficiency and direct-emission drivers
=====================================================

Status: emission-scaling correction verified; constant-range hardware sizing
remains in progress. This is the first independent part of remediation step 8.

Finding and correction
----------------------

Premise derives its vehicle efficiency index from final energy divided by
transport service, relative to 2020. The car mappings use vehicle-kilometres;
truck mappings use tonne-kilometres. The default upper index bound of 1.25
limits the corresponding energy reduction to 20%. This is an overall energy
intensity, not an isolated motor/engine efficiency. Future native carculator
improvements must not be applied in addition to the same IAM reduction.

The old transport transformation multiplied every biosphere exchange by the
energy-demand factor. The combustion-car energy floor additionally rescaled
several HBEFA pollutants. Neither operation establishes a physical relationship
between energy demand and distance/start-based emission factors.

The correction uses the model's existing inventory equations:

* Burned-fuel CO2 follows fuel purchases; the fuel module still resolves the
  final regional fossil/non-fossil split.
* Sulphur dioxide follows fuel mass at the existing sulphur concentration.
* Generic-air methane leakage follows fuel throughput. Urban/rural/highway
  HBEFA combustion methane is separate and retains its distance basis.
* HBEFA hot, cold-start and evaporative emissions are not rescaled by this
  energy-intensity operation. This includes NOx, PM, CO, NMVOC, formaldehyde,
  benzene and PAHs. No new emission factors or speciation are introduced.
* Refrigerants and other distance/time/resource flows are not energy-scaled.
  Wear treatment and manufacturing technosphere exchanges already lay outside
  the energy selection and remain unchanged in this commit.

Premise's separate GAINS pollutant projections remain active. Therefore this
correction does not imply identical 2020 and 2050 pollutant inventories.
Neither the plausibility screen nor the correction clips emissions to a EURO
limit. Buses/two-wheelers and other transport modules retain their existing
behavior pending their own inventory updates.

Validation
----------

Both complete builds use REMIND SSP2-NPi, ecoinvent 3.12 cutoff, identical
encrypted IAM input and workbooks, and an isolated Brightway project copy.
No persistent user database was written. The control is the completed truck
HEV correction in ``premise_truck_hev_storage_20261013``.

.. list-table:: Complete scenario comparisons
   :header-rows: 1

   * - Check
     - 2020
     - 2050
   * - Activities
     - 42,564
     - 42,574
   * - Materially changed exchanges
     - 0
     - 9,295 biosphere exchanges
   * - Changed activities
     - 0
     - 357 car/truck services
   * - Fuel purchases, vehicle manufacture and batteries
     - Unchanged
     - Unchanged
   * - Final fuel-carbon balance checks
     - 495 passed
     - 495 passed
   * - Hydrogen compression checks
     - 147 passed
     - 147 passed
   * - Validation errors
     - 0
     - 0
   * - Validation warnings
     - 401, unchanged
     - 445, previously 398

Every material change equals removal of the previous unsupported scaling,
including the old energy-floor correction where applicable. Changes below
1e-9 relative or 1e-13 absolute are counted separately as roundoff.
Suppliers, reference identities, fuel-derived CO2 and all technosphere
coefficients are unchanged within that tolerance.

The 47 additional warnings all belong to the inherited hot-only 0.5–2 times
screen. That screen uses a fuel-normalized reference; its reference declines
with energy demand while corrected distance/start-based emissions do not.
These are screening disagreements, not newly demonstrated EURO-limit failures.
Warnings remain visible and are not suppressed to obtain a clean report.

The EUR 40 t BEV's R134a emission increases from 1.0283e-7 to 1.2854e-7 kg/tkm:
removing the old 0.8 multiplier raises the value 25%. The EUR Mini gasoline
car's urban formaldehyde changes from 8.5224e-7 to 8.7526e-7 kg/km, about 2.70%.
Across affected exchanges, changes range from +2.09% to +25%. These increases
remove an unsupported future benefit; they do not revise HBEFA factors.

All 121 focused tests pass, including 28 emission-driver regressions. They
exercise conventional and electrified cars, trucks, compact exchange records,
uncertainty scaling, a binding energy floor, methane compartments, unrelated
burdens, invalid factors, regional fuel-carbon accounting, hydrogen compression
and physical battery purchases. Runtime source changes are confined to
``transport.py``, ``car_energy.py`` and ``vehicle_emissions.py``.

Remaining hardware work
-----------------------

Battery quantities and vehicle hardware intentionally have not yet changed
in this independent correction. The user approved the original chemistry's
Premise density projection for BEV/PHEV physical mass, including NMC-622
0.24 to 0.26 kWh/kg from 2020 to 2050. High-power HEV specifications remain
separate. The approved range policy still requires consistent capacity, mass,
power, lifetime and inventory propagation without double-counting IAM gains.

Artifacts
---------

``build_2020.json`` and ``build_2050.json`` record runtime/source/input hashes.
``verification_summary.json`` contains independent comparison checks;
``scenario_emission_changes.csv`` lists changed foreground coefficients;
``warning_changes.json`` records warning-count differences by activity/rule.
Full licensed inventories and validation payloads remain private/untracked.
The build and audit are reproducible with ``dev/build_premise_vehicle_efficiency.py``
and ``dev/audit_premise_vehicle_efficiency.py``.
