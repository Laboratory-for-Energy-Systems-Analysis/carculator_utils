Impact indicators and their units
=================================

B-matrix rows are impact indicators; columns follow the inventory input labels.
A background supplier's column contains its upstream impacts per unit purchased.
An elementary-flow column contains characterization factors per unit emitted or
extracted. Activities whose recipes are expanded in A have zero direct B columns:
their impacts come through the inputs to those recipes. B is therefore not a
matrix of raw elementary emissions. Solving A gives the required input amounts;
multiplying B by those amounts gives impacts per vehicle-kilometre. Passenger-
and tonne-kilometre results then divide by the selected passenger or cargo load.

``get_dict_impact_categories(method, indicator)`` returns metadata in the same
category order as B. Its records contain the method group, assessment level,
source, category, indicator type, abbreviation and unit, using the seven columns
of ``data/lcia/dict_impact_categories.csv``. Category labels, including existing
spaces, remain unchanged so labelled selections and matrix positions stay aligned.

The unit describes the impact indicator, not the functional unit. For example,
``kg CO2-Eq`` becomes kg CO2-equivalent per vehicle-km when the functional unit is
``vkm``. Several indicators need particular care:

* ReCiPe midpoint fossil resource scarcity is measured in **kg oil-equivalent**.
  It is a different indicator from cumulative energy demand in MJ. The
  `ReCiPe methodology, section 13.3
  <https://www.rivm.nl/bibliotheek/rapporten/2016-0104.pdf>`_ defines this indicator
  from fossil resources' energy content relative to crude oil.
* ReCiPe midpoint ionising radiation uses **kBq Co-60-equivalent**. Its numerical
  coefficient is not expressed in kilograms or Bq without the kilo prefix.
* EF freshwater ecotoxicity, including its organic-substance component, uses
  **CTUe**, comparative toxic units for ecosystems.

The inventory audit identified shifted CSV fields and incorrect or missing
labels for these units. The correction changes the metadata, not the verified
numerical coefficients. Existing category identifiers and row ordering are
preserved. The cached ethylene factors use the same corrected unit labels, with
their numerical amounts unchanged. Code that previously interpreted ``method``
as the assessment level should now use ``indicator``; ``method`` identifies the
method group.

Coefficient builds compare every mapped row's declared unit against the selected
Brightway method metadata before calculation. A mismatch stops the build rather
than silently changing units or scaling values. Only explicit spelling synonyms,
such as ``cubic meter`` and ``m3``, are accepted. Custom noise indicators have no
matching Brightway methods and retain separately documented units; this check
does not independently validate their characterization factors.
