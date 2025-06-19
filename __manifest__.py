{
    'name': 'Helpdesk Routing',
    'version': '17.0.1.0.0',
    'category': 'Services/Helpdesk',
    'summary': 'Route helpdesk tickets based on email domain and notify team leaders',
    'description': """
        This module automatically routes helpdesk tickets based on the email domain of the requester:
        - wavext.io emails -> Internal team
        - All other emails -> External team
        
        Features:
        - Automatic team assignment based on email domain
        - Notification to team leader with internal link
        - Configurable domain mapping
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['helpdesk_mgmt'],
    'data': [
        'security/ir.model.access.csv',
        'data/helpdesk_data.xml',
        'views/helpdesk_ticket_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
