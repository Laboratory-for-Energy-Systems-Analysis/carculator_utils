FCEV electrical power and buffer plausibility
=============================================

14 October 2026. This is a diagnostic follow-up to the earlier
`FCEV accounting correction <../premise_vehicle_fcev_20261014/report.html>`_.
Fresh runs cover all eight installed 2020 FCEV car sizes and seven FCEV truck
sizes, Swiss climate, WLTC for cars and Regional delivery for trucks. The
physical specifications agree with the installed Premise parameter companions.

Finding: mechanical and electrical power are mixed
--------------------------------------------------

The previous correction closes the declared nominal allocation, but that is
not an electrical feasibility test. ``power`` and ``electric power`` are
mechanical motor-shaft ratings in the driving-cycle calculation. The fuel-cell
rating divided by its own-consumption multiplier is net electrical output.
Adding battery electrical power to this output must cover motor conversion
losses and auxiliary electricity. Currently the sum merely equals shaft power.

With the existing 2020 motor/inverter efficiency of 0.9, the appropriate
boundary is::

    required DC kW = motor shaft kW / 0.9 + auxiliary DC kW
    net fuel-cell kW = gross stack kW / gross-to-net multiplier
    required buffer kW = max(required DC kW - net fuel-cell kW, 0)

The 0.9 input already describes motor/inverter conversion; no separate inverter
loss is added. Stack own consumption is included once. Auxiliaries bypass the
motor. The current Swiss-climate auxiliary demand is used here, not an extreme
temperature design envelope. Battery internal losses enter stored-energy
calculations, not this terminal-output sum.

.. list-table:: Ratings at current vehicle masses, before resizing feedback
   :header-rows: 1

   * - Quantity
     - Medium car
     - 40 t truck
   * - Motor shaft rating, kW
     - 139.47
     - 290.69
   * - Net fuel-cell rating, kW
     - 104.60
     - 72.67
   * - Recorded buffer power, kW
     - 34.87
     - 218.02
   * - Motor plus auxiliaries, required DC kW
     - 155.35
     - 328.49
   * - Uncovered DC power, kW
     - 15.88
     - 37.80
   * - Buffer required if fuel-cell rating is retained, kW
     - 50.75
     - 255.81
   * - Net fuel cell if the electrical split is retained, kW
     - 116.51
     - 82.12
   * - Buffer if the electrical split is retained, kW
     - 38.84
     - 246.36

All fifteen templates have this boundary mismatch. Preserving the existing
fuel-cell/battery shares on the electrical side is the proposed correction;
retaining fuel-cell ratings and increasing only the buffer is an alternative.
The user has been asked to choose the allocation. Neither has been installed.
Both require consistent source-model mass feedback; neither requires a solver
in Premise. The existing share parameters do not establish which design choice
was intended.

Cycle screening does not certify the batteries
----------------------------------------------

The audit independently recovers DC demand from wheel energy, transmission and
motor efficiencies and checks it against the hydrogen-input trace multiplied
by fuel-cell efficiency. Every cell passes this energy identity.

All car WLTC traces remain below their net fuel-cell rating. Under an
instantaneously responding fuel cell they therefore need no battery discharge
assistance. This does not validate acceleration at rated motor output, startup,
fuel-cell ramping or regenerative charge acceptance.

The 40 t truck needs up to 150.29 kW of battery assistance on Regional delivery,
while its current trace assumes regenerative DC recovery reaching 261.62 kW.
These are different charge and discharge requirements. The model has no
validated FCEV-specific battery charge-power limit or SOC controller.

The 3.5 t and 7.5 t trucks exceed their motor shaft ratings for ten seconds
each, with peaks of 53.87 versus 51.06 kW and 107.01 versus 93.74 kW,
respectively. Correcting the electrical allocation alone does not resolve
these mechanical shortfalls. The 32 t truck exceeds its recorded buffer
requirement for three seconds even though its motor rating is sufficient.
These counts describe the selected traces, not measured road-test performance.

