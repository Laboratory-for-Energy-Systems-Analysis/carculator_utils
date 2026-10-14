FCEV truck battery correction
================================

The approved AKASOL pack proxy is implemented in the native truck model, with
shared battery charging constraints in carculator_utils. All seven 2020 FCEV
truck inventories have been regenerated and installed in Premise. No new
driving-cycle calculation is added to Premise runtime.

This report compares the correction with the immediately preceding verified
small-FCEV motor update. It is not the final original-legacy-versus-refreshed
vehicle comparison, which remains outstanding.

Physical changes
-------------------

The `AKASOL May 2021 manufacturer sheet
<https://www.act-news.com/wp-content/uploads/2020/11/210525_LowRes_AK_Datenblatt_AKASystem_15-OEM-37-PRC_2021_2159x2794mm_EN.pdf>`_
is an explicitly approved proxy for 2020: 25 kWh, 238 kg, 36 kW continuous
charging, 50 kW continuous RMS discharge, and 150 kW discharge for ten seconds.
The same product appears in the earlier manufacturer brochure.

The inherited range-related battery rule is retained as a floor. Packs grow
where the cycle's instantaneous battery assistance exceeds the continuous
rating. Using that rating at every second avoids inventing a repeated-pulse
recovery rule. The full motor's buffer requirement also fits the ten-second
rating; indefinite full motor output is not claimed. The 7.5 t and 32 t packs
are primarily enlarged by the continuous-discharge requirement.

Regeneration supplies concurrent DC auxiliaries first, then charges up to the
continuous battery-terminal limit. Storage losses apply only to the stored
portion. Excess braking receives neither fuel nor brake-wear credit. The
existing conservative brake-wear conversion discount is retained, including
the credit for regeneration used directly by auxiliaries.

The model reconverges vehicle mass, fuel storage and payload. Explicit battery
capacities are preserved and rejected if too small at the converged vehicle
mass. Propulsion demand is never clipped to hide a power deficit. All seven
selected Regional-delivery templates satisfy the motor and battery cycle-power
checks; the 57/129 kW small-truck motor proxies remain adequate. Requested cargo
is unchanged and within available payload; the target range remains 400 km.

.. list-table::
   :header-rows: 1

   * - Truck
     - Before kWh
     - After kWh
     - Before kg
     - After kg
     - Hydrogen use
   * - 3.5 t
     - 32.73
     - 32.86
     - 195
     - 313
     - +0.96%
   * - 7.5 t
     - 39.18
     - 49.27
     - 233
     - 469
     - +1.38%
   * - 18 t
     - 51.32
     - 52.12
     - 305
     - 496
     - +2.55%
   * - 26 t
     - 57.91
     - 59.92
     - 345
     - 570
     - +5.33%
   * - 32 t
     - 68.18
     - 87.77
     - 406
     - 836
     - +3.53%
   * - 40 t
     - 71.14
     - 74.31
     - 423
     - 707
     - +6.20%
   * - 60 t
     - 88.61
     - 95.57
     - 527
     - 910
     - +10.14%

All values are for 2020, Swiss climate and Regional delivery. Hydrogen changes
include the mass and charging-limit effects together. The 40 t truck changes
from 6.393 to 6.789 kg H2 per 100 km. These differ from the earlier fixed-mass
charging-limit sensitivity, which deliberately excluded resizing.

Premise treatment and provenance
-----------------------------------

The 127-activity workbook preserves every identity. Numerical changes are
confined to seven FCEV services and seven production recipes. Other workbook
coefficients are unchanged. Both full scenarios differ in only 74 activities:
seven RER production recipes, the two unmatched RER services (32 t and 60 t),
and five operating services in each of thirteen IAM regions. The other RER
services remain forwarders with unchanged forwarding coefficients.

Premise retains the MIX capacity market per nominal kWh including replacements.
The physical pack has 9.52 kg/kWh; no mass-equivalence adjustment is applied to
the market. Dataset comments and structured metadata disclose this mismatch,
the reference edition, conditioning assumption, power boundaries and retained
manufacturing proxies. Model name, publication, source hashes and original
component provenance are retained. Saved Brightway metadata matches exactly.

The seven FCEV production recipes keep the regenerated 2020 battery, motor,
inverter and fuel-cell quantities in 2050. Scenario efficiency still changes
operating energy. Future FCEV hardware resizing remains outside the approved
scope. Hydrogen and its 30-to-700-bar compression electricity remain linked
and scaled consistently through the regional scenario supplies.

Incremental EF 3.1 comparison
--------------------------------

Both private databases use 2020 REMIND SSP2-NPi and ecoinvent 3.12 cutoff. The
comparison covers all seven RER FCEV services plus the five matched EUR services,
with one tonne-kilometre and sixteen EF 3.1 headline indicators: 192 paired
scores. The table uses EUR where present and the unmatched RER services otherwise.

