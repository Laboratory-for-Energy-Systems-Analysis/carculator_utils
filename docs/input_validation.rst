Input validation
================

These contracts are shared by ``carculator``, ``carculator_truck``,
``carculator_bus``, and ``carculator_two_wheeler``.

Parameter records
-----------------

Vehicle input classes validate parameter records when they are loaded, before
sampling or building the model array. Invalid records raise ``ValueError`` with
the record identifier, parameter name when available, and offending field.

* Each record needs a nonempty ``name``, nonempty sequences of unique string
  labels in ``sizes`` and ``powertrain``, an integer ``year``, and an ``amount``.
* ``amount`` and any supplied ``loc``, ``minimum``, ``maximum``, ``scale``, or
  ``shape`` must be finite numbers. Booleans and numeric strings are rejected.
* ``minimum`` must not exceed ``maximum``. Distribution-specific requirements
  still apply when sampling uncertain parameters.

Some bundled records overlap after expansion across sizes and powertrains.
Their existing first-record precedence is preserved. Authors can explicitly
audit new data for overlapping cells:

.. code-block:: python

    from carculator_utils.vehicle_input_parameters import (
        load_parameters,
        validate_parameters,
    )

    records = load_parameters("my_parameters.json")
    validate_parameters(records, check_duplicates=True)

This audit identifies the duplicated ``(name, size, powertrain, year)`` cell and
the two record identifiers. It does not rewrite data or resolve conflicts.

Fuel blends
-----------

Each supplied fuel category must have a primary component with a known fuel
``type`` and a ``share``. Shares must be finite numbers between zero and one.
They may be scalars, one-element sequences, or one-dimensional sequences with
one entry per model year, in the order of ``array.year``. Scalars and
one-element sequences are expanded to all years.

.. code-block:: python

    fuel_blend = {
        "diesel": {
            "primary": {"type": "diesel", "share": 0.8},
            "secondary": {
                "type": "diesel - biodiesel - cooking oil",
                "share": 0.2,
            },
        }
    }
    # Pass fuel_blend=fuel_blend to a vehicle model constructor.

An omitted secondary component is completed with the default secondary fuel and
the complementary share. If both components are provided, their shares must sum
to one for every year (absolute tolerance ``1e-7``). The caller's dictionary is
preserved. Unsupported categories, unknown fuel types, malformed shapes, and
invalid shares raise contextual ``ValueError`` exceptions.

When an inventory is constructed, selected suppliers must exist in the bundled
inventory index. An unresolved supplier raises ``KeyError`` naming the category,
component, fuel type, and supplier before the large inventory matrices are
allocated. A fuel specification alone does not guarantee a corresponding
inventory supplier; missing mappings require a justified data update.
