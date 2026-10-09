Repeating completed model runs
==============================

The four vehicle models retain a private copy of the inputs used by ``set_all``.
Calling it again rebuilds from those inputs; computed transmission efficiency,
recuperation and sized components do not become new physical assumptions.
PHEV component inputs remain available privately after intermediate output modes
are dropped. Seeded cost factors retain their sample identity.

Selecting or reordering existing years, sizes, powertrains and samples before a
second call is supported. Cells explicitly edited after the previous completion
are carried into the next input array. Edit the inputs of a fresh model when
adding coordinates or changing a PHEV's component assumptions: edits to an
aggregated PHEV output raise a contextual error because they cannot be allocated
unambiguously to its electric and combustion modes. Constructor override
precedence continues to apply. A failed completion restores the previous array.

Before this repair, an unchanged 2025 Medium BEV run changed range from
447.74 to 456.17 km on its second completion; a PHEV-only second run failed after
intermediate modes were removed. Independent new model runs are still the
clearest way to compare scenarios. The regression covers seeded samples,
repeated LCIA, retained selections, explicit glider-input edits and all four
vehicle families. Chemistry-specific prices also select retained sample labels.
