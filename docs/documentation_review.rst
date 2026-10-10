Documentation review, 10 October 2026
======================================

Scope
-----

This review covered the five packages' documentation entry points, installation
and usage examples, methodology chapters, current calibration and validation
pages, recent assumption/repair guides, API pages, README files and release
information. Stored research data, downloaded sources and historical run logs
were retained. A dated audit is evidence of that run, not a report of the current
aggregate test suite.

The reader-facing changes add definitions, units, a reading order and validation
examples. Detailed sources and equations remain available. Historical figures
and tables are identified as such rather than silently relabelled as new results.

Checks against implementation
------------------------------

* Fuel energy is in kWh when mass in kg is multiplied by MJ/kg and divided by
  3.6. Wheel force must be multiplied by speed and integrated before it is energy.
* Battery charge and discharge efficiencies multiply for round-trip efficiency.
  Stored energy, terminal DC and purchased AC electricity are distinct outputs.
* Sulfur content is kg S/kg fuel; the SO2 conversion uses the molar-mass ratio
  of SO2 to sulfur. Noise powers are summed before logarithmic conversion.
* Cars use distance- and year-based battery replacement factors; trucks use
  fractional throughput-based factors without a compulsory pack. Buses retain
  their deliberate minimum of one replacement. Two-wheelers allow zero.
* Truck sizing tests available payload at 1% relative tolerance; bus sizing
  tests driving mass at 0.1%, per active vehicle/year/sample. The bus peak-load
  diagnostic and legacy charging-schedule check are not its gross-mass flag.
* Petrol two-wheelers use a complete scooter manufacturing proxy, including
  engine, tank, delivery and disposal. The documentation must not add these
  suppliers separately. Current two-wheeler energy use is cycle-based.
* A has sample/product/activity/year axes. B contains precomputed impact
  coefficients, not raw biosphere exchanges. Current background and export
  defaults use ecoinvent 3.12 cutoff and the supported scenario labels.
* Repeated model runs and seeded projected costs follow their repaired input
  handling. Additional methane leakage defaults to zero; supplier and exhaust
  losses remain. The default exhaust-carbon calculation is not a closed
  elemental balance.

The review corrected narrative equations and API documentation; it did not
change model equations, parameter tables or inventory coefficients.

Validation figures
------------------

The new :doc:`validation_examples` pages show recorded energy comparisons and a
separate background-update comparison. Nine new bar charts are generated from
saved numbers; the ADAC-cycle and truck diagnostic figures are reused unchanged.
Every new plot starts its value axis at zero and identifies its units and two
series. CSV values and source-file checksums accompany the figures. Source
measurements, calibration inputs, held-out cycles and screening comparisons are
explicitly distinguished. No new empirical calibration is claimed.

Build and example checks
-------------------------

All five sites built with Sphinx 9.1.0 on Python 3.12.13, using matching source
checkouts and treating warnings as errors. The first build exposed an old
installed shared package in the documentation environment; the verified builds
explicitly selected the five current checkout paths.

The scan covers 94 top-level narrative RST pages, plus README/release material
and the historical developer records. All 30 explicitly marked Python code
blocks parse successfully. The shared quick start runs, and all four vehicle
quick starts complete model, inventory and finite LCIA calculations. Repeating
each vehicle's ``set_all()`` preserves its energy result. This is a targeted
example check, not a new full release qualification or empirical validation.

Source-file checksums, climate percentage arithmetic and matching copies of
plot data were checked. A syntax-tree comparison confirms that the truck Python
edit changes docstrings only. Existing staged changes were preserved in all five
repositories. See the :download:`machine-readable verification record
<_static/documentation_review_20261010.json>`.

From each repository, using an environment with matching packages installed::

   python -m sphinx -E -b html -W --keep-going docs /tmp/REPOSITORY-docs-html

Use a different output directory for each repository. Historical results were
not regenerated, external websites were not re-audited, and numerical model
assumptions were not changed by this documentation review.
