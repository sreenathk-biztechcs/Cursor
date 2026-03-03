# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import csv
import base64
import io


class ServerBulkImport(models.TransientModel):
    _name = 'server.monitoring.bulk.import'
    _description = 'Bulk Import Servers'

    file = fields.Binary(string='CSV File', required=True)
    filename = fields.Char(string='Filename')

    def action_import(self):
        """Import servers from CSV file.
        Expected columns: hostname,ip_address,os_type,cpu_cores,ram_total_gb,disk_total_gb,purpose
        """
        data = base64.b64decode(self.file)
        reader = csv.DictReader(io.StringIO(data.decode('utf-8')))

        created = 0
        for row in reader:
            self.env['server.monitoring.server'].create({
                'name': row.get('hostname', ''),
                'ip_address': row.get('ip_address', ''),
                'os_type': row.get('os_type', 'linux'),
                'cpu_cores': int(row.get('cpu_cores', 0) or 0),
                'ram_total_gb': float(row.get('ram_total_gb', 0) or 0),
                'disk_total_gb': float(row.get('disk_total_gb', 0) or 0),
                'purpose': row.get('purpose', ''),
                'state': 'draft',
            })
            created += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Import Complete'),
                'message': _('%d servers imported successfully.') % created,
                'type': 'success',
            },
        }
