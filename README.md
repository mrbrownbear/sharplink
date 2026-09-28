# SharpLink localized mirror

This repository is generated as a fully localized static mirror of SharpLink and is ready for Vercel static hosting.

The localization workflow downloads the public pages and their runtime assets, rewrites same origin and Storyblok asset URLs to repository local paths, snapshots JSON API responses, and commits the generated site to the repository.

Vercel settings:
* Framework Preset: Other
* Build Command: leave empty
* Output Directory: leave empty
