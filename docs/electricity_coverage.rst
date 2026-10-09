Electricity geographic coverage
===============================

This table describes the bundled 9 October 2026 snapshot, derived from
``electricity_history.csv`` and ``electricity_geographies.csv``. See
:doc:`electricity_scenarios` for source attribution, exclusions, technology
mappings and the interpretation of the future scenarios.

All 209 countries/economies listed below have their own Ember historical
generation records. GECO supplies country projections for 27 of them; 180 use
regional proxies and two use the World proxy. World (``GLO``), Europe
(``RER``) and the European Union (``EU27``) are three additional aggregate
histories, giving 212 geographic codes.
Territories and economies follow the source dataset's geographic labels.

Historical dates are the first and latest retained source observations; the
record count excludes any missing or rejected country-years. The annual array's
interpolation and endpoint holds do not create additional observations.
Coverage varies by country and recent values can include source estimates.

All three GECO scenarios provide endpoints in 2030, 2035, 2040, 2050, 2060 and
2070. A regional proxy replaces national shares at those endpoints; it is not
a national forecast. For example, all EU member states use the EU27 mix from
2030. The China model region includes Hong Kong and Macau. Geographic
assignments follow the published GECO crosswalk and the extensions documented
in the source manifest, including its non-geographic assignments of Seychelles
to Rest of South Asia and Sao Tome and Principe to Rest of Central America.

TYNDP option: national EU27 projections
---------------------------------------

``tyndp-2026-ntplus`` adds national projections for Austria (AT), Belgium (BE),
Bulgaria (BG), Croatia (HR), Cyprus (CY), Czechia (CZ), Denmark (DK), Estonia
(EE), Finland (FI), France (FR), Germany (DE), Greece (GR), Hungary (HU),
Ireland (IE), Italy (IT), Latvia (LV), Lithuania (LT), Luxembourg (LU), Malta
(MT), Netherlands (NL), Poland (PL), Portugal (PT), Romania (RO), Slovakia
(SK), Slovenia (SI), Spain (ES) and Sweden (SE).

These 27 countries use their own NT+ endpoints in 2030, 2035, 2040 and 2050,
holding 2050 thereafter. Their historical coverage is unchanged and is listed
in the European Union table below. The remaining countries retain the GECO
assignments below. Thus this option provides 54 country projections, 153
regional proxies and two World proxies, plus the three aggregate geographies.
The table below describes the GECO scenarios; its EU grouping is replaced only
when the TYNDP option is selected. See :doc:`electricity_scenarios` for the
draft scenario's assumptions and the hydrogen-power LCI proxies.

Select ``country="EU27"`` on any vehicle model to use the EU27 as a whole.
It has its own Ember history from 2000 to 2025. Its future uses the published,
generation-weighted TYNDP EU27 aggregate in the TYNDP scenario, or GECO's
European Union aggregate in each GECO scenario. ``RER`` remains a separate
Europe selection. Grid losses for EU27 use a disclosed RER proxy.

GECO country projections (27)
------------------------------

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records", "Projection region"
   :widths: 7, 26, 10, 10, 9, 28

   "AR","Argentina","1985","2025","41","Argentina"
   "AU","Australia","1985","2025","41","Australia"
   "BR","Brazil","1985","2025","41","Brazil"
   "CA","Canada","1985","2025","41","Canada"
   "CL","Chile","2000","2025","26","Chile"
   "CN","China","1985","2025","41","China"
   "EG","Egypt","1985","2025","41","Egypt"
   "IS","Iceland","2000","2025","26","Iceland"
   "IN","India","1985","2025","41","India"
   "ID","Indonesia","2000","2025","26","Indonesia"
   "IR","Iran","1985","2025","41","Iran"
   "JP","Japan","1985","2025","41","Japan"
   "MY","Malaysia","1985","2025","41","Malaysia"
   "MX","Mexico","1985","2025","41","Mexico"
   "NZ","New Zealand","2000","2025","26","New Zealand"
   "NO","Norway","1990","2025","36","Norway"
   "RU","Russia","1985","2025","41","Russian Federation"
   "SA","Saudi Arabia","1985","2025","41","Saudi Arabia"
   "ZA","South Africa","2000","2025","26","South Africa"
   "KR","South Korea","1985","2025","41","South Korea"
   "CH","Switzerland","2000","2025","26","Switzerland"
   "TH","Thailand","1985","2025","41","Thailand"
   "TR","Türkiye","1990","2025","36","Türkiye"
   "UA","Ukraine","1985","2022","38","Ukraine"
   "GB","United Kingdom","1985","2025","41","United Kingdom"
   "US","United States","2000","2025","26","United States"
   "VN","Viet Nam","1985","2025","41","Vietnam"

