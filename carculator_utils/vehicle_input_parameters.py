import json
from copy import deepcopy
from itertools import product
from numbers import Integral, Real
from pathlib import Path

import numpy as np
import stats_arrays as sa
from klausen import NamedParameters

from .battery_costs import remember_samples
from .cost_uncertainty import sample_cost_factors


def load_parameters(obj):
    if isinstance(obj, (str, Path)):
        filepath = Path(obj)
        if not filepath.exists():
            raise FileNotFoundError(f"Can't find this filepath {filepath}.")
        with open(filepath, encoding="utf-8") as file:
            return json.load(file)
    else:
        # Already in correct form, just return
        return obj


def validate_parameters(parameters, *, check_duplicates=False):
    """Validate vehicle parameter records without changing their values.

    :param parameters: Mapping from record identifiers to parameter definitions.
    :param check_duplicates: Reject overlapping name/size/powertrain/year cells.
        Disabled by default to preserve precedence in existing bundled data.
    :raises ValueError: A record is malformed, nonfinite, or has invalid bounds.
    """
    if not isinstance(parameters, dict):
        raise ValueError("Parameters must be a dictionary of parameter records.")

    cells = {}
    for identifier, record in parameters.items():
        context = f"Parameter record {identifier!r}"
        if not isinstance(record, dict):
            raise ValueError(f"{context} must be a dictionary.")
        name = record.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{context}: name must be a nonempty string.")
        context += f" ({name!r})"
        for field in ("sizes", "powertrain"):
            labels = record.get(field)
            if (
                not isinstance(labels, (list, tuple))
                or not labels
                or not all(isinstance(x, str) and x.strip() for x in labels)
            ):
                raise ValueError(f"{context}: {field} must be nonempty string labels.")
            if len(labels) != len(set(labels)):
                raise ValueError(f"{context}: {field} contains duplicate labels.")
        year = record.get("year")
        if isinstance(year, (bool, np.bool_)) or not isinstance(year, Integral):
            raise ValueError(f"{context}: year must be an integer.")
        if "amount" not in record:
            raise ValueError(f"{context}: amount is required.")
        for field in ("amount", "loc", "minimum", "maximum", "scale", "shape"):
            if field not in record:
                continue
            value = record[field]
            if (
                isinstance(value, (bool, np.bool_))
                or not isinstance(value, Real)
                or not np.isfinite(value)
            ):
                raise ValueError(f"{context}: {field} must be a finite number.")
        if record.get("minimum", -np.inf) > record.get("maximum", np.inf):
            raise ValueError(f"{context}: minimum must not exceed maximum.")
        if record.get("uncertainty_type") == sa.TriangularUncertainty.id:
            context += (
                f" (year={year}, sizes={record['sizes']!r}, "
                f"powertrain={record['powertrain']!r})"
            )
            missing = [
                field for field in ("minimum", "loc", "maximum") if field not in record
            ]
            if missing:
                raise ValueError(
                    f"{context}: triangular uncertainty requires {', '.join(missing)}."
                )
            lower, mode, upper = (record[k] for k in ("minimum", "loc", "maximum"))
            if lower == upper:
                raise ValueError(
                    f"{context}: triangular minimum must be less than maximum. "
                    "Use uncertainty_type=1 for a deterministic value."
                )
            if not lower <= mode <= upper:
                raise ValueError(
                    f"{context}: triangular loc (mode) {mode} must lie within "
                    f"minimum {lower} and maximum {upper}."
                )
        if check_duplicates:
            for size, powertrain in product(record["sizes"], record["powertrain"]):
                cell = (name, size, powertrain, year)
                if cell in cells:
                    raise ValueError(
                        f"{context}: duplicate cell {cell!r}, "
                        f"already defined by record {cells[cell]!r}."
                    )
                cells[cell] = identifier


