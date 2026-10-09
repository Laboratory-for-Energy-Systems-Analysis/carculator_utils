Fuel catalogue and supplier identity
====================================

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

Supported and unavailable choices
---------------------------------

``background_systems.get_default_fuels()`` lists supported choices per category.
Each advertised option has physical properties and either an exact bundled
supplier or a documented foreground delivery recipe with resolvable dependencies.
Both default roles belong to that supported list.

``background_systems.get_unavailable_fuels()`` lists excluded labels and reasons.
These include biogas steam reforming, coal-gasification hydrogen, electrochemical
methane, cement/MSWI biological methane and the ambiguous petrol electrolysis
aliases. Selecting one now raises a contextual ``ValueError`` during model
construction, before an expensive completed run. No replacement pathway is
silently substituted. The explicit cement petrol options remain supported.

This road-vehicle catalogue does not advertise aviation kerosene options.
Specifications retained for legacy reference are not evidence of inventory
support. Custom supplier-name overrides must still resolve at inventory creation.