Regional projections (180)
--------------------------

Algeria and Libya (2)
~~~~~~~~~~~~~~~~~~~~~

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records"
   :widths: 9, 43, 16, 16, 16

   "DZ","Algeria","2000","2024","25"
   "LY","Libya","2000","2024","25"

China (2)
~~~~~~~~~

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records"
   :widths: 9, 43, 16, 16, 16

   "HK","Hong Kong (SAR of China)","2000","2024","25"
   "MO","Macao (SAR of China)","2000","2024","25"

European Union (27)
~~~~~~~~~~~~~~~~~~~

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records"
   :widths: 9, 43, 16, 16, 16

   "AT","Austria","1990","2025","36"
   "BE","Belgium","1990","2025","36"
   "BG","Bulgaria","1990","2025","36"
   "HR","Croatia","1990","2024","35"
   "CY","Cyprus","1990","2025","36"
   "CZ","Czechia","1990","2024","35"
   "DK","Denmark","1990","2025","36"
   "EE","Estonia","1990","2024","35"
   "FI","Finland","1990","2025","36"
   "FR","France","1990","2025","36"
   "DE","Germany","1985","2025","41"
   "GR","Greece","1990","2025","36"
   "HU","Hungary","1990","2025","36"
   "IE","Ireland","1990","2025","36"
   "IT","Italy","1990","2025","36"
   "LV","Latvia","1990","2025","36"
   "LT","Lithuania","1990","2025","36"
   "LU","Luxembourg","1990","2025","36"
   "MT","Malta","1990","2025","36"
   "NL","Netherlands","1990","2024","35"
   "PL","Poland","1990","2025","36"
   "PT","Portugal","1990","2025","36"
   "RO","Romania","1990","2025","36"
   "SK","Slovakia","1990","2025","36"
   "SI","Slovenia","1990","2024","35"
   "ES","Spain","1990","2024","35"
   "SE","Sweden","1990","2025","36"

Mediterranean Middle-East (5)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records"
   :widths: 9, 43, 16, 16, 16

   "IL","Israel","2000","2025","26"
   "JO","Jordan","2000","2024","25"
   "LB","Lebanon","2000","2024","25"
   "PS","Palestine (State of)","2000","2024","25"
   "SY","Syria","2000","2024","25"

Morocco and Tunisia (2)
~~~~~~~~~~~~~~~~~~~~~~~

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records"
   :widths: 9, 43, 16, 16, 16

   "MA","Morocco","2000","2025","26"
   "TN","Tunisia","2000","2025","26"

Rest of Balkans (7)
~~~~~~~~~~~~~~~~~~~

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records"
   :widths: 9, 43, 16, 16, 16

   "AL","Albania","2000","2024","25"
   "BA","Bosnia Herzegovina","2000","2025","26"
   "XK","Kosovo","2000","2025","26"
   "MD","Moldova","2000","2025","26"
   "ME","Montenegro","2005","2025","21"
   "MK","North Macedonia","1990","2025","36"
   "RS","Serbia","1990","2025","36"

Rest of CIS (9)
~~~~~~~~~~~~~~~

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records"
   :widths: 9, 43, 16, 16, 16

   "AM","Armenia","2000","2025","26"
   "AZ","Azerbaijan","2000","2024","25"
   "BY","Belarus","2000","2025","26"
   "GE","Georgia","2000","2025","26"
   "KZ","Kazakhstan","1985","2025","41"
   "KG","Kyrgyzstan","2000","2024","25"
   "TJ","Tajikistan","2000","2025","26"
   "TM","Turkmenistan","2000","2024","25"
   "UZ","Uzbekistan","2000","2025","26"

