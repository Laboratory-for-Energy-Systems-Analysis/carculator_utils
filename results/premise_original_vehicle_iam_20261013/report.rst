Recovery of vehicle intensity series from original REMIND scenarios
===================================================================

The original REMIND 3.5.2 scenarios contain the technology-specific energy
intensities needed for most of the current car and truck mappings. Their
absence from the installed Premise input is a filtering omission. This is a
read-only investigation: no scenario, mapping, vehicle inventory or external
notebook was modified.

Source identification and filtering
-----------------------------------

The original directory is the user's ``IAM-ecoinvent`` folder. Fifteen MIF
files were inspected: all twelve originals in ``remind 3.5.2``, plus the
SSP2-NPi cases in ``remind 3.5``, ``old/remind 3.2`` and ``remind 3-5-MagPie``.

The installed encrypted ``remind_SSP2-NPi.csv`` (SHA256 beginning
``3a9f77641a1cf287``) matches every retained region/variable/unit identity
and numerical year value in
``remind 3.5.2/allocated/REMIND_generic_SSP2-NPi2025_feedstock_filtered_filtered.csv``:
32,992 rows and 626,848 year cells, using relative tolerance 1e-10 and absolute
tolerance 1e-12 for decimal parsing differences. Of those cells, 626,642 are
also exactly equal as parsed floating-point values. The original 3.5 file has materially
different values and is not a suitable source for filling this 3.5.2 input.
Full hashes and comparisons are recorded in ``source_audit.json``.

The 3.5.2 NPi original and its feedstock-allocated MIF each contain 2,702
``Energy intensity|...`` rows, of which 212 are in EUR. Both filtered CSV
stages and the installed input contain zero. The filtering code in
``encryption/encryption.ipynb``, cell index 6 (zero based), retains variables
whose names start with a prefix from ``l_var``. It includes ``Efficiency``
but omits ``Energy intensity``. These are different prefixes. The stored
notebook is currently configured for IMAGE; its generic whitelist explains
the observed omission, but its present state is not an execution log proving
which historical run produced each REMIND output.

Recovered coverage and remaining regional gap
---------------------------------------------

For EUR in the matching 3.5.2 SSP2-NPi2025 original:

* 25 of the 30 declared REMIND car mappings have an exact corresponding
  ``Energy intensity`` variable, measured in MJ/vehkm, with finite positive
  values in both 2020 and 2050. This covers five size groups and BEV, FCEV,
  compressed gas, hybrid electric and liquid-fuel technologies.
* All 20 declared REMIND truck mappings have such a positive intensity pair.
  This includes the ten BEV/FCEV cases whose 2020 aggregate FE/ES ratio was
  undefined. Their modeled intensity is available even without fleet service.
* The five separate ``Large Car`` mappings remain absent in EUR. That class
  exists in CAZ, LAM, OAS, USA and World. EUR has ``Large Car and SUV``.
  The earlier assertion that the separate class was absent from the file
  should have been qualified as absent from EUR. This regional distinction
  is present in the original and is not caused by filtering.
* The five car and eighteen truck mapping entries that declare no REMIND
  service alias are outside these denominators. Recovering direct intensities
  does not supply native IAM pathways for all proxy technologies.

The same 25/30 car and 20/20 truck EUR intensity coverage, with positive
2020/2050 values, is present in all twelve inspected 3.5.2 scenarios, including
the EU21 files. The checked 3.5 and MagPie cases have fewer matching car size
categories (15/30); the old 3.2 case has none of these exact intensity aliases.
See ``coverage_summary.csv`` and ``coverage.csv``.

For example, the recovered medium BEV variable is
``Energy intensity|Transport|Pass|Road|LDV|Four Wheelers|Medium|Midsize Car|BEV``.
The same hierarchy has ``FCEV`` and ``Hybrid electric`` variants. No invented
FE variable or allocation of pooled Electricity/Liquids demand is needed to
obtain their total energy-intensity trend.

.. list-table:: EUR SSP2-NPi2025, raw 2050 change relative to 2020
   :header-rows: 1

   * - Vehicle mapping
     - Energy per vehicle-km change
   * - Medium BEV car
     - -18.84%
   * - Medium FCEV car
     - -32.43%
   * - Medium hybrid-electric car
     - -27.00%
   * - Medium liquid-fuel car
     - -22.50%
   * - Medium compressed-gas car
     - +14.25%
   * - 40 t BEV truck
     - -25.46%

These are source ratios, not final Premise multipliers. Premise currently
imposes monotonic improvements and caps the relative vehicle efficiency index
at 1.25, equivalent to at most a 20% energy reduction. A source intensity
increase is also affected by that policy. Neither policy was changed here.

Interpretation and proposed correction
--------------------------------------

The current primary reporting implementation identifies ``Energy intensity``
as a fleet-level quantity: new-vehicle energy intensities are weighted across
construction years. It explicitly retains modeled intensities for technologies
with no fleet demand. See
`reportBaseVarSet <https://github.com/pik-piam/reporttransport/blob/master/R/reportBaseVarSet.R>`_
and
`reportFleetVariables <https://github.com/pik-piam/reporttransport/blob/master/R/reportFleetVariables.R>`_.
These are corroborating current sources; the precise reporting commit used
for the local MIF export is not established. The original MIF files checked
here do not include separate ``Energy intensity sales`` or load-factor series.
Use the recovered signal as a fleet technical trend, not as proof of a new
2050 vehicle's physical specifications.

The reporting implementation also splits hybrid final energy into electricity
and liquids before aggregating carrier totals; see
`reportFinalEnergy <https://github.com/pik-piam/reporttransport/blob/master/R/reportFinalEnergy.R>`_.
Changing a BEV FE alias to total Electricity can therefore mix BEV and hybrid
energy. A hybrid's direct intensity provides its total trend; it does not
independently provide electric-mode and combustion-mode engineering inputs.
The local MIF does not expose the electric-share parameter as a separate series.

The concrete correction should:

1. Preserve the relevant ``Energy intensity`` rows from the matching original
   scenario through filtering and encryption, with version/hash provenance.
2. Map car and truck intensity separately from transport volumes and fuel
   markets. Normalize energy intensity as ``I(year) / I(2020)``. Where Premise
   expects an efficiency index, supply its inverse. Merely passing the new
   names as ``efficiency_labels`` is insufficient: the current generic method
   only recognizes names containing ``specific`` for explicit-label inversion.
3. Keep absent region/class cells explicit. An EUR Large Car intensity proxy
   from Large Car and SUV would need a documented rule; sharing an intensity
   must not duplicate its fleet volume. Native Large Car regions should keep
   their own data.
4. Retain and expose the existing efficiency cap and monotonicity policy
   unless separately reviewed. Add regressions for data retention, direction
   of intensity conversion, absent regional cells, positive modeled intensity
   with zero fleet activity, and hybrid carrier separation.
5. Resume constant-range hardware calibration using the recovered signals.
   The broad carculator fallback question is superseded for the 25 represented
   car mappings and 20 truck mappings. Calibration, unsupported regional
   classes and unmapped proxy technologies still need their explicit treatment.

Reproduction
------------

Run ``dev/audit_premise_original_vehicle_iam.py`` with the Python 3.12 Premise
environment. The script accepts ``--source`` and ``--output``. It compares
the encrypted installed scenario in memory, checks unique identities before
comparison, excludes unresolved duplicate identities in the intermediate
filtered file, and verifies the final filtered file against all installed
rows. It never writes to the original directory or exports raw time series.

This audit requires no numerical model regression run because runtime code
and inputs are unchanged. The executable audit completed successfully and
records its own hash plus all source file hashes.
