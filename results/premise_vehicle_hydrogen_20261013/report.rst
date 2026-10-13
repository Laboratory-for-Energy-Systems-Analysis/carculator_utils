Hydrogen tank compression: step 4
=================================

Completed on 13 October 2026. Hydrogen vehicle compression electricity now
follows final hydrogen consumption. The user approved the documented Premise
delivery pressure of **30 bar**, replacing the generic 25-bar assumption.
The same compressor model requires **2.450619 kWh/kg H2** to reach 700 bar,
instead of 2.616238. All **147 marked hydrogen car/truck services** pass the
independent check in each completed 2020 and 2050 scenario.

The existing fuel module was investigated first
-----------------------------------------------

``HydrogenMixin`` creates the regional low-pressure hydrogen market and adds
one kilogram of ``hydrogen supply, distributed by pipeline`` service per
kilogram supplied. The source inventory describes 250 km of transmission,
regional storage and another 250 km to the consumer, arriving at 30 bar.
Its direct electricity requirement is 1.816554 kWh/kg; production, infrastructure,
storage and loss replacement have their own upstream burdens.

This is already part of fuel supply. It does not include compression from
the delivered pressure to the vehicle's 700-bar tank. The older
``add_compression_electricity`` function, which mentions 900-bar dispensing,
has no call site in the current production/market pipeline. Its presence in
the source was therefore not evidence that tank preparation was counted twice.

The audit follows every marked vehicle's actual hydrogen market, including
original-geography and World forwarders, to the delivery inventories. Twelve
distinct regional delivery chains are reached in each year; each retains the
documented 30-bar boundary. Original RER, CN and US links are retained where
they serve the corresponding regional chain. The upstream recipes are unchanged.

The confirmed scaling defect was downstream: truck fuel aliases selected
hydrogen but omitted the separate tank-compression electricity exchange.
Hydrogen purchases fell with IAM efficiency, while that electricity stayed
fixed. A blanket electricity alias would also affect unrelated power and
could double-scale explicitly handled compression.

Correction and boundaries
-------------------------

The eight car and seven truck FCEV templates retain their hydrogen demand,
hardware, tank pressure, exact identities and all non-compression exchanges.
Only tank-compression electricity and its identifying metadata are adapted.
The compressor assumptions remain the carculator_utils defaults: 300 K,
three equal-pressure-ratio intercooled stages, ideal hydrogen with gamma 1.4,
0.56 isentropic efficiency and 0.92 motor efficiency. The pressure correction
reduces specific electricity by approximately 6.33%. It is a supply-boundary
adaptation, not an assumed compressor-efficiency improvement over time.
Precooling and fast-fill overpressure remain outside this model calculation.

The ``hydrogen tank compression`` activity metadata identify the fuel product,
electricity product, pressures, specific requirement, source and boundary.
They survive Excel import and regional relinking, which can aggregate exchanges
and discard their individual comments. The transport helper separates the
identified compression share before generic efficiency scaling, then sets it
once from final H2 purchases. A residual for other uses of the same electricity
product is retained, including when relinking merges them into one exchange.

``premise hydrogen compression balance`` records final H2, compression energy
and the other-electricity remainder. Validation checks these against current
exchanges. Retained templates receive a record; forwarding originals do not
retain a stale direct-use record. Unmarked legacy inventories are not assigned
an inferred compression purpose. Future old/new inventory comparisons must
make any compatibility adaptation explicit.

The regeneration adapters now calculate compression from the final purchased
H2 quantity after the reference-fuel conversion. This avoids small differences
from float32 source-export rounding. The installation receipt checks original
workbook hashes, preserves baseline copies privately, and verifies parsed
inventories against the intended changes. Truck parameter sidecars update
their seven compression values; car model parameters and both noise files
remain unchanged. Workbook provenance records the approved adaptation.

Replaying both adapters from the frozen raw model exports independently
reproduces all 5,451 car and 3,556 truck numerical coefficients across the
installed 162 and 127 datasets, respectively (relative tolerance 1e-12,
absolute tolerance 1e-18). The replay does not rerun or change vehicle sizing.
``adapter_reproduction.json`` records the checks and adapter source hashes.

Numerical example
------------------

