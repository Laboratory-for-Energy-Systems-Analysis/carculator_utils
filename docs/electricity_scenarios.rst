National electricity data and scenarios
=======================================

The default electricity supply now combines observed national generation from
Ember with the Reference scenario of JRC's GECO 2025 release. Three electricity
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
* ``legacy``: the previous TYNDP 2020/TEMBA/WEO 2017 table, its original
  normalization and its truncated lifetime averaging convention.

These labels do not imply equivalence to ``SSP2-NPi``, ``SSP2-PkBudg1000`` or
``SSP2-PkBudg650``. Record both choices in a study. ``scenario="static"`` still
selects static background impact factors; it does not freeze generation shares.
The same country/year history is used in all three refreshed scenarios.

An explicit ``custom electricity mix`` retains its existing year-by-technology
shape and overrides generation shares for all selected vehicles and samples.
It works even for a country absent from the national dataset. Unknown countries
otherwise raise; an intentional geographic fallback can be specified with
``"electricity fallback country": "GLO"``. ``GLO`` is World, while ``RER`` uses
Ember Europe history and EU27 projections. ``UK`` and the former table's ``NM``
are recognized as aliases for ``GB`` and ``NA`` respectively. Substitution is
reported, not silent.

Data and geographic meaning
---------------------------

The bundled snapshot contains 5,957 observed country/region-year records and
211 geographic codes. Historical coverage varies by country (the earliest
record is 1985); the most recent observations are from 2022--2025. The latest
years may include estimates. Each country's actual final historical year is
available as ``history_last_year`` in the background array and provenance.

See :doc:`electricity_coverage` for the full country/economy list, each retained
historical year range and its projection source: 27 country projections,
180 regional proxies and two World proxies, plus the World and Europe aggregates.

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

The refresh uses the existing 21 background electricity activities. Coarse
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

TYNDP 2026 is included as a reproducible candidate audit, not a selectable
runtime scenario. Its NT+ dashboard provides generation in TWh at four future
years with weather-weighted results. ``tyndp_2026_mapping_audit.csv`` preserves
these values, missing cells and mapping status. Pumped storage output,
curtailment and unserved demand are excluded from candidate primary generation.
Hydrogen generation, evolving gas composition, broad other categories and
adequacy units remain unresolved. None are silently assigned fossil gas or
zero impact. NT+ is also a draft target-compliant scenario, not a direct
replacement for an enacted-policy GECO Reference trajectory.

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

Review both audits, exclusions, geography mappings and changed results before
copying the six generated resources into ``carculator_utils/data/electricity``.
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
