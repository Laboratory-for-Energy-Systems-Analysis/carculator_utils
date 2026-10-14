Development tools after the vehicle campaign
=============================================

The 2020 Premise vehicle campaign closed on 14 October 2026. Scientific policy,
verification scope and accepted limitations are in
``../docs/premise_vehicle_update.rst``. The generators and reusable checks remain;
superseded one-off patch/build drivers were removed. Their exact historical
versions are available at Git revision ``862bc96``.

Maintained vehicle workflow
----------------------------

* ``regenerate_premise_cars.py`` and ``regenerate_premise_trucks.py`` write 2020
  candidates in a new output folder. Use matching Python 3.12 sibling sources.
* ``premise_vehicle_baseline.py`` reads original workbooks from pinned Premise
  Git history and checks their hashes. It replaces the untracked audit-JSON
  dependency. The selected recipe CSV remains tracked under ``../results/``.
* ``premise_vehicle_excel.py`` and the battery/LPG/provenance modules preserve
  import structure, physical assumptions and metadata. Unit tests cover these
  boundaries, including rejection of stale FCEV capacity/mass exports.
* ``validate_premise_cars.py`` and ``validate_premise_trucks.py`` check generated
  workbooks and exact suppliers. Their Brightway checks require a compatible
  local ecoinvent 3.12 cutoff project; native generation does not.
* ``audit_premise_vehicle_plausibility.py`` checks complete private scenario
  inventories against build hashes, with explicit generation/workspace/output
  arguments. ``verify_premise_vehicle_provenance.py`` checks saved metadata.
* ``verify_car_fcev_buffer_model.py`` and ``verify_fcev_buffer_model.py`` check
  the completed native designs. Their corresponding hardware checks compare
  the retained 2020/2050 scenario builds.

The final ``*_premise_car_fcev_buffer.py`` scripts are dated reproduction drivers
for the last controlled build/EF comparison, not a general scenario-building API.
They pin input hashes and private workspace paths and refuse inappropriate
overwrites. Other retained ``audit_*`` modules supply parsing, coefficient and
energy-balance helpers to this workflow; their historical ``main`` routines may
require archived run data and the original source revisions.

Keep model-run metadata with ``raw.json``, ``model_parameters.json`` and
``battery_sizing.json`` if using ``--reuse-raw``. Reuse validates the adapter,
not a fresh vehicle-model run. Do not install generated inventories without
checking identities, coefficients and the accompanying parameter/provenance files.

Background rebuild and release tools
------------------------------------

IAM matrix, photovoltaic, tank and general model/background validation tools
are retained separately. They were not retired by this vehicle campaign.
Do not commit Brightway project databases, private source inventories, scratch
notebooks or intermediate copies of installed workbooks as development outputs.