class VehicleInputParameters(NamedParameters):
    """
    A class used to represent vehicles with associated type, size,
    technology, year and parameters.

    This class inherits from NamedParameters, located in the *klausen* package.
    It sources default parameters for all vehicle types from a dictionary in
    default_parameters and format them into an array following the structured described
    in the *klausen* package.

    :ivar sizes: List of string items e.g., ['Large', 'Lower medium', 'Medium', 'Mini', 'SUV', 'Small', 'Van']
    :vartype sizes: list
    :ivar powertrains: List of string items
            e.g., ['BEV', 'FCEV', 'HEV-p', 'ICEV-d', 'ICEV-g', 'ICEV-p', 'PHEV-c', 'PHEV-e']
    :vartype powertrains: list
    :ivar parameters: List of string items e.g., ['Benzene', 'CH4', 'CNG tank mass intercept',...]
    :vartype parameters: list
    :ivar years: List of integers e.g., [2017, 2040]
    :vartype years: list
    :ivar metadata: Dictionary for metadata.
    :vartype metadata: dict
    :ivar values: Dictionary for storing values, of format {'param':[value]}.
    :vartype values: dict
    :ivar iterations: Number of iterations executed
          by the method :func:`~car_input_parameters.CarInputParameters.stochastic`.
          None if :func:`~car_input_parameters.CarInputParameters.static` used instead.
    :vartype iterations: int


    """

    DEFAULT = Path(__file__, "..").resolve() / "data" / "default_parameters.json"
    EXTRA = Path(__file__, "..").resolve() / "data" / "extra_parameters.json"

    def __init__(self, parameters=None, extra=None, limit=None):
        """Create a `klausen <https://github.com/cmutel/klausen>`__ model with the car input parameters."""
        super().__init__(None)

        if parameters is None and not self.DEFAULT.exists():
            raise FileNotFoundError(
                "No default vehicle parameter file is packaged with "
                f"{self.__class__.__name__}. Pass `parameters` explicitly or "
                "override DEFAULT in a downstream input-parameter subclass."
            )

        if extra is None and not self.EXTRA.exists():
            raise FileNotFoundError(
                "No default extra-parameter file is packaged with "
                f"{self.__class__.__name__}. Pass `extra` explicitly or "
                "override EXTRA in a downstream input-parameter subclass."
            )

        parameters = deepcopy(
            load_parameters(self.DEFAULT if parameters is None else parameters)
        )
        extra = load_parameters(self.EXTRA if extra is None else extra)
        if not isinstance(extra, (list, tuple, set)) or not all(
            isinstance(x, str) for x in extra
        ):
            raise ValueError("extra must be a sequence of parameter-name strings.")
        extra = set(extra)

        validate_parameters(parameters)
        self.sizes = sorted(
            {size for o in parameters.values() for size in o.get("sizes", [])}
        )
        self.powertrains = sorted(
            {pt for o in parameters.values() for pt in o.get("powertrain", [])}
        )
        self.parameters = sorted(
            {o["name"] for o in parameters.values()}.union(set(extra))
        )

        # keep a list of input parameters, for sensitivity purpose
        self.input_parameters = sorted({o["name"] for o in parameters.values()})

        self.years = sorted({o["year"] for o in parameters.values()})
        self.add_vehicle_parameters(parameters)

    def static(self):
        """Load static values and retain references for editable battery costs."""
        super().static()
        remember_samples(self)
        self._cost_factors = sample_cost_factors(1, stochastic=False)

    def stochastic(self, iterations=1000, seed=None):
        """Sample with a local RNG; an explicit seed makes runs reproducible.

        Existing ``stochastic(n)`` calls retain their unseeded behavior. Sampling
        never resets or consumes NumPy's process-wide random state.
        Projected-cost factors use independent local streams with the same seed
        and are retained alongside the input samples, including for ``n=1``.

        Records with the same optional ``uncertainty_group`` metadata reuse one
        draw vector. Their sampling distributions must be identical. This
        represents a shared uncertain assumption, for example across years.
        """
        if (
            isinstance(iterations, bool)
            or not isinstance(iterations, (int, np.integer))
            or iterations < 1
        ):
            raise ValueError("iterations must be a positive integer.")
        keys = sorted(
            key
            for key in self.data
            if self.data[key].get("kind") in ("distribution", None)
        )
        groups = {}
        for key in keys:
            group = self.metadata[key].get("uncertainty_group")
            if group is None:
                continue
            if not isinstance(group, str) or not group.strip():
                raise ValueError("uncertainty_group must be a nonempty string.")
            if group in groups and self.data[key] != self.data[groups[group]]:
                raise ValueError(
                    f"Uncertainty group {group!r} requires identical distributions."
                )
            groups.setdefault(group, key)
        parameters = sa.UncertaintyBase.from_dicts(*[self.data[key] for key in keys])
        rng = sa.MCRandomNumberGenerator(parameters, seed=seed)
        samples = rng.generate(iterations)
        self.iterations = int(iterations)
        self.values = {key: row.reshape((-1,)) for key, row in zip(keys, samples)}
        for key in keys:
            group = self.metadata[key].get("uncertainty_group")
            if group is not None:
                self.values[key] = self.values[groups[group]].copy()
        remember_samples(self)
        self._cost_factors = sample_cost_factors(self.iterations, seed=seed)

    def add_vehicle_parameters(self, parameters):
        """
        Split data and metadata according to ``klausen`` convention.

        The parameters are split into the *metadata* and *values* attributes
        of the CarInputParameters class by the add_parameters() method of the parent class.

        :param parameters: A dictionary that contains parameters.
        :type parameters: dict


        """
        KEYS = {"kind", "uncertainty_type", "amount", "loc", "minimum", "maximum"}

        reformatted = {}
        for key, dct in parameters.items():
            reformatted[key] = {k: v for k, v in dct.items() if k in KEYS}
            reformatted[key]["metadata"] = {
                k: v for k, v in dct.items() if k not in KEYS
            }

        self.add_parameters(reformatted)
