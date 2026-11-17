import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { SUPPORT_ARTICLES, SUPPORT_CATEGORIES, SUPPORT_CONTACT } from '../packages/app-client/src/supportContent.mjs';

const destination = fileURLToPath(new URL('../docs/USER_HELP.md', import.meta.url));
const lines = ['# Jouft Help & Support', '', 'Find an answer, get unstuck, or reach the Jouft team.', '',
  `Email: [${SUPPORT_CONTACT.email}](mailto:${SUPPORT_CONTACT.email}) · Phone: [${SUPPORT_CONTACT.phone}](${SUPPORT_CONTACT.phoneUrl})`, '',
  'For a listing problem, use **Report issue** or **Report an Issue** on the listing when available. For other questions, contact the team using the details above.', ''];
for (const category of SUPPORT_CATEGORIES) {
  lines.push(`## ${category}`, '');
  for (const article of SUPPORT_ARTICLES.filter(article => article.category === category)) {
    lines.push(`### ${article.title}`, '', ...article.body.flatMap(paragraph => [paragraph, '']));
    for (const link of article.links || []) lines.push(`[${link.label}](https://jouft.com${link.path})`, '');
  }
}
lines.push('## Contact the team', '', 'Include your account email, relevant listing or trade reference, device and app/browser version, what happened, what you expected, and the steps to reproduce. Screenshots help; hide private details first.', '',
  'Never send passwords, verification codes, or full payment details. Opening an email draft does not submit a request: review and send the message yourself.', '',
  '[Privacy Policy](https://jouft.com/privacy) · [Terms](https://jouft.com/terms) · [User data deletion instructions](https://jouft.com/data-deletion)', '');
const result = lines.join('\n');
if (process.argv.includes('--check')) {
  if (readFileSync(destination, 'utf8') !== result) throw Error('User help is out of date. Run node scripts/build_user_help.mjs.');
  console.log('User help matches the shared in-app articles.');
} else { writeFileSync(destination, result); console.log('Built docs/USER_HELP.md.'); }
