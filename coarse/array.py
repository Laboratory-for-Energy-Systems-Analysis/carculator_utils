import numpy as np
import xarray as xr


def fill_xarray_from_input_parameters(cip):
    """Create an ``xarray`` labeled array from the sampled input parameters.

    Dimensions:

        0: Vehicle size, e.g. "small", "medium". str.
        1: Powertrain, e.g. "ICE-p", "BEV". str.
        2: Year. int.
        3: Samples.

    """
    array = xr.DataArray(
        np.zeros(
            (
                len(cip.sizes),
                len(cip.powertrains),
                len(cip.parameters),
                len(cip.years),
                cip.iterations or 1,
            )
        ),
        coords=[
            cip.sizes,
            cip.powertrains,
            cip.parameters,
            cip.years,
            np.arange(cip.iterations or 1),
        ],
        dims=["size", "powertrain", "parameter", "year", "value"],
    )

    size_dict = {k: i for i, k in enumerate(cip.sizes)}
    powertrain_dict = {k: i for i, k in enumerate(cip.powertrains)}
    year_dict = {k: i for i, k in enumerate(cip.years)}
    parameter_dict = {k: i for i, k in enumerate(cip.parameters)}

    for param in cip:
        for size in cip.metadata[param]["sizes"]:
            for powertrain in cip.metadata[param]["powertrain"]:
                array[
                    size_dict[size],
                    powertrain_dict[powertrain],
                    parameter_dict[cip.metadata[param]["name"]],
                    year_dict[cip.metadata[param]["year"]],
                    :,
                ] = cip.values[param]

    return (size_dict, powertrain_dict, parameter_dict, year_dict), array