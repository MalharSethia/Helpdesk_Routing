# models/res_config_settings.py
from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    internal_domains = fields.Char(
        string="Internal Email Domains",
        config_parameter='helpdesk_routing.internal_domains',
        default='wavext.io',
        help="Comma-separated list of internal email domains"
    )
    
    internal_team_id = fields.Many2one(
        'helpdesk.ticket.team',
        string="Internal Team",
        config_parameter='helpdesk_routing.internal_team_id',
        help="Team for internal tickets"
    )
    
    external_team_id = fields.Many2one(
        'helpdesk.ticket.team',
        string="External Team", 
        config_parameter='helpdesk_routing.external_team_id',
        help="Team for external tickets"
    )
