Vehicle inventory remediation: campaign closed
================================================

The user closed the fixing campaign on 14 October 2026. This replaces the
running plan. The implementation and final verification are described in
``../../docs/premise_vehicle_update.rst``. Historical planning and step-by-step
records remain available at pre-cleanup Git revision ``862bc96``.

Completed work
----------------

* Regenerated 2020 cars and Regional-delivery, 400 km trucks while retaining
  selected service identities, explicit powertrain proxies and source metadata.
* Corrected CNG delivered-energy accounting and regional compression sequencing;
  final-supplier fossil/non-fossil CO2; hydrogen tank compression scaling.
* Replaced pollutant clamping with species-aware diagnostics, preserved
  distance/start-related emission drivers and corrected hybrid deterioration.
* Restored mapped IAM intensity signals and approved relative efficiency fallback.
* Preserved BEV/PHEV range with simple battery capacity/mass arithmetic and
  increased BEV truck payload at fixed utilization.
* Corrected PHEV physical capacity, mode consistency, purchase costs and
  replacement arithmetic; calibrated 2020 car PHEV mass/capacity pairs.
* Added finite HEV truck storage and calibrated FCEV electrical allocation,
  small-truck motor proxies and car/truck battery references.
* Preserved original-model and component sources through generation, regional
  transformation and saved Brightway metadata.

The final full 2020/2050 builds have zero validation errors and unchanged
warning identities. Fuel/carbon, battery allocations, retained future hardware
and saved metadata pass. Final car/truck buffer reports and incremental EF 3.1
results are retained in the adjacent result folders.

Accepted boundaries at closure
--------------------------------

Buses and two-wheelers were not regenerated. MIX capacity markets remain
approved manufacturing proxies where physical pack mass or chemistry differs.
Car charging/continuous-output limits and truck hot-NOx coefficient derivation
remain unverified. The broader PHEV cycling review and future FCEV tank resizing
were skipped. A full original-legacy-versus-final catalogue LCIA comparison
was not completed; the incremental comparisons do not substitute for it.

These boundaries are recorded rather than left as active remediation tasks.
No new package release or scientific-validation claim is made by closing the
campaign. Cleanup preserves the installed inventories, regression tests and
maintained generation inputs.
