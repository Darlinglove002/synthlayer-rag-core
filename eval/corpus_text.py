"""Synthetic corpus for the eval harness: three short documents about a *fictional* product.

Everything here is invented (Halden Systems / Brightbay do not exist), so no question can be
answered from a model's memory: a correct answer proves retrieval worked. Each page holds one
fact the questions in questions.json are written against.
"""

DOCS: dict[str, list[str]] = {
    "brightbay_admin_guide": [
        # page 1
        "Brightbay Admin Guide - Installation. A Brightbay server needs at least 4 vCPU and 16 GB of RAM "
        "for a production deployment; smaller machines are fine for evaluation only. The platform runs on "
        "PostgreSQL 14 or newer, which can be installed on the same host or provided as a managed service.\n\n"
        "Install the server with the command brightbay-ctl install --channel stable. The installer "
        "listens on port 7443 by default and creates the service account automatically. Place the license "
        "file at /etc/brightbay/license.key before the first start, otherwise the service will refuse to boot.\n\n"
        "After installation, open the admin console in a browser and complete the first-run wizard. The "
        "wizard asks for the organisation name, the time zone, and the address of the outgoing mail relay.",
        # page 2
        "Backups. Brightbay takes a full snapshot every night at 02:30 UTC. Snapshots are encrypted with "
        "AES-256 and stored in the backup bucket you configure during installation. By default old snapshots "
        "are deleted after 14 days; change this with the configuration key backup.retention_days.\n\n"
        "To restore, stop the application and run brightbay-ctl restore --snapshot <id>. A restore replaces "
        "the current database, so export anything you want to keep first. Optional cross-region replication "
        "copies every snapshot to a second bucket within one hour.\n\n"
        "Test your restore procedure at least once per quarter. A backup that has never been restored is "
        "only a hope, not a plan.",
        # page 3
        "User management and single sign-on. Brightbay supports SAML 2.0 and OIDC for single sign-on, and "
        "SCIM provisioning to create and disable accounts automatically from your identity provider. Local "
        "accounts remain available as a fallback for the break-glass administrator.\n\n"
        "The password policy requires at least 12 characters. After 5 failed sign-in attempts an account is "
        "locked for 15 minutes; the number of attempts is controlled by auth.lockout_threshold. Sessions "
        "expire after 8 hours, or after 30 minutes without activity.\n\n"
        "Roles are assigned per workspace. The Owner role can manage billing and delete the workspace, "
        "while the Analyst role is read-only.",
        # page 4
        "Monitoring and health. Brightbay exposes Prometheus metrics at /metrics on port 9102. Load "
        "balancers should probe /healthz, which returns HTTP 200 only when the database and the job queue "
        "are reachable. We recommend alerting when the queue depth exceeds 500 jobs for more than five minutes.\n\n"
        "Application logs are written as JSON lines. They rotate at 100 MB and the last 7 files are kept. "
        "Ship them to your log platform with any standard agent; no custom parser is needed.\n\n"
        "Dashboards for the most common metrics are included in the monitoring bundle that ships with each release.",
        # page 5
        "Upgrades. Brightbay supports rolling upgrades with no downtime, but only one minor version at a "
        "time: to go from 4.6 to 4.8 you must pass through 4.7. Run brightbay-ctl upgrade --to 4.8.2 to start. "
        "Always read the release notes first and take a snapshot.\n\n"
        "Downgrades are not supported once the schema migration has run. If an upgrade goes wrong, the only "
        "way back is to restore the snapshot you took before starting.\n\n"
        "Plan a maintenance window even though the upgrade is rolling; long-running reports may be "
        "interrupted when their worker restarts.",
    ],
    "brightbay_troubleshooting": [
        # page 1
        "Troubleshooting Handbook - License errors. Error E-4012 means the license is expired or the server "
        "clock differs from real time by more than 5 minutes. Check that NTP synchronisation is running, "
        "then re-install the license file and restart the service.\n\n"
        "A license that expires on a weekend does not cause an immediate outage: there is a 72-hour grace "
        "period, during which the console shows a yellow banner but every feature keeps working.\n\n"
        "If the error persists after the clock is corrected, collect a support bundle and contact support.",
        # page 2
        "Database connection errors. Error E-5307 means the database connection pool is exhausted: every "
        "connection is busy and new requests have to wait. Raise db.pool_max from the default of 20 to 50, "
        "and make sure the PostgreSQL max_connections setting is higher than the sum of all pools.\n\n"
        "Long-running transactions are the usual cause. Look for sessions that have been idle in "
        "transaction for more than a few minutes and ask the owning team to fix the report or integration.\n\n"
        "Do not simply restart the service: the pool fills up again within minutes if the cause is not removed.",
        # page 3
        "Webhook delivery. Error E-6120 is raised when a webhook could not be delivered after 6 retries "
        "with exponential backoff. Your endpoint must answer within 10 seconds with a 2xx status; slower "
        "or failing endpoints are treated as down.\n\n"
        "Events that exhaust their retries are not discarded. They are moved to the dead letter queue "
        "dlq.webhooks, where they stay for 7 days and can be replayed from the console once the endpoint is healthy.\n\n"
        "Use the delivery log to see the response code and latency of every attempt.",
        # page 4
        "Slow dashboards. Dashboard charts read from materialized views that are refreshed every 15 minutes, "
        "so very recent data may be missing; this is expected and not an error.\n\n"
        "If a dashboard takes longer than 30 seconds to load, first reduce the date range, because the "
        "cost grows with the number of days scanned. Next, remove unused filters and split a very large "
        "dashboard into several smaller ones. Charts that scan more than 90 days of raw events should use the "
        "pre-aggregated daily tables instead.\n\n"
        "Persistent slowness after these steps usually points to missing database indexes or an undersized server.",
        # page 5
        "Contacting support. Support tickets have three severity levels. A P1 ticket, meaning production is "
        "completely down, receives a first response within 1 hour, around the clock. A P2 ticket, meaning a "
        "major feature is degraded, is answered within 4 business hours. A P3 ticket, for questions and "
        "minor issues, is answered by the next business day.\n\n"
        "Before opening a ticket, run brightbay-ctl support-bundle and attach the archive. It collects "
        "logs, configuration with secrets removed, and version information, and usually saves a day of "
        "back-and-forth.\n\n"
        "Write to support@halden.example or use the in-product help button.",
    ],
    "halden_security_overview": [
        # page 1
        "Halden Security Overview - Encryption. All traffic between clients and Halden services is protected "
        "with TLS 1.3. Customer data stored on disk, including database volumes and backups, is encrypted "
        "at rest with AES-256.\n\n"
        "Encryption keys are managed in a cloud KMS and rotated every 90 days. Old key versions remain "
        "available only to decrypt existing data and are retired once no data depends on them.\n\n"
        "Customers on the Enterprise plan can bring their own key and revoke it at any time.",
        # page 2
        "Data residency and retention. Customers in the European Union are hosted in the Frankfurt region; "
        "customers in the United States are hosted in Virginia. Data never leaves the chosen region unless "
        "the customer enables cross-region replication.\n\n"
        "When a customer closes their account, their data is purged within 30 days. Audit logs are kept "
        "for 400 days so that investigations can look back more than a year.\n\n"
        "Residency is chosen at signup and cannot be changed afterwards without a migration project.",
        # page 3
        "Certifications and audits. Halden holds a SOC 2 Type II report, renewed every October, and has been "
        "certified to ISO 27001 since 2022. An independent firm performs a penetration test every year and "
        "the summary is available under NDA.\n\n"
        "A HIPAA BAA, the business associate agreement for health data, is available on the Enterprise "
        "plan. Customers on other plans should not store protected health information.\n\n"
        "Auditor reports can be requested through the trust portal.",
        # page 4
        "Incident response. If customer data is affected by a security incident, Halden notifies the affected "
        "customers within 72 hours of confirming the breach. A dedicated on-call rotation covers security "
        "incidents around the clock.\n\n"
        "After every significant incident a blameless postmortem is published to affected customers within "
        "10 business days. It describes the timeline, the root cause and the concrete follow-up actions.\n\n"
        "Customers can report suspected vulnerabilities to the security mailbox and are acknowledged within one business day.",
        # page 5
        "Employee access. Access to production systems requires a hardware security key. Engineers get "
        "just-in-time access that is approved by a second person and expires automatically after 4 hours; "
        "there are no standing administrator rights.\n\n"
        "All employees pass a background check before they join, and access rights are reviewed every "
        "quarter. Every production session is recorded and the recordings are kept with the audit logs.\n\n"
        "Contractors follow the same rules and receive access only for the duration of their contract.",
    ],
}
