# Nordic Capital Watch

Automatisk bevakning av kapitalhändelser (funding rounds, IPO, nyemissioner) i Sverige och Norge. Körs varje måndag och torsdag kl 08:00 CET via GitHub Actions och skickar en sammanfattning till Slack.

## Datakällor

| Källa | Land | Typ |
|-------|------|-----|
| MFN Newswire | SE/NO | Formella pressreleaser |
| Breakit | SE | Startup-nyheter |
| Finanstidningen | SE | Finansnyheter |
| Shifter.no | NO | Startup-nyheter |
| Recharge.no | NO | Tech/startup |

## Setup (engångssteg)

### 1. Skapa Slack Incoming Webhook

1. Gå till [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**
2. Välj ett namn (t.ex. "Capital Watch") och din workspace
3. I menyn till vänster: **Incoming Webhooks** → aktivera → **Add New Webhook to Workspace**
4. Välj kanal (t.ex. `#kapital-watch`) → **Allow**
5. Kopiera **Webhook URL** (börjar med `https://hooks.slack.com/services/...`)

### 2. Skapa GitHub-repo

```bash
cd ~/nordic-capital-watch
git init
git add .
git commit -m "Initial commit"
gh repo create nordic-capital-watch --public --source=. --push
```

### 3. Lägg till repository secret

```bash
gh secret set SLACK_WEBHOOK_URL --body "https://hooks.slack.com/services/XXX/YYY/ZZZ"
```

Eller via GitHub-webben: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
- Name: `SLACK_WEBHOOK_URL`
- Secret: din webhook-URL

### 4. Verifiera

**Lokalt:**
```bash
pip install -r requirements.txt
SLACK_WEBHOOK_URL="https://hooks.slack.com/..." python collector.py
```

**GitHub Actions (manuellt):**
GitHub → repo → **Actions** → **Nordic Capital Watch** → **Run workflow**

## Lägga till nya datakällor

Lägg till en dict i `FEEDS`-listan i `collector.py`:

```python
{"url": "https://ny-kalla.se/rss", "country": "SE", "source": "NyKälla"},
```

## Justera nyckelord

Redigera `KEYWORDS`-listan i `collector.py`. Alla jämförelser är case-insensitive.

## Schema

| Körning | Cron | Täcker |
|---------|------|--------|
| Måndag 08:00 CET | `0 7 * * 1` | Tors–Sön |
| Torsdag 08:00 CET | `0 7 * * 4` | Sön–Ons |

`LOOKBACK_DAYS = 4` säkerställer att inget mellanrum uppstår mellan körningarna.
