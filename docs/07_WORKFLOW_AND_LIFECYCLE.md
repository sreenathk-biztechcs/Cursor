# 07 — Server Workflow & Lifecycle

## The Complete Journey of a Server — From Request to Decommission

---

## Lifecycle State Machine

```
                                    ┌───────────┐
                                    │           │
                                    │   DRAFT   │ ← You create a server record
                                    │           │
                                    └─────┬─────┘
                                          │ Submit Request
                                          v
                                    ┌───────────┐
                          ┌─────────│ REQUESTED │
                          │         └─────┬─────┘
                          │               │ Manager Reviews
                          │               v
                     ┌────┴────┐    ┌───────────┐
                     │REJECTED │    │ APPROVED  │
                     └─────────┘    └─────┬─────┘
                                          │ IT Team Sets Up
                                          v
                                    ┌───────────┐
                                    │ ALLOCATED │ ← Server assigned, details filled
                                    └─────┬─────┘
                                          │ Enable Monitoring
                                          v
                         ┌──────────────────────────────────┐
                         │                                  │
                    ┌────┴────┐                        ┌────┴────┐
             ┌──────│ ACTIVE  │◄──────────────────────│INACTIVE │
             │      └────┬────┘    (AI auto-switches) └────┬────┘
             │           │                                  │
             │           │                                  │
             │      ┌────┴────────┐                         │
             │      │ MAINTENANCE │◄────────────────────────┘
             │      └─────────────┘
             │           │
             │           v
             │    ┌──────────────────┐
             └───>│ DECOMMISSIONED   │ ← End of life
                  └──────────────────┘
```

---

## State Descriptions

| State | Meaning | Who Sets It | Monitoring Active? |
|---|---|---|---|
| **Draft** | Record created, no request submitted | User | No |
| **Requested** | Formal request submitted for approval | User | No |
| **Approved** | Management approved the request | Manager | No |
| **Rejected** | Request denied | Manager | No |
| **Allocated** | Server assigned, IP/credentials configured | IT Admin | No |
| **Active** | Server in use, monitoring running | Auto (AI/System) | Yes |
| **Inactive** | Server not actively used (AI detected) | Auto (AI) | Yes |
| **Maintenance** | Planned downtime for maintenance | User/Admin | Yes (alerts suppressed) |
| **Decommissioned** | Server removed from service | Admin | No |

---

## Detailed Workflow

### Step 1: Create Server Record (Draft)

**Who**: Any user with "Server User" role
**What happens**:
- User creates a new record in Odoo with basic info:
  - Name: "New DB Server for Project X"
  - Category: Database Server
  - Environment: Production
  - Purpose: "PostgreSQL server for Project X customer data"
  - Requested specs: 8 CPU, 32GB RAM, 500GB SSD

### Step 2: Submit Request (Requested)

**Who**: User clicks "Submit Request" button
**What happens**:
- State changes to "Requested"
- `server.request` record created automatically
- Email notification sent to approvers (configured per department)
- Activity assigned to the IT manager

### Step 3: Approval (Approved/Rejected)

**Who**: IT Manager or designated approver
**What happens on Approve**:
- State changes to "Approved"
- Email notification to requester
- Activity assigned to IT operations team to set up the server

**What happens on Reject**:
- State changes to "Rejected"
- Rejection reason recorded
- Email notification to requester with reason

### Step 4: Server Setup (Allocated)

**Who**: IT Operations team
**What happens**:
- IT team provisions the server (physical or cloud)
- Fills in actual details:
  - Real hostname and IP address
  - SSH credentials
  - Actual specifications
  - Data center / rack location
- Installs monitoring agent (Telegraf / custom)
- Generates API key for the server
- State changes to "Allocated"

### Step 5: Enable Monitoring (Active)

**Who**: IT Admin clicks "Start Monitoring" or automatic on first metric received
**What happens**:
- `is_monitored` set to True
- State changes to "Active"
- Monitoring agent starts sending metrics
- Server appears on the dashboard
- AI analysis begins for this server

