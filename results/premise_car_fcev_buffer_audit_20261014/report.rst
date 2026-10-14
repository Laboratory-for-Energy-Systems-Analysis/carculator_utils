FCEV passenger-car battery calibration audit
=============================================

14 October 2026. All eight installed 2020 FCEV car templates were rebuilt and
checked. Their accounting is internally consistent, but the joint battery
energy/mass/power calibration lacks a matched pack reference. Two manufacturer
references support a materially heavier pack with less nominal energy at the
same required buffer power. Adoption of a reference is awaiting the user's
decision. No model defaults, installed inventories or scenario databases have
changed by this audit. The user subsequently approved the scaled Mirai pack
proxy. Its implementation and regenerated inventories are a separate step;
the charging limit remains unsupported by a matched source.

Current implementation
----------------------

The shared model sizes cells from the battery's share of net electrical
power, then derives nominal energy and complete pack mass. The 2020 inputs
combine 2.1304 kW/kg cell power density, 0.24 kWh/kg cell energy density and
a 70% cell mass fraction. The power input cites several references together
and an own assumption, without a matched pulse duration or SOC/temperature
boundary. The resulting pack has 168 Wh/kg and 1.491 kW/kg.

All eight WLTC traces remain below the net stack rating when instantaneous
fuel-cell response is assumed. This supplies no evidence about the buffer's
actual peak capability, fuel-cell ramp response or startup support. The
recorded battery power is a required allocation, not an independently verified
rating. The inherited FCEV DoD of zero is a charge-sustaining range convention;
it is not a physical zero usable SOC window.

Car energy calculations do not pass a battery charging limit to the shared
energy model. Regeneration is limited by motor power and conversion/storage
efficiencies. The new optional charging constraint used by trucks is available
in utils, but does not automatically validate or constrain the car packs.

.. csv-table:: Installed 2020 packs and charging demand
   :header: "Size", "Nominal kWh", "Pack kg", "Required buffer kW", "Peak net regenerative kW"

   "Mini", 1.844, 10.98, 16.37, 17.14
   "Small", 2.622, 15.61, 23.28, 22.24
   "Lower medium", 3.304, 19.67, 29.33, 25.84
   "Medium", 4.463, 26.56, 39.62, 30.37
   "Large", 5.106, 30.39, 45.33, 34.54
   "Medium SUV", 3.775, 22.47, 33.51, 27.13
   "Large SUV", 5.632, 33.52, 49.99, 40.30
   "Van", 3.717, 22.12, 32.99, 30.06

Net regenerative power here deducts simultaneous auxiliary DC demand before
storage losses. It is a charging requirement, not a demonstrated capability.
The Mini's charging peak exceeds its declared discharge allocation; different
charge and discharge ratings prevent treating this alone as a violation.

Manufacturer references
------------------------

Toyota's `30 November 2020 Mirai announcement
<https://newsroom.toyota.eu/introducing-the-all-new-toyota-mirai/>`_ specifies
310.8 V, 4 Ah, a 44.6 kg pack and 31.5 kW output for ten seconds. Nominal
energy calculated from voltage and charge is 1.2432 kWh. This is a late-2020
launch reference. Its paired pack quantities and declared pulse duration make
it a useful candidate; using it across all car classes remains a proxy. The
announcement provides no continuous discharge or separate charging envelope.

Hyundai's `2020 Australian Nexo emergency response guide
<https://www.hyundai.com/content/dam/hyundai/au/en/documents/NEXO_Emergency_Response_Guide_Australia_2020.pdf>`_
(printed page 9, PDF page 12, visually checked) gives 240 V, 6.5 Ah,
1.56 kWh and 51.2 kg. Its `2018 launch specification
<https://www.hyundai.news/uk/articles/press-releases/nexo-the-next-generation-fuel-cell-vehicle-from-hyundai.html>`_
gives 40 kW battery output without a duration. The guide and announcement
list different motor ratings, 113 and 120 kW, and the latter explicitly
qualifies market variants. This is a corroborating battery proxy, not a
combined calibration of the complete vehicle.

These references do not prove that the existing generic pack is physically
impossible. They provide a more traceable joint calibration and show why a
capacity-only adjustment would be inappropriate. The retained 70% cell mass
allocation and NMC-622 manufacturing identity would remain documented proxies;
the proposed effective cell densities do not claim a measured internal layout.

Coupled model sensitivities
---------------------------

An offline CarModel subclass scales each reference pack by the required buffer
power divided by the reference discharge rating. Energy and complete mass
scale together inside the existing mass/power convergence loop. Motor rating,
stack rating and hydrogen consumption consequently respond to the new mass.
No reference is installed as a default. Fuel-cell power share, chemistry,
efficiencies, usage and other vehicle assumptions are retained.

