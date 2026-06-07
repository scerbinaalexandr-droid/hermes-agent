# Diary & Protocol Workflow (2026-06-05)

## Requirement

User wants TWO parallel systems:

### 1. DAILY DIARY (continuous collection)
**Purpose:**
- Track daily activities, meetings, tasks, decisions
- Build historical record for future competency/experience analytics
- Enable long-term pattern recognition

**Collection:**
- User dictates throughout the day (via voice memo or text)
- Auto-save to diary repository/database

**Reports:**
- **Weekly (Friday, cron):** Summary report of entire week
- **Quarterly (cron):** Full quarter summary with detailed analytics capability

**Storage location:**
- Repository: `memory/diary/` (to be created)
- Format: Daily markdown files `YYYY-MM-DD.md`
- Structure: Timestamped entries with auto-detected context

### 2. EXCEL MEETING PROTOCOLS (on-demand)
**Purpose:**
- Formal meeting minutes in Excel format
- Only for meetings (not all tasks/activities)

**Workflow:**
1. User dictates meeting protocol content
2. Agent collects into Excel document
3. Agent shows draft for approval
4. **After user approval** → email to: **scerbinaalexandr@gmail.com**

**Format:**
- Excel file (.xlsx)
- Columns TBD (likely: Date | Time | Participants | Topic | Decisions | Action Items | Deadlines)

---

## Implementation Notes

**Diary cron schedule:**
- Weekly report: Friday, time TBD (suggest 18:00 EEST)
- Quarterly report: First week of Q start (Jan/Apr/Jul/Oct), time TBD

**Excel protocol delivery:**
- Requires email sending capability (check if available in environment)
- Draft-approval flow must be explicit (user said "после его согласования")

**Open questions for user:**
1. Weekly report time? (suggest Friday 18:00)
2. Excel columns — confirm structure
3. Diary collection — passive (user sends when ready) or active prompt (e.g., evening "what happened today?")?

---

## Privacy Guard Reminder

Both diary and protocols subject to privacy rules from `soul.md`:
- Pseudonymize unknown partner names
- Price ranges instead of exact contract values
- No banking/passwords/family medical data
- NDA-risk quotes → rephrase as "own judgment"
