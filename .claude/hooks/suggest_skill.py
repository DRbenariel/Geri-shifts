#!/usr/bin/env python
"""UserPromptSubmit hook — suggests relevant skills based on prompt keywords.

Reads the JSON event from stdin. If any keyword matches a known skill, prints
a single hint line to stdout, which Claude Code injects into the model's context.
Silent (no output) when no keywords match. Errors fail silently — never blocks
the prompt from being processed.
"""
import sys
import json

try:
    event = json.load(sys.stdin)
    prompt = (event.get('prompt') or '').lower()
except Exception:
    sys.exit(0)

# (skill-name → list of trigger keywords). Keywords are matched as substrings.
SKILLS = {
    'frontend-design':           ['html', 'css', 'react', 'design',
                                  'frontend', 'ui ', 'styling', 'tailwind',
                                  'component', 'landing page', 'dashboard',
                                  'infographic'],
    'anthropic-skills:pdf':      ['pdf', 'export to pdf', 'print to pdf',
                                  'merge pdf', 'extract pdf'],
    'hebrew-document-generator': ['pdf בעברית', 'hebrew pdf', 'חשבונית',
                                  'הצעת מחיר', 'חוזה', 'פרוטוקול'],
    'hebrew-rtl-best-practices': ['rtl', 'right-to-left', 'right to left',
                                  'bidi', 'direction:rtl'],
    'anthropic-skills:docx':     ['docx', 'word doc', 'word document', '.docx'],
    'anthropic-skills:xlsx':     ['xlsx', 'excel', 'spreadsheet', '.xlsx'],
    'anthropic-skills:pptx':     ['pptx', 'powerpoint', 'slide deck', '.pptx',
                                  'presentation', 'slides'],
    'update-config':             ['hook', 'settings.json', 'permission',
                                  'allowlist', 'env var', 'rebind', 'allow '],
    'claude-api':                ['claude api', 'anthropic sdk', 'prompt caching',
                                  'cache_control'],
    'keybindings-help':          ['keybinding', 'keyboard shortcut', 'chord'],
    'simplify':                  ['review my code', 'simplify', 'cleanup',
                                  'refactor', 'dead code'],
    'loop':                      ['every minute', 'recurring task', 'poll for'],
    'schedule':                  ['cron', 'scheduled task'],

    # Performance / debugging — surface gstack code-review skills
    'gstack-review':             ['debug', 'debugg', 'debbug', 'slow', 'slowly',
                                  'performance', 'perf', 'optimize',
                                  'bottleneck', 'lag', 'laggy', 'speed up',
                                  'why is', 'why does',
                                  'freeze', 'freezes', 'frozen',
                                  'hang', 'hangs', 'hanging', 'stuck',
                                  'crash', 'crashes', 'crashing',
                                  'doesn\'t work', 'not working', 'broken'],
    'gstack-careful':            ['scheduling algorithm', 'risky', 'careful',
                                  'don\'t break', 'do not break'],
    'gstack-qa':                 ['test this', 'qa', 'verify the app',
                                  'end-to-end', 'e2e'],
}

matches = [s for s, kws in SKILLS.items() if any(k in prompt for k in kws)]

if matches:
    print(
        "[skill-hint] The user's prompt may benefit from these skills: "
        f"{', '.join(matches)}. Consider invoking via the Skill tool."
    )