Rest of Central America (31)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records"
   :widths: 9, 43, 16, 16, 16

   "AG","Antigua and Barbuda","2000","2024","25"
   "AW","Aruba","2000","2024","25"
   "BS","Bahamas","2000","2024","25"
   "BB","Barbados","2000","2024","25"
   "BZ","Belize","2000","2024","25"
   "KY","Cayman Islands","2000","2024","25"
   "CR","Costa Rica","2000","2024","25"
   "CU","Cuba","2000","2024","25"
   "DM","Dominica","2000","2023","24"
   "DO","Dominican Republic","2000","2025","26"
   "SV","El Salvador","2000","2025","26"
   "GD","Grenada","2000","2024","25"
   "GP","Guadeloupe","2000","2023","24"
   "GT","Guatemala","2000","2024","25"
   "HT","Haiti","2000","2024","25"
   "HN","Honduras","2000","2024","25"
   "JM","Jamaica","2000","2024","25"
   "MQ","Martinique","2000","2023","24"
   "MS","Montserrat","2000","2024","25"
   "NI","Nicaragua","2000","2024","25"
   "PA","Panama","2000","2024","25"
   "PR","Puerto Rico","2000","2025","26"
   "KN","Saint Kitts and Nevis","2000","2024","25"
   "LC","Saint Lucia","2000","2024","25"
   "PM","Saint Pierre and Miquelon","2000","2023","24"
   "VC","Saint Vincent and the Grenadines","2000","2024","25"
   "ST","Sao Tome and Principe","2000","2023","24"
   "TT","Trinidad and Tobago","2000","2024","25"
   "TC","Turks and Caicos Islands","2000","2024","25"
   "VG","Virgin Islands (British)","2000","2023","24"
   "VI","Virgin Islands (U.S.)","2000","2023","24"

Rest of Pacific (13)
~~~~~~~~~~~~~~~~~~~~

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records"
   :widths: 9, 43, 16, 16, 16

   "AS","American Samoa","2000","2024","25"
   "CK","Cook Islands (the)","2000","2024","25"
   "FJ","Fiji","2000","2024","25"
   "PF","French Polynesia","2000","2024","25"
   "GU","Guam","2000","2024","25"
   "KI","Kiribati","2000","2024","25"
   "NR","Nauru","2000","2024","25"
   "NC","New Caledonia","2000","2024","25"
   "PG","Papua New Guinea","2000","2024","25"
   "WS","Samoa","2000","2024","25"
   "SB","Solomon Islands","2000","2024","25"
   "TO","Tonga","2000","2024","25"
   "VU","Vanuatu","2000","2023","24"

Rest of Persian Gulf (7)
~~~~~~~~~~~~~~~~~~~~~~~~

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records"
   :widths: 9, 43, 16, 16, 16

   "BH","Bahrain","2000","2024","25"
   "IQ","Iraq","2000","2024","25"
   "KW","Kuwait","2000","2025","26"
   "OM","Oman","2000","2025","26"
   "QA","Qatar","2000","2025","26"
   "AE","United Arab Emirates","1985","2025","41"
   "YE","Yemen","2000","2024","25"

Rest of South America (11)
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records"
   :widths: 9, 43, 16, 16, 16

   "BO","Bolivia","2000","2025","26"
   "CO","Colombia","2000","2025","26"
   "EC","Ecuador","2000","2025","26"
   "FK","Falkland Islands (Malvinas)","2000","2023","24"
   "GF","French Guiana","2000","2023","24"
   "GY","Guyana","2000","2024","25"
   "PY","Paraguay","2000","2025","26"
   "PE","Peru","2000","2025","26"
   "SR","Suriname","2000","2024","25"
   "UY","Uruguay","2000","2025","26"
   "VE","Venezuela","2000","2024","25"

Rest of South Asia (8)
~~~~~~~~~~~~~~~~~~~~~~

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records"
   :widths: 9, 43, 16, 16, 16

   "AF","Afghanistan","2000","2024","25"
   "BD","Bangladesh","2000","2024","25"
   "BT","Bhutan","2000","2024","25"
   "MV","Maldives","2000","2024","25"
   "NP","Nepal","2000","2024","25"
   "PK","Pakistan","2000","2025","26"
   "SC","Seychelles","2000","2024","25"
   "LK","Sri Lanka","2000","2025","26"

