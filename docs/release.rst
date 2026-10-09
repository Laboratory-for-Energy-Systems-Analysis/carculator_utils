Release notes
=============

1.3.6
-----

When upgrading from an earlier version:

* Create a Python 3.12 environment and install the updated package as described
  in :doc:`installation`. Use matching versions of the vehicle packages.
* Background coefficients now use premise 2.5.4 and ecoinvent 3.12 cutoff;
  see :doc:`background_rebuild`. Exports default to 3.12. Legacy targets
  reject suppliers without verified older links.
* Rename custom battery selections from ``NMC-523`` to ``NMC-532``. This uses
  the actual 5:3:2 inventory; existing physical and cost priors carry forward.
* Recalculate saved scenarios: changes to energy accounting, battery sizing,
  costs and emissions can affect results.
* Select a supported background scenario: ``SSP2-NPi``,
  ``SSP2-PkBudg1000``, ``SSP2-PkBudg650`` or ``static``. Older ``1150`` and
  ``500`` pathway labels are no longer accepted.

The :download:`changelog <../CHANGELOG.md>` lists the changes in each version.
See :doc:`validity` for calibration evidence and the scope of model validation.
