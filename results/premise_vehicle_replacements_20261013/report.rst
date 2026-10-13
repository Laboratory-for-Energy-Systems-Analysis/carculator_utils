PHEV battery replacement accounting
===================================

13 October 2026. Remediation-plan step 6.

Status
------

The passenger-car lifetime policy, shared physical-count correction and truck
net-energy arithmetic correction are implemented. At the user's request to
commit and proceed, the tested correction is committed with its existing
net-energy boundary. This does not select or implement the separate proposal
to include regenerative cycling. That modelling question remains open and will
be revisited with hybrid traction storage. The corrected arithmetic is complete;
the broader battery-use review in step 6 remains open.

Passenger cars
--------------

The electric-mode PHEV battery was missing its distance-life input. Its zero
default produced a nonfinite distance-based replacement calculation, which the
legacy finite-value conversion reduced to zero. The combustion intermediate
had the 200,000-km assumption, so the combined vehicle could also inherit a
driving-share-weighted fraction of that intermediate's replacement count.

The user approved 200,000 **total vehicle-km** and the existing 18-year limit.
The electric intermediate is now included in the seven existing distance-life
parameter records; their values, uncertainty and source metadata are unchanged.
One physical pack's replacement count is calculated as::

    max(0, vehicle lifetime km / 200000 - 1,
           vehicle lifetime km / annual km / 18 - 1)

That count belongs to both driving modes before their costs are calculated and
is retained when assembling the combined vehicle. It is not multiplied by
electric driving share. At 200,000 km and 12,000 km/year, the 2020 car PHEVs still
have zero replacements, so their inventory coefficients are unchanged. Comments
and parameter/provenance companions now state the lifetime policy.

Regression cases independently check a 300,000-km vehicle driven 20,000 km/year
(0.5 replacements) and a 72,000-km vehicle driven 2,000 km/year (1 replacement),
at electric shares 0, 0.5 and 1. Both petrol and diesel PHEVs, replacement costs,
labelled samples and caller-owned inputs are covered. All three parametrized
cases failed before the correction and pass afterward.

The source commits are ``1e97290`` in carculator_utils and ``dc0fc4c`` in
carculator; the truck arithmetic fix is ``e49c0d8`` and the Premise inventories
and integration regressions are ``0be3f03``. Matching sibling checkouts are
needed for these changes together. Generation records capture the source
hashes used before these commits were created.

Truck arithmetic defect
-----------------------

The inherited calculation assigned the electric intermediate the vehicle's
entire lifetime travel, subtracted one initial pack, clipped the count, and
then multiplied that replacement count by electric driving share during mode
aggregation. Subtracting the initial pack and applying the three-replacement
cap before usage weighting is mathematically different from applying those
operations to actual lifetime battery use.

For a 40 t Regional-delivery PHEV, the current defaults are 710,000 lifetime km,
15% electric travel, a 60-km electric leg at 80% depth of discharge, nominal
capacity 77.323265 kWh, and 3,000 equivalent full cycles per pack. Under the
inherited net-energy approximation, lifetime electric travel is 106,500 km and
uses 1,420 nominal-capacity cycles. A pack serves 225,000 electric km. The old
0.323333 replacement factor therefore becomes zero when the initial pack is
subtracted once at the correct stage. At 50% electric travel, the same
approximation yields 0.577778 replacements, rather than a usage-weighted count
calculated before subtracting the initial pack.

The correction sets electric utility factor before replacement
calculation, weights lifetime use before subtraction/clipping, and copies the
one physical replacement count into both driving-mode costs. Nonzero explicit
inputs remain whole-pack replacement counts. Conflicting nonzero values for
the same physical pack are rejected. Zero continues to request automatic
calculation. The existing fractional allocation, three-replacement cap and
absence of a separate truck calendar-life model are retained.

Regenerative cycling is a separate unresolved boundary
-------------------------------------------------------

Net stored-energy use subtracts recuperation. It consequently omits repeated
charging and discharging during braking and acceleration, including use in
combustion mode. That omission is material for the larger PHEV trucks.

