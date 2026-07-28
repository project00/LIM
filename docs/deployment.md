# Production Deployment Guide — Nginx Reverse Proxy & TLS Termination

This document details the configuration and manual steps required to deploy the LIM-AI Copilot Remote Server securely in production with Nginx and SSL/TLS termination.

---

## Architecture

The remote FastAPI server runs in a secure, isolated container. To ensure maximum transport security and prevent exposing any unencrypted endpoints, its internal application port `8000` is **not** exposed to the public Internet. Instead, an Nginx container terminates SSL/TLS traffic on port `443` (redirecting plain HTTP traffic on port `80` to HTTPS) and proxies requests to the FastAPI backend over the internal Docker network.

```
[Client (Widget / Daemon)] ---> HTTPS (Port 443) ---> [Nginx Proxy (TLS Termination)] ---> HTTP (Port 8000) ---> [FastAPI Server]
```

---

## Prerequisite: Manual TLS Certificate Acquisition

**IMPORTANT:** Before deploying the Docker Compose services, you must obtain real, valid SSL/TLS certificates for your school's actual domain name (e.g., `lim.your-school.it`).

**This step cannot be automated by Jules (the AI assistant) or any pre-packaged script because it requires a real, registered domain name that you own and have DNS control over.**

### Recommended: Certbot & Let's Encrypt

To obtain a free, trusted TLS certificate using Let's Encrypt, follow these manual steps on your production host machine:

1. **Install Certbot:**
   On Ubuntu/Debian:
   ```bash
   sudo apt-get update
   sudo apt-get install -y certbot
   ```

2. **Generate the Certificates:**
   Run Certbot in standalone mode. Note that port 80 on your host must be temporarily free and accessible from the Internet for the challenge to succeed:
   ```bash
   sudo certbot certonly --standalone -d lim.your-school.it
   ```

3. **Locate and Copy the Certificate Files:**
   Certbot will save the certificate files under `/etc/letsencrypt/live/lim.your-school.it/`.
   - `fullchain.pem` (The certificate chain)
   - `privkey.pem` (The private key)

4. **Install the Certificates into Nginx Volumes:**
   Copy or symlink these files into the `./nginx/certs/` directory of this repository:
   ```bash
   mkdir -p ./nginx/certs
   sudo cp /etc/letsencrypt/live/lim.your-school.it/fullchain.pem ./nginx/certs/fullchain.pem
   sudo cp /etc/letsencrypt/live/lim.your-school.it/privkey.pem ./nginx/certs/privkey.pem
   sudo chown -R $USER:$USER ./nginx/certs
   ```

---

## Configuration Files

### 1. `nginx/nginx.conf`
The Nginx configuration file is mounted read-only at `/etc/nginx/nginx.conf` and handles:
- Listening on port `80` and returning a `301` redirect to the secure HTTPS endpoint.
- Listening on port `443` with standard SSL configuration.
- Routing all traffic to the `mock-server` FastAPI container on port `8000` while setting essential proxy headers (`Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`).
- WebSocket proxy support to enable smooth full-duplex communications.

### 2. `docker-compose.yml`
The compose file configures two services:
- **`mock-server`**: Runs the FastAPI app backend (no raw ports exposed).
- **`nginx`**: Uses `nginx:alpine`, binds ports `80` and `443`, and mounts the config template and the `certs/` folder read-only.

---

## Starting the Server

Once your certificates are placed inside `./nginx/certs/`, deploy the production stack by running:

```bash
docker compose up -d
```

Nginx will start, load your certificates, bind to ports `80` and `443`, and secure all communications to the LIM-AI Copilot Remote Server.
