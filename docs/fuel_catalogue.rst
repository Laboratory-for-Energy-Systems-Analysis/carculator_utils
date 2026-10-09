Fuel catalogue and supplier identity
===================================

Synthetic methanol diesel distinguishes direct air capture (the historical
``electrolysis`` label) from cement-plant CO2 (``cement``). Economic and energy
allocation select different supplier datasets. The swapped diesel carbon-source
mappings and the petrol energy/economic allocation mismatch were corrected in
the unreleased version. Regenerate inventories using affected fuels.

For petrol, both historical ``electrolysis`` aliases have pointed to cement CO2;
the bundled index contains no corresponding direct-air-capture gasoline supplier.
Use the explicit ``cement`` option when that is the intended carbon source.
Supplier identity checks establish consistency with the bundled index, not
independent validation of the underlying synthesis inventories or capture credits.
