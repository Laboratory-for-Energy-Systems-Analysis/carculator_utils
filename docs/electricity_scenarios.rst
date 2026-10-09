National electricity data and scenarios
=======================================

The default electricity supply now combines observed national generation from
Ember with the Reference scenario of JRC's GECO 2025 release. Four electricity
scenarios are available offline, independently of the IAM scenario used for
background impact factors. The previous table remains available as ``legacy``.

This changes calculated electricity-related impacts. It does not recalibrate
vehicle mass, driving energy, range, battery replacements or costs.

Selecting and inspecting a scenario
-----------------------------------

Pass the same background configuration to any vehicle family's inventory::

    inventory = InventoryCar(
        model,
        scenario="SSP2-NPi",
        background_configuration={
            "electricity scenario": "geco-2025-reference",
        },
    )

    inventory.electricity_provenance
    inventory.electricity_mix.sel(
        combined_dim="Medium - BEV", year=2030, value=0
    )

The electricity scenario choices are:

* ``geco-2025-reference`` (default): GECO Reference projections.
* ``geco-2025-ndc-lts``: GECO national pledges and long-term strategies.
* ``geco-2025-1.5c``: GECO's 1.5-degree pathway.
* ``tyndp-2026-ntplus``: national TYNDP 2026 NT+ projections for all EU27
  countries; GECO Reference projections elsewhere. This is an explicit,
  draft target-compliant alternative to the default GECO Reference scenario.
* ``legacy``: the previous TYNDP 2020/TEMBA/WEO 2017 table, its original
  normalization and its truncated lifetime averaging convention.

These labels do not imply equivalence to ``SSP2-NPi``, ``SSP2-PkBudg1000`` or
``SSP2-PkBudg650``. Record both choices in a study. ``scenario="static"`` still
selects static background impact factors; it does not freeze generation shares.
The same country/year history is used in all four refreshed scenarios.

An explicit ``custom electricity mix`` retains its existing year-by-technology
shape and overrides generation shares for all selected vehicles and samples.
It works even for a country absent from the national dataset. Unknown countries
otherwise raise; an intentional geographic fallback can be specified with
``"electricity fallback country": "GLO"``. ``GLO`` is World, while ``RER`` uses
Ember Europe history and GECO EU27 projections. ``EU27`` selects the European
Union itself, with its own Ember EU history and matching EU27 projections.
``UK`` and the former table's ``NM``
are recognized as aliases for ``GB`` and ``NA`` respectively. Substitution is
reported, not silent.

Data and geographic meaning
---------------------------

The bundled snapshot contains 5,983 observed country/region-year records and
212 geographic codes. Historical coverage varies by country (the earliest
record is 1985); the most recent observations are from 2022--2025. The latest
years may include estimates. Each country's actual final historical year is
available as ``history_last_year`` in the background array and provenance.

See :doc:`electricity_coverage` for the full country/economy list, each retained
historical year range and its projection source. GECO has 27 country projections,
180 regional proxies and two World proxies, plus World, Europe and EU27 aggregates.
The TYNDP option raises country projection coverage to 54 by replacing the
27 EU regional proxies with national trajectories.

GECO supplies generation endpoints in 2030, 2035, 2040, 2050, 2060 and 2070.
Its public workbooks contain individual countries as well as regional groups;
EU member states, for example, use the EU27 regional projection. The geography
crosswalk follows the GECO report's Annex 1, tables 2--3, with separately
documented proxy extensions for territories not listed there. The published
China region includes Hong Kong and Macau.

When recent observations are unavailable, the last valid national observation
is held through the snapshot boundary (2025); these are imputed values, not
additional observations. Historical years therefore do not depend on the future
scenario. The 2025 anchor is joined to the next GECO endpoint by linear
interpolation of shares. Regional endpoints replace national shares at
that endpoint: this is an explicit regional proxy, not a country-level
downscaling model. Consequently, different countries using the same region
converge to its mix. A warning identifies these cases, and
``electricity_geographies.csv`` records every assignment. Missing history never
silently becomes the European average.

