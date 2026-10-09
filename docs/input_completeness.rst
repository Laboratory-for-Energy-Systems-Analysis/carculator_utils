Input completeness
===================

Input arrays retain ``input_status`` (provided, derived, not applicable or missing)
and a numeric ``missing_input`` coordinate. Required record scopes come from the
vehicle input subclass's bundled defaults. Extra output parameters can start at
zero; a recorded input zero remains a valid supplied value. Missing declared
inputs for an active vehicle raise a contextual error before full-model sizing.
The existing technology/year availability policy excludes unavailable cells, and
PHEV aggregate outputs are validated through their component inputs.

Custom input dictionaries can be partial for construction and inspection. A full
run needs the active model's declared inputs. Nonzero values supplied directly in
the array or by constructor hooks repair wholly missing cells. To intentionally
provide a zero, assign it and explicitly mark its record coverage::

   from carculator_utils.input_completeness import mark_inputs_provided

   array.loc[dict(parameter="maintenance cost per glider cost")] = 0
   array = mark_inputs_provided(array, "maintenance cost per glider cost")

Selections and linear interpolation retain coverage. Interpolation between a
missing and a provided native-year input fails preflight until corrected, even
if its interpolated numerical value is nonzero. Complete the native inputs
before interpolating. Status codes on interpolated arrays can be fractional;
``missing_input > 0`` is the coverage diagnostic.

This is a record-completeness check, not scientific validation of the defaults or
all hand-built arrays. Hand-built arrays without coverage remain compatible and
cannot identify whether a zero came from a missing record. Build arrays through
the public input pipeline to obtain these diagnostics. Existing numerical,
convergence and physical-boundary checks still apply independently.