An optimistic periodic energy calculation gives minimum usable storage of
1.71--6.42 kWh for trucks, below their 32.72--88.56 kWh nominal capacities.
It allows instantaneous full fuel-cell power, unrestricted charging and
discharging, freely chosen initial SOC and curtailment. This establishes only
a lower bound. FCEV ``battery DoD`` defaults are zero, so no operating SOC
window is available to test usable capacity. The lower-bound controller is
not used to revise hydrogen consumption or replacement counts.

Battery specification evidence
------------------------------

Car buffers combine 0.24 kWh/kg cell energy density, 2.1304 kW/kg cell power
density and a 70% cell mass fraction. Their implied pack energy density is
168 Wh/kg; their declared output corresponds to 1.491 kW/kg of complete pack.
The power source lists several references together and supplies no common
duration, SOC or temperature for the paired energy/power assumptions. The
Medium car consequently has 3.93 kWh in 23.38 kg. This is not a validated
dedicated FCEV buffer specification.

For comparison, Toyota's second-generation Mirai announcement of
`30 November 2020 <https://newsroom.toyota.eu/introducing-the-all-new-toyota-mirai/>`_
gives 310.8 V, 4 Ah, 44.6 kg and 31.5 kW for ten seconds. Nominal energy
calculated from voltage and charge is 1.2432 kWh, or 27.9 Wh/kg of pack.
This is a late-2020 launch reference, not an all-class fleet average or a
continuous-power rating.

Hyundai's `2020 Nexo emergency guide, printed page 9
<https://www.hyundai.com/content/dam/hyundai/au/en/documents/NEXO_Emergency_Response_Guide_Australia_2020.pdf>`_
gives a lithium-ion-polymer pack of 1.56 kWh and 51.2 kg, or 30.5 Wh/kg.
Its `2018 launch specification
<https://www.hyundai.news/uk/articles/press-releases/nexo-the-next-generation-fuel-cell-vehicle-from-hyundai.html>`_
reports 40 kW from the battery, 95 kW from the fuel cell and a 120 kW motor.
The battery power duration is unspecified. Market variants differ: the
Australian emergency guide lists a 113 kW motor, so these two motor ratings
are not merged into one calibration.

These references support reviewing the car pack's joint mass/energy/power
calibration. Their different chemistry and architecture prevent declaring the
generic model pack physically impossible solely from the comparison.

The truck's inherited 0.15 kW/kg parameter explicitly describes a lead-acid
starter. It cannot validate the final lithium-ion traction buffer, which is
instead energy-sized at 20 kWh plus 6% of hydrogen chemical energy. The 40 t
pack is 71.10 kWh and 423.22 kg. Hyundai's `retrospective on the Swiss XCIENT
fleet introduced in 2020
<https://www.hyundai.com/worldwide/en/newsroom/detail/0000000134>`_ reports
72 kWh total across three batteries, a 180 kW fuel-cell system and a 350 kW
motor. Its similar capacity supports only an order-of-magnitude comparison:
it does not validate the model's pack mass, power limits or smaller fuel-cell
rating. No matched continuous/pulse power source has been established for the
model's NMC-622 pack.

Implementation status and reproducibility
------------------------------------------

``dev/audit_premise_fcev_power.py`` produces ``power_screen.csv``, the complete
model snapshot, extracted parameter sources and a run manifest with package
paths, source hashes and installed-parameter hashes. Nine focused unit tests
pass for electrical/mechanical boundaries, repeated-cycle storage, charge and
discharge losses, regeneration and invalid inputs. Full-catalogue trace and
installed-template comparisons pass in the recorded Python 3.12 environment.

No model default, vehicle workbook, Premise runtime or LCIA score changes in
this diagnostic step. The current future-year policy retains FCEV hardware;
the range-preserving battery-resizing contract is restricted to BEV/PHEV.
IAM hydrogen-efficiency scaling does not repair these baseline power ratings.
The full legacy-versus-new EF 3.1 comparison remains a later step.

Next actions, one issue at a time: settle the electrical allocation and correct
it with native-model regressions; address the two undersized truck motors;
then agree paired buffer specifications and explicit charge/discharge limits.
The unrelated PHEV cycling review remains skipped as requested.
