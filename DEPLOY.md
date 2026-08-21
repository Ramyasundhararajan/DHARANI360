# DHARANI 360 — putting it on GitHub and on the web

Everything here is free and open source. No card, no monthly bill.

---

## Part 1 — Push the code to GitHub (private)

The repository has already been created and the first commit made for you.
What is left is the part only you can do, because it needs your GitHub login.

**The easy way — double-click `push-to-github.bat`**

It checks Git is installed, makes the commit, asks for your GitHub username,
and pushes. Run it again any time you want to save new changes.

**Or do it by hand**

1. Open <https://github.com/new>. Name it `dharani360`, choose **Private**, and
   do **not** tick "Add a README", ".gitignore" or "license" — this folder
   already has them.

2. Then, in a Command Prompt opened in this folder:

```
cd "C:\Users\ramya\OneDrive\Desktop\Dharani 360\dharani360-portal"
git gc --prune=now
git commit -m "DHARANI 360 - initial commit"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/dharani360.git
git push -u origin main
```

Windows will pop up a GitHub sign-in box the first time. Sign in there — never
paste a password or token into a chat.

3. From then on:

```
git add -A
git commit -m "what changed"
git push
```

> The repository is already initialised and all 86 files are staged, ready for
> that first commit. The `git gc` line just sweeps up some temporary files left
> behind during setup; it is safe and takes a second.

### What deliberately does NOT go to GitHub

Checked and confirmed excluded by `.gitignore`:

| Excluded | Why |
|---|---|
| `instance/` | The database, every attachment, staff photos, the signing key |
| `supabase_config.json` | The live keys for this installation |
| `.env` | Any secret you add later |
| `dashboard.mp4` | 96 MB — would bloat every clone forever |
| `.venv/`, `__pycache__/` | Rebuilt automatically, never shared |

**Never commit the Supabase `service_role` key.** The app does not need it. Only
the publishable `anon` key belongs in `supabase_config.json`, and even that file
stays out of the repo.

> One note: this folder is inside OneDrive, and OneDrive syncing a `.git` folder
> can occasionally corrupt it. Once GitHub is working, the tidy thing is to move
> the project to something like `C:\Users\ramya\Projects\dharani360` — GitHub
> becomes the backup, so OneDrive is no longer doing that job.

---

## Part 2 — Put it on the web, free

### The recommended way: Cloudflare Tunnel

`cloudflared` is Cloudflare's open-source tunnel client (Apache-2.0). It makes an
outbound connection from the PC running DHARANI 360 to Cloudflare, and Cloudflare
gives you an HTTPS address. Your team opens that address from anywhere.

**Why this suits this app better than any free hosting platform:**

- **£0 / $0, permanently.** No trial credit, no sleeping, no card.
- **No code changes.** Uploads keep writing to disk, exactly as today.
- **Your records never leave the office.** For UAE staff and compliance data
  that is a real advantage, not a technicality.
- **Nothing is opened on your router.** No port forwarding, no fixed IP.
- **It solves the shared-data problem too.** Everyone uses one instance, so
  everyone sees the same records — the thing that was missing before.

The one honest trade-off: **that PC has to be switched on.** If it sleeps, the
address stops answering. Set the machine to never sleep, or use an old spare PC
as the office server.

**Setup, about fifteen minutes**

1. Make a free Cloudflare account and add a domain you own (a `.ae` or any
   cheap domain works). Cloudflare's own DNS is free.
2. Install `cloudflared` on the PC: <https://github.com/cloudflare/cloudflared/releases>
3. In a Command Prompt:

```
cloudflared tunnel login
cloudflared tunnel create dharani360
cloudflared tunnel route dns dharani360 app.yourdomain.ae
```

4. Create `C:\Users\ramya\.cloudflared\config.yml`:

```yaml
tunnel: dharani360
credentials-file: C:\Users\ramya\.cloudflared\<TUNNEL-ID>.json

ingress:
  - hostname: app.yourdomain.ae
    service: http://127.0.0.1:5000
  - service: http_status:404
```

5. Run it as a Windows service so it starts with the machine:

```
cloudflared service install
```

6. Start DHARANI 360 as usual (`start.bat`), and open `https://app.yourdomain.ae`.

**Then add a second lock — do not skip this.** Cloudflare Access is free for up
to 50 users. In the Cloudflare dashboard: *Zero Trust → Access → Applications →
Add an application → Self-hosted*, point it at `app.yourdomain.ae`, and add a
policy allowing only `@dharanis.ae` email addresses. Cloudflare then makes people
prove their email **before the request ever reaches your PC**. Your app's own
sign-in still applies on top.

### If you would rather not use the office PC

The repository ships a `Dockerfile` and `docker-compose.yml`, so the app runs
unchanged on any machine that has Docker:

```
docker compose up -d
python bootstrap.py        # first time only, creates the team
```

That works on a company server, a home mini-PC, or a cheap VPS with
[Coolify](https://coolify.io) (open source, self-hosted, MIT licence) if you ever
want a proper deploy dashboard. All of it is portable — nothing is locked to a
provider.

### Why not Vercel, or Render's free tier

Both throw away the filesystem between requests. This app writes **every**
uploaded file — record attachments, staff photos, file-manager documents — to
disk. On either platform those uploads would silently disappear on the next
restart. Making them work would mean rewriting every upload and download path to
use Supabase Storage first. It is doable, just not free in effort, and it buys
nothing that a tunnel does not already give you.

---

## Part 3 — First run on any new machine

```
python bootstrap.py
```

It creates the tables, creates the five team accounts, links their work emails,
and then **checks that somebody can actually sign in** before it finishes.

This matters: running `setup_signin.py` on its own against a fresh database
disables every account it does not recognise — including the built-in
administrator — and leaves the system with nobody able to get in. `bootstrap.py`
enforces the right order and puts the administrator back if anything goes wrong.

---

## Part 4 — A shareable demo link, free, updated by `git push`

For showing clients without buying a domain and without leaving the office PC
switched on. **Render's free plan**, deployed straight from the GitHub repo.

**One-time setup, about five minutes**

1. Go to <https://render.com> and sign in **with GitHub**.
2. **New → Web Service** → pick the `DHARANI360` repository.
3. Render finds `render.yaml` and fills everything in. Click **Create**.
4. First build takes 3-5 minutes. You get a permanent address:
   `https://dharani360.onrender.com`

**Updating it afterwards is just:**

```
git add -A
git commit -m "what changed"
git push
```

Render notices the push and redeploys on its own. No dashboard, no clicking.

**Signing in to the demo**

The five work-email accounts are created automatically on every boot.
Sign in with any of them, password `Dharani360`.

**Know what you are showing**

| | |
|---|---|
| Address | permanent, and free |
| Data | **wiped on every restart and redeploy** - the free plan has no disk |
| Contents | `start-render.sh` re-seeds on boot: the team, 33 demo records, chat and call history |
| Expiry dates | written relative to today, so the compliance calendar always opens with one overdue, one urgent and several further out |
| Sleeping | after 15 minutes idle; the next visit takes about 50 seconds to wake |

That data reset is a feature for a demo - every client sees the same clean
system - and a reason never to keep real records there. Real records stay on
the office PC behind Cloudflare Tunnel.

**Removing the demo records from a real installation**

They are all tagged `[demo]` in their Notes. Search for `[demo]` and delete,
or just do not run `demo_data.py`.