The array's annual endpoints are held outside available coverage. Lifetime
averaging includes all whole operating years, including those after 2070;
fractional lifetimes retain the earlier truncation convention. See
:doc:`electricity_lifetime`. Future technology impact factors are still taken
at the vehicle's manufacturing year and capped at the background matrix horizon
(2050). Extending generation to 2070 does not extend those background factors.

Source validation and explicit transformations
----------------------------------------------

The old table contained 139 rows whose raw shares differed from one by more
than one percentage point, including totals from 0.165 to 1.919. The refreshed
loader rejects nonfinite/negative shares, duplicate keys, unmapped columns and
unbalanced records. It only normalizes numerical rounding within 1e-7.

The source builder works from generation in TWh, preserving technology mass
balances before calculating shares. Aggregate rows, capacity, demand and trade
are not added to domestic generation. Absent Ember fuel rows can be zero only
when the independently reported total reconciles within source precision.

The inspected Ember snapshot has ten country-years with negative generation
and two with zero domestic generation. The ten negative records are excluded
only when ``--allow-history-exclusions`` is explicitly supplied. Each whole
country-year exclusion is listed in ``electricity_sources.json``. Values are
not clipped; remaining observations and subsequent interpolation are used.

The GECO workbooks' nine generation categories do not sum exactly to their
gross-generation totals. The build additionally uses
``--geco-other-residual``: the eight named fuel groups and reported gross total
are preserved, and ``Other`` is calculated as their residual. This is a modelling
assumption about which reported fields are authoritative, not a source-confirmed
explanation of the discrepancy. The reported Other amount, residual and surplus
are preserved for all 756 projection records in ``geco_2025_balance_audit.csv``.
Negative residuals or a residual materially larger than reported Other fail the
build. Source CCS subgroups are subtracted from their parent fuel category and
mapped separately, so they are not double-counted.

LCI proxies and remaining limitations
-------------------------------------

The Ember/GECO refresh uses the existing 21 background electricity activities. Coarse
source categories cannot recover all of their distinctions:

* Aggregate coal uses hard coal; gas uses the conventional gas activity.
* Hydro uses run-of-river; wind uses onshore wind; solar uses rooftop PV.
* Bioenergy and biomass/waste use wood CHP; biomass/waste CCS uses Biomass CCS.
* Other fossil uses oil; other renewables and GECO's reconciled Other category
  use geothermal as a coarse proxy.

These are explicit approximations, not assertions that each category consists
of that technology. In particular, the source update does not establish national
coal/lignite, CCGT/CHP, reservoir/run-of-river, onshore/offshore or biomass/waste
splits, nor does it regionalize the underlying Swiss/German/etc. inventories.
The complete mappings are included in ``electricity_sources.json``.

The boundary remains domestic generation, excluding electricity imports.
Grid losses still use the existing ecoinvent 3.6 low-voltage multipliers;
missing loss countries emit a warning and record the RER fallback. Neither new
voltage-specific fuel-production markets nor a consumption mix reconstructed
from bilateral trade has been introduced. These need additional source data
and validation beyond a generation-share refresh.

National EU27 projections with TYNDP
--------------------------------------

Select the country-specific alternative with::

    inventory = InventoryCar(
        model,
        scenario="static",
        background_configuration={"electricity scenario": "tyndp-2026-ntplus"},
    )

For the EU27 as a whole, select it on the vehicle model::

    model = CarModel(array, country="EU27")
    model.set_all()
    inventory = InventoryCar(
        model,
        scenario="static",
        background_configuration={"electricity scenario": "tyndp-2026-ntplus"},
    )

``EU27`` uses Ember's published EU aggregate for 2000--2025 and the TYNDP EU27
aggregate for future years. The importer verifies the latter against summed
member-country generation in TWh; it never takes an unweighted average of
country shares. ``EU27`` also works with all three GECO scenarios, using their
European Union projections through 2070. It is distinct from ``RER`` (Europe).
EU27 grid losses currently use the existing RER multiplier, with an explicit
warning and ``loss_country="RER"`` in provenance.

