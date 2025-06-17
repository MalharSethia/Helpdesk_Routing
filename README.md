Helpdesk Ticket Routing Module
🚀 Automatically route helpdesk tickets based on email domains and notify team leaders with internal links.

📌 Features
✔ Automatic Team Assignment

Tickets from @wavext.io → Internal Team

All other domains → External Team

✔ Configurable Domain Mapping

Set custom domains for internal tickets via Settings

✔ Team Leader Notifications

Email + in-app notifications with direct ticket links

✔ Dashboard Enhancements

New filters (Internal/External tickets)

Email domain visibility in views

🛠 Installation
Clone or add the module to your Odoo addons folder:

bash
git clone [your-repo-url] /opt/odoo17/odoo-custom-addons/Helpdesk_Routing
Install the module:

Go to Apps → Update Apps List

Search for "Helpdesk Ticket Routing" → Click Install

⚙ Configuration
Set up Teams & Domains

Go to Settings → Helpdesk → Ticket Routing

Configure:

Internal Email Domains (e.g., wavext.io)

Internal/External Teams

Enable Notifications

Toggle "Send Notifications to Team Leaders" in Settings.

📂 File Structure
text
Helpdesk_Routing/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── helpdesk_ticket.py          # Core routing logic
│   └── res_config_settings.py      # Configuration options
├── security/
│   └── ir.model.access.csv         # Permissions
├── data/
│   └── helpdesk_data.xml           # Default teams + email template
└── views/
    ├── helpdesk_ticket_views.xml    # UI enhancements
    └── res_config_settings_views.xml  # Settings panel
🔧 Dependencies
Odoo 17.0+

helpdesk_mgmt module

🚨 Troubleshooting
"Module not appearing?"

Check __manifest__.py for correct dependencies.

Restart Odoo and upgrade the module.

"Notifications not sent?"

Verify email templates (data/helpdesk_data.xml).

Check Settings → Technical → Email → Logs.

"Team assignment fails?"

Ensure team_id exists in helpdesk.ticket model.

