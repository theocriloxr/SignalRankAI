"""Fix field mappings for EconomicEvent"""
import re

# Fix the economic_calendar.py to use correct field names from EconomicEvent model
with open('services/economic_calendar.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the field mapping
old_pattern = '''                    {
                        "title": e.event_name,
                        "currency": e.currency,
                        "impact": e.impact_level,
                        "event_time": e.event_time,
                        "source": "db",
                    }'''

new_pattern = '''                    {
                        "title": e.title,
                        "currency": e.currency,
                        "impact": e.impact,
                        "event_time": e.event_date,
                        "source": e.source or "db",
                    }'''

content = content.replace(old_pattern, new_pattern)

with open('services/economic_calendar.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed economic_calendar.py field mappings')