Rest of South-East Asia (9)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records"
   :widths: 9, 43, 16, 16, 16

   "BN","Brunei Darussalam","2000","2024","25"
   "KH","Cambodia","2000","2025","26"
   "LA","Lao PDR","2000","2024","25"
   "MN","Mongolia","2000","2025","26"
   "MM","Myanmar","2000","2024","25"
   "KP","North Korea","2000","2024","25"
   "SG","Singapore","2000","2025","26"
   "TW","Taiwan (China)","1985","2025","41"
   "PH","The Philippines","2000","2025","26"

Rest of Sub-Saharan Africa (47)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records"
   :widths: 9, 43, 16, 16, 16

   "AO","Angola","2000","2024","25"
   "BJ","Benin","2000","2024","25"
   "BW","Botswana","2000","2024","25"
   "BF","Burkina Faso","2000","2024","25"
   "BI","Burundi","2000","2024","25"
   "CV","Cabo Verde","2000","2024","25"
   "CM","Cameroon","2000","2024","25"
   "CF","Central African Republic","2000","2023","24"
   "TD","Chad","2000","2024","25"
   "KM","Comoros","2000","2023","24"
   "CG","Congo","2000","2024","25"
   "CD","Congo (DRC)","2000","2024","25"
   "CI","Cote d'Ivoire","2000","2024","25"
   "DJ","Djibouti","2000","2024","25"
   "GQ","Equatorial Guinea","2000","2024","25"
   "ER","Eritrea","2000","2024","25"
   "SZ","Eswatini","2000","2024","25"
   "ET","Ethiopia","2000","2025","26"
   "GA","Gabon","2000","2024","25"
   "GM","Gambia","2000","2024","25"
   "GH","Ghana","2000","2024","25"
   "GN","Guinea","2000","2024","25"
   "GW","Guinea-Bissau","2000","2024","25"
   "KE","Kenya","2000","2025","26"
   "LS","Lesotho","2000","2022","23"
   "LR","Liberia","2000","2024","25"
   "MG","Madagascar","2000","2024","25"
   "MW","Malawi","2000","2024","25"
   "ML","Mali","2000","2024","25"
   "MR","Mauritania","2000","2024","25"
   "MU","Mauritius","2000","2024","25"
   "MZ","Mozambique","2000","2024","25"
   "NA","Namibia","2000","2024","25"
   "NE","Niger","2000","2024","25"
   "NG","Nigeria","2000","2025","26"
   "RE","Reunion","2000","2023","24"
   "RW","Rwanda","2000","2024","25"
   "SN","Senegal","2000","2024","25"
   "SL","Sierra Leone","2000","2024","25"
   "SO","Somalia","2000","2024","25"
   "SS","South Sudan","2012","2024","13"
   "SD","Sudan","2000","2024","25"
   "TZ","Tanzania (the United Republic of)","2000","2024","25"
   "TG","Togo","2000","2024","25"
   "UG","Uganda","2000","2024","25"
   "ZM","Zambia","2000","2024","25"
   "ZW","Zimbabwe","2000","2024","25"

World projection fallback (2)
-----------------------------

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records", "Projection region"
   :widths: 7, 26, 10, 10, 9, 28

   "FO","Faroe Islands","2000","2023","24","World"
   "GL","Greenland","2000","2024","25","World"

Additional aggregates (3)
-------------------------

Europe history is the Ember Europe aggregate; its EU27 projection is a
regional proxy with a different geographic boundary. World uses the World
projection. EU27 has matching EU history and projections; the GECO assignment
below is replaced by TYNDP's EU27 aggregate when that scenario is selected.

.. csv-table::
   :header: "Code", "Country/economy", "First year", "Latest year", "Records", "Projection region"
   :widths: 7, 26, 10, 10, 9, 28

   "RER","Europe","2000","2025","26","European Union"
   "EU27","European Union","2000","2025","26","European Union"
   "GLO","World","2000","2025","26","World"
