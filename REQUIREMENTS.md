# Requirement Export

Create a web page that introduces the mini-keyboard tool and provides a clear
usage guide.

## Source references

- Refer to the existing sibling projects for page and deployment style.
- Refer to `web2local` only for the local-script launching approach.

## Page content

- Briefly introduce what mini-keyboard does.
- Show the macro pad layout and mode mappings.
- Provide setup guidance without duplicated command blocks.
- Provide two usage paths:
  - Manual terminal setup.
  - Web2local-assisted actions from the website.
- For web2local, include only a short introduction and a link to the project.
  Do not explain web2local in depth on this page.

## Manual path

- Show the exact terminal flow once:
  - clone the repository
  - install keyd
  - run `./install.sh`
  - run `hud/install-hud.sh`

## Web2local path

- Use web2local to run supported local helper actions from the website.
- Keep actions narrow and named rather than accepting arbitrary shell input.
- Suggested actions:
  - check daemon status
  - request page access
  - show mini-keyboard repo/keyd/HUD status
  - validate scripts
  - show recent keyd logs
  - install or uninstall HUD
- Include a link to `https://github.com/LueApp/web2local-bridge`.

## Deployment

- Push the project to GitHub.
- Configure Cloudflare deployment from the dashboard.
