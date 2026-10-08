import itertools

import numpy as np
import pandas as pd
import xarray as xr

from .battery_costs import SENSITIVITY, attach_references
from .vehicle_input_parameters import VehicleInputParameters as vip


def fill_xarray_from_input_parameters(input_parameters, sensitivity=False, scope=None):
    """Build a labelled vehicle array from static or sampled input parameters.

    :param input_parameters: A ``VehicleInputParameters`` subclass after
        ``static()`` or ``stochastic()`` has populated its values.
    :param sensitivity: Produce a reference and one-at-a-time 10% perturbations.
        Requires static inputs.
    :param scope: Optional size, powertrain and native-year selections. The
        supplied dictionary is not mutated; required PHEV modes are added locally.
    :returns: ``(mappings, array)``. Mappings are ordered as size, powertrain,
        parameter and year. The array dimensions are ``size``, ``powertrain``,
        ``parameter``, ``year`` and ``value``.

    Missing static cells retain the legacy zero convention and overlapping
    records retain first-entry precedence. Build bracketing native years before
    using ``array.interp(year=...)`` for annual interpolation.
    """

    # Check whether the argument passed is an instance of :class:`TruckInputParameters`
    if not isinstance(input_parameters, vip):
        raise TypeError(
            "The argument passed is not an object of the TruckInputParameter class"
        )

    # Own the scope: PHEV expansion must not alter caller input or parameter metadata.
    scope = {} if scope is None else dict(scope)
    for dimension, defaults in (
        ("size", input_parameters.sizes),
        ("powertrain", input_parameters.powertrains),
        ("year", input_parameters.years),
    ):
        values = scope.get(dimension, defaults)
        if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
            raise ValueError(f"scope[{dimension!r}] must be a nonempty sequence.")
        scope[dimension] = list(values)
        if not scope[dimension] or len(set(scope[dimension])) != len(scope[dimension]):
            raise ValueError(
                f"scope[{dimension!r}] must contain unique, nonempty values."
            )

    if sensitivity:
        if input_parameters.iterations:
            raise ValueError(
                "Sensitivity requires static parameters; call .static() first."
            )
        mappings, reference = fill_xarray_from_input_parameters(
            input_parameters, scope=scope
        )
        labels = ["reference"] + input_parameters.input_parameters
        array = reference.isel(value=0, drop=True).expand_dims(value=labels)
        array = array.transpose(*reference.dims).copy(deep=True)
        for parameter in labels[1:]:
            array.loc[dict(parameter=parameter, value=parameter)] *= 1.1
        array.attrs[SENSITIVITY] = 1
        return mappings, array

    # Make sure to include PHEV-e and PHEV-c-d if
    # PHEV-d is listed

    missing_pwts = [
        ("PHEV-d", "PHEV-e", "PHEV-c-d"),
        ("PHEV-p", "PHEV-e", "PHEV-c-p"),
    ]

    for missing_pwt in missing_pwts:
        if missing_pwt[0] in scope["powertrain"]:
            for p in missing_pwt[1:]:
                if not p in scope["powertrain"]:
                    scope["powertrain"].append(p)

    if any(s for s in scope["size"] if s not in input_parameters.sizes):
        raise ValueError("One of the size types is not valid.")

    if any(y for y in scope["year"] if y not in input_parameters.years):
        raise ValueError("One of the years defined is not valid.")

    if any(pt for pt in scope["powertrain"] if pt not in input_parameters.powertrains):
        raise ValueError("One of the powertrain types is not valid.")

    # if the purpose is not to do a sensitivity analysis
    # the dimension `value` of the array is as large as
    # the number of iterations to perform
    # that is, 1 in `static` mode, or several in `stochastic` mode.

    size_dict = {k: i for i, k in enumerate(scope["size"])}
    powertrain_dict = {k: i for i, k in enumerate(scope["powertrain"])}
    year_dict = {k: i for i, k in enumerate(scope["year"])}
    parameter_dict = {k: i for i, k in enumerate(input_parameters.parameters)}

    params = ["reference"] + input_parameters.input_parameters

    data_dict = [dict()]
    parameter_list = set()
    for param in input_parameters:
        pwt = (
            set(input_parameters.metadata[param]["powertrain"])
            if isinstance(input_parameters.metadata[param]["powertrain"], list)
            else set([input_parameters.metadata[param]["powertrain"]])
        )

        size = (
            set(input_parameters.metadata[param]["sizes"])
            if isinstance(input_parameters.metadata[param]["sizes"], list)
            else set([input_parameters.metadata[param]["sizes"]])
        )

        year = (
            set(input_parameters.metadata[param]["year"])
            if isinstance(input_parameters.metadata[param]["year"], list)
            else set([input_parameters.metadata[param]["year"]])
        )
        if (
            pwt.intersection(scope["powertrain"])
            and size.intersection(scope["size"])
            and year.intersection(scope["year"])
        ):
            powertrains = list(pwt.intersection(scope["powertrain"]))
            years = list(year.intersection(scope["year"]))
            sizes = list(size.intersection(scope["size"]))
            if len(sizes) > 1 and len(powertrains) > 1:
                pwt_size_couple = np.array(list(itertools.product(powertrains, sizes)))
                powertrains = pwt_size_couple[:, 0]
                sizes = pwt_size_couple[:, 1]

            data = {
                "size": sizes,
                "powertrain": powertrains,
                "parameter": input_parameters.metadata[param]["name"],
                "year": years,
                "data": input_parameters.values[param],
            }
            if not sensitivity:
                data["value"] = np.arange(input_parameters.iterations or 1)
            else:
                data["value"] = params

            data_dict.append(data)

            parameter_list.add(input_parameters.metadata[param]["name"])

    parameter_diff = parameter_list.symmetric_difference(input_parameters.parameters)

    for param in parameter_diff:
        data = {
            "size": scope["size"],
            "powertrain": scope["powertrain"],
            "parameter": param,
            "year": scope["year"],
            "data": 0.0,
        }
        if not sensitivity:
            data["value"] = np.arange(input_parameters.iterations or 1)
        else:
            data["value"] = params
        data_dict.append(data)

    df = pd.DataFrame.from_dict(data_dict)
    cols = ["powertrain", "size", "value", "year", "parameter"]
    df1 = pd.concat(
        [
            df[x]
            .explode()
            .to_frame()
            .assign(g=lambda x: x.groupby(level=0).cumcount())
            .set_index("g", append=True)
            for x in cols
        ],
        axis=1,
    )

    df = df.drop(cols, axis=1).join(df1.droplevel(1))
    # Object columns contain numeric coordinates mixed with strings. Infer
    # their types before filling so pandas does not silently downcast them.
    df[cols] = df[cols].infer_objects().ffill()

    df = df.explode("data", ignore_index=False)
    df["value"] = df.groupby(["size", "powertrain", "parameter", "year"]).cumcount()

    df.set_index(["size", "powertrain", "parameter", "year", "value"], inplace=True)
    df.dropna(inplace=True)
    df = df[~df.index.duplicated(keep="first")]
    df = df.reset_index()
    if input_parameters.iterations:
        df = df[df["value"].isin(range(input_parameters.iterations))]
    else:
        df = df[df["value"] == 0]

    # Ensure index is correctly set
    df.set_index(["size", "powertrain", "parameter", "year", "value"], inplace=True)

    # Create the DataArray
    array = xr.DataArray.from_series(df["data"])

    # Optional: cast types
    array = array.astype("float32")
    array.coords["year"] = array.coords["year"].astype("int")
    array = array.dropna("value", how="all")
    array = array.fillna(0.0)

    if sensitivity:
        # we increase each value by 10% for each params excepting reference one

        for param in params[1:]:
            array.loc[dict(parameter=param, value=param)] *= 1.1

    # xarray sorts coordinates when building from a Series; mapping indices must
    # describe that actual ordering, rather than the requested scope order.
    mappings = tuple(
        {label: index for index, label in enumerate(array[dim].values.tolist())}
        for dim in ("size", "powertrain", "parameter", "year")
    )
    return mappings, attach_references(array, input_parameters)
