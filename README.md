# IP Inventory Management System

A web application for managing VLANs and the IP addresses inside them. An Admin enters a network and CIDR, and the system calculates the range and automatically creates every usable IP record. Users then assign IPs to equipment, and every change is written to an audit log.

Built to replace spreadsheet-based IP tracking: no duplicate IPs, no overlapping networks, and a clear record of who changed what.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688)
![React](https://img.shields.io/badge/React-frontend-61dafb)
![MySQL](https://img.shields.io/badge/MySQL-8.0.16%2B-4479a1)

## Features

- **Automatic IP generation.** Enter `10.10.20.0/24`, preview the range, confirm, and all usable IP records are created.
- **Duplicate and overlap protection.** Rejects an existing network, a subnet inside an existing network, and a network that swallows an existing one.
- **Strict validation.** Network addresses must be aligned to the CIDR, and the gateway and reserved IPs must fall inside the range. CIDR `/16` to `/30` is supported.
- **IP assignment.** Assign an IP with room, department, equipment ID and name, CPU S/N, instrument S/N, user name and remarks. Edit, set inactive, reactivate or release it later.
- **Race-free.** If two users pick the same IP at the same moment, only one succeeds.
- **Roles.** Admin (full control) and Normal User (view and assign IPs).
- **User management.** Admins add users, deactivate them, change roles and reset passwords. Users can change their own password.
- **Audit log.** Who did what, when, with old and new values. Passwords are never logged.
- **Dashboard.** Utilization per VLAN with totals for assigned, available, reserved and inactive IPs.
- **CSV export** of the filtered IP list (opens in Excel).
- **Single-server hosting.** One Uvicorn process serves both the API and the built React app, and runs as a Windows service.

## Demo and screenshots

### Demo video

<!-- Option 1: on github.com, edit this file and drag your .mp4 here; GitHub inserts the player link automatically. -->
<!-- Option 2: YouTube link with a thumbnail:
[![Demo video](docs/images/demo-thumbnail.png)](https://www.youtube.com/watch?v=YOUR_VIDEO_ID)
-->

> Demo video coming soon.

### Screenshots

All screenshots use sample data only.

| | |
|---|---|
| ![Screenshot 1](Screenshot%202026-10-05%20124242.png) | ![Screenshot 2](Screenshot%202026-10-05%20124438.png) |
| ![Screenshot 3](Screenshot%202026-10-05%20124451.png) | ![Screenshot 4](Screenshot%202026-10-05%20124747.png) |
| ![Screenshot 5](Screenshot%202026-10-05%20124801.png) | ![Screenshot 6](Screenshot%202026-10-05%20124821.png) |
| ![Screenshot 7](Screenshot%202026-10-05%20124835.png) | ![Screenshot 8](Screenshot%202026-10-05%20124847.png) |
| ![Screenshot 9](Screenshot%202026-10-05%20124859.png) | ![Screenshot 10](Screenshot%202026-10-05%20124907.png) |
| ![Screenshot 11](Screenshot%202026-10-05%20125118.png) | ![Screenshot 12](Screenshot%202026-10-05%20125132.png) |
| ![Screenshot 13](Screenshot%202026-10-05%20125206.png) | ![Screenshot 14](Screenshot%202026-10-05%20125217.png) |
| ![Screenshot 15](Screenshot%202026-10-05%20125232.png) | ![Screenshot 16](Screenshot%202026-10-05%20125457.png) |
| ![Screenshot 17](Screenshot%202026-10-05%20125506.png) | ![Screenshot 18](Screenshot%202026-10-05%20125612.png) |
| ![Screenshot 19](Screenshot%202026-10-05%20125653.png) | ![Screenshot 20](Screenshot%202026-10-05%20125707.png) |
| ![Screenshot 21](Screenshot%202026-10-05%20125717.png) |   |

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy, PyMySQL |
| Auth | JWT (PyJWT), bcrypt password hashing |
| Frontend | React, Vite |
| Database | MySQL 8.0.16+ (InnoDB) |
| Hosting | Uvicorn, NSSM (Windows service) |

## Project structure

```text
.
├── backend/
│   ├── app/                 FastAPI application (auth, users, vlans, ips, edit, audit, dashboard, ipcalc)
│   ├── requirements.txt
│   ├── set_password.py      Set or reset a user's password
│   └── backup.bat           Database backup script (Windows)
├── frontend/
│   ├── src/                 React app (App.jsx, main.jsx, styles.css)
│   ├── public/              Static files (optional logo: amn_logo.png)
│   └── package.json
├── database/
│   └── setup_database.sql   Complete database schema
└── docs/
    └── IP_Inventory_Setup_Guide.md   Full setup and operations guide
```

## Quick start (Windows)

Requirements: Python 3.10+, MySQL 8.0.16+, Node.js 18+.

**1. Create the database**

```bat
mysql -u root -p < database\setup_database.sql
```

**2. Install the backend**

```bat
python -m venv venv
venv\Scripts\activate
pip install -r backend\requirements.txt
```

**3. Configure and run the backend**

The app reads two environment variables:

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | `mysql+pymysql://USER:PASSWORD@localhost:3306/ip_inventory` (URL-encode special characters, e.g. `@` becomes `%40`) |
| `JWT_SECRET` | A long random string (32+ characters) used to sign login tokens |

Generate a secret:

```bat
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Then, in the same window:

```bat
cd backend
set DATABASE_URL=mysql+pymysql://USER:PASSWORD@localhost:3306/ip_inventory
set JWT_SECRET=YOUR_LONG_RANDOM_SECRET
python set_password.py admin YourAdminPassword
python -m uvicorn app.main:app
```

**4. Build the frontend**

```bat
cd frontend
npm install
npm run build
```

Open `http://localhost:8000` and log in as `admin`. Interactive API documentation is at `http://localhost:8000/docs`.

For development with hot reload, run `npm run dev` in `frontend` (it proxies `/api` to port 8000) and open `http://localhost:5173`.

For running as a Windows service, firewall setup, backups, moving data to a new PC, and troubleshooting, see the **[full setup guide](docs/IP_Inventory_Setup_Guide.md)**.

## Roles

| Capability | Admin | Normal User |
|---|---|---|
| Dashboard, IP list, search, CSV export | Yes | Yes |
| Assign, edit, release IPs | Yes | Yes |
| Create and edit VLANs, reserve IPs | Yes | No |
| Manage users | Yes | No |
| View audit log | Yes | No |

## API overview

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/change-password` |
| Users (Admin) | `GET/POST /api/users`, `PATCH /api/users/{id}`, `POST /api/users/{id}/password` |
| VLANs (Admin) | `GET/POST /api/vlans`, `POST /api/vlans/preview`, `GET/PATCH /api/vlans/{id}` |
| IPs | `GET /api/ips`, `GET /api/ips/available`, `POST /api/ips/{id}/assign`, `/release`, `/status`, `PATCH /api/ips/{id}` |
| Audit (Admin) | `GET /api/audit` |
| Reports | `GET /api/dashboard`, `GET /api/export/ips.csv` |

## Design notes

- IP addresses are stored as integers (`INET_ATON` / `INET_NTOA`), so sorting is correct and range queries are fast.
- Each VLAN stores its first and last address as integers. Overlap detection is a single range comparison.
- VLAN creation takes a MySQL named lock and runs the overlap check and the bulk insert in one transaction.
- Assignment uses a conditional `UPDATE ... WHERE status = 'available'`, so two simultaneous requests cannot both succeed.
- Network and broadcast addresses are not stored as IP records. New IPs start as `available`, and the gateway is `reserved`.

## Security notes

- **Never commit passwords, `.env` files, or `JWT_SECRET`.** The `.gitignore` in this repository excludes them.
- Use a dedicated MySQL user with only `SELECT, INSERT, UPDATE, DELETE` on `ip_inventory`, not `root`.
- Always set a strong `JWT_SECRET`. Anyone who knows it can forge a login token.
- The app serves plain HTTP. On a shared or untrusted network, put it behind an HTTPS reverse proxy.
- The default `admin` account is created with a placeholder hash and cannot log in until you run `set_password.py`.

## Future enhancements

**Data and workflow**
- Bulk import of existing IPs from Excel, with validation and a report of rejected rows
- VLAN deactivate/delete (soft delete, blocked while IPs are assigned)
- Per-IP assignment history (which equipment used the IP, and when)
- Duplicate warnings for equipment ID, CPU S/N and instrument S/N
- Ping / reachability check to find IPs marked available but actually in use

**Reports and alerts**
- Dashboard charts (utilization per VLAN, usage by department)
- Printable reports and PDF export
- Email alerts when a VLAN passes a utilization threshold (for example 90%)

**Security and administration**
- Login attempt limiting and automatic account lockout
- Automatic logout after inactivity and a password strength policy
- HTTPS through a reverse proxy
- A read-only role for managers
- Dedicated database user and encrypted secrets management

**Platform**
- Docker support for one-command deployment
- Automated scheduled database backups with off-server copy
- Automated tests and a CI pipeline

## Author

Developed by **Mr. C.K. Chiranjivi**, IT_EUS_TEAM_Pipan.

## License

Add a `LICENSE` file before publishing (for example MIT), and update this section. If the project is internal to your organization, check your company's policy before making the repository public.
