Release notes
=============

1.3.7
-----

Recent inventory corrections in this release:

* Use the corresponding petrol/diesel engine's existing deterioration factors
  for hybrid hot exhaust, consistently with hot-factor lookup. Preserve the
  vehicle-mileage basis and PHEV mode weighting. See :doc:`hot_emission_audit`
  for the limits of this combustion-engine ageing proxy.
* Correct FCEV buffer power and car pack mass accounting. The net fuel-cell
  contribution plus battery power now equals the model's vehicle power.
  Starter sizing preserves this power in trucks and buses. Their existing
  energy-based capacities are retained; this is not a validation of cell
  peak-power capability or a new powertrain calibration.
* Follow actual inventory links when replacing fuel-production electricity,
  including expanded upstream supply chains. Preserve embedded electricity in
  suppliers characterized only through background coefficients.
* Exclude aggregate hydrocarbon totals from inventories and carbon balances
  where the individual species are already counted; assign rural exhaust to
  immediate non-urban air.
* Correct shifted LCIA metadata fields and the units of fossil resource
  scarcity, ionising radiation and freshwater ecotoxicity without rescaling
  verified coefficients. The metadata's ``method`` now names the method group;
  use ``indicator`` for the assessment level. See :doc:`lcia_metadata`.

When upgrading from an earlier version:

* Create a Python 3.12 environment and install the updated package as described
  in :doc:`installation`. Use matching versions of the vehicle packages.
* Background coefficients now use premise 2.5.4 and ecoinvent 3.12 cutoff;
  see :doc:`background_rebuild`. Exports default to 3.12. Legacy targets
  reject suppliers without verified older links.
* Rename custom battery selections from ``NMC-523`` to ``NMC-532``. This uses
  the actual 5:3:2 inventory; existing physical and cost assumptions carry forward.
* Recalculate saved scenarios: changes to energy accounting, battery sizing,
  costs and emissions can affect results.
* Select a supported background scenario: ``SSP2-NPi``,
  ``SSP2-PkBudg1000``, ``SSP2-PkBudg650`` or ``static``. Older ``1150`` and
  ``500`` pathway labels are no longer accepted.

The :download:`changelog <../CHANGELOG.md>` lists the changes in each version.
See :doc:`validity` for calibration evidence and the scope of model validation.
