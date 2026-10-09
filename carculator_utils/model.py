from copy import deepcopy
from itertools import product
from pathlib import Path
from typing import Dict, List, Union

import numexpr as ne
import numpy as np
import xarray as xr
import yaml

from .background_systems import BackgroundSystemModel
from .battery_costs import ENERGY_COST, POWER_COST, capture_inputs, is_battery_cost
from .combustion_controls import validate_control_keys
from .cost_uncertainty import FCEV_FACTOR, GENERAL_FACTOR, attach_cost_factors
from .driving_cycles import detect_vehicle_type
from .energy_consumption import get_default_driving_cycle_name
from .hot_emissions import HotEmissionsModel
from .noise_emissions import NoiseEmissionsModel
from .numerical import iterate_until_converged
from .particulates_emissions import ParticulatesEmissionsModel

REQUIRED_ARRAY_DIMS = ("size", "powertrain", "parameter", "year", "value")


def validate_temperature(value, name):
    """Normalize a Celsius scalar or twelve monthly values without mutation."""
    temperature = np.asarray(value, dtype=float)
    if temperature.shape not in ((), (12,)) or not np.isfinite(temperature).all():
        raise ValueError(f"{name} must be a finite scalar or twelve monthly values.")
    if np.any(temperature <= -273.15):
        raise ValueError(f"{name} must be above absolute zero in degrees Celsius.")
    return float(temperature) if temperature.ndim == 0 else temperature.copy()


def finite(array, mask_value=0):
    return np.where(np.isfinite(array), array, mask_value)


def load_default_specs_for_fuels():
    """
    Load default_fuels.yaml file and return a dictionary with fuel specifications.
    """
    with open(Path(__file__).parent / "data" / "fuel" / "default_fuels.yaml") as file:
        return yaml.load(file, Loader=yaml.FullLoader)


def validate_vehicle_array(array: xr.DataArray) -> None:
    """
    Validate the shared vehicle model array contract.
    """
    if not isinstance(array, xr.DataArray):
        raise TypeError("VehicleModel expects `array` to be an xarray.DataArray.")

    missing = [dim for dim in REQUIRED_ARRAY_DIMS if dim not in array.dims]
    if missing:
        raise ValueError(
            "VehicleModel array is missing required dimensions: "
            f"{', '.join(missing)}."
        )

    if set(array.dims) != set(REQUIRED_ARRAY_DIMS):
        raise ValueError("VehicleModel array has unsupported dimensions.")
    for dim in REQUIRED_ARRAY_DIMS:
        if dim not in array.coords or not array.sizes[dim]:
            raise ValueError(
                f"VehicleModel requires nonempty labelled {dim!r} coordinates."
            )
        if not array.get_index(dim).is_unique:
            raise ValueError(f"VehicleModel requires unique {dim!r} coordinates.")


