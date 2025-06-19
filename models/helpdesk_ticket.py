# models/helpdesk_ticket.py
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import re
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
            else:
                ticket.email_domain = False

    @api.depends('email_domain')
    def _compute_is_internal_ticket(self):
        internal_domains = self.env['ir.config_parameter'].sudo().get_param(
            'helpdesk_routing.internal_domains', 'wavext.io'
        ).split(',')
        internal_domains = [domain.strip().lower() for domain in internal_domains]
        
        for ticket in self:
            ticket.is_internal_ticket = ticket.email_domain in internal_domains

    @api.model_create_multi
    def create(self, vals_list):
        tickets = super().create(vals_list)
        for ticket in tickets:
            if not ticket.routing_processed:
                ticket._auto_assign_team()
                ticket._notify_team_leader()
                ticket.routing_processed = True
        return tickets

    def _auto_assign_team(self):
        """Automatically assign team based on email domain"""
        self.ensure_one()
        
        # Only auto-assign if no team is already set
        if not self.team_id:
            team_to_assign = None
            
            if self.is_internal_ticket:
                # Try to get team from config first, then fallback to data
                internal_team_id = self.env['ir.config_parameter'].sudo().get_param(
                    'helpdesk_routing.internal_team_id'
                )
                if internal_team_id:
                    team_to_assign = self.env['helpdesk.ticket.team'].browse(int(internal_team_id))
                else:
                    team_to_assign = self.env.ref('helpdesk_routing.internal_helpdesk_team', raise_if_not_found=False)
            else:
                # Try to get team from config first, then fallback to data
                external_team_id = self.env['ir.config_parameter'].sudo().get_param(
                    'helpdesk_routing.external_team_id'
                )
                if external_team_id:
                    team_to_assign = self.env['helpdesk.ticket.team'].browse(int(external_team_id))
                else:
                    team_to_assign = self.env.ref('helpdesk_routing.external_helpdesk_team', raise_if_not_found=False)
            
            if team_to_assign and team_to_assign.exists():
                self.team_id = team_to_assign.id
                ticket_type = "internal" if self.is_internal_ticket else "external"
                _logger.info(f"Assigned ticket {self.name} to {ticket_type} team: {team_to_assign.name}")

    def _get_verified_from_email(self):
        """Get a verified email address for AWS SES"""
        # Get the configured FROM email address
        helpdesk_from_email = self.env['ir.config_parameter'].sudo().get_param(
            'helpdesk_routing.from_email', 'helpdesk@wavext.io'
        )
        
        # List of fallback verified emails (add your verified SES emails here)
        verified_emails = [
            helpdesk_from_email,
            'helpdesk@wavext.io',
            'noreply@wavext.io',
            # Add other verified emails as needed
        ]
        
        # Return the first configured email (should be verified)
        return verified_emails[0]

    def _notify_team_leader(self):
        """Send notification to team leader using email template"""
        self.ensure_one()
        
        # Check if notifications are enabled
        notifications_enabled = self.env['ir.config_parameter'].sudo().get_param(
            'helpdesk_routing.enable_notifications', 'True'
        ).lower() == 'true'
        
        if not notifications_enabled:
            return
        
        if not self.team_id or not self.team_id.user_id:
            _logger.warning(f"No team leader found for ticket {self.name}")
            return
            
        team_leader = self.team_id.user_id
        
        # Get the verified FROM email address
        verified_from_email = self._get_verified_from_email()
        
        # Get the SMTP server to use
        smtp_server = self.env['ir.mail_server'].sudo().search([
            ('smtp_host', '=', 'email-smtp.eu-west-1.amazonaws.com')
        ], limit=1)
        
        if not smtp_server:
            # Fallback to any available SMTP server
            smtp_server = self.env['ir.mail_server'].sudo().search([
                ('smtp_host', '!=', False)
            ], limit=1)
        
        # Send email notification using template
        try:
            mail_template = self.env.ref('helpdesk_routing.ticket_assignment_email_template', raise_if_not_found=False)
            if mail_template:
                # Create mail record with verified FROM address
                mail_values = mail_template.generate_email(self.id)
                
                # Set proper reply-to address (customer's email)
                customer_email = self.partner_email or (self.partner_id.email if self.partner_id else verified_from_email)
                
                # FORCE OVERRIDE with verified email addresses
                mail_values.update({
                    'email_from': verified_from_email,  # Use verified email
                    'email_to': team_leader.email,
                    'reply_to': customer_email,  # Customer can still be reached via reply-to
                    'mail_server_id': smtp_server.id if smtp_server else False,
                })
                
                # DEBUG: Log the actual values being used
                _logger.info(f"DEBUG - Final mail values:")
                _logger.info(f"DEBUG - email_from: {mail_values.get('email_from')}")
                _logger.info(f"DEBUG - email_to: {mail_values.get('email_to')}")
                _logger.info(f"DEBUG - reply_to: {mail_values.get('reply_to')}")
                _logger.info(f"DEBUG - mail_server_id: {mail_values.get('mail_server_id')}")
                _logger.info(f"DEBUG - smtp_server: {smtp_server.name if smtp_server else 'None'}")
                
                # Create and send the mail
                mail_record = self.env['mail.mail'].create(mail_values)
                
                try:
                    mail_record.send()
                    _logger.info(f"Successfully sent email notification to {team_leader.email} for ticket {self.name}")
                except Exception as email_error:
                    _logger.error(f"Failed to send email for ticket {self.name}: {email_error}")
                    mail_record.write({'state': 'exception', 'failure_reason': str(email_error)})
            else:
                _logger.warning(f"Email template 'helpdesk_routing.ticket_assignment_email_template' not found")
        except Exception as e:
            _logger.error(f"Could not send email notification for ticket {self.name}: {e}")
        
        # Send in-app notification as fallback
        try:
            ticket_type = "Internal" if self.is_internal_ticket else "External"
            
            # Include customer info in the notification
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
            _logger.info(f"Sent in-app notification to team leader {team_leader.name} for ticket {self.name}")
        except Exception as e:
            _logger.warning(f"Could not send in-app notification for ticket {self.name}: {e}")

    def write(self, vals):
        result = super().write(vals)
        
        # If partner_email or partner_id is updated, reprocess routing if needed
        if ('partner_email' in vals or 'partner_id' in vals) and not vals.get('routing_processed'):
            for ticket in self:
                if not ticket.team_id:  # Only reassign if no team is set
                    ticket._auto_assign_team()
                    ticket._notify_team_leader()
                    ticket.routing_processed = True
        
        return result
