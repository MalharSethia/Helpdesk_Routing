# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    is_internal_ticket = fields.Boolean(
        string="Internal Ticket",
        compute="_compute_is_internal_ticket",
        store=True,
        help="Indicates if this ticket is from an internal user"
    )
    
    email_domain = fields.Char(
        string="Email Domain",
        compute="_compute_email_domain",
        store=True,
        help="Domain extracted from partner email",
        index=True
    )
    
    routing_processed = fields.Boolean(
        string="Routing Processed",
        default=False,
        help="Technical field to track if routing has been processed"
    )

    @api.depends('partner_email', 'partner_id.email')
    def _compute_email_domain(self):
        for ticket in self:
            email = ticket.partner_email or (ticket.partner_id and ticket.partner_id.email)
            if email:
                domain = email.split('@')[-1].lower()
                ticket.email_domain = domain
                _logger.debug("Computed domain %s for ticket %s", domain, ticket.id)
            else:
                ticket.email_domain = False
                _logger.debug("No email found for ticket %s", ticket.id)

    @api.depends('email_domain')
    def _compute_is_internal_ticket(self):
        internal_domains = self.env['ir.config_parameter'].sudo().get_param(
            'helpdesk_routing.internal_domains', 'wavext.io'
        ).split(',')
        internal_domains = [domain.strip().lower() for domain in internal_domains]
        _logger.info("Internal domains configured: %s", internal_domains)
        
        for ticket in self:
            ticket.is_internal_ticket = ticket.email_domain in internal_domains
            _logger.debug("Ticket %s internal status: %s (domain: %s)", 
                         ticket.id, ticket.is_internal_ticket, ticket.email_domain)

    @api.model_create_multi
    def create(self, vals_list):
        _logger.info("Creating %d tickets with vals: %s", len(vals_list), vals_list)
        tickets = super().create(vals_list)
        for ticket in tickets:
            if not ticket.routing_processed:
                _logger.info("Processing routing for new ticket %s", ticket.id)
                ticket._auto_assign_team()
                ticket._notify_team_leader()
                ticket.routing_processed = True
                _logger.info("Routing processed for ticket %s", ticket.id)
        return tickets

    def _auto_assign_team(self):
        """Automatically assign team based on email domain"""
        self.ensure_one()
        _logger.info("Starting team assignment for ticket %s", self.id)
        
        if not self.team_id:
            team_to_assign = None
            
            if self.is_internal_ticket:
                _logger.debug("Ticket %s is internal", self.id)
                internal_team_id = self.env['ir.config_parameter'].sudo().get_param(
                    'helpdesk_routing.internal_team_id'
                )
                _logger.debug("Internal team ID from params: %s", internal_team_id)
                
                if internal_team_id:
                    team_to_assign = self.env['helpdesk.ticket.team'].browse(int(internal_team_id))
                else:
                    team_to_assign = self.env.ref('helpdesk_routing.internal_helpdesk_team', raise_if_not_found=False)
                    _logger.debug("Using default internal team: %s", team_to_assign)
            else:
                _logger.debug("Ticket %s is external", self.id)
                external_team_id = self.env['ir.config_parameter'].sudo().get_param(
                    'helpdesk_routing.external_team_id'
                )
                _logger.debug("External team ID from params: %s", external_team_id)
                
                if external_team_id:
                    team_to_assign = self.env['helpdesk.ticket.team'].browse(int(external_team_id))
                else:
                    team_to_assign = self.env.ref('helpdesk_routing.external_helpdesk_team', raise_if_not_found=False)
                    _logger.debug("Using default external team: %s", team_to_assign)
            
            if team_to_assign and team_to_assign.exists():
                self.team_id = team_to_assign.id
                _logger.info("Assigned ticket %s to team %s (%s)", 
                            self.id, team_to_assign.id, 'internal' if self.is_internal_ticket else 'external')
            else:
                _logger.warning("No valid team found for ticket %s", self.id)
        else:
            _logger.debug("Ticket %s already has team %s assigned", self.id, self.team_id.id)

    def _notify_team_leader(self):
        """Send notification to team leader without customer email in reply_to"""
        self.ensure_one()
        _logger.info("Preparing to notify team leader for ticket %s", self.id)
        
        if not self.env['ir.config_parameter'].sudo().get_param(
            'helpdesk_routing.enable_notifications', 'True'
        ).lower() == 'true':
            _logger.info("Notifications disabled by system parameter")
            return
        
        if not self.team_id or not self.team_id.user_id:
            _logger.warning("No team leader found for ticket %s (team: %s)", 
                          self.id, self.team_id.id if self.team_id else None)
            return
            
        team_leader = self.team_id.user_id
        _logger.debug("Team leader identified: %s (ID: %s)", 
                     team_leader.name, team_leader.id)

        try:
            mail_template = self.env.ref('Helpdesk_Routing.ticket_assignment_email_template')
            if mail_template:
                forced_sender = self.env['ir.config_parameter'].sudo().get_param(
                    'helpdesk_routing.notification_sender_email', 'msethia@wavext.io'
                )
                _logger.info("Using forced sender email: %s", forced_sender)
                
                mail_values = mail_template.generate_email(
                    self.id, 
                    fields=['email_from', 'email_to', 'subject', 'body_html']
                )
                _logger.debug("Original mail values: %s", mail_values)
                
                # Force the sender email
                mail_values['email_from'] = forced_sender
                _logger.info("Final email_from being used: %s", mail_values.get('email_from'))
                
                mail = self.env['mail.mail'].create(mail_values)
                mail.send()
                
                _logger.info("Successfully sent notification from %s to team leader %s", 
                            forced_sender, team_leader.email)
            else:
                _logger.error("Email template 'helpdesk_routing.ticket_assignment_email_template' not found")
        except Exception as e:
            _logger.error("Notification failed for ticket %s: %s", self.id, str(e), exc_info=True)
        
        self._send_in_app_notification(team_leader)

    def _send_in_app_notification(self, team_leader):
        """In-app notification with customer details (unchanged)"""
        try:
            ticket_type = "Internal" if self.is_internal_ticket else "External"
            customer_info = f"Customer: {self.partner_id.name if self.partner_id else 'Guest'}"
            email_info = f"Email: {self.partner_email or (self.partner_id.email if self.partner_id else 'No email')}"
            
            plain_message = (
                f"New {ticket_type.lower()} ticket assigned to your team.\n\n"
                f"Ticket: {self.name}\n"
                f"{customer_info}\n"
                f"{email_info}\n"
                f"Subject: {self.name or 'No subject'}"
            )
            
            self.message_post(
                body=plain_message,
                subject=f"New {ticket_type} Ticket Assigned",
                partner_ids=[team_leader.partner_id.id],
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            _logger.info("Successfully posted in-app notification for ticket %s to %s", 
                        self.id, team_leader.name)
        except Exception as e:
            _logger.error("In-app notification failed for ticket %s: %s", self.id, str(e), exc_info=True)

    def write(self, vals):
        _logger.debug("Writing to ticket with values: %s", vals)
        result = super().write(vals)
        
        if ('partner_email' in vals or 'partner_id' in vals) and not vals.get('routing_processed'):
            _logger.info("Email or partner changed, reprocessing routing")
            for ticket in self:
                if not ticket.team_id:
                    _logger.debug("No team assigned, processing routing for ticket %s", ticket.id)
                    ticket._auto_assign_team()
                    ticket._notify_team_leader()
                    ticket.routing_processed = True
                    _logger.info("Routing reprocessed for ticket %s", ticket.id)
        
        return result
