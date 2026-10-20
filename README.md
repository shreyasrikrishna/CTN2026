# CTN 2026 team bot

## Local setup (VS Code + Claude Code)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # paste team code, set SIDE from your team page
cp accounts.example.json accounts.json   # edit usernames/passwords/personas
python bot.py                   # DRY_RUN=1 prints posts without sending
```
Set `DRY_RUN=0` once the output looks right.

## Run 24/7 on a cloud VM
1. Create a small Ubuntu VM (AWS Lightsail, DigitalOcean, Oracle free tier). Sydney region.
2. `git clone` this repo (private repo!), make the venv, copy in `.env` and `accounts.json`.
3. `sudo cp deploy/ctn-bot.service /etc/systemd/system/ && sudo systemctl enable --now ctn-bot`
4. Logs: `journalctl -u ctn-bot -f`

Only ONE copy may run per team. Limits are shared across the team.
Never commit `.env`, `accounts.json` or the team code.