class VehicleModel:
    """
    This class represents the entirety of the vehicles considered,
    with useful attributes, such as an array that stores
    all the vehicles parameters.

    :ivar array: multi-dimensional numpy-like array that contains parameters' value(s)
    :ivar cycle: name of a driving_cycles, or custom driving_cycles
    :ivar gradient: series of gradients, for each second of the driving_cycles
    :ivar energy_storage: dictionary with selection of battery chemistry for each powertrain

    """

    DATA_DIR = Path(__file__).resolve().parent / "data"

    def __init__(
        self,
        array: xr.DataArray,
        country="CH",
        cycle: Union[None, str, np.ndarray] = None,
        gradient: Union[None, np.ndarray] = None,
        energy_storage: Union[None, Dict] = None,
        electric_utility_factor: float = None,
        drop_hybrids: bool = True,
        payload=None,
        annual_mileage=None,
        energy_target=None,
        energy_consumption: dict = None,
        engine_efficiency: dict = None,
        transmission_efficiency: dict = None,
        target_range: dict = None,
        target_mass: dict = None,
        power: dict = None,
        fuel_blend: dict = None,
        ambient_temperature: float = None,
        indoor_temperature: float = 20,
        max_iterations: int = 100,
        combustion_controls: dict = None,
        battery_costs: dict = None,
    ) -> None:
        """
        :param array: multi-dimensional numpy-like array that contains parameters' value(s)
        :param country: country code
        :param cycle: name of a driving_cycles, or custom driving_cycles
        :param gradient: series of gradients, for each second of the driving_cycles
        :param energy_storage: dictionary with selection of battery chemistry, capacity and origin for each powertrain-size-year combination
        :param electric_utility_factor: fraction of electricity that is generated from renewable sources
        :param drop_hybrids: boolean, if True, hybrid vehicles are dropped from the inventory
        :param payload: dictionary with payload for each powertrain-size-year combination
        :param energy_target: dictionary with energy target for each year
        :param energy_consumption: dictionary with energy consumption for each powertrain-size-year combination
        :param engine_efficiency: Fixed engine efficiencies keyed by
            ``(powertrain, size, year)``. Values are scalars or one value per sample,
            in (0, 1]. Unspecified cells retain their default efficiency model.
        :param transmission_efficiency: Fixed transmission efficiencies, with
            the same key and value contract as ``engine_efficiency``.
        :param combustion_controls: Opt-in conventional petrol-car controls keyed
            by (powertrain, size, year). See combustion control documentation.
        :param target_range: dictionary with target range for each powertrain-size-year combination
        :param fuel_blend: Fuel-category overrides. Supplied categories replace
            their defaults; omitted categories retain country/year defaults for
            the selected powertrains. None or an empty dictionary uses defaults.
        :param ambient_temperature: Celsius scalar or twelve monthly values for
            bus HVAC only. Other families use annual-average thermal-demand
            inputs and reject temperature overrides rather than ignoring them.
        :param indoor_temperature: Bus cabin setpoint in Celsius, default 20.
        :param battery_costs: Explicit battery unit costs, keyed by parameter
            name and then ``(powertrain, size, year)``. Values are nonnegative
            scalars or one value per sample. Useful for arrays without input
            provenance, or to explicitly choose a value equal to a default.

        """
        if (
            not isinstance(max_iterations, int)
            or isinstance(max_iterations, bool)
            or max_iterations < 1
        ):
            raise ValueError("max_iterations must be a positive integer.")
        self.max_iterations = max_iterations
        validate_vehicle_array(array)
        self.array = array.transpose(*REQUIRED_ARRAY_DIMS).copy(deep=True)
        self._selection_stack = []
        self.country = country

        self.vehicle_type = detect_vehicle_type(list(self.array.coords["size"].values))
        validate_control_keys(combustion_controls, self.array, self.vehicle_type)
        if combustion_controls and energy_consumption:
            raise ValueError(
                "Combustion controls cannot be combined with a consumption override."
            )
        self.combustion_controls = deepcopy(combustion_controls)

        indoor_temperature = validate_temperature(
            indoor_temperature, "Indoor temperature"
        )
        if ambient_temperature is not None:
            ambient_temperature = validate_temperature(
                ambient_temperature, "Ambient temperature"
            )
        if self.vehicle_type != "bus" and (
            ambient_temperature is not None
            or np.any(np.asarray(indoor_temperature) != 20)
        ):
            raise ValueError(
                "Temperature overrides are supported only by bus HVAC. "
                "Other vehicle families use annual-average thermal-demand inputs."
            )
        self.cycle = (
            cycle
            if type(cycle) in [np.ndarray, str, list]
            else get_default_driving_cycle_name(self.vehicle_type)
        )

        self.gradient = gradient
        self.energy_storage = (
            deepcopy(energy_storage) if energy_storage is not None else {}
        )
        self.energy_target = (
            deepcopy(energy_target)
            if energy_target is not None
            else {2025: 0.85, 2030: 0.7, 2050: 0.6}
        )
        self.payload = deepcopy(payload) if payload is not None else {}
        self.annual_mileage = (
            deepcopy(annual_mileage) if annual_mileage is not None else {}
        )
        self.energy = None
        self.electric_utility_factor = deepcopy(electric_utility_factor)
        self.drop_hybrids = drop_hybrids
        self.energy_consumption = (
            deepcopy(energy_consumption) if energy_consumption is not None else None
        )
        self.engine_efficiency = (
            deepcopy(engine_efficiency) if engine_efficiency is not None else None
        )
        self.transmission_efficiency = (
            deepcopy(transmission_efficiency)
            if transmission_efficiency is not None
            else None
        )

        # a range to reach can be defined by the user
        self.target_range = deepcopy(target_range)
        # a curb mass to reach can be defined by the user
        self.target_mass = deepcopy(target_mass)
        # overrides the engine/motor power
        self.power = deepcopy(power)

        self.bs = BackgroundSystemModel()

        self.fuel_blend = self.bs.define_fuel_blends(
            self.array.powertrain.values, self.country, self.array.year.values
        )
        if fuel_blend is not None:
            # Complete each override on its own: an omitted secondary component
            # uses the complementary share, not the country default's share.
            self.fuel_blend.update(self.check_fuel_blend(fuel_blend))

        self.ambient_temperature = ambient_temperature
        self.indoor_temperature = indoor_temperature

        self._battery_cost_inputs = capture_inputs(self.array)
        self._set_battery_cost_overrides(battery_costs)
        self._validate_phev_battery_costs()
        self.set_battery_chemistry()
        self.set_battery_preferences()

    def __call__(self, key: Union[str, List]):
        """
        This method fixes a dimension of the `array` attribute given
        a powertrain technology selected.
        Set up this class as a context manager,
        so we can have some nice syntax

        .. code-block:: python

            with class('some powertrain') as cpm:
                cpm['something']. # Will be filtered for the correct powertrain

        On with block exit, this filter is cleared
        https://stackoverflow.com/a/10252925/164864

        :param key: A powertrain type, e.g., "FCEV"
        :return: An instance of `array` filtered after the powertrain selected.

        """
        if isinstance(key, str):
            key = [key]

        if not hasattr(self, "_selection_stack"):
            self._selection_stack = []
        self._selection_stack.append(self.array)
        self.array = self.array.loc[
            dict(powertrain=[k for k in key if k in self.array.powertrain])
        ]
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.array = self._selection_stack.pop()

    def __getitem__(self, key: Union[str, List]) -> xr.DataArray:
        """
        Make class['foo'] automatically filter for the parameter 'foo'
        Makes the model code much cleaner

        :param key: Parameter name
        :return: `array` filtered after the parameter selected
        """

        return self.array.loc[dict(parameter=key)]

    def __setitem__(self, key, value):
        self.array.loc[{"parameter": key}] = value

    def iterate_sizing(self, parameter, rtol, mask=None):
        """Iterate sizing with per-vehicle/sample convergence diagnostics."""
        return iterate_until_converged(
            lambda: self[parameter] if mask is None else self[parameter].where(mask, 0),
            label=parameter,
            rtol=rtol,
            max_iterations=self.max_iterations,
        )

    def set_all(self):
        """
        Extension hook for downstream vehicle packages.

        Subclasses normally override this method to populate all calculated
        vehicle parameters. The base implementation intentionally does
        nothing to keep partial parent models instantiable.
        """
        pass

    def set_battery_chemistry(self):
        """
        Extension hook for downstream battery chemistry defaults.

        Subclasses can populate ``self.energy_storage`` before battery
        preferences are applied. The base implementation intentionally does
        nothing.
        """
        pass

    def set_battery_preferences(self):
        """Apply physical chemistry data independently of optional cost data.

        Generic battery costs are retained when a chemistry-specific cost is
        absent. ``battery_cost_fallbacks`` records those selections. Missing
        physical properties are errors, rather than silently leaving zeroes.
        """
        physical = (
            "battery cell energy density",
            "battery cell mass share",
            "battery cycle life",
        )
        cost = "energy battery cost per kWh"
        labels = set(self.array.parameter.values)
        fallbacks = []
        for key, chemistry in self.energy_storage.get("electric", {}).items():
            if not isinstance(key, tuple) or len(key) != 3:
                raise ValueError(
                    "Battery selection keys must be (powertrain, size, year)."
                )
            powertrain, size, year = key
            if chemistry is None or any(
                value not in self.array[dim].values
                for dim, value in (
                    ("powertrain", powertrain),
                    ("size", size),
                    ("year", year),
                )
            ):
                continue
            selection = dict(powertrain=powertrain, size=size, year=year)
            for parameter in (*physical, cost):
                if parameter not in labels:
                    continue
                source = f"{parameter}, {chemistry}"
                if source not in labels:
                    if parameter == cost:
                        fallbacks.append((key, chemistry))
                        continue
                    raise ValueError(
                        f"Missing {parameter!r} for chemistry {chemistry!r} at {key!r}."
                    )
                self.array.loc[dict(selection, parameter=parameter)] = self.array.sel(
                    dict(selection, parameter=source)
                ).values
        self.battery_cost_fallbacks = fallbacks
        self.apply_battery_cost_inputs()

    def _set_battery_cost_overrides(self, overrides):
        """Validate explicit prices, retaining zero and sample-specific values."""
        if overrides is None:
            return
        if not isinstance(overrides, dict):
            raise ValueError("battery_costs must be a dictionary.")
        for parameter, cells in overrides.items():
            if (
                not isinstance(parameter, str)
                or not is_battery_cost(parameter)
                or parameter not in self._battery_cost_inputs
                or not isinstance(cells, dict)
            ):
                raise ValueError(f"Invalid battery_costs parameter {parameter!r}.")
            values, explicit, _ = self._battery_cost_inputs[parameter]
            for key, amount in cells.items():
                if not isinstance(key, tuple) or len(key) != 3:
                    raise ValueError(
                        "battery_costs keys must be (powertrain, size, year)."
                    )
                selection = dict(zip(("powertrain", "size", "year"), key))
                if any(v not in values[d].values for d, v in selection.items()):
                    raise ValueError(f"Unknown battery_costs selection {key!r}.")
                try:
                    numeric = np.asarray(amount)
                    valid = (
                        numeric.dtype.kind in "iuf"
                        and numeric.shape in ((), (values.sizes["value"],))
                        and np.isfinite(numeric).all()
                        and (numeric >= 0).all()
                    )
                except (TypeError, ValueError):
                    valid = False
                if not valid:
                    raise ValueError(
                        f"battery_costs {parameter!r} at {key!r} must be finite, "
                        "nonnegative and scalar or one value per sample."
                    )
                values.loc[selection] = numeric
                explicit.loc[selection] = True
                self.array.loc[dict(selection, parameter=parameter)] = numeric

    def _validate_phev_battery_costs(self):
        """Reject prices that PHEV aggregation would silently discard."""
        for parameter, (values, explicit, _) in self._battery_cost_inputs.items():
            for final, combustion in (("PHEV-p", "PHEV-c-p"), ("PHEV-d", "PHEV-c-d")):
                if final not in values.powertrain.values:
                    continue
                chosen = explicit.sel(powertrain=final, drop=True)
                if not chosen.any():
                    continue
                price = values.sel(powertrain=final, drop=True)
                for component in ("PHEV-e", combustion):
                    if (
                        component not in values.powertrain.values
                        or (
                            chosen
                            & (
                                ~explicit.sel(powertrain=component, drop=True)
                                | (values.sel(powertrain=component, drop=True) != price)
                            )
                        ).any()
                    ):
                        raise ValueError(
                            f"Explicit {parameter!r} for {final} would be overwritten "
                            f"by PHEV aggregation. Set prices on PHEV-e and {combustion}; "
                            "leave the combined PHEV input unchanged, or give it "
                            "the same explicit price as both components."
                        )

    def apply_battery_cost_inputs(self, projected=False):
        """Restore explicit prices after chemistry or automatic cost adjustment.

        Generic explicit prices take precedence over selected-chemistry prices.
        Generated sensitivity samples perturb the projected default, while
        ordinary array edits are absolute unit prices. Partial base models
        without captured inputs keep the permissive legacy hook behavior.
        """
        inputs = getattr(self, "_battery_cost_inputs", {})
        for parameter in (ENERGY_COST, POWER_COST):
            if parameter not in inputs:
                continue
            values, explicit, multiplier = (
                a.sel({d: self.array[d] for d in a.dims}) for a in inputs[parameter]
            )
            prices = self[parameter].reset_coords(drop=True)
            if projected:
                prices = prices * multiplier
            if parameter == ENERGY_COST:
                for (powertrain, size, year), chemistry in self.energy_storage.get(
                    "electric", {}
                ).items():
                    specific = inputs.get(f"{ENERGY_COST}, {chemistry}")
                    selection = dict(powertrain=powertrain, size=size, year=year)
                    if specific is None or any(
                        v not in prices[d].values for d, v in selection.items()
                    ):
                        continue
                    cost, chosen, factor = (a.sel(selection) for a in specific)
                    default = prices.sel(selection)
                    if projected:
                        default = default * factor
                    prices.loc[selection] = xr.where(chosen, cost, default)
            self[parameter] = xr.where(explicit, values, prices)

    def _get_cost_factors(self):
        """Reuse input cost draws; initialize legacy arrays once on this model."""
        self.array = attach_cost_factors(self.array)
        return tuple(
            self.array.coords[name].reset_coords(drop=True)
            for name in (GENERAL_FACTOR, FCEV_FACTOR)
        )

    def adjust_cost(self) -> None:
        """
        This method adjusts costs of energy storage over time, to correct for the overly optimistic linear
        interpolation between years.

        """

        cost_factor, _ = self._get_cost_factors()
        years = self.array.year

        # Hydrogen tank cost per kg of stored hydrogen, and stack cost per kW.
        if "FCEV" in self.array.powertrain:
            self.array.loc[
                dict(powertrain="FCEV", parameter="fuel tank cost per kg")
            ] = (1.078e58 * np.exp(-6.32e-2 * years) + 3.43e2) * cost_factor

            self.array.loc[
                dict(powertrain="FCEV", parameter="fuel cell cost per kW")
            ] = (3.15e66 * np.exp(-7.35e-2 * years) + 2.39e1) * cost_factor

        # Correction of energy battery system cost, per kWh
        list_batt = [
            i
            for i in ["BEV", "PHEV-e", "PHEV-c-p", "PHEV-c-d"]
            if i in self.array.powertrain
        ]
        if len(list_batt) > 0:
            self.array.loc[
                dict(powertrain=list_batt, parameter="energy battery cost per kWh")
            ] = (2.75e86 * np.exp(-9.61e-2 * years) + 5.059e1) * cost_factor

        # Correction of power battery system cost, per kW
        list_pwt = [
            i
            for i in [
                "ICEV-p",
                "ICEV-d",
                "ICEV-g",
                "PHEV-c-p",
                "PHEV-c-d",
                "FCEV",
                "HEV-p",
                "HEV-d",
            ]
            if i in self.array.powertrain
        ]

        if len(list_pwt) > 0:
            self.array.loc[
                dict(powertrain=list_pwt, parameter="power battery cost per kW")
            ] = (8.337e40 * np.exp(-4.49e-2 * years) + 11.17) * cost_factor

        # Correction of combustion powertrain cost for ICEV-g
        if "ICEV-g" in self.array.powertrain:
            self.array.loc[
                dict(powertrain="ICEV-g", parameter="combustion powertrain cost per kW")
            ] = np.clip(
                ((5.92e160 * np.exp(-0.1819 * years) + 26.76) * cost_factor),
                None,
                100,
            )

        self.apply_battery_cost_inputs(projected=True)

    def drop_hybrid(self) -> None:
        """
        This method drops the powertrains `PHEV-c-p`, `PHEV-c-d` and `PHEV-e` as they were only used to create the
        `PHEV` powertrain.
        :returns: Does not return anything. Modifies ``self.array`` in place.
        """
        self.array = self.array.sel(
            powertrain=[
                pt
                for pt in self.array.coords["powertrain"].values
                if pt not in ["PHEV-e", "PHEV-c-p", "PHEV-c-d"]
            ]
        )

    def set_electricity_consumption(self) -> None:
        """
        This method calculates the total electricity consumption for BEV
        and plugin-hybrid vehicles
        :returns: Does not return anything. Modifies ``self.array`` in place.
        """
        _ = lambda x: np.where(x == 0, 1, x)

        self["electricity consumption"] = (
            self["TtW energy"]
            / _(self["battery charge efficiency"])
            / _(self["charger efficiency"])
            / 3600
            * (self["charger mass"] > 0)
        )

        var = (
            "range"
            if "range" in self.array.coords["parameter"].values
            else (
                "target range"
                if "target range" in self.array.coords["parameter"].values
                else "daily distance"
            )
        )

        self["fuel consumption"] = (
            self["fuel mass"] / _(self[var]) / _(self["fuel density per kg"])
        )

    def override_ttw_energy(self):
        # override of TtW energy, provided by the user
        if self.energy_consumption:
            for key, val in self.energy_consumption.items():
                pwt, size, year = key
                if val is not None:
                    # Overrides use the public stored-energy boundary. The
                    # trace uses delivered DC until final battery accounting.
                    trace_value = val
                    if pwt.startswith("BEV") or pwt == "PHEV-e":
                        trace_value = val * self["battery discharge efficiency"].sel(
                            powertrain=pwt, size=size, year=year
                        )
                    print(
                        f"Overriding TtW energy for {pwt} {size} {year} "
                        f"with {val} kj/km"
                    )

                    distance = (
                        self.energy.sel(
                            parameter="velocity",
                            powertrain=pwt,
                            size=size,
                            year=year,
                        ).sum(dim="second")
                        / 1000
                    )

                    self.energy.loc[
                        dict(
                            powertrain=pwt,
                            size=size,
                            year=year,
                            parameter="motive energy",
                        )
                    ] = (
                        trace_value * distance / self.energy.shape[0]
                    )

                    self.energy.loc[
                        dict(
                            powertrain=pwt,
                            size=size,
                            year=year,
                            parameter=[
                                "auxiliary energy",
                                "recuperated energy",
                                "cooling energy",
                                "heating energy",
                                "battery cooling energy",
                                "battery heating energy",
                            ],
                        )
                    ] = 0

                    # update self["TtW energy"]
                    self["TtW energy"] = (
                        self.energy.sel(
                            parameter=[
                                "motive energy",
                                "auxiliary energy",
                                "recuperated energy",
                            ]
                        ).sum(dim=["second", "parameter"])
                        / distance
                    ).T

            # we flag vehicles that are not compliant
            if "gross mass" in self.array.parameter.values:
                self["TtW energy"] = np.where(
                    (self["driving mass"] > self["gross mass"]), 0, self["TtW energy"]
                )

    def calculate_ttw_energy(self) -> None:
        """
        This method calculates the energy required to operate auxiliary
        services as well as to move the car. The sum is stored under the
        parameter label "TtW energy" in :attr:`self.array`.

        """

        pass

    def set_fuel_cell_mass(self):
        """
        Specific setup for fuel cells, which are mild hybrids.
        Must be called after :meth:`.set_power_parameters`.
        """

        # our basic fuel cell mass is based
        # on a car fuel cell with 800 mW/cm2
        # the cell power density is adapted for truck or bus use
        # it is decreased comparatively to that of a passenger car
        # to reflect increased durability

        _ = lambda x: np.where(x == 0, 1, x)

        self["fuel cell stack mass"] = (
            self["fuel cell power density"]
            * self["fuel cell power"]
            * (800 / _(self["fuel cell power area density"]))
        )
        self["fuel cell ancillary BoP mass"] = (
            self["fuel cell power"] * self["fuel cell ancillary BoP mass per power"]
        )
        self["fuel cell essential BoP mass"] = (
            self["fuel cell power"] * self["fuel cell essential BoP mass per power"]
        )

        if "FCEV" in self.array.powertrain.values:
            self.array.loc[
                dict(parameter="battery power", powertrain="FCEV")
            ] = self.array.loc[dict(parameter="fuel cell power", powertrain="FCEV")] * (
                np.array(1)
                - self.array.loc[
                    dict(parameter="fuel cell power share", powertrain="FCEV")
                ]
            )

            self.array.loc[dict(parameter="battery cell mass", powertrain="FCEV")] = (
                self.array.loc[dict(parameter="battery power", powertrain="FCEV")]
                / self.array.loc[
                    dict(parameter="battery cell power density", powertrain="FCEV")
                ]
            )

            self.array.loc[
                dict(parameter="battery BoP mass", powertrain="FCEV")
            ] = self.array.loc[
                dict(parameter="battery cell mass", powertrain="FCEV")
            ] * (
                np.array(1)
                - self.array.loc[
                    dict(parameter="battery cell mass share", powertrain="FCEV")
                ]
            )

            self.array.loc[dict(parameter="energy battery mass", powertrain="FCEV")] = (
                self.array.loc[dict(parameter="battery cell mass", powertrain="FCEV")]
                + self.array.loc[dict(parameter="battery BoP mass", powertrain="FCEV")]
            )

            self.array.loc[
                dict(parameter="electric energy stored", powertrain="FCEV")
            ] = (
                self.array.loc[dict(parameter="battery cell mass", powertrain="FCEV")]
                * self.array.loc[
                    dict(parameter="battery cell energy density", powertrain="FCEV")
                ]
            )

    def set_fuel_cell_power(self) -> None:
        """
        Specific setup for fuel cells, which are mild hybrids.
        Must be called after :meth:`.set_power_parameters`.
        """

        _ = lambda x: np.where(x == 0, 1, x)

        self["fuel cell system efficiency"] = (
            self["fuel cell stack efficiency"]
            / _(self["fuel cell own consumption"])
            * (self["fuel cell own consumption"] > 0)
        )

        self["fuel cell power"] = (
            self["power"]
            * self["fuel cell power share"]
            * self["fuel cell own consumption"]
        )

    def set_auxiliaries(self) -> None:
        """
        Calculates the power needed to operate the auxiliary services
        of the vehicle (heating, cooling).

        The demand for heat and cold are expressed as a fraction of the
        heating and cooling capacities

        .. note:

            Auxiliary power demand (W) = Base auxiliary power (W) +
            (Heating demand (dimensionless, between 0 and 1) * Heating power (W)) +
            (Cooling demand (dimensionless, between 0 and 1) * Cooling power (W))

        """
        self["auxiliary power demand"] = (
            self["auxilliary power base demand"]
            + self["heating thermal demand"] * self["heating energy consumption"]
            + self["cooling thermal demand"] * self["cooling energy consumption"]
        )

    def get_energy_efficiency_override(self, parameter, default=None):
        """Return per-cell fixed efficiencies for the energy model.

        Public override keys are ``(powertrain, size, year)``; each value is a
        scalar or one value per sample. Unspecified cells retain the supplied
        default (two-wheelers) or the shared load-dependent map. Explicit electric
        component priors take precedence over these defaults; user overrides
        take precedence over component priors.
        """
        overrides = getattr(self, parameter.replace(" ", "_"))
        if overrides is not None and not isinstance(overrides, dict):
            raise ValueError(f"{parameter} overrides must be a dictionary.")
        values = xr.zeros_like(self[parameter], dtype=float)
        mask = xr.ones_like(values, dtype=bool)
        if default is not None:
            values[:] = default
            mask[:] = False
        component = {
            "engine efficiency": "electric motor efficiency",
            "transmission efficiency": "electric transmission efficiency",
        }[parameter]
        if component in self.array.parameter:
            electric = self.array.powertrain.str.startswith("BEV") | (
                self.array.powertrain.isin(["PHEV-e", "FCEV"])
            )
            specified = electric & (self[component] != 0)
            values = xr.where(specified, self[component], values)
            mask = xr.where(specified, False, mask)
        for key, value in (overrides or {}).items():
            if not isinstance(key, tuple) or len(key) != 3:
                raise ValueError(
                    f"{parameter}: expected (powertrain, size, year), got {key!r}."
                )
            selection = dict(zip(("powertrain", "size", "year"), key))
            if any(label not in values.coords[dim] for dim, label in selection.items()):
                raise ValueError(
                    f"{parameter}: override coordinate {key!r} is outside the model scope."
                )
            value = np.asarray(value, dtype=float)
            if (
                value.ndim > 1
                or not np.isfinite(value).all()
                or np.any((value <= 0) | (value > 1))
            ):
                raise ValueError(
                    f"{parameter} at {key!r} must be finite and in (0, 1]."
                )
            if value.ndim == 1 and value.size != values.sizes["value"]:
                raise ValueError(
                    f"{parameter} at {key!r}: expected one value per sample."
                )
            values.loc[selection] = value
            mask.loc[selection] = False
        dimensions = self[parameter].dims
        return np.ma.array(
            values.transpose(*dimensions).values,
            mask=mask.transpose(*dimensions).values,
        )

    def set_recuperation(self):
        self["recuperation efficiency"] = self["transmission efficiency"] * (
            self["electric power"] > 0
        )

    def get_electric_motor_efficiency(self):
        """Assumed bidirectional motor efficiency for regenerative energy reuse.

        This is a cycle-average component assumption, not a fitted hybrid
        fuel efficiency. It can be supplied as an input parameter; 0.9 is the
        fallback for tables predating the parameter.
        """
        if "electric motor efficiency" in self.array.parameter.values:
            value = self["electric motor efficiency"]
            return xr.where(value == 0, 0.9, value)
        return xr.full_like(self["power"], 0.9, dtype=float)

    def get_regeneration_credit(self):
        """Convert reusable DC electricity to avoided propulsion input (kJ/km).

        Hybrid reuse passes through the electric motor and transmission, then
        displaces fuel at the cycle's positive-work-weighted conversion ratio.
        Fuel-cell reuse displaces DC fuel-cell output. Fuel savings cannot exceed
        positive propulsion input; excess recovered energy receives no fuel credit.
        """
        energy = self.energy
        distance = energy.sel(parameter="velocity").sum("second") / 1000
        recovered = -energy.sel(parameter="recuperated energy").sum("second")
        positive_input = energy.sel(parameter="motive energy").sum("second")
        positive_wheels = energy.sel(parameter="motive energy at wheels").sum("second")
        # Work weighting avoids charging idle/deceleration samples a fictitious
        # transmission loss when estimating propulsion displaced by recovery.
        transmission = energy.sel(parameter="transmission efficiency")
        wheel_power = energy.sel(parameter="motive energy at wheels")
        mean_transmission = (transmission * wheel_power).sum("second") / xr.where(
            positive_wheels > 0, positive_wheels, 1
        )
        motor = self.get_electric_motor_efficiency().transpose(
            "value", "year", "powertrain", "size"
        )
        combustion = (self["combustion power share"] > 0).transpose(
            "value", "year", "powertrain", "size"
        )
        fuel_cell = self["fuel cell system efficiency"].transpose(
            "value", "year", "powertrain", "size"
        )
        fuel_per_wheel = positive_input / xr.where(
            positive_wheels > 0, positive_wheels, 1
        )
        credit = xr.where(
            combustion,
            recovered * motor * mean_transmission * fuel_per_wheel,
            recovered,
        )
        credit = xr.where(
            fuel_cell > 0, recovered / xr.where(fuel_cell > 0, fuel_cell, 1), credit
        )
        credit = xr.where(
            combustion | (fuel_cell > 0), np.minimum(credit, positive_input), credit
        )
        self.regeneration_credit = -credit / xr.where(distance > 0, distance, 1)
        return self.regeneration_credit.transpose("size", "powertrain", "year", "value")

    def mask_energy_outputs(self, available: xr.DataArray) -> None:
        """Apply vehicle availability consistently to reported energy demands.

        ``available`` expresses technology and mass policy, not whether net
        energy happens to be zero. Retain the second-by-second energy trace
        for diagnostics; mask reported supply and battery-terminal outputs.
        """
        for parameter in (
            "TtW energy",
            "TtW energy, combustion mode",
            "TtW energy, electric mode",
            "auxiliary energy",
            "electricity consumption",
            "fuel consumption",
        ):
            if parameter in self.array.parameter.values:
                self[parameter] = self[parameter].where(available, 0)
        if hasattr(self, "battery_terminal_energy"):
            # PHEV aggregation can remove intermediate powertrain coordinates.
            # Report terminal demand only for the retained public vehicle grid.
            self.battery_terminal_energy = self.battery_terminal_energy.reindex_like(
                available, fill_value=0
            ).where(available, 0)

    def set_battery_energy_balance(self, *, include_recuperation=True) -> None:
        """Convert electric-mode TtW demand from reusable DC to stored kJ/km.

        Positive DC demand D and generator output R imply a stored-energy
        decrease D / eta_discharge - R * eta_charge. The energy trace reports
        recuperation as R * eta_charge * eta_discharge, so dividing its net DC
        demand by eta_discharge gives precisely this balance. Terminal demand
        D - R is retained separately for comparisons with onboard meters.

        Combustion and fuel-cell TtW values already refer to fuel input and
        are unchanged. Two-wheelers can explicitly omit recuperation until a
        regenerative drivetrain is specified.
        """
        electric = self.array.powertrain.str.startswith("BEV") | (
            self.array.powertrain == "PHEV-e"
        )
        discharge = self["battery discharge efficiency"]
        charge = self["battery charge efficiency"]
        active = electric & (self["TtW energy"] != 0)
        for name, efficiency in (("discharge", discharge), ("charge", charge)):
            invalid = active & (
                ~np.isfinite(efficiency) | (efficiency <= 0) | (efficiency > 1)
            )
            if bool(invalid.any()):
                raise ValueError(
                    f"Active battery vehicles require {name} efficiency in (0, 1]."
                )
        safe_discharge = discharge.where(active, 1)
        safe_charge = charge.where(active, 1)
        distance = self.energy.sel(parameter="velocity").sum("second") / 1000
        recovered = (
            -self.energy.sel(parameter="recuperated energy").sum("second")
            / xr.where(distance > 0, distance, 1)
        ).transpose("size", "powertrain", "year", "value")
        if not include_recuperation:
            recovered = xr.zeros_like(recovered)
        positive_dc = self["TtW energy"] + recovered
        self.battery_terminal_energy = (
            positive_dc - recovered / (safe_charge * safe_discharge)
        ).where(electric, 0)
        self["TtW energy"] = xr.where(
            electric, self["TtW energy"] / safe_discharge, self["TtW energy"]
        )

    def set_battery_fuel_cell_replacements(self) -> None:
        """
        Calculates the fraction of the replacement battery
        needed to match the vehicle lifetime.

        .. note::
            if ``car lifetime`` = 200000 (km) and
            ``battery lifetime`` = 190000 (km)
            then ``replacement battery`` = 0.05

        .. note::
            It is debatable whether this is realistic or not.
            Car owners may not decide to invest in a new
            battery if the remaining lifetime of the car is
            only 10000 km. Also, a battery lifetime may be expressed
            in other terms, e.g., charging cycles.

        """
        # We estimate here battery replacements
        # We use two methods:
        # 1) the lifetime of the battery (in km) over the vehicle's lifetime (in km)
        # 2) the lifetime of the vehicle (in years) over the lifetime of the battery (in years)
        # Which ever is the highest is used to calculate the number of replacements

        # The number of battery replacements is based on the
        # average distance driven with a set of batteries given
        # their lifetime expressed in kilometers.

        battery_replacement_km = finite(
            np.clip(
                (self["lifetime kilometers"] / self["battery lifetime kilometers"]) - 1,
                0,
                None,
            )
        )

        battery_replacement_years = finite(
            np.clip(
                (
                    (self["lifetime kilometers"] / self["kilometers per year"])
                    / 18  # 18 years is the maximum lifetime of a battery
                )
                - 1,
                0,
                None,
            )
        )

        self["battery lifetime replacements"] = np.maximum(
            battery_replacement_km, battery_replacement_years
        )

        # The number of fuel cell replacements is based on the
        # average distance driven with a set of fuel cells given
        # their lifetime expressed in hours of use.
        # The number of replacement is rounded *up* as we assume
        # no allocation of burden with a second life

        average_speed = (
            np.nanmean(
                np.where(
                    self.energy.sel(parameter="velocity") > 0,
                    self.energy.sel(parameter="velocity"),
                    np.nan,
                ),
                0,
            )
            * 3.6
        )

        _ = lambda array: np.where(array == 0, 1, array)

        self["fuel cell lifetime replacements"] = np.ceil(
            np.clip(
                self["lifetime kilometers"]
                / (average_speed.T * _(self["fuel cell lifetime hours"]))
                - 1,
                0,
                5,
            )
        ) * (self["fuel cell lifetime hours"] > 0)

    def override_vehicle_mass(self):
        for key, target_mass in self.target_mass.items():
            pwt, size, year = key

            if target_mass:
                current_curb_mass = self.array.loc[
                    dict(powertrain=pwt, size=size, year=year, parameter="curb mass")
                ]
                mass_difference = target_mass - current_curb_mass

                self.array.loc[
                    dict(
                        powertrain=pwt,
                        size=size,
                        year=year,
                        parameter="glider base mass",
                    )
                ] += mass_difference / (
                    1
                    - self.array.loc[
                        dict(
                            powertrain=pwt,
                            size=size,
                            year=year,
                            parameter="lightweighting",
                        )
                    ]
                )

                self.array.loc[
                    dict(powertrain=pwt, size=size, year=year, parameter="curb mass")
                ] = target_mass

    def override_power(self):
        if self.power:
            for key, power in self.power.items():
                pwt, size, year = key
                if power:
                    self.array.loc[
                        dict(powertrain=pwt, size=size, year=year, parameter="power")
                    ] = power

    def set_power_parameters(self) -> None:
        """
        Set electric and combustion motor powers
        based on input parameter ``power to mass ratio``.
        """
        # Convert from W/kg to kW
        self["power"] = self["power to mass ratio"] * self["curb mass"] / 1000

        if self.power:
            self.override_power()

        self["combustion power share"] = self["combustion power share"].clip(0, 1)
        self["combustion power"] = self["power"] * self["combustion power share"]
        self["electric power"] = self["power"] * (
            np.array(1) - self["combustion power share"]
        )
        if "electric motor power share" in self.array.parameter.values:
            share = self["electric motor power share"]
            if np.any(~np.isfinite(share)) or np.any(share < 0):
                raise ValueError(
                    "Electric motor power share must be finite and nonnegative."
                )
            # Hybrid component peak ratings need not sum to the combined system
            # rating: their peaks can occur at different speeds. Zero retains
            # the legacy complementary split for records without this input.
            self["electric power"] = xr.where(
                share > 0, self["power"] * share, self["electric power"]
            )

    def set_component_masses(self) -> None:
        self["combustion engine mass"] = (
            self["combustion power"] * self["combustion mass per power"]
            + self["combustion fixed mass"]
        )

        self["electric engine mass"] = (
            self["electric power"] * self["electric mass per power"]
            + self["electric fixed mass"]
        ) * (self["electric power"] > 0)

        self["powertrain mass"] = (
            self["power"] * self["powertrain mass per power"]
            + self["powertrain fixed mass"]
        )

    def set_share_recuperated_energy(self) -> None:
        """
        Calculate the share of recuperated energy,
        over the total negative motive energy.
        """

        _ = lambda x: np.where(x == 0, 1, x)

        self["share recuperated energy"] = (
            self.energy.sel(parameter="recuperated energy").sum(dim="second")
            / _(self.energy.sel(parameter="negative motive energy").sum(dim="second"))
        ).values.T
        self["share recuperated energy"] *= self["electric power"] > 0

        if "PHEV-d" in self.array.powertrain:
            self.array.loc[
                dict(powertrain="PHEV-c-d", parameter="share recuperated energy")
            ] = self.array.loc[
                dict(powertrain="PHEV-e", parameter="share recuperated energy")
            ]

        if "PHEV-p" in self.array.powertrain:
            self.array.loc[
                dict(powertrain="PHEV-c-p", parameter="share recuperated energy")
            ] = self.array.loc[
                dict(powertrain="PHEV-e", parameter="share recuperated energy")
            ]

    def set_electric_utility_factor(self) -> None:
        pass

    def create_PHEV(self):
        """
        Function to create plugin-hybrid vehicles.
        PHEV-p/d is the range-weighted average
        between PHEV-c-p/PHEV-c-d and PHEV-e.
        """
        _ = lambda array: np.where(array == 0, 1, array)

        for pwt, pwtc in (("PHEV-d", "PHEV-c-d"), ("PHEV-p", "PHEV-c-p")):
            if pwt in self.array.coords["powertrain"].values:
                self.array.loc[:, pwt] = (
                    self.array.loc[:, "PHEV-e"]
                    * self.array.loc[:, "PHEV-e", "electric utility factor"]
                ) + (
                    self.array.loc[:, pwtc]
                    * (
                        np.array(1)
                        - self.array.loc[:, "PHEV-e", "electric utility factor"]
                    )
                )

                self.array.loc[:, pwt, "electric utility factor"] = self.array.loc[
                    :, "PHEV-e", "electric utility factor"
                ]

                self.energy.loc[
                    dict(
                        powertrain=pwt,
                    )
                ] = self.energy.loc[dict(powertrain="PHEV-e")]

                self.energy.loc[
                    dict(
                        powertrain=pwt,
                    )
                ] *= self.array.loc[
                    dict(parameter="electric utility factor", powertrain="PHEV-e")
                ].T.values[None, ..., None]

                self.energy.loc[
                    dict(
                        powertrain=pwt,
                    )
                ] += (
                    np.array(1)
                    - self.array.loc[
                        dict(parameter="electric utility factor", powertrain="PHEV-e")
                    ].T.values[None, ..., None]
                ) * self.energy.loc[dict(powertrain=pwtc)]

                # We need to preserve the fuel mass and fuel tank mass
                self.array.loc[
                    dict(
                        parameter=[
                            # "fuel mass",
                            "fuel tank mass",
                            "oxidation energy stored",
                            "LHV fuel MJ per kg",
                            "fuel density per kg",
                        ],
                        powertrain=pwt,
                    )
                ] = self.array.loc[
                    dict(
                        parameter=[
                            "fuel tank mass",
                            "oxidation energy stored",
                            "LHV fuel MJ per kg",
                            "fuel density per kg",
                        ],
                        powertrain=pwtc,
                    )
                ]

                # we need to preserve the battery mass from PHEV-e as well
                self.array.loc[
                    dict(
                        parameter=[
                            "energy battery mass",
                            "battery BoP mass",
                            "battery cell mass",
                            "battery DoD",
                            "battery cell energy density",
                            "battery charge efficiency",
                            "battery discharge efficiency",
                            "battery lifetime kilometers",
                            "charger efficiency",
                            "recuperation efficiency",
                            "charger mass",
                            "inverter mass",
                            "power distribution unit mass",
                        ],
                        powertrain=pwt,
                    )
                ] = self.array.loc[
                    dict(
                        parameter=[
                            "energy battery mass",
                            "battery BoP mass",
                            "battery cell mass",
                            "battery DoD",
                            "battery cell energy density",
                            "battery charge efficiency",
                            "battery discharge efficiency",
                            "battery lifetime kilometers",
                            "charger efficiency",
                            "recuperation efficiency",
                            "charger mass",
                            "inverter mass",
                            "power distribution unit mass",
                        ],
                        powertrain="PHEV-e",
                    )
                ]

                # We store the tank-to-wheel energy consumption
                # in combustion and electric mode separately
                self.array.loc[
                    dict(parameter="TtW energy", powertrain=pwt)
                ] = self.array.loc[dict(parameter="TtW energy", powertrain=pwtc)] * (
                    1
                    - self.array.loc[
                        dict(parameter="electric utility factor", powertrain="PHEV-e")
                    ]
                )
                self.array.loc[
                    dict(parameter="TtW energy", powertrain=pwt)
                ] += self.array.loc[
                    dict(parameter="TtW energy", powertrain="PHEV-e")
                ] * (
                    self.array.loc[
                        dict(parameter="electric utility factor", powertrain="PHEV-e")
                    ]
                )

                self.array.loc[
                    dict(parameter="TtW energy, combustion mode", powertrain=pwt)
                ] = self.array.loc[dict(parameter="TtW energy", powertrain=pwtc)]

                self.array.loc[
                    dict(parameter="TtW energy, electric mode", powertrain=pwt)
                ] = self.array.loc[dict(parameter="TtW energy", powertrain="PHEV-e")]

                # We need to recalculate the tank-to-wheel efficiency

                distance = (
                    self.energy.sel(
                        parameter="velocity",
                        powertrain=pwtc,
                    ).sum(dim="second")
                    / 1000
                )

                self.array.loc[dict(parameter="TtW efficiency", powertrain=pwt)] = (
                    self.energy.sel(
                        parameter=["motive energy at wheels", "negative motive energy"],
                        powertrain=pwt,
                    ).sum(dim=["second", "parameter"])
                    / distance
                ) / self.array.loc[dict(parameter="TtW energy", powertrain=pwt)]

                # We need to recalculate the range as well

                var = (
                    "range"
                    if "range" in self.array.coords["parameter"].values
                    else (
                        "target range"
                        if "target range" in self.array.coords["parameter"].values
                        else "daily distance"
                    )
                )

                self.array.loc[dict(parameter=var, powertrain=pwt)] = (
                    self.array.loc[
                        dict(parameter="oxidation energy stored", powertrain=pwt)
                    ]
                    * 3600
                    / self.array.loc[
                        dict(parameter="TtW energy, combustion mode", powertrain=pwt)
                    ]
                )

                self.array.loc[dict(parameter=var, powertrain=pwt)] += (
                    self.array.loc[
                        dict(parameter="electric energy stored", powertrain=pwt)
                    ]
                    * 3600
                    / self.array.loc[
                        dict(parameter="TtW energy, electric mode", powertrain="PHEV-e")
                    ]
                )

    def set_battery_properties(self) -> None:
        """
        Calculate mass and power of batteries.
        :return:
        """

        self["battery cell mass"] = (
            self["energy battery mass"] * self["battery cell mass share"]
        )

        self["battery BoP mass"] = self["energy battery mass"] * (
            np.array(1.0) - self["battery cell mass share"]
        )

    def _set_battery_capacity(self, selection, capacity):
        """Set nominal capacity (kWh) and pack/component masses (kg) in one cell."""
        vehicle = self.array.sel(selection)
        cell_mass = capacity / vehicle.sel(parameter="battery cell energy density")
        pack_mass = cell_mass / vehicle.sel(parameter="battery cell mass share")
        for parameter, value in {
            "energy battery mass": pack_mass,
            "battery cell mass": cell_mass,
            "battery BoP mass": pack_mass - cell_mass,
            "electric energy stored": capacity,
        }.items():
            self.array.loc[dict(parameter=parameter, **selection)] = value

    def override_battery_capacity(self) -> None:
        """Apply nominal-capacity overrides only to their selected vehicles.

        Other vehicles retain their existing battery properties, including
        power batteries whose cell/pack split uses a different sizing method.
        Vehicle mass, energy demand and range are calculated by the sizing loop.
        """
        for (pwt, size, year), capacity in self.energy_storage["capacity"].items():
            if capacity:
                self._set_battery_capacity(
                    dict(powertrain=pwt, size=size, year=year), capacity
                )

    def override_range(self):
        """Resize only the specified BEVs using their current stored-energy demand.

        The caller must converge vehicle mass and energy demand with this sizing
        step. Unselected vehicles retain their properties, including FCEV power
        batteries whose mass calculation differs from energy batteries.
        """
        for (pwt, size, year), target in (self.target_range or {}).items():
            if pwt != "BEV" or target is None:
                continue
            selection = dict(powertrain=pwt, size=size, year=year)
            vehicle = self.array.sel(selection)
            demand = vehicle.sel(parameter="TtW energy")  # kJ/km
            depth = vehicle.sel(parameter="battery DoD")
            capacity = target * demand / depth / 3600  # nominal kWh
            self._set_battery_capacity(selection, capacity)
            self.array.loc[dict(parameter="range", **selection)] = (
                capacity * depth * 3600 / demand
            )

    def set_range(self) -> None:
        """
        Calculate range autonomy of vehicles
        :return:
        """

        self["range"] = (
            self["fuel mass"] * self["LHV fuel MJ per kg"] * np.array(1000)
        ) / self["TtW energy"]

        self["range"] += (
            self["electric energy stored"]
            * self["battery DoD"]
            * np.array(3600)
            / self["TtW energy"]
        )

    def check_fuel_blend(self, fuel_blend: dict) -> dict:
        """Validate and complete fuel shares without modifying caller data.

        Shares may be scalars or one-dimensional arrays with one entry per model
        year. Primary and secondary shares must sum to one for every year.
        Both components must use fuel types listed in the requested category.
        Property overrides use the same year order: lhv (MJ/kg) and density
        (kg/L) must be positive, CO2 (kg/kg fuel) nonnegative, and the biogenic
        fraction within [0, 1]. All numeric inputs must be finite.
        """
        if not isinstance(fuel_blend, dict):
            raise ValueError("fuel_blend must be a dictionary.")
        fuel_blend = deepcopy(fuel_blend)
        default_specs = load_default_specs_for_fuels()
        n_years = self.array.sizes["year"]

        def numeric_values(context, field, value):
            try:
                values = np.asarray(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{context}: {field} must be numeric.") from exc
            if values.dtype.kind not in "iuf":
                raise ValueError(f"{context}: {field} must be numeric.")
            if values.ndim > 1 or values.size not in (1, n_years):
                raise ValueError(
                    f"{context}: {field} must be scalar or have one entry per "
                    f"model year ({self.array.year.values.tolist()})."
                )
            if not np.isfinite(values).all():
                raise ValueError(f"{context}: {field} must contain finite values.")
            return values

        def validate_component(fuel, role, component):
            context = f"Fuel blend {fuel!r}, {role}"
            if not isinstance(component, dict):
                raise ValueError(f"{context} must be a dictionary.")
            fuel_type = component.get("type")
            if not isinstance(fuel_type, str) or fuel_type not in self.bs.fuel_specs:
                raise ValueError(f"{context}: unknown fuel type {fuel_type!r}.")
            if fuel_type not in default_specs[fuel]["all"]:
                raise ValueError(
                    f"{context}: fuel type {fuel_type!r} is not allowed "
                    f"in the {fuel!r} category."
                )
            if "share" not in component:
                raise ValueError(f"{context}: share is required.")
            share = numeric_values(context, "share", component["share"])
            if ((share < 0) | (share > 1)).any():
                raise ValueError(f"{context}: shares must be within [0, 1].")
            component["share"] = np.broadcast_to(share, (n_years,)).astype(float)
            specification = self.bs.fuel_specs[fuel_type]
            component.setdefault("name", tuple(specification["name"]))
            component.setdefault("CO2", specification["co2"])
            component.setdefault("biogenic share", specification["biogenic_share"])
            for field in ("lhv", "density", "CO2", "biogenic share"):
                if field not in component:
                    continue
                values = numeric_values(context, field, component[field])
                if field in ("lhv", "density"):
                    valid, requirement = values > 0, "strictly positive"
                elif field == "CO2":
                    valid, requirement = values >= 0, "nonnegative"
                else:
                    valid = (values >= 0) & (values <= 1)
                    requirement = "within [0, 1]"
                if not valid.all():
                    raise ValueError(f"{context}: {field} must be {requirement}.")
                component[field] = (
                    float(values)
                    if values.ndim == 0
                    else np.broadcast_to(values, (n_years,)).astype(float)
                )
            return component

        for fuel, specs in fuel_blend.items():
            if fuel not in default_specs:
                raise ValueError(f"Unknown fuel blend category {fuel!r}.")
            if not isinstance(specs, dict) or "primary" not in specs:
                raise ValueError(f"Primary fuel not specified for {fuel}.")
            primary = validate_component(fuel, "primary", specs["primary"])
            if "secondary" not in specs:
                secondary_type = default_specs[fuel]["secondary"]
                if secondary_type == primary["type"]:
                    secondary_type = next(
                        candidate
                        for candidate in default_specs[fuel]["all"]
                        if candidate != primary["type"]
                    )
                specs["secondary"] = {
                    "type": secondary_type,
                    "share": 1 - primary["share"],
                }
            secondary = validate_component(fuel, "secondary", specs["secondary"])
            if not np.allclose(
                primary["share"] + secondary["share"], 1, rtol=0, atol=1e-7
            ):
                raise ValueError(
                    f"Fuel blend {fuel!r}: primary and secondary shares "
                    "must sum to one for every model year."
                )
        return fuel_blend

    def set_average_lhv(self) -> None:
        """
        Calculate average LHV of fuel.
        :return:
        """

        d_map_fuel = {
            "ICEV-p": "petrol",
            "ICEV-d": "diesel",
            "HEV-d": "diesel",
            "HEV-p": "petrol",
            "PHEV-c-d": "diesel",
            "PHEV-c-p": "petrol",
            "ICEV-g": "methane",
            "FCEV": "hydrogen",
        }

        for pt in [
            pwt
            for pwt in [
                "ICEV-p",
                "ICEV-d",
                "HEV-d",
                "HEV-p",
                "PHEV-c-d",
                "PHEV-c-p",
                "ICEV-g",
                "FCEV",
            ]
            if pwt in self.array.coords["powertrain"].values
        ]:
            # calculate the average LHV based on fuel blend
            fuel_type = d_map_fuel[pt]
            primary_name = self.fuel_blend[fuel_type]["primary"]["type"]
            primary_fuel_share = self.fuel_blend[fuel_type]["primary"]["share"]
            primary_fuel_lhv = self.fuel_blend[fuel_type]["primary"].get(
                "lhv", self.bs.fuel_specs[primary_name]["lhv"]
            )
            primary_fuel_density = self.fuel_blend[fuel_type]["primary"].get(
                "density", self.bs.fuel_specs[primary_name]["density"]
            )

            if "secondary" in self.fuel_blend[fuel_type]:
                secondary_name = self.fuel_blend[fuel_type]["secondary"]["type"]
                secondary_fuel_share = self.fuel_blend[fuel_type]["secondary"]["share"]
                secondary_fuel_lhv = self.fuel_blend[fuel_type]["secondary"].get(
                    "lhv", self.bs.fuel_specs[secondary_name]["lhv"]
                )
                secondary_fuel_density = self.fuel_blend[fuel_type]["secondary"].get(
                    "density", self.bs.fuel_specs[secondary_name]["density"]
                )
            else:
                secondary_fuel_share = 0
                secondary_fuel_lhv = 0
                secondary_fuel_density = 0

            self.array.loc[dict(powertrain=pt, parameter="LHV fuel MJ per kg")] = (
                (np.array(primary_fuel_share) * primary_fuel_lhv)
                + (np.array(secondary_fuel_share) * secondary_fuel_lhv)
            ).reshape(1, -1, 1)

            self.array.loc[dict(powertrain=pt, parameter="fuel density per kg")] = (
                (np.array(primary_fuel_share) * primary_fuel_density)
                + (np.array(secondary_fuel_share) * secondary_fuel_density)
            ).reshape(1, -1, 1)

    def set_energy_stored_properties(self) -> None:
        """
        Calculate size and capacity of onboard
        energy storage components.
        :return:
        """

        self.set_average_lhv()
        self["oxidation energy stored"] = (
            self["fuel mass"] * self["LHV fuel MJ per kg"] / 3.6
        )

        self["fuel tank mass"] = (
            self["oxidation energy stored"] * self["fuel tank mass per energy"]
        )

        if "ICEV-g" in self.array.coords["powertrain"].values:
            self["fuel tank mass"] += (
                self["oxidation energy stored"] * self["CNG tank mass slope"]
                + self["CNG tank mass intercept"]
            )

        self["electric energy stored"] = (
            self["battery cell mass"] * self["battery cell energy density"]
        )

    def set_power_battery_properties(self):
        _ = lambda x: np.where(x == 0, 1, x)

        # battery power to start up combustion engine
        # we assume the battery needs to deliver about 3%
        # of the engine rated shaft power to start it
        # for cars, it's more 2-5%, while for trucks, it's 1-3%

        self["battery power"] = 0.03 * self["combustion power"]

        self["battery cell mass"] += (
            self["battery power"]
            / _(self["battery cell power density"])
            * (self["combustion power share"] > 0)
        )

        self["battery BoP mass"] += (
            self["battery cell mass"]
            * (np.array(1) - self["battery cell mass share"])
            * (self["combustion power share"] > 0)
        )

    def set_cargo_mass_and_annual_mileage(self):
        pass

    def set_costs(self) -> None:
        """
        Calculate the different cost types.
        :return:
        """
        self["glider cost"] = (
            self["glider base mass"] * self["glider cost slope"]
            + self["glider cost intercept"]
        )
        self["lightweighting cost"] = (
            self["glider base mass"]
            * self["lightweighting"]
            * self["glider lightweighting cost per kg"]
        )
        self["electric powertrain cost"] = (
            self["electric powertrain cost per kW"] * self["electric power"]
        )
        self["combustion powertrain cost"] = (
            self["combustion power"] * self["combustion powertrain cost per kW"]
        )
        self["fuel cell cost"] = self["fuel cell power"] * self["fuel cell cost per kW"]
        self["power battery cost"] = (
            self["battery power"] * self["power battery cost per kW"]
        )
        self["energy battery cost"] = (
            self["energy battery cost per kWh"] * self["electric energy stored"]
        )
        self["fuel tank cost"] = self["fuel tank cost per kg"] * self["fuel mass"]
        # Per km
        self["energy cost"] = self["energy cost per kWh"] * self["TtW energy"] / 3600

        # For battery, need to divide cost of electricity
        # at battery by efficiency of charging
        # to get costs at the "wall socket".

        _ = lambda x: np.where(x == 0, 1, x)
        self["energy cost"] /= _(self["battery charge efficiency"])

        self["component replacement cost"] = (
            self["energy battery cost"] * self["battery lifetime replacements"]
            + self["fuel cell cost"] * self["fuel cell lifetime replacements"]
        )

        with open(self.DATA_DIR / "purchase_cost_params.yaml", "r") as stream:
            to_markup = yaml.safe_load(stream)["markup"]

        self[to_markup] *= self["markup factor"]

        # calculate costs per km:
        self["lifetime"] = self["lifetime kilometers"] / self["kilometers per year"]

        with open(self.DATA_DIR / "purchase_cost_params.yaml", "r") as stream:
            purchase_cost_params = yaml.safe_load(stream)["purchase"]

        # if purchase cost is zero, we claculate it
        if np.all(self["purchase cost"]) == 0:
            self["purchase cost"] = self[purchase_cost_params].sum(axis=2)

        # per km
        amortisation_factor = self["interest rate"] + (
            self["interest rate"]
            / (
                (np.array(1) + self["interest rate"]) ** self["lifetime kilometers"]
                - np.array(1)
            )
        )
        self["amortised purchase cost"] = (
            self["purchase cost"] * amortisation_factor / self["kilometers per year"]
        )

        # per km
        self["maintenance cost"] = (
            self["maintenance cost per glider cost"]
            * self["glider cost"]
            / self["kilometers per year"]
        )

        # simple assumption that component replacement
        # occurs at half of life.
        self["amortised component replacement cost"] = (
            (
                self["component replacement cost"]
                * (
                    (np.array(1) - self["interest rate"]) ** self["lifetime kilometers"]
                    / 2
                )
            )
            * amortisation_factor
            / self["kilometers per year"]
        )

        self["total cost per km"] = (
            self["energy cost"]
            + self["amortised purchase cost"]
            + self["maintenance cost"]
            + self["amortised component replacement cost"]
        )

    def set_ttw_efficiency(self) -> None:
        """
        Fill in the tank-to-wheel efficiency
        calculated by `calculate_ttw_efficiency`.
        :return:
        """

        distance = self.energy.sel(parameter="velocity").sum(dim="second") / 1000
        self["TtW efficiency"] = (
            self.energy.sel(
                parameter=["motive energy at wheels", "negative motive energy"],
                size=self.array.coords["size"].values,
                powertrain=self.array.coords["powertrain"].values,
            ).sum(dim=["second", "parameter"])
            / distance
        ) / self["TtW energy"]

    def set_hot_emissions(self) -> None:
        """
        Calculate hot pollutant emissions based on ``driving_cycles``.
        The driving_cycles is passed to the :class:`HotEmissionsModel` class
        and :meth:`get_emissions_per_powertrain`
        return emissions per substance per second of driving_cycles.
        Those are summed up and divided by
        the distance driven, to obtain emissions, in kg per km.
        :return: Does not return anything. Modifies ``self.array`` in place.
        """

        hem = HotEmissionsModel(
            velocity=self.energy.sel(parameter="velocity"),
            cycle_name=self.cycle,
            vehicle_type=self.vehicle_type,
            powertrains=self.array.coords["powertrain"].values,
            sizes=self.array.coords["size"].values,
        )

        with open(
            self.DATA_DIR / "emission_factors" / "exhaust_flows.yaml", "r"
        ) as stream:
            list_direct_emissions = sorted(yaml.safe_load(stream))

        list_direct_emissions = [
            e + f", {c}"
            for c in ["urban", "suburban", "rural"]
            for e in list_direct_emissions
        ]

        with open(
            self.DATA_DIR / "emission_factors" / "euro_classes.yaml", "r"
        ) as stream:
            euro_classes = yaml.safe_load(stream)[self.vehicle_type]

        list_years = np.clip(
            self.array.coords["year"].values,
            min(euro_classes.keys()),
            max(euro_classes.keys()),
        )

        list_euro_classes = [euro_classes[y] for y in list(list_years)]

        # to calculate emissions and degradation factors
        # we need the vehicle's lifetime, annual mileage
        # as well as its instant fuel consumption

        # Distribute completed cycle fuel demand over positive fuel-input
        # samples. Regenerative electricity is not negative fuel combustion;
        # its avoided fuel is already accounted for in TtW energy. This also
        # preserves energy overrides and optional combustion-control losses.
        components = ["motive energy", "auxiliary energy"]
        if "combustion control energy" in self.energy.parameter:
            components.append("combustion control energy")
        gross = (
            self.energy.sel(
                parameter=components,
                size=self.array.coords["size"],
                powertrain=self.array.coords["powertrain"],
            )
            .sum("parameter")
            .clip(min=0)
        )
        distance = self.energy.sel(parameter="velocity").sum("second") / 1000
        target = (
            xr.where(self["combustion power share"] > 0, self["TtW energy"], 0)
            * distance
        )
        total = gross.sum("second")
        if bool(((target > 0) & (total <= 0)).any()):
            raise ValueError(
                "Positive combustion energy requires a positive fuel-input trace."
            )
        energy_consumption = (gross * target / xr.where(total > 0, total, 1)).transpose(
            "second", "value", "year", "powertrain", "size"
        )

        hot_emissions = hem.get_hot_emissions(
            euro_class=list_euro_classes,
            lifetime_km=self["lifetime kilometers"],
            energy_consumption=energy_consumption,
            yearly_km=self["kilometers per year"],
        )
        aliases = {
            "Hydrocarbon": "Hydrocarbons",
            "Particulate matters 2.5": "Particulate matters",
            "PAH polycyclic aromatic hydrocarbons": "PAH, polycyclic aromatic hydrocarbons",
            "PAHs": "PAH, polycyclic aromatic hydrocarbons",
        }
        labels = []
        for component in hot_emissions.component.values:
            substance, compartment = component.rsplit(", ", 1)
            labels.append(
                f"{aliases.get(substance, substance)} direct emissions, {compartment}"
            )
        hot_emissions = hot_emissions.assign_coords(component=labels).rename(
            component="parameter"
        )
        self.array.loc[dict(parameter=list_direct_emissions)] = hot_emissions.sel(
            parameter=list_direct_emissions
        )

    def set_particulates_emission(self) -> None:
        """
        Calculate the emission of particulates according to
        https://www.eea.europa.eu/ds_resolveuid/6USNA27I4D

        and further disaggregated in:
        https://doi.org/10.1016/j.atmosenv.2020.117886

        for:

        - brake wear
        - tire wear
        - road wear
        - re-suspended road dust

        by considering:

        - vehicle mass
        - driving situation (urban, rural, motorway)

        into the following fractions:

        - PM 2.5
        - PM 10

        Emissions are subdivided in compartments: urban, suburban and rural.

        """

        list_param = [
            "tire wear emissions",
            "brake wear emissions",
            "road wear emissions",
            "road dust emissions",
        ]

        pem = ParticulatesEmissionsModel(
            velocity=self.energy.sel(parameter="velocity"),
            mass=self["driving mass"],
        )

        self[list_param] = pem.get_abrasion_emissions()

        # brake emissions are discounted by
        # the use of regenerative braking
        self["brake wear emissions"] *= np.array(1) - self["share recuperated energy"]

    def set_noise_emissions(self) -> None:
        """
        Calculate noise emissions based on ``driving_cycles``.
        The driving_cycles is passed to the :class:`NoiseEmissionsModel` class
        and :meth:`get_sound_power_per_compartment`
        returns emissions per compartment type ("rural", "non-urban" and "urban")
        per second of driving_cycles.

        Noise emissions are not differentiated by size classes at the moment,
        but only by powertrain "type"
        (e.g., combustion, hybrid and electric)

        :return: Does not return anything. Modifies ``self.array`` in place.
        """
        velocity = self.energy.sel(parameter="velocity")
        nem = NoiseEmissionsModel(velocity, vehicle_type=self.vehicle_type)

        with open(
            self.DATA_DIR / "emission_factors" / "noise_flows.yaml", "r"
        ) as stream:
            list_noise_emissions = yaml.safe_load(stream)

        self.array.loc[dict(parameter=list_noise_emissions)] = (
            nem.get_sound_power_per_compartment()
        )

    def calculate_cost_impacts(self, sensitivity=False) -> xr.DataArray:
        """
        This method returns an array with cost values per vehicle-km,
        subdivided into the following groups:

            * Purchase
            * Maintenance
            * Component replacement
            * Energy
            * Total cost of ownership

        :return: A xarray array with cost information per vehicle-km
        """

        list_cost_cat = [
            "purchase",
            "maintenance",
            "component replacement",
            "energy",
            "total",
        ]

        response = self.array.sel(
            parameter=[
                "amortised purchase cost",
                "maintenance cost",
                "amortised component replacement cost",
                "energy cost",
                "total cost per km",
            ],
        )

        response.coords["parameter"] = list_cost_cat

        if not sensitivity:
            return response

        return response / response.sel(value="reference")
