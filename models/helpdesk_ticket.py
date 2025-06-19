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
            'Helpdesk_Routing.internal_domains', 'wavext.io'
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
                    'Helpdesk_Routing.internal_team_id'
                )
                if internal_team_id:
                    team_to_assign = self.env['helpdesk.ticket.team'].browse(int(internal_team_id))
                else:
                    team_to_assign = self.env.ref('Helpdesk_Routing.internal_helpdesk_team', raise_if_not_found=False)
            else:
                # Try to get team from config first, then fallback to data
                external_team_id = self.env['ir.config_parameter'].sudo().get_param(
                    'Helpdesk_Routing.external_team_id'
                )
                if external_team_id:
                    team_to_assign = self.env['helpdesk.ticket.team'].browse(int(external_team_id))
                else:
                    team_to_assign = self.env.ref('Helpdesk_Routing.external_helpdesk_team', raise_if_not_found=False)

            if team_to_assign and team_to_assign.exists():
                self.team_id = team_to_assign.id
                ticket_type = "internal" if self.is_internal_ticket else "external"
                _logger.info(f"Assigned ticket {self.name} to {ticket_type} team: {team_to_assign.name}")

    def _notify_team_leader(self):
        """Send notification to team leader using email template"""
        self.ensure_one()

        # Check if notifications are enabled
        notifications_enabled = self.env['ir.config_parameter'].sudo().get_param(
            'Helpdesk_Routing.enable_notifications', 'True'
        ).lower() == 'true'

        if not notifications_enabled:
            return

        if not self.team_id or not self.team_id.user_id:
            _logger.warning(f"No team leader found for ticket {self.name}")
            return

        team_leader = self.team_id.user_id

        # Send email notification using template
        try:
            mail_template = self.env.ref('Helpdesk_Routing.ticket_assignment_email_template', raise_if_not_found=False)
            if mail_template:
                # Use with_context to ensure proper email sending
                mail_template.with_context(
                    lang=team_leader.lang or self.env.user.lang
                ).send_mail(
                    self.id,
                    force_send=True,
                    email_values={
                        'email_to': team_leader.email,
                        'recipient_ids': [(4, team_leader.partner_id.id)],
                    }
                )
                _logger.info(f"Sent email notification to {team_leader.email} for ticket {self.name}")
            else:
                _logger.warning(f"Email template 'Helpdesk_Routing.ticket_assignment_email_template' not found")
        except Exception as e:
            _logger.error(f"Could not send email notification for ticket {self.name}: {e}")

        # Send in-app notification (chatter message) - simplified version
        try:
            ticket_type = "Internal" if self.is_internal_ticket else "External"
            simple_body = f"""
            <p>New {ticket_type.lower()} ticket assigned to your team.</p>
            <p><strong>Ticket:</strong> {self.name}<br/>
            <strong>Customer:</strong> {self.partner_id.name if self.partner_id else 'Guest'}<br/>
            <strong>Email:</strong> {self.partner_email or (self.partner_id.email if self.partner_id else 'No email')}</p>
            """

            self.message_post(
                body=simple_body,
                subject=f"New {ticket_type} Ticket Assigned",
                partner_ids=[team_leader.partner_id.id],
                message_type='notification',
                subtype_xmlid='mail.mt_note'  # Use mt_note instead of mt_comment
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