.. csv-table:: Medium car after native mass/power convergence
   :header: "Case", "Nominal kWh", "Pack kg", "Buffer kW", "H2 kg/100 km", "H2 change"

   "Installed baseline", 4.4628, 26.564, 39.615, 0.88456, "0%"
   "Scaled Mirai, pack only", 1.5976, 57.313, 40.479, 0.89386, "+1.052%"
   "Scaled Nexo, pack only", 1.5724, 51.608, 40.319, 0.89213, "+0.857%"

Across the eight car classes, the Mirai candidate gives 0.656--2.013 kWh and
23.5--72.2 kg, with hydrogen use increasing 0.52--1.09%. The Nexo candidate
gives 0.646--1.982 kWh and 21.2--65.0 kg, with hydrogen use increasing
0.43--0.89%. These differences include mass feedback; they do not include a
newly established charging limit, SOC controller or cycle-life calibration.
All selected cycle motor requirements remain satisfied.

Charging evidence and separate diagnostics
-------------------------------------------

No manufacturer charging envelope was established from the reviewed sources.
The 2024 `instrumented second-generation Mirai study
<https://doi.org/10.1016/j.egyai.2024.100415>`_ shows that battery operation
depends on driving cycle, SOC and temperature. Its measured operating traces
do not establish a continuous charge-acceptance specification. First-generation
Mirai tests concern a NiMH pack and cannot supply the missing rating for the
new lithium-ion reference. A discharge rating is not reused as an asserted
charging rating.

Two deliberately hypothetical charging caps, 50% and 100% of the modelled
buffer discharge requirement, quantify sensitivity. They are not recommended
limits or confidence bounds. Shared accounting supplies auxiliaries directly
from the generator, applies the cap to the remaining DC power, and applies
storage efficiencies only to the accepted battery energy. A third effectively
unlimited case isolates the direct-auxiliary accounting difference.

For the Medium Mirai candidate, the 50% diagnostic cap is 20.24 kW: it curtails
2.97% of generator energy and raises hydrogen use to 0.90061 kg/100 km,
1.82% above the installed baseline. The 100% diagnostic cap does not curtail
this car's WLTC regeneration; its 1.01% hydrogen increase includes the small
benefit of direct auxiliary supply. Across all eight cases, the 50% diagnostic
curtails 2.90--9.60% of generator energy and gives 1.59--2.29% total hydrogen
increases. None of these limits have been adopted.

Premise inventory implications
-------------------------------

All eight installed production datasets correctly purchase nominal kWh times
one plus replacement count from ``market for battery capacity (MIX scenario)``.
No parallel kilogram-based battery production or disposal exchange remains in
those production recipes. All eight current replacement counts are zero.

The approved market policy preserves nominal capacity accounting rather than
matching the physical mass of a dedicated high-power pack. Under the Mirai
candidate, the Medium car's capacity purchase would fall from 4.46 to 1.60 kWh
while physical pack mass rises from 26.6 to 57.3 kg. A lower battery LCIA burden
would therefore reflect the retained capacity-market proxy; it would not
demonstrate that the heavier physical pack requires less manufacturing material.
This qualification was included in the user's pending calibration question.

If approved, implement the matched pack reference and metadata in carculator,
then regenerate the eight FCEV car services and production templates. Retain
the existing Premise policy of fixed 2020 FCEV hardware in future scenarios.
The shared energy module already supports optional charge constraints; it
requires a defensible car-specific limit before enabling that path. No new
Premise runtime solver is required. Recheck fuel/carbon, capacity purchases,
saved metadata and incremental EF results after an actual implementation.

Verification and reproducibility
--------------------------------

``dev/audit_car_fcev_buffer.py`` runs six cases over eight car sizes in the
matched Python 3.12 / NumPy 1.26.4 environment. All 48 cases pass independent
wheel/DC/fuel-energy and pack-mass/energy identities. The baseline reproduces
the installed parameter companions and all eight capacity purchases. Workbook
and parameter-file hashes are unchanged. The existing FCEV diagnostic and
energy-physics suites pass 89 tests.

``model_screen.csv`` records every case; ``pack_comparison.csv`` contains the
three pack comparisons. ``installed_capacity_links.csv``, ``reference_packs.json``,
``source_review.json`` and ``run.json`` record inventory checks, evidence,
source hashes and revisions. Downloaded source documents remain in the private
workspace. No full background inventory is included. The broader final
legacy-versus-refreshed EF comparison and the previously skipped PHEV cycling
review are unaffected by this audit.