.. list-table::
   :header-rows: 1

   * - Truck
     - Location
     - Climate change
     - Largest indicator increase
     - Change
   * - 3.5 t
     - EUR
     - +0.96%
     - land use
     - +3.05%
   * - 7.5 t
     - EUR
     - +2.22%
     - human toxicity: carcinogenic
     - +5.11%
   * - 18 t
     - EUR
     - +1.60%
     - ozone depletion
     - +1.79%
   * - 26 t
     - EUR
     - +3.29%
     - ozone depletion
     - +3.66%
   * - 32 t
     - RER
     - +3.04%
     - human toxicity: non-carcinogenic
     - +4.03%
   * - 40 t
     - EUR
     - +4.00%
     - ozone depletion
     - +4.49%
   * - 60 t
     - RER
     - +5.89%
     - ionising radiation: human health
     - +6.94%

All paired changes are positive, from 0.17% to 6.94%. Exchange contribution
analysis independently reconciles the largest indicator and climate change
for each truck against the forward LCIA solve. The dominant explanations are:

* 3.5 t land use: increased road input accounts for 98.6% of the increase.
* 7.5 t carcinogenic toxicity: added battery-capacity manufacture accounts for
  87.7% of the increase.
* 32 t non-carcinogenic toxicity: battery-capacity manufacture explains 50.5%
  and brake-wear treatment 16.5% of the increase.
* 18 t, 26 t and 40 t ozone depletion: hydrogen supply explains 69.1%, 82.6%
  and 86.3% of their respective increases.
* 60 t ionising radiation: compression electricity and hydrogen supply explain
  50.9% and 45.7% of the increase.

Manufacturing sub-contributions are nested within vehicle production and must
not be added to it a second time. No unexplained numerical residual or change
outside the FCEV correction was found. This explains the changes within the
chosen inventory and LCIA assumptions; it is not independent validation of
the background supply-chain impact factors.

Verification
---------------

* 159 focused model/sibling checks passed, followed by 91 shared-energy and
  adapter checks (these runs overlap). Explicit capacity, repeated runs, named
  samples, losses, auxiliary bypass and invalid charging inputs are covered.
* 115 Premise regressions passed; one passenger-car-only calibration test is
  intentionally skipped for the truck fixture.
* All five packages passed wheel/sdist resource checks and offline core-only
  native model/LCIA smoke checks. Full installed test suites were not rerun.
* Both full builds have zero errors and unchanged warning identities:
  401 warnings in 2020 and 468 in 2050. They contain 42,564 and 42,795 activities.
* Fuel-energy/carbon checks, battery allocation and retained future hardware
  pass. Each saved database passes 968 operating-energy link checks; metadata
  matches for 965 activities in 2020 and 1,186 in 2050.
* A separate native audit reproduces the installed parameters and independently
  checks generator energy, storage losses, auxiliary use, fuel energy, mass,
  payload and the 400 km range. Historical unavailable FCEVs remain masked and
  finite in a mixed 2000/2020 FCEV/diesel run.

Limits and retained assumptions
----------------------------------

This is a conditioned-pack engineering proxy, not certification at arbitrary
SOC or temperature. No SOC controller, fuel-cell ramp, thermal model or revised
ageing calculation is introduced. The existing cycle-average fuel conversion
and battery replacement assumptions are retained. The 70% internal cell mass
allocation and NMC-622 inventory/cost mapping are proxies; the effective cell
density reproduces the documented whole-pack mass rather than claiming a
measured AKASOL cell specification. Other chemistry choices retain their
inventory identity while using the supplied physical pack profile.

Future native-model years retain this pack profile unless explicitly overridden.
The approved Premise scenarios instead retain the complete 2020 FCEV hardware.
Cars, buses and two-wheelers do not opt into the new charging constraint by
default. The separately skipped PHEV cycling review remains skipped.

Reproducibility and local commits
------------------------------------

Source corrections: utils ``f55b6ec``; truck ``2dbccc9``. Installed Premise
inventories and regressions: ``93d918f``. Generation source file hashes identify
the exact sources used, including the then-uncommitted corrections; the final
source commits contain those same files.

The private workspace is ``/private/tmp/premise-fcev-buffer-20261014``. Existing
user Brightway projects were not modified. Workflow scripts in ``dev/`` are
``regenerate_premise_trucks.py``, ``install_premise_fcev_buffer.py``,
``build_premise_fcev_buffer.py``, ``audit_premise_fcev_buffer.py``,
``verify_fcev_buffer_model.py``, ``verify_fcev_buffer_hardware.py``,
``save_premise_fcev_buffer.py``, ``compare_premise_fcev_buffer.py`` and
``explain_premise_fcev_buffer.py``. The generic plausibility audit supplies the
``accounting/`` tables. Build records pin encrypted IAM files and workbook hashes.

The detailed outputs are ``model_screen.csv``, ``model_changes.csv``,
``template_changes.csv``, ``scenario_changes.csv``, ``incremental_ef31.csv`` and
``incremental_ef31_contributions.csv``. Verification and artifact records are
included alongside the report. This correction is complete; the final broader
legacy-vehicle EF comparison remains a separate outstanding exercise.
