# NEXTSPACE working rules

## One consistent workflow for user review and testing

Whenever the user is asked to review or test work, reuse the established preview
setup, update workflow and launch entry point. This applies to every NEXTSPACE
change across all components and features.

- Keep the user's commands, public filenames, installation paths and VM identity
  stable across features and revisions.
- Prepare and verify the latest reviewable result behind those existing entry
  points before telling the user it is ready.
- The agent owns regression testing before handoff. User review is for judging
  the experience, not finding basic functional failures. Verify ordinary first
  clicks, repeated interactions, focus and cancellation in the complete desktop
  at the relevant display densities. Assisted focus and isolated API checks do
  not establish ordinary interaction readiness.
- Before handoff, personally use the packaged preview through its normal
  graphical launcher. Observe the screen after each interaction, including
  clicking the same control while its panel is open, selecting page text,
  scrolling, resizing and zooming. Investigate every visible defect. Scripted
  pass counts and selected screenshots cannot substitute for this exploratory
  review or establish that the whole experience works.
- Run one graphical workload at a time. Wait for its process and cleanup
  receipt before starting another GUI fixture, preview session or build in the
  review VM; do not infer completion from a yielded command.
- Firefox automation fixtures must explicitly disable `focusmanager.testmode`;
  Marionette enables it by default. The final desktop gate must use ordinary
  browsers without automation ports or focus overrides.
- Keep internal build directories, feature names, adapter names and runtime
  hashes out of the user's required handoff steps. A new feature must not
  introduce another download location, extraction directory or launch command.
- Preserve the user's existing installation, VM disk and test state during
  ordinary updates.
- Explain what changed and what to try, using the established workflow. Honor
  requested pauses so the user can review and test before development resumes.

The current operational paths and exact commands are recorded in
`docs/MacBook-Preview.md`. Existing feature wording in an artifact filename is
historical; it does not restrict this project-wide review/testing rule or
justify a new handoff procedure for the next feature.

The user-requested automation wrapper is `Tests/Lima/Review.command`, installed
once at `~/Downloads/Review.command`. The recurring user command is
`bash ~/Downloads/Review.command`. Preserve this entry point for all future
review/test handoffs and refresh the existing archive and SHA-256 sidecar.

Before each handoff, verify that the established delivery artifact contains the
newly qualified result and passes its manifest checks. If an unavoidable
migration requires changing the user-facing workflow, explain why and obtain
the user's agreement first.

## Writing

Do not insert spaces between CJK characters and adjacent English letters or
digits. Check this before sending user-facing text.