All 27 EU members have national endpoints in 2030, 2035, 2040 and 2050 from
the weather-weighted NT+ KPI dashboard, alongside the EU27 aggregate. The last observed Ember mix is held
through 2025, then shares are interpolated to these endpoints. The national
2050 mix is held for every later operating year, including after 2070; countries
do not revert to the European GECO proxy. Other countries and ``GLO``/``RER``
retain GECO Reference. ``projection_last_year``, ``projection_region`` and
``projection_source`` in inventory provenance identify the selected country's
actual source and horizon. NT+ is a draft target-compliant scenario, and should
not be interpreted as an enacted-policy forecast.

The importer reconciles generation components against the separate electricity
energy-balance total before interpreting blank cells as zero. It then removes
pumped-storage output, unserved energy and curtailment before calculating
generation shares. Batteries and vehicle discharge are outside the generation
block and are not added. Storage infrastructure and losses are not resolved;
this is still a domestic generation mix. The raw 40-area workbook audit is
retained, but only the 27 validated EU countries and their EU27 aggregate enter
this scenario.

Wind, solar, hydro and nuclear retain the dashboard's distinctions, including
offshore wind, concentrated solar and reservoir hydro. Remaining categories
use explicit LCI proxies: SRES electricity uses PV, Biofuel and Other RES use
wood CHP, Other Non RES uses oil, coal uses hard coal, and gas/adequacy units use
fossil CCGT. In particular, this implementation does not recover renewable-gas
shares or country-specific fuels hidden inside the broad Other categories.
These approximations can matter for impacts even when generation balances close.

Hydrogen power is retained through six added foreground routes: turbine or
fuel-cell generation, each supplied by electrolysis, grey reforming or reforming
with CCS. Fuel fractions use the dashboard's EU27 hydrogen supply pool for each
endpoint, as an explicit proxy for national fuel sourcing. Domestic electrolysis
uses the modelled country's electricity supply; blue SMR/pyrolysis uses SMR with
CCS. Grey SMR, hydrogen adequacy units and unspecified imported hydrogen/ammonia
use grey SMR. This does not claim that imported hydrogen is actually fossil;
its production, transport and ammonia cracking remain unresolved.

The hydrogen recipes use 60% LHV conversion efficiency (TYNDP Common Data,
categories 25/26), 120 MJ/kg hydrogen and 0.5% delivery loss. The turbine uses
a CCGT plant proxy, including NOx and construction inputs from the attributed
CLIC inventory. It also represents unresolved OCGT output. Fuel cells include
PEM stack and balance-of-plant production with a 40,000-hour life assumption.
Electrolysis retains the bundled PEM process and its 54 kWh/kg input, which is
rewired to the country electricity market. The resulting electricity/hydrogen
feedback is solved in the inventory matrix; hydrogen is not free electricity.
Fuel routes remain separate during interpolation and lifetime averaging so
the fuel mix is weighted by hydrogen generation. Vehicles with different
lifetimes retain independent supply chains, including the feedback loop.

``hydrogen_power.yaml`` records the exact supplier keys, quantities, source
links and limitations. The original bundled A/B matrices and their indices
remain unchanged; the new activities are appended privately. The TYNDP array
has 27 technology columns (the original 21 followed by six hydrogen routes).
An explicit custom mix still accepts the established 21 columns and overrides
TYNDP completely. Exported foregrounds include their recipe provenance.

``tyndp_2026_projections.csv`` contains 108 national and four EU27 aggregate endpoints.
``tyndp_2026_balance_audit.csv`` records reported totals and exclusions;
``tyndp_2026_hydrogen_audit.csv`` records the EU fuel-pool quantities; and
``tyndp_2026_mapping_audit.csv`` preserves raw generation, blanks and mapping
status. Runtime loading requires no network or Excel reader.

Attribution and reproducible refresh
------------------------------------

The derivative data retain attribution under CC BY 4.0. The manifest records
the original source URLs, SHA-256 hashes, transformations and generated-file
hashes. Source files are not downloaded during model execution.

* `Ember yearly electricity data <https://ember-energy.org/data/yearly-electricity-data/>`_,
  downloaded 9 October 2026. Its CSV format changed in July 2026.
