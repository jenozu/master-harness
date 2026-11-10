---
paths:
  - "frontend/src/**"
  - "src/**/*.{jsx,tsx,css}"
  - "**/manifest.*"
  - "**/sw.*"
---

# Phone-first / PWA rules

<!-- Library rule. Adjust the paths above to the UI code in this project. -->

- Design at 390 px wide first, then check desktop. No horizontal scrolling.
- Tap targets ≥ 44 px; input font-size ≥ 16 px (stops iOS zooming); numeric inputs use `inputMode="decimal"`.
- Respect safe areas (`env(safe-area-inset-*)`) so nothing hides under the notch or home bar.
- The service worker never caches API responses (network only for `/api/`); cache only the app shell and assets.
- Camera, mic and location: ask only on a user action, stop all media tracks on close/unmount, handle "denied".
- Anything that changes the UI needs the `mobile-ui-check` skill's checklist in the builder's MANUAL CHECK.