``dev/audit_phev_replacement_inputs.py`` adds the modelled reusable regenerative
energy from both driving modes as a diagnostic, using the physical pack's
discharge efficiency and weighting each mode by its travel share. It is a
cycle-energy-balance sensitivity, not a calibrated battery-current trace or
state-of-health prediction. The four large-truck cases checked separately use
only 17--19% of positive combustion-mode wheel work as regenerative credit, so
their existing positive-propulsion credit cap is not binding.

.. csv-table:: Net-energy correction and regenerative-cycling sensitivity
   :header: "Size", "Old replacements", "Corrected net-energy replacements", "Regeneration-inclusive EFC", "Sensitivity replacements"

   "3.5 t", "0.0313", "0", "847.83", "0"
   "7.5 t", "0.1147", "0", "1537.23", "0"
   "18 t", "0.0600", "0", "1435.97", "0"
   "26 t", "0.2367", "0", "3027.72", "0.00924"
   "32 t", "0.3233", "0", "3736.00", "0.24533"
   "40 t", "0.3233", "0", "3788.00", "0.26267"
   "60 t", "0.3233", "0", "4165.34", "0.38845"

The detailed inputs are in ``truck_replacement_inputs.csv``. These figures
retain the model's existing cycle-life assumptions. The nominal-capacity EFC
basis follows the cited experimental convention: cumulative discharged
capacity is divided by nominal capacity. Depth of discharge is already used
in the range/storage calculation and is not applied again as an extra divisor.
Preger et al. (2020), *Journal of The Electrochemical Society* 167, 120532,
defines this convention and evaluates chemistry and operating-condition
effects (`DOI <https://doi.org/10.1149/1945-7111/abae37>`_,
`full text <https://onefiniteplanet.org/wp-content/uploads/2024/02/Preger_2020_J._Electrochem._Soc._167_120532.pdf>`_).
The model's numerical 3,000-cycle default is retained; it is not a new fitted
estimate or a claim of a universal measured PHEV pack life.

Integration checks
-------------------

The net-energy correction was freshly generated and installed with private
rollback copies. All 162 car and 127 truck dataset identities are preserved.
Only the seven truck PHEV production battery purchases change materially;
vehicle masses, operation and all other inventory coefficients are unchanged.
The 40 t lifetime battery purchase falls from 102.324451 to 77.323265 kWh under
this calculation. Both battery supply and end of life remain included once in
Premise's capacity markets.

Fresh REMIND SSP2-NPi / ecoinvent 3.12 cutoff builds passed the following checks:

.. list-table:: Full database checks
   :header-rows: 1

   * - Year
     - Activities
     - Errors
     - Existing warnings
     - CO2 checks
     - H2 checks
   * - 2020
     - 42,564
     - 0
     - 401
     - 495
     - 147
   * - 2050
     - 42,574
     - 0
     - 398
     - 495
     - 147

Warning identities are unchanged from the preceding PHEV-capacity builds.
All seven battery purchase differences reproduce the workbook changes in both
years. Other numerical differences are floating-point roundoff, bounded in
``verification_summary.json``. Full inventories and Brightway storage remain
private temporary artifacts.

Focused checks passed: 85 shared/family tests, 85 truck tests, 16 car tests,
one additional positive-replacement inventory/LCIA test, and 51 Premise tests
(238 cases across these runs). The installed-artifact family verification also
completed successfully: 1,377 utils, 77 car, 151 truck, 43 bus and 100 two-wheeler
tests, for **1,748 passing tests**, with no failures, errors or skips. Wheels
and wheels rebuilt from source distributions passed resource-hash checks and
matching offline model/LCIA smoke checks in fresh core-only environments.
``installed_artifact_verification.json`` records the artifact hashes, counts and
confirmation that the tested model/input bytes match the current sources.
This is a local macOS/Python 3.12 check, not a cross-platform CI claim. It does
not verify a later change to a regeneration-inclusive calculation.

Remaining work
---------------

Truck HEV traction storage is the next investigation. Resolve the truck cycling
choice before claiming that the replacement model accounts for all battery use.
The complete old/new EF 3.1 comparison remains later in the remediation plan.
The earlier PHEV capacity fix
also explicitly left mode-specific vehicle mass reconciliation for the
hardware/future-sizing work; this replacement calculation does not resolve it.
