#!/usr/bin/env python3
"""Script to fix extra whitespace lines in class definition"""

with open('engine/core.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix: remove lines that are just 9 spaces + newline inside the class
# These appear as '        \n' after stripping leading spaces
old_block = '''    class _FallbackThresholdOptimizer:
        def get_threshold(self) -> float:
            return float(os.getenv('ML_PROB_THRESHOLD', '0.55') or 0.55)
        
        async def analyze_and_adjust(self, force: bool = False):
            return None
        
        def get_config(self):
            from datetime import datetime
            return type('Config', (), {
                'ml_prob_threshold': self.get_threshold(),
                'min_score_threshold': 70.0,
                'confluence_min': 0.0,
                'last_updated': datetime.utcnow(),
                'source': 'env',
            })()
    '''

new_block = '''    class _FallbackThresholdOptimizer:
        def get_threshold(self) -> float:
            return float(os.getenv('ML_PROB_THRESHOLD', '0.55') or 0.55)
        
        async def analyze_and_adjust(self, force: bool = False):
            return None
        
        def get_config(self):
            from datetime import datetime
            return type('Config', (), {
                'ml_prob_threshold': self.get_threshold(),
                'min_score_threshold': 70.0,
                'confluence_min': 0.0,
                'last_updated': datetime.utcnow(),
                'source': 'env',
            })()
    '''

# The issue is there's an extra line with only whitespace between methods
# Let's manually fix lines 150, 152, 153

lines = content.split('\n')
new_lines = []
for i, line in enumerate(lines):
    # Skip lines that are exactly '        ' (8 spaces) followed by newline - remove these
    if line.strip() == '' and i > 147 and i < 163:
        stripped = line.replace('        ', '').replace('    ', '')
        if stripped == '':
            continue
    new_lines.append(line)

content = '\n'.join(new_lines)

# Actually, let's just delete specific lines
lines = content.split('\n')
new_lines = []
skip = False
for i, line in enumerate(lines):
    # Line 150 (index 149) is '        \n' - 8 spaces, remove it
    if i == 149 and line.strip() == '':
        continue
    # Line 152 (index 151) is '        \n' - 8 spaces, remove it  
    if i == 151 and line.strip() == '':
        continue
    # Line 153 (index 152) is '        \n' - 8 spaces, remove it
    if i == 152 and line.strip() == '':
        continue
    new_lines.append(line)

content = '\n'.join(new_lines)

with open('engine/core.py', 'w', encoding='utf-8') as f:
    f.write(content)
    
print("Fixed empty lines in class!")