### Step 6: Ongoing Monitoring (Active ↔ Inactive)

**Who**: Automatic (AI + System)
**What happens**:
- Metrics collected every 60 seconds
- Dashboard shows real-time data
- AI classifies server every hour:
  - **Active**: Normal usage patterns detected
  - **Inactive**: Very low or no usage for extended period
  - **Underutilized**: Some usage but significantly below capacity
  - **Overloaded**: Consistently high resource usage
- Alerts fire automatically for threshold violations
- The system can auto-switch between Active and Inactive

### Step 7: Maintenance Mode

**Who**: Admin/User puts server in maintenance mode
**What happens**:
- State changes to "Maintenance"
- Alerts are suppressed (no false alarms during planned downtime)
- Monitoring continues (to verify server comes back)
- Scheduled return-to-active date can be set
- Dashboard shows maintenance icon

### Step 8: Decommission

**Who**: IT Admin
**What happens**:
- State changes to "Decommissioned"
- Monitoring disabled
- Historical data retained (for audit/reporting)
- Server removed from active dashboard
- AI stops analyzing this server
- Date recorded for lifecycle tracking

---

## Approval Workflow Configuration

### Simple Approval (Default)

```
User → IT Manager → Done
```

### Multi-Level Approval (Optional)

```
User → Team Lead → IT Manager → CTO (for production only) → Done
```

### Department-Based Routing

| Requester Department | Approver |
|---|---|
| Engineering | Engineering Manager |
| Marketing | Marketing Head → IT Manager |
| Finance | Finance Director → IT Manager |
| Any (Production) | IT Manager → CTO |

### Approval Notifications

Each state change triggers:
1. **Email** to relevant parties
2. **Odoo Activity** assigned to next person in chain
3. **Odoo Discuss** notification in the #server-requests channel
4. **Optional**: Slack/Telegram notification

---

## Automation Rules

These run automatically with no human intervention:

| Trigger | Condition | Action |
|---|---|---|
| No metrics for 5 min | Active server, `last_metric_time < now - 5min` | Set `monitoring_state = 'down'`, create alert |
| No metrics for 30 min | Active server | Change state to Inactive, alert to owner |
| Metrics resume | Inactive/Down server starts sending metrics | Change state to Active, resolve "down" alerts |
| Low usage 7 days | CPU < 5% avg for 7 days | Set AI classification to "idle", notify owner |
| High usage 1 hour | CPU > 90% avg for 1 hour | Create "overloaded" alert, notify owner |
| Disk > 90% | Disk usage crosses 90% | Create critical alert, notify IT team |
| Maintenance ended | Current date > maintenance end date | Return to Active state |
| Allocation expired | Allocated state > 30 days without activation | Notify IT team to follow up |

---

## User Roles & Permissions

| Role | Can Do | Cannot Do |
|---|---|---|
| **Server User** | View all servers, create draft records, submit requests, use AI chat | Approve requests, modify other users' servers, change monitoring config |
| **Server Manager** | Everything User can + approve/reject requests, modify any server | Change global settings, decommission servers |
| **Server Admin** | Everything + configure monitoring, manage API keys, set alert rules, decommission | N/A (full access) |
| **System Administrator** | Everything + configure AI, manage global settings | N/A (Odoo admin) |

### Access Rights (ir.model.access.csv)

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_server_user,server.server.user,model_server_server,group_server_user,1,1,1,0
access_server_manager,server.server.manager,model_server_server,group_server_manager,1,1,1,0
access_server_admin,server.server.admin,model_server_server,group_server_admin,1,1,1,1
```

### Record Rules

- Users can only edit servers they own (unless Manager/Admin)
- Users can only see servers in their department (optional, configurable)
- Everyone can view the dashboard
- AI Chat accessible to all users

---

## Integration with HR Department

If your company uses Odoo HR module:
- `server.server.department_id` links to `hr.department`
- Server costs can be allocated to departments
- Department heads auto-assigned as approvers
- Department-level dashboards show only their servers