* `JRC GECO 2025 dataset <https://data.jrc.ec.europa.eu/dataset/11c8deb7-5831-421a-bcd9-ecfff145a615>`_,
  workbooks in the ``published 20260623`` archive directory.
* `TYNDP 2026 draft data <https://2026.entsos-tyndp-scenarios.eu/download/>`_,
  NT+ KPI dashboard downloaded 9 October 2026. Attribution: TYNDP 2026 Scenarios.

Download the three files using the exact URLs in the manifest, retaining their
hashes. Install the test extra for the Excel-reading build dependency; runtime
loading needs no Excel reader. Build into a separate directory::

    python scripts/refresh_electricity.py \
      --ember /path/to/release_generation_yearly_global.csv \
      --geco /path/to/GECO2025.zip \
      --tyndp /path/to/NT+_KPI_Dashboard.xlsx \
      --output /tmp/electricity-refresh \
      --allow-history-exclusions \
      --geco-other-residual

Review the audits, exclusions, geography mappings, hydrogen recipes and changed
results before copying the ten generated resources into
``carculator_utils/data/electricity``.
The source files are independently versioned; a later download from the same URL
can have different content. Reusing these reconciliation rules on another
release requires inspecting its balances and definitions again.

Verification scope
------------------

``tests/test_electricity_scenarios.py`` checks source-independent mass balances,
CCS accounting, explicit residual reconciliation, historical spot checks,
geography fallback, mutation isolation and packaged-resource hashes. Completed
car, bus, truck and two-wheeler cases compare electricity scenarios while
preserving model energy, and export checks retain supply provenance. These
checks establish implementation consistency; they do not validate future
forecasts or the accuracy of the coarse LCI proxies.

``tests/test_tyndp_electricity.py`` adds all-EU coverage and horizon checks,
independent generation totals, rejected missing output, an analytic hydrogen
feedback calculation, all four vehicle families and multi-vehicle export/scope
invariance. The installed artifact verifier also checks all bundled resource
hashes. The source refresh reproduces all ten generated resources byte for byte
from the pinned source snapshots and the versioned hydrogen recipe.

Explicit consumption mixes and grid losses
------------------------------------------

The default scenarios describe domestic generation. They do not become
consumption mixes simply by changing the country label. To account for imports,
use ``carculator_utils.electricity_trade.consumption_mix`` with generation by
``country, year, technology`` and bilateral physical trade by
``exporter, importer, year``. Both must contain absolute energy in the same
``attrs['unit']`` and include all external suppliers. The function requires an
explicit source description and rejects missing boundaries, negative balances,
duplicate labels, and trade cycles without an identifiable generation source.

For each year, it solves ``(diag(supply) - trade.T) * shares = generation``,
where supply is domestic generation plus imports. This proportional-sharing
assumption traces re-exports as well as direct imports and conserves generation
by technology across final consumption. See `Hörsch et al. (2018)
<https://doi.org/10.1016/j.ijepes.2017.10.024>`_. Annual inputs represent annual
pooling; hourly flow tracing can give different results. The helper does not
infer bilateral flows from net imports, trade contracts, or certificates.

Select a country's result, retaining exactly the inventory years and technology
labels, and pass it as ``background_configuration['custom electricity mix']``.
A labelled mix is aligned by coordinates, including reordered technologies;
an unlabelled array retains the existing year-by-technology convention.
Custom mixes are supplied lifetime mixes for each manufacturing year: they are
not automatically averaged over future years. Source and trade-boundary
metadata are retained in inventory/export provenance.

``background_configuration['electricity loss multiplier']`` accepts a finite
scalar of at least one, defined as generated electricity divided by delivered
low-voltage electricity. Supply ``'electricity loss source'`` with its source,
date and boundary. A measured loss fraction of generation ``l`` corresponds to
``1 / (1 - l)``. Do not apply losses twice if the custom mix already includes
them. Without an override, the legacy ecoinvent 3.6 loss table and any RER
fallback remain explicitly identified in provenance.

These additions allow a documented consumption boundary; they do not establish
new global bilateral trade observations or update the default grid-loss data.
Coarse hydro, coal and wind LCI proxies also remain scientific limitations.
