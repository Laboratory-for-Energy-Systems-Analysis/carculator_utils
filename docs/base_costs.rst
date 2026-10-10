Shared base cost calculation
============================

This page concerns developers who use the shared base class directly. For a
normal car, truck, bus or two-wheeler calculation, use the cost method in that
vehicle package. Capital recovery converts a purchase price into an annual cost
over the assumed service life; it is not calculated over a number of kilometres.

``VehicleModel.set_costs()`` is available to custom vehicle implementations.
It now uses lifetime kilometres divided by annual kilometres for annual capital
recovery, including zero and near-zero interest. Component replacements retain
the existing mid-life assumption and are discounted by ``(1 + rate)**(-years/2)``.
Zero-mileage/zero-lifetime cells accrue no capital or maintenance allocation.
Nonzero purchase-price inputs are preserved independently for each cell;
zero-price cells use the component sum.

The four vehicle packages override this method and already use year-based
financial calculations. Their default results are not changed by this repair.
``tests/test_base_costs.py`` checks independent discounted cash flows across
rates, lifetimes, named samples and explicit/computed purchase prices.