.. list-table:: EUR 40 t FCEV truck, per tonne-kilometre
   :header-rows: 1

   * - Quantity
     - 2020
     - 2050
   * - Hydrogen, kg (unchanged by this correction)
     - 0.006201551
     - 0.004961241
   * - Previous tank-compression electricity, kWh
     - 0.016224734
     - 0.016224734
   * - Corrected tank-compression electricity, kWh
     - 0.015197640
     - 0.012158112
   * - Previous electricity per kg H2
     - 2.616238
     - 3.270298
   * - Corrected electricity per kg H2
     - 2.450619
     - 2.450619

The corrected 2050 electricity is 20% below corrected 2020, matching the
hydrogen reduction. Compared with the previous 2050 build it is 25.0643% lower,
combining the pressure adaptation and the missing demand scaling. The Medium
EUR FCEV car has no H2 efficiency change in this scenario: its electricity
falls from 0.02288280 to 0.02143422 kWh/km in both years solely because of the
pressure adaptation. These are direct inventory quantities, not EF 3.1 scores.

Verification
-------------

The full builds use REMIND SSP2-NPi, ecoinvent 3.12 cutoff and encrypted IAM
inputs. They retain the step-3 code/data baseline except for the documented
compression changes. Build records include current Python source, workbook,
IAM and private-inventory hashes; the persistent user Brightway databases are
not written.

.. list-table:: Completed checks
   :header-rows: 1

   * - Check
     - 2020
     - 2050
   * - Activities
     - 42,564
     - 42,574
   * - Marked FCEV services checked
     - 147 (80 cars, 67 trucks)
     - 147 (80 cars, 67 trucks)
   * - Locations
     - 14, including World and RER
     - 14, including World and RER
   * - Changes outside vehicle compression electricity
     - 0
     - 0
   * - Validation errors / warnings
     - 0 / 401
     - 0 / 398

Warning identities and multiplicities match the preceding builds. Inherited
warnings remain recorded; they are not claimed to be resolved here. The audit
independently calculates the ideal-gas compression requirement, compares every
marked service's electricity/H2 ratio, follows the actual delivery chains and
verifies repeated helper execution leaves all numerical coefficients unchanged.
All hydrogen purchases, CO2, other pollutants, upstream recipes and hardware
coefficients are unchanged relative to the preceding builds. The full-database
scope comparison uses relative tolerance 1e-11 and absolute tolerance 1e-18.

The expanded suite passes **365 tests**, including **23 new hydrogen cases**.
They cover cars/trucks, factors 1/0.8/1.2, compact exchange mappings, uncertainty,
merged auxiliary electricity, avoiding double scaling, missing IAM efficiency,
legacy inventories, invalid inputs, split providers, forwarders, validation and
real Excel import of all 15 templates. Temporarily disabling final compression
handling makes all 12 parametrized integration cases fail, including missing
records at factor one. These runtime mutations were not written to source.
Separately, 52 focused shared-utils tests passed before committing the earlier
evaporation/cold-start corrections; this step changes no core carculator model.

Reproduction and files
----------------------

From the carculator_utils checkout, with the documented Python 3.12 environments::

    python dev/install_premise_hydrogen_compression.py
    python dev/build_premise_vehicle_hydrogen.py --year 2020
    python dev/build_premise_vehicle_hydrogen.py --year 2050
    python dev/audit_premise_vehicle_hydrogen.py

The installer and builder refuse to overwrite completed receipts. The builder
requires an isolated copy of the private Brightway source project and authorized
IAM access. Complete background inventories and frozen raw vehicle exports stay
outside the committed report artifacts.

* ``workbook_installation.json`` and ``template_compression_changes.csv`` record
  the 15 template changes and file hashes.
* ``build_*.json`` and local ``validation_*.json`` record full scenario checks.
* ``vehicle_compression_comparison.csv`` gives all 294 before/after results.
* ``changed_electricity_exchanges.csv`` records the changed coefficients.
* ``hydrogen_delivery_boundary.csv`` records the reached pipeline boundaries.
* ``verification_summary.json`` records the independent checks.
* Local ``tests.log`` and ``mutation_tests.log`` retain test evidence.

Step 4 of the `remediation plan
<../premise_vehicle_2050_audit_20261013/remediation_plan.html>`_ is complete.
The next issue is PHEV physical-capacity aggregation. Future constant-range
sizing, remaining hardware/provenance work and the final controlled EF 3.1
comparison remain open.
