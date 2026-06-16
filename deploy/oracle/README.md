# Deploy on an Oracle Cloud Always-Free VM

Free forever, always-on (no cold starts). The stack is `app + postgres + caddy`
(automatic HTTPS) via [docker-compose.yml](docker-compose.yml).

## What you do (Oracle Console — one time)

1. **Create an Oracle Cloud account** (a credit card is required for identity
   verification; Always-Free resources are not charged).
2. **Launch an instance**: Compute → Instances → Create.
   - Image: **Canonical Ubuntu 22.04**.
   - Shape: **Always Free** — `VM.Standard.A1.Flex` (ARM, up to 4 OCPU / 24 GB)
     or `VM.Standard.E2.1.Micro` (AMD). If ARM shows "out of host capacity",
     retry later or use the AMD micro.
   - Add your SSH **public key** so you (and I) can log in.
3. **Open ports 80 and 443**:
   - VCN → the instance's subnet → Security List → add **Ingress** rules:
     source `0.0.0.0/0`, TCP, dest ports `80` and `443`.
   - (Oracle's default Ubuntu image also has a host firewall — handled in step 4.)
4. Give me the **public IP** and confirm SSH access. From there I run the rest.

## What I run (over SSH — server setup + bring-up)

```bash
# 4. host firewall: allow 80/443 (Oracle Ubuntu uses iptables by default)
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80  -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save

# install Docker + compose plugin
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"   # re-login for group to take effect

# get the code + config
git clone https://github.com/saieeshward/rm-agent.git
cd rm-agent/deploy/oracle
cp .env.example .env
#   edit .env: SITE_ADDRESS=<ip-with-dashes>.nip.io, OPENROUTER_API_KEY,
#   BASIC_AUTH_PASS  (creds are private — never commit them)

# build + start (Caddy fetches a Let's Encrypt cert for SITE_ADDRESS)
docker compose up -d --build
```

## 5. Load the data into the hosted Postgres

The Postgres container starts empty. Load it by piping a dump of the
**already-verified local DB** straight into the VM container (no ETL deps or
scrape cache needed on the VM; the data still originates from the ETL load, so
the `row_hash` matches `etl/LOAD_PROOF.json`):

```bash
# run from your laptop, with the local dev Postgres up (docker compose up -d)
docker compose exec -T postgres \
  pg_dump -U hackathon -d hotel_hackathon --clean --if-exists \
  | ssh ubuntu@<VM_IP> 'docker exec -i rm-postgres psql -U hackathon -d hotel_hackathon'
```

> Alternative (ETL-from-scratch): SSH-tunnel the VM Postgres to your laptop and
> run `DATABASE_URL=... ./scripts/init_db.sh`. Needs the venv + `etl/.cache/` on
> your laptop. The dump/restore above is simpler and yields an identical DB.

## 6. Verify

```bash
curl -s https://<ip-with-dashes>.nip.io/health    # fingerprint fields, no auth
curl -s -u gm:<pass> https://<ip-with-dashes>.nip.io/   # 200, the Revenue Desk
```

`/health`'s `row_hash` must equal the one in `etl/LOAD_PROOF.json`. Then submit
`https://<ip-with-dashes>.nip.io` as the live agent URL.
