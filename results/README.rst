Retained vehicle campaign evidence
===================================

The fixing campaign closed on 14 October 2026. The current conclusions and
accepted limitations are in ``../docs/premise_vehicle_update.rst``. Dated reports
describe the state at their own step; references there to unfinished work may
have been superseded or explicitly left outside the closed campaign.

Retention policy
------------------

* ``premise_car_fcev_buffer_20261014/`` retains the final 2020/2050 build records,
  model/accounting checks, saved-metadata checks and 224 incremental EF 3.1 pairs.
* ``premise_fcev_buffer_20261014/`` retains the final truck-buffer evidence and
  its 192 incremental EF 3.1 pairs.
* The car/truck buffer audits and car PHEV calibration audit retain source
  references, paired physical specifications and the reviewed proxy decisions.
* ``premise_vehicle_audit_20261012/candidate_recipes.csv`` remains a generator
  input. ``decisions.json`` records closure and its implemented scope.
* ``premise_original_vehicle_iam_20261013/`` retains original-IAM evidence.
* Earlier tracked narrative reports remain as historical scientific records.
  Superseded raw tables, build/validation snapshots and one-off diagnostic
  scripts were removed from the working tree; retrieve tracked versions from
  pre-cleanup Git revision ``862bc96`` when reconstructing those historical runs.

Untracked campaign intermediates were removed after a local compressed recovery
snapshot outside the repositories. They are not required by the maintained
generators. The closeout verification records the removal counts and confirms
that all three installed workbooks retain exactly the same identities and
exchange coefficients after switching to the pinned baseline reader.

The full original-legacy-versus-final catalogue comparison was not completed.
The retained incremental comparisons must not be described as that comparison.
Private ecoinvent/Brightway databases are not included in repository artifacts.
Earlier release/background diagnostics outside this campaign are unchanged.
