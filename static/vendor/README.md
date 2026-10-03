# Locally bundled chart dependencies

- `plotly.min.js`: Plotly.js 3.7.0, copied from the installed Plotly Python
  package using `plotly.offline.get_plotlyjs()`. The bundle includes its MIT
  license notice and third-party notices.
- `usa_110m.json`: US map topology downloaded from
  https://cdn.plot.ly/usa_110m.json on 2026-09-20.

These files are served by Flask so saved demo charts do not depend on a live
chart CDN. `public-data.js` sets Plotly's `topojsonURL` to this directory.
