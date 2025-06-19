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

            # Use generate_email_dict() instead of generate_email()
            mail_values = mail_template.generate_email_dict(
                res_id=self.id
            )
            _logger.debug("Original mail values: %s", mail_values)

            # Force sender and recipient
            mail_values['email_from'] = forced_sender
            mail_values['email_to'] = team_leader.email
            _logger.info("Final email_from: %s, email_to: %s",
                         mail_values.get('email_from'), mail_values.get('email_to'))

            mail = self.env['mail.mail'].create(mail_values)
            mail.send()

            _logger.info("Successfully sent notification from %s to team leader %s",
                         forced_sender, team_leader.email)
        else:
            _logger.error("Email template 'Helpdesk_Routing.ticket_assignment_email_template' not found")
    except Exception as e:
        _logger.error("Notification failed for ticket %s: %s",
                      self.id, str(e), exc_info=True)

    self._send_in_app_notification(team_leader)
