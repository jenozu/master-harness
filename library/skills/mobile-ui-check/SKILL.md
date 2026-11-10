---
name: mobile-ui-check
description: Check a UI change works on a phone-sized screen before calling it done - build, lint, and a filled-in manual checklist at 390x844. Use for any task that changes the frontend.
---

# Phone-screen check

<!-- Library skill. BOOTSTRAP adds `paths:` for this project's UI folder and the project's design notes. -->

Automated (run them, report results):
1. The production build passes.
2. Lint is clean for the files you touched.
3. Component tests, if the project has them.

Manual: you can't see a phone. Put this checklist, filled in for the screen you changed, under MANUAL CHECK in
your report (the phase-runner files it under Eyes-on):
- [ ] Chrome DevTools → device toolbar → 390×844. Reload.
- [ ] No horizontal scrolling; nothing hidden under fixed bars, the notch or the home bar.
- [ ] Every button and row is easy to tap (≥ 44 px); inputs don't zoom the page on focus.
- [ ] Numeric inputs open the number keyboard.
- [ ] Loading, empty and error states (stop the backend) all look intentional.
- [ ] <the specific flow this task added, step by step, with the expected result of each step>
- [ ] After deploy: the same flow on a real phone (and in the installed home-screen app, if it's a PWA).

Anything you *can* prove with a running dev server and curl (the API returns the right data, a page renders
server-side) belongs under Agent-checkable, not here.
