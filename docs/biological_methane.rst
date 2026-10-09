Biological synthetic methane
=============================

``methane - synthetic - biological`` uses the bundled biological-methanation
production route with regional market hydrogen and CO2 captured from air.
The premise 2.5.4 / ecoinvent 3.12 refresh replaces the older direct PEM hydrogen
input with ``market for hydrogen, gaseous, low pressure`` (RER). Synthetic
methane therefore does not imply renewable or low-carbon hydrogen.
Previously, its supplier mapping silently selected sewage-sludge biomethane.
This correction applies to the shared fuel supply used by cars, buses and trucks;
the two-wheeler model has no methane powertrain.

The delivered-fuel activity
---------------------------

The production dataset ends at the methanation plant. It is not a complete
vehicle-fuel supplier. The packaged recipe in
``carculator_utils/data/fuel/supply_chains.yaml`` therefore constructs a separate
activity for one kg of delivered methane:

* 1.02 kg of biological-methanation product, retaining the existing gas-delivery
  template's 2% production allowance;
* 0.314 kWh of station electricity per kg delivered, for compression to 200 bar;
* the existing template's pipeline, fuelling-station infrastructure, heat and
  direct emissions, retained as delivery proxies.

The template is the bundled sewage-biomethane fuelling activity. Its gas
production input is removed entirely, and its 0.209889 kWh/kg electricity input
is replaced, not supplemented, by 0.314 kWh/kg. The latter comes from the
`BioCat II life-cycle analysis, January 2017, Annex I, page 15
<https://carbonstorage.io/media/project_files/Biocat_Life_Cycle_Analysis.pdf>`_,
which attributes the station assumption to Audi AG. This is a specified
compression scenario, not a measurement applicable to every station.

Per kg of production, the existing biological-methanation activity requires
0.5 kg hydrogen, 2.75 kg captured CO2 and 1.55 kWh plant electricity, plus
nutrients and wastewater treatment. Station compression is additional to that
plant electricity and to the upstream hydrogen and air-capture supply chains.
Explicit foreground electricity purchases follow the fuel-preparation mix;
the hydrogen market is a background supplier characterized in B and retains
its background/scenario mix. The upstream inventories follow the refreshed
source recipes. See :doc:`background_rebuild`.

The recipe is instantiated only when its supplier tuple is selected. Explicit
user supplier-name overrides remain authoritative. Existing A/B matrix indices
are preserved; the new foreground activity is appended and receives impacts
through its exchanges. Exports carry the recipe's source and limitations.
Unselected fuel routes do not acquire this activity.

Fuel properties and atmospheric carbon
--------------------------------------

The lower heating value is 49.9 MJ/kg, as specified on page 15 of the BioCat
report. The complete-oxidation factor is 2.75 kg CO2/kg methane, consistent with
the stoichiometric methane basis of the bundled production activity. These
replace the generic gas values of 47.5 MJ/kg and 2.68 kg CO2/kg previously
inherited by this fuel label. Thus both fuel mass per unit combustion energy
and tailpipe CO2 may change for this selected route. Density remains
0.000717 kg/litre on the existing normal-volume convention.

Atmospheric carbon uses ``biogenic_share=1`` as the model's non-fossil accounting
flag; this does not mean that air-captured carbon is physically biogenic.
The air-capture activity already withdraws one kg of atmospheric CO2 per kg of
captured product. No second capture credit is added. Combustion releases
non-fossil CO2 based on fuel actually burned.

The bundled default ReCiPe climate category assigns zero to both atmospheric
CO2 uptake and non-fossil CO2 release. Its ``climate change w bio`` category
assigns -1 and +1 respectively. EF similarly excludes both flows from its
climate-change total. This avoids mixing an explicit capture credit with an
uncharacterized release. It does not make the whole supply chain carbon-neutral:
hydrogen, electricity, heat, infrastructure and methane emissions still matter.

Validation scope and remaining uncertainty
------------------------------------------

``tests/test_biological_methane.py`` completes 2025/2030 model and LCIA runs for
Medium gas cars, 13m-city gas buses and 40t long-haul gas trucks, with two load
samples, a pure synthetic fuel and a fossil/synthetic blend. Independent
expectations check production quantities, compression, hydrogen, atmospheric
CO2 capture, fuel purchases and fossil/non-fossil combustion CO2. Repeated
Brightway exports check supplier identity, amounts, provenance and preservation
of the original inventory. Core tests also check unchanged bundled indices,
delivery-template exchanges, explicit overrides and missing dependencies.

This validates the corrected supplier chain and its accounting, not the full
empirical representativeness of the production or distribution inventories.
In particular:

* The production dataset adapts BioCat operating data to an atmospheric-CO2
  route using stoichiometric hydrogen and CO2 inputs. Methanation-plant
  infrastructure is missing in that bundled production dataset.
* Delivery heat and direct emissions remain generic proxies. The inherited
  2% extra production requirement is not an explicitly balanced methane loss;
  it must not be interpreted as a verified carbon balance for distribution.
* Vehicle pump-to-tank leakage remains separate. Its fossil/non-fossil allocation
  and missing bus/truck emissions are corrected in :doc:`methane_leakage`.
  That correction also documents possible boundary overlap with this delivery
  proxy; it does not establish a new measured leakage rate.
* Complete-oxidation CO2 is separate from the CO, methane and hydrocarbon
  pollutant models; this is not a closed elemental exhaust balance.
* Electrochemical synthetic methane still raises the existing missing-supplier
  error. This repair does not establish a delivery mapping for that route or
  for alternative captured-carbon sources.

Run the focused checks with the sibling packages and export extras installed::

   CARCULATOR_REQUIRE_FAMILY=1 python -m pytest tests/test_biological_methane.py tests/test_fuel_mappings.py

Verification on 2026-10-08: 53 shared inventory/export checks and the passenger-car
package's broader fuel-blend test passed with the sibling source packages.
The shared wheel's isolated suite passed 272 tests and skipped 183 requiring
uninstalled sibling packages. Wheel/sdist resource hashes and core-only imports
passed the installation verifier. The documentation built successfully; the
full build retained 18 pre-existing API/docstring warnings.
