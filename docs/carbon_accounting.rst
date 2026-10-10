Physical carbon and climate accounting
======================================

Fuel carbon can leave the vehicle as CO2, carbon monoxide, methane and other
compounds. This page explains which amounts the model counts, why their sum can
exceed the fuel carbon under the default convention, and how to inspect that
difference. A climate-accounting label is not always a physical carbon origin.

The legacy fuel field ``biogenic share`` selects the fraction assigned to
non-fossil CO2 accounting. It must not be interpreted as a measured biological
carbon fraction for every synthetic fuel. Biomass carbon, carbon captured from
air, and recycled cement-process carbon are distinct origins. In particular,
cement-derived fuel is not biologically produced simply because that field is
one. The source inventory's capture-credit allocation also needs to be reviewed
separately from physical tailpipe releases.

The cement capture workbook records allocation of the capture credit to the
fuel producer, and the bundled capture activity includes an assumed biogenic
contribution. These observations do not by themselves establish a complete
physical fossil/biogenic split and consistent avoided-emission allocation along
every allocated fuel branch. No new credit is added, and the existing climate
allocation is not silently reinterpreted. Its scientific qualification remains
open. User-supplied supplier names require their own provenance review.

Carbon diagnostics
------------------

``inventory.carbon_balance()`` returns a labelled dataset in kg carbon per
vehicle-km. It compares carbon implied by the fuel's full-oxidation CO2 factor
with the actual CO2 inventory and carbon in CO, methane and chemically identified
hydrocarbons. Integer molecular masses follow the existing 12/44 CO2 convention.
Generic NMHC, chlorinated hydrocarbons, PAHs and particulates have unknown carbon
fractions; the diagnostic reports lower/upper bounds rather than assigning an
unsupported composition. The method leaves the inventory unchanged.

The default full-oxidation CO2 calculation and independently estimated exhaust
pollutants generally produce a positive carbon excess. Consequently, the default
must not be described as a closed elemental balance. The report records the
legacy non-fossil accounting amount separately from named-route carbon origins.
Evaporation, lubricant consumption and non-exhaust material carbon are outside
this engine-fuel/exhaust diagnostic.

Explicit exhaust reconciliation
-------------------------------

When appropriate source measurements or a documented scenario supply the
missing composition, call::

    report = inventory.reconcile_exhaust_carbon(
        carbon_fractions=fractions,
        source="Study/report, page, date, and exhaust boundary",
    )
    impacts = inventory.calculate_impacts()

``fractions`` maps each present unspecified exhaust group to kg C/kg group.
The accepted keys are ``Non-methane hydrocarbon``, ``Hydrocarbons``,
``PAH, polycyclic aromatic hydrocarbons``, and ``Particulate matters``. Values
must be finite and within zero to one. A nonzero group cannot be omitted.
Do not set these fractions to zero simply to obtain agreement.

The operation assigns all counted exhaust carbon to engine fuel and calculates
CO2 from the remaining carbon. It rejects a negative carbon budget, validates
all assumptions before changing any matrix entries, and recomputes from fuel
on every call so repeated calls cannot subtract carbon twice. It retains the
chosen legacy fossil/non-fossil accounting allocation; it does not resolve the
upstream capture-credit question. Its source and assumptions accompany exported
transport activities. Default exports explicitly state the full-oxidation
boundary. Changing this inventory does not change model energy consumption.

Completed tests for all four vehicle families verify the existing excess,
no mutation during diagnostics or rejected reconciliation, closure under
explicit analytic composition assumptions, repeatability and finite LCIA.
These analytic fractions are test scenarios, not newly calibrated defaults.
A universal default correction awaits defensible exhaust composition and
capture-accounting evidence; the software now exposes and supports that review.
