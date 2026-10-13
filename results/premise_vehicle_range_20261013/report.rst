Prerequisites for constant-range future vehicle sizing
======================================================

The approved policy retains each car's baseline range and the truck 400 km
range, with consistently resized hardware. The user has also approved
Premise's density projection for the original BEV/PHEV chemistry, retaining
the high-power HEV specifications separately. This audit changes no installed
inventory or modelling parameter.

The preceding emission-driver correction is committed and validated in
``../premise_vehicle_efficiency_20261013/report.rst``. It removes blanket
IAM energy scaling of HBEFA and refrigerant emissions. Constant-range
hardware implementation remains open; the probes below identify required
scientific choices before implementing it.

Exact IAM-variable and unit audit
---------------------------------

The checked input is the same encrypted REMIND SSP2-NPi file used in both
controlled scenario builds, SHA256 beginning ``3a9f77641a1cf287``. These
findings concern that file and the current mappings, not every REMIND release.

* Of 35 car mapping entries, 30 declare REMIND service aliases. Only 10 have
  both their exact service and energy aliases in the file. The other five
  entries have no declared REMIND mapping and are not unexpected missing data.
* The existing mappings request FE variables ending in BEV, FCEV and
  Hybrid electric that are absent. Carrier-level Electricity and Hydrogen
  labels are present, but their existence alone does not establish a matching
  technology-specific numerator, especially for BEV/PHEV electricity.
* The requested Large Car class is absent: the file uses Large Car and SUV.
  Sharing this signal between templates or splitting fleet volumes needs an
  explicit rule; duplicating a combined fleet total would overcount service.
* All 25 available car service aliases use billion passenger-km/year.
  The file contains 120 detailed four-wheeler ES series in passenger-km and
  no corresponding VKM series. The mapping-file comment claiming vehicle-km
  is not evidence of the input unit.
* All 20 declared REMIND truck mappings have exact service/energy labels.
  However, ten BEV/FCEV pairs have a zero 2020 numerator or denominator in
  EUR; a direct 2050/2020 intensity ratio is undefined. Existing Premise
  processing backfills missing intensities from later years before
  normalization. The resulting index is not an observed 2020 intensity.
* The remaining 18 truck mappings declare no REMIND signal. This includes
  proxy technologies and hybrids; absence must remain visible.

``get_iam_efficiencies`` currently substitutes ones when required aliases are
missing. It backfills/fills missing ratios, normalizes to 2020, applies its
monotonicity policy, and limits the vehicle efficiency index to 1.25.
``find_iam_efficiency_change`` also substitutes one for a nonfinite result.
Consequently a factor of one does not distinguish no projected change from
missing input. A raw ratio in the audit CSV is not necessarily the factor
eventually applied by Premise.

Passenger-service intensity can reflect occupancy as well as vehicle energy
use. Applying its relative change to a fixed-occupancy vehicle is an explicit
transfer assumption, not a reconstruction of vehicle-km intensity. REMIND's
public reporting source distinguishes ES in passenger-km and VKM after
division by load factor; its FE names use energy carriers. See
`REMIND reporting source <https://github.com/pik-piam/remind/blob/master/R/reportEDGETransport.R>`_.
That public source is corroborating methodology, not proof of the exact
software revision that generated the local scenario.

Native-model sizing probes
--------------------------

The probe uses matching local 2020 carculator sources, Swiss climate, the
Regional delivery truck cycle and the approved NMC-622 cell density of
0.26 kWh/kg for 2050. It first sizes a candidate pack from the existing IAM
energy factor, then lets the native model reconverge mass and power without
forcing its energy trace to match that factor. All runs retain the baseline
range objective, duty, load and lifetime; reported ranges below are the
actual capacity/energy result, not a claim that the objective was met.

.. list-table:: EUR 40 t BEV, candidate pack 440.692 kWh
   :header-rows: 1

   * - Diagnostic case
     - Pack mass, kg
     - Stored energy, kJ/km
     - Actual range, km
   * - Original 2020, 550.865 kWh
     - 3278.96
     - 3966.23
     - 400.00
   * - Smaller pack and approved density only
     - 2421.38
     - 3892.84
     - 326.03
   * - Plus native 2050 drag/rolling/drivetrain inputs
     - 2421.38
     - 3291.19
     - 385.63
   * - Native 2050 hardware inputs, baseline duty/load/lifetime
     - 2421.38
     - 2913.52
     - 435.62

The existing IAM factor is 0.8. With unchanged charging efficiency it targets
3172.98 kJ/km. Merely setting nominal capacity to 0.8 times the baseline does
not reproduce that energy demand in the physical model. Applying all native
future engineering assumptions would overshoot the IAM improvement. The
physical model must be calibrated once against the intended final energy
boundary, with bounded convergence and no second independent IAM multiplier.
If charging efficiency changes, grid and stored-energy targets must be
reconciled explicitly before sizing nominal capacity.

The Large BEV car currently receives a factor of one because its requested
aliases are missing. Its 2020 pack is 97.44 kWh and baseline range 466.17 km.
The approved density alone raises physical range to 471.65 km with unchanged
capacity; native future hardware assumptions raise it to 537.41 km in this
diagnostic. These are not approved final future inventories.

Pending scientific choices
--------------------------

Two specific questions were sent to the user:

1. Where a technology-specific IAM signal cannot be recovered without an
   unsupported energy split, use explicitly documented native carculator
   technical projections, retain 2020 efficiency, or obtain additional IAM
   technology data. Correct unambiguous aliases first; a fallback must not
   conceal a repairable mapping error.
2. For a valid IAM target, calibrate the extent of the native aerodynamic,
   rolling-resistance, lightweighting and drivetrain projections, or retain
   2020 engineering with an explicitly lumped energy adjustment. The former
   can be bounded by the native physical assumptions and should expose
   infeasible targets rather than force a synthetic energy trace.

No dependent hardware changes have been installed while these choices remain
pending. The existing PHEV regeneration-lifetime question also remains
separate from the completed HEV buffer correction.

Reproduction and artifacts
--------------------------

``dev/audit_premise_vehicle_iam_boundary.py`` reads the same encrypted scenario
without printing its key or exporting raw time series. ``iam_alias_coverage.csv``
records exact aliases, availability, units and normalized ratios;
``available_passenger_variables.json`` contains names and units only.
``dev/probe_premise_constant_range.py`` runs the two small native model cases.
``engineering_probe.json`` and ``probe_sources.json`` record results and source
hashes. No full licensed inventory or private IAM payload is committed.
