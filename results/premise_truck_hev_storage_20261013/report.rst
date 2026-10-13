Truck HEV traction batteries
============================

13 October 2026. Remediation-plan step 7.

Correction and scope
--------------------

The seven native hybrid trucks previously had zero traction-battery capacity,
mass, manufacture and disposal, while receiving regenerative fuel savings.
Their small power-battery mass represented the lead-acid starter. The missing
traction pack is now sized jointly with vehicle mass, motor power and fuel
consumption. Only the nine HEV service templates (seven diesel hybrids and two
documented gasoline proxies) and seven production recipes change materially.
All 127 workbook identities are retained. Other vehicle powertrains remain
unchanged within numerical tolerance.

The user approved power/energy sizing with the existing motor design, retaining
Premise's MIX capacity market despite its physical mass mismatch, and using
existing chemistry-specific prices as explicit financial proxies. Native
manufacture and disposal use physical pack mass. The adapted Premise workbook
instead purchases nominal capacity times one plus the replacement count, with
no additional pack-mass or disposal exchange.

The model now separates the lead-acid starter from the traction pack, includes
its mass in the truck and supplies at least one starter, retaining the existing
five-year starter lifetime. The older fixed 16 kg inventory recipe is unchanged
for other powertrains.

Sizing and scientific boundary
------------------------------

The power-oriented sizing follows the distinction made in
`Vijayagopal and Rousseau (2020), Benefits of Electrified Powertrains in
Medium- and Heavy-Duty Vehicles <https://doi.org/10.3390/wevj11010012>`_.
Their 5--8 kWh packs are a plausibility reference, not a universal capacity:
the present model's motor ratings differ. Motor-design parameters are retained;
absolute kW change slightly as battery mass enters the existing sizing loop.

The reference is the pre-2020 A123 Systems AHR32113M1Ultra-B high-power LFP
cell: 3.3 V, 4.5 Ah, 205 g. See the manufacturer's 2014
`Battery Pack Design, Validation, and Assembly Guide, document 493005-002
Rev 02 <https://ctc.chontech.ac.th/files/220427099180464_24051016164406.pdf>`_,
Tables 4 and 30--33. Continuous limits at 25 degrees C are 33 A charging and
200 A discharging. Multiplication by the 2 V cutoff gives conservative 66 W
and 400 W limits per cell. Pulse ratings are not used continuously. A 60%
usable SOC window and 70% cell mass share are explicit engineering assumptions.

The pack supports the full motor discharge rating and the cycle's required
usable energy. A finite, periodic buffer accepts braking energy up to the
charge-power and capacity limits and reuses it during subsequent propulsion.
Excess energy gets neither a fuel-saving credit nor a brake-wear reduction.
There is no external electricity or engine charging and no free initial energy.
Fuel conversion retains the model's existing cycle-average conversion boundary.
The positive-propulsion fuel limit is applied after the actual battery reuse
is known. This order is tested independently for a surplus-braking downhill
cycle; scaling an already capped unrestricted credit would understate the
fuel displaced by the accepted energy.

An initial proposal to accept every braking peak continuously produced about
52 kWh and one tonne for the 40 t truck. That design was rejected before final
installation. The final model permits curtailed regenerative braking, as a
finite HEV buffer should. The first private scenario build also preceded the
brake-wear correction; it is archived separately and is not final evidence.

2020 Regional-delivery results
--------------------------------

The 400 km range describes the fuelled truck, not an electric-only HEV range.
The high-power pack is about 19.7 kg per nominal kWh. Replacement quantities
are fractional lifetime allocations, excluding the initial pack.

.. csv-table:: Updated 2020 native diesel HEVs (gasoline proxies reuse their hardware)
   :header: "Gross class", "Nominal kWh", "Pack kg", "Replacements", "Fuel increase"
   :widths: 16, 18, 18, 20, 20

   "3.5 t", "3.748", "73.9", "0", "+2.23%"
   "7.5 t", "4.070", "80.3", "0", "+3.59%"
   "18 t", "8.796", "173.5", "0", "+4.16%"
   "26 t", "9.861", "194.5", "0.109", "+6.08%"
   "32 t", "7.976", "157.3", "0.759", "+9.17%"
   "40 t", "9.956", "196.3", "0.623", "+8.50%"
   "60 t", "13.010", "256.6", "0.621", "+10.93%"

Fuel changes are relative to the preceding inventories with no traction pack
and unrestricted storage acceptance. Added mass and curtailed regeneration
explain the increase. The 40 t pack accepts and reuses 61.4% of the previously
credited regenerative electricity. Native 2020/2050 runs for all seven sizes
remain available and compliant; see ``updated_native_hev_storage.csv``.

Replacement demand uses lifetime distance times actual stored-energy discharge
per km, divided by nominal capacity and cycle life, minus one initial pack and
bounded to 0--3. The inherited LFP cycle-life assumption is 7000 equivalent full
cycles in 2020; it is not a manufacturer guarantee for this high-power use.
Nonzero caller-supplied counts remain physical pack counts. Costs use the
approved generic chemistry proxy (90 EUR/kWh before markup for 2020 LFP).

Explicit limitations
--------------------

* Cell ratings assume a conditioned pack at 25 degrees C. Thermal conditioning
  demand, low-temperature derating, resistance ageing, pack electrical layout
  and an optimized hybrid controller are not independently modelled.
* Generic chemistry cycle life and prices are retained proxies. There is no
  separate HEV calendar-age model; replacement predictions have this boundary.
* The user explicitly retained the MIX capacity market. Its chemistry and mass
  do not match the physical high-power LFP pack. For comparison, the ordinary
  2020 LFP recipe supplies 8.6 kg/kWh, versus this pack's 19.7 kg/kWh; MIX mass
  varies with chemistry shares. Manufacture and disposal remain internally
  consistent within the capacity market, but do not represent the physical
  vehicle mass. No hidden mass-equivalence correction was applied.
* Native future-year model runs and Premise 2050 transformations are distinct.
  This step verifies integration; it does not implement the separately planned
  range-preserving future hardware resizing. The PHEV regenerative-cycling
  decision also remains open and was not inferred from the HEV authorization.
  The nine HEV services remain RER templates without a separate mapped IAM
  efficiency signal. Their fuel quantities remain at the corrected 2020 level
  in the 2050 build, while their fuel suppliers are EUR scenario markets and
  fossil/non-fossil CO2 follows those suppliers. This is not evidence of a
  newly sized 2050 HEV fleet.

Verification evidence
---------------------

The permanent regressions cover independent power/energy balances, periodic
storage, braking curtailment, invalid ratings, chemistry/capacity/cost overrides,
named samples, repeated runs, input preservation, native manufacture/disposal,
starter separation, equivalent-full-cycle accounting and Premise capacity
purchases and metadata. A historical resource audit still verifies all original
price values and uncertainty bounds after undoing the documented HEV scope
extension.

The full REMIND SSP2-NPi builds contain 42,564 activities in 2020 and 42,574 in
2050, with zero validation errors and the same 401/398 warning identities as
before. In each build, 589 materially changed exchanges are confined to the
16 HEV service/production activities. Other differences are below
2.9e-13 in absolute exchange amount. Each build passes 495 fuel-carbon and
147 hydrogen-compression checks; the seven new battery-capacity purchases
agree with nominal packs and replacement counts. Seventy focused Premise
regressions pass.

All 1768 tests pass against the final installed family wheels (1377 shared,
77 car, 171 truck, 43 bus and 100 two-wheeler), with no failures, errors or
skips. This includes 20 new HEV cases. Wheel and sdist-rebuilt wheel resources
match, all five changed truck runtime files match the source bytes, and the
offline core-only model/LCIA smoke checks pass for both artifact routes.

Final scenario checks and installed-artifact results are recorded in
``verification_summary.json`` and ``installed_artifact_verification.json``.
Full databases and validation details remain in the private build workspace.
This report is a battery-correction audit; the final controlled EF 3.1 comparison
across the completed remediation exercise remains a later plan step.

The model correction and regressions are committed as ``fb0106e`` in
carculator_truck. The regenerated Premise workbook, metadata and integration
tests are committed as ``9372892``. Generation-time repository heads are
supplemented by hashes of the actual source files and verified wheel contents.
